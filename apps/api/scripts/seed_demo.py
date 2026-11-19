"""Loads a fictional demo organization through the public API, so every business rule applies as in real use.

    python scripts/seed_demo.py --api-log <file the API writes its log to>

The API must be running. With the default console email backend the verification and invitation links are read
from the API log, which is why the log path is needed. Development only: refuses to run when
TALVYNZA_ENVIRONMENT=production. Passwords are generated for each run and printed once.
"""
import argparse
import json
import os
import re
import secrets
import sys
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import httpx

if os.environ.get("TALVYNZA_ENVIRONMENT") == "production":
    sys.exit("Refusing to seed demo data in production.")

p = argparse.ArgumentParser()
p.add_argument("--api", default="http://127.0.0.1:8000")
p.add_argument("--api-log", help="file the API log is written to (needed to read emailed links in development)")
p.add_argument("--org", default="Talvynza Demo")
p.add_argument("--domain", default="talvynza-demo.com")
p.add_argument("--accounts-file", help="Write local fictional demo credentials to this private file")
args = p.parse_args()


def password() -> str:
    return f"Tv-{secrets.token_urlsafe(10)}-9x!"


def emailed_token(kind: str) -> str:
    """Latest token of this kind in the API log. `kind` is the path in the emailed link."""
    if not args.api_log:
        return input(f"Paste the token from the API log line containing {kind}?token=... : ").strip()
    for _ in range(20):
        found = re.findall(kind + r"\?token=([\w-]+)", open(args.api_log, encoding="utf-8", errors="ignore").read())
        if found:
            return found[-1]
        time.sleep(0.25)
    sys.exit(f"No {kind} link found in {args.api_log}")


class User:
    def __init__(self):
        self.c = httpx.Client(base_url=args.api + "/api/v1", timeout=60)

    def call(self, method, path, ok=(200, 201, 202, 204), **kw):
        csrf = self.c.cookies.get("nx_csrf")
        r = self.c.request(method, path, headers={"X-CSRF-Token": csrf} if csrf and method != "GET" else {}, **kw)
        if r.status_code not in ok:
            sys.exit(f"{method} {path} -> {r.status_code} {r.text[:300]}")
        return r.json() if r.content else None

    def get(self, path, **kw):
        return self.call("GET", path, **kw)

    def post(self, path, json=None, **kw):
        return self.call("POST", path, json=json, **kw)


today = date.today()
tz = timezone(timedelta(hours=5))
owner = User()
OWNER_EMAIL, OWNER_PW = f"owner@{args.domain}", password()
r = owner.c.post("/auth/register", json={
    "email": OWNER_EMAIL, "password": OWNER_PW, "full_name": "Nadia Rahman", "organization_name": args.org,
    "country": "PK", "currency": "PKR", "timezone": "Asia/Karachi", "expected_employee_count": 40})
if r.status_code != 202:
    sys.exit(f"Registration failed: {r.status_code} {r.text}")
if owner.c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW}).status_code != 200:
    owner.post("/auth/verify-email", {"token": emailed_token("verify-email")})
    if owner.c.post("/auth/login", json={"email": OWNER_EMAIL, "password": OWNER_PW}).status_code != 200:
        sys.exit(f"{OWNER_EMAIL} already exists. Use --domain to seed a second demo organization.")

# ---------------------------------------------------------------- structure
branches = {n: owner.post("/branches", {"name": n, "city": c, "code": code})["id"]
            for n, c, code in (("Head Office", "Peshawar", "PSH"), ("Lahore Office", "Lahore", "LHE"))}
depts = {n: owner.post("/departments", {"name": n, "description": d})["id"] for n, d in (
    ("Engineering", "Product development"), ("Sales", "Revenue and client accounts"), ("Finance", "Accounting and payroll"),
    ("People Operations", "HR and administration"))}
desig = {}
for name, dept in (("Engineering Manager", "Engineering"), ("Senior Software Engineer", "Engineering"),
                   ("Software Engineer", "Engineering"), ("Sales Lead", "Sales"), ("Account Executive", "Sales"),
                   ("Finance Manager", "Finance"), ("Accountant", "Finance"), ("HR Officer", "People Operations")):
    desig[name] = owner.post("/designations", {"name": name, "department_id": depts[dept]})["id"]
for d, n in ((f"{today.year}-12-25", "Quaid-e-Azam Day"), (f"{today.year + 1}-02-05", "Kashmir Day"),
             (f"{today.year + 1}-03-23", "Pakistan Day")):
    owner.post("/holidays", {"holiday_date": d, "name": n})

# ---------------------------------------------------------------- pay structure
hra = owner.post("/payroll/components", {"name": "House rent allowance", "kind": "earning", "calc": "percent_of_basic", "default_value": "40"})
medical = owner.post("/payroll/components", {"name": "Medical allowance", "kind": "earning", "calc": "percent_of_basic",
                                             "default_value": "10", "taxable": True, "exempt_percent_of_basic": "10"})
pf = owner.post("/payroll/components", {"name": "Provident fund", "kind": "deduction", "calc": "percent_of_basic", "default_value": "5"})
LINES = [{"component_id": c["id"]} for c in (hra, medical, pf)]

#          first      last        designation                 dept                 branch           manager  basic
PEOPLE = [("Imran", "Qureshi", "Engineering Manager", "Engineering", "Head Office", None, 260000),
          ("Sara", "Khan", "Senior Software Engineer", "Engineering", "Head Office", 0, 180000),
          ("Bilal", "Ahmed", "Software Engineer", "Engineering", "Lahore Office", 0, 120000),
          ("Hira", "Malik", "Software Engineer", "Engineering", "Head Office", 0, 110000),
          ("Usman", "Ghani", "Software Engineer", "Engineering", "Head Office", 0, 95000),
          ("Zain", "Raza", "Sales Lead", "Sales", "Lahore Office", None, 150000),
          ("Ayesha", "Siddiqui", "Account Executive", "Sales", "Lahore Office", 5, 85000),
          ("Faisal", "Anwar", "Finance Manager", "Finance", "Head Office", None, 170000),
          ("Noor", "Fatima", "Accountant", "Finance", "Head Office", 7, 70000),
          ("Mariam", "Tariq", "HR Officer", "People Operations", "Head Office", None, 90000),
          ("Omer", "Javed", "Account Executive", "Sales", "Head Office", 5, 48000)]
emps = []
for i, (fn, ln, title, dept, branch, mgr, basic) in enumerate(PEOPLE):
    body = {"first_name": fn, "last_name": ln, "email": f"{fn.lower()}.{ln.lower()}@{args.domain}",
            "phone": f"+92300{1000000 + i * 111111}", "joining_date": (today - timedelta(days=900 - i * 60)).isoformat(),
            "designation_id": desig[title], "department_id": depts[dept], "branch_id": branches[branch],
            "gender": "female" if fn in ("Sara", "Hira", "Ayesha", "Noor", "Mariam") else "male",
            "bank_name": "HBL", "bank_account": f"PK36HABB00000{1000000 + i}", "payment_method": "bank_transfer"}
    if mgr is not None:
        body["manager_id"] = emps[mgr]["id"]
    if fn == "Omer":  # a recent joiner still on probation, with a contract ending soon
        body.update(joining_date=(today - timedelta(days=45)).isoformat(), probation_end=(today + timedelta(days=20)).isoformat(),
                    contract_type="fixed_term", contract_end=(today + timedelta(days=25)).isoformat())
    e = owner.post("/employees", body)
    emps.append(e)
    owner.post(f"/employees/{e['id']}/salary", {"effective_from": "2025-01-01", "basic": str(basic), "lines": LINES, "reason": "Starting salary"})
by = {e["first_name"]: e for e in emps}
owner.post(f"/employees/{by['Sara']['id']}/salary", {"effective_from": (today.replace(day=1) - timedelta(days=1)).replace(day=1).isoformat(),
                                                    "basic": "200000", "lines": LINES, "reason": "Annual review"})


def portal(first: str, role: str) -> tuple[User, str, str]:
    """Invites an employee to the portal and completes the join as them."""
    e, pw, u = by[first], password(), User()
    owner.post(f"/employees/{e['id']}/invite", {"role_key": role})
    u.post("/auth/join", {"token": emailed_token("accept-invitation"), "full_name": e["full_name"], "password": pw})
    return u, e["email"], pw


manager, MANAGER_EMAIL, MANAGER_PW = portal("Imran", "department_manager")
employee, EMPLOYEE_EMAIL, EMPLOYEE_PW = portal("Sara", "employee")
finance, FINANCE_EMAIL, FINANCE_PW = portal("Faisal", "finance_manager")

# ---------------------------------------------------------------- attendance: last 12 working days
owner.post("/shifts", {"name": "Night", "start_time": "22:00", "end_time": "06:00", "break_minutes": 30})
for back in range(1, 17):
    d = today - timedelta(days=back)
    if d.weekday() >= 5:
        continue
    for j, e in enumerate(emps):
        if (j * 3 + back) % 11 == 0:
            continue  # absent that day
        late = 22 if (j + back) % 4 == 0 else 0
        start = datetime(d.year, d.month, d.day, 9, 0, tzinfo=tz) + timedelta(minutes=late + j % 5)
        end = datetime(d.year, d.month, d.day, 18, 0, tzinfo=tz) + timedelta(minutes=(j * 13 + back * 7) % 70)
        owner.post("/attendance/manual", {"employee_id": e["id"], "kind": "in", "occurred_at": start.isoformat()})
        owner.post("/attendance/manual", {"employee_id": e["id"], "kind": "out", "occurred_at": end.isoformat()})
employee.post("/attendance/check-in")
manager.post("/attendance/check-in")
missed = today - timedelta(days=3 if (today - timedelta(days=3)).weekday() < 5 else 5)
employee.post("/attendance/adjustments", {"work_date": missed.isoformat(), "in_time": "09:05", "out_time": "18:10",
                                         "reason": "Biometric device was offline in the morning"})

# ---------------------------------------------------------------- leave
owner.post("/leave/grants/run", params={"year": today.year})
owner.post("/leave/grants/run", params={"year": today.year + 1})
types = {t["name"]: t["id"] for t in owner.get("/leave/types")}
mon = today + timedelta(days=(7 - today.weekday()) % 7 or 7)
employee.post("/leave/requests", {"leave_type_id": types["Casual Leave"], "start_date": (mon + timedelta(days=3)).isoformat(),
                                 "end_date": (mon + timedelta(days=3)).isoformat(), "reason": "Family event"})
for first, kind, offset, days in (("Bilal", "Sick Leave", 0, 1), ("Hira", "Casual Leave", 8, 1), ("Ayesha", "Casual Leave", 1, 1)):
    req = owner.post("/leave/requests", {"employee_id": by[first]["id"], "leave_type_id": types[kind], "reason": "Personal",
                                        "start_date": (mon + timedelta(days=offset)).isoformat(),
                                        "end_date": (mon + timedelta(days=offset + days - 1)).isoformat()})
    if first == "Bilal":
        owner.post(f"/leave/requests/{req['id']}/decision", {"approve": True})

# ---------------------------------------------------------------- expenses, loans, tickets, goals (from the employee side)
cats = {c["name"]: c["id"] for c in employee.get("/expenses/categories")}
pdf = b"%PDF-1.4\n1 0 obj<<>>endobj\ntrailer<<>>\n%%EOF"
c1 = employee.post("/expenses", data={"category_id": cats["Meals"], "amount": "3200", "expense_date": (today - timedelta(days=4)).isoformat(),
                                     "description": "Client lunch, Lahore visit"})
c2 = employee.post("/expenses", files={"receipt": ("fuel.pdf", pdf, "application/pdf")},
                   data={"category_id": cats["Fuel"], "amount": "6500", "expense_date": (today - timedelta(days=9)).isoformat(),
                         "description": "Fuel for the Islamabad client trip"})
manager.post(f"/expenses/{c2['id']}/manager-decision", {"approve": True})
finance.post(f"/expenses/{c2['id']}/finance-decision", {"approve": True, "reimburse_via": "payroll"})
loan = employee.post("/loans", {"kind": "loan", "principal": "120000", "installments": 6, "reason": "Home repairs"})
owner.post(f"/loans/{loan['id']}/decision", {"approve": True})
owner.post(f"/loans/{loan['id']}/disburse", {"disbursed_on": today.isoformat(), "first_due_month": today.strftime("%Y-%m")})
manager.post("/loans", {"kind": "advance", "principal": "50000", "installments": 2, "reason": "School fees"})
t1 = employee.post("/tickets", {"category": "payroll", "priority": "high", "subject": "Tax certificate for the bank",
                               "description": "I need a salary and tax deduction certificate for a home loan application."})
owner.post(f"/tickets/{t1['id']}/comments", {"body": "We will have it ready by Thursday."})
manager.post("/tickets", {"category": "policy", "priority": "normal", "subject": "Remote work policy for my team",
                          "description": "Can two engineers work remotely on Fridays? Please confirm the policy."})
employee.post("/goals", {"title": "Ship the reporting module", "description": "Released to all customers with fewer than 5 open bugs.",
                         "due_date": (today + timedelta(days=45)).isoformat()})
g = manager.post("/goals", {"title": "Mentor two junior engineers", "employee_id": by["Sara"]["id"], "due_date": (today + timedelta(days=90)).isoformat()})
employee.call("PATCH", f"/goals/{g['id']}", json={"progress": 40})
manager.post("/goals", {"title": "Reduce the release cycle to two weeks", "due_date": (today + timedelta(days=60)).isoformat()})

# ---------------------------------------------------------------- assets, training, reviews, notices, tasks, hiring
assets = [owner.post("/assets", {"name": n, "category": c, "serial_number": s, "condition": k, "purchase_date": "2025-03-10"})
          for n, c, s, k in (("MacBook Pro 14", "Laptop", "C02XK1HZ", "good"), ("Dell Latitude 5440", "Laptop", "DL5440-2291", "good"),
                             ("iPhone 14", "Phone", "F2LXQ8A1", "good"), ("Dell 27 Monitor", "Monitor", "DM27-8842", "new"),
                             ("Access card 0142", "Access card", "AC-0142", "good"))]
owner.post(f"/assets/{assets[0]['id']}/assign", {"employee_id": by["Sara"]["id"], "assigned_on": (today - timedelta(days=200)).isoformat()})
owner.post(f"/assets/{assets[4]['id']}/assign", {"employee_id": by["Sara"]["id"], "assigned_on": (today - timedelta(days=200)).isoformat()})
owner.post(f"/assets/{assets[1]['id']}/assign", {"employee_id": by["Imran"]["id"], "assigned_on": (today - timedelta(days=300)).isoformat()})
owner.post(f"/assets/{assets[2]['id']}/assign", {"employee_id": by["Zain"]["id"], "assigned_on": (today - timedelta(days=120)).isoformat()})
c = owner.post("/courses", {"title": "Information security basics", "category": "Compliance", "mandatory": True, "duration_hours": "1.5",
                            "description": "Passwords, phishing and handling customer data.", "url": "https://example.com/security-basics"})
owner.post(f"/courses/{c['id']}/assign", {"everyone": True, "due_date": (today + timedelta(days=21)).isoformat()})
c = owner.post("/courses", {"title": "Effective code reviews", "category": "Engineering", "duration_hours": "2",
                            "description": "Giving and receiving review feedback."})
owner.post(f"/courses/{c['id']}/assign", {"department_id": depts["Engineering"]})
mine = employee.get("/enrollments")
employee.call("PATCH", f"/enrollments/{mine[-1]['id']}", json={"status": "completed"})
cyc = owner.post("/review-cycles", {"name": f"Annual review {today.year}", "period_start": f"{today.year}-01-01", "period_end": f"{today.year}-12-31"})
owner.post(f"/review-cycles/{cyc['id']}/launch")
rv = employee.get("/reviews")[0]
employee.post(f"/reviews/{rv['id']}/self", {"rating": 4, "comment": "Led the reporting module and mentored two new joiners. I want to improve my estimates."})
owner.post("/notices", {"title": "Office closed on 25 December", "body": "The office is closed on Quaid-e-Azam Day. Payroll for December is processed on the 24th."})
owner.post("/notices", {"title": "New parking arrangement in Lahore", "body": "From Monday, staff parking moves to the basement of the adjacent building.",
                        "branch_id": branches["Lahore Office"]})
owner.post("/tasks", {"title": "Review the Q1 hiring plan", "assignee_id": by["Imran"]["id"], "priority": "high", "due_date": (today + timedelta(days=5)).isoformat()})
manager.post("/tasks", {"title": "Prepare the release notes", "assignee_id": by["Sara"]["id"], "due_date": (today + timedelta(days=2)).isoformat()})
employee.post("/tasks", {"title": "Renew my passport copy with HR", "due_date": (today + timedelta(days=10)).isoformat()})
job = owner.post("/recruitment/jobs", {"title": "Backend Engineer", "department_id": depts["Engineering"], "openings": 2,
                                       "description": "Design and run the services behind our product. Python and PostgreSQL experience needed."})
owner.post(f"/recruitment/jobs/{job['id']}/status", {"stage": "open"})
for name, mail, stage in (("Omar Sheikh", "omar.sheikh@example.com", "Interview"), ("Laila Aziz", "laila.aziz@example.com", "Screening"),
                          ("Hamza Butt", "hamza.butt@example.com", "Applied"), ("Sana Iqbal", "sana.iqbal@example.com", "Offer")):
    a = owner.post("/recruitment/applications", {"job_id": job["id"], "full_name": name, "email": mail})
    if stage != "Applied":
        owner.post(f"/recruitment/applications/{a['id']}/stage", {"stage": stage})

# ---------------------------------------------------------------- payroll: two finalized months and one waiting for approval
def month(back: int) -> tuple[date, date]:
    first = today.replace(day=1)
    for _ in range(back):
        first = (first - timedelta(days=1)).replace(day=1)
    return first, (first.replace(day=28) + timedelta(days=4)).replace(day=1) - timedelta(days=1)


for back in (3, 2):
    s, e = month(back)
    run = finance.post("/payroll/runs", {"period_start": s.isoformat(), "period_end": e.isoformat()})
    finance.post(f"/payroll/runs/{run['id']}/calculate")
    owner.post(f"/payroll/runs/{run['id']}/approve")
    owner.post(f"/payroll/runs/{run['id']}/finalize")
s, e = month(1)
run = finance.post("/payroll/runs", {"period_start": s.isoformat(), "period_end": e.isoformat()})
finance.post(f"/payroll/runs/{run['id']}/calculate")

print(f"\nDemo organization ready: {args.org} ({len(emps) + 1} employees). Sign in at http://localhost:5173/login\n")
for label, mail, pw in (("Owner (full admin)", OWNER_EMAIL, OWNER_PW), ("Manager (Engineering)", MANAGER_EMAIL, MANAGER_PW),
                        ("Employee", EMPLOYEE_EMAIL, EMPLOYEE_PW), ("Finance manager", FINANCE_EMAIL, FINANCE_PW)):
    print(f"  {label:<24} {mail:<40} {pw}")
print(f"\nPayroll for {s:%B %Y} is calculated and waiting for the owner to approve it.")
if args.accounts_file:
    accounts = [
        {"key": "admin", "label": "Administrator", "name": "Nadia Rahman", "email": OWNER_EMAIL, "password": OWNER_PW},
        {"key": "employee", "label": "Employee", "name": "Sara Khan", "email": EMPLOYEE_EMAIL, "password": EMPLOYEE_PW},
        {"key": "manager", "label": "Team manager", "name": "Imran", "email": MANAGER_EMAIL, "password": MANAGER_PW},
        {"key": "finance", "label": "Finance", "name": "Finance manager", "email": FINANCE_EMAIL, "password": FINANCE_PW},
    ]
    target = Path(args.accounts_file)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(json.dumps({"organization": args.org, "accounts": accounts}, indent=2), encoding="utf-8")
