# Architecture

## 1. Shape

A modular monolith: one FastAPI service, one Celery worker, one PostgreSQL database, Redis for rate limiting and queues.
Business domains live in `apps/api/app/modules/<domain>/` and talk to each other through service functions and
in-process events (`app/core/events.py`).

```
apps/api/app/
  core/       config, errors, security, rate limiting, email adapter, events, logging, pagination, file storage
  db/         Base and mixins, portable column types, session factory, tenant_scope (isolation)
  modules/
    identity/       identities, sessions, email tokens, MFA, security events
    tenancy/        tenants, memberships, roles and permissions, invitations, audit log
    organization/   branches, departments, designations, holidays
    employees/      profiles, placements, lifecycle, education, documents, checklist, bulk import
    attendance/     policy, shifts, punches, daily summaries, corrections (engine.py is pure)
    leave/          types, ledger, requests, grants and carry-forward
    payroll/        components, salary revisions, runs, entries (engine.py is pure)
    recruitment/    jobs, candidates, applications, interviews, public careers
    notifications/  notices, in-app notifications, tasks
    reporting/      dashboard statistics
    scheduling, performance, expenses, assets, training, workflows, billing, ai   (empty, not built)
  models.py   imports every model module so Alembic and create_all see the whole schema
  main.py     app factory, middleware, routers, health checks
apps/web/     React, TypeScript, Vite, Tailwind v4. TanStack Query for server state, Zustand for UI preferences only
```

Each module is router (HTTP, validation, permission dependency), service (transactions, rules, audit), models.
Routers hold no business logic. Services own `commit()`. Calculations that carry business rules are pure functions in
`engine.py` files, so they are tested without a database.

## 2. Tenant isolation

Every tenant-owned table has a non-null, indexed `tenant_id` by inheriting `TenantScoped`. Three layers:

1. The active tenant is stored on the server-side session. The client can ask to switch, which works only with an active
   membership. No endpoint reads a tenant id from the request to decide what data to return.
2. `app/db/tenant_scope.py` adds `tenant_id = <session scope>` to every SELECT, UPDATE and DELETE touching a scoped
   entity, stamps new rows, refuses rows for another tenant and makes `tenant_id` immutable. A session without a scope
   sees nothing and cannot insert. `ALL_TENANTS` is an explicit system scope used for invitation lookup and the public
   careers page, which then narrows to one tenant.
3. Endpoints call `require("permission.code")`.

An id belonging to another tenant gets the same 404 as an id that does not exist, for HR and owners too.
Row-level security in PostgreSQL is not enabled yet. The ORM layer does not protect raw SQL, so raw SQL on tenant
tables is not allowed.

## 3. Identity and access

- One identity per person, many memberships. Platform admin is `identities.is_platform_admin` and holds no tenant
  permissions.
- Server-side sessions: an opaque token in an HttpOnly SameSite cookie, only its hash stored. Absolute and idle expiry,
  revocation, revoked on password change or reset.
- CSRF token is an HMAC of the session token, sent in `X-CSRF-Token`, plus an Origin allow-list.
- Argon2id passwords with a policy, lockout after repeated failures, identical errors for unknown account and wrong
  password, enumeration-safe register, forgot and resend endpoints.
- TOTP MFA with replay protection and single-use recovery codes. The secret is encrypted at rest.
- Roles are copied per tenant from `modules/tenancy/permissions.py`. Default roles are immutable, custom roles are
  allowed, and nobody can grant a permission they do not hold. An organization always keeps one owner.
- Sensitive fields (bank account, national ID, MFA secret) use `EncryptedString`. Salary reads need `salary.read`,
  bank details need `bank.read`.
- Employee visibility: `employees.read` sees everyone, `employees.read_team` sees the manager's reporting tree,
  otherwise only oneself.

## 4. Business rules worth knowing

- Placement (branch, department, designation, manager) is effective-dated. Rows are closed, never deleted.
- Attendance: all instants are UTC, shifts are interpreted in the organization time zone (so daylight saving works),
  overnight shifts belong to the date they start, duplicate reads within 60 seconds collapse.
- Lateness has two modes. After the grace window `full` counts every minute from shift start, `grace_exempt` counts only
  the minutes beyond the grace window.
- Leave balances come from an append-only ledger. Entitled, used, reserved and available are derived, per leave year.
- Payroll uses `Decimal` throughout, rounds half-up once per line, and never overwrites a salary revision.
  Approved or finalized runs are immutable (service guard and ORM guard). The creator of a run cannot approve it.
  Details in `docs/product/payroll-calculation.md`.
- Nobody approves their own leave request or attendance correction.

## 5. API conventions

- Base path `/api/v1`, OpenAPI at `/api/docs`, exported to `docs/api/openapi.json`.
- Errors are `{"error": {"code", "message", "details", "request_id"}}`. Unhandled errors never leak internals.
- Lists return `{items, total, page, page_size}`.
- Every response carries `X-Request-ID` and security headers. Logs are structured JSON.

## 6. Data

PostgreSQL in production. Tests run the same models on SQLite through portable types (`Uuid`, `Numeric` for money,
`UTCDateTime`). Alembic owns the schema, and a test checks that the migrations match the models and downgrade cleanly.
See `docs/database/erd.md`.

## 7. Frontend

A single-page app behind nginx in production, with a Vite proxy in development. The session cookie is not readable by
JavaScript. The query cache is cleared when switching organization or signing out. The layout follows the existing
Talvynza visual system: clear navigation, blue and teal accents from the logo, and readable dashboard cards.
Playwright tests drive the real UI against a throwaway API.

## 8. Decisions

| Decision | Reason |
|---|---|
| Server-side sessions instead of JWT | Instant revocation, tenant switching without new tokens |
| Roles copied per tenant | Strict isolation, custom roles behave like default ones |
| Registration creates the first organization | One step from sign-up to a working workspace |
| Every employee record can exist without a login | HR can add people before inviting them. A matching email links the account on acceptance |
| SQLite for tests | No PostgreSQL on the build machine. CI applies migrations to PostgreSQL |
