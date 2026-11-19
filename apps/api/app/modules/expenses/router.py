from __future__ import annotations

import uuid
from datetime import date
from decimal import Decimal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core import storage
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.session import get_db
from app.modules.common import audit, emp_map, in_team, me_of, need_any, need_me, serialize_financial_writes
from app.modules.employees import service as emp_service
from app.modules.expenses.models import ExpenseCategory, ExpenseClaim
from app.modules.identity.deps import AuthContext, check_origin, get_tenant_ctx, require
from app.modules.notifications.service import notify_employee, notify_permission_holders

router = APIRouter(prefix="/expenses", tags=["expenses"],
                   dependencies=[Depends(check_origin), Depends(serialize_financial_writes)])
DEFAULT_CATEGORIES = [("Travel", None, True), ("Meals", "5000", False), ("Fuel", None, True),
                      ("Office supplies", "20000", True), ("Other", None, False)]


class CategoryIn(BaseModel):
    name: str = Field(min_length=2, max_length=80)
    max_amount: Decimal | None = Field(default=None, gt=0)
    requires_receipt: bool = False
    is_active: bool = True


class DecisionIn(BaseModel):
    approve: bool
    note: str | None = Field(default=None, max_length=500)


class FinanceDecisionIn(DecisionIn):
    approved_amount: Decimal | None = Field(default=None, gt=0)
    reimburse_via: str = Field(default="payroll", pattern="^(payroll|direct)$")


def ensure_categories(db: Session, tenant_id: uuid.UUID) -> None:
    if db.scalar(select(func.count()).select_from(ExpenseCategory)):
        return
    for name, cap, receipt in DEFAULT_CATEGORIES:
        db.add(ExpenseCategory(tenant_id=tenant_id, name=name, max_amount=Decimal(cap) if cap else None,
                               requires_receipt=receipt))
    db.commit()


def _cat(c: ExpenseCategory) -> dict:
    return {"id": c.id, "name": c.name, "max_amount": c.max_amount, "requires_receipt": c.requires_receipt,
            "is_active": c.is_active}


def _claim(c: ExpenseClaim, emps: dict, cats: dict) -> dict:
    e = emps.get(c.employee_id)
    return {"id": c.id, "employee_id": c.employee_id, "employee": e.full_name if e else None,
            "category_id": c.category_id, "category": cats.get(c.category_id), "amount": c.amount,
            "approved_amount": c.approved_amount, "expense_date": c.expense_date, "description": c.description,
            "status": c.status, "reimburse_via": c.reimburse_via, "manager_note": c.manager_note,
            "finance_note": c.finance_note, "has_receipt": c.receipt_key is not None,
            "in_payroll": c.payroll_run_id is not None, "created_at": c.created_at}


@router.get("/categories")
def categories(ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    ensure_categories(db, ctx.tenant.id)
    return [_cat(c) for c in db.scalars(select(ExpenseCategory).order_by(ExpenseCategory.name))]


@router.post("/categories", status_code=201)
def create_category(body: CategoryIn, ctx: AuthContext = Depends(require("expenses.finance_approve")),
                    db: Session = Depends(get_db)):
    if db.scalar(select(ExpenseCategory.id).where(func.lower(ExpenseCategory.name) == body.name.lower())):
        raise Conflict("A category with this name exists", code="duplicate_name")
    c = ExpenseCategory(tenant_id=ctx.tenant.id, **body.model_dump())
    db.add(c)
    db.commit()
    return _cat(c)


@router.put("/categories/{category_id}")
def update_category(category_id: uuid.UUID, body: CategoryIn,
                    ctx: AuthContext = Depends(require("expenses.finance_approve")), db: Session = Depends(get_db)):
    c = db.get(ExpenseCategory, category_id)
    if c is None:
        raise NotFound("Category not found")
    for k, v in body.model_dump().items():
        setattr(c, k, v)
    db.commit()
    return _cat(c)


@router.post("", status_code=201)
def submit(category_id: uuid.UUID = Form(...), amount: Decimal = Form(..., gt=0, le=Decimal("100000000")),
           expense_date: date = Form(...), description: str = Form(..., min_length=3, max_length=1000),
           receipt: UploadFile | None = File(default=None), ctx: AuthContext = Depends(require("expenses.submit")),
           db: Session = Depends(get_db)):
    me = need_me(db, ctx)
    cat = db.get(ExpenseCategory, category_id)
    if cat is None or not cat.is_active:
        raise ValidationFailed("Unknown expense category", details=[{"field": "category_id"}])
    if expense_date > date.today():
        raise ValidationFailed("The expense date cannot be in the future", code="future_date")
    if cat.max_amount is not None and amount > cat.max_amount:
        raise ValidationFailed(f"{cat.name} claims are limited to {cat.max_amount} per claim", code="over_limit")
    if cat.requires_receipt and receipt is None:
        raise ValidationFailed(f"{cat.name} claims need a receipt", code="receipt_required")
    claim = ExpenseClaim(tenant_id=ctx.tenant.id, employee_id=me.id, category_id=cat.id, amount=amount,
                         expense_date=expense_date, description=description.strip(), status="submitted")
    if receipt is not None:
        data = receipt.file.read(storage.MAX_UPLOAD_BYTES + 1)
        ctype = receipt.content_type or "application/octet-stream"
        storage.validate_upload(data, receipt.filename or "receipt", ctype)
        claim.receipt_key = storage.get_storage().put(ctx.tenant.id, data)
        claim.receipt_name, claim.receipt_type, claim.receipt_size = (receipt.filename or "receipt")[:255], ctype, len(data)
    db.add(claim)
    db.flush()
    if me.manager_id:
        notify_employee(db, db.get(emp_service.Employee, me.manager_id), "expense",
                        f"Expense claim from {me.full_name}", f"{cat.name}: {amount}",
                        f"/inbox/expense/{claim.id}")
    else:
        notify_permission_holders(db, ctx.tenant.id, "expenses.finance_approve", "expense",
                                  f"Expense claim from {me.full_name}", f"{cat.name}: {amount}", f"/inbox/expense/{claim.id}",
                                  dedupe_key=f"expense-finance:{claim.id}", exclude_identity_id=ctx.identity.id)
    audit(db, ctx, "expense.submitted", "expense_claim", claim.id, {"amount": str(amount)})
    db.commit()
    return _claim(claim, {me.id: me}, {cat.id: cat.name})


@router.get("")
def list_claims(scope: str = Query("mine", pattern="^(mine|team|all)$"), status: str | None = None,
                ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    me = me_of(db, ctx)
    stmt = select(ExpenseClaim).order_by(ExpenseClaim.created_at.desc()).limit(300)
    if scope == "all":
        need_any(ctx, "expenses.finance_approve")
    elif scope == "team":
        need_any(ctx, "expenses.approve")
        stmt = stmt.where(ExpenseClaim.employee_id.in_((emp_service.team_ids(db, me.id) - {me.id}) if me else set()))
    else:
        if me is None:
            return []
        stmt = stmt.where(ExpenseClaim.employee_id == me.id)
    if status:
        stmt = stmt.where(ExpenseClaim.status == status)
    rows = db.scalars(stmt).all()
    cats = {c.id: c.name for c in db.scalars(select(ExpenseCategory))}
    return [_claim(c, emp_map(db, {r.employee_id for r in rows}), cats) for c in rows]


def _load(db: Session, claim_id: uuid.UUID) -> ExpenseClaim:
    c = db.get(ExpenseClaim, claim_id)
    if c is None:
        raise NotFound("Expense claim not found")
    return c


@router.post("/{claim_id}/manager-decision")
def manager_decision(claim_id: uuid.UUID, body: DecisionIn, ctx: AuthContext = Depends(require("expenses.approve")),
                     db: Session = Depends(get_db)):
    c, me = _load(db, claim_id), me_of(db, ctx)
    if me is not None and me.id == c.employee_id:
        raise Forbidden("You cannot approve your own claim", code="self_approval")
    if not in_team(db, me, c.employee_id):
        raise NotFound("Expense claim not found")
    if c.status != "submitted":
        raise Conflict("This claim is not waiting for manager approval", code="invalid_state")
    c.status = "manager_approved" if body.approve else "rejected"
    c.manager_note, c.manager_decided_by = body.note, ctx.identity.id
    owner = db.get(emp_service.Employee, c.employee_id)
    notify_employee(db, owner, "expense", f"Your expense claim was {'approved by your manager' if body.approve else 'rejected'}",
                    body.note, "/me/expenses")
    if body.approve:
        notify_permission_holders(db, ctx.tenant.id, "expenses.finance_approve", "expense",
                                  f"Expense claim awaiting finance: {owner.full_name}", f"Amount: {c.amount}",
                                  f"/inbox/expense/{c.id}", dedupe_key=f"expense-finance:{c.id}",
                                  exclude_identity_id=ctx.identity.id)
    audit(db, ctx, f"expense.manager_{'approved' if body.approve else 'rejected'}", "expense_claim", c.id)
    db.commit()
    return {"id": c.id, "status": c.status}


@router.post("/{claim_id}/finance-decision")
def finance_decision(claim_id: uuid.UUID, body: FinanceDecisionIn,
                     ctx: AuthContext = Depends(require("expenses.finance_approve")), db: Session = Depends(get_db)):
    c, me = _load(db, claim_id), me_of(db, ctx)
    if me is not None and me.id == c.employee_id:
        raise Forbidden("You cannot approve your own claim", code="self_approval")
    owner = emp_service.get_employee(db, c.employee_id)
    waiting = "manager_approved" if owner.manager_id else "submitted"  # no manager on file: finance decides directly
    if c.status not in (waiting, "manager_approved"):
        raise Conflict("This claim is waiting for the manager's approval first" if c.status == "submitted"
                       else "This claim has already been decided", code="invalid_state")
    if body.approve:
        approved = body.approved_amount or c.amount
        if approved > c.amount:
            raise ValidationFailed("The approved amount cannot exceed the claimed amount", code="over_claim")
        c.status, c.approved_amount, c.reimburse_via = "approved", approved, body.reimburse_via
    else:
        c.status = "rejected"
    c.finance_note, c.finance_decided_by = body.note, ctx.identity.id
    notify_employee(db, owner, "expense", f"Your expense claim was {'approved' if body.approve else 'rejected'}",
                    body.note, "/me/expenses")
    audit(db, ctx, f"expense.finance_{'approved' if body.approve else 'rejected'}", "expense_claim", c.id,
          {"approved_amount": str(c.approved_amount) if c.approved_amount else None, "via": c.reimburse_via})
    db.commit()
    return {"id": c.id, "status": c.status, "approved_amount": c.approved_amount}


@router.post("/{claim_id}/reimburse")
def reimburse(claim_id: uuid.UUID, ctx: AuthContext = Depends(require("expenses.finance_approve")),
              db: Session = Depends(get_db)):
    """Marks a directly paid claim as reimbursed. Claims paid through payroll are settled when the run is finalized."""
    c = _load(db, claim_id)
    if c.status == "reimbursed":
        raise Conflict("This claim has already been reimbursed", code="already_reimbursed")
    if c.status != "approved":
        raise Conflict("Only approved claims can be reimbursed", code="invalid_state")
    if c.reimburse_via == "payroll":
        raise Conflict("This claim is paid through payroll and is settled when the run is finalized",
                       code="paid_via_payroll")
    c.status, c.reimbursed_at = "reimbursed", utcnow()
    notify_employee(db, emp_service.get_employee(db, c.employee_id), "expense",
                    "Your expense claim was reimbursed", f"Amount: {c.approved_amount}", "/me/expenses")
    audit(db, ctx, "expense.reimbursed", "expense_claim", c.id, {"amount": str(c.approved_amount)})
    db.commit()
    return {"id": c.id, "status": c.status}


@router.post("/{claim_id}/cancel")
def cancel(claim_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    c, me = _load(db, claim_id), me_of(db, ctx)
    if me is None or me.id != c.employee_id:
        raise NotFound("Expense claim not found")
    if c.status not in ("submitted", "manager_approved"):
        raise Conflict("This claim can no longer be cancelled", code="invalid_state")
    c.status = "cancelled"
    db.commit()
    return {"id": c.id, "status": c.status}


@router.get("/{claim_id}/receipt")
def receipt(claim_id: uuid.UUID, ctx: AuthContext = Depends(get_tenant_ctx), db: Session = Depends(get_db)):
    c, me = _load(db, claim_id), me_of(db, ctx)
    own = me is not None and me.id == c.employee_id
    if not (own or "expenses.finance_approve" in ctx.permissions
            or ("expenses.approve" in ctx.permissions and in_team(db, me, c.employee_id))):
        raise NotFound("Expense claim not found")
    if not c.receipt_key:
        raise NotFound("No receipt attached")
    name = (c.receipt_name or "receipt").replace('"', "")
    return Response(storage.get_storage().get(c.receipt_key), media_type=c.receipt_type or "application/octet-stream",
                    headers={"Content-Disposition": f'attachment; filename="{name}"', "X-Content-Type-Options": "nosniff"})
