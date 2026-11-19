import { useQueryClient } from '@tanstack/react-query'
import { AlarmClock, ArrowRight, CalendarClock, CalendarDays, FileWarning, HandCoins, LifeBuoy, LogIn, LogOut, ReceiptText, UserCheck, UserPlus, UserX, Users, Wallet } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from '@/components/ui/card'
import { Progress, StatTile, StatusText } from '@/components/ui/extras'
import { hhmm, timeOf, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'

export interface Stats {
  organization: null | {
    employees: number; employee_limit: number; departments: number; designations: number; branches: number
    today: { present: number; late: number; absent: number; working_day: boolean }; late_last_7_days: number
    attendance_chart: { date: string; present: number; late: number; absent: number; working_day: boolean }[]
  }
  me: null | { employee_name: string; today_status: string; first_in: string | null; open_tasks: number; balances: { leave_type_id: string; name: string; entitled: string; used: string; reserved: string; available: string }[] }
  approvals: { leave: number; attendance: number; expenses: number; loans: number; tickets: number }
  alerts: { type: string; employee: string; date: string; employee_id: string }[]
}
interface Today { work_date: string; state: 'in' | 'out'; summary: { status: string; first_in: string | null; last_out: string | null; worked_minutes: number; late_minutes: number } }

export const greeting = () => { const h = new Date().getHours(); return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening' }

/** Check in and out. Used on the employee home and attendance pages. */
export function CheckInCard() {
  const qc = useQueryClient()
  const q = useGet<Today>('/attendance/today')
  const [now, setNow] = React.useState(new Date())
  React.useEffect(() => { const t = setInterval(() => setNow(new Date()), 30_000); return () => clearInterval(t) }, [])
  const done = () => qc.invalidateQueries({ predicate: (x) => ['/attendance', '/dashboard'].some((p) => String(x.queryKey[0]).startsWith(p)) })
  const checkIn = useSend('POST', '/attendance/check-in', { success: 'Checked in', onSuccess: done })
  const checkOut = useSend('POST', '/attendance/check-out', { success: 'Checked out', onSuccess: done })
  const d = q.data
  return (
    <Card className="overflow-hidden">
      <div className="brand-gradient px-5 py-4 text-white">
        <p className="text-xs font-medium uppercase tracking-wider opacity-85">{now.toLocaleDateString(undefined, { weekday: 'long', day: 'numeric', month: 'long' })}</p>
        <p className="font-display text-3xl font-extrabold tabular-nums">{now.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}</p>
      </div>
      <CardBody>
        {q.isError ? <p className="text-sm text-muted">Attendance is available once your account is linked to an employee record.</p>
          : !d ? <Skeleton className="h-24 w-full" /> : (
            <div className="space-y-4">
              <div className="flex items-center justify-between"><span className="text-sm text-muted">Today</span><StatusText status={d.summary.status} /></div>
              <dl className="grid grid-cols-3 gap-2 text-center">
                {[['Check in', timeOf(d.summary.first_in)], ['Check out', timeOf(d.summary.last_out)], ['Worked', hhmm(d.summary.worked_minutes)]].map(([k, v]) => (
                  <div key={k} className="rounded-lg bg-surface-2 px-2 py-2.5"><dt className="text-[11px] uppercase tracking-wide text-muted">{k}</dt><dd className="font-semibold tabular-nums">{v}</dd></div>))}
              </dl>
              {d.summary.late_minutes > 0 && <p className="text-xs font-medium text-warning">Late by {d.summary.late_minutes} minutes</p>}
              {d.state === 'out'
                ? <Button size="lg" className="w-full" onClick={() => checkIn.mutate(undefined as never)} loading={checkIn.isPending}><LogIn className="h-4 w-4" />Check in</Button>
                : <Button size="lg" variant="danger" className="w-full" onClick={() => checkOut.mutate(undefined as never)} loading={checkOut.isPending}><LogOut className="h-4 w-4" />Check out</Button>}
            </div>)}
      </CardBody>
    </Card>
  )
}

function Approvals({ a }: { a: Stats['approvals'] }) {
  const rows: [number, string, string, LucideIcon][] = [
    [a.leave, 'Leave requests', '/leave', CalendarDays], [a.attendance, 'Attendance corrections', '/attendance', CalendarClock],
    [a.expenses, 'Expense claims', '/expenses', ReceiptText], [a.loans, 'Loan requests', '/loans', HandCoins], [a.tickets, 'Open help desk tickets', '/helpdesk', LifeBuoy],
  ]
  const open = rows.filter(([n]) => n > 0)
  return (
    <Card>
      <CardHeader><CardTitle>Needs your attention</CardTitle><Link to="/inbox" className="text-xs font-semibold text-primary">Open inbox</Link></CardHeader>
      {open.length === 0 ? <EmptyState title="You are all caught up" description="Requests that need a decision appear here." icon={UserCheck} /> : (
        <ul className="divide-y divide-border">
          {open.map(([n, label, to, Icon]) => (
            <li key={to}><Link to={to} className="flex items-center gap-3 px-5 py-3 text-sm hover:bg-surface-2/60">
              <span className="flex h-8 w-8 items-center justify-center rounded-lg bg-warning-soft text-warning"><Icon className="h-4 w-4" aria-hidden /></span>
              <span className="flex-1 font-medium">{label}</span>
              <span className="rounded-full bg-warning-soft px-2 py-0.5 text-xs font-bold text-warning">{n}</span><ArrowRight className="h-4 w-4 text-subtle" aria-hidden />
            </Link></li>))}
        </ul>)}
    </Card>
  )
}

interface Headcount { by_department: { label: string; count: number }[]; total: number }

export function DashboardPage() {
  const { data: me } = useMe()
  const q = useGet<Stats>('/dashboard/stats')
  const perms = new Set(me?.permissions ?? [])
  const head = useGet<Headcount>('/reports/headcount', undefined, perms.has('reports.view'))
  const org = q.data?.organization
  if (!me?.active_organization) return null
  const first = me.identity.full_name.split(' ')[0]
  const chart = (org?.attendance_chart ?? []).map((c) => ({ ...c, day: new Date(c.date + 'T00:00:00').toLocaleDateString(undefined, { weekday: 'short', day: 'numeric' }) }))
  const maxDept = Math.max(1, ...(head.data?.by_department ?? []).map((d) => d.count))

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-[22px] font-bold tracking-tight">{greeting()}, {first}</h1>
          <p className="mt-1 text-sm text-muted">{me.active_organization.name} · {new Date().toLocaleDateString(undefined, { dateStyle: 'full' })}</p>
        </div>
        <div className="flex flex-wrap gap-2">
          {perms.has('employees.manage') && <Button asChild variant="outline"><Link to="/employees?tab=add"><UserPlus className="h-4 w-4" />Add employee</Link></Button>}
          {perms.has('payroll.process') && <Button asChild><Link to="/payroll"><Wallet className="h-4 w-4" />Run payroll</Link></Button>}
        </div>
      </div>

      {q.isError && <Card><ErrorState message="The dashboard could not be loaded." onRetry={() => q.refetch()} /></Card>}
      {q.isLoading && <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-24 w-full rounded-xl" />)}</div>}

      {org && (
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <StatTile icon={Users} label="Employees" value={org.employees} tone="primary" progress={(org.employees / org.employee_limit) * 100} hint={`${org.employee_limit - org.employees} seats left on your plan`} />
          <StatTile icon={UserCheck} label="Present today" value={org.today.present} tone="teal" hint={org.today.working_day ? `of ${org.employees} employees` : 'Today is not a working day'} />
          <StatTile icon={AlarmClock} label="Late today" value={org.today.late} tone="amber" hint={`${org.late_last_7_days} late arrivals in the last 7 days`} />
          <StatTile icon={UserX} label="Absent today" value={org.today.absent} tone="rose" hint={org.today.working_day ? 'No attendance and no approved leave' : 'Not counted on days off'} />
        </div>
      )}

      <div className="grid gap-6 xl:grid-cols-3">
        {org && (
          <Card className="xl:col-span-2">
            <CardHeader>
              <CardTitle>Attendance, last 7 days</CardTitle>
              <div className="flex items-center gap-4 text-xs text-muted">
                {[['Present', '#0b8f63'], ['Late', '#d99a1c'], ['Absent', '#d02b49']].map(([l, c]) => <span key={l} className="flex items-center gap-1.5"><i className="h-2 w-2 rounded-full" style={{ background: c }} />{l}</span>)}
              </div>
            </CardHeader>
            <CardBody>
              <div className="h-64" role="img" aria-label="Present, late and absent employees over the last seven days">
                <ResponsiveContainer width="100%" height="100%">
                  <AreaChart data={chart} margin={{ left: -18, right: 8, top: 8 }}>
                    <defs><linearGradient id="gp" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#0b8f63" stopOpacity={0.22} /><stop offset="100%" stopColor="#0b8f63" stopOpacity={0} /></linearGradient></defs>
                    <CartesianGrid vertical={false} stroke="var(--color-border)" />
                    <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: 'var(--color-muted)' }} />
                    <YAxis allowDecimals={false} tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: 'var(--color-muted)' }} />
                    <Tooltip contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 10, fontSize: 13 }} />
                    <Area type="monotone" dataKey="present" name="Present" stroke="#0b8f63" strokeWidth={2} fill="url(#gp)" />
                    <Area type="monotone" dataKey="late" name="Late" stroke="#d99a1c" strokeWidth={2} fill="none" />
                    <Area type="monotone" dataKey="absent" name="Absent" stroke="#d02b49" strokeWidth={2} fill="none" />
                  </AreaChart>
                </ResponsiveContainer>
              </div>
            </CardBody>
          </Card>
        )}
        <div className={cn('space-y-6', !org && 'xl:col-span-3 xl:grid xl:grid-cols-2 xl:gap-6 xl:space-y-0')}>
          {q.data && <Approvals a={q.data.approvals} />}
          {!!q.data?.alerts.length && (
            <Card>
              <CardHeader><CardTitle>Coming up in 30 days</CardTitle></CardHeader>
              <ul className="divide-y divide-border">
                {q.data.alerts.slice(0, 6).map((a, i) => (
                  <li key={i}><Link to={`/employees/${a.employee_id}`} className="flex items-center gap-3 px-5 py-3 text-sm hover:bg-surface-2/60">
                    <FileWarning className="h-4 w-4 shrink-0 text-warning" aria-hidden />
                    <span className="min-w-0 flex-1"><span className="block truncate font-medium">{a.employee}</span><span className="text-xs text-muted">{a.type === 'contract_expiry' ? 'Contract ends' : 'Probation ends'} {formatDate(a.date, { dateStyle: 'medium' })}</span></span>
                  </Link></li>))}
              </ul>
            </Card>)}
        </div>
      </div>

      {org && (
        <div className="grid gap-6 xl:grid-cols-3">
          <Card className="xl:col-span-2">
            <CardHeader><CardTitle>Headcount by department</CardTitle><Link to="/reports" className="text-[13px] font-medium text-primary hover:underline">All reports</Link></CardHeader>
            <CardBody className="space-y-3">
              {!head.data ? <Skeleton className="h-28 w-full" /> : head.data.by_department.length === 0 ? <p className="text-sm text-muted">No employees yet.</p>
                : head.data.by_department.slice(0, 7).map((d) => (
                  <div key={d.label} className="flex items-center gap-3 text-sm"><span className="w-40 truncate">{d.label}</span><Progress value={(d.count / maxDept) * 100} className="flex-1" /><span className="w-8 text-right font-semibold tabular-nums">{d.count}</span></div>))}
            </CardBody>
          </Card>
          <Card>
            <CardHeader><CardTitle>Organization</CardTitle></CardHeader>
            <ul className="divide-y divide-border text-sm">
              {[['Departments', org.departments, '/departments'], ['Designations', org.designations, '/departments'], ['Branches', org.branches, '/branches']].map(([l, n, to]) => (
                <li key={l as string}><Link to={to as string} className="flex items-center justify-between px-5 py-3 hover:bg-surface-2/60"><span className="text-muted">{l}</span><span className="font-display text-lg font-bold">{n}</span></Link></li>))}
            </ul>
          </Card>
        </div>
      )}
    </div>
  )
}
