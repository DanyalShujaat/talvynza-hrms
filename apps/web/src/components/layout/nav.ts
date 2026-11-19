import type { LucideIcon } from 'lucide-react'
import {
  BarChart3, BookOpen, Boxes, BriefcaseBusiness, Building, Building2, CalendarClock, CalendarDays, CircleUserRound, Clock,
  DoorOpen, GraduationCap, HandCoins, History, Home, KeyRound, Laptop, LayoutDashboard, LifeBuoy, ListChecks, Megaphone, Network,
  Receipt, ReceiptText, ScrollText, ShieldCheck, Target, UserCog, Users, Wallet, Inbox,
} from 'lucide-react'

export interface NavItem { to: string; label: string; icon: LucideIcon; any?: string[]; end?: boolean }
export interface NavGroup { label: string; items: NavItem[] }

/** The employee's own side of the product. Everyone with an employee record sees this. */
export const MY_SPACE: NavGroup[] = [
  { label: 'My work', items: [
    { to: '/me', label: 'Home', icon: Home, end: true },
    { to: '/me/requests', label: 'My requests', icon: Inbox },
    { to: '/me/attendance', label: 'Attendance', icon: Clock },
    { to: '/me/leave', label: 'Leave', icon: CalendarDays },
    { to: '/me/tasks', label: 'Tasks', icon: ListChecks },
    { to: '/me/notices', label: 'Notices', icon: Megaphone },
  ] },
  { label: 'Pay and benefits', items: [
    { to: '/me/payslips', label: 'Payslips', icon: Receipt },
    { to: '/me/expenses', label: 'Expenses', icon: ReceiptText },
    { to: '/me/loans', label: 'Loans and advances', icon: HandCoins },
  ] },
  { label: 'Growth', items: [
    { to: '/me/performance', label: 'Goals and reviews', icon: Target },
    { to: '/me/training', label: 'Training', icon: GraduationCap },
  ] },
  { label: 'My account', items: [
    { to: '/me/profile', label: 'Profile', icon: CircleUserRound },
    { to: '/me/assets', label: 'Assets', icon: Laptop },
    { to: '/me/helpdesk', label: 'Help desk', icon: LifeBuoy },
    { to: '/me/security', label: 'Security', icon: ShieldCheck },
  ] },
]

/** Management side. Each item is shown only to people who hold one of its permissions. */
export const ADMIN: NavGroup[] = [
  { label: 'Overview', items: [
    { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
    { to: '/inbox', label: 'Request inbox', icon: Inbox, any: ['leave.approve', 'attendance.approve', 'expenses.approve', 'expenses.finance_approve', 'loans.manage', 'helpdesk.manage'] },
    { to: '/reports', label: 'Reports', icon: BarChart3, any: ['reports.view'] },
  ] },
  { label: 'People', items: [
    { to: '/employees', label: 'Employees', icon: Users, any: ['employees.read', 'employees.read_team'] },
    { to: '/org-chart', label: 'Org chart', icon: Network, any: ['employees.read', 'employees.read_team'] },
    { to: '/departments', label: 'Departments', icon: Boxes, any: ['org.manage'] },
    { to: '/branches', label: 'Branches', icon: Building, any: ['org.manage'] },
    { to: '/hire', label: 'Recruitment', icon: BriefcaseBusiness, any: ['recruitment.read_assigned', 'recruitment.manage'] },
    { to: '/offboarding', label: 'Offboarding', icon: DoorOpen, any: ['employees.manage'] },
  ] },
  { label: 'Time', items: [
    { to: '/attendance', label: 'Attendance', icon: Clock, any: ['attendance.approve', 'attendance.manage'] },
    { to: '/shifts', label: 'Shifts', icon: CalendarClock, any: ['attendance.manage'] },
    { to: '/leave', label: 'Leave', icon: CalendarDays, any: ['leave.approve', 'leave.manage'] },
  ] },
  { label: 'Pay', items: [
    { to: '/payroll', label: 'Payroll', icon: Wallet, any: ['payroll.read', 'salary.read'] },
    { to: '/expenses', label: 'Expenses', icon: ReceiptText, any: ['expenses.approve', 'expenses.finance_approve'] },
    { to: '/loans', label: 'Loans', icon: HandCoins, any: ['loans.manage'] },
  ] },
  { label: 'Workplace', items: [
    { to: '/performance', label: 'Performance', icon: Target, any: ['performance.review_team', 'performance.manage'] },
    { to: '/training', label: 'Training', icon: BookOpen, any: ['training.manage'] },
    { to: '/tasks', label: 'Tasks', icon: ListChecks, any: ['tasks.manage'] },
    { to: '/assets', label: 'Assets', icon: Laptop, any: ['assets.manage'] },
    { to: '/helpdesk', label: 'Help desk', icon: LifeBuoy, any: ['helpdesk.manage'] },
    { to: '/notices', label: 'Notices', icon: Megaphone, any: ['notices.manage'] },
  ] },
  { label: 'Settings', items: [
    { to: '/policies', label: 'HR policies', icon: ScrollText, any: ['attendance.manage', 'leave.manage'] },
    { to: '/people/members', label: 'Users', icon: UserCog, any: ['members.read'] },
    { to: '/access/roles', label: 'Roles', icon: KeyRound, any: ['roles.manage'] },
    { to: '/audit', label: 'Audit log', icon: History, any: ['audit.read'] },
    { to: '/settings/organization', label: 'Organization', icon: Building2, any: ['org.manage'] },
  ] },
]

export const visibleGroups = (groups: NavGroup[], perms: Set<string>): NavGroup[] =>
  groups
    .map((g) => ({ ...g, items: g.items.filter((i) => !i.any || i.any.some((p) => perms.has(p))) }))
    .filter((g) => g.items.length > 0)

/** True when the person has anything to do on the management side beyond the dashboard. */
export const hasAdminSide = (perms: Set<string>) =>
  ADMIN.some((g) => g.items.some((i) => i.any?.some((p) => perms.has(p))))

export const isMySpace = (pathname: string) => pathname === '/me' || pathname.startsWith('/me/')

const selfPermissions: Record<string, string[]> = {
  '/me/attendance': ['attendance.read_own'], '/me/leave': ['leave.apply'], '/me/payslips': ['payslip.read_own'],
  '/me/expenses': ['expenses.submit'], '/me/loans': ['loans.request'], '/me/performance': ['performance.read_own'],
  '/me/profile': ['employees.read_own'], '/me/helpdesk': ['helpdesk.submit'],
}
for (const group of MY_SPACE) for (const item of group.items) item.any = selfPermissions[item.to]

/** Mirrors navigation for direct URLs; server authorization remains authoritative. */
export function allowedPath(path: string, perms: Set<string>) {
  if (path === '/settings/security' || path === '/organizations/new') return true
  const items = (isMySpace(path) ? MY_SPACE : ADMIN).flatMap(g => g.items)
  const item = [...items].sort((a, b) => b.to.length - a.to.length).find(i => path === i.to || (i.to !== '/' && path.startsWith(i.to + '/')))
  if (!item) return true
  if (!isMySpace(path) && !hasAdminSide(perms)) return false
  return !item.any || item.any.some(p => perms.has(p))
}
