import io

import pytest

from tests.helpers import API, join, mkemp, my_employee_id


def test_owner_gets_an_employee_record_automatically(signup):
    owner = signup()
    me = owner.get(f"{API}/me/employee").json()
    assert me["full_name"] == "Olivia Owner" and me["has_login"] is True and me["employee_code"] == "1001"


def test_create_list_filter_search_and_sort(signup):
    owner = signup()
    dept = owner.post(f"{API}/departments", {"name": "Engineering"}).json()
    mkemp(owner, first_name="Zara", last_name="Ahmed", email="zara@acme.test", department_id=dept["id"])
    mkemp(owner, first_name="Bilal", last_name="Shah", email="bilal@acme.test")
    names = [e["first_name"] for e in owner.get(f"{API}/employees").json()["items"]]
    assert names == sorted(names)
    assert owner.get(f"{API}/employees", params={"q": "zara"}).json()["total"] == 1
    assert owner.get(f"{API}/employees", params={"letter": "B"}).json()["items"][0]["first_name"] == "Bilal"
    assert owner.get(f"{API}/employees", params={"department_id": dept["id"]}).json()["total"] == 1
    assert owner.get(f"{API}/employees", params={"page_size": 2, "page": 2}).json()["page"] == 2


def test_duplicate_code_and_email_rejected(signup):
    owner = signup()
    mkemp(owner, employee_code="E-1", email="a@acme.test")
    r = owner.post(f"{API}/employees", {"first_name": "B", "last_name": "B", "joining_date": "2026-01-05",
                                        "employee_code": "E-1"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_employee_code"
    r = owner.post(f"{API}/employees", {"first_name": "B", "last_name": "B", "joining_date": "2026-01-05",
                                        "email": "A@acme.test"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "duplicate_email"


def test_employee_limit_is_enforced(signup, db):
    from sqlalchemy import select

    from app.modules.tenancy.models import Tenant

    owner = signup()
    t = db.scalar(select(Tenant))
    t.employee_capacity = 2
    db.commit()
    mkemp(owner, email="one@acme.test")  # owner + 1 = 2
    r = owner.post(f"{API}/employees", {"first_name": "X", "last_name": "Y", "joining_date": "2026-01-05"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "employee_limit_reached"


def test_manager_cycle_is_rejected_and_history_is_kept(signup):
    owner = signup()
    a, b = mkemp(owner, first_name="A", email="a@x.test"), mkemp(owner, first_name="B", email="b@x.test")
    assert owner.patch(f"{API}/employees/{b['id']}", {"manager_id": a["id"]}).status_code == 200
    r = owner.patch(f"{API}/employees/{a['id']}", {"manager_id": b["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "manager_cycle"
    r = owner.patch(f"{API}/employees/{a['id']}", {"manager_id": a["id"]})
    assert r.status_code == 422
    hist = owner.get(f"{API}/employees/{b['id']}/history").json()
    assert len(hist["assignments"]) == 2  # joining placement closed, new reporting line opened
    assert sum(1 for x in hist["assignments"] if x["effective_to"] is None) == 1


def test_lifecycle_transitions_and_audit(signup):
    owner = signup()
    emp = mkemp(owner, email="l@x.test", probation_end="2026-12-01")
    assert emp["status"] == "probation"
    ok = owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "confirmation", "effective_date": "2026-11-01"})
    assert ok.json()["status"] == "active" and ok.json()["confirmation_date"] == "2026-11-01"
    bad = owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "confirmation", "effective_date": "2026-11-01"})
    assert bad.status_code == 409 and bad.json()["error"]["code"] == "invalid_transition"
    sus = owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "suspension", "effective_date": "2026-11-02"})
    assert sus.json()["status"] == "suspended"
    assert owner.post(f"{API}/employees/{emp['id']}/lifecycle",
                      {"event_type": "reinstatement", "effective_date": "2026-11-05"}).json()["status"] == "active"
    out = owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "resignation", "effective_date": "2026-11-10"})
    assert out.json()["status"] == "resigned" and out.json()["exit_date"] == "2026-11-10"
    back = owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "rehire", "effective_date": "2026-12-01"})
    assert back.json()["status"] == "active" and back.json()["exit_date"] is None
    kinds = [e["event_type"] for e in owner.get(f"{API}/employees/{emp['id']}/history").json()["events"]]
    assert {"joined", "confirmation", "suspension", "reinstatement", "resignation", "rehire"} <= set(kinds)
    actions = {a["action"] for a in owner.get(f"{API}/audit-logs", params={"page_size": 100}).json()["items"]}
    assert {"employee.created", "employee.resignation", "employee.rehire"} <= actions


def test_promotion_and_transfer_open_new_assignments(signup):
    owner = signup()
    d1, d2 = (owner.post(f"{API}/departments", {"name": n}).json() for n in ("Sales", "Support"))
    des = owner.post(f"{API}/designations", {"name": "Lead", "department_id": d1["id"]}).json()
    emp = mkemp(owner, email="p@x.test", department_id=d1["id"])
    owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "promotion", "effective_date": "2026-06-01",
                                                          "details": {"designation_id": des["id"]}})
    owner.post(f"{API}/employees/{emp['id']}/lifecycle", {"event_type": "transfer", "effective_date": "2026-07-01",
                                                          "details": {"department_id": d2["id"]}})
    e = owner.get(f"{API}/employees/{emp['id']}").json()
    assert e["designation"] == "Lead" and e["department"] == "Support"
    assert len(owner.get(f"{API}/employees/{emp['id']}/history").json()["assignments"]) == 3


# ------------------------------------------------------------------ visibility & field protection
def test_employee_sees_only_self_manager_sees_team_hr_sees_all(signup, new_client):
    owner = signup()
    boss = mkemp(owner, first_name="Boss", email="boss@x.test")
    rep = mkemp(owner, first_name="Rep", email="rep@x.test", manager_id=boss["id"])
    other = mkemp(owner, first_name="Other", email="other@x.test")
    boss_api = join(owner, new_client, "boss@x.test", "reporting_manager")
    rep_api = join(owner, new_client, "rep@x.test", "employee")

    team = {e["first_name"] for e in boss_api.get(f"{API}/employees").json()["items"]}
    assert team == {"Boss", "Rep"}
    assert {e["first_name"] for e in rep_api.get(f"{API}/employees").json()["items"]} == {"Rep"}
    assert boss_api.get(f"{API}/employees/{rep['id']}").status_code == 200
    assert boss_api.get(f"{API}/employees/{other['id']}").status_code == 404
    assert rep_api.get(f"{API}/employees/{boss['id']}").status_code == 404
    assert rep_api.get(f"{API}/employees/{other['id']}").status_code == 404
    assert rep_api.post(f"{API}/employees", {"first_name": "N", "last_name": "N", "joining_date": "2026-01-05"}).status_code == 403
    assert rep_api.patch(f"{API}/employees/{rep['id']}", {"first_name": "Hacked"}).status_code == 403


def test_bank_and_national_id_are_field_protected(signup, new_client):
    owner = signup()
    emp = mkemp(owner, email="pay@x.test", bank_name="HBL", bank_account="PK36HABB0000001234567", national_id="35201-1234567-1")
    assert owner.get(f"{API}/employees/{emp['id']}").json()["bank_account"] == "PK36HABB0000001234567"
    # an HR manager has employees.manage but not bank.read
    owner.post(f"{API}/roles", {"key": "hr_no_bank", "name": "HR no bank", "permissions": ["employees.read", "employees.manage"]})
    hr = join(owner, new_client, "hr@x.test", "hr_no_bank")
    seen = hr.get(f"{API}/employees/{emp['id']}").json()
    assert seen["bank_account"] is None and seen["bank_name"] is None and seen["national_id"] == "35201-1234567-1"
    assert hr.patch(f"{API}/employees/{emp['id']}", {"bank_account": "X"}).status_code == 403
    assert hr.post(f"{API}/employees", {"first_name": "N", "last_name": "N", "joining_date": "2026-01-05",
                                        "bank_account": "X"}).status_code == 403


def test_bank_account_is_encrypted_at_rest(signup, db):
    owner = signup()
    mkemp(owner, email="enc@x.test", bank_account="PK36HABB0000001234567")
    raw = db.connection().exec_driver_sql("SELECT bank_account FROM employees WHERE bank_account IS NOT NULL").scalar()
    assert raw and "PK36" not in raw


def test_employees_are_isolated_between_tenants(signup):
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    ea = mkemp(a, first_name="Secret", email="s@a.test")
    assert b.get(f"{API}/employees/{ea['id']}").status_code == 404
    assert b.patch(f"{API}/employees/{ea['id']}", {"first_name": "Pwn"}).status_code == 404
    assert b.get(f"{API}/employees/{ea['id']}/documents").status_code == 404
    assert "Secret" not in str(b.get(f"{API}/employees").json())
    assert b.post(f"{API}/employees", {"first_name": "X", "last_name": "Y", "joining_date": "2026-01-05",
                                       "manager_id": ea["id"]}).status_code == 422


def test_self_service_profile_edit_is_limited(signup):
    owner = signup()
    r = owner.patch(f"{API}/me/employee", {"phone": "+923001112233", "address": "House 1", "first_name": "Hacked"})
    assert r.status_code == 200 and r.json()["phone"] == "+923001112233"
    assert r.json()["first_name"] == "Olivia"  # not editable through self service


# ------------------------------------------------------------------ bulk import
CSV = (
    "employee_code,first_name,last_name,email,joining_date,department,manager_code\n"
    "7001,Sara,Khan,sara@x.test,2026-02-01,Engineering,\n"
    "7002,Omar,Ali,omar@x.test,15/03/2026,Engineering,7001\n"
)


def _upload(api, url, text, name="people.csv", **data):
    return api.post(f"{API}{url}", files={"file": (name, io.BytesIO(text.encode()), "text/csv")}, data=data)


def test_bulk_import_preview_then_commit(signup):
    owner = signup()
    owner.post(f"{API}/departments", {"name": "Engineering"})
    pre = _upload(owner, "/employees/import/preview", CSV).json()
    assert pre["summary"] == {"total": 2, "valid": 2, "invalid": 0}
    assert owner.get(f"{API}/employees", params={"q": "sara"}).json()["total"] == 0  # preview writes nothing
    done = _upload(owner, "/employees/import/commit", CSV).json()
    assert done["created"] == 2
    omar = owner.get(f"{API}/employees", params={"q": "omar"}).json()["items"][0]
    assert omar["department"] == "Engineering" and omar["joining_date"] == "2026-03-15"
    assert omar["manager_id"] is not None


def test_bulk_import_reports_row_errors_and_does_not_corrupt(signup):
    owner = signup()
    mkemp(owner, employee_code="9000", email="dup@x.test")
    bad = (
        "employee_code,first_name,last_name,email,joining_date,department\n"
        "9001,Good,One,good@x.test,2026-02-01,\n"
        "9000,Dup,Code,new@x.test,2026-02-01,\n"
        "9002,Dup,Email,dup@x.test,2026-02-01,\n"
        "9003,,NoFirst,x@x.test,2026-02-01,\n"
        "9004,Bad,Date,y@x.test,not-a-date,\n"
        "9005,Bad,Dept,z@x.test,2026-02-01,Nowhere\n"
    )
    pre = _upload(owner, "/employees/import/preview", bad).json()
    assert pre["summary"] == {"total": 6, "valid": 1, "invalid": 5}
    errs = {r["row"]: " ".join(r["errors"]) for r in pre["rows"] if r["errors"]}
    assert "already exists" in errs[3] and "email already exists" in errs[4]
    assert "first_name" in errs[5] and "joining_date" in errs[6] and "unknown department" in errs[7]
    refused = _upload(owner, "/employees/import/commit", bad)
    assert refused.status_code == 422 and refused.json()["error"]["code"] == "import_has_errors"
    assert owner.get(f"{API}/employees", params={"q": "good"}).json()["total"] == 0
    partial = _upload(owner, "/employees/import/commit", bad, skip_invalid="true").json()
    assert partial == {"created": 1, "skipped": 5}


def test_bulk_import_duplicates_inside_the_file_and_bad_files(signup):
    owner = signup()
    dup = "first_name,last_name,email,joining_date\nA,A,same@x.test,2026-01-01\nB,B,same@x.test,2026-01-01\n"
    rows = _upload(owner, "/employees/import/preview", dup).json()["rows"]
    assert "duplicated in the file" in " ".join(rows[1]["errors"])
    assert _upload(owner, "/employees/import/preview", "x", name="a.exe").status_code == 422
    assert _upload(owner, "/employees/import/preview", "first_name\n").status_code == 422


def test_bulk_import_column_mapping_and_aliases(signup):
    owner = signup()
    csv = "Given,Surname,Mobile,Joined\nNadia,Iqbal,0300111,2026-04-01\n"
    r = owner.post(f"{API}/employees/import/preview", files={"file": ("m.csv", io.BytesIO(csv.encode()), "text/csv")},
                   data={"mapping": '{"Given": "first_name"}'})
    assert r.json()["summary"]["valid"] == 1


def test_bulk_import_respects_capacity(signup, db):
    from sqlalchemy import select

    from app.modules.tenancy.models import Tenant

    owner = signup()
    db.scalar(select(Tenant)).employee_capacity = 2
    db.commit()
    csv = "first_name,last_name,joining_date\nA,A,2026-01-01\nB,B,2026-01-01\n"
    pre = _upload(owner, "/employees/import/preview", csv).json()
    assert pre["summary"]["valid"] == 1 and "limit" in " ".join(pre["rows"][1]["errors"])


def test_import_template_downloads(signup):
    owner = signup()
    r = owner.get(f"{API}/employees/template.csv")
    assert r.status_code == 200 and r.text.startswith("employee_code,first_name,last_name")


# ------------------------------------------------------------------ documents & checklist
def _doc(api, eid, content=b"%PDF-1.4 hello", ctype="application/pdf", name="contract.pdf"):
    return api.post(f"{API}/employees/{eid}/documents", files={"file": (name, io.BytesIO(content), ctype)},
                    data={"title": "Contract", "category": "contract"})


def test_documents_upload_download_and_access_control(signup, new_client, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    owner = signup()
    emp = mkemp(owner, email="doc@x.test")
    other = mkemp(owner, email="other@x.test")
    up = _doc(owner, emp["id"])
    assert up.status_code == 201
    doc_id = up.json()["id"]
    dl = owner.get(f"{API}/documents/{doc_id}/download")
    assert dl.status_code == 200 and dl.content == b"%PDF-1.4 hello" and dl.headers["x-content-type-options"] == "nosniff"
    emp_api = join(owner, new_client, "doc@x.test", "employee")
    assert emp_api.get(f"{API}/documents/{doc_id}/download").status_code == 200  # own document
    other_api = join(owner, new_client, "other@x.test", "employee")
    assert other_api.get(f"{API}/documents/{doc_id}/download").status_code == 404
    assert other_api.get(f"{API}/employees/{emp['id']}/documents").status_code == 404
    assert other_api.delete(f"{API}/documents/{doc_id}").status_code == 404
    actions = [a["action"] for a in owner.get(f"{API}/audit-logs", params={"page_size": 100}).json()["items"]]
    assert "document.downloaded" in actions and "document.uploaded" in actions
    assert other["id"]


def test_document_upload_validation_and_tenant_isolation(signup, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    emp = mkemp(a, email="e@a.test")
    assert _doc(a, emp["id"], b"MZ", "application/x-msdownload", "x.exe").status_code == 422
    assert _doc(a, emp["id"], b"", "application/pdf").status_code == 422
    assert _doc(a, emp["id"], b"x" * (10 * 1024 * 1024 + 5)).status_code == 422
    doc_id = _doc(a, emp["id"]).json()["id"]
    assert b.get(f"{API}/documents/{doc_id}/download").status_code == 404
    assert b.delete(f"{API}/documents/{doc_id}").status_code == 404


def test_checklist_defaults_toggle_and_overview(signup):
    owner = signup()
    emp = mkemp(owner, email="c@x.test")
    items = owner.get(f"{API}/employees/{emp['id']}/checklist").json()
    assert len(items) == 6 and not any(i["done"] for i in items)
    r = owner.patch(f"{API}/employees/{emp['id']}/checklist/{items[0]['id']}", {"done": True})
    assert r.json()["done"] is True and r.json()["done_at"]
    added = owner.post(f"{API}/employees/{emp['id']}/checklist", {"title": "Issue ID card"})
    assert added.status_code == 201
    overview = owner.get(f"{API}/checklists/overview").json()
    assert any(o["employee_code"] == emp["employee_code"] and o["done"] == 1 and o["total"] == 7 for o in overview)


def test_education_records_are_owned_by_the_employee(signup, new_client):
    owner = signup()
    emp = mkemp(owner, email="edu@x.test")
    other = mkemp(owner, email="other@x.test")
    me = join(owner, new_client, "edu@x.test", "employee")
    r = me.post(f"{API}/employees/{emp['id']}/education", {"level": "Intermediate", "degree": "FSc", "grade": "B"})
    assert r.status_code == 201
    assert me.get(f"{API}/employees/{emp['id']}/education").json()[0]["degree"] == "FSc"
    assert me.post(f"{API}/employees/{other['id']}/education", {"level": "x", "degree": "y"}).status_code == 404


def test_org_structure_rules(signup):
    owner = signup()
    d = owner.post(f"{API}/departments", {"name": "Finance"}).json()
    assert owner.post(f"{API}/departments", {"name": "finance"}).status_code == 409
    sub = owner.post(f"{API}/departments", {"name": "Payables", "parent_id": d["id"]}).json()
    r = owner.put(f"{API}/departments/{d['id']}", {"name": "Finance", "parent_id": sub["id"]})
    assert r.status_code == 422 and r.json()["error"]["code"] == "department_cycle"
    br = owner.post(f"{API}/branches", {"name": "Head Office", "city": "Peshawar"}).json()
    mkemp(owner, email="b@x.test", branch_id=br["id"], department_id=d["id"])
    assert owner.delete(f"{API}/branches/{br['id']}").status_code == 409
    assert owner.delete(f"{API}/departments/{d['id']}").status_code == 409
    listed = {x["name"]: x for x in owner.get(f"{API}/departments").json()}
    assert listed["Finance"]["employee_count"] == 1
    owner.post(f"{API}/holidays", {"holiday_date": "2026-12-25", "name": "Quaid Day"})
    assert owner.post(f"{API}/holidays", {"holiday_date": "2026-12-25", "name": "Dup"}).status_code == 409
    assert len(owner.get(f"{API}/holidays", params={"year": 2026}).json()) == 1


@pytest.mark.parametrize("path", ["/branches", "/departments", "/designations", "/holidays", "/org-chart"])
def test_structure_endpoints_need_authentication(new_client, path):
    assert new_client().get(f"{API}{path}").status_code == 401


def test_my_employee_id_helper(signup):
    assert my_employee_id(signup())
