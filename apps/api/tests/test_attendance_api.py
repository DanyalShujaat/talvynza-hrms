import io
from datetime import date, datetime, timedelta, timezone

from tests.helpers import API, join, mkemp, my_employee_id

PAST = (date.today() - timedelta(days=10))
while PAST.weekday() >= 5:
    PAST -= timedelta(days=1)


def utc(d, h, m):
    """Asia/Karachi (UTC+5) local time to an aware ISO string."""
    return (datetime(d.year, d.month, d.day, h, m, tzinfo=timezone(timedelta(hours=5)))).isoformat()


def setup(signup, new_client):
    owner = signup()
    emp = mkemp(owner, first_name="Worker", email="w@x.test")
    boss = mkemp(owner, first_name="Boss", email="boss@x.test")
    owner.patch(f"{API}/employees/{emp['id']}", {"manager_id": boss["id"]})
    return owner, join(owner, new_client, "w@x.test", "employee"), join(owner, new_client, "boss@x.test", "reporting_manager"), emp


def test_check_in_and_out_create_a_daily_summary(signup):
    owner = signup()
    assert owner.get(f"{API}/attendance/today").json()["state"] == "out"
    r = owner.post(f"{API}/attendance/check-in")
    assert r.status_code == 200 and r.json()["first_in"]
    assert owner.get(f"{API}/attendance/today").json()["state"] == "in"
    out = owner.post(f"{API}/attendance/check-out")
    assert out.status_code == 200 and out.json()["last_out"]
    assert owner.get(f"{API}/attendance/today").json()["state"] == "out"


def test_double_check_in_and_checkout_without_checkin_are_refused(signup):
    owner = signup()
    assert owner.post(f"{API}/attendance/check-out").json()["error"]["code"] == "not_checked_in"
    owner.post(f"{API}/attendance/check-in")
    r = owner.post(f"{API}/attendance/check-in")
    assert r.status_code == 409 and r.json()["error"]["code"] == "already_checked_in"


def test_policy_roundtrip_and_permission(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    pol = owner.get(f"{API}/attendance/policy").json()
    assert pol["grace_minutes"] == 10 and pol["late_mode"] == "grace_exempt" and pol["weekend_days"] == [5, 6]
    pol.update(grace_minutes=15, late_mode="full")
    assert owner.put(f"{API}/attendance/policy", pol).status_code == 200
    assert owner.get(f"{API}/attendance/policy").json()["late_mode"] == "full"
    assert worker.put(f"{API}/attendance/policy", pol).status_code == 403
    pol["weekend_days"] = [9]
    assert owner.put(f"{API}/attendance/policy", pol).status_code == 422


def test_manual_entry_applies_the_configured_late_policy(signup):
    owner = signup()
    eid = my_employee_id(owner)
    pol = owner.get(f"{API}/attendance/policy").json()
    pol.update(default_start="09:30", default_end="18:00", grace_minutes=10, late_mode="full")
    owner.put(f"{API}/attendance/policy", pol)
    owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "in", "occurred_at": utc(PAST, 9, 45)})
    r = owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "out", "occurred_at": utc(PAST, 18, 0)})
    assert r.json()["late_minutes"] == 15 and r.json()["status"] == "present"
    pol["late_mode"] = "grace_exempt"
    owner.put(f"{API}/attendance/policy", pol)
    owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "in", "occurred_at": utc(PAST, 9, 46)})
    month = owner.get(f"{API}/attendance/me", params={"month": PAST.strftime("%Y-%m")}).json()
    assert month["days"][0]["late_minutes"] == 5  # recalculated under the new mode (first_in is still 9:45 -> 5)
    assert owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "in", "occurred_at": "2026-01-01T10:00:00"}).status_code == 422


def test_correction_request_approval_updates_attendance_and_blocks_self_approval(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    r = worker.post(f"{API}/attendance/adjustments", {"work_date": PAST.isoformat(), "in_time": "09:00", "out_time": "18:00",
                                                     "reason": "Forgot to check in"})
    assert r.status_code == 201
    aid = r.json()["id"]
    dup = worker.post(f"{API}/attendance/adjustments", {"work_date": PAST.isoformat(), "in_time": "09:00", "reason": "again"})
    assert dup.status_code == 409
    assert worker.post(f"{API}/attendance/adjustments/{aid}/decision", {"approve": True}).status_code == 403
    pending = boss.get(f"{API}/attendance/adjustments", params={"scope": "team", "status": "pending"}).json()
    assert len(pending) == 1
    assert any("Time adjustment from" in n["title"] for n in boss.get(f"{API}/notifications").json()["items"])
    assert boss.post(f"{API}/attendance/adjustments/{aid}/decision", {"approve": True}).status_code == 200
    assert any("time adjustment was approved" in n["title"] for n in worker.get(f"{API}/notifications").json()["items"])
    day = worker.get(f"{API}/attendance/me", params={"month": PAST.strftime("%Y-%m")}).json()["days"]
    assert day[0]["status"] == "present" and day[0]["worked_minutes"] > 0
    again = boss.post(f"{API}/attendance/adjustments/{aid}/decision", {"approve": False})
    assert again.status_code == 409


def test_manager_cannot_approve_their_own_correction_or_a_strangers(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    mine = boss.post(f"{API}/attendance/adjustments", {"work_date": PAST.isoformat(), "in_time": "09:00", "reason": "x y z"}).json()["id"]
    r = boss.post(f"{API}/attendance/adjustments/{mine}/decision", {"approve": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    other = join(owner, new_client, "o@x.test", "reporting_manager", name="Other Manager")
    wid = worker.post(f"{API}/attendance/adjustments", {"work_date": PAST.isoformat(), "in_time": "09:00", "reason": "x y z"}).json()["id"]
    assert other.post(f"{API}/attendance/adjustments/{wid}/decision", {"approve": True}).status_code == 404
    assert worker.post(f"{API}/attendance/adjustments", {"work_date": (date.today() + timedelta(days=3)).isoformat(),
                                                        "in_time": "09:00", "reason": "future"}).status_code == 422
    assert worker.post(f"{API}/attendance/adjustments", {"work_date": PAST.isoformat(), "reason": "no times"}).status_code == 422


def test_team_attendance_view_scope(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    worker.post(f"{API}/attendance/check-in")
    team = boss.get(f"{API}/attendance/daily", params={"date": date.today().isoformat()}).json()
    assert {t["full_name"].split()[0] for t in team} == {"Boss", "Worker"}
    assert worker.get(f"{API}/attendance/daily", params={"date": date.today().isoformat()}).status_code == 403
    everyone = owner.get(f"{API}/attendance/daily", params={"date": date.today().isoformat()}).json()
    assert len(everyone) == 3
    assert worker.get(f"{API}/attendance/me", params={"month": date.today().strftime("%Y-%m"),
                                                      "employee_id": my_employee_id(owner)}).status_code == 404


def test_csv_import_dedupes_and_reports_bad_rows(signup):
    owner = signup()
    d = PAST.isoformat()
    csv = (f"employee_code,timestamp\n1001,{d}T09:00:00+05:00\n1001,{d}T18:00:00+05:00\n"
           f"1001,{d}T09:00:00+05:00\n9999,{d}T09:00:00+05:00\n1001,garbage\n")
    r = owner.post(f"{API}/attendance/import", files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")})
    assert r.status_code == 200
    body = r.json()
    assert body["imported"] == 2 and body["duplicates_ignored"] == 1 and len(body["errors"]) == 2
    day = owner.get(f"{API}/attendance/me", params={"month": PAST.strftime("%Y-%m")}).json()["days"]
    assert day[0]["worked_minutes"] == 9 * 60 - 60  # one continuous span minus the 60 minute default break


def test_shift_crud_assignment_and_roster(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    night = owner.post(f"{API}/shifts", {"name": "Night", "start_time": "22:00", "end_time": "06:00"}).json()
    assert night["overnight"] is True
    assert owner.post(f"{API}/shifts", {"name": "Night", "start_time": "22:00", "end_time": "06:00"}).status_code == 409
    assert owner.post(f"{API}/shifts", {"name": "Zero", "start_time": "08:00", "end_time": "08:00"}).status_code == 422
    assert worker.post(f"{API}/shifts", {"name": "X", "start_time": "08:00", "end_time": "16:00"}).status_code == 403
    r = owner.post(f"{API}/shifts/assign", {"shift_id": night["id"], "employee_ids": [emp["id"]],
                                           "effective_from": "2026-01-01"})
    assert r.json()["assigned"] == 1
    assert any("Shift assigned: Night" in n["title"] for n in worker.get(f"{API}/notifications").json()["items"])
    roster = {x["full_name"].split()[0]: x["shift"] for x in owner.get(f"{API}/shifts/roster").json()}
    assert roster["Worker"] == "Night"
    assert owner.delete(f"{API}/shifts/{night['id']}").status_code == 409  # in use
    assert owner.post(f"{API}/shifts/assign", {"shift_id": night["id"], "effective_from": "2026-01-01"}).status_code == 422


def test_overnight_punches_belong_to_the_shift_start_date(signup):
    owner = signup()
    eid = my_employee_id(owner)
    night = owner.post(f"{API}/shifts", {"name": "Night", "start_time": "22:00", "end_time": "06:00"}).json()
    owner.post(f"{API}/shifts/assign", {"shift_id": night["id"], "employee_ids": [eid], "effective_from": "2026-01-01"})
    d = PAST
    owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "in", "occurred_at": utc(d, 22, 0)})
    r = owner.post(f"{API}/attendance/manual", {"employee_id": eid, "kind": "out", "occurred_at": utc(d + timedelta(days=1), 6, 5)})
    assert r.json()["work_date"] == d.isoformat() and r.json()["worked_minutes"] == 8 * 60 + 5
    assert r.json()["status"] == "present"


def test_attendance_is_tenant_isolated(signup):
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    ea = my_employee_id(a)
    a.post(f"{API}/attendance/check-in")
    assert b.get(f"{API}/attendance/me", params={"month": date.today().strftime("%Y-%m"), "employee_id": ea}).status_code == 404
    assert b.post(f"{API}/attendance/manual", {"employee_id": ea, "kind": "in", "occurred_at": utc(PAST, 9, 0)}).status_code == 404
    assert all(x["employee_id"] != ea for x in b.get(f"{API}/attendance/daily", params={"date": date.today().isoformat()}).json())
