from __future__ import annotations

import uuid
from datetime import date

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.errors import Conflict, NotFound, ValidationFailed
from app.db.session import get_db
from app.modules.assets.models import Asset, AssetAssignment
from app.modules.common import audit, emp_map, need_me
from app.modules.employees import service as emp_service
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications.service import notify_employee

router = APIRouter(tags=["assets"], dependencies=[Depends(check_origin)])
manage = require("assets.manage")
CONDITIONS = "^(new|good|fair|damaged)$"


class AssetIn(BaseModel):
    name: str = Field(min_length=2, max_length=160)
    category: str = Field(min_length=2, max_length=60)
    serial_number: str | None = Field(default=None, max_length=80)
    condition: str = Field(default="good", pattern=CONDITIONS)
    purchase_date: date | None = None
    notes: str | None = Field(default=None, max_length=2000)


class AssignIn(BaseModel):
    employee_id: uuid.UUID
    assigned_on: date
    note: str | None = Field(default=None, max_length=500)


class ReturnIn(BaseModel):
    returned_on: date
    condition: str = Field(pattern=CONDITIONS)
    note: str | None = Field(default=None, max_length=500)


class StatusIn(BaseModel):
    status: str = Field(pattern="^(available|maintenance|retired)$")


def open_assignment(db: Session, asset_id: uuid.UUID) -> AssetAssignment | None:
    return db.scalar(select(AssetAssignment).where(AssetAssignment.asset_id == asset_id,
                                                   AssetAssignment.returned_on.is_(None)))


def _asset(a: Asset, holder: dict) -> dict:
    h = holder.get(a.id)
    return {"id": a.id, "name": a.name, "category": a.category, "serial_number": a.serial_number,
            "condition": a.condition, "status": a.status, "purchase_date": a.purchase_date, "notes": a.notes,
            "assigned_to": h[0] if h else None, "assigned_to_id": h[1] if h else None,
            "assigned_on": h[2] if h else None}


def _holders(db: Session) -> dict:
    rows = db.scalars(select(AssetAssignment).where(AssetAssignment.returned_on.is_(None))).all()
    emps = emp_map(db, {r.employee_id for r in rows})
    return {r.asset_id: (emps[r.employee_id].full_name if r.employee_id in emps else None, r.employee_id, r.assigned_on)
            for r in rows}


def _check_serial(db: Session, serial: str | None, exclude: uuid.UUID | None = None) -> None:
    if not serial:
        return
    stmt = select(Asset.id).where(func.lower(Asset.serial_number) == serial.lower())
    if exclude:
        stmt = stmt.where(Asset.id != exclude)
    if db.scalar(stmt):
        raise Conflict("An asset with this serial number exists", code="duplicate_serial")


@router.get("/assets")
def list_assets(status: str | None = None, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    stmt = select(Asset).order_by(Asset.category, Asset.name)
    if status:
        stmt = stmt.where(Asset.status == status)
    holders = _holders(db)
    return [_asset(a, holders) for a in db.scalars(stmt)]


@router.post("/assets", status_code=201)
def create_asset(body: AssetIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    _check_serial(db, body.serial_number)
    a = Asset(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(a)
    db.flush()
    audit(db, ctx, "asset.created", "asset", a.id, {"name": a.name})
    db.commit()
    return _asset(a, {})


def _get(db: Session, asset_id: uuid.UUID) -> Asset:
    a = db.get(Asset, asset_id)
    if a is None:
        raise NotFound("Asset not found")
    return a


@router.put("/assets/{asset_id}")
def update_asset(asset_id: uuid.UUID, body: AssetIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    a = _get(db, asset_id)
    _check_serial(db, body.serial_number, exclude=a.id)
    for k, v in body.model_dump().items():
        setattr(a, k, v)
    db.commit()
    return _asset(a, _holders(db))


@router.post("/assets/{asset_id}/status")
def set_status(asset_id: uuid.UUID, body: StatusIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    a = _get(db, asset_id)
    if a.status == "assigned":
        raise Conflict("Return the asset before changing its status", code="asset_assigned")
    a.status = body.status
    audit(db, ctx, f"asset.{body.status}", "asset", a.id)
    db.commit()
    return _asset(a, {})


@router.post("/assets/{asset_id}/assign")
def assign(asset_id: uuid.UUID, body: AssignIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    a = _get(db, asset_id)
    if a.status != "available":
        raise Conflict(f"This asset is {a.status} and cannot be assigned", code="not_available")
    emp = emp_service.get_employee(db, body.employee_id)
    db.add(AssetAssignment(tenant_id=ctx.tenant.id, asset_id=a.id, employee_id=emp.id, assigned_on=body.assigned_on,
                           condition_out=a.condition, note=body.note, assigned_by=ctx.identity.id))
    a.status = "assigned"
    notify_employee(db, emp, "asset", f"{a.name} has been assigned to you", None, "/me/assets")
    audit(db, ctx, "asset.assigned", "asset", a.id, {"employee_id": str(emp.id)})
    db.commit()
    return _asset(a, _holders(db))


@router.post("/assets/{asset_id}/return")
def return_asset(asset_id: uuid.UUID, body: ReturnIn, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    a = _get(db, asset_id)
    row = open_assignment(db, a.id)
    if row is None:
        raise Conflict("This asset is not assigned to anyone", code="not_assigned")
    if body.returned_on < row.assigned_on:
        raise ValidationFailed("The return date is before the assignment date", code="bad_date")
    row.returned_on, row.condition_in = body.returned_on, body.condition
    if body.note:
        row.note = f"{row.note or ''}\nReturn: {body.note}".strip()
    a.status, a.condition = "available", body.condition
    notify_employee(db, emp_service.get_employee(db, row.employee_id), "asset",
                    f"{a.name} was marked as returned", None, "/me/assets")
    audit(db, ctx, "asset.returned", "asset", a.id, {"condition": body.condition})
    db.commit()
    return _asset(a, {})


@router.get("/assets/{asset_id}/history")
def history(asset_id: uuid.UUID, ctx: AuthContext = Depends(manage), db: Session = Depends(get_db)):
    a = _get(db, asset_id)
    rows = db.scalars(select(AssetAssignment).where(AssetAssignment.asset_id == a.id)
                      .order_by(AssetAssignment.assigned_on.desc())).all()
    emps = emp_map(db, {r.employee_id for r in rows})
    return [{"employee": emps[r.employee_id].full_name if r.employee_id in emps else None,
             "assigned_on": r.assigned_on, "returned_on": r.returned_on, "condition_out": r.condition_out,
             "condition_in": r.condition_in, "note": r.note} for r in rows]


@router.get("/me/assets")
def my_assets(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    rows = db.execute(select(AssetAssignment, Asset).join(Asset, Asset.id == AssetAssignment.asset_id).where(
        AssetAssignment.employee_id == me.id).order_by(AssetAssignment.assigned_on.desc())).all()
    return [{"id": a.id, "name": a.name, "category": a.category, "serial_number": a.serial_number,
             "assigned_on": r.assigned_on, "returned_on": r.returned_on, "condition": r.condition_in or r.condition_out}
            for r, a in rows]
