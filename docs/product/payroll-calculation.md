# Payroll calculation

Implemented in `apps/api/app/modules/payroll/engine.py` as pure functions, tested in
`tests/test_payroll_engine.py` and `tests/test_payroll_api.py`.

## Inputs
- Salary revisions per employee: effective date, basic salary per pay period, optional component lines.
  A change is a new revision. Old revisions are never edited.
- Components: earning or deduction, fixed amount or percent of basic, taxable flag. A revision line may override the
  component's default amount.
- Pay period start and end, proration method (`calendar_days` or `working_days`), weekend days and holidays from the
  organization's attendance policy and holiday list.
- Approved unpaid leave in the period.
- Joining date and exit date.

## Method
1. Take the part of the period the employee was employed. Split it into segments at each salary revision date.
2. The divisor is the number of countable days in the whole period (calendar days, or working days).
3. For each segment the fraction is `countable days in segment / divisor`. Basic and every component line is charged
   `monthly amount * fraction` for that segment, then summed per line.
4. Percent components use the basic of the segment's revision.
5. Unpaid leave: `full gross of the last revision / working days in the period * unpaid days`. Unpaid leave days are
   working days, so this rate uses working days whichever proration method is selected. Half days count as 0.5.
6. Each line is rounded half-up to 2 decimals once, after summing segments. `gross = earnings`,
   `deductions = deduction lines + unpaid leave`, `net = gross - deductions`.

## Worked example
Salary 100,000 until 14 October, 110,000 from 15 October. October has 31 days.

`100000 * 14/31 + 110000 * 17/31 = 45161.2903 + 60322.5806 = 105483.8709`, shown as 105,483.87.
With working-day proration (22 weekdays, 10 before the change and 12 after) the result is 105,454.55.

## Exceptions that block approval
`negative_net_pay`, `no_salary_in_period`, `period_has_no_countable_days`. Employees with no salary on file are listed
as skipped when calculating and get no entry.

## Workflow and controls
draft, calculated, approved, finalized.
- Only one run per organization and pay period (database unique constraint).
- Calculate can be repeated until approval and produces the same figures.
- The creator of a run cannot approve it. An organization with a single owner can switch this off with the tenant
  setting `payroll_allow_self_approval`, which is recorded in the audit log trail of that run.
- Approved and finalized runs cannot be recalculated, deleted or edited. The ORM also refuses updates to their entries
  and line items.
- Payslips are visible to the employee only after finalization, and only their own.
- The payment export is available for finalized runs to users holding `payroll.read` and `bank.read`, and every export
  is audited.

## Not calculated
Income tax, social insurance, pension, statutory reporting. See `known-limitations.md`.
