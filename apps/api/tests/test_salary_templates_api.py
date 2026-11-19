from decimal import Decimal

from tests.helpers import API, mkemp, portal_join


def test_template_increment_and_bulk_application_create_salary_revisions(signup, new_client):
    owner = signup()
    alice = mkemp(owner, first_name="Alice", last_name="One", email="alice@x.test")
    bob = mkemp(owner, first_name="Bob", last_name="Two", email="bob@x.test")
    component = owner.post(f"{API}/payroll/components", {"name": "Transport", "kind": "earning",
                                                           "calc": "fixed", "default_value": "5000"}).json()
    payload = {"name": "Professional", "basic": "100000", "lines": [{"component_id": component["id"]}],
               "increment_type": "percent", "increment_value": "10"}
    created = owner.post(f"{API}/payroll/templates", payload)
    assert created.status_code == 201, created.text
    template = created.json()
    assert Decimal(str(template["effective_basic"])) == Decimal("110000.00")
    assert owner.post(f"{API}/payroll/templates", payload).status_code == 409

    applied = owner.post(f"{API}/payroll/templates/{template['id']}/apply",
                         {"effective_from": "2027-01-01", "employee_ids": [alice["id"], bob["id"]]})
    assert applied.status_code == 200, applied.text
    assert applied.json()["applied"] == 2
    for employee in (alice, bob):
        history = owner.get(f"{API}/employees/{employee['id']}/salary").json()
        assert history[0]["template_id"] == template["id"]
        assert Decimal(str(history[0]["basic"])) == Decimal("110000.00")
        assert Decimal(str(history[0]["lines"][0]["amount"])) == Decimal("5000")
    roster = owner.get(f"{API}/payroll/salary-roster").json()
    assert next(row for row in roster if row["employee_id"] == alice["id"])["template"] == "Professional"
    assert owner.post(f"{API}/payroll/templates/{template['id']}/apply",
                      {"effective_from": "2027-01-01", "employee_ids": [alice["id"]]}).status_code == 409

    raised = owner.put(f"{API}/payroll/templates/{template['id']}",
                       {**payload, "increment_value": "15"}).json()
    assert Decimal(str(raised["effective_basic"])) == Decimal("115000.00")
    all_result = owner.post(f"{API}/payroll/templates/{template['id']}/apply",
                            {"effective_from": "2027-02-01", "all_employees": True})
    assert all_result.status_code == 200, all_result.text
    assert all_result.json()["applied"] >= 2
    assert Decimal(str(owner.get(f"{API}/employees/{alice['id']}/salary").json()[0]["basic"])) == Decimal("115000.00")

    worker = portal_join(owner, new_client, alice["id"], name="Alice One")
    assert worker.get(f"{API}/payroll/templates").status_code == 403
    assert worker.post(f"{API}/payroll/templates/{template['id']}/apply",
                       {"effective_from": "2027-03-01", "all_employees": True}).status_code == 403
