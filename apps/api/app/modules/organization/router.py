from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.session import get_db
from app.modules.employees.models import LIVE_STATUSES, Employee
from app.modules.identity.deps import AuthContext, check_origin, require
from app.modules.notifications.service import notify_employee
from app.modules.organization.models import Branch, Department, Designation, Holiday
from app.modules.tenancy import service as tenancy

router = APIRouter(tags=["organization"], dependencies=[Depends(check_origin)])
read = require("org.read")
manage = require("org.manage")


def _count(db: Session, column) -> dict:
    rows = db.execute(select(column, func.count()).where(Employee.deleted_at.is_(None),
                                                         Employee.status.in_(LIVE_STATUSES)).group_by(column))
    return dict(rows.all())


def _unique(db: Session, model, name: str, exclude: uuid.UUID | None = None, **extra) -> None:
    stmt = select(func.count()).select_from(model).where(func.lower(model.name) == name.lower())
    for k, v in extra.items():
        stmt = stmt.where(getattr(model, k) == v)
    if exclude:
        stmt = stmt.where(model.id != exclude)
    if db.scalar(stmt):
        raise Conflict(f"{model.__tablename__[:-1].capitalize()} '{name}' already exists", code="duplicate_name")


# ------------------------------------------------------------------ branches
class BranchIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=80)
    address: str | None = Field(default=None, max_length=300)
    phone: str | None = Field(default=None, max_length=40)
    is_active: bool = True


def _branch(b: Branch, counts: dict) -> dict:
    return {"id": b.id, "name": b.name, "code": b.code, "city": b.city, "address": b.address, "phone": b.phone,
            "is_active": b.is_active, "employee_count": counts.get(b.id, 0)}


@router.get("/branches")
def list_branches(ctx: AuthContext = Depends(read), db: Session = Depends(get_db)):
    counts = _count(db, Employee.branch_id)
    return [_branch(b, counts) for b in db.scalars(select(Branch).order_by(Branch.name))]


@router.post("/branches", status_code=201)
def create_branch(body: BranchIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    _unique(db, Branch, body.name)
    b = Branch(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(b)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="branch.created",
                         entity_type="branch", details={"name": b.name}, ip=ctx.ip)
    db.commit()
    return _branch(b, {})


@router.put("/branches/{branch_id}")
def update_branch(branch_id: uuid.UUID, body: BranchIn, ctx: AuthContext = Depends(manage),
                  db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if b is None:
        raise NotFound("Branch not found")
    _unique(db, Branch, body.name, exclude=b.id)
    for k, v in body.model_dump().items():
        setattr(b, k, v)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="branch.updated",
                         entity_type="branch", entity_id=b.id, ip=ctx.ip)
    db.commit()
    return _branch(b, _count(db, Employee.branch_id))


@router.delete("/branches/{branch_id}", status_code=204)
def delete_branch(branch_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    b = db.get(Branch, branch_id)
    if b is None:
        raise NotFound("Branch not found")
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.branch_id == b.id)):
        raise Conflict("This branch has employees. Move them first or mark the branch inactive.", code="in_use")
    db.delete(b)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="branch.deleted",
                         entity_type="branch", entity_id=b.id, ip=ctx.ip)
    db.commit()


# ------------------------------------------------------------------ departments & designations
class DepartmentIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    description: str | None = Field(default=None, max_length=1000)
    parent_id: uuid.UUID | None = None
    is_active: bool = True


class DesignationIn(BaseModel):
    name: str = Field(min_length=2, max_length=120)
    department_id: uuid.UUID | None = None
    grade: str | None = Field(default=None, max_length=20)


def _dept(d: Department, counts: dict, desig_counts: dict) -> dict:
    return {"id": d.id, "name": d.name, "description": d.description, "parent_id": d.parent_id,
            "is_active": d.is_active, "employee_count": counts.get(d.id, 0),
            "designation_count": desig_counts.get(d.id, 0)}


def _no_dept_cycle(db: Session, dept_id: uuid.UUID, parent_id: uuid.UUID | None) -> None:
    seen = set()
    cur = parent_id
    while cur is not None:
        if cur == dept_id or cur in seen:
            raise ValidationFailed("A department cannot sit under itself", code="department_cycle")
        seen.add(cur)
        parent = db.get(Department, cur)
        cur = parent.parent_id if parent else None


@router.get("/departments")
def list_departments(ctx: AuthContext = Depends(read), db: Session = Depends(get_db)):
    counts = _count(db, Employee.department_id)
    dc = dict(db.execute(select(Designation.department_id, func.count()).group_by(Designation.department_id)).all())
    return [_dept(d, counts, dc) for d in db.scalars(select(Department).order_by(Department.name))]


@router.post("/departments", status_code=201)
def create_department(body: DepartmentIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    _unique(db, Department, body.name)
    if body.parent_id and db.get(Department, body.parent_id) is None:
        raise ValidationFailed("Unknown parent department")
    d = Department(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(d)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="department.created",
                         entity_type="department", details={"name": d.name}, ip=ctx.ip)
    db.commit()
    return _dept(d, {}, {})


@router.put("/departments/{department_id}")
def update_department(department_id: uuid.UUID, body: DepartmentIn, ctx: AuthContext = Depends(manage),
                      db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None:
        raise NotFound("Department not found")
    _unique(db, Department, body.name, exclude=d.id)
    _no_dept_cycle(db, d.id, body.parent_id)
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="department.updated",
                         entity_type="department", entity_id=d.id, ip=ctx.ip)
    db.commit()
    return _dept(d, _count(db, Employee.department_id), {})


@router.delete("/departments/{department_id}", status_code=204)
def delete_department(department_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    d = db.get(Department, department_id)
    if d is None:
        raise NotFound("Department not found")
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.department_id == d.id)):
        raise Conflict("This department has employees. Move them first or mark it inactive.", code="in_use")
    if db.scalar(select(func.count()).select_from(Department).where(Department.parent_id == d.id)):
        raise Conflict("This department has sub-departments", code="in_use")
    for des in db.scalars(select(Designation).where(Designation.department_id == d.id)):
        if db.scalar(select(func.count()).select_from(Employee).where(Employee.designation_id == des.id)):
            raise Conflict("A designation in this department is still assigned to employees", code="in_use")
        db.delete(des)
    db.delete(d)
    tenancy.record_audit(db, tenant_id=ctx.tenant.id, actor=ctx.identity.id, action="department.deleted",
                         entity_type="department", entity_id=d.id, ip=ctx.ip)
    db.commit()


def _desig(d: Designation, counts: dict) -> dict:
    return {"id": d.id, "name": d.name, "department_id": d.department_id, "grade": d.grade,
            "employee_count": counts.get(d.id, 0)}


@router.get("/designations")
def list_designations(department_id: uuid.UUID | None = None, ctx: AuthContext = Depends(read),
                      db: Session = Depends(get_db)):
    stmt = select(Designation).order_by(Designation.name)
    if department_id:
        stmt = stmt.where(Designation.department_id == department_id)
    counts = _count(db, Employee.designation_id)
    return [_desig(d, counts) for d in db.scalars(stmt)]


@router.post("/designations", status_code=201)
def create_designation(body: DesignationIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    if body.department_id and db.get(Department, body.department_id) is None:
        raise ValidationFailed("Unknown department")
    _unique(db, Designation, body.name, department_id=body.department_id)
    d = Designation(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(d)
    db.commit()
    return _desig(d, {})


@router.put("/designations/{designation_id}")
def update_designation(designation_id: uuid.UUID, body: DesignationIn, ctx: AuthContext = Depends(manage),
                       db: Session = Depends(get_db)):
    d = db.get(Designation, designation_id)
    if d is None:
        raise NotFound("Designation not found")
    _unique(db, Designation, body.name, exclude=d.id, department_id=body.department_id)
    for k, v in body.model_dump().items():
        setattr(d, k, v)
    db.commit()
    return _desig(d, _count(db, Employee.designation_id))


@router.delete("/designations/{designation_id}", status_code=204)
def delete_designation(designation_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    d = db.get(Designation, designation_id)
    if d is None:
        raise NotFound("Designation not found")
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.designation_id == d.id)):
        raise Conflict("This designation is assigned to employees", code="in_use")
    db.delete(d)
    db.commit()


# ------------------------------------------------------------------ holidays
class HolidayIn(BaseModel):
    holiday_date: date
    name: str = Field(min_length=2, max_length=120)
    branch_id: uuid.UUID | None = None


@router.get("/holidays")
def list_holidays(year: int | None = None, ctx: AuthContext = Depends(read), db: Session = Depends(get_db)):
    stmt = select(Holiday).order_by(Holiday.holiday_date)
    if year:
        stmt = stmt.where(Holiday.holiday_date >= date(year, 1, 1), Holiday.holiday_date <= date(year, 12, 31))
    return [{"id": h.id, "holiday_date": h.holiday_date, "name": h.name, "branch_id": h.branch_id}
            for h in db.scalars(stmt)]


@router.post("/holidays", status_code=201)
def create_holiday(body: HolidayIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    if db.scalar(select(func.count()).select_from(Holiday).where(
            Holiday.holiday_date == body.holiday_date, Holiday.branch_id == body.branch_id)):
        raise Conflict("A holiday already exists on that date", code="duplicate_holiday")
    h = Holiday(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(h)
    db.flush()
    stmt = select(Employee).where(Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES),
                                  Employee.membership_id.is_not(None))
    if h.branch_id:
        stmt = stmt.where(Employee.branch_id == h.branch_id)
    for emp in db.scalars(stmt):
        notify_employee(db, emp, "holiday", f"Holiday added: {h.name}",
                        f"{h.holiday_date}", "/me/leave", dedupe_key=f"holiday:{h.id}")
    db.commit()
    return {"id": h.id, "holiday_date": h.holiday_date, "name": h.name, "branch_id": h.branch_id}


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(holiday_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    h = db.get(Holiday, holiday_id)
    if h is None:
        raise NotFound("Holiday not found")
    db.delete(h)
    db.commit()


# ------------------------------------------------------------------ org chart
@router.get("/org-chart")
def org_chart(ctx: AuthContext = Depends(read), db: Session = Depends(get_db)):
    """Flat reporting list; the client builds the tree. Visible to anyone with org.read (names and titles only)."""
    des = {d.id: d.name for d in db.scalars(select(Designation))}
    dep = {d.id: d.name for d in db.scalars(select(Department))}
    emps = db.scalars(select(Employee).where(Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES)))
    return [{"id": e.id, "name": e.full_name, "designation": des.get(e.designation_id),
             "department": dep.get(e.department_id), "manager_id": e.manager_id} for e in emps]
