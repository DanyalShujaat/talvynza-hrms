"""Security-critical tests: tenant isolation, privilege escalation, BOLA, audit immutability."""
import uuid

import pytest
from sqlalchemy import select, update

from app.db.base import utcnow
from app.db.tenant_scope import ALL_TENANTS, TenantViolation, set_tenant, tenant_scope
from app.modules.tenancy.models import AuditLog, Role, Tenant
from tests.conftest import PASSWORD, last_token


def _tenant_id(api):
    return api.get("/api/v1/me").json()["active_organization"]["id"]


# ------------------------------------------------------------------ API-level isolation
def test_user_cannot_see_other_tenants_data(signup):
    a = signup("a@a.test", "Org A")
    b = signup("b@b.test", "Org B")
    assert {m["email"] for m in a.get("/api/v1/members").json()["items"]} == {"a@a.test"}
    assert {m["email"] for m in b.get("/api/v1/members").json()["items"]} == {"b@b.test"}
    roles_a = {r["id"] for r in a.get("/api/v1/roles").json()}
    roles_b = {r["id"] for r in b.get("/api/v1/roles").json()}
    assert roles_a and roles_b and roles_a.isdisjoint(roles_b)
    # audit logs are per-tenant too
    assert all(entry["entity_id"] != _tenant_id(a) for entry in b.get("/api/v1/audit-logs").json()["items"])


def test_cannot_switch_into_foreign_tenant(signup):
    a = signup("a@a.test", "Org A")
    b = signup("b@b.test", "Org B")
    r = a.post("/api/v1/me/switch-organization", {"tenant_id": _tenant_id(b)})
    assert r.status_code == 404  # indistinguishable from a non-existent tenant
    r = a.post("/api/v1/me/switch-organization", {"tenant_id": str(uuid.uuid4())})
    assert r.status_code == 404
    assert a.get("/api/v1/me").json()["active_organization"]["name"] == "Org A"


def test_foreign_role_and_membership_ids_are_not_found(signup):
    """Broken object-level authorization: guessing another tenant's object ids must not work."""
    a = signup("a@a.test", "Org A")
    b = signup("b@b.test", "Org B")
    foreign_role = b.get("/api/v1/roles").json()[0]["id"]
    foreign_member = b.get("/api/v1/members").json()["items"][0]["membership_id"]
    assert a.put(f"/api/v1/roles/{foreign_role}/permissions", {"permissions": []}).status_code == 404
    assert a.put(f"/api/v1/members/{foreign_member}/roles", {"role_keys": ["employee"]}).status_code == 404


def test_tenant_id_from_client_is_ignored(signup):
    a = signup("a@a.test", "Org A")
    b = signup("b@b.test", "Org B")
    r = a.get("/api/v1/members", headers={"X-Tenant-ID": _tenant_id(b)}, params={"tenant_id": _tenant_id(b)})
    assert {m["email"] for m in r.json()["items"]} == {"a@a.test"}


def test_multi_org_user_can_switch_between_authorized_orgs(signup):
    a = signup("multi@x.test", "First Org")
    created = a.post("/api/v1/organizations", {"name": "Second Org", "country": "GB", "currency": "GBP",
                                              "timezone": "Europe/London"})
    assert created.status_code == 201
    me = a.get("/api/v1/me").json()
    assert len(me["organizations"]) == 2
    second = created.json()["id"]
    assert a.post("/api/v1/me/switch-organization", {"tenant_id": second}).status_code == 200
    me = a.get("/api/v1/me").json()
    assert me["active_organization"]["name"] == "Second Org" and me["active_organization"]["currency"] == "GBP"
    assert {m["email"] for m in a.get("/api/v1/members").json()["items"]} == {"multi@x.test"}


def test_suspended_tenant_is_locked_out(signup, db):
    a = signup("s@s.test", "Suspend Me")
    t = db.scalar(select(Tenant))
    t.status = "suspended"
    db.commit()
    r = a.get("/api/v1/members")
    assert r.status_code == 403 and r.json()["error"]["code"] == "tenant_suspended"


# ------------------------------------------------------------------ DB-layer isolation
def _two_tenants(signup):
    a = signup("a@a.test", "Org A")
    b = signup("b@b.test", "Org B")
    return _tenant_id(a), _tenant_id(b)


def test_db_layer_filters_queries_by_scope(signup, db):
    ta, tb = map(uuid.UUID, _two_tenants(signup))
    set_tenant(db, ta)
    roles = db.scalars(select(Role)).all()
    assert roles and {r.tenant_id for r in roles} == {ta}
    assert db.scalar(select(Role).where(Role.tenant_id == tb)) is None  # explicit foreign filter still blocked
    set_tenant(db, tb)
    assert {r.tenant_id for r in db.scalars(select(Role))} == {tb}


def test_db_layer_fails_closed_without_scope(signup, db):
    _two_tenants(signup)
    assert db.scalars(select(Role)).all() == []
    assert db.scalars(select(AuditLog)).all() == []


def test_db_layer_system_scope_sees_everything(signup, db):
    ta, tb = map(uuid.UUID, _two_tenants(signup))
    with tenant_scope(db, ALL_TENANTS):
        assert {r.tenant_id for r in db.scalars(select(Role))} == {ta, tb}


def test_db_layer_blocks_cross_tenant_writes(signup, db):
    ta, tb = map(uuid.UUID, _two_tenants(signup))
    set_tenant(db, ta)
    db.add(AuditLog(tenant_id=tb, action="x", entity_type="x", created_at=utcnow()))
    with pytest.raises(TenantViolation):
        db.flush()
    db.rollback()
    set_tenant(db, None)
    db.add(AuditLog(tenant_id=ta, action="x", entity_type="x", created_at=utcnow()))
    with pytest.raises(TenantViolation):
        db.flush()


def test_db_layer_scoped_bulk_update_cannot_touch_other_tenant(signup, db):
    ta, tb = map(uuid.UUID, _two_tenants(signup))
    set_tenant(db, ta)
    db.execute(update(Role).values(description="pwned"))
    db.commit()
    with tenant_scope(db, ALL_TENANTS):
        assert {r.description == "pwned" for r in db.scalars(select(Role).where(Role.tenant_id == ta))} == {True}
        assert all(r.description != "pwned" for r in db.scalars(select(Role).where(Role.tenant_id == tb)))


def test_tenant_id_is_immutable(signup, db):
    ta, tb = map(uuid.UUID, _two_tenants(signup))
    set_tenant(db, ta)
    role = db.scalars(select(Role)).first()
    role.tenant_id = tb
    with pytest.raises(TenantViolation):
        db.flush()


def test_audit_log_is_append_only(signup, db):
    ta, _ = map(uuid.UUID, _two_tenants(signup))
    set_tenant(db, ta)
    row = db.scalars(select(AuditLog)).first()
    row.action = "tampered"
    with pytest.raises(PermissionError):
        db.flush()
    db.rollback()
    db.delete(db.scalars(select(AuditLog)).first())
    with pytest.raises(PermissionError):
        db.flush()


# ------------------------------------------------------------------ permissions & escalation
def _invite_and_join(owner, new_client, email, role_key, org_name_for_user="Their Own Org"):
    r = owner.post("/api/v1/invitations", {"email": email, "role_key": role_key})
    assert r.status_code == 201, r.text
    token = last_token("accept-invitation")
    user = new_client()
    user.post("/api/v1/auth/register", {"email": email, "password": PASSWORD, "full_name": "Invited Person",
                                       "organization_name": org_name_for_user, "country": "PK", "currency": "PKR",
                                       "timezone": "Asia/Karachi"})
    user.post("/api/v1/auth/verify-email", {"token": last_token("verify-email")})
    user.post("/api/v1/auth/login", {"email": email, "password": PASSWORD})
    r = user.post("/api/v1/invitations/accept", {"token": token})
    assert r.status_code == 200, r.text
    assert user.post("/api/v1/me/switch-organization", {"tenant_id": r.json()["tenant_id"]}).status_code == 200
    return user


def test_employee_cannot_access_admin_endpoints(signup, new_client):
    owner = signup("o@o.test", "Org O")
    emp = _invite_and_join(owner, new_client, "emp@o.test", "employee")
    assert emp.get("/api/v1/me").json()["roles"] == ["employee"]
    for url in ("/api/v1/audit-logs", "/api/v1/members", "/api/v1/permissions"):
        r = emp.get(url)
        assert r.status_code == 403 and r.json()["error"]["code"] == "permission_denied", url
    assert emp.patch("/api/v1/organization", {"name": "Hacked"}).status_code == 403
    assert emp.post("/api/v1/invitations", {"email": "x@o.test", "role_key": "employee"}).status_code == 403


def test_hr_admin_cannot_escalate_to_owner(signup, new_client):
    owner = signup("o@o.test", "Org O")
    hr = _invite_and_join(owner, new_client, "hr@o.test", "hr_admin")
    # cannot invite someone as owner, nor promote self
    assert hr.post("/api/v1/invitations", {"email": "x@o.test", "role_key": "owner"}).status_code == 403
    me_member = next(m for m in hr.get("/api/v1/members").json()["items"] if m["email"] == "hr@o.test")
    r = hr.put(f"/api/v1/members/{me_member['membership_id']}/roles", {"role_keys": ["owner"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "privilege_escalation"
    # HR admin has no roles.manage at all
    assert hr.post("/api/v1/roles", {"key": "sneaky", "name": "Sneaky", "permissions": []}).status_code == 403


def test_role_manager_cannot_grant_permissions_they_lack(signup, new_client):
    owner = signup("o@o.test", "Org O")
    assert owner.post("/api/v1/roles", {"key": "role_admin", "name": "Role Admin",
                                        "permissions": ["roles.manage", "members.read", "members.manage"]}).status_code == 201
    ra = _invite_and_join(owner, new_client, "ra@o.test", "role_admin")
    r = ra.post("/api/v1/roles", {"key": "sneaky", "name": "Sneaky", "permissions": ["payroll.approve"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "privilege_escalation"
    ok = ra.post("/api/v1/roles", {"key": "fine", "name": "Fine", "permissions": ["members.read"]})
    assert ok.status_code == 201
    # nor can they edit an existing custom role up beyond their own permissions
    r = ra.put(f"/api/v1/roles/{ok.json()['id']}/permissions", {"permissions": ["payroll.approve"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "privilege_escalation"
    # nor assign the owner role
    me = next(m for m in ra.get("/api/v1/members").json()["items"] if m["email"] == "ra@o.test")
    r = ra.put(f"/api/v1/members/{me['membership_id']}/roles", {"role_keys": ["owner"]})
    assert r.status_code == 403 and r.json()["error"]["code"] == "privilege_escalation"


def test_system_roles_are_immutable_and_custom_roles_work(signup):
    owner = signup()
    roles = {r["key"]: r for r in owner.get("/api/v1/roles").json()}
    assert owner.put(f"/api/v1/roles/{roles['employee']['id']}/permissions", {"permissions": []}).status_code == 403
    r = owner.post("/api/v1/roles", {"key": "ops_lead", "name": "Ops Lead",
                                     "permissions": ["employees.read_team", "leave.approve"]})
    assert r.status_code == 201
    rid = r.json()["id"]
    assert owner.put(f"/api/v1/roles/{rid}/permissions", {"permissions": ["nope.nope"]}).status_code == 422
    assert owner.post("/api/v1/roles", {"key": "ops_lead", "name": "Dup", "permissions": []}).status_code == 409


def test_cannot_remove_last_owner(signup):
    owner = signup()
    m = owner.get("/api/v1/members").json()["items"][0]
    r = owner.put(f"/api/v1/members/{m['membership_id']}/roles", {"role_keys": ["employee"]})
    assert r.status_code == 409 and r.json()["error"]["code"] == "last_owner"


def test_invitation_bound_to_email_and_single_use(signup, new_client):
    owner = signup("o@o.test", "Org O")
    owner.post("/api/v1/invitations", {"email": "target@o.test", "role_key": "employee"})
    token = last_token("accept-invitation")
    other = signup("other@z.test", "Z Org")
    assert other.post("/api/v1/invitations/accept", {"token": token}).status_code == 403  # wrong identity
    target = new_client()
    target.post("/api/v1/auth/register", {"email": "target@o.test", "password": PASSWORD, "full_name": "Target Person",
                                         "organization_name": "T Org", "country": "PK", "currency": "PKR",
                                         "timezone": "Asia/Karachi"})
    target.post("/api/v1/auth/verify-email", {"token": last_token("verify-email")})
    target.post("/api/v1/auth/login", {"email": "target@o.test", "password": PASSWORD})
    assert target.post("/api/v1/invitations/accept", {"token": token}).status_code == 200
    assert target.post("/api/v1/invitations/accept", {"token": token}).status_code == 404  # already used


def test_sensitive_actions_are_audited(signup):
    owner = signup()
    owner.patch("/api/v1/organization", {"name": "Acme Renamed"})
    owner.post("/api/v1/roles", {"key": "auditor_plus", "name": "Auditor+", "permissions": ["audit.read"]})
    actions = {entry["action"] for entry in owner.get("/api/v1/audit-logs").json()["items"]}
    assert {"tenant.created", "tenant.updated", "role.created"} <= actions
    filtered = owner.get("/api/v1/audit-logs", params={"action": "role.created"}).json()
    assert filtered["total"] == 1
