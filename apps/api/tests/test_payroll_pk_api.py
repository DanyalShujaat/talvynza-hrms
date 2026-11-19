"""Pakistan withholding, EOBI, loan repayments and expense reimbursements inside payroll runs."""
from decimal import Decimal as D

from tests.helpers import API, join, mkemp, portal_join

OCT = {"period_start": "2026-10-01", "period_end": "2026-10-31"}
NOV = {"period_start": "2026-11-01", "period_end": "2026-11-30"}


def dec(v):
    return D(str(v))


def setup(signup, new_client, basic="200000", lines=None):
    owner = signup()
    pat = mkemp(owner, first_name="Pat", email="pat@x.test", joining_date="2026-01-05")
    r = owner.post(f"{API}/employees/{pat['id']}/salary", {"effective_from": "2026-01-01", "basic": basic, "lines": lines or []})
    assert r.status_code == 201, r.text
    owner.post(f"{API}/roles", {"key": "payroll_approver", "name": "Payroll Approver", "permissions": ["payroll.approve", "payroll.read"]})
    approver = join(owner, new_client, "approver@x.test", "payroll_approver", name="Approver")
    return owner, approver, pat


def run(owner, body=OCT):
    r = owner.post(f"{API}/payroll/runs", body)
    assert r.status_code == 201, r.text
    rid = r.json()["id"]
    assert owner.post(f"{API}/payroll/runs/{rid}/calculate").status_code == 200
    return rid


def entry(api, rid, name="Pat"):
    data = api.get(f"{API}/payroll/runs/{rid}").json()
    return next(e for e in data["entries"] if e["employee"].startswith(name)), data


def slip(api, rid, e):
    return api.get(f"{API}/payroll/runs/{rid}/entries/{e['id']}").json()


def finalize(approver, rid):
    assert approver.post(f"{API}/payroll/runs/{rid}/approve").status_code == 200
    assert approver.post(f"{API}/payroll/runs/{rid}/finalize").status_code == 200


def test_income_tax_is_withheld_by_default_for_a_pakistan_organization(signup, new_client):
    """200,000 a month, first run in October (9 months left): projected 1,800,000 for the tax year.
    Tax 6,000 + 11% of 600,000 = 72,000, spread over 9 months = 8,000."""
    owner, approver, pat = setup(signup, new_client)
    rid = run(owner)
    e, data = entry(owner, rid)
    assert data["statutory_status"] == "pk:ty2027" and "tax year 2027" in data["statutory_notice"]
    assert dec(e["income_tax"]) == 8000 and dec(e["taxable_income"]) == 200000
    assert dec(e["gross"]) == 200000 and dec(e["net"]) == 192000
    assert dec(data["total_income_tax"]) == 8000
    lines = {x["name"]: dec(x["amount"]) for x in slip(owner, rid, e)["deduction_lines"]}
    assert lines == {"Income tax": D(8000)}


def test_year_to_date_from_finalized_runs_feeds_the_next_month(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    finalize(approver, run(owner))
    # raise from 1 November: 300,000. Projected = 200,000 paid + 300,000 x 8 = 2,600,000 -> 116,000 + 20% of 400,000
    # = 196,000; less 8,000 already withheld = 188,000 over 8 months = 23,500
    assert owner.post(f"{API}/employees/{pat['id']}/salary", {"effective_from": "2026-11-01", "basic": "300000"}).status_code == 201
    e, _ = entry(owner, run(owner, NOV))
    assert dec(e["income_tax"]) == 23500 and dec(e["net"]) == 276500


def test_partly_exempt_allowance_and_non_taxable_component(signup, new_client):
    owner = signup()
    medical = owner.post(f"{API}/payroll/components", {"name": "Medical allowance", "kind": "earning", "default_value": "30000",
                                                        "taxable": True, "exempt_percent_of_basic": "10"}).json()
    fuel = owner.post(f"{API}/payroll/components", {"name": "Fuel reimbursement", "kind": "earning", "default_value": "15000",
                                                     "taxable": False}).json()
    pat = mkemp(owner, first_name="Pat", email="pat@x.test", joining_date="2026-01-05")
    owner.post(f"{API}/employees/{pat['id']}/salary", {"effective_from": "2026-01-01", "basic": "200000",
                                                       "lines": [{"component_id": medical["id"]}, {"component_id": fuel["id"]}]})
    e, _ = entry(owner, run(owner))
    # medical 30,000: the first 10% of basic (20,000) is exempt, 10,000 is taxable. Fuel is not taxable at all.
    assert dec(e["gross"]) == 245000 and dec(e["taxable_income"]) == 210000
    # projected 210,000 x 9 = 1,890,000 -> 6,000 + 11% of 690,000 = 81,900 / 9 = 9,100
    assert dec(e["income_tax"]) == 9100


def test_salary_under_the_threshold_has_no_tax_line(signup, new_client):
    owner, approver, pat = setup(signup, new_client, basic="45000")
    e, _ = entry(owner, run(owner))
    assert dec(e["income_tax"]) == 0 and dec(e["net"]) == 45000
    rid = run(owner, NOV)
    assert slip(owner, rid, entry(owner, rid)[0])["deduction_lines"] == []


def test_no_guessing_for_periods_without_verified_rules_or_partial_months(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    future = run(owner, {"period_start": "2027-08-01", "period_end": "2027-08-31"})  # tax year 2028: no rule set
    e, data = entry(owner, future)
    assert data["statutory_status"] == "pk:no_rules:2028" and "No verified income tax rates" in data["statutory_notice"]
    assert dec(e["income_tax"]) == 0
    half = run(owner, {"period_start": "2026-10-01", "period_end": "2026-10-15"})
    e, data = entry(owner, half)
    assert data["statutory_status"] == "pk:not_monthly" and dec(e["income_tax"]) == 0


def test_statutory_settings_and_eobi(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    cfg = owner.get(f"{API}/payroll/statutory").json()
    assert cfg["income_tax"] is True and cfg["eobi_enabled"] is False and cfg["current_rules_loaded"] is True
    years = {t["tax_year"]: t for t in cfg["tax_years"]}
    assert years[2027]["law"] == "Finance Act 2026" and years[2027]["sources"] and len(years[2027]["slabs"]) == 8
    bad = owner.put(f"{API}/payroll/statutory", {"income_tax": True, "eobi_enabled": True})
    assert bad.status_code == 422  # EOBI needs its wage base entered first
    ok = owner.put(f"{API}/payroll/statutory", {"income_tax": True, "eobi_enabled": True, "eobi_wage_base": "40000"})
    assert ok.status_code == 200
    rid = run(owner)
    e, data = entry(owner, rid)
    s = slip(owner, rid, e)
    assert {x["name"]: dec(x["amount"]) for x in s["deduction_lines"]} == {"Income tax": D(8000), "EOBI (employee share)": D(400)}
    assert s["employer_contributions"] == [{"name": "EOBI (employer share)", "amount": "2000.00"}]
    assert dec(data["total_employer_contributions"]) == 2000 and data["statutory_status"] == "pk:ty2027+eobi"
    assert dec(e["net"]) == 200000 - 8000 - 400
    assert approver.put(f"{API}/payroll/statutory", {"income_tax": False, "eobi_enabled": False}).status_code == 403
    actions = [a["action"] for a in owner.get(f"{API}/audit-logs", params={"page_size": 100}).json()["items"]]
    assert "payroll.statutory_changed" in actions


def test_organizations_outside_pakistan_get_no_statutory_deductions(signup):
    owner = signup()
    org = owner.post(f"{API}/organizations", {"name": "London Ltd", "country": "GB", "currency": "GBP", "timezone": "Europe/London"}).json()
    owner.post(f"{API}/me/switch-organization", {"tenant_id": org["id"]})
    me = owner.get(f"{API}/me/employee").json()
    owner.post(f"{API}/employees/{me['id']}/salary", {"effective_from": "2026-01-01", "basic": "5000"})
    cfg = owner.get(f"{API}/payroll/statutory").json()
    assert cfg["supported"] is False and cfg["income_tax"] is False and cfg["tax_years"] == []
    assert owner.put(f"{API}/payroll/statutory", {"income_tax": True, "eobi_enabled": False}).status_code == 409
    data = owner.get(f"{API}/payroll/runs/{run(owner, {'period_start': '2026-12-01', 'period_end': '2026-12-31'})}").json()
    assert data["statutory_status"] == "unconfigured" and "not available for GB" in data["statutory_notice"]
    assert dec(data["total_income_tax"]) == 0


def test_loan_installments_are_deducted_once_and_settled_on_finalize(signup, new_client):
    owner, approver, pat = setup(signup, new_client, basic="45000")
    pat_api = portal_join(owner, new_client, pat["id"], name="Pat Khan")
    loan = pat_api.post(f"{API}/loans", {"kind": "loan", "principal": "60000", "installments": 3, "reason": "Medical"}).json()
    owner.post(f"{API}/loans/{loan['id']}/decision", {"approve": True})
    d = owner.post(f"{API}/loans/{loan['id']}/disburse", {"disbursed_on": "2026-10-02", "first_due_month": "2026-10"}).json()
    assert [dec(i["amount"]) for i in d["schedule"]] == [20000, 20000, 20000]
    rid = run(owner)
    e, _ = entry(owner, rid)
    assert {x["name"]: dec(x["amount"]) for x in slip(owner, rid, e)["deduction_lines"]} == {"Loan repayment": D(20000)}
    assert dec(e["net"]) == 25000
    # while the run holds the installment it cannot also be repaid by hand
    first = owner.get(f"{API}/loans/{loan['id']}").json()["schedule"][0]
    assert first["in_payroll"] is True
    r = owner.post(f"{API}/loans/{loan['id']}/repay", {"installment_ids": [first["id"]]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "in_payroll"
    owner.post(f"{API}/payroll/runs/{rid}/calculate")  # recalculating does not double it
    assert dec(entry(owner, rid)[0]["net"]) == 25000
    finalize(approver, rid)
    after = owner.get(f"{API}/loans/{loan['id']}").json()
    assert after["schedule"][0]["status"] == "paid" and after["schedule"][0]["method"] == "payroll"
    assert dec(after["outstanding"]) == 40000
    e2, _ = entry(owner, run(owner, NOV))
    assert dec(e2["deductions"]) == 20000  # only the November installment, not October again
    # settling the rest by hand closes the loan after the pending run is removed
    nov_id = owner.get(f"{API}/payroll/runs").json()[0]["id"]
    assert owner.delete(f"{API}/payroll/runs/{nov_id}").status_code == 204
    done = owner.post(f"{API}/loans/{loan['id']}/repay", {"settle_all": True}).json()
    assert done["status"] == "closed" and dec(done["outstanding"]) == 0


def test_expense_claims_paid_through_payroll_are_untaxed_and_never_paid_twice(signup, new_client):
    owner, approver, pat = setup(signup, new_client)
    pat_api = portal_join(owner, new_client, pat["id"], name="Pat Khan")
    cats = {c["name"]: c["id"] for c in pat_api.get(f"{API}/expenses/categories").json()}
    claim = pat_api.post(f"{API}/expenses", data={"category_id": cats["Meals"], "amount": "4000", "expense_date": "2026-10-10",
                                                  "description": "Client lunch"}).json()
    r = owner.post(f"{API}/expenses/{claim['id']}/finance-decision", {"approve": True, "approved_amount": "3500", "reimburse_via": "payroll"})
    assert r.status_code == 200, r.text
    assert owner.post(f"{API}/expenses/{claim['id']}/reimburse").json()["error"]["code"] == "paid_via_payroll"
    rid = run(owner)
    e, _ = entry(owner, rid)
    s = slip(owner, rid, e)
    assert {x["name"]: dec(x["amount"]) for x in s["earnings"]} == {"Basic salary": D(200000), "Expense reimbursement": D(3500)}
    assert dec(e["taxable_income"]) == 200000 and dec(e["income_tax"]) == 8000  # the reimbursement is not taxed
    assert dec(e["net"]) == 200000 + 3500 - 8000
    finalize(approver, rid)
    mine = pat_api.get(f"{API}/expenses").json()[0]
    assert mine["status"] == "reimbursed"
    e2, _ = entry(owner, run(owner, NOV))
    assert dec(e2["gross"]) == 200000  # not reimbursed a second time
    assert pat_api.get(f"{API}/payslips").json()[0]["income_tax"] is not None
