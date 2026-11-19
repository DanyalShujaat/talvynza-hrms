import io

from tests.helpers import API, join, mkemp

PDF = b"%PDF-1.4 resume"


def slug_of(api):
    return api.get(f"{API}/organization").json()["slug"]


def open_job(owner, title="Backend Engineer"):
    j = owner.post(f"{API}/recruitment/jobs", {"title": title, "description": "Build things", "openings": 2}).json()
    owner.post(f"{API}/recruitment/jobs/{j['id']}/status", {"stage": "open"})
    return j


def public_apply(client, slug, job_id, email="cand@x.test", resume=True):
    files = {"resume": ("cv.pdf", io.BytesIO(PDF), "application/pdf")} if resume else None
    return client.post(f"{API}/public/careers/{slug}/jobs/{job_id}/apply", files=files,
                       data={"full_name": "Cara Candidate", "email": email, "phone": "0300", "cover_note": "Hello"})


def test_career_page_settings_are_public_and_tenant_scoped(signup, new_client):
    a, b = signup("career-a@test.example", org="Career A"), signup("career-b@test.example", org="Career B")
    visitor = new_client()
    settings = {"headline": "Join the team", "introduction": "Work with us.",
                "accent_color": "#123abc", "cover_url": "https://example.com/cover.jpg",
                "logo_url": None}
    assert a.put(f"{API}/recruitment/career-settings", settings).status_code == 200
    assert a.get(f"{API}/recruitment/career-settings").json()["headline"] == "Join the team"
    assert visitor.get(f"{API}/public/careers/{slug_of(a)}").json()["settings"]["accent_color"] == "#123abc"
    assert b.get(f"{API}/recruitment/career-settings").json()["headline"] != "Join the team"
    assert a.put(f"{API}/recruitment/career-settings", {**settings, "cover_url": "javascript:alert(1)"}).status_code == 422


def test_public_careers_page_lists_only_open_jobs_and_accepts_applications(signup, new_client, tmp_path, monkeypatch):
    from app.core.config import get_settings

    monkeypatch.setattr(get_settings(), "storage_dir", str(tmp_path))
    owner = signup()
    job = open_job(owner)
    draft = owner.post(f"{API}/recruitment/jobs", {"title": "Hidden draft"}).json()
    visitor = new_client()  # no login
    page = visitor.get(f"{API}/public/careers/{slug_of(owner)}").json()
    assert page["organization"] == "Acme Ltd" and [j["title"] for j in page["jobs"]] == ["Backend Engineer"]
    assert public_apply(visitor, slug_of(owner), job["id"]).status_code == 201
    assert public_apply(visitor, slug_of(owner), job["id"]).status_code == 409  # one application per job
    assert public_apply(visitor, slug_of(owner), draft["id"]).status_code == 404  # not open
    apps = owner.get(f"{API}/recruitment/applications").json()
    assert len(apps) == 1 and apps[0]["stage"] == "Applied" and apps[0]["has_resume"] and apps[0]["source"] == "careers_page"
    assert owner.get(f"{API}/recruitment/applications/{apps[0]['id']}/resume").content == PDF


def test_public_endpoints_do_not_leak_or_cross_tenants(signup, new_client):
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    ja = open_job(a, "Secret Role")
    visitor = new_client()
    assert visitor.get(f"{API}/public/careers/{slug_of(b)}").json()["jobs"] == []
    assert public_apply(visitor, slug_of(b), ja["id"], resume=False).status_code == 404  # A's job via B's page
    assert visitor.get(f"{API}/public/careers/no-such-org").status_code == 404
    assert visitor.get(f"{API}/recruitment/applications").status_code == 401


def test_resume_upload_is_validated(signup, new_client):
    owner = signup()
    job = open_job(owner)
    bad = new_client().post(f"{API}/public/careers/{slug_of(owner)}/jobs/{job['id']}/apply",
                            files={"resume": ("x.exe", io.BytesIO(b"MZ"), "application/x-msdownload")},
                            data={"full_name": "Eve Evil", "email": "eve@x.test"})
    assert bad.status_code == 422
    assert owner.get(f"{API}/recruitment/applications").json() == []


def test_pipeline_moves_and_validation(signup, new_client):
    owner = signup()
    job = open_job(owner)
    app = owner.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "Sam Lee", "email": "sam@x.test"}).json()
    assert owner.get(f"{API}/recruitment/pipeline").json()["stages"][:3] == ["Applied", "Screening", "Assessment"]
    assert owner.post(f"{API}/recruitment/applications/{app['id']}/stage", {"stage": "Interview"}).json()["stage"] == "Interview"
    assert owner.post(f"{API}/recruitment/applications/{app['id']}/stage", {"stage": "Nonsense"}).status_code == 422
    r = owner.post(f"{API}/recruitment/applications/{app['id']}/stage", {"stage": "Hired"})
    assert r.status_code == 409 and r.json()["error"]["code"] == "use_hire_action"
    iv = owner.post(f"{API}/recruitment/applications/{app['id']}/interviews",
                    {"scheduled_at": "2026-12-01T10:00:00+05:00", "interviewer": "Dana Lead", "rating": 4, "notes": "Strong"})
    assert iv.status_code == 201
    assert owner.get(f"{API}/recruitment/applications/{app['id']}/interviews").json()[0]["rating"] == 4
    assert owner.post(f"{API}/recruitment/applications/{app['id']}/interviews",
                      {"scheduled_at": "2026-12-01T10:00:00", "interviewer": "X Y"}).status_code == 422


def test_custom_pipeline_rules(signup):
    owner = signup()
    job = open_job(owner)
    app = owner.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "Sam Lee", "email": "sam@x.test"}).json()
    new = ["Applied", "Phone Screen", "Onsite", "Offer", "Hired", "Rejected"]
    assert owner.put(f"{API}/recruitment/pipeline", {"stages": new}).status_code == 200
    assert owner.post(f"{API}/recruitment/applications/{app['id']}/stage", {"stage": "Onsite"}).status_code == 200
    assert owner.put(f"{API}/recruitment/pipeline", {"stages": ["Applied", "Hired", "Rejected"]}).status_code == 409  # Onsite in use
    assert owner.put(f"{API}/recruitment/pipeline", {"stages": ["Applied", "X", "Rejected"]}).status_code == 422  # Hired missing
    assert owner.put(f"{API}/recruitment/pipeline", {"stages": ["Applied", "Applied", "Hired", "Rejected"]}).status_code == 422


def test_hire_converts_candidate_to_employee_once(signup):
    owner = signup()
    dept = owner.post(f"{API}/departments", {"name": "Engineering"}).json()
    manager = mkemp(owner, email="manager@x.test")
    job = owner.post(f"{API}/recruitment/jobs", {"title": "Dev", "department_id": dept["id"]}).json()
    app = owner.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "Ada Lovelace", "email": "ada@x.test"}).json()
    r = owner.post(f"{API}/recruitment/applications/{app['id']}/hire", {"joining_date": "2026-12-01", "manager_id": manager["id"]})
    assert r.status_code == 200
    emp = owner.get(f"{API}/employees/{r.json()['employee_id']}").json()
    assert emp["full_name"] == "Ada Lovelace" and emp["department"] == "Engineering" and emp["status"] == "probation"
    assert emp["manager_id"] == manager["id"]
    assert len(owner.get(f"{API}/employees/{emp['id']}/checklist").json()) == 6  # onboarding starts automatically
    again = owner.post(f"{API}/recruitment/applications/{app['id']}/hire", {"joining_date": "2026-12-01"})
    assert again.status_code == 409 and again.json()["error"]["code"] == "already_hired"
    assert owner.get(f"{API}/recruitment/applications").json()[0]["stage"] == "Hired"


def test_hire_respects_duplicate_email_and_permissions(signup, new_client):
    owner = signup()
    mkemp(owner, email="dup@x.test")
    job = owner.post(f"{API}/recruitment/jobs", {"title": "Dev"}).json()
    app = owner.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "Dup Person", "email": "dup@x.test"}).json()
    assert owner.post(f"{API}/recruitment/applications/{app['id']}/hire", {"joining_date": "2026-12-01"}).status_code == 409
    rec = join(owner, new_client, "rec@x.test", "recruiter", name="Rec Ruiter")
    assert rec.get(f"{API}/recruitment/applications").status_code == 200
    assert rec.post(f"{API}/recruitment/applications/{app['id']}/hire", {"joining_date": "2026-12-01"}).status_code == 403  # no employees.manage
    emp = join(owner, new_client, "e@x.test", "employee", name="Plain Employee")
    assert emp.get(f"{API}/recruitment/applications").status_code == 403
    assert emp.get(f"{API}/recruitment/jobs").status_code == 403


def test_recruitment_data_is_tenant_isolated(signup):
    a, b = signup("a@a.test", "Org A"), signup("b@b.test", "Org B")
    job = open_job(a)
    app = a.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "Ann A", "email": "ann@a.test"}).json()
    assert b.get(f"{API}/recruitment/applications").json() == []
    assert b.post(f"{API}/recruitment/applications/{app['id']}/stage", {"stage": "Screening"}).status_code == 404
    assert b.post(f"{API}/recruitment/applications/{app['id']}/hire", {"joining_date": "2026-12-01"}).status_code == 404
    assert b.get(f"{API}/recruitment/applications/{app['id']}/resume").status_code == 404
    assert b.post(f"{API}/recruitment/applications", {"job_id": job["id"], "full_name": "X Y", "email": "x@y.test"}).status_code == 404
