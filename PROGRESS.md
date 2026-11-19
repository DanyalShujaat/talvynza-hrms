# Progress

Last updated 2026-11-14.

## Status by area

| Area | State |
|---|---|
| Auth, sessions, MFA, CSRF, lockout | Done, tested |
| Multi-tenancy (server-side tenant, ORM isolation), roles, permissions, invitations, audit log | Done, tested |
| Organization: branches, departments, designations, holidays | Done, tested |
| Employees: profile, lifecycle events, effective-dated placement, documents, education, onboarding checklist, bulk import | Done, tested |
| Attendance: check in and out, policy (grace, lateness modes, overtime, weekends), shifts, rosters, corrections, CSV import | Done, tested |
| Leave: types, ledger, per-year balances, approvals, pro-rated grants, carry-forward, planner | Done, tested |
| Payroll: components, salary revisions, run workflow, payslips, payment export | Done, tested. Statutory deductions are not configured |
| Recruitment: jobs, pipeline, interviews, public careers page, hire to employee | Done, tested |
| Notices, in-app notifications, tasks | Done, tested |
| Dashboard | Done, real data |
| Frontend (Talvynza visual system) | Done for every module above, 14 browser tests |
| Expenses, loans and advances, assets, training, help desk, performance, offboarding workflow | Not started |
| Workflow engine, AI assistant, advanced reports, scheduled reports | Not started |
| Billing, plans, entitlements, platform admin | Not started |
| Docker, CI, PostgreSQL verification | Written, never run |

## Tests run on 2026-11-14

| Suite | Result |
|---|---|
| Backend pytest (SQLite) | 155 passed |
| Backend ruff | clean |
| Frontend vitest | 9 passed |
| Frontend typecheck and production build | clean |
| Playwright browser tests (Chromium) | 14 passed |

## Migrations
- `0001` identities, sessions, tenants, memberships, roles, permissions, invitations, audit log
- `0002` branches, departments, designations, holidays, employees and related tables, attendance, leave, payroll,
  recruitment, notices, notifications, tasks

## Next steps
1. Run the Docker stack and the CI migration job against PostgreSQL, fix what they find.
2. Expenses, loans, assets, help desk, training, performance and the offboarding checklist.
3. Plans, entitlements and billing with a sandbox payment gateway adapter.
4. Row-level security in PostgreSQL as a second tenant isolation layer.
5. Reports with CSV and PDF export, scheduled delivery.
