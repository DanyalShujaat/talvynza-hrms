"""Employee business logic: creation, assignments, lifecycle, visibility, bulk import."""
from __future__ import annotations

import csv
import io
import re
import uuid
from datetime import date, datetime

from email_validator import EmailNotValidError, validate_email
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from app.core import events
from app.core.errors import Conflict, Forbidden, NotFound, ValidationFailed
from app.db.base import utcnow
from app.db.tenant_scope import tenant_scope
from app.modules.employees.models import (
    LIVE_STATUSES,
    STATUSES,
    ChecklistItem,
    Employee,
    EmployeeAssignment,
    EmployeeLifecycleEvent,
)
from app.modules.leave.models import LeaveType
from app.modules.organization.models import Branch, Department, Designation
from app.modules.payroll.models import SalaryTemplate
from app.modules.tenancy import service as tenancy
from app.modules.tenancy.models import AuditLog, Tenant

DEFAULT_CHECKLIST = [
    "Collect identification documents", "Sign employment contract", "Create work email account",
    "Assign equipment", "Orientation session", "Add to payroll",
]
LIFECYCLE_TYPES = {
    "confirmation", "promotion", "transfer", "suspension", "reinstatement", "resignation", "termination",
    "retirement", "rehire", "contract_renewal", "probation_extension", "deactivation",
}


# ------------------------------------------------------------------ helpers
def current_employee(db: Session, membership_id: uuid.UUID | None) -> Employee | None:
    if membership_id is None:
        return None
    return db.scalar(select(Employee).where(Employee.membership_id == membership_id, Employee.deleted_at.is_(None)))


def get_employee(db: Session, employee_id: uuid.UUID) -> Employee:
    emp = db.scalar(select(Employee).where(Employee.id == employee_id, Employee.deleted_at.is_(None)))
    if emp is None:
        raise NotFound("Employee not found")
    return emp


def team_ids(db: Session, manager_id: uuid.UUID) -> set[uuid.UUID]:
    """The manager plus every direct and indirect report (breadth-first, cycle safe)."""
    seen = {manager_id}
    frontier = {manager_id}
    while frontier:
        rows = db.scalars(select(Employee.id).where(Employee.manager_id.in_(frontier), Employee.deleted_at.is_(None)))
        frontier = {r for r in rows if r not in seen}
        seen |= frontier
    return seen


def visible_ids(db: Session, perms: set[str], me: Employee | None) -> set[uuid.UUID] | None:
    """None means every employee in the tenant. Otherwise the set of employee ids the caller may see."""
    if "employees.read" in perms:
        return None
    if "employees.read_team" in perms and me is not None:
        return team_ids(db, me.id)
    if me is not None:
        return {me.id}
    return set()


def assert_can_view(db: Session, perms: set[str], me: Employee | None, employee_id: uuid.UUID) -> None:
    allowed = visible_ids(db, perms, me)
    if allowed is not None and employee_id not in allowed:
        raise NotFound("Employee not found")  # same answer as a missing record
    get_employee(db, employee_id)  # an id from another tenant (or a deleted record) is a 404 even for HR


def next_code(db: Session) -> str:
    codes = db.scalars(select(Employee.employee_code))
    nums = [int(c) for c in codes if c.isdigit()]
    return str(max(nums, default=1000) + 1)


def _check_refs(db: Session, branch_id, department_id, designation_id, manager_id, self_id=None) -> None:
    for model, value, label in ((Branch, branch_id, "branch"), (Department, department_id, "department"),
                                (Designation, designation_id, "designation")):
        if value is not None and db.get(model, value) is None:
            raise ValidationFailed(f"Unknown {label}", details=[{"field": f"{label}_id"}])
    if manager_id is not None:
        if db.get(Employee, manager_id) is None:
            raise ValidationFailed("Unknown manager", details=[{"field": "manager_id"}])
        # team_ids includes the employee and everyone below them, so any hit would create a loop
        if self_id is not None and manager_id in team_ids(db, self_id):
            raise ValidationFailed("That manager already reports to this employee, directly or indirectly",
                                   code="manager_cycle")


def _check_designation_department(db: Session, designation_id, department_id) -> None:
    designation = db.get(Designation, designation_id) if designation_id else None
    if designation and designation.department_id and designation.department_id != department_id:
        raise ValidationFailed("Select a designation in the employee's department", details=[{"field": "designation_id"}])


def _live_count(db: Session) -> int:
    return db.scalar(select(func.count()).select_from(Employee).where(
        Employee.deleted_at.is_(None), Employee.status.in_(LIVE_STATUSES))) or 0


def _check_capacity(db: Session, tenant: Tenant, adding: int = 1) -> None:
    if _live_count(db) + adding > tenant.employee_capacity:
        raise Conflict(f"Employee limit of {tenant.employee_capacity} reached for this plan",
                       code="employee_limit_reached")


def _open_assignment(db: Session, emp: Employee, effective_from: date) -> None:
    db.add(EmployeeAssignment(
        tenant_id=emp.tenant_id, employee_id=emp.id, branch_id=emp.branch_id, department_id=emp.department_id,
        designation_id=emp.designation_id, manager_id=emp.manager_id, effective_from=effective_from))


def _close_assignment(db: Session, emp: Employee, on: date) -> None:
    for a in db.scalars(select(EmployeeAssignment).where(
            EmployeeAssignment.employee_id == emp.id, EmployeeAssignment.effective_to.is_(None))):
        a.effective_to = on


def _event(db: Session, emp: Employee, kind: str, on: date, actor: uuid.UUID | None, details: dict | None = None) -> None:
    db.add(EmployeeLifecycleEvent(tenant_id=emp.tenant_id, employee_id=emp.id, event_type=kind, effective_date=on,
                                  details=details or {}, created_by=actor, created_at=utcnow()))


# ------------------------------------------------------------------ create / update
SETUP_REQUIREMENTS = {
    "branch": ("an active branch", select(Branch.id).where(Branch.is_active.is_(True))),
    "department": ("an active department", select(Department.id).where(Department.is_active.is_(True))),
    # Reading the policy can create defaults. A saved policy is recorded explicitly in the audit log.
    "attendance_policy": (
        "a saved attendance policy", select(AuditLog.id).where(AuditLog.action == "attendance.policy_updated"),
    ),
    "leave_type": ("an active leave type", select(LeaveType.id).where(LeaveType.is_active.is_(True))),
    "payroll": ("an active salary template", select(SalaryTemplate.id).where(SalaryTemplate.is_active.is_(True))),
}


def missing_setup(db: Session) -> list[str]:
    return [key for key, (_, query) in SETUP_REQUIREMENTS.items() if db.scalar(query.limit(1)) is None]


def require_setup(db: Session) -> None:
    missing = missing_setup(db)
    if missing:
        labels = ", ".join(SETUP_REQUIREMENTS[key][0] for key in missing)
        raise Conflict(f"Employee setup requires {labels}.", code="employee_setup_required", details=missing)


def create_employee(db: Session, *, tenant: Tenant, actor: uuid.UUID, data: dict, ip: str | None = None) -> Employee:
    require_setup(db)
    _check_capacity(db, tenant)
    code = (data.get("employee_code") or "").strip() or next_code(db)
    if db.scalar(select(func.count()).select_from(Employee).where(Employee.employee_code == code)):
        raise Conflict("Employee ID already exists", code="duplicate_employee_code")
    email = (data.get("email") or "").strip().lower() or None
    if email and db.scalar(select(func.count()).select_from(Employee).where(
            Employee.email == email, Employee.deleted_at.is_(None))):
        raise Conflict("An employee with this email already exists", code="duplicate_email")
    for model, field in ((Branch, "branch"), (Department, "department")):
        field_id = f"{field}_id"
        placement = db.get(model, data[field_id]) if data.get(field_id) else None
        if placement is None or not placement.is_active:
            raise ValidationFailed(f"Select an active {field}", details=[{"field": field_id}])
    _check_refs(db, None, None, data.get("designation_id"), data.get("manager_id"))
    _check_designation_department(db, data.get("designation_id"), data.get("department_id"))
    fields = {k: v for k, v in data.items() if k not in {"employee_code", "email"}}
    fields.setdefault("status", "active")
    fields.setdefault("employment_type", "full_time")
    emp = Employee(tenant_id=tenant.id, employee_code=code, email=email, **fields)
    if emp.status not in STATUSES:
        raise ValidationFailed("Unknown status", details=[{"field": "status"}])
    if emp.probation_end and emp.status == "active":
        emp.status = "probation"
    db.add(emp)
    db.flush()
    _open_assignment(db, emp, emp.joining_date)
    _event(db, emp, "joined", emp.joining_date, actor, {"status": emp.status})
    for title in DEFAULT_CHECKLIST:
        db.add(ChecklistItem(tenant_id=tenant.id, employee_id=emp.id, title=title))
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="employee.created", entity_type="employee",
                         entity_id=emp.id, details={"code": code}, ip=ip)
    db.commit()
    return emp


def update_employee(db: Session, *, tenant: Tenant, actor: uuid.UUID, emp: Employee, changes: dict,
                    ip: str | None = None) -> Employee:
    if "email" in changes and changes["email"]:
        changes["email"] = changes["email"].strip().lower()
        if db.scalar(select(func.count()).select_from(Employee).where(
                Employee.email == changes["email"], Employee.id != emp.id, Employee.deleted_at.is_(None))):
            raise Conflict("An employee with this email already exists", code="duplicate_email")
    org_keys = ("branch_id", "department_id", "designation_id", "manager_id")
    if any(k in changes for k in org_keys):
        _check_refs(db, changes.get("branch_id", emp.branch_id), changes.get("department_id", emp.department_id),
                    changes.get("designation_id", emp.designation_id), changes.get("manager_id", emp.manager_id),
                    self_id=emp.id)
    if "designation_id" in changes and changes["designation_id"] != emp.designation_id:
        _check_designation_department(db, changes.get("designation_id", emp.designation_id),
                                      changes.get("department_id", emp.department_id))
    if "status" in changes and changes["status"] not in STATUSES:
        raise ValidationFailed("Unknown status", details=[{"field": "status"}])
    placement_changed = any(k in changes and changes[k] != getattr(emp, k) for k in org_keys)
    manager_changed = "manager_id" in changes and changes["manager_id"] != emp.manager_id
    for k, v in changes.items():
        setattr(emp, k, v)
    if placement_changed:
        today = date.today()
        _close_assignment(db, emp, today)
        db.flush()
        _open_assignment(db, emp, today)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="employee.updated", entity_type="employee",
                         entity_id=emp.id, details={"fields": sorted(changes)}, ip=ip)
    if placement_changed:
        from app.modules.notifications.service import notify_employee
        notify_employee(db, emp, "people", "Your organization placement was updated",
                        "Review your department, branch, and reporting manager.", "/me/profile")
        if manager_changed and emp.manager_id:
            notify_employee(db, db.get(Employee, emp.manager_id), "people",
                            f"{emp.full_name} now reports to you", None, f"/employees/{emp.id}")
    db.commit()
    return emp


def record_lifecycle(db: Session, *, tenant: Tenant, actor: uuid.UUID, emp: Employee, event_type: str,
                     effective_date: date, details: dict, ip: str | None = None, commit: bool = True) -> Employee:
    if event_type not in LIFECYCLE_TYPES:
        raise ValidationFailed("Unknown lifecycle event", details=[{"field": "event_type"}])
    d = details or {}
    if event_type == "confirmation":
        if emp.status != "probation":
            raise Conflict("Only employees on probation can be confirmed", code="invalid_transition")
        emp.status, emp.confirmation_date = "active", effective_date
    elif event_type == "probation_extension":
        new_end = d.get("probation_end")
        if not new_end:
            raise ValidationFailed("probation_end is required", details=[{"field": "details.probation_end"}])
        emp.probation_end, emp.status = date.fromisoformat(new_end), "probation"
    elif event_type == "promotion":
        if not d.get("designation_id"):
            raise ValidationFailed("designation_id is required", details=[{"field": "details.designation_id"}])
        designation_id = uuid.UUID(d["designation_id"])
        _check_refs(db, None, None, designation_id, None)
        _check_designation_department(db, designation_id, emp.department_id)
        _close_assignment(db, emp, effective_date)
        emp.designation_id = designation_id
        db.flush()
        _open_assignment(db, emp, effective_date)
    elif event_type == "transfer":
        ids = {k: (uuid.UUID(d[k]) if d.get(k) else getattr(emp, k)) for k in
               ("branch_id", "department_id", "manager_id")}
        _check_refs(db, ids["branch_id"], ids["department_id"], None, ids["manager_id"], self_id=emp.id)
        if d.get("designation_id"):
            designation_id = uuid.UUID(d["designation_id"])
            _check_refs(db, None, None, designation_id, None)
            _check_designation_department(db, designation_id, ids["department_id"])
            ids["designation_id"] = designation_id
        _close_assignment(db, emp, effective_date)
        for k, v in ids.items():
            setattr(emp, k, v)
        db.flush()
        _open_assignment(db, emp, effective_date)
    elif event_type == "suspension":
        if emp.status not in LIVE_STATUSES or emp.status == "suspended":
            raise Conflict("Employee cannot be suspended in their current status", code="invalid_transition")
        d["previous_status"] = emp.status
        emp.status = "suspended"
    elif event_type == "reinstatement":
        if emp.status != "suspended":
            raise Conflict("Employee is not suspended", code="invalid_transition")
        last = db.scalar(select(EmployeeLifecycleEvent).where(
            EmployeeLifecycleEvent.employee_id == emp.id, EmployeeLifecycleEvent.event_type == "suspension"
        ).order_by(EmployeeLifecycleEvent.created_at.desc()))
        emp.status = (last.details.get("previous_status") if last else None) or "active"
    elif event_type in ("resignation", "termination", "retirement", "deactivation"):
        if emp.status not in LIVE_STATUSES:
            raise Conflict("Employee has already left", code="invalid_transition")
        emp.status = {"resignation": "resigned", "termination": "terminated", "retirement": "retired",
                      "deactivation": "inactive"}[event_type]
        emp.exit_date = effective_date
        _close_assignment(db, emp, effective_date)
    elif event_type == "rehire":
        if emp.status in LIVE_STATUSES:
            raise Conflict("Employee is already active", code="invalid_transition")
        _check_capacity(db, tenant)
        emp.status, emp.exit_date = "active", None
        _open_assignment(db, emp, effective_date)
    elif event_type == "contract_renewal":
        if not d.get("contract_end"):
            raise ValidationFailed("contract_end is required", details=[{"field": "details.contract_end"}])
        emp.contract_end = date.fromisoformat(d["contract_end"])
    _event(db, emp, event_type, effective_date, actor, d)
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action=f"employee.{event_type}", entity_type="employee",
                         entity_id=emp.id, details={"effective_date": effective_date.isoformat()}, ip=ip)
    if commit:
        db.commit()
        events.publish(f"employee.{event_type}", {"tenant_id": tenant.id, "employee_id": emp.id})
    else:
        db.flush()
    return emp


# ------------------------------------------------------------------ listing
def list_employees(db: Session, *, allowed: set[uuid.UUID] | None, branch_id=None, department_id=None, status=None,
                   q: str | None = None, letter: str | None = None, page: int = 1, page_size: int = 25):
    stmt = select(Employee).where(Employee.deleted_at.is_(None))
    if allowed is not None:
        stmt = stmt.where(Employee.id.in_(allowed))
    if branch_id:
        stmt = stmt.where(Employee.branch_id == branch_id)
    if department_id:
        stmt = stmt.where(Employee.department_id == department_id)
    if status == "active":
        stmt = stmt.where(Employee.status.in_(LIVE_STATUSES))
    elif status == "former":
        stmt = stmt.where(Employee.status.in_(("resigned", "terminated", "retired", "inactive")))
    elif status in STATUSES:
        stmt = stmt.where(Employee.status == status)
    if q:
        like = f"%{q.strip().lower()}%"
        full_name = Employee.first_name + " " + Employee.last_name
        stmt = stmt.where(or_(func.lower(full_name).like(like),
                              func.lower(Employee.email).like(like), Employee.employee_code.like(like),
                              Employee.bio_id.like(like), Employee.phone.like(like)))
    if letter and re.fullmatch(r"[A-Za-z]", letter):
        stmt = stmt.where(func.lower(Employee.first_name).like(letter.lower() + "%"))
    total = db.scalar(select(func.count()).select_from(stmt.subquery())) or 0
    rows = db.scalars(stmt.order_by(Employee.first_name, Employee.last_name).limit(page_size)
                      .offset((page - 1) * page_size)).all()
    return rows, total


def name_maps(db: Session) -> dict[str, dict[uuid.UUID, str]]:
    return {
        "branch": {b.id: b.name for b in db.scalars(select(Branch))},
        "department": {d.id: d.name for d in db.scalars(select(Department))},
        "designation": {d.id: d.name for d in db.scalars(select(Designation))},
    }


# ------------------------------------------------------------------ bulk import
IMPORT_COLUMNS = ["employee_code", "first_name", "last_name", "email", "phone", "gender", "date_of_birth",
                  "joining_date", "branch", "department", "designation", "manager_code", "employment_type",
                  "bio_id"]
ALIASES = {
    "employee_id": "employee_code", "code": "employee_code", "emp_code": "employee_code", "firstname": "first_name",
    "first": "first_name", "lastname": "last_name", "last": "last_name", "surname": "last_name",
    "mobile": "phone", "mobile#": "phone", "phone_number": "phone", "dob": "date_of_birth",
    "birth_date": "date_of_birth", "join_date": "joining_date", "date_of_joining": "joining_date",
    "joined": "joining_date", "manager": "manager_code", "reporting_manager": "manager_code",
    "type": "employment_type", "biometric_id": "bio_id", "e-mail": "email", "email_address": "email",
}
MAX_IMPORT_ROWS = 5000
MAX_IMPORT_BYTES = 5 * 1024 * 1024
_DATE_FORMATS = ("%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y", "%m/%d/%Y")


def _norm_header(h: str) -> str:
    key = re.sub(r"[\s\-]+", "_", str(h or "").strip().lower())
    return ALIASES.get(key, key)


def template_csv() -> str:
    sample = ["", "Sara", "Khan", "sara.khan@example.com", "+923001234567", "female", "1994-05-21", "2026-01-15",
              "Head Office", "Engineering", "Software Engineer", "", "full_time", ""]
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(IMPORT_COLUMNS)
    w.writerow(sample)
    return out.getvalue()


def parse_sheet(filename: str, data: bytes, mapping: dict[str, str] | None = None) -> list[dict]:
    if len(data) > MAX_IMPORT_BYTES:
        raise ValidationFailed("File is larger than 5 MB", code="file_too_large")
    rows: list[list] = []
    name = filename.lower()
    if name.endswith(".xlsx"):
        import openpyxl

        try:
            wb = openpyxl.load_workbook(io.BytesIO(data), read_only=True, data_only=True)
        except Exception:
            raise ValidationFailed("The Excel file could not be read", code="bad_file") from None
        rows = [list(r) for r in wb.active.iter_rows(values_only=True)]
    elif name.endswith(".csv"):
        try:
            text = data.decode("utf-8-sig")
        except UnicodeDecodeError:
            raise ValidationFailed("CSV must be UTF-8 encoded", code="bad_file") from None
        rows = list(csv.reader(io.StringIO(text)))
    else:
        raise ValidationFailed("Upload a .csv or .xlsx file", code="bad_file")
    rows = [r for r in rows if any(str(c).strip() for c in r if c is not None)]
    if len(rows) < 2:
        raise ValidationFailed("The file has no data rows", code="empty_file")
    if len(rows) - 1 > MAX_IMPORT_ROWS:
        raise ValidationFailed(f"At most {MAX_IMPORT_ROWS} rows per import", code="too_many_rows")
    mapping = {str(k).strip().lower(): v for k, v in (mapping or {}).items()}
    headers = [mapping.get(str(h or "").strip().lower()) or _norm_header(h) for h in rows[0]]
    out = []
    for i, r in enumerate(rows[1:], start=2):
        rec = {headers[j]: (str(c).strip() if c is not None and not isinstance(c, (datetime, date)) else c)
               for j, c in enumerate(r) if j < len(headers) and headers[j]}
        rec["_row"] = i
        out.append(rec)
    return out


def _parse_date(v) -> date | None:
    if v in (None, ""):
        return None
    if isinstance(v, datetime):
        return v.date()
    if isinstance(v, date):
        return v
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(str(v).strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError("invalid date")


def validate_import(db: Session, tenant: Tenant, records: list[dict]) -> dict:
    require_setup(db)
    branches = {b.name.lower(): b.id for b in db.scalars(select(Branch).where(Branch.is_active.is_(True)))}
    depts = {d.name.lower(): d.id for d in db.scalars(select(Department).where(Department.is_active.is_(True)))}
    desigs: dict[str, list[uuid.UUID]] = {}
    for d in db.scalars(select(Designation)):
        desigs.setdefault(d.name.lower(), []).append(d.id)
    existing_codes = set(db.scalars(select(Employee.employee_code)))
    existing_emails = {e for e in db.scalars(select(Employee.email).where(Employee.deleted_at.is_(None))) if e}
    code_to_id = {e.employee_code: e.id for e in db.scalars(select(Employee).where(Employee.deleted_at.is_(None)))}
    seen_codes: set[str] = set()
    seen_emails: set[str] = set()
    explicit_codes = {(r.get("employee_code") or "").strip() for r in records} - {""}
    next_n = int(next_code(db))
    room = tenant.employee_capacity - _live_count(db)
    results = []
    for rec in records:
        errors: list[str] = []
        row: dict = {}
        for field in ("first_name", "last_name"):
            if not rec.get(field):
                errors.append(f"{field} is required")
        row["first_name"], row["last_name"] = rec.get("first_name", ""), rec.get("last_name", "")
        try:
            jd = _parse_date(rec.get("joining_date"))
            if jd is None:
                errors.append("joining_date is required")
            row["joining_date"] = jd
        except ValueError:
            errors.append("joining_date is not a valid date")
        try:
            row["date_of_birth"] = _parse_date(rec.get("date_of_birth"))
        except ValueError:
            errors.append("date_of_birth is not a valid date")
        email = (rec.get("email") or "").strip().lower() or None
        if email:
            try:
                validate_email(email, check_deliverability=False)
            except EmailNotValidError:
                errors.append("email is not valid")
            if email in existing_emails:
                errors.append("email already exists in this organization")
            if email in seen_emails:
                errors.append("email is duplicated in the file")
            seen_emails.add(email)
        row["email"] = email
        code = (rec.get("employee_code") or "").strip()
        if code:
            if code in existing_codes:
                errors.append("employee_code already exists")
            if code in seen_codes:
                errors.append("employee_code is duplicated in the file")
        else:
            while str(next_n) in existing_codes or str(next_n) in seen_codes:
                next_n += 1
            code = str(next_n)
            next_n += 1
        seen_codes.add(code)
        row["employee_code"] = code
        for key, lookup, label in (("branch", branches, "branch"), ("department", depts, "department")):
            name = (rec.get(key) or "").strip()
            if name:
                if name.lower() in lookup:
                    row[f"{key}_id"] = lookup[name.lower()]
                else:
                    errors.append(f"unknown {label} '{name}'")
            else:
                errors.append(f"{label} is required")
        dname = (rec.get("designation") or "").strip().lower()
        if dname:
            ids = desigs.get(dname, [])
            if len(ids) == 1:
                row["designation_id"] = ids[0]
            elif not ids:
                errors.append(f"unknown designation '{rec.get('designation')}'")
            else:
                errors.append(f"designation '{rec.get('designation')}' is ambiguous across departments")
        mcode = (rec.get("manager_code") or "").strip()
        if mcode:
            if mcode in code_to_id:
                row["manager_id"] = code_to_id[mcode]
            elif mcode in explicit_codes and mcode != code:
                row["manager_code"] = mcode  # defined elsewhere in this file; resolved when committing
            elif mcode == code:
                errors.append("an employee cannot report to themselves")
            else:
                errors.append(f"unknown manager_code '{mcode}'")
        row["phone"] = rec.get("phone") or None
        row["gender"] = (rec.get("gender") or "").lower() or None
        row["bio_id"] = rec.get("bio_id") or None
        row["employment_type"] = (rec.get("employment_type") or "full_time").lower().replace(" ", "_")
        results.append({"row": rec["_row"], "errors": errors, "data": row})
    # a reporting loop inside the file (A reports to B, B to A) would corrupt the hierarchy
    deferred = {r["data"]["employee_code"]: r["data"]["manager_code"] for r in results if "manager_code" in r["data"]}
    for r in results:
        cur, hops = r["data"].get("manager_code"), 0
        while cur and hops <= len(deferred):
            if cur == r["data"]["employee_code"]:
                r["errors"].append("reporting loop: this employee is their own indirect manager")
                break
            cur, hops = deferred.get(cur), hops + 1
    valid = [r for r in results if not r["errors"]]
    if len(valid) > room:
        for r in valid[room:]:
            r["errors"].append(f"employee limit of {tenant.employee_capacity} would be exceeded")
        valid = valid[:room]
    return {"rows": results, "summary": {"total": len(results), "valid": len(valid),
                                         "invalid": len(results) - len(valid)}}


def commit_import(db: Session, *, tenant: Tenant, actor: uuid.UUID, validated: dict, skip_invalid: bool,
                  ip: str | None = None) -> int:
    summary = validated["summary"]
    if summary["invalid"] and not skip_invalid:
        raise ValidationFailed("Fix the listed errors or choose to skip invalid rows", code="import_has_errors",
                               details=summary)
    created: dict[str, Employee] = {}
    deferred: dict[str, str] = {}
    for r in validated["rows"]:
        if r["errors"]:
            continue
        d = {k: v for k, v in r["data"].items() if v is not None and k not in ("employee_code", "manager_code")}
        emp = Employee(tenant_id=tenant.id, employee_code=r["data"]["employee_code"], **d)
        emp.status = "active"
        db.add(emp)
        db.flush()
        created[emp.employee_code] = emp
        if r["data"].get("manager_code"):
            deferred[emp.employee_code] = r["data"]["manager_code"]
    for code, mcode in deferred.items():
        if mcode in created:
            created[code].manager_id = created[mcode].id
    for emp in created.values():
        _open_assignment(db, emp, emp.joining_date)
        _event(db, emp, "joined", emp.joining_date, actor, {"source": "bulk_import"})
        for title in DEFAULT_CHECKLIST:
            db.add(ChecklistItem(tenant_id=tenant.id, employee_id=emp.id, title=title))
    tenancy.record_audit(db, tenant_id=tenant.id, actor=actor, action="employee.bulk_imported",
                         entity_type="employee", details={"created": len(created), "skipped": summary["invalid"]}, ip=ip)
    db.commit()  # one transaction: either every valid row lands or none do
    return len(created)


# ------------------------------------------------------------------ event wiring
def _on_tenant_created(payload: dict) -> None:
    """The owner gets an employee record so self-service (attendance, leave, payslips) works from day one."""
    db: Session = payload["db"]
    tenant_id, identity = payload["tenant_id"], payload["owner"]
    membership = tenancy.get_active_membership(db, identity.id, tenant_id)
    if membership is None:
        return
    with tenant_scope(db, tenant_id):
        first, _, last = identity.full_name.partition(" ")
        emp = Employee(tenant_id=tenant_id, employee_code=next_code(db), membership_id=membership.id,
                       first_name=first, last_name=last or "-", email=identity.email, status="active",
                       joining_date=date.today())
        db.add(emp)
        db.flush()
        _open_assignment(db, emp, emp.joining_date)
        _event(db, emp, "joined", emp.joining_date, identity.id, {"source": "organization_owner"})
    db.commit()


def _on_member_joined(payload: dict) -> None:
    """Link an accepted invitation to an existing employee record with the same email."""
    db: Session = payload["db"]
    with tenant_scope(db, payload["tenant_id"]):
        emp = db.scalar(select(Employee).where(Employee.email == payload["email"], Employee.membership_id.is_(None),
                                               Employee.deleted_at.is_(None)))
        if emp is not None:
            emp.membership_id = payload["membership_id"]
    db.commit()


def backfill_owner_employees(db: Session) -> None:
    """Organizations created before the employees module existed get an employee record for each owner."""
    from app.modules.identity.models import Identity
    from app.modules.tenancy.models import MembershipRole, Role, TenantMembership

    for tenant_id in list(db.scalars(select(Tenant.id))):
        with tenant_scope(db, tenant_id):
            owner_role = db.scalar(select(Role).where(Role.key == "owner"))
            if owner_role is None:
                continue
            for mid in list(db.scalars(select(MembershipRole.membership_id).where(MembershipRole.role_id == owner_role.id))):
                if db.scalar(select(Employee.id).where(Employee.membership_id == mid)):
                    continue
                m = db.get(TenantMembership, mid)
                ident = db.get(Identity, m.identity_id) if m else None
                if ident is None:
                    continue
                first, _, last = ident.full_name.partition(" ")
                emp = Employee(tenant_id=tenant_id, employee_code=next_code(db), membership_id=mid, first_name=first,
                               last_name=last or "-", email=ident.email, status="active", joining_date=date.today())
                db.add(emp)
                db.flush()
                _open_assignment(db, emp, emp.joining_date)
                _event(db, emp, "joined", emp.joining_date, ident.id, {"source": "backfill"})
    db.commit()


def register_handlers() -> None:
    events.subscribe("tenant.created", _on_tenant_created)
    events.subscribe("member.joined", _on_member_joined)


def forbid_self_decision(me: Employee | None, target_employee_id: uuid.UUID) -> None:
    if me is not None and me.id == target_employee_id:
        raise Forbidden("You cannot approve your own request", code="self_approval")
