"""Permission catalogue and default role definitions (single source of truth; see docs/product/permission-matrix.md).

Platform Super Admin is not a tenant role. It is `Identity.is_platform_admin` and grants no tenant data
permissions. Access to a tenant's private data needs explicit, audited, time-limited support access.
"""
from __future__ import annotations

# code -> (module, description, sensitive)
CATALOG: dict[str, tuple[str, str, bool]] = {
    "org.read": ("organization", "View organization structure and settings", False),
    "org.manage": ("organization", "Manage organization structure and settings", False),
    "settings.manage": ("organization", "Manage tenant configuration and policies", False),
    "members.read": ("tenancy", "View tenant members", False),
    "members.manage": ("tenancy", "Invite members and assign roles", False),
    "roles.manage": ("tenancy", "Create and edit custom roles", False),
    "audit.read": ("tenancy", "Read audit logs", True),
    "billing.manage": ("billing", "Manage subscription and billing", True),
    "employees.read_own": ("employees", "View own employee profile", False),
    "employees.read_team": ("employees", "View direct reports and team", False),
    "employees.read": ("employees", "View employee directory and records", False),
    "employees.manage": ("employees", "Create and edit employee records", False),
    "salary.read": ("employees", "View salary information", True),
    "salary.manage": ("employees", "Create salary revisions", True),
    "bank.read": ("employees", "View bank account details", True),
    "attendance.read_own": ("attendance", "View own attendance", False),
    "attendance.record_own": ("attendance", "Check in / out", False),
    "attendance.approve": ("attendance", "Approve attendance corrections", False),
    "attendance.manage": ("attendance", "Manage attendance policies and records", False),
    "leave.apply": ("leave", "Apply for leave", False),
    "leave.approve": ("leave", "Approve leave requests", False),
    "leave.manage": ("leave", "Manage leave policies and balances", False),
    "payroll.read": ("payroll", "View payroll runs", True),
    "payroll.process": ("payroll", "Prepare and calculate payroll", True),
    "payroll.approve": ("payroll", "Approve and finalize payroll", True),
    "payslip.read_own": ("payroll", "View own payslips", False),
    "recruitment.read_assigned": ("recruitment", "View assigned hiring pipelines", False),
    "recruitment.manage": ("recruitment", "Manage requisitions, candidates and offers", False),
    "performance.read_own": ("performance", "View own goals and reviews", False),
    "performance.review_team": ("performance", "Review direct reports", False),
    "performance.manage": ("performance", "Manage review cycles and ratings", True),
    "expenses.submit": ("expenses", "Submit expense claims", False),
    "expenses.approve": ("expenses", "Approve team expense claims", False),
    "expenses.finance_approve": ("expenses", "Finance approval and reimbursement", True),
    "assets.manage": ("assets", "Manage company assets", False),
    "training.manage": ("training", "Manage training programs", False),
    "helpdesk.submit": ("helpdesk", "Raise HR tickets", False),
    "helpdesk.manage": ("helpdesk", "Work HR tickets", False),
    "documents.manage": ("documents", "Manage employee documents", True),
    "workflows.manage": ("workflows", "Configure workflows", False),
    "notices.manage": ("notices", "Publish company notices", False),
    "tasks.manage": ("tasks", "Assign tasks to employees", False),
    "loans.manage": ("loans", "Approve and disburse loans and advances", True),
    "loans.request": ("loans", "Request a loan or salary advance", False),
    "reports.view": ("reporting", "View reports and dashboards", False),
    "ai.use": ("ai", "Use the AI assistant", False),
}

SELF_SERVICE = {
    "employees.read_own", "attendance.read_own", "attendance.record_own", "leave.apply", "payslip.read_own",
    "performance.read_own", "expenses.submit", "helpdesk.submit", "org.read", "ai.use", "loans.request",
}
TEAM = {
    "employees.read_team", "attendance.approve", "leave.approve", "performance.review_team",
    "expenses.approve", "reports.view", "members.read", "tasks.manage",
}
HR_BASE = TEAM | {
    "employees.read", "employees.manage", "salary.read", "attendance.manage", "leave.manage", "org.manage",
    "recruitment.manage", "performance.manage", "assets.manage", "training.manage", "helpdesk.manage",
    "documents.manage", "workflows.manage", "notices.manage", "loans.manage",
}

# key -> (display name, description, permissions)
DEFAULT_ROLES: dict[str, tuple[str, str, set[str]]] = {
    "owner": ("Organization Owner", "Full control of the organization", set(CATALOG)),
    "hr_admin": (
        "HR Administrator", "Manages all HR records and configuration",
        SELF_SERVICE | HR_BASE | {"settings.manage", "members.manage", "bank.read", "salary.manage", "audit.read"},
    ),
    "hr_manager": ("HR Manager", "Manages HR operations", SELF_SERVICE | HR_BASE),
    "finance_manager": (
        "Finance Manager", "Processes payroll and reimbursements (cannot approve own payroll runs)",
        SELF_SERVICE | {
            "payroll.read", "payroll.process", "salary.read", "bank.read", "expenses.finance_approve",
            "reports.view", "employees.read", "members.read",
        },
    ),
    "department_manager": ("Department Manager", "Manages a department", SELF_SERVICE | TEAM),
    "reporting_manager": ("Reporting Manager", "Manages direct reports", SELF_SERVICE | TEAM),
    "employee": ("Employee", "Standard self-service access", set(SELF_SERVICE)),
    "recruiter": (
        "Recruiter", "Works assigned hiring pipelines",
        SELF_SERVICE | {"recruitment.read_assigned", "recruitment.manage"},
    ),
    "auditor": (
        "Auditor", "Read-only access to audit and reports",
        {"audit.read", "reports.view", "org.read", "members.read", "employees.read_own"},
    ),
}

assert all(p in CATALOG for _, _, perms in DEFAULT_ROLES.values() for p in perms), "unknown permission in role"
