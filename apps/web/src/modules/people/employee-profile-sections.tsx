import type { Member } from '@talvynza/shared-types'
import { CalendarDays, ShieldCheck } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Skeleton } from '@/components/ui/card'
import { ConfirmButton, DataTable, StatusText } from '@/components/ui/extras'
import { errorMessage } from '@/lib/api'
import { attendanceChannels, type AttendanceChannel } from '@/lib/attendance'
import { today, useGet, useSend } from '@/lib/hooks'
import { useRoles } from '@/lib/queries'
import { formatDate } from '@/lib/utils'
import { EditRolesDialog } from '@/modules/platform/access'
import { ApplyDialog, Requests, type Bal } from '@/modules/time/leave'

const EmployeeReport = React.lazy(() => import('@/modules/time/attendance').then(m => ({ default: m.EmployeeReport })))

export function ProfileFacts({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-1 overflow-hidden rounded-lg border border-border bg-border min-[460px]:grid-cols-2 xl:grid-cols-3 gap-px">
      {items.map(([label, value]) => (
        <div key={label} className="min-w-0 bg-surface px-4 py-3">
          <dt className="text-xs font-medium text-muted">{label}</dt>
          <dd className="mt-1 break-words text-sm font-semibold">{value ?? '-'}</dd>
        </div>
      ))}
    </dl>
  )
}

export function ProfileCard({ title, action, children }: { title: string; action?: React.ReactNode; children: React.ReactNode }) {
  return (
    <Card>
      <CardHeader><CardTitle>{title}</CardTitle>{action}</CardHeader>
      <CardBody>{children}</CardBody>
    </Card>
  )
}

interface AttendanceSettings {
  channels: Record<AttendanceChannel, boolean>
  location_required: boolean
  branch_id: string | null
  shift: string | null
  effective_from: string | null
  start: string | null
  end: string | null
  break_minutes: number | null
  grace_minutes: number | null
}

export function ProfileAttendance({ id, bioId, canSetPolicy, canSetAccess, canManagePremises }: { id: string; bioId: string | null; canSetPolicy: boolean; canSetAccess: boolean; canManagePremises: boolean }) {
  const q = useGet<AttendanceSettings>(`/attendance/employees/${id}/settings`)
  const settings = q.data
  const access = useSend<{ channel: AttendanceChannel; enabled: boolean; employee_ids: string[] }>('PATCH', '/attendance/access', {
    invalidate: ['/attendance'], success: 'Attendance access updated',
  })
  return (
    <div className="space-y-4">
      <ProfileCard title="Attendance settings" action={<div className="flex flex-wrap gap-2">
        {canSetPolicy && <Button asChild size="sm" variant="outline"><Link to="/policies">Attendance policy</Link></Button>}
        {canManagePremises && settings?.branch_id && <Button asChild size="sm" variant="outline"><Link to={`/branches?premises=${settings.branch_id}`}>Branch premises</Link></Button>}
      </div>}>
        {q.isPending ? <Skeleton className="h-24" /> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : settings && (
          <div className="space-y-4">
          <ul className="divide-y divide-border rounded-lg border border-border px-4">
            {(Object.keys(attendanceChannels) as AttendanceChannel[]).map(channel => {
              const enabled = settings.channels[channel]
              const label = attendanceChannels[channel].label
              const detail = channel === 'web' && settings.location_required ? 'Blocked by the assigned branch perimeter.'
                : channel === 'premises' && (!bioId || !settings.branch_id) ? 'Assign a branch and biometric ID to receive device punches.'
                  : attendanceChannels[channel].description
              return <li key={channel} className="flex flex-wrap items-center justify-between gap-2 py-3">
                <div><p className="text-sm font-semibold">{label} <Badge tone={enabled && channel === 'web' && settings.location_required ? 'warning' : enabled ? 'success' : 'neutral'}>
                  {enabled && channel === 'web' && settings.location_required ? 'Blocked by perimeter' : enabled ? 'Enabled' : 'Disabled'}
                </Badge></p>
                  <p className="mt-1 text-xs text-muted">{detail}</p></div>
                {canSetAccess && <ConfirmButton label={enabled ? 'Disable' : 'Enable'} title={`${enabled ? 'Disable' : 'Enable'} ${label.toLowerCase()}?`}
                  message={detail} variant="outline" loading={access.isPending}
                  onConfirm={() => access.mutate({ channel, enabled: !enabled, employee_ids: [id] })} />}
              </li>
            })}
          </ul>
          <ProfileFacts items={[
            ['Biometric ID', bioId],
            ['Mobile punch locations', settings.location_required ? 'Branch premises' : 'Anywhere'],
            ['Shift', settings.shift ?? (settings.start ? 'Organization default' : null)],
            ['Shift hours', settings.start && settings.end && `${settings.start}–${settings.end}`],
            ['Break', settings.break_minutes != null ? `${settings.break_minutes} min` : null],
            ['Grace period', settings.grace_minutes != null ? `${settings.grace_minutes} min` : null],
            ['Shift assigned from', settings.effective_from && formatDate(settings.effective_from)],
          ]} />
          </div>
        )}
      </ProfileCard>
      <React.Suspense fallback={<Skeleton className="h-40" />}>
        <EmployeeReport fixedEmployeeId={id} />
      </React.Suspense>
    </div>
  )
}

export function ProfileLeave({ id, scope, canApply, showRequests }: {
  id: string
  scope: 'mine' | 'team' | 'all'
  canApply: boolean
  showRequests: boolean
}) {
  const [year, setYear] = React.useState(Number(today().slice(0, 4)))
  const [applying, setApplying] = React.useState(false)
  const q = useGet<Bal[]>('/leave/balances', { employee_id: id, year })
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <CardTitle>Leave balance</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Button variant="outline" size="sm" disabled={year <= 2000} onClick={() => setYear(year - 1)} aria-label="Previous leave year">−</Button>
            <span aria-live="polite" className="min-w-10 text-center text-sm font-semibold tabular-nums">{year}</span>
            <Button variant="outline" size="sm" disabled={year >= Number(today().slice(0, 4))} onClick={() => setYear(year + 1)} aria-label="Next leave year">+</Button>
            {canApply && <Button size="sm" onClick={() => setApplying(true)}><CalendarDays className="h-4 w-4" />Apply for leave</Button>}
          </div>
        </CardHeader>
        <DataTable rows={q.data} query={q} rowKey={b => b.leave_type_id} empty="No leave types configured" cols={[
          { header: 'Leave type', cell: b => b.name },
          { header: 'Entitled', right: true, cell: b => Number(b.entitled) },
          { header: 'Used', right: true, cell: b => Number(b.used) },
          { header: 'Pending', right: true, cell: b => Number(b.reserved) },
          { header: 'Carried forward', right: true, cell: b => Number(b.carried_forward) },
          { header: 'Available', right: true, cell: b => <span className="font-semibold">{Number(b.available)}</span> },
        ]} />
      </Card>
      {showRequests && <section aria-label="Leave applications" className="space-y-2">
        <h2 className="font-semibold">Leave applications</h2>
        <Requests scope={scope} employeeId={id} />
      </section>}
      {applying && <ApplyDialog open={applying} onOpenChange={setApplying} employeeId={id} />}
    </div>
  )
}

export function ProfileAccount({ membershipId, canEdit, invite }: {
  membershipId: string | null
  canEdit: boolean
  invite: React.ReactNode
}) {
  const membership = useGet<{ items: Member[] }>('/members', { membership_id: membershipId ?? undefined }, !!membershipId)
  const roles = useRoles()
  if (!membershipId) return (
    <ProfileCard title="Account privileges" action={invite}>
      <EmptyState icon={ShieldCheck} title="No portal account linked" />
    </ProfileCard>
  )
  const member = membership.data?.items[0]
  return (
    <ProfileCard title="Account privileges" action={member && canEdit && <EditRolesDialog membershipId={membershipId} current={member.roles} name={member.full_name} />}>
      {membership.isPending || roles.isPending ? <Skeleton className="h-24" />
        : membership.isError || roles.isError ? <ErrorState message={errorMessage(membership.error ?? roles.error)} onRetry={() => { membership.refetch(); roles.refetch() }} />
          : !member ? <EmptyState icon={ShieldCheck} title="Portal account unavailable" />
            : <>
              <ProfileFacts items={[[ 'Login email', member.email ], ['Account status', <StatusText status={member.status} />]]} />
              <ul className="mt-4 divide-y divide-border">
                {member.roles.map(key => {
                  const role = roles.data?.find(r => r.key === key)
                  return <li key={key} className="flex items-center justify-between gap-3 py-3">
                    <div><p className="text-sm font-semibold">{role?.name ?? key}</p>{role?.description && <p className="text-xs text-muted">{role.description}</p>}</div>
                    {role && <Badge>{role.permissions.length} permissions</Badge>}
                  </li>
                })}
              </ul>
            </>}
    </ProfileCard>
  )
}

interface TaskSummary { id: string; title: string; due_date: string | null; status: string; priority: string }
interface GoalSummary { id: string; title: string; due_date: string | null; status: string; progress: number }
interface ReviewSummary { id: string; cycle: string | null; reviewer: string | null; status: string; manager_rating: number | null }

export function ProfileTasks({ id, scope }: { id: string; scope: 'mine' | 'team' }) {
  const q = useGet<TaskSummary[]>('/tasks', { scope, assignee_id: id })
  return (
    <Card>
      <CardHeader><CardTitle>Assigned tasks</CardTitle></CardHeader>
      <DataTable rows={q.data} query={q} rowKey={t => t.id} empty="No assigned tasks" cols={[
        { header: 'Task', cell: t => t.title },
        { header: 'Due', cell: t => t.due_date ? formatDate(t.due_date) : '-' },
        { header: 'Priority', cell: t => <span className="capitalize">{t.priority}</span> },
        { header: 'Status', cell: t => <StatusText status={t.status} /> },
      ]} />
    </Card>
  )
}

export function ProfilePerformance({ id, scope }: { id: string; scope: 'mine' | 'team' | 'all' }) {
  const params = { scope, employee_id: id }
  const goals = useGet<GoalSummary[]>('/goals', params)
  const reviews = useGet<ReviewSummary[]>('/reviews', params)
  return (
    <div className="space-y-4">
      <Card>
        <CardHeader><CardTitle>Goals</CardTitle></CardHeader>
        <DataTable rows={goals.data} query={goals} rowKey={g => g.id} empty="No performance goals" cols={[
          { header: 'Goal', cell: g => g.title },
          { header: 'Due', cell: g => g.due_date ? formatDate(g.due_date) : '-' },
          { header: 'Progress', cell: g => `${g.progress}%` },
          { header: 'Status', cell: g => <StatusText status={g.status} /> },
        ]} />
      </Card>
      <Card>
        <CardHeader><CardTitle>Reviews</CardTitle></CardHeader>
        <DataTable rows={reviews.data} query={reviews} rowKey={r => r.id} empty="No performance reviews" cols={[
          { header: 'Review cycle', cell: r => r.cycle ?? '-' },
          { header: 'Reviewer', cell: r => r.reviewer ?? '-' },
          { header: 'Rating', cell: r => r.manager_rating ?? '-' },
          { header: 'Status', cell: r => <StatusText status={r.status} /> },
        ]} />
      </Card>
    </div>
  )
}
