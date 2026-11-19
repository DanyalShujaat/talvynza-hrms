"""Expenses, loans, assets and the help desk."""
import io
from datetime import date
from decimal import Decimal as D

from app.modules.loans.router import schedule
from tests.helpers import API, mkemp, portal_join, team


def cats(api):
    return {c["name"]: c["id"] for c in api.get(f"{API}/expenses/categories").json()}


def claim(api, category_id, amount="3000", receipt=False, **kw):
    files = {"receipt": ("r.pdf", io.BytesIO(b"%PDF-1.4 receipt"), "application/pdf")} if receipt else None
    return api.post(f"{API}/expenses", files=files, data={"category_id": category_id, "amount": amount,
                                                           "expense_date": "2026-11-02", "description": "Team lunch", **kw})


# ------------------------------------------------------------------ expenses
def test_expense_policy_checks(signup, new_client, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    owner, worker, boss, *_ = team(signup, new_client)
    c = cats(worker)
    over = claim(worker, c["Meals"], "6000")
    assert over.status_code == 422 and over.json()["error"]["code"] == "over_limit"
    assert claim(worker, c["Travel"]).json()["error"]["code"] == "receipt_required"
    assert claim(worker, c["Travel"], receipt=True).status_code == 201
    assert worker.post(f"{API}/expenses", data={"category_id": c["Meals"], "amount": "10", "expense_date": "2999-01-01",
                                                "description": "future"}).status_code == 422
    assert worker.post(f"{API}/expenses/categories", {"name": "Perks"}).status_code == 403


def test_expense_two_step_approval_partial_amount_and_single_reimbursement(signup, new_client):
    owner, worker, boss, *_ = team(signup, new_client)
    cid = claim(worker, cats(worker)["Meals"]).json()["id"]
    # finance cannot skip the manager when the employee has one
    early = owner.post(f"{API}/expenses/{cid}/finance-decision", {"approve": True})
    assert early.status_code == 409 and early.json()["error"]["code"] == "invalid_state"
    assert worker.post(f"{API}/expenses/{cid}/manager-decision", {"approve": True}).status_code == 403
    assert len(boss.get(f"{API}/expenses", params={"scope": "team"}).json()) == 1
    assert boss.post(f"{API}/expenses/{cid}/manager-decision", {"approve": True}).json()["status"] == "manager_approved"
    assert boss.post(f"{API}/expenses/{cid}/manager-decision", {"approve": True}).status_code == 409
    too_much = owner.post(f"{API}/expenses/{cid}/finance-decision", {"approve": True, "approved_amount": "9999"})
    assert too_much.status_code == 422
    ok = owner.post(f"{API}/expenses/{cid}/finance-decision", {"approve": True, "approved_amount": "2500", "reimburse_via": "direct"})
    assert ok.json()["status"] == "approved" and D(str(ok.json()["approved_amount"])) == 2500
    assert owner.post(f"{API}/expenses/{cid}/reimburse").json()["status"] == "reimbursed"
    again = owner.post(f"{API}/expenses/{cid}/reimburse")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_reimbursed"
    assert worker.get(f"{API}/expenses").json()[0]["status"] == "reimbursed"
    assert worker.get(f"{API}/notifications").json()["unread"] >= 2


def test_expense_self_approval_strangers_and_cancel(signup, new_client):
    owner, worker, boss, _w, boss_emp = team(signup, new_client)
    mine = claim(boss, cats(boss)["Meals"]).json()["id"]
    r = boss.post(f"{API}/expenses/{mine}/manager-decision", {"approve": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    # the boss has no manager on file, so finance decides directly
    assert owner.post(f"{API}/expenses/{mine}/finance-decision", {"approve": False, "note": "No receipt"}).json()["status"] == "rejected"
    other_emp = mkemp(owner, first_name="Other", last_name="Mgr", email="other@x.test")
    other = portal_join(owner, new_client, other_emp["id"], "reporting_manager", name="Other Mgr")
    cid = claim(worker, cats(worker)["Meals"]).json()["id"]
    assert other.post(f"{API}/expenses/{cid}/manager-decision", {"approve": True}).status_code == 404
    assert other.get(f"{API}/expenses/{cid}/receipt").status_code == 404
    assert worker.post(f"{API}/expenses/{cid}/cancel").json()["status"] == "cancelled"
    assert boss.post(f"{API}/expenses/{cid}/manager-decision", {"approve": True}).status_code == 409
    assert worker.get(f"{API}/expenses", params={"scope": "all"}).status_code == 403


def test_expenses_are_tenant_isolated(signup, new_client):
    owner, worker, *_ = team(signup, new_client)
    cid = claim(worker, cats(worker)["Meals"]).json()["id"]
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/expenses", params={"scope": "all"}).json() == []
    assert other.post(f"{API}/expenses/{cid}/finance-decision", {"approve": True}).status_code == 404
    assert other.post(f"{API}/expenses/{cid}/reimburse").status_code == 404
    assert claim(other, cats(worker)["Meals"]).status_code == 422  # another organization's category id


# ------------------------------------------------------------------ loans
def test_installment_schedule_rounding():
    rows = schedule(D("100"), 3, date(2026, 11, 1))
    assert [a for _, _, a in rows] == [D("33.33"), D("33.33"), D("33.34")] and sum(a for _, _, a in rows) == D("100")
    assert [d for _, d, _ in schedule(D("300"), 3, date(2026, 11, 1))] == [date(2026, 11, 1), date(2026, 12, 1), date(2027, 1, 1)]


def test_loan_request_approval_disbursement_and_repayment(signup, new_client):
    owner, worker, boss, *_ = team(signup, new_client)
    loan = worker.post(f"{API}/loans", {"kind": "loan", "principal": "90000", "installments": 3, "reason": "Rent"})
    assert loan.status_code == 201
    lid = loan.json()["id"]
    dup = worker.post(f"{API}/loans", {"kind": "loan", "principal": "1000", "installments": 1})
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "open_loan_exists"
    assert worker.post(f"{API}/loans", {"kind": "advance", "principal": "1000", "installments": 5}).status_code == 422
    assert worker.post(f"{API}/loans/{lid}/decision", {"approve": True}).status_code == 403
    assert boss.get(f"{API}/loans/{lid}").status_code == 404  # a colleague cannot see it
    assert owner.post(f"{API}/loans/{lid}/disburse", {"disbursed_on": "2026-11-05", "first_due_month": "2026-12"}).status_code == 409
    assert owner.post(f"{API}/loans/{lid}/decision", {"approve": True}).json()["status"] == "approved"
    assert owner.post(f"{API}/loans/{lid}/decision", {"approve": True}).status_code == 409
    bad = owner.post(f"{API}/loans/{lid}/disburse", {"disbursed_on": "2026-11-05", "first_due_month": "2026-10"})
    assert bad.status_code == 422
    d = owner.post(f"{API}/loans/{lid}/disburse", {"disbursed_on": "2026-11-05", "first_due_month": "2026-12"}).json()
    assert d["status"] == "active" and len(d["schedule"]) == 3 and D(str(d["outstanding"])) == 90000
    first = d["schedule"][0]["id"]
    assert worker.post(f"{API}/loans/{lid}/repay", {"installment_ids": [first]}).status_code == 403
    one = owner.post(f"{API}/loans/{lid}/repay", {"installment_ids": [first]}).json()
    assert D(str(one["outstanding"])) == 60000 and one["schedule"][0]["method"] == "manual"
    assert owner.post(f"{API}/loans/{lid}/repay", {"installment_ids": [first]}).status_code == 409  # already paid
    done = owner.post(f"{API}/loans/{lid}/repay", {"settle_all": True}).json()
    assert done["status"] == "closed"
    assert worker.get(f"{API}/loans").json()[0]["status"] == "closed"


def test_loan_self_approval_and_isolation(signup, new_client):
    owner, worker, *_ = team(signup, new_client)
    own = owner.post(f"{API}/loans", {"kind": "advance", "principal": "20000", "installments": 1}).json()
    r = owner.post(f"{API}/loans/{own['id']}/decision", {"approve": True})
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"
    assert owner.post(f"{API}/loans/{own['id']}/cancel").json()["status"] == "cancelled"
    lid = worker.post(f"{API}/loans", {"kind": "loan", "principal": "5000", "installments": 2}).json()["id"]
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/loans/{lid}").status_code == 404
    assert other.post(f"{API}/loans/{lid}/decision", {"approve": True}).status_code == 404
    assert other.get(f"{API}/loans", params={"scope": "all"}).json() == []


# ------------------------------------------------------------------ assets
def test_asset_assignment_return_and_history(signup, new_client):
    owner, worker, boss, worker_emp, boss_emp = team(signup, new_client)
    a = owner.post(f"{API}/assets", {"name": "MacBook Pro 14", "category": "Laptop", "serial_number": "C02XK1"}).json()
    assert owner.post(f"{API}/assets", {"name": "Dup", "category": "Laptop", "serial_number": "c02xk1"}).status_code == 409
    assert worker.get(f"{API}/assets").status_code == 403
    r = owner.post(f"{API}/assets/{a['id']}/assign", {"employee_id": worker_emp["id"], "assigned_on": "2026-11-01"})
    assert r.json()["status"] == "assigned" and r.json()["assigned_to"] == "Worker Bee"
    again = owner.post(f"{API}/assets/{a['id']}/assign", {"employee_id": boss_emp["id"], "assigned_on": "2026-11-02"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "not_available"
    assert owner.post(f"{API}/assets/{a['id']}/status", {"status": "retired"}).status_code == 409
    mine = worker.get(f"{API}/me/assets").json()
    assert len(mine) == 1 and mine[0]["name"] == "MacBook Pro 14" and mine[0]["returned_on"] is None
    assert boss.get(f"{API}/me/assets").json() == []
    assert owner.post(f"{API}/assets/{a['id']}/return", {"returned_on": "2026-10-01", "condition": "good"}).status_code == 422
    back = owner.post(f"{API}/assets/{a['id']}/return", {"returned_on": "2026-11-10", "condition": "fair"}).json()
    assert back["status"] == "available" and back["condition"] == "fair"
    assert owner.post(f"{API}/assets/{a['id']}/return", {"returned_on": "2026-11-11", "condition": "fair"}).status_code == 409
    owner.post(f"{API}/assets/{a['id']}/assign", {"employee_id": boss_emp["id"], "assigned_on": "2026-11-12"})
    hist = owner.get(f"{API}/assets/{a['id']}/history").json()
    assert [h["employee"] for h in hist] == ["Boss Lead", "Worker Bee"] and hist[1]["condition_in"] == "fair"
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/assets").json() == []
    assert other.post(f"{API}/assets/{a['id']}/return", {"returned_on": "2026-11-13", "condition": "good"}).status_code == 404


# ------------------------------------------------------------------ help desk
def test_ticket_lifecycle_privacy_and_internal_notes(signup, new_client):
    owner, worker, boss, *_ = team(signup, new_client)
    t = worker.post(f"{API}/tickets", {"category": "payroll", "priority": "high", "subject": "Payslip missing",
                                       "description": "I cannot see my October payslip."})
    assert t.status_code == 201 and t.json()["number"] == 1001 and t.json()["status"] == "open"
    tid = t.json()["id"]
    assert worker.post(f"{API}/tickets", {"category": "nonsense", "subject": "abc", "description": "abc"}).status_code == 422
    assert boss.get(f"{API}/tickets/{tid}").status_code == 404  # a colleague cannot read it
    assert worker.get(f"{API}/tickets", params={"scope": "all"}).status_code == 403
    assert len(owner.get(f"{API}/tickets", params={"scope": "all", "status": "active"}).json()) == 1
    owner.post(f"{API}/tickets/{tid}/comments", {"body": "Checking with finance", "internal": True})
    owner.post(f"{API}/tickets/{tid}/comments", {"body": "We are looking into it."})
    seen = worker.get(f"{API}/tickets/{tid}").json()["comments"]
    assert [c["body"] for c in seen] == ["We are looking into it."]
    assert len(owner.get(f"{API}/tickets/{tid}").json()["comments"]) == 2
    worker.post(f"{API}/tickets/{tid}/comments", {"body": "Thanks", "internal": True})  # the flag is ignored for requesters
    assert worker.get(f"{API}/tickets/{tid}").json()["comments"][-1]["internal"] is False
    assert worker.post(f"{API}/tickets/{tid}/rating", {"rating": 5}).status_code == 409  # not resolved yet
    assert worker.patch(f"{API}/tickets/{tid}", {"status": "resolved"}).status_code == 403
    assert owner.patch(f"{API}/tickets/{tid}", {"status": "resolved"}).json()["status"] == "resolved"
    assert worker.post(f"{API}/tickets/{tid}/rating", {"rating": 5}).json()["rating"] == 5
    worker.post(f"{API}/tickets/{tid}/comments", {"body": "Still not visible"})
    assert worker.get(f"{API}/tickets/{tid}").json()["status"] == "in_progress"  # a reply reopens it
    assert worker.post(f"{API}/tickets/{tid}/close").json()["status"] == "closed"
    assert worker.post(f"{API}/tickets/{tid}/comments", {"body": "more"}).status_code == 409
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/tickets/{tid}").status_code == 404
    assert other.patch(f"{API}/tickets/{tid}", {"status": "open"}).status_code == 404
