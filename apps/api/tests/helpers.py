from datetime import date, timedelta

from tests.conftest import PASSWORD, last_token

API = "/api/v1"


def mkemp(api, **kw):
    payload = {"first_name": "Ali", "last_name": "Khan", "joining_date": "2026-01-05", **kw}
    r = api.post(f"{API}/employees", payload)
    assert r.status_code == 201, r.text
    return r.json()


def join(owner, new_client, email, role_key, name="Invited Person"):
    """Invite `email` into the owner's org with a role; the invitee registers, accepts and switches in."""
    r = owner.post(f"{API}/invitations", {"email": email, "role_key": role_key})
    assert r.status_code == 201, r.text
    token = last_token("accept-invitation")
    user = new_client()
    user.post(f"{API}/auth/register", {"email": email, "password": PASSWORD, "full_name": name,
                                      "organization_name": f"{name} Own Org", "country": "PK", "currency": "PKR",
                                      "timezone": "Asia/Karachi"})
    user.post(f"{API}/auth/verify-email", {"token": last_token("verify-email")})
    assert user.post(f"{API}/auth/login", {"email": email, "password": PASSWORD}).status_code == 200
    r = user.post(f"{API}/invitations/accept", {"token": token})
    assert r.status_code == 200, r.text
    assert user.post(f"{API}/me/switch-organization", {"tenant_id": r.json()["tenant_id"]}).status_code == 200
    return user


def next_weekday(start: date, weekday: int = 0) -> date:
    return start + timedelta(days=(weekday - start.weekday()) % 7)


def my_employee_id(api):
    r = api.get(f"{API}/me/employee")
    assert r.status_code == 200, r.text
    return r.json()["id"]


def portal_join(owner, new_client, employee_id, role_key="employee", name="Portal User"):
    """HR invites an employee to the portal; they set a password from the emailed link and are signed in."""
    r = owner.post(f"{API}/employees/{employee_id}/invite", {"role_key": role_key})
    assert r.status_code == 201, r.text
    user = new_client()
    r = user.post(f"{API}/auth/join", {"token": last_token("accept-invitation"), "full_name": name, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return user


def team(signup, new_client):
    """Owner plus a worker who reports to a boss, all with logins. Returns (owner, worker, boss, worker_emp, boss_emp)."""
    owner = signup()
    boss_emp = mkemp(owner, first_name="Boss", last_name="Lead", email="boss@x.test")
    worker_emp = mkemp(owner, first_name="Worker", last_name="Bee", email="worker@x.test", manager_id=boss_emp["id"])
    boss = portal_join(owner, new_client, boss_emp["id"], "reporting_manager", name="Boss Lead")
    worker = portal_join(owner, new_client, worker_emp["id"], name="Worker Bee")
    return owner, worker, boss, worker_emp, boss_emp
