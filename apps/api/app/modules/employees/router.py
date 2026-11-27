from __future__ import annotations

import json
import uuid
from datetime import date
from typing import Any

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.employees import service
from app.modules.employees.models import (
    LIVE_STATUSES,
    ChecklistItem,
    Employee,
    EmployeeAssignment,
    EmployeeDocument,
    EmployeeEducation,
    EmployeeLifecycleEvent,
)
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import TenantMembership

router = APIRouter(tags=["employees"], dependencies=[Depends(check_origin)])


# ------------------------------------------------------------------ schemas
class EmployeeIn(BaseModel):
    employee_code: str | None = Field(default=None, max_length=30)
    bio_id: str | None = Field(default=None, max_length=30)
    first_name: str = Field(min_length=1, max_length=80)
    last_name: str = Field(min_length=1, max_length=80)
    preferred_name: str | None = Field(default=None, max_length=80)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=40)
    gender: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    national_id: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=400)
    emergency_contacts: list[dict[str, Any]] = Field(default_factory=list, max_length=5)
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    employment_type: str = "full_time"
    contract_type: str | None = None
    contract_end: date | None = None
    work_location: str | None = None
    joining_date: date
    probation_end: date | None = None
    payment_method: str | None = None
    bank_name: str | None = None
    bank_account: str | None = Field(default=None, max_length=60)


class EmployeeUpdate(BaseModel):
    bio_id: str | None = None
    first_name: str | None = Field(default=None, min_length=1, max_length=80)
    last_name: str | None = Field(default=None, min_length=1, max_length=80)
    preferred_name: str | None = None
    email: EmailStr | None = None
    phone: str | None = None
    gender: str | None = None
    date_of_birth: date | None = None
    nationality: str | None = None
    national_id: str | None = None
    address: str | None = None
    emergency_contacts: list[dict[str, Any]] | None = None
    branch_id: uuid.UUID | None = None
    department_id: uuid.UUID | None = None
    designation_id: uuid.UUID | None = None
    manager_id: uuid.UUID | None = None
    employment_type: str | None = None
    contract_type: str | None = None
    contract_end: date | None = None
    work_location: str | None = None
    probation_end: date | None = None
    payment_method: str | None = None
    bank_name: str | None = None
    bank_account: str | None = None


class SelfUpdate(BaseModel):
    preferred_name: str | None = Field(default=None, max_length=80)
    phone: str | None = Field(default=None, max_length=40)
    address: str | None = Field(default=None, max_length=400)
    emergency_contacts: list[dict[str, Any]] | None = Field(default=None, max_length=5)


class LifecycleIn(BaseModel):
    event_type: str
    effective_date: date
    details: dict[str, Any] = Field(default_factory=dict)


class EducationIn(BaseModel):
    level: str = Field(max_length=60)
    degree: str = Field(max_length=120)
    institute: str | None = None
    obtained_marks: str | None = None
    total_marks: str | None = None
    grade: str | None = None
    division: str | None = None
    remarks: str | None = None


class ChecklistIn(BaseModel):
    title: str = Field(min_length=2, max_length=160)


class ChecklistPatch(BaseModel):
    done: bool


class LinkIn(BaseModel):
    membership_id: uuid.UUID | None


# ------------------------------------------------------------------ serialization
def _summary(e: Employee, names: dict) -> dict:
    return {
        "id": e.id, "employee_code": e.employee_code, "bio_id": e.bio_id, "first_name": e.first_name,
        "last_name": e.last_name, "full_name": e.full_name, "email": e.email, "phone": e.phone,
        "branch_id": e.branch_id, "branch": names["branch"].get(e.branch_id),
        "department_id": e.department_id, "department": names["department"].get(e.department_id),
        "designation_id": e.designation_id, "designation": names["designation"].get(e.designation_id),
        "manager_id": e.manager_id, "status": e.status, "joining_date": e.joining_date,
        "has_login": e.membership_id is not None,
    }


def _detail(e: Employee, names: dict, perms: set[str], is_self: bool) -> dict:
    out = _summary(e, names)
    out.update({
        "preferred_name": e.preferred_name, "gender": e.gender, "date_of_birth": e.date_of_birth,
        "nationality": e.nationality, "address": e.address, "emergency_contacts": e.emergency_contacts,
        "employment_type": e.employment_type, "contract_type": e.contract_type, "contract_end": e.contract_end,
        "work_location": e.work_location, "probation_end": e.probation_end,
        "confirmation_date": e.confirmation_date, "exit_date": e.exit_date, "payment_method": e.payment_method,
        "national_id": e.national_id if (is_self or "employees.manage" in perms) else None,
        "bank_name": e.bank_name if (is_self or "bank.read" in perms) else None,
        "bank_account": e.bank_account if (is_self or "bank.read" in perms) else None,
        "membership_id": e.membership_id,
    })
    return out


def _me(db: Session, ctx: AuthContext) -> Employee | None:
    return service.current_employee(db, ctx.membership.id if ctx.membership else None)


def _need_any(ctx: AuthContext, *perms: str) -> None:
    if not any(p in ctx.permissions for p in perms):
        raise Forbidden("You do not have permission to perform this action", code="permission_denied",
                        details=list(perms))


def _target(db: Session, ctx: AuthContext, employee_id: uuid.UUID) -> tuple[Employee, Employee | None]:
    me = _me(db, ctx)
    service.assert_can_view(db, ctx.permissions, me, employee_id)
    return service.get_employee(db, employee_id), me


# ------------------------------------------------------------------ employees
@router.get("/employees")
def list_employees(branch_id: uuid.UUID | None = None, department_id: uuid.UUID | None = None,
                   status: str | None = "active", q: str | None = Query(default=None, max_length=80),
                   letter: str | None = Query(default=None, max_length=1), page: int = Query(1, ge=1),
                   page_size: int = Query(25, ge=1, le=100), ctx: AuthContext = Depends(get_tenant_ctx),
                   db: Session = Depends(get_db)):
    _need_any(ctx, "employees.read", "employees.read_team", "employees.read_own")
    allowed = service.visible_ids(db, ctx.permissions, _me(db, ctx))
    rows, total = service.list_employees(db, allowed=allowed, branch_id=branch_id, department_id=department_id,
                                         status=status, q=q, letter=letter, page=page, page_size=page_size)
    names = service.name_maps(db)
    return {"items": [_summary(e, names) for e in rows], "total": total, "page": page, "page_size": page_size}


@router.post("/employees", status_code=201)
def create_employee(body: EmployeeIn, ctx: AuthContext = Depends(require("employees.manage")),
                    db: Session = Depends(get_db)):
    data = body.model_dump()
    if (data.get("bank_account") or data.get("bank_name")) and "bank.read" not in ctx.permissions:
        raise Forbidden("Bank details need the bank.read permission", code="permission_denied")
    emp = service.create_employee(db, tenant=ctx.tenant, actor=ctx.identity.id, data=data, ip=ctx.ip)
    return _detail(emp, service.name_maps(db), ctx.permissions, False)


@router.get("/employees/setup")
def employee_setup(ctx: AuthContext = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    return {"missing": service.missing_setup(db)}


@router.get("/employees/template.csv", response_class=PlainTextResponse)
def import_template(ctx: AuthContext = Depends(require("employees.manage"))):
    return PlainTextResponse(service.template_csv(), media_type="text/csv",
                             headers={"Content-Disposition": 'attachment; filename="employee-import-template.csv"'})


def _read_import(file: UploadFile, mapping: str | None) -> list[dict]:
    data = file.file.read(service.MAX_IMPORT_BYTES + 1)
    parsed_map = None
    if mapping:
        try:
            parsed_map = json.loads(mapping)
        except ValueError:
            from app.core.errors import ValidationFailed
            raise ValidationFailed("Column mapping must be valid JSON") from None
    return service.parse_sheet(file.filename or "", data, parsed_map)


@router.post("/employees/import/preview")
def import_preview(file: UploadFile = File(...), mapping: str | None = Form(default=None),
                   ctx: AuthContext = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    validated = service.validate_import(db, ctx.tenant, _read_import(file, mapping))
    for r in validated["rows"]:  # JSON friendly
        r["data"] = {k: (str(v) if isinstance(v, (uuid.UUID, date)) else v) for k, v in r["data"].items()}
    return validated


@router.post("/employees/import/commit")
def import_commit(file: UploadFile = File(...), mapping: str | None = Form(default=None),
                  skip_invalid: bool = Form(default=False), ctx: AuthContext = Depends(require("employees.manage")),
                  db: Session = Depends(get_db)):
    validated = service.validate_import(db, ctx.tenant, _read_import(file, mapping))
    created = service.commit_import(db, tenant=ctx.tenant, actor=ctx.identity.id, validated=validated,
                                    skip_invalid=skip_invalid, ip=ctx.ip)
    return {"created": created, "skipped": validated["summary"]["invalid"]}


@router.get("/me/employee")
def my_profile(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    if me is None:
        raise NotFound("No employee record is linked to your account")
    return _detail(me, service.name_maps(db), ctx.permissions, True)


@router.patch("/me/employee")
def update_my_profile(body: SelfUpdate, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = _me(db, ctx)
    if me is None:
        raise NotFound("No employee record is linked to your account")
    service.update_employee(db, tenant=ctx.tenant, actor=ctx.identity.id, emp=me,
                            changes=body.model_dump(exclude_unset=True), ip=ctx.ip)
    return _detail(me, service.name_maps(db), ctx.permissions, True)


@router.get("/employees/{employee_id}")
def get_employee(employee_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    emp, me = _target(db, ctx, employee_id)
    return _detail(emp, service.name_maps(db), ctx.permissions, me is not None and me.id == emp.id)


@router.patch("/employees/{employee_id}")
def update_employee(employee_id: uuid.UUID, body: EmployeeUpdate,
                    ctx: AuthContext = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    changes = body.model_dump(exclude_unset=True)
    if {"bank_name", "bank_account", "payment_method"} & set(changes) and "bank.read" not in ctx.permissions:
        raise Forbidden("Bank details need the bank.read permission", code="permission_denied")
    service.update_employee(db, tenant=ctx.tenant, actor=ctx.identity.id, emp=emp, changes=changes, ip=ctx.ip)
    return _detail(emp, service.name_maps(db), ctx.permissions, False)


@router.delete("/employees/{employee_id}", status_code=204)
def delete_employee(employee_id: uuid.UUID, ctx: AuthContext = Depends(require("employees.manage")),
                    db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    if emp.membership_id is not None:
        raise Forbidden("Remove the member's access before deleting this record", code="has_login")
    emp.deleted_at = utcnow()  # soft delete; history stays
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="employee.deleted",
                         entity_type="employee", entity_id=emp.id, ip=ctx.ip)
    db.commit()


@router.post("/employees/{employee_id}/lifecycle")
def lifecycle(employee_id: uuid.UUID, body: LifecycleIn, ctx: AuthContext = Depends(require("employees.manage")),
              db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    service.record_lifecycle(db, tenant=ctx.tenant, actor=ctx.identity.id, emp=emp, event_type=body.event_type,
                             effective_date=body.effective_date, details=body.details, ip=ctx.ip)
    return _detail(emp, service.name_maps(db), ctx.permissions, False)


@router.get("/employees/{employee_id}/history")
def history(employee_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    emp, _ = _target(db, ctx, employee_id)
    names = service.name_maps(db)
    assignments = db.scalars(select(EmployeeAssignment).where(EmployeeAssignment.employee_id == emp.id)
                             .order_by(EmployeeAssignment.effective_from.desc()))
    evts = db.scalars(select(EmployeeLifecycleEvent).where(EmployeeLifecycleEvent.employee_id == emp.id)
                      .order_by(EmployeeLifecycleEvent.effective_date.desc(),
                                EmployeeLifecycleEvent.created_at.desc()))
    return {
        "assignments": [{"branch": names["branch"].get(a.branch_id), "department": names["department"].get(a.department_id),
                         "designation": names["designation"].get(a.designation_id), "manager_id": a.manager_id,
                         "effective_from": a.effective_from, "effective_to": a.effective_to} for a in assignments],
        "events": [{"id": v.id, "event_type": v.event_type, "effective_date": v.effective_date, "details": v.details}
                   for v in evts],
    }


class PortalInviteIn(BaseModel):
    role_key: str = Field(default="employee", max_length=60)


@router.post("/employees/{employee_id}/invite", status_code=201)
def invite_to_portal(employee_id: uuid.UUID, body: PortalInviteIn,
                     ctx: AuthContext = Depends(require("employees.manage", "members.manage")),
                     db: Session = Depends(get_db)):
    """Emails the employee a link to set a password and sign in. The login is linked to this record by email."""
    emp = service.get_employee(db, employee_id)
    if emp.membership_id is not None:
        raise Conflict("This employee already has a login", code="already_has_login")
    if not emp.email:
        raise ValidationFailed("Add a work email to this employee before inviting them", code="email_required")
    if emp.status not in LIVE_STATUSES:
        raise Conflict("Only current employees can be invited", code="invalid_status")
    tenancy.invite_member(db, tenant=ctx.tenant, actor=ctx.identity, actor_perms=ctx.permissions, email=emp.email,
                          role_key=body.role_key, ip=ctx.ip)
    return {"message": f"Invitation sent to {emp.email}"}


@router.put("/employees/{employee_id}/link-member")
def link_member(employee_id: uuid.UUID, body: LinkIn,
                ctx: AuthContext = Depends(require("employees.manage", "members.manage")),
                db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    if body.membership_id is not None:
        m = db.scalar(select(TenantMembership).where(TenantMembership.id == body.membership_id,
                                                     TenantMembership.tenant_id == ctx.tenant.id))
        if m is None:
            raise NotFound("Member not found")
        if db.scalar(select(Employee).where(Employee.membership_id == m.id, Employee.id != emp.id)):
            from app.core.errors import Conflict
            raise Conflict("That member is already linked to another employee")
    emp.membership_id = body.membership_id
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="employee.login_linked",
                         entity_type="employee", entity_id=emp.id, ip=ctx.ip)
    db.commit()
    return {"membership_id": emp.membership_id}


# ------------------------------------------------------------------ education
def _edu(e: EmployeeEducation) -> dict:
    return {"id": e.id, "level": e.level, "degree": e.degree, "institute": e.institute,
            "obtained_marks": e.obtained_marks, "total_marks": e.total_marks, "grade": e.grade,
            "division": e.division, "remarks": e.remarks}


def _can_edit_profile(ctx: AuthContext, me: Employee | None, emp: Employee) -> bool:
    return "employees.manage" in ctx.permissions or (me is not None and me.id == emp.id)


@router.get("/employees/{employee_id}/education")
def list_education(employee_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    emp, _ = _target(db, ctx, employee_id)
    return [_edu(e) for e in db.scalars(select(EmployeeEducation).where(EmployeeEducation.employee_id == emp.id))]


@router.post("/employees/{employee_id}/education", status_code=201)
def add_education(employee_id: uuid.UUID, body: EducationIn, ctx: AuthContext = Depends(get_tenant_ctx),
                  db: Session = Depends(get_db)):
    emp, me = _target(db, ctx, employee_id)
    if not _can_edit_profile(ctx, me, emp):
        raise Forbidden("You cannot edit this profile", code="permission_denied")
    row = EmployeeEducation(tenant_id=ctx.tenant.id, employee_id=emp.id, **body.model_dump())
    db.add(row)
    db.commit()
    return _edu(row)


@router.delete("/employees/{employee_id}/education/{edu_id}", status_code=204)
def delete_education(employee_id: uuid.UUID, edu_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx),
                     db: Session = Depends(get_db)):
    emp, me = _target(db, ctx, employee_id)
    if not _can_edit_profile(ctx, me, emp):
        raise Forbidden("You cannot edit this profile", code="permission_denied")
    row = db.scalar(select(EmployeeEducation).where(EmployeeEducation.id == edu_id,
                                                    EmployeeEducation.employee_id == emp.id))
    if row is None:
        raise NotFound("Record not found")
    db.delete(row)
    db.commit()


# ------------------------------------------------------------------ checklist
def _chk(c: ChecklistItem) -> dict:
    return {"id": c.id, "title": c.title, "done": c.done, "done_at": c.done_at}


@router.get("/employees/{employee_id}/checklist")
def checklist(employee_id: uuid.UUID, ctx: AuthContext = Depends(require("employees.manage")),
              db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    return [_chk(c) for c in db.scalars(select(ChecklistItem).where(ChecklistItem.employee_id == emp.id)
                                        .order_by(ChecklistItem.done, ChecklistItem.title))]


@router.get("/checklists/overview")
def checklist_overview(ctx: AuthContext = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    """Per-employee onboarding progress for everyone with open items."""
    emps = {e.id: e for e in db.scalars(select(Employee).where(Employee.deleted_at.is_(None),
                                                              Employee.status.in_(("active", "probation"))))}
    prog: dict[uuid.UUID, list[int]] = {}
    for c in db.scalars(select(ChecklistItem)):
        p = prog.setdefault(c.employee_id, [0, 0])
        p[0] += int(c.done)
        p[1] += 1
    out = [{"employee_id": i, "full_name": emps[i].full_name, "employee_code": emps[i].employee_code,
            "done": d, "total": t} for i, (d, t) in prog.items() if i in emps and d < t]
    return sorted(out, key=lambda r: r["full_name"])


@router.post("/employees/{employee_id}/checklist", status_code=201)
def add_checklist(employee_id: uuid.UUID, body: ChecklistIn, ctx: AuthContext = Depends(require("employees.manage")),
                  db: Session = Depends(get_db)):
    emp = service.get_employee(db, employee_id)
    c = ChecklistItem(tenant_id=ctx.tenant.id, employee_id=emp.id, title=body.title.strip())
    db.add(c)
    db.commit()
    return _chk(c)


@router.patch("/employees/{employee_id}/checklist/{item_id}")
def toggle_checklist(employee_id: uuid.UUID, item_id: uuid.UUID, body: ChecklistPatch,
                     ctx: AuthContext = Depends(require("employees.manage")), db: Session = Depends(get_db)):
    c = db.scalar(select(ChecklistItem).where(ChecklistItem.id == item_id, ChecklistItem.employee_id == employee_id))
    if c is None:
        raise NotFound("Checklist item not found")
    c.done, c.done_at = body.done, (utcnow() if body.done else None)
    db.commit()
    return _chk(c)


# ------------------------------------------------------------------ documents
def _doc(d: EmployeeDocument) -> dict:
    return {"id": d.id, "title": d.title, "category": d.category, "filename": d.filename,
            "content_type": d.content_type, "size_bytes": d.size_bytes, "expires_on": d.expires_on,
            "created_at": d.created_at}


def _doc_access(ctx: AuthContext, me: Employee | None, emp: Employee) -> None:
    own = me is not None and me.id == emp.id
    if not (own or "documents.manage" in ctx.permissions or "employees.manage" in ctx.permissions):
        raise NotFound("Employee not found")


@router.get("/employees/{employee_id}/documents")
def list_documents(employee_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    emp, me = _target(db, ctx, employee_id)
    _doc_access(ctx, me, emp)
    return [_doc(d) for d in db.scalars(select(EmployeeDocument).where(EmployeeDocument.employee_id == emp.id)
                                        .order_by(EmployeeDocument.created_at.desc()))]


@router.post("/employees/{employee_id}/documents", status_code=201)
def upload_document(employee_id: uuid.UUID, file: UploadFile = File(...), title: str = Form(...),
                    category: str = Form(default="other"), expires_on: date | None = Form(default=None),
                    ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    emp, me = _target(db, ctx, employee_id)
    _doc_access(ctx, me, emp)
    data = file.file.read(storage.MAX_UPLOAD_BYTES + 1)
    ctype = file.content_type or "application/octet-stream"
    storage.validate_upload(data, file.filename or "upload", ctype)
    key = storage.get_storage().put(ctx.tenant.id, data)
    doc = EmployeeDocument(tenant_id=ctx.tenant.id, employee_id=emp.id, title=title.strip()[:160],
                           category=category[:40], filename=(file.filename or "upload")[:255], content_type=ctype,
                           size_bytes=len(data), storage_key=key, expires_on=expires_on,
                           uploaded_by=ctx.identity.id, created_at=utcnow())
    db.add(doc)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="document.uploaded",
                         entity_type="employee_document", entity_id=doc.id, details={"employee_id": str(emp.id)},
                         ip=ctx.ip)
    db.commit()
    return _doc(doc)


@router.get("/documents/{doc_id}/download")
def download_document(doc_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    doc = db.scalar(select(EmployeeDocument).where(EmployeeDocument.id == doc_id))
    if doc is None:
        raise NotFound("Document not found")
    emp = service.get_employee(db, doc.employee_id)
    _doc_access(ctx, _me(db, ctx), emp)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="document.downloaded",
                         entity_type="employee_document", entity_id=doc.id, ip=ctx.ip)
    db.commit()
    safe = doc.filename.replace('"', "")
    return Response(storage.get_storage().get(doc.storage_key), media_type=doc.content_type,
                    headers={"Content-Disposition": f'attachment; filename="{safe}"', "X-Content-Type-Options": "nosniff"})


@router.delete("/documents/{doc_id}", status_code=204)
def delete_document(doc_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    doc = db.scalar(select(EmployeeDocument).where(EmployeeDocument.id == doc_id))
    if doc is None:
        raise NotFound("Document not found")
    emp = service.get_employee(db, doc.employee_id)
    _doc_access(ctx, _me(db, ctx), emp)
    storage.get_storage().delete(doc.storage_key)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="document.deleted",
                         entity_type="employee_document", entity_id=doc.id, ip=ctx.ip)
    db.delete(doc)
    db.commit()

