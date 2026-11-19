from __future__ import annotations

import uuid
from datetime import date, datetime

from fastapi import APIRouter, Depends, File, Form, UploadFile
from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.errors import Conflict, NotFound, ValidationFailed
from app.core.ratelimit import rate_limit
from app.db.base import utcnow
from app.db.session import get_db
from app.db.tenant_scope import tenant_scope
from app.modules.employees import service as emp_service
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.notifications.service import notify_employee, notify_permission_holders
from app.modules.recruitment.models import DEFAULT_PIPELINE, Candidate, InterviewRecord, Job, JobApplication
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import Tenant

router = APIRouter(prefix="/recruitment", tags=["recruitment"], dependencies=[Depends(check_origin)])
public = APIRouter(prefix="/public", tags=["public careers"], dependencies=[Depends(check_origin)])
manage = require("recruitment.manage")


class JobIn(BaseModel):
    title: str = Field(min_length=3, max_length=160)
    department_id: uuid.UUID | None = None
    branch_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    description: str | None = Field(default=None, max_length=20000)
    employment_type: str = "full_time"
    openings: int = Field(default=1, ge=1, le=500)


class CandidateIn(BaseModel):
    full_name: str = Field(min_length=2, max_length=160)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=40)
    job_id: uuid.UUID
    cover_note: str | None = Field(default=None, max_length=5000)


class StageIn(BaseModel):
    stage: str = Field(max_length=40)


class InterviewIn(BaseModel):
    scheduled_at: datetime
    interviewer: str = Field(min_length=2, max_length=120)
    rating: int | None = Field(default=None, ge=1, le=5)
    notes: str | None = Field(default=None, max_length=5000)


class PipelineIn(BaseModel):
    stages: list[str] = Field(min_length=3, max_length=12)


class CareerSettingsIn(BaseModel):
    headline: str = Field(default="Build your future with us", min_length=3, max_length=120)
    introduction: str = Field(default="Explore our open roles and find your next opportunity.", max_length=600)
    accent_color: str = Field(default="#2563eb", pattern=r"^#[0-9a-fA-F]{6}$")
    cover_url: AnyHttpUrl | None = None
    logo_url: AnyHttpUrl | None = None


class HireIn(BaseModel):
    joining_date: date
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None


def pipeline_of(t: Tenant) -> list[str]:
    return list(t.settings.get("pipeline") or DEFAULT_PIPELINE)


def career_settings_of(t: Tenant) -> dict:
    return CareerSettingsIn.model_validate(t.settings.get("career_page") or {}).model_dump(mode="json")


@router.get("/career-settings")
def get_career_settings(ctx: AuthContext = Depends(require("recruitment.read_assigned"))):
    return career_settings_of(ctx.tenant)


@router.put("/career-settings")
def set_career_settings(body: CareerSettingsIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    settings = body.model_dump(mode="json")
    ctx.tenant.settings = {**ctx.tenant.settings, "career_page": settings}
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id,
                         action="recruitment.career_page_changed", entity_type="tenant", ip=ctx.ip)
    db.commit()
    return settings


def _job(j: Job, counts: dict) -> dict:
    return {"id": j.id, "title": j.title, "department_id": j.department_id, "branch_id": j.branch_id,
            "designation_id": j.designation_id, "description": j.description, "employment_type": j.employment_type,
            "openings": j.openings, "status": j.status, "published_at": j.published_at,
            "applicants": counts.get(j.id, 0)}


# ------------------------------------------------------------------ pipeline
@router.get("/pipeline")
def get_pipeline(ctx: AuthContext = Depends(require("recruitment.read_assigned")), db: Session = Depends(get_db)):
    return {"stages": pipeline_of(ctx.tenant)}


@router.put("/pipeline")
def set_pipeline(body: PipelineIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    stages = [s.strip() for s in body.stages]
    if len({s.lower() for s in stages}) != len(stages) or any(not s for s in stages):
        raise ValidationFailed("Stage names must be unique and not empty")
    for required in ("Applied", "Hired", "Rejected"):
        if required not in stages:
            raise ValidationFailed(f"The pipeline must keep the '{required}' stage")
    in_use = set(db.scalars(select(JobApplication.stage).distinct()))
    missing = in_use - set(stages)
    if missing:
        raise Conflict(f"Candidates are in stages you removed: {', '.join(sorted(missing))}", code="stage_in_use")
    ctx.tenant.settings = {**ctx.tenant.settings, "pipeline": stages}
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="recruitment.pipeline_changed",
                         entity_type="tenant", details={"stages": stages}, ip=ctx.ip)
    db.commit()
    return {"stages": stages}


# ------------------------------------------------------------------ jobs
@router.get("/jobs")
def list_jobs(ctx: AuthContext = Depends(require("recruitment.read_assigned")), db: Session = Depends(get_db)):
    counts = dict(db.execute(select(JobApplication.job_id, func.count()).group_by(JobApplication.job_id)).all())
    return [_job(j, counts) for j in db.scalars(select(Job).order_by(Job.created_at.desc()))]


@router.post("/jobs", status_code=201)
def create_job(body: JobIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    j = Job(tenant_id=ctx.tenant.id, created_by=ctx.identity.id, **body.model_dump())
    db.add(j)
    db.commit()
    return _job(j, {})


@router.put("/jobs/{job_id}")
def update_job(job_id: uuid.UUID, body: JobIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise NotFound("Job not found")
    for k, v in body.model_dump().items():
        setattr(j, k, v)
    db.commit()
    return _job(j, {})


@router.post("/jobs/{job_id}/status")
def set_job_status(job_id: uuid.UUID, body: StageIn, ctx: AuthContext = Depends(manage),
                   db: Session = Depends(get_db)):
    j = db.get(Job, job_id)
    if j is None:
        raise NotFound("Job not found")
    if body.stage not in ("draft", "open", "closed"):
        raise ValidationFailed("Status must be draft, open or closed")
    j.status = body.stage
    if body.stage == "open" and j.published_at is None:
        j.published_at = utcnow()
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action=f"job.{body.stage}",
                         entity_type="job", entity_id=j.id, ip=ctx.ip)
    db.commit()
    return _job(j, {})


# ------------------------------------------------------------------ candidates & applications
def _app(a: JobApplication, cands: dict, jobs: dict) -> dict:
    c = cands.get(a.candidate_id)
    return {"id": a.id, "job_id": a.job_id, "job": jobs.get(a.job_id), "candidate_id": a.candidate_id,
            "full_name": c.full_name if c else None, "email": c.email if c else None,
            "phone": c.phone if c else None, "source": c.source if c else None,
            "has_resume": bool(c and c.resume_key), "stage": a.stage, "cover_note": a.cover_note,
            "employee_id": a.employee_id, "created_at": a.created_at}


@router.get("/applications")
def list_applications(job_id: uuid.UUID | None = None,
                      ctx: AuthContext = Depends(require("recruitment.read_assigned")),
                      db: Session = Depends(get_db)):
    stmt = select(JobApplication).order_by(JobApplication.created_at.desc()).limit(500)
    if job_id:
        stmt = stmt.where(JobApplication.job_id == job_id)
    rows = db.scalars(stmt).all()
    cands = {c.id: c for c in db.scalars(select(Candidate))}
    jobs = {j.id: j.title for j in db.scalars(select(Job))}
    return [_app(a, cands, jobs) for a in rows]


@router.post("/applications", status_code=201)
def add_candidate(body: CandidateIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    return _create_application(db, ctx.tenant.id, body.job_id, body.full_name, str(body.email), body.phone,
                               body.cover_note, "manual", None, None, None, ctx.identity.id)


def _create_application(db, tenant_id, job_id, name, email, phone, note, source, key, fname, ctype,
                        actor_id=None) -> dict:
    job = db.get(Job, job_id)
    if job is None:
        raise NotFound("Job not found")
    email = email.strip().lower()
    cand = db.scalar(select(Candidate).where(Candidate.email == email))
    if cand is None:
        cand = Candidate(tenant_id=tenant_id, full_name=name.strip(), email=email, phone=phone, source=source,
                         resume_key=key, resume_name=fname, resume_type=ctype)
        db.add(cand)
        db.flush()
    elif key and not cand.resume_key:
        cand.resume_key, cand.resume_name, cand.resume_type = key, fname, ctype
    if db.scalar(select(JobApplication.id).where(JobApplication.job_id == job.id,
                                                 JobApplication.candidate_id == cand.id)):
        raise Conflict("This candidate has already applied for this job", code="duplicate_application")
    a = JobApplication(tenant_id=tenant_id, job_id=job.id, candidate_id=cand.id, stage="Applied",
                       cover_note=note, stage_changed_at=utcnow())
    db.add(a)
    db.flush()
    notify_permission_holders(db, tenant_id, "recruitment.manage", "recruitment",
                              f"New applicant for {job.title}", cand.full_name, "/hire",
                              dedupe_key=f"application-new:{a.id}", exclude_identity_id=actor_id)
    db.commit()
    return _app(a, {cand.id: cand}, {job.id: job.title})


@router.post("/applications/{application_id}/stage")
def move_stage(application_id: uuid.UUID, body: StageIn, ctx: AuthContext = Depends(manage),
               db: Session = Depends(get_db)):
    a = db.get(JobApplication, application_id)
    if a is None:
        raise NotFound("Application not found")
    stages = pipeline_of(ctx.tenant)
    if body.stage not in stages:
        raise ValidationFailed("Unknown pipeline stage", details=stages)
    if body.stage == "Hired":
        raise Conflict("Use the hire action to convert a candidate into an employee", code="use_hire_action")
    if a.stage == "Hired":
        raise Conflict("This candidate has already been hired", code="already_hired")
    a.stage, a.stage_changed_at = body.stage, utcnow()
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="application.stage_changed",
                         entity_type="application", entity_id=a.id, details={"stage": body.stage}, ip=ctx.ip)
    notify_permission_holders(db, ctx.tenant.id, "recruitment.manage", "recruitment",
                              "Applicant stage updated", f"{body.stage}: {db.get(Candidate, a.candidate_id).full_name}",
                              "/hire", exclude_identity_id=ctx.identity.id)
    db.commit()
    return {"id": a.id, "stage": a.stage}


@router.post("/applications/{application_id}/hire")
def hire(application_id: uuid.UUID, body: HireIn, ctx: AuthContext = Depends(require("recruitment.manage",
                                                                                      "employees.manage")),
         db: Session = Depends(get_db)):
    """Converts the candidate into an employee record without re-typing their details."""
    a = db.get(JobApplication, application_id)
    if a is None:
        raise NotFound("Application not found")
    if a.stage == "Hired" or a.employee_id:
        raise Conflict("This candidate has already been hired", code="already_hired")
    cand, job = db.get(Candidate, a.candidate_id), db.get(Job, a.job_id)
    first, _, last = cand.full_name.partition(" ")
    emp = emp_service.create_employee(db, tenant=ctx.tenant, actor=ctx.identity.id, ip=ctx.ip, data={
        "first_name": first, "last_name": last or "-", "email": cand.email, "phone": cand.phone,
        "joining_date": body.joining_date, "employment_type": job.employment_type, "status": "probation",
        "branch_id": body.branch_id or job.branch_id, "department_id": body.department_id or job.department_id,
        "designation_id": body.designation_id or job.designation_id, "manager_id": body.manager_id})
    a.stage, a.employee_id, a.stage_changed_at = "Hired", emp.id, utcnow()
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="application.hired",
                         entity_type="application", entity_id=a.id, details={"employee_id": str(emp.id)}, ip=ctx.ip)
    if emp.manager_id:
        notify_employee(db, db.get(emp_service.Employee, emp.manager_id), "onboarding",
                        f"New team member: {emp.full_name}", "Review the onboarding checklist.",
                        f"/employees/{emp.id}")
    db.commit()
    return {"employee_id": emp.id, "employee_code": emp.employee_code}


@router.get("/applications/{application_id}/interviews")
def list_interviews(application_id: uuid.UUID, ctx: AuthContext = Depends(require("recruitment.read_assigned")),
                    db: Session = Depends(get_db)):
    return [{"id": i.id, "scheduled_at": i.scheduled_at, "interviewer": i.interviewer, "rating": i.rating,
             "notes": i.notes} for i in db.scalars(select(InterviewRecord).where(
                 InterviewRecord.application_id == application_id).order_by(InterviewRecord.scheduled_at))]


@router.post("/applications/{application_id}/interviews", status_code=201)
def add_interview(application_id: uuid.UUID, body: InterviewIn, ctx: AuthContext = Depends(manage),
                  db: Session = Depends(get_db)):
    if db.get(JobApplication, application_id) is None:
        raise NotFound("Application not found")
    if body.scheduled_at.tzinfo is None:
        raise ValidationFailed("scheduled_at needs a time zone offset", code="naive_datetime")
    i = InterviewRecord(tenant_id=ctx.tenant.id, application_id=application_id, created_by=ctx.identity.id,
                        **body.model_dump())
    db.add(i)
    db.commit()
    return {"id": i.id}


@router.get("/applications/{application_id}/resume")
def download_resume(application_id: uuid.UUID, ctx: AuthContext = Depends(require("recruitment.read_assigned")),
                    db: Session = Depends(get_db)):
    from fastapi import Response

    a = db.get(JobApplication, application_id)
    cand = db.get(Candidate, a.candidate_id) if a else None
    if cand is None or not cand.resume_key:
        raise NotFound("No resume on file")
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="resume.downloaded",
                         entity_type="candidate", entity_id=cand.id, ip=ctx.ip)
    db.commit()
    filename = (cand.resume_name or "resume").replace('"', "")
    return Response(storage.get_storage().get(cand.resume_key), media_type=cand.resume_type or "application/pdf",
                    headers={"Content-Disposition": f'attachment; filename="{filename}"',
                             "X-Content-Type-Options": "nosniff"})


# ------------------------------------------------------------------ public careers page (no login)
def _public_tenant(db: Session, slug: str) -> Tenant:
    t = db.scalar(select(Tenant).where(Tenant.slug == slug))
    if t is None or t.status not in ("trialing", "active"):
        raise NotFound("Careers page not found")
    return t


@public.get("/careers/{slug}", dependencies=[Depends(rate_limit("careers", limit=60))])
def careers(slug: str, db: Session = Depends(get_db)):
    t = _public_tenant(db, slug)
    with tenant_scope(db, t.id):
        rows = db.scalars(select(Job).where(Job.status == "open").order_by(Job.published_at.desc())).all()
        jobs = [{"id": j.id, "title": j.title, "description": j.description,
                 "employment_type": j.employment_type} for j in rows]
        return {"organization": t.name, "settings": career_settings_of(t), "jobs": jobs}


@public.post("/careers/{slug}/jobs/{job_id}/apply", status_code=201,
             dependencies=[Depends(rate_limit("apply", limit=10))])
def apply_public(slug: str, job_id: uuid.UUID, full_name: str = Form(min_length=2, max_length=160),
                 email: EmailStr = Form(...), phone: str | None = Form(default=None, max_length=40),
                 cover_note: str | None = Form(default=None, max_length=5000),
                 resume: UploadFile | None = File(default=None), db: Session = Depends(get_db)):
    t = _public_tenant(db, slug)
    with tenant_scope(db, t.id):
        job = db.get(Job, job_id)
        if job is None or job.status != "open":
            raise NotFound("This job is not open")
        key = fname = ctype = None
        if resume is not None:
            data = resume.file.read(storage.MAX_UPLOAD_BYTES + 1)
            ctype = resume.content_type or "application/octet-stream"
            storage.validate_upload(data, resume.filename or "resume", ctype)
            key, fname = storage.get_storage().put(t.id, data), (resume.filename or "resume")[:255]
        _create_application(db, t.id, job.id, full_name, str(email), phone, cover_note, "careers_page", key, fname,
                            ctype)
    return {"message": "Application received"}
