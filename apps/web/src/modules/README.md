# Web modules

Pages live with their business domain. `src/main.tsx` owns URL routing; `src/components/layout/nav.ts` owns the permission-aware navigation; `src/components/layout/guides.ts` owns first-visit walkthrough content. Shared controls, API helpers, and session state remain under `components`, `lib`, and `stores`.

The cross-module request inbox is `platform/requests.tsx`, with shared request mapping in `platform/request-data.ts` and a dedicated request page in `platform/request-detail.tsx`. It reads leave, attendance, expense, loan, and help desk records and links to the source module. The global notification drawer is `components/layout/Notifications.tsx` and uses the notifications API for read state.

The task board is `workplace/tasks.tsx`, with To do, In progress, Blocked, and Done columns. Task writes use the notifications API, as do employee-facing events from leave, attendance, shifts, expenses, loans, help desk, recruitment, training, assets, performance, payroll, and notices. Backend event creation lives with each domain service or router; shared delivery helpers live in `apps/api/app/modules/notifications/service.py`.

| Folder | Pages and workflow |
| --- | --- |
| `people/` | Employee directory and profile, org chart, onboarding and offboarding |
| `organization/` | Departments, subdepartments, branches and HR policies |
| `recruitment/` | Vacancies, applicant pipeline, candidate details, career page and hire handoff |
| `time/` | Attendance and corrections, shifts, leave requests, public holidays, leave planner |
| `pay/` | Salary templates and increments (`salary-templates.tsx`), payroll, expenses, loans and advances |
| `workplace/` | Kanban tasks (`tasks.tsx`) and notices (`work.tsx`), performance, training, assets, HR help desk |
| `platform/` | Dashboard, request inbox, reports, users and roles, organization settings, authentication, demo and public landing |

## Connected record flow

Recruitment creates an employee and starts onboarding. An employee belongs to a branch and department and may report to another employee; these records feed the org chart and filtered directory. Shifts, holiday rules, attendance, and approved leave feed time reports and payroll. Expenses, loans, assets, and unused leave appear in offboarding clearance. The request inbox links back to the source modules, which remain the record of truth.

When adding a module, place its page in the corresponding folder, register its route in `main.tsx`, navigation and permissions in `nav.ts`, and its walkthrough in `guides.ts`. Reuse `lib/hooks.ts` for data access so mutations invalidate related modules.
