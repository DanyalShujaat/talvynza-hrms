/** API types shared between the web app and any TypeScript client. Mirrors apps/api schemas. */
export interface Identity {
  id: string
  email: string
  full_name: string
  mfa_enabled: boolean
  is_platform_admin: boolean
  email_verified: boolean
}
export interface OrgSummary {
  tenant_id: string
  name: string
  slug: string
  status: string
}
export interface ActiveOrg {
  id: string
  name: string
  slug: string
  country: string
  currency: string
  timezone: string
  status: string
  plan_code: string
  trial_ends_at: string | null
  enabled_modules: string[]
}
export interface MyEmployee {
  id: string
  employee_code: string
  full_name: string
  designation: string | null
  department: string | null
  direct_reports: number
}
export interface Me {
  identity: Identity
  organizations: OrgSummary[]
  active_organization: ActiveOrg | null
  roles: string[]
  permissions: string[]
  employee: MyEmployee | null
}
export interface Member {
  membership_id: string
  identity_id: string
  email: string
  full_name: string
  status: string
  roles: string[]
}
export interface Role {
  id: string
  key: string
  name: string
  description: string | null
  is_system: boolean
  permissions: string[]
}
export interface PermissionDef {
  code: string
  module: string
  description: string
  is_sensitive: boolean
}
export interface AuditEntry {
  id: string
  actor_identity_id: string | null
  action: string
  entity_type: string
  entity_id: string | null
  details: Record<string, unknown>
  created_at: string
}
export interface Page<T> {
  items: T[]
  total: number
  page: number
  page_size: number
}
export interface SessionInfo {
  id: string
  created_at: string
  last_seen_at: string
  ip: string | null
  user_agent: string | null
  current: boolean
}
export interface OrgDetail extends ActiveOrg {
  legal_name: string | null
  employee_capacity: number
  expected_employee_count: number | null
  onboarding_state: Record<string, unknown>
}
