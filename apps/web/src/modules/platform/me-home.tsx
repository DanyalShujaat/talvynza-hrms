import { CalendarDays, ChevronRight, Clock, LifeBuoy, ListChecks, Megaphone, PartyPopper, ReceiptText } from 'lucide-react'
import { Link } from 'react-router-dom'
import { Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from '@/components/ui/card'
import { Avatar, Progress } from '@/components/ui/extras'
import { money, today as localToday, useGet } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { CheckInCard, greeting, type Stats } from '@/modules/platform/dashboard'

interface Task { id: string; title: string; due_date: string | null; status: string; priority: string; overdue: boolean }
interface NoticeRow { id: string; title: string; body: string; published_at: string }
interface Slip { entry_id: string; period_start: string; period_end: string; net: string; currency: string }
interface Holiday { id: string; holiday_date: string; name: string }

const ACTIONS = [
  { to: '/me/leave?apply=1', permission: 'leave.apply', label: 'Apply for leave', icon: CalendarDays, tone: 'bg-primary-soft text-primary' },
  { to: '/me/attendance?tab=adjust', permission: 'attendance.read_own', label: 'Request a time correction', icon: Clock, tone: 'bg-info-soft text-cyan' },
  { to: '/me/expenses?new=1', permission: 'expenses.submit', label: 'Claim an expense', icon: ReceiptText, tone: 'bg-success-soft text-success' },
  { to: '/me/helpdesk?new=1', permission: 'helpdesk.submit', label: 'Ask HR', icon: LifeBuoy, tone: 'bg-warning-soft text-warning' },
]

export function MyHomePage() {
  const { data: me } = useMe()
  const stats = useGet<Stats>('/dashboard/stats')
  const tasks = useGet<Task[]>('/tasks', { scope: 'mine' })
  const notices = useGet<NoticeRow[]>('/notices')
  const slips = useGet<Slip[]>('/payslips', undefined, !!me?.permissions.includes('payslip.read_own'))
  const holidays = useGet<Holiday[]>('/holidays', { year: new Date().getFullYear() })
  if (!me?.employee) return null
  const permissions = new Set(me.permissions)
  const actions = ACTIONS.filter(action => permissions.has(action.permission))
  const emp = me.employee
  const today = localToday()
  const openTasks = (tasks.data ?? []).filter((t) => t.status !== 'done').slice(0, 5)
  const upcoming = (holidays.data ?? []).filter((h) => h.holiday_date >= today).slice(0, 3)
  const balances = stats.data?.me?.balances ?? []
  const slip = slips.data?.[0]

  return (
    <div className="space-y-6">
      {stats.isError && <Card><ErrorState message="Your workspace could not be refreshed." onRetry={() => stats.refetch()} /></Card>}
      <Card><CardBody className="flex flex-wrap items-center gap-4">
        <Avatar name={emp.full_name} size="xl" />
        <div className="min-w-0 flex-1">
          <h1 className="text-[22px] font-bold tracking-tight">{greeting()}, {emp.full_name.split(' ')[0]}</h1>
          <p className="mt-0.5 text-sm text-muted">{[emp.designation, emp.department].filter(Boolean).join(' · ') || me.active_organization?.name} · Employee ID {emp.employee_code}</p>
        </div>
        {permissions.has('employees.read_own') && <Link to="/me/profile" className="inline-flex items-center gap-1 text-sm font-medium text-primary hover:underline">View profile<ChevronRight className="h-4 w-4" /></Link>}
      </CardBody></Card>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6">
          {permissions.has('attendance.read_own') && <CheckInCard />}
          {slip && (
            <Card><CardHeader><CardTitle>Latest payslip</CardTitle><Link to="/me/payslips" className="text-[13px] font-medium text-primary hover:underline">All payslips</Link></CardHeader>
              <CardBody><p className="text-xs text-muted">{formatDate(slip.period_start, { month: 'long', year: 'numeric' })}</p><p className="font-display text-2xl font-bold">{money(slip.net, slip.currency)}</p><p className="text-xs text-muted">Net pay</p></CardBody></Card>)}
        </div>

        <div className="space-y-6 lg:col-span-2">
          {!!actions.length && <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
            {actions.map((a) => (
              <Link key={a.to} to={a.to} className="group rounded-xl border border-border bg-surface p-4 shadow-card transition-colors hover:border-primary/40">
                <span className={cn('mb-3 flex h-9 w-9 items-center justify-center rounded-lg', a.tone)}><a.icon className="h-[18px] w-[18px]" aria-hidden /></span>
                <span className="text-sm font-semibold group-hover:text-primary">{a.label}</span>
              </Link>))}
          </div>}

          <Card>
            <CardHeader><CardTitle>Leave balance</CardTitle>{permissions.has('leave.apply') && <Link to="/me/leave" className="text-[13px] font-medium text-primary hover:underline">Requests and history</Link>}</CardHeader>
            <CardBody>
              {stats.isLoading ? <Skeleton className="h-20 w-full" /> : balances.length === 0 ? <p className="text-sm text-muted">No leave has been granted for this year yet. HR grants entitlements at the start of the leave year.</p> : (
                <div className="grid gap-5 sm:grid-cols-3">
                  {balances.map((b) => (
                    <div key={b.leave_type_id}>
                      <div className="flex items-baseline justify-between"><span className="text-sm text-muted">{b.name}</span><span className="font-display text-xl font-bold">{Number(b.available)}</span></div>
                      <Progress className="mt-2" tone="success" value={Number(b.entitled) > 0 ? (Number(b.available) / Number(b.entitled)) * 100 : 0} />
                      <p className="mt-1.5 text-xs text-muted">{Number(b.used)} used{Number(b.reserved) > 0 && `, ${Number(b.reserved)} pending`} of {Number(b.entitled)}</p>
                    </div>))}
                </div>)}
            </CardBody>
          </Card>

          <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
            <Card>
              <CardHeader><CardTitle>My tasks</CardTitle><Link to="/me/tasks" className="text-[13px] font-medium text-primary hover:underline">Open board</Link></CardHeader>
              {tasks.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : openTasks.length === 0 ? <EmptyState title="No open tasks" icon={ListChecks} /> : (
                <ul className="divide-y divide-border">{openTasks.map((t) => (
                  <li key={t.id} className="flex items-center gap-3 px-5 py-2.5 text-sm">
                    <span className={cn('h-2 w-2 shrink-0 rounded-full', t.priority === 'high' ? 'bg-danger' : t.status === 'in_progress' ? 'bg-primary' : 'bg-border-strong')} aria-hidden />
                    <Link to={`/me/tasks?record=${t.id}`} className="min-w-0 flex-1 truncate font-medium text-primary hover:underline">{t.title}</Link>
                    {t.due_date && <span className={cn('shrink-0 text-xs', t.overdue ? 'font-semibold text-danger' : 'text-muted')}>{formatDate(t.due_date, { day: 'numeric', month: 'short' })}</span>}
                  </li>))}</ul>)}
            </Card>
            <Card>
              <CardHeader><CardTitle>Notices</CardTitle><Link to="/me/notices" className="text-[13px] font-medium text-primary hover:underline">All notices</Link></CardHeader>
              {notices.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : !notices.data?.length ? <EmptyState title="No notices" icon={Megaphone} /> : (
                <ul className="divide-y divide-border">{notices.data.slice(0, 4).map((n) => (
                  <li key={n.id} className="px-5 py-2.5"><p className="truncate text-sm font-medium">{n.title}</p><p className="truncate text-xs text-muted">{formatDate(n.published_at, { dateStyle: 'medium' })} · {n.body}</p></li>))}</ul>)}
            </Card>
          </div>

          {upcoming.length > 0 && (
            <Card><CardHeader><CardTitle>Upcoming holidays</CardTitle></CardHeader>
              <ul className="divide-y divide-border">{upcoming.map((h) => (
                <li key={h.id} className="flex items-center gap-3 px-5 py-2.5 text-sm"><PartyPopper className="h-4 w-4 text-warning" aria-hidden /><span className="flex-1 font-medium">{h.name}</span><span className="text-muted">{formatDate(h.holiday_date, { weekday: 'short', day: 'numeric', month: 'long' })}</span></li>))}</ul></Card>)}
        </div>
      </div>
    </div>
  )
}
