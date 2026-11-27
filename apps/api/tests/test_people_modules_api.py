"""Employee portal sign-in, member removal, performance, training, offboarding and reports."""
from datetime import date

from app.core import email as email_mod
from tests.conftest import PASSWORD, last_token
from tests.helpers import API, mkemp, team


# ------------------------------------------------------------------ portal sign-in
def test_employee_joins_the_portal_from_an_invitation_without_creating_an_organization(signup, new_client):
    owner = signup()
    emp = mkemp(owner, first_name="Sara", last_name="Khan", email="sara@x.test")
    no_email = mkemp(owner, first_name="No", last_name="Email")
    r = owner.post(f"{API}/employees/{no_email['id']}/invite", {})
    assert r.status_code == 422 and r.json()["error"]["code"] == "email_required"
    assert owner.post(f"{API}/employees/{emp['id']}/invite", {}).status_code == 201
    assert "Set your password" in email_mod.OUTBOX[-1].body
    token = last_token("accept-invitation")
    visitor = new_client()
    info = visitor.get(f"{API}/auth/invitation", params={"token": token}).json()
    assert info == {"email": "sara@x.test", "organization": "Acme Ltd", "has_account": False}
    assert visitor.get(f"{API}/auth/invitation", params={"token": "x" * 30}).status_code == 404
    weak = visitor.post(f"{API}/auth/join", {"token": token, "full_name": "Sara Khan", "password": "short"})
    assert weak.status_code == 422 and weak.json()["error"]["code"] == "weak_password"
    assert visitor.post(f"{API}/auth/join", {"token": token, "full_name": "Sara Khan", "password": PASSWORD}).status_code == 200
    me = visitor.get(f"{API}/me").json()
    assert me["roles"] == ["employee"] and me["identity"]["email_verified"] is True
    assert [o["name"] for o in me["organizations"]] == ["Acme Ltd"]  # no organization of their own was created
    assert me["employee"]["id"] == emp["id"] and me["employee"]["full_name"] == "Sara Khan"
    assert visitor.get(f"{API}/me/employee").json()["employee_code"] == emp["employee_code"]
    assert new_client().post(f"{API}/auth/join", {"token": token, "full_name": "Eve", "password": PASSWORD}).status_code == 404
    again = owner.post(f"{API}/employees/{emp['id']}/invite", {})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_has_login"
    # signing in later works with the password they chose
    fresh = new_client()
    assert fresh.post(f"{API}/auth/login", {"email": "sara@x.test", "password": PASSWORD}).status_code == 200


def test_join_is_refused_when_an_account_exists_and_invites_cannot_escalate(signup, new_client):
    owner = signup()
    signup("has@account.test", "Their Org")
    emp = mkemp(owner, first_name="Has", last_name="Account", email="has@account.test")
    owner.post(f"{API}/employees/{emp['id']}/invite", {})
    token = last_token("accept-invitation")
    assert new_client().get(f"{API}/auth/invitation", params={"token": token}).json()["has_account"] is True
    r = new_client().post(f"{API}/auth/join", {"token": token, "full_name": "Has Account", "password": PASSWORD})
    assert r.status_code == 409 and r.json()["error"]["code"] == "account_exists"
    hr_emp = mkemp(owner, first_name="Hr", last_name="Person", email="hr@x.test")
    from tests.helpers import portal_join

    hr = portal_join(owner, new_client, hr_emp["id"], "hr_admin", name="Hr Person")
    target = mkemp(owner, first_name="New", last_name="Owner", email="newowner@x.test")
    esc = hr.post(f"{API}/employees/{target['id']}/invite", {"role_key": "owner"})
    assert esc.status_code == 403 and esc.json()["error"]["code"] == "privilege_escalation"


def test_removing_a_member_revokes_access_but_keeps_the_employee_record(signup, new_client):
    owner, worker, boss, worker_emp, _ = team(signup, new_client)
    members = {m["email"]: m for m in owner.get(f"{API}/members").json()["items"]}
    mine = members["owner@acme.test"]["membership_id"]
    assert owner.delete(f"{API}/members/{mine}").json()["error"]["code"] == "cannot_remove_self"
    assert worker.delete(f"{API}/members/{members['boss@x.test']['membership_id']}").status_code == 403
    assert owner.delete(f"{API}/members/{members['worker@x.test']['membership_id']}").status_code == 204
    assert worker.get(f"{API}/me").status_code == 401  # their session for this organization is revoked
    emp = owner.get(f"{API}/employees/{worker_emp['id']}").json()
    assert emp["has_login"] is False and emp["status"] == "active"
    assert "worker@x.test" not in {m["email"] for m in owner.get(f"{API}/members").json()["items"]}
    assert owner.post(f"{API}/employees/{worker_emp['id']}/invite", {}).status_code == 201  # can be invited again


# ------------------------------------------------------------------ performance
def test_goals_and_visibility(signup, new_client):
    owner, worker, boss, worker_emp, boss_emp = team(signup, new_client)
    g = worker.post(f"{API}/goals", {"title": "Ship the billing module", "due_date": "2026-12-31"}).json()
    assert g["progress"] == 0 and g["status"] == "active"
    assigned = boss.post(f"{API}/goals", {"title": "Mentor a junior", "employee_id": worker_emp["id"]})
    assert assigned.status_code == 201
    owner_id = owner.get(f"{API}/me/employee").json()["id"]
    assert boss.post(f"{API}/goals", {"title": "Not my report", "employee_id": owner_id}).status_code == 404
    assert worker.post(f"{API}/goals", {"title": "For my boss", "employee_id": boss_emp["id"]}).status_code == 404
    assert len(worker.get(f"{API}/goals").json()) == 2
    assert len(boss.get(f"{API}/goals", params={"scope": "team"}).json()) == 2
    assert len(boss.get(f"{API}/goals", params={"scope": "team", "employee_id": worker_emp["id"]}).json()) == 2
    assert worker.get(f"{API}/goals", params={"employee_id": boss_emp["id"]}).json() == []
    assert worker.get(f"{API}/goals", params={"scope": "team"}).status_code == 403
    done = worker.patch(f"{API}/goals/{g['id']}", {"progress": 100}).json()
    assert done["status"] == "achieved"
    assert boss.patch(f"{API}/goals/{g['id']}", {"progress": 50}).status_code == 200  # their manager may update it
    other = signup("x@other.test", "Other Org")
    assert other.patch(f"{API}/goals/{g['id']}", {"progress": 1}).status_code == 404
    assert other.delete(f"{API}/goals/{g['id']}").status_code == 404


def test_review_cycle_self_then_manager_and_hidden_rating(signup, new_client):
    owner, worker, boss, worker_emp, _ = team(signup, new_client)
    cyc = owner.post(f"{API}/review-cycles", {"name": "H2 2026", "period_start": "2026-07-01", "period_end": "2026-12-31"}).json()
    assert worker.post(f"{API}/review-cycles", {"name": "X Y Z", "period_start": "2026-07-01", "period_end": "2026-12-31"}).status_code == 403
    launched = owner.post(f"{API}/review-cycles/{cyc['id']}/launch").json()
    assert launched["status"] == "active" and launched["reviews"] == 3
    assert owner.post(f"{API}/review-cycles/{cyc['id']}/launch").status_code == 409
    mine = worker.get(f"{API}/reviews").json()[0]
    assert mine["status"] == "pending_self" and mine["reviewer"] == "Boss Lead"
    early = boss.post(f"{API}/reviews/{mine['id']}/manager", {"rating": 4, "comment": "Solid"})
    assert early.status_code == 409 and early.json()["error"]["code"] == "awaiting_self"
    assert boss.post(f"{API}/reviews/{mine['id']}/self", {"rating": 5, "comment": "Not mine"}).status_code == 404
    assert worker.post(f"{API}/reviews/{mine['id']}/self", {"rating": 4, "comment": "Delivered two launches"}).json()["status"] == "pending_manager"
    assert worker.post(f"{API}/reviews/{mine['id']}/self", {"rating": 5, "comment": "Again again"}).status_code == 409
    assert worker.post(f"{API}/reviews/{mine['id']}/manager", {"rating": 5, "comment": "Self review"}).status_code == 404
    team_list = boss.get(f"{API}/reviews", params={"scope": "team"}).json()
    assert len(team_list) == 1 and team_list[0]["self_rating"] == 4
    assert boss.post(f"{API}/reviews/{mine['id']}/manager", {"rating": 3, "comment": "Good, needs focus"}).json()["status"] == "completed"
    seen = worker.get(f"{API}/reviews").json()[0]
    assert seen["manager_rating"] == 3 and seen["manager_comment"] == "Good, needs focus"
    # the owner holds performance.manage but still cannot complete their own review
    own = owner.get(f"{API}/reviews").json()[0]
    owner.post(f"{API}/reviews/{own['id']}/self", {"rating": 4, "comment": "Own self review"})
    r = owner.post(f"{API}/reviews/{own['id']}/manager", {"rating": 5, "comment": "Own manager review"})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    assert owner.post(f"{API}/review-cycles/{cyc['id']}/close").json()["status"] == "closed"
    boss_review = boss.get(f"{API}/reviews").json()[0]
    late = boss.post(f"{API}/reviews/{boss_review['id']}/self", {"rating": 4, "comment": "Too late"})
    assert late.status_code == 409 and late.json()["error"]["code"] == "cycle_closed"


def test_manager_rating_stays_hidden_until_the_review_is_complete(signup, new_client, db):
    from sqlalchemy import select

    from app.db.tenant_scope import ALL_TENANTS, tenant_scope
    from app.modules.performance.models import Review

    owner, worker, boss, *_ = team(signup, new_client)
    cyc = owner.post(f"{API}/review-cycles", {"name": "Q4 2026", "period_start": "2026-10-01", "period_end": "2026-12-31"}).json()
    owner.post(f"{API}/review-cycles/{cyc['id']}/launch")
    mine = worker.get(f"{API}/reviews").json()[0]
    with tenant_scope(db, ALL_TENANTS):  # a draft rating saved before completion
        row = db.scalar(select(Review).where(Review.id == __import__("uuid").UUID(mine["id"])))
        row.manager_rating, row.manager_comment = 2, "draft"
        db.commit()
    assert worker.get(f"{API}/reviews").json()[0]["manager_rating"] is None
    assert worker.get(f"{API}/reviews").json()[0]["manager_comment"] is None


# ------------------------------------------------------------------ training
def test_courses_assignment_and_completion(signup, new_client):
    owner, worker, boss, worker_emp, _ = team(signup, new_client)
    c = owner.post(f"{API}/courses", {"title": "Information security basics", "mandatory": True, "duration_hours": "1.5",
                                      "url": "https://example.com/security"}).json()
    assert owner.post(f"{API}/courses", {"title": "Bad link", "url": "javascript:alert(1)"}).status_code == 422
    assert worker.post(f"{API}/courses", {"title": "Mine mine"}).status_code == 403
    assert owner.post(f"{API}/courses/{c['id']}/assign", {}).status_code == 422
    r = owner.post(f"{API}/courses/{c['id']}/assign", {"employee_ids": [worker_emp["id"]], "due_date": "2026-11-30"})
    assert r.json()["assigned"] == 1
    assert owner.post(f"{API}/courses/{c['id']}/assign", {"everyone": True}).json()["assigned"] == 2  # not the worker again
    mine = worker.get(f"{API}/enrollments").json()
    assert len(mine) == 1 and mine[0]["mandatory"] is True and mine[0]["status"] == "assigned"
    done = worker.patch(f"{API}/enrollments/{mine[0]['id']}", {"status": "completed"}).json()
    assert done["status"] == "completed" and done["completed_on"] == date.today().isoformat()
    assert boss.patch(f"{API}/enrollments/{mine[0]['id']}", {"status": "assigned"}).status_code == 404
    c2 = owner.post(f"{API}/courses", {"title": "Presentation skills"}).json()
    assert worker.post(f"{API}/courses/{c2['id']}/enroll").status_code == 201
    assert worker.post(f"{API}/courses/{c2['id']}/enroll").status_code == 409
    stats = {x["title"]: x for x in owner.get(f"{API}/courses").json()}
    assert stats["Information security basics"]["enrolled"] == 3 and stats["Information security basics"]["completed"] == 1
    assert worker.get(f"{API}/enrollments", params={"scope": "all"}).status_code == 403
    other = signup("x@other.test", "Other Org")
    assert other.post(f"{API}/courses/{c['id']}/enroll").status_code == 404
    assert other.get(f"{API}/courses").json() == []


# ------------------------------------------------------------------ offboarding
def test_exit_needs_clearance_then_marks_the_employee_left_and_revokes_access(signup, new_client):
    owner, worker, boss, worker_emp, _ = team(signup, new_client)
    asset = owner.post(f"{API}/assets", {"name": "Laptop", "category": "Laptop", "serial_number": "L-1"}).json()
    owner.post(f"{API}/assets/{asset['id']}/assign", {"employee_id": worker_emp["id"], "assigned_on": "2026-11-01"})
    loan = worker.post(f"{API}/loans", {"kind": "advance", "principal": "10000", "installments": 1}).json()
    owner.post(f"{API}/loans/{loan['id']}/decision", {"approve": True})
    owner.post(f"{API}/loans/{loan['id']}/disburse", {"disbursed_on": "2026-11-02", "first_due_month": "2026-12"})
    body = {"employee_id": worker_emp["id"], "kind": "resignation", "notice_date": "2026-11-10", "last_working_day": "2026-12-10",
            "reason": "Moving abroad"}
    assert boss.post(f"{API}/offboarding", body).status_code == 403
    assert owner.post(f"{API}/offboarding", {**body, "last_working_day": "2026-11-01"}).status_code == 422
    off = owner.post(f"{API}/offboarding", body).json()
    assert off["items_total"] == 6 and off["items_done"] == 0
    assert owner.post(f"{API}/offboarding", body).json()["error"]["code"] == "already_open"
    d = owner.get(f"{API}/offboarding/{off['id']}").json()
    assert len(d["open_assets"]) == 1 and float(d["loan_balance"]) == 10000
    blocked = owner.post(f"{API}/offboarding/{off['id']}/complete")
    assert blocked.status_code == 409 and len(blocked.json()["error"]["details"]) == 3
    for item in d["items"]:
        owner.patch(f"{API}/offboarding/{off['id']}/items/{item['id']}", {"done": True})
    owner.post(f"{API}/assets/{asset['id']}/return", {"returned_on": "2026-12-09", "condition": "good"})
    still = owner.post(f"{API}/offboarding/{off['id']}/complete")
    assert still.status_code == 409 and still.json()["error"]["details"] == ["a loan balance is outstanding"]
    owner.post(f"{API}/loans/{loan['id']}/repay", {"settle_all": True})
    assert owner.patch(f"{API}/offboarding/{off['id']}", {"exit_interview": "Left for relocation.",
                                                          "settlement": {"leave_encashment_days": "3", "notice_pay": "0"}}).status_code == 200
    assert worker.get(f"{API}/me/employee").status_code == 200  # still has access until the exit completes
    done = owner.post(f"{API}/offboarding/{off['id']}/complete").json()
    assert done == {"id": off["id"], "status": "completed", "access_revoked": True}
    emp = owner.get(f"{API}/employees/{worker_emp['id']}").json()
    assert emp["status"] == "resigned" and emp["exit_date"] == "2026-12-10"
    assert worker.get(f"{API}/me").status_code == 401
    assert owner.post(f"{API}/offboarding/{off['id']}/complete").status_code == 409
    kinds = [e["event_type"] for e in owner.get(f"{API}/employees/{worker_emp['id']}/history").json()["events"]]
    assert "resignation" in kinds
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/offboarding/{off['id']}").status_code == 404
    assert other.get(f"{API}/offboarding").json() == []


# ------------------------------------------------------------------ reports
def test_reports_respect_scope_and_permissions(signup, new_client):
    owner, worker, boss, worker_emp, boss_emp = team(signup, new_client)
    owner.post(f"{API}/attendance/check-in")
    owner.post(f"{API}/leave/grants/run", params={"year": date.today().year})
    head = owner.get(f"{API}/reports/headcount").json()
    assert head["total"] == 3 and len(head["movement"]) == 12 and sum(m["joined"] for m in head["movement"]) >= 1
    assert boss.get(f"{API}/reports/headcount").json()["total"] == 2  # a manager sees their own team only
    assert worker.get(f"{API}/reports/headcount").status_code == 403
    month = date.today().strftime("%Y-%m")
    rows = owner.get(f"{API}/reports/attendance", params={"month": month}).json()["rows"]
    assert len(rows) == 3 and {"present_days", "late_minutes", "worked_hours", "absent_days"} <= set(rows[0])
    assert len(boss.get(f"{API}/reports/attendance", params={"month": month}).json()["rows"]) == 2
    leave = owner.get(f"{API}/reports/leave", params={"year": date.today().year}).json()["rows"]
    assert leave and {"entitled", "used", "pending", "available"} <= set(leave[0])
    assert owner.get(f"{API}/reports/payroll", params={"year": date.today().year}).json()["runs"] == []
    assert boss.get(f"{API}/reports/payroll", params={"year": date.today().year}).status_code == 403
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/reports/headcount").json()["total"] == 1
