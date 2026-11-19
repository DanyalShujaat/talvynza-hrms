from decimal import Decimal as Dec

from sqlalchemy import select

from app.modules.payroll.models import PayrollEntry, PayrollLineItem, PayrollRun
from tests.helpers import API, join, mkemp

OCT = {"period_start": "2026-10-01", "period_end": "2026-10-31"}


def test_regular_payroll_cannot_overlap_but_adjacent_periods_are_allowed(signup):
    owner = signup()
    assert owner.post(f"{API}/payroll/runs", OCT).status_code == 201
    for start, end in (("2026-09-15", "2026-10-15"), ("2026-10-15", "2026-11-15"),
                       ("2026-10-05", "2026-10-06"), ("2026-09-01", "2026-11-30")):
        response = owner.post(f"{API}/payroll/runs", {"period_start": start, "period_end": end})
        assert response.status_code == 409 and response.json()["error"]["code"] == "overlapping_run"
    assert owner.post(f"{API}/payroll/runs", {"period_start": "2026-11-01", "period_end": "2026-11-30"}).status_code == 201


def salary(api, eid, frm, basic, lines=None):
    return api.post(f"{API}/employees/{eid}/salary", {"effective_from": frm, "basic": basic, "lines": lines or []})


def dec(v):
    return Dec(str(v))


def setup(signup, new_client):
    owner = signup()
    # These tests check the arithmetic and the workflow, so statutory deductions are switched off.
    # Pakistan withholding has its own tests in test_payroll_pk_api.py.
    assert owner.put(f"{API}/payroll/statutory", {"income_tax": False, "eobi_enabled": False}).status_code == 200
    pat = mkemp(owner, first_name="Pat", email="pat@x.test", joining_date="2026-01-05", bank_name="HBL",
                bank_account="PK36HABB0000001234567")
    assert salary(owner, pat["id"], "2026-01-01", "100000").status_code == 201
    assert salary(owner, pat["id"], "2026-10-15", "110000").status_code == 201
    owner.post(f"{API}/roles", {"key": "payroll_approver", "name": "Payroll Approver",
                                "permissions": ["payroll.approve", "payroll.read"]})
    approver = join(owner, new_client, "approver@x.test", "payroll_approver", name="Approver")
    return owner, approver, pat


def run_and_calc(owner, body=OCT):
    run = owner.post(f"{API}/payroll/runs", body)
    assert run.status_code == 201, run.text
    rid = run.json()["id"]
    calc = owner.post(f"{API}/payroll/runs/{rid}/calculate")
    assert calc.status_code == 200, calc.text
    return rid, calc.json()


def entry_for(api, rid, name="Pat"):
    run = api.get(f"{API}/payroll/runs/{rid}").json()
    return next(e for e in run["entries"] if e["employee"].startswith(name)), run


def test_spec_example_mid_month_raise_end_to_end(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, summary = run_and_calc(owner)
    e, run = entry_for(owner, rid)
    assert dec(e["gross"]) == dec(e["net"]) == Dec("105483.87")  # 14d at 100000 + 17d at 110000 over 31d
    assert run["statutory_status"] == "pk:off" and "switched off" in run["statutory_notice"]
    assert summary["entries"] == 1 and summary["skipped"] == []  # the owner joined after October, so is not in this run
    detail = owner.get(f"{API}/payroll/runs/{rid}/entries/{e['id']}").json()
    assert detail["earnings"][0]["name"] == "Basic salary"


def test_recalculation_is_reproducible_before_approval(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    first = entry_for(owner, rid)[0]["net"]
    owner.post(f"{API}/payroll/runs/{rid}/calculate")
    again = entry_for(owner, rid)
    assert again[0]["net"] == first and len(again[1]["entries"]) == 1  # no duplicated entries


def test_working_day_proration_option(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner, {**OCT, "proration": "working_days"})
    assert dec(entry_for(owner, rid)[0]["net"]) == Dec("105454.55")


def test_components_percent_and_deduction_lines(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    hra = owner.post(f"{API}/payroll/components", {"name": "House rent", "kind": "earning", "calc": "percent_of_basic",
                                                    "default_value": "40"}).json()
    pf = owner.post(f"{API}/payroll/components", {"name": "Provident fund", "kind": "deduction", "calc": "percent_of_basic",
                                                   "default_value": "5", "taxable": False}).json()
    assert salary(owner, pat["id"], "2026-11-01", "100000", [{"component_id": hra["id"]}, {"component_id": pf["id"]}]).status_code == 201
    rid, _ = run_and_calc(owner, {"period_start": "2026-11-01", "period_end": "2026-11-30"})
    e, _ = entry_for(owner, rid)
    assert (dec(e["gross"]), dec(e["deductions"]), dec(e["net"])) == (Dec("140000.00"), Dec("5000.00"), Dec("135000.00"))
    assert owner.post(f"{API}/payroll/components", {"name": "house rent", "kind": "earning"}).status_code == 409


def test_unpaid_leave_reduces_pay(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    pat_api = join(owner, new_client, "pat@x.test", "employee", name="Pat")
    unpaid = next(t["id"] for t in pat_api.get(f"{API}/leave/types").json() if t["name"] == "Unpaid Leave")
    r = pat_api.post(f"{API}/leave/requests", {"leave_type_id": unpaid, "start_date": "2026-10-05", "end_date": "2026-10-06"})
    assert r.status_code == 201
    assert owner.post(f"{API}/leave/requests/{r.json()['id']}/decision", {"approve": True}).status_code == 200
    rid, _ = run_and_calc(owner)
    e, _ = entry_for(owner, rid)
    # October 2026 has 22 working days: 110000 / 22 = 5000 per day, 2 days = 10000
    assert dec(e["unpaid_days"]) == 2 and dec(e["net"]) == Dec("105483.87") - Dec("10000.00")


def test_separation_of_duties_and_finalization_lock(signup, new_client, db):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    r = owner.post(f"{API}/payroll/runs/{rid}/approve")
    assert r.status_code == 403 and r.json()["error"]["code"] == "self_approval"  # creator cannot approve
    assert owner.post(f"{API}/payroll/runs/{rid}/finalize").status_code == 409  # not approved yet
    assert approver.post(f"{API}/payroll/runs/{rid}/calculate").status_code == 403  # approver cannot process
    assert approver.post(f"{API}/payroll/runs/{rid}/approve").status_code == 200
    assert owner.post(f"{API}/payroll/runs/{rid}/calculate").status_code == 409  # approved runs are locked
    assert owner.delete(f"{API}/payroll/runs/{rid}").status_code == 409
    assert approver.post(f"{API}/payroll/runs/{rid}/finalize").status_code == 200
    again = approver.post(f"{API}/payroll/runs/{rid}/finalize")
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_finalized"
    assert owner.post(f"{API}/payroll/runs/{rid}/calculate").status_code == 409
    # tampering below the API: the ORM refuses to change entries or line items of a finalized run
    from app.db.tenant_scope import ALL_TENANTS, tenant_scope

    with tenant_scope(db, ALL_TENANTS):
        entry = db.scalar(select(PayrollEntry))
        entry.net = Dec("1.00")
        try:
            db.flush()
            raise AssertionError("finalized payroll entry was modified")
        except PermissionError:
            db.rollback()
        line = db.scalar(select(PayrollLineItem))
        line.amount = Dec("1.00")
        try:
            db.flush()
            raise AssertionError("finalized payroll line item was modified")
        except PermissionError:
            db.rollback()
        assert db.scalar(select(PayrollRun)).status == "finalized"


def test_self_approval_can_be_enabled_explicitly_for_single_owner_companies(signup, new_client, db):
    from app.modules.tenancy.models import Tenant

    owner, approver, pat = setup(signup, new_client)
    t = db.scalar(select(Tenant))
    t.settings = {**t.settings, "payroll_allow_self_approval": True}
    db.commit()
    rid, _ = run_and_calc(owner)
    assert owner.post(f"{API}/payroll/runs/{rid}/approve").status_code == 200


def test_duplicate_period_is_refused_and_bad_periods_rejected(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    run_and_calc(owner)
    dup = owner.post(f"{API}/payroll/runs", OCT)
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_run"
    assert owner.post(f"{API}/payroll/runs", {"period_start": "2026-10-31", "period_end": "2026-10-01"}).status_code == 422
    assert owner.post(f"{API}/payroll/runs", {**OCT, "proration": "hourly"}).status_code == 422


def test_negative_net_blocks_approval(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    loan = owner.post(f"{API}/payroll/components", {"name": "Loan", "kind": "deduction", "default_value": "500000"}).json()
    assert salary(owner, pat["id"], "2026-11-01", "100000", [{"component_id": loan["id"]}]).status_code == 201
    rid, _ = run_and_calc(owner, {"period_start": "2026-11-01", "period_end": "2026-11-30"})
    r = approver.post(f"{API}/payroll/runs/{rid}/approve")
    assert r.status_code == 409 and r.json()["error"]["code"] == "unresolved_exceptions"
    assert approver.get(f"{API}/payroll/runs/{rid}/exceptions").json()[0]["exceptions"] == ["negative_net_pay"]


def test_salary_revisions_are_never_overwritten(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    dup = salary(owner, pat["id"], "2026-10-15", "999999")
    assert dup.status_code == 409 and dup.json()["error"]["code"] == "duplicate_revision"
    assert salary(owner, pat["id"], "2027-01-01", "0").status_code == 422
    hist = owner.get(f"{API}/employees/{pat['id']}/salary").json()
    assert [dec(h["basic"]) for h in hist] == [Dec("110000"), Dec("100000")]  # both kept, newest first


def test_back_dated_revision_warns_about_finalized_periods(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    approver.post(f"{API}/payroll/runs/{rid}/approve")
    approver.post(f"{API}/payroll/runs/{rid}/finalize")
    r = salary(owner, pat["id"], "2026-10-20", "120000")
    assert r.status_code == 201 and "finalized payroll" in r.json()["warning"]
    assert dec(entry_for(owner, rid)[0]["net"]) == Dec("105483.87")  # history is untouched


def test_variance_against_previous_finalized_run(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    approver.post(f"{API}/payroll/runs/{rid}/approve")
    approver.post(f"{API}/payroll/runs/{rid}/finalize")
    nov, _ = run_and_calc(owner, {"period_start": "2026-11-01", "period_end": "2026-11-30"})
    v = owner.get(f"{API}/payroll/runs/{nov}/variance").json()
    assert v[0]["employee"] == "Pat Khan" and v[0]["change_percent"] == 4.3


def test_payslip_privacy_and_publication(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    colleague = mkemp(owner, first_name="Col", email="col@x.test")
    salary(owner, colleague["id"], "2026-01-01", "50000")
    pat_api = join(owner, new_client, "pat@x.test", "employee", name="Pat")
    col_api = join(owner, new_client, "col@x.test", "employee", name="Col")
    rid, _ = run_and_calc(owner)
    assert pat_api.get(f"{API}/payslips").json() == []  # nothing is visible before finalization
    entry = entry_for(owner, rid)[0]
    assert pat_api.get(f"{API}/payslips/{entry['id']}").status_code == 404
    approver.post(f"{API}/payroll/runs/{rid}/approve")
    approver.post(f"{API}/payroll/runs/{rid}/finalize")
    slips = pat_api.get(f"{API}/payslips").json()
    assert len(slips) == 1 and dec(slips[0]["net"]) == Dec("105483.87")
    slip = pat_api.get(f"{API}/payslips/{entry['id']}").json()
    assert slip["employee"] == "Pat Khan" and slip["earnings"] and "switched off" in slip["statutory_notice"]
    assert col_api.get(f"{API}/payslips/{entry['id']}").status_code == 404  # someone else's payslip
    assert len(col_api.get(f"{API}/payslips").json()) == 1
    assert pat_api.get(f"{API}/notifications").json()["unread"] >= 1


def test_salary_and_payroll_access_is_denied_to_regular_employees(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    pat_api = join(owner, new_client, "pat@x.test", "employee", name="Pat")
    rid, _ = run_and_calc(owner)
    for method, url in (("get", f"/employees/{pat['id']}/salary"), ("get", "/payroll/runs"), ("get", f"/payroll/runs/{rid}"),
                        ("get", "/payroll/components"), ("get", f"/payroll/runs/{rid}/variance")):
        assert getattr(pat_api, method)(f"{API}{url}").status_code == 403, url
    assert pat_api.post(f"{API}/payroll/runs", {"period_start": "2026-12-01", "period_end": "2026-12-31"}).status_code == 403
    assert pat_api.post(f"{API}/employees/{pat['id']}/salary", {"effective_from": "2026-12-01", "basic": "1"}).status_code == 403
    hr = join(owner, new_client, "hr@x.test", "hr_admin", name="Hr Admin")  # HR can read salary but not run payroll
    assert hr.get(f"{API}/employees/{pat['id']}/salary").status_code == 200
    assert hr.post(f"{API}/payroll/runs", {"period_start": "2026-12-01", "period_end": "2026-12-31"}).status_code == 403


def test_payment_export_needs_finalization_bank_permission_and_is_audited(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    assert owner.get(f"{API}/payroll/runs/{rid}/export.csv").status_code == 409
    approver.post(f"{API}/payroll/runs/{rid}/approve")
    approver.post(f"{API}/payroll/runs/{rid}/finalize")
    assert approver.get(f"{API}/payroll/runs/{rid}/export.csv").status_code == 403  # no bank.read
    r = owner.get(f"{API}/payroll/runs/{rid}/export.csv")
    assert r.status_code == 200 and "PK36HABB0000001234567" in r.text and "105483.87" in r.text
    actions = [a["action"] for a in owner.get(f"{API}/audit-logs", params={"page_size": 100}).json()["items"]]
    assert "payroll.exported" in actions and "payroll.finalized" in actions and "payroll.approved" in actions


def test_payroll_is_tenant_isolated(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    rid, _ = run_and_calc(owner)
    other = signup("x@other.test", "Other Org")
    assert other.get(f"{API}/payroll/runs").json() == []
    assert other.get(f"{API}/payroll/runs/{rid}").status_code == 404
    assert other.post(f"{API}/payroll/runs/{rid}/approve").status_code == 404
    assert other.get(f"{API}/employees/{pat['id']}/salary").status_code == 404
    assert other.post(f"{API}/employees/{pat['id']}/salary", {"effective_from": "2026-12-01", "basic": "5"}).status_code == 404
    same_period = other.post(f"{API}/payroll/runs", OCT)
    assert same_period.status_code == 201  # the unique period rule is per tenant, not global
