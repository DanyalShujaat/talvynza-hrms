from datetime import date
from decimal import Decimal as Dec

from tests.helpers import API, join, mkemp, my_employee_id, next_weekday

YEAR = 2031
MON = next_weekday(date(YEAR, 3, 1), 0)  # a Monday in March 2031


def types(api):
    return {t["name"]: t["id"] for t in api.get(f"{API}/leave/types").json()}


def bal(api, name, eid=None, year=YEAR):
    params = {"year": year, **({"employee_id": eid} if eid else {})}
    return next(b for b in api.get(f"{API}/leave/balances", params=params).json() if b["name"] == name)


def apply(api, type_id, start, end=None, **kw):
    return api.post(f"{API}/leave/requests", {"leave_type_id": type_id, "start_date": start.isoformat(),
                                             "end_date": (end or start).isoformat(), **kw})


def setup(signup, new_client):
    owner = signup()
    emp = mkemp(owner, first_name="Worker", email="w@x.test")
    boss = mkemp(owner, first_name="Boss", email="boss@x.test")
    owner.patch(f"{API}/employees/{emp['id']}", {"manager_id": boss["id"]})
    owner.post(f"{API}/leave/grants/run", params={"year": YEAR})
    worker = join(owner, new_client, "w@x.test", "employee")
    boss_api = join(owner, new_client, "boss@x.test", "reporting_manager")
    return owner, worker, boss_api, emp


def test_default_types_and_balance_breakdown(signup):
    owner = signup()
    assert {"Annual Leave", "Casual Leave", "Sick Leave", "Unpaid Leave"} <= set(types(owner))
    owner.post(f"{API}/leave/grants/run", params={"year": YEAR})
    b = bal(owner, "Annual Leave")
    assert (b["entitled"], b["used"], b["reserved"], b["available"]) == (Dec("20"), 0, 0, Dec("20"))


def test_apply_reserves_then_approve_converts_to_used(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    tid = types(worker)["Casual Leave"]
    r = apply(worker, tid, MON, MON.replace(day=MON.day + 2), reason="family")  # Mon to Wed = 3 working days
    assert r.status_code == 201 and Dec(r.json()["days"]) == 3
    assert any("Leave request from" in n["title"] for n in boss.get(f"{API}/notifications").json()["items"])
    b = bal(worker, "Casual Leave")
    assert (b["entitled"], b["used"], b["reserved"], b["available"]) == (Dec("10"), 0, Dec("3"), Dec("7"))
    rid = r.json()["id"]
    assert boss.post(f"{API}/leave/requests/{rid}/decision", {"approve": True}).status_code == 200
    assert any("leave request was approved" in n["title"] for n in worker.get(f"{API}/notifications").json()["items"])
    b = bal(worker, "Casual Leave")
    assert (b["used"], b["reserved"], b["available"]) == (Dec("3"), 0, Dec("7"))
    ledger = [e["entry_type"] for e in worker.get(f"{API}/leave/ledger").json()]
    assert {"grant", "reserved", "released", "used"} <= set(ledger)  # auditable trail, not a mutable total


def test_reject_and_cancel_release_the_reservation(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    tid = types(worker)["Casual Leave"]
    r1 = apply(worker, tid, MON).json()
    boss.post(f"{API}/leave/requests/{r1['id']}/decision", {"approve": False, "note": "busy week"})
    assert bal(worker, "Casual Leave")["available"] == Dec("10")
    r2 = apply(worker, tid, MON).json()
    assert worker.post(f"{API}/leave/requests/{r2['id']}/cancel").status_code == 200
    assert bal(worker, "Casual Leave")["available"] == Dec("10")
    assert worker.post(f"{API}/leave/requests/{r2['id']}/cancel").status_code == 409


def test_cancelling_an_approved_future_leave_restores_the_balance(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    rid = apply(worker, types(worker)["Casual Leave"], MON).json()["id"]
    boss.post(f"{API}/leave/requests/{rid}/decision", {"approve": True})
    assert bal(worker, "Casual Leave")["available"] == Dec("9")
    assert worker.post(f"{API}/leave/requests/{rid}/cancel").status_code == 200
    assert bal(worker, "Casual Leave")["available"] == Dec("10")


def test_negative_balance_is_blocked_unless_the_type_allows_it(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    long = apply(worker, types(worker)["Casual Leave"], MON, date(YEAR, 3, 28))
    assert long.status_code == 409 and long.json()["error"]["code"] == "insufficient_balance"
    unpaid = apply(worker, types(worker)["Unpaid Leave"], MON, date(YEAR, 3, 28))
    assert unpaid.status_code == 201  # unpaid leave allows going negative by design


def test_overlapping_requests_are_rejected(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    tid = types(worker)["Casual Leave"]
    assert apply(worker, tid, MON).status_code == 201
    dup = apply(worker, tid, MON)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "overlapping_leave"


def test_weekends_and_holidays_do_not_count(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    tid = types(worker)["Casual Leave"]
    assert Dec(apply(worker, tid, MON, MON.replace(day=MON.day + 6)).json()["days"]) == 5  # Mon..Sun
    only_weekend = apply(worker, tid, date(YEAR, 3, 8), date(YEAR, 3, 9))
    assert only_weekend.status_code == 422 and only_weekend.json()["error"]["code"] == "no_working_days"
    owner.post(f"{API}/holidays", {"holiday_date": date(YEAR, 3, 17).isoformat(), "name": "Test Holiday"})
    r = apply(worker, tid, date(YEAR, 3, 17), date(YEAR, 3, 18))  # Mon holiday + Tue
    assert Dec(r.json()["days"]) == 1


def test_half_day(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    r = apply(worker, types(worker)["Casual Leave"], MON, half_day=True)
    assert Dec(r.json()["days"]) == Dec("0.5")
    assert apply(worker, types(worker)["Sick Leave"], MON.replace(day=MON.day + 7),
                 MON.replace(day=MON.day + 8), half_day=True).status_code == 422


def test_self_approval_and_outsider_approval_are_blocked(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    rid = apply(worker, types(worker)["Casual Leave"], MON).json()["id"]
    assert worker.post(f"{API}/leave/requests/{rid}/decision", {"approve": True}).status_code == 403  # no leave.approve
    # a manager cannot approve their own request even though they hold leave.approve
    mine = apply(boss, types(boss)["Casual Leave"], MON).json()["id"]
    r = boss.post(f"{API}/leave/requests/{mine}/decision", {"approve": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    # a manager who is not this person's manager sees nothing
    stranger = join(owner, new_client, "s@x.test", "reporting_manager", name="Stranger")
    assert stranger.post(f"{API}/leave/requests/{rid}/decision", {"approve": True}).status_code == 404
    # already decided
    assert boss.post(f"{API}/leave/requests/{rid}/decision", {"approve": True}).status_code == 200
    again = boss.post(f"{API}/leave/requests/{rid}/decision", {"approve": False})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_decided"


def test_request_scopes_team_and_all(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    apply(worker, types(worker)["Casual Leave"], MON)
    assert len(boss.get(f"{API}/leave/requests", params={"scope": "team"}).json()) == 1
    assert worker.get(f"{API}/leave/requests", params={"scope": "team"}).status_code == 403
    assert worker.get(f"{API}/leave/requests", params={"scope": "all"}).status_code == 403
    assert len(owner.get(f"{API}/leave/requests", params={"scope": "all"}).json()) == 1
    selected = boss.get(f"{API}/leave/requests", params={"scope": "team", "employee_id": emp["id"]}).json()
    assert len(selected) == 1 and selected[0]["employee_id"] == emp["id"]
    assert worker.get(f"{API}/leave/requests", params={"employee_id": my_employee_id(boss)}).json() == []
    month = boss.get(f"{API}/leave/calendar", params={"month": f"{YEAR}-03"}).json()
    assert len(month) == 1 and month[0]["status"] == "pending"
    assert worker.get(f"{API}/leave/balances", params={"employee_id": my_employee_id(boss)}).status_code == 404


def test_grants_are_prorated_and_idempotent(signup):
    owner = signup()
    mkemp(owner, first_name="Late", email="late@x.test", joining_date=f"{YEAR}-07-01")
    first = owner.post(f"{API}/leave/grants/run", params={"year": YEAR}).json()["entries_created"]
    again = owner.post(f"{API}/leave/grants/run", params={"year": YEAR}).json()["entries_created"]
    assert first > 0 and again == 0
    emp_id = next(e["id"] for e in owner.get(f"{API}/employees", params={"q": "late"}).json()["items"])
    # joined July 1: 6 of 12 months left, 20 * 6/12 = 10
    assert bal(owner, "Annual Leave", emp_id)["entitled"] == Dec("10")


def test_carry_forward_is_capped_and_year_scoped(signup):
    owner = signup()
    owner.post(f"{API}/leave/grants/run", params={"year": YEAR})
    owner.post(f"{API}/leave/grants/run", params={"year": YEAR + 1})
    assert owner.post(f"{API}/leave/carry-forward", params={"from_year": YEAR}).json()["entries_created"] >= 1
    assert owner.post(f"{API}/leave/carry-forward", params={"from_year": YEAR}).json()["entries_created"] == 0
    assert bal(owner, "Annual Leave", year=YEAR + 1)["entitled"] == Dec("25")  # 20 + cap of 5
    assert bal(owner, "Casual Leave", year=YEAR + 1)["entitled"] == Dec("10")  # no carry configured
    assert bal(owner, "Annual Leave", year=YEAR)["entitled"] == Dec("20")  # previous year untouched


def test_probation_restriction(signup, new_client):
    owner = signup()
    mkemp(owner, first_name="New", email="new@x.test", probation_end="2027-12-31")
    owner.post(f"{API}/leave/grants/run", params={"year": YEAR})
    new = join(owner, new_client, "new@x.test", "employee")
    r = apply(new, types(new)["Annual Leave"], MON)
    assert r.status_code == 409 and r.json()["error"]["code"] == "probation_restricted"
    assert apply(new, types(new)["Casual Leave"], MON).status_code == 201


def test_manual_adjustment_and_permissions(signup, new_client):
    owner, worker, boss, emp = setup(signup, new_client)
    assert worker.post(f"{API}/leave/adjustments", {"employee_id": emp["id"], "leave_type_id": types(worker)["Casual Leave"],
                                                    "days": "5", "note": "x"}).status_code == 403
    r = owner.post(f"{API}/leave/adjustments", {"employee_id": emp["id"], "leave_type_id": types(owner)["Casual Leave"],
                                                "days": "2", "note": "compensatory day"})
    assert r.status_code == 201
    year = date.today().year
    assert bal(worker, "Casual Leave", year=year)["entitled"] == Dec("2")


def test_leave_is_tenant_isolated(signup, new_client):
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    ea = mkemp(a, first_name="Ann", email="ann@a.test")
    a.post(f"{API}/leave/grants/run", params={"year": YEAR})
    assert b.get(f"{API}/leave/balances", params={"employee_id": ea["id"]}).status_code == 404
    rid = apply(a, types(a)["Casual Leave"], MON).json()["id"]
    assert b.post(f"{API}/leave/requests/{rid}/decision", {"approve": True}).status_code == 404
    assert b.post(f"{API}/leave/requests/{rid}/cancel").status_code == 404
    assert b.get(f"{API}/leave/requests", params={"scope": "all"}).json() == []
