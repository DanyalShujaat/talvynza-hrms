# Known limitations

## Not verified
- The Docker files, nginx config and the GitHub Actions workflow have never been run. The build machine had no Docker,
  PostgreSQL or Redis.
- Backend tests and migrations run on SQLite. The CI workflow applies migrations to PostgreSQL 16 and runs
  `alembic check`, but that has not executed yet.
- Redis rate limiting and Celery with a real broker are untested. The in-memory limiter and an eager Celery task are tested.
- Browser tests cover Chromium at desktop and phone width only.

## Not built
- Expenses, loans and salary advances, asset tracking, training, help desk, performance reviews and goals,
  an offboarding clearance workflow (lifecycle events exist, clearance and final settlement do not).
- Workflow engine with configurable approval chains. Leave and corrections use a fixed rule: the employee's manager or
  HR approves, nobody approves their own request.
- AI assistant, advanced dashboards, saved and scheduled reports, PDF export.
- Subscription plans, entitlements, billing, payment gateway adapters, platform admin interface.
- SSO (OIDC and SAML), SMS and push notifications, outgoing webhooks, biometric device adapters (CSV import exists).
- Email is sent immediately by the console or SMTP backend. There is no queue, retry or template system yet.
- Data retention, anonymization and tenant deletion workflows.

## Payroll
- No statutory calculation exists: no income tax, social insurance or pension. Runs report `statutory_status =
  unconfigured` and payslips say so. These rules must be sourced, versioned and verified per country before use.
- Salary amounts are per pay period. Monthly is the tested case. Biweekly and weekly runs work arithmetically but have
  no dedicated calendar or per-frequency salary basis.
- Back-dated salary revisions do not change finalized runs. The API warns and the difference must be handled in a later
  run. There is no arrears or supplemental run type yet.
- Loans and expense reimbursements do not feed payroll yet.

## Security
- PostgreSQL row-level security is not enabled. Isolation relies on the ORM layer, which does not cover raw SQL.
- No time-limited, audited support access for platform staff.
- Trusted-proxy configuration for client IP addresses.
- `npm audit` reported 2 moderate advisories in development tooling at install time. Not triaged.
- Uploaded files are validated by type and size. A malware scanner hook exists but no scanner is registered.
- Backups, restore drills and error monitoring are not configured.

## Product behavior to know about
- A person must register (which also creates their own organization) before accepting an invitation.
- Roles can be assigned but members cannot yet be suspended or removed from the interface.
- Leave balances are per leave year, and a request counts toward the year it starts in.
- The overnight shift rule is: punches from 4 hours before the shift start to 5 hours after its end belong to that
  shift's start date.
- The production bundle is a single 1 MB script. Route-level code splitting has not been done.
