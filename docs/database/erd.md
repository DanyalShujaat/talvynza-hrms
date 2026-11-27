# Database ERD

The first diagram shows organization access. The second summarizes the records that connect placement,
attendance, leave, payroll, and workplace workflows. See the Alembic migrations for exact columns and constraints.

## Access and tenancy

```mermaid
erDiagram
    identities ||--o{ sessions : "has"
    identities ||--o{ email_tokens : "has"
    identities ||--o{ tenant_memberships : "joins tenants via"
    tenants ||--o{ tenant_memberships : "has members"
    tenants ||--o{ roles : "owns (tenant_id)"
    roles ||--o{ role_permissions : "grants"
    permissions ||--o{ role_permissions : "catalogue"
    tenant_memberships ||--o{ membership_roles : "assigned"
    roles ||--o{ membership_roles : "assigned"
    tenants ||--o{ invitations : "issues"
    tenants ||--o{ audit_logs : "records"
    sessions }o--|| tenants : "active_tenant_id"
    identities ||--o{ security_events : "optional"

    identities { uuid id PK
      string email UK
      string password_hash
      bool is_platform_admin
      bool mfa_enabled
      text mfa_secret "Fernet-encrypted"
      int failed_login_count
      datetime locked_until }
    sessions { uuid id PK
      uuid identity_id FK
      string token_hash UK
      uuid active_tenant_id FK
      datetime expires_at
      datetime revoked_at }
    tenants { uuid id PK
      string slug UK
      string country
      string currency
      string timezone
      string status
      string plan_code
      json enabled_modules }
    tenant_memberships { uuid id PK
      uuid tenant_id FK
      uuid identity_id FK
      string status }
    roles { uuid id PK
      uuid tenant_id FK "TenantScoped"
      string key "UK with tenant_id"
      bool is_system }
    permissions { string code PK
      string module
      bool is_sensitive }
    role_permissions { uuid id PK
      uuid tenant_id FK
      uuid role_id FK
      string permission_code FK }
    membership_roles { uuid id PK
      uuid tenant_id FK
      uuid membership_id FK
      uuid role_id FK }
    invitations { uuid id PK
      uuid tenant_id FK
      string email
      string role_key
      string token_hash UK }
    audit_logs { uuid id PK
      uuid tenant_id FK
      uuid actor_identity_id
      string action
      json details "append-only" }
    email_tokens { uuid id PK
      uuid identity_id FK
      string purpose
      string token_hash UK }
    security_events { uuid id PK
      string event_type
      string ip }
```

## HR domains (migration 0002)

```mermaid
erDiagram
    tenants ||--o{ branches : has
    tenants ||--o{ departments : has
    departments ||--o{ designations : has
    departments ||--o{ departments : "parent_id"
    tenants ||--o{ employees : has
    tenant_memberships ||--o| employees : "optional login"
    employees ||--o{ employees : "manager_id"
    employees ||--o{ employee_assignments : "placement history"
    employees ||--o{ employee_lifecycle_events : has
    employees ||--o{ employee_education : has
    employees ||--o{ employee_documents : has
    employees ||--o{ employee_checklist_items : has
    employees ||--o{ attendance_events : punches
    employees ||--o{ attendance_daily : "derived summary"
    employees ||--o{ attendance_adjustments : corrections
    shifts ||--o{ shift_assignments : "assigned to"
    employees ||--o{ shift_assignments : has
    leave_types ||--o{ leave_ledger : "balance source"
    employees ||--o{ leave_ledger : has
    employees ||--o{ leave_requests : files
    leave_requests ||--o{ leave_ledger : "reserve, release, use"
    employees ||--o{ salary_revisions : "never overwritten"
    salary_revisions ||--o{ salary_revision_lines : has
    salary_components ||--o{ salary_revision_lines : used
    payroll_runs ||--o{ payroll_entries : has
    employees ||--o{ payroll_entries : paid
    payroll_entries ||--o{ payroll_line_items : breakdown
    jobs ||--o{ job_applications : receives
    candidates ||--o{ job_applications : makes
    job_applications ||--o{ interview_records : has
    tenant_memberships ||--o{ notifications : receives
    employees ||--o{ tasks : assigned
```

Notes: `attendance_events` are immutable punches and `attendance_daily` is recalculated from them. `leave_ledger` is
append-only and balances are always derived from it. Payroll entries and line items cannot be modified once the run
is approved. Money columns are `NUMERIC(14,2)`. Dates without a time zone (joining date, work date, leave dates) are
`DATE`. Instants are UTC `timestamptz`.

## Conventions
* UUID primary keys; constraint names follow the metadata naming convention (`ix_`, `uq_`, `fk_`, `pk_`).
* `TenantScoped` tables carry `tenant_id` (NOT NULL, FK, indexed) and are filtered automatically by the ORM layer.
* Timestamps are UTC instants (`timestamptz`); money will use `NUMERIC(18,2)` (never float).
* `audit_logs` is append-only (ORM update/delete raises). `security_events` is platform-level, not tenant-scoped.
* `tenants`, `tenant_memberships`, `identities` and `permissions` are intentionally not auto-scoped (see ARCHITECTURE §2).


## Employee and operational records

```mermaid
erDiagram
    TENANTS ||--o{ BRANCHES : owns
    TENANTS ||--o{ DEPARTMENTS : owns
    TENANTS ||--o{ EMPLOYEES : employs
    BRANCHES o|--o{ EMPLOYEES : places
    DEPARTMENTS o|--o{ EMPLOYEES : groups
    DEPARTMENTS o|--o{ DESIGNATIONS : defines
    EMPLOYEES ||--o{ EMPLOYEE_ASSIGNMENTS : tracks
    EMPLOYEES ||--o{ ATTENDANCE_EVENTS : records
    EMPLOYEES ||--o{ ATTENDANCE_DAILY : summarizes
    EMPLOYEES ||--o{ LEAVE_REQUESTS : submits
    EMPLOYEES ||--o{ SALARY_REVISIONS : receives
    EMPLOYEES ||--o{ PAYROLL_ENTRIES : receives
    PAYROLL_RUNS ||--o{ PAYROLL_ENTRIES : contains
    EMPLOYEES ||--o{ EXPENSE_CLAIMS : submits
    EMPLOYEES ||--o{ LOANS : requests
    EMPLOYEES ||--o{ ASSET_ASSIGNMENTS : holds
```

A branch stores its premises as named circular boundaries. Employee attendance settings separately control
web, mobile, and biometric access. Historical employee data can have an empty placement. New employees
require an active branch and department.
