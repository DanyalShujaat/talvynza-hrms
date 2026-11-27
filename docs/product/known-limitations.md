# Known limitations

- Biometric attendance uses branch-scoped CSV imports. Direct vendor device synchronization requires an integration.
- Request approvals follow each module's role and reporting rules. A configurable approval-chain designer is outside the current scope.
- Payroll supports configured statutory schedules. Confirm the applicable schedule and rates for each pay period before finalizing. Finalized runs retain their original amounts when salary revisions are backdated.
- Browser automation covers Chromium at desktop and phone widths. Device location checks use simulated coordinates in the automated suite.
- PostgreSQL organization scoping is enforced by the application's ORM and access checks. Raw SQL requires explicit organization scoping.
- File storage must be persistent across production releases if the organization uses document uploads or attachments.
