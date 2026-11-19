# Business rules

Each rule names where it is enforced and tested.

## Employees
- Employee ID is unique per organization and generated when left blank (`test_duplicate_code_and_email_rejected`).
- Email is unique among current employees. A matching email links an invited login to the record.
- The number of active employees (active, probation, suspended) cannot exceed the organization's limit.
- A manager cannot report to themselves or to someone below them (`test_manager_cycle_is_rejected_and_history_is_kept`).
- Changing branch, department, designation or manager closes the open placement and opens a new one.
- Lifecycle transitions: confirmation only from probation, suspension and reinstatement as a pair, resignation,
  termination and retirement only for current staff, rehire only for former staff (`test_lifecycle_transitions_and_audit`).
- Deleting an employee is a soft delete and is refused while the record has a login.
- Bank details and national ID are encrypted at rest and hidden without `bank.read` or `employees.manage`.

## Bulk import
Preview writes nothing. Rows are checked for required fields, date formats, email format, duplicates in the file and in
the organization, unknown branch, department or designation names, unknown managers, reporting loops and the employee
limit. Commit refuses a file with errors unless the user chooses to skip invalid rows. All valid rows are saved in one
transaction.

## Attendance
- Grace period and lateness mode are configurable per organization, with an optional grace override per shift.
- Worked time is the sum of punched intervals. With a single continuous interval the shift's unpaid break is deducted.
- Missing check-out makes the day incomplete, not present with zero hours.
- Work on weekends and holidays counts as overtime and is never late.
- A correction request is approved by the employee's manager or by HR, never by the requester
  (`test_correction_request_approval_updates_attendance_and_blocks_self_approval`).

## Leave
- Weekends and holidays are not counted. A half day must be a single date.
- Overlapping pending or approved requests are refused.
- A request that exceeds the available balance is refused unless the leave type allows negative balances.
- Types can be restricted to after probation.
- Approval is by the manager (leave.approve and in their reporting tree) or HR (leave.manage), never the requester.
- Grants are pro-rated by whole months for mid-year joiners, rounded to the nearest half day, and idempotent.
- Carry-forward is capped per type and idempotent.

## Payroll
See `payroll-calculation.md`.

## Recruitment
- A candidate can apply once per job. Public applications are rate limited and resumes are type and size checked.
- The pipeline is customizable but must keep Applied, Hired and Rejected, and a stage with candidates cannot be removed.
- Moving a candidate to Hired is only possible through the hire action, which creates the employee record.

## Access
- Nobody can grant a permission they do not hold. Default roles cannot be edited. An organization keeps one owner.
- Notices reach everyone, or only a branch or department. Employees see only notices for their audience.
