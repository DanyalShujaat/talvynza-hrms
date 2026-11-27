# Product workflows

## Organization setup and onboarding

```mermaid
flowchart TD
    Branch["Create an active branch"] --> Department["Create an active department"]
    Department --> Setup["Check organization setup"]
    Policy["Save attendance policy"] --> Setup
    Leave["Configure an active leave type"] --> Setup
    Salary["Create an active salary template"] --> Setup
    Setup --> Entry{"Choose an entry path"}
    Entry --> Manual["Add employee"]
    Entry --> Bulk["Preview and commit employee import"]
    Entry --> Hire["Hire from candidate record"]
    Manual --> Profile["Employee profile and onboarding checklist"]
    Bulk --> Profile
    Hire --> Profile
    Profile --> Assign["Review placement, attendance access, salary, and portal access"]
```

New employees require an active branch and department. Department designation choices follow the selected department. The employee profile links placement with attendance, leave, payroll, and onboarding records.

## Attendance and branch premises

```mermaid
flowchart TD
    Start["Employee attempts a punch"] --> Channel{"Attendance method"}
    Channel --> Web["Web checks channel access and branch premises"]
    Channel --> Mobile["Mobile submits location when branch premises exist"]
    Channel --> Device["Branch biometric import resolves the employee by biometric ID"]
    Web --> Eligible{"Method and location permitted?"}
    Mobile --> Eligible
    Device --> Eligible
    Eligible -->|Yes| Event["Persist attendance event"]
    Eligible -->|No| Feedback["Explain why the punch was declined"]
    Event --> Day["Resolve workday using shift and time zone"]
    Day --> Report["Recalculate the employee's attendance summary"]
```

Web attendance is blocked when the branch has premises. Mobile can punch anywhere when enabled and the branch has no premises. Administrators can change one attendance method for a selection of employees using branch and department filters.

## Requests and payroll

```mermaid
flowchart TD
    Submit["Employee submits a request"] --> Source["Save in the source module"]
    Source --> Inbox["Show in My Requests and the reviewer inbox"]
    Inbox --> Review["Reviewer opens the request and source record"]
    Review --> Decision["Record a permitted decision"]
    Decision --> Update["Refresh status, notifications, and relevant balances"]
    Salary["Effective salary revisions"] --> Calculate["Calculate the draft payroll run"]
    Update -->|Eligible payroll inputs| Calculate
    Calculate --> ReviewRun["Review employees, exceptions, and totals"]
    ReviewRun --> Approve["Separate approver approves the run"]
    Approve --> Publish["Finalize and publish employee payslips"]
```

Payroll finalization also settles expense claims and loan installments included in that run. Each payroll entry links to the corresponding employee record when the reviewer has access.

## Employee exit

```mermaid
flowchart LR
    Record["Record exit dates and reason"] --> Clearance["Complete clearance checklist"]
    Clearance --> Settle["Review assets, loans, expenses, and leave"]
    Settle --> Review["Record final settlement inputs"]
    Review --> Complete["Complete exit and remove organization access"]
    Complete --> History["Retain employee and exit history"]
```

The exit record links directly to the employee's assets, loans, expenses, and payslips. Outstanding assigned assets, loan balances, and clearance items block completion.
