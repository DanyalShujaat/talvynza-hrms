# Testing

| Suite | Location | Command |
|---|---|---|
| Backend unit and API | `apps/api/tests` | `pytest -q` |
| Frontend unit | `apps/web/src/**/*.test.ts(x)` | `npm test` |
| Browser end-to-end | `apps/web/e2e` | `npm run e2e` |

Backend tests use an in-memory SQLite database that is rebuilt for every test. Emails go to an in-memory outbox that tests
read to complete verification and invitation flows. Rate limiting is off in tests, and the limiter class is unit tested.

Browser tests start their own API (`apps/api/scripts/run_e2e_api.py`, fresh SQLite file, email verification off) and a Vite
server on port 5174, then drive Chromium through signup, organization setup, employees, bulk import, check in and out,
time adjustments, branch premises, leave, payroll, requests, hiring, Tali, the phone layout, and organization isolation.

## Where the important checks live
- Tenant isolation, privilege escalation, audit immutability: `test_tenant_isolation.py`, plus an isolation test in each
  module's API tests.
- Attendance rules: `test_attendance_engine.py` (grace modes, overnight, daylight saving, duplicates).
- Payroll arithmetic: `test_payroll_engine.py` (including the mid-month raise example).
- Payroll controls (separation of duties, immutability, payslip privacy, export): `test_payroll_api.py`.
- Migrations match the models and downgrade cleanly: `test_migrations.py`.

## Release checks

After deployment, verify the public application, a direct client route, and API readiness.
