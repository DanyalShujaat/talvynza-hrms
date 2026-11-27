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


def test_punch_after_shift_window_updates_the_current_workday(signup, monkeypatch):
    from app.modules.attendance import router, service

    owner = signup()
    late = datetime.fromisoformat(utc(date.today(), 23, 30))
    monkeypatch.setattr(service, "utcnow", lambda: late)
    monkeypatch.setattr(router, "utcnow", lambda: late)
    check_in = owner.post(f"{API}/attendance/mobile/check-in")
    assert check_in.status_code == 200 and check_in.json()["first_in"] is not None
    today = owner.get(f"{API}/attendance/today").json()
    assert today["work_date"] == late.date().isoformat() and today["state"] == "in"
    late += timedelta(minutes=10)
    check_out = owner.post(f"{API}/attendance/mobile/check-out")
    assert check_out.status_code == 200 and check_out.json()["worked_minutes"] == 10


def test_branch_premises_gate_both_punches_and_removal_allows_anywhere(signup, new_client):
    owner, worker, _, emp = setup(signup, new_client)
    premises = f"{API}/branches/{emp['branch_id']}/premises"
    check_in, check_out = f"{API}/attendance/mobile/check-in", f"{API}/attendance/mobile/check-out"
    first = {"name": "Main entrance", "latitude": 34, "longitude": 71, "radius_m": 100}
    second = {"name": "Annex", "latitude": 34.01, "longitude": 71, "radius_m": 80}
    inside = {"latitude": 34.01, "longitude": 71, "accuracy_m": 5}
    outside = {"latitude": 35, "longitude": 71, "accuracy_m": 5}
    assert worker.get(premises).status_code == 403
    assert worker.put(premises, {"premises": [first]}).status_code == 403
    assert owner.put(premises, {"premises": [{**first, "radius_m": 0}]}).status_code == 422
    assert owner.put(premises, {"premises": [first, {**first, "name": "MAIN ENTRANCE"}]}).status_code == 422
    assert owner.get(premises).json() == {"premises": []}
    assert owner.put(premises, {"premises": [first, second]}).status_code == 200
    assert owner.get(premises).json() == {"premises": [first, second]}
    assert worker.get(f"{API}/attendance/today").json()["location_required"] is True
    assert worker.post(f"{API}/attendance/check-in", {"location": inside}).json()["error"]["code"] == "web_blocked_by_premises"
    assert worker.post(check_in).json()["error"]["code"] == "location_required"
    assert worker.post(check_in, {"location": outside}).json()["error"]["code"] == "outside_premises"
    assert worker.post(check_in, {"location": {**inside, "accuracy_m": 200}}).json()["error"]["code"] == "location_inaccurate"
    assert worker.post(check_in, {"location": inside}).status_code == 200
    assert worker.post(f"{API}/attendance/check-out").json()["error"]["code"] == "web_blocked_by_premises"
    assert worker.post(check_out).json()["error"]["code"] == "location_required"
    assert worker.post(check_out, {"location": outside}).json()["error"]["code"] == "outside_premises"
    assert owner.put(premises, {"premises": []}).status_code == 200
    assert worker.get(f"{API}/attendance/today").json()["location_required"] is False
    assert worker.post(check_out).status_code == 200


def test_biometric_import_uses_the_selected_branch_and_employee_access(signup):
    owner = signup()
    first = mkemp(owner, first_name="Main worker", bio_id="23")
    annex = owner.post(f"{API}/branches", {"name": "Annex"}).json()
    second = mkemp(owner, first_name="Annex worker", branch_id=annex["id"], bio_id="23")
    csv = f"bio_id,timestamp,kind\n23,{PAST.isoformat()}T17:00:00,out\n23,{PAST.isoformat()}T09:00:00,in\n"

    def upload(branch):
        return owner.post(f"{API}/attendance/import", files={"file": ("p.csv", io.BytesIO(csv.encode()), "text/csv")},
                          data={"branch_id": branch} if branch else {})

    assert upload(None).status_code == 422
    assert owner.patch(f"{API}/attendance/access", {
        "channel": "premises", "enabled": False, "employee_ids": [second["id"]],
    }).status_code == 200
    assert upload(annex["id"]).json()["errors"][0]["error"] == "premises attendance is disabled for this employee"
    assert upload(first["branch_id"]).json()["imported"] == 2
    assert upload(first["branch_id"]).json()["duplicates_ignored"] == 2
    for emp, days in ((first, 1), (second, 0)):
        report = owner.get(f"{API}/attendance/me", params={"employee_id": emp["id"], "month": PAST.strftime("%Y-%m")})
        assert len(report.json()["days"]) == days


def test_bulk_attendance_access_intersects_filters_and_requires_explicit_scope(signup, new_client):
    owner, worker, _, emp = setup(signup, new_client)
    other_branch = owner.post(f"{API}/branches", {"name": "Annex"}).json()
    other_dept = owner.post(f"{API}/departments", {"name": "Support"}).json()
    branch_only = mkemp(owner, first_name="BranchOnly", branch_id=emp["branch_id"], department_id=other_dept["id"])
    department_only = mkemp(owner, first_name="DepartmentOnly", branch_id=other_branch["id"],
                            department_id=emp["department_id"])
    path = f"{API}/attendance/access"
    scope = {"branch_id": emp["branch_id"], "department_id": emp["department_id"]}
    assert owner.patch(path, {"enabled": False}).status_code == 422
    assert owner.patch(path, {**scope, "enabled": False, "all_employees": True}).status_code == 422
    assert worker.get(path, params=scope).status_code == 403
    assert worker.patch(path, {**scope, "enabled": False}).status_code == 403
    preview = owner.get(path, params=scope).json()
    assert preview["total"] == preview["enabled"] == 2
    assert owner.patch(path, {**scope, "enabled": False}).json() == {"matched": 2, "changed": 2}
    assert owner.patch(path, {**scope, "enabled": False}).json() == {"matched": 2, "changed": 0}
    assert worker.post(f"{API}/attendance/check-in").json()["error"]["code"] == "attendance_disabled"
    assert worker.get(f"{API}/attendance/today").json()["channels"] == {"web": False, "mobile": True, "premises": True}
    for e in (branch_only, department_only):
        assert owner.get(f"{API}/attendance/employees/{e['id']}/settings").json()["attendance_enabled"] is True
    assert owner.patch(path, {"employee_ids": [emp["id"]], "enabled": True}).json() == {"matched": 1, "changed": 1}
    assert worker.post(f"{API}/attendance/check-in").status_code == 200
    assert owner.patch(path, {"all_employees": True, "enabled": True}).json()["changed"] == 1


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
    path = f"{API}/attendance/employees/{emp['id']}/settings"
    settings = boss.get(path).json()
    assert settings["shift"] == "Night" and settings["start"] == "22:00" and settings["end"] == "06:00"
    assert worker.get(path).status_code == 200
    assert worker.get(f"{API}/attendance/employees/{my_employee_id(boss)}/settings").status_code == 404
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
