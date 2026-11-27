import { useRecordFocus, useViewQuery, useViewTab } from '@/lib/view-state'
import { CalendarDays, ChevronLeft, ChevronRight, Plus } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Card, CardBody, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, Person, Progress, StatusText, Tabs } from '@/components/ui/extras'
import { Checkbox, Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { today, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'

interface LType { id: string; name: string; allow_half_day: boolean; is_paid: boolean }
export interface Bal { leave_type_id: string; name: string; entitled: string; used: string; reserved: string; available: string; carried_forward: string }
interface Req { id: string; employee: string | null; employee_code: string | null; leave_type: string | null; start_date: string; end_date: string; half_day: boolean; days: string; reason: string | null; status: string; decision_note: string | null }

const range = (r: { start_date: string; end_date: string }) => {
  const o = { day: 'numeric', month: 'short', year: 'numeric' } as const
  return r.start_date === r.end_date ? formatDate(r.start_date, o) : `${formatDate(r.start_date, { day: 'numeric', month: 'short' })} to ${formatDate(r.end_date, o)}`
}
const days = (r: Req) => `${Number(r.days)} day${Number(r.days) === 1 ? '' : 's'}${r.half_day ? ' (half day)' : ''}`

export function ApplyDialog({ open, onOpenChange, employeeId }: { open: boolean; onOpenChange: (o: boolean) => void; employeeId?: string }) {
  const types = useGet<LType[]>('/leave/types')
  const balances = useGet<Bal[]>('/leave/balances', { employee_id: employeeId })
  const [f, setF] = React.useState({ leave_type_id: '', start_date: today(), end_date: today(), half_day: false, reason: '' })
  const type = types.data?.find((t) => t.id === f.leave_type_id)
  const bal = balances.data?.find((b) => b.leave_type_id === f.leave_type_id)
  const m = useSend<typeof f & { employee_id?: string }>('POST', '/leave/requests', { invalidate: ['/leave', '/dashboard'], success: 'Leave request submitted', onSuccess: () => { onOpenChange(false); setF({ ...f, reason: '' }) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Apply for leave" description="Weekends and public holidays inside the dates are not counted.">
        <div className="space-y-4">
          <Field id="l-t" label="Leave type" hint={bal ? `${Number(bal.available)} days available` : undefined}>{(a) => (
            <Select value={f.leave_type_id} onChange={(e) => setF({ ...f, leave_type_id: e.target.value })} {...a}><option value="">Select a leave type</option>{types.data?.map((t) => <option key={t.id} value={t.id}>{t.name}{t.is_paid ? '' : ' (unpaid)'}</option>)}</Select>)}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="l-s" label="From">{(a) => <Input type="date" value={f.start_date} onChange={(e) => setF({ ...f, start_date: e.target.value, end_date: f.half_day || e.target.value > f.end_date ? e.target.value : f.end_date })} {...a} />}</Field>
            <Field id="l-e" label="To">{(a) => <Input type="date" min={f.start_date} disabled={f.half_day} value={f.end_date} onChange={(e) => setF({ ...f, end_date: e.target.value })} {...a} />}</Field>
          </div>
          {type?.allow_half_day && <Checkbox label="Half day" checked={f.half_day} onChange={(e) => setF({ ...f, half_day: e.target.checked, end_date: e.target.checked ? f.start_date : f.end_date })} />}
          <Field id="l-r" label="Reason (optional)">{(a) => <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={!f.leave_type_id} onClick={() => m.mutate({ ...f, employee_id: employeeId })}>Submit request</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Balances() {
  const q = useGet<Bal[]>('/leave/balances')
  if (q.isLoading) return <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">{[0, 1, 2].map((i) => <Skeleton key={i} className="h-28 rounded-xl" />)}</div>
  const rows = (q.data ?? []).filter((b) => Number(b.entitled) > 0 || Number(b.used) > 0)
  if (!rows.length) return <Card className="mb-6"><CardBody className="text-sm text-muted">No leave has been granted for this year yet. HR grants entitlements at the start of the leave year.</CardBody></Card>
  return (
    <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      {rows.map((b) => (
        <Card key={b.leave_type_id}><CardBody className="py-4">
          <p className="text-[13px] text-muted">{b.name}</p>
          <p className="mt-1 font-display text-3xl font-bold leading-none">{Number(b.available)}<span className="ml-1.5 font-sans text-sm font-normal text-muted">of {Number(b.entitled)} days left</span></p>
          <Progress className="mt-3" tone="success" value={Number(b.entitled) > 0 ? (Number(b.available) / Number(b.entitled)) * 100 : 0} />
          <p className="mt-2 text-xs text-muted">{Number(b.used)} used · {Number(b.reserved)} pending approval</p>
        </CardBody></Card>))}
    </div>
  )
}

export function Requests({ scope, employeeId }: { scope: 'mine' | 'team' | 'all'; employeeId?: string }) {
  const [params, update] = useViewQuery()
  const statusKey = employeeId ? 'leave_status' : 'status'
  const chosen = params.get(statusKey) ?? (scope === 'mine' || employeeId ? 'all' : 'pending')
  const status = chosen === 'all' ? '' : chosen
  const record = employeeId ? null : params.get('record')
  const focusRow = useRecordFocus(record)
  const q = useGet<Req[]>('/leave/requests', { scope, status: status || undefined, employee_id: employeeId })
  const { data: me } = useMe()
  const decide = useSend<{ id: string; approve: boolean }>('POST', (b) => `/leave/requests/${b.id}/decision`, { invalidate: ['/leave', '/dashboard', '/attendance'], success: 'Decision saved' })
  const cancel = useSend<string>('POST', (id) => `/leave/requests/${id}/cancel`, { invalidate: ['/leave', '/dashboard'], success: 'Request cancelled' })
  return (
    <>
      <div className="mb-4"><Select aria-label="Filter by status" className="w-44" value={status} onChange={(e) => update({ [statusKey]: e.target.value || 'all', record: null })}>
        {[['', 'All requests'], ['pending', 'Pending'], ['approved', 'Approved'], ['rejected', 'Rejected'], ['cancelled', 'Cancelled']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
      {q.isLoading ? <Skeleton className="h-40 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
        : !q.data?.length ? <Card><EmptyState title={scope === 'mine' ? 'No leave requests yet' : 'Nothing waiting for a decision'} icon={CalendarDays} /></Card> : (
          <Card><ul className="divide-y divide-border">{q.data.map((r) => (
            <li key={r.id} ref={r.id === record ? focusRow : undefined} tabIndex={r.id === record ? -1 : undefined} className={cn('flex flex-wrap items-center justify-between gap-4 px-5 py-4', r.id === record && 'scroll-mt-28 bg-primary-soft')}>
              <div className="flex min-w-0 items-center gap-3">
                {scope === 'mine'
                  ? <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><CalendarDays className="h-5 w-5" aria-hidden /></span>
                  : null}
                <div className="min-w-0">
                {scope !== 'mine' && !employeeId && <div className="mb-1"><Person name={r.employee ?? 'Unknown'} sub={r.employee_code} size="sm" /></div>}
                  <p className="font-semibold">{r.leave_type} <span className="font-normal text-muted">· {days(r)}</span></p>
                  <p className="text-sm text-muted">{range(r)}{r.reason && ` · ${r.reason}`}</p>
                  {r.decision_note && <p className="mt-0.5 text-xs text-muted">Note: {r.decision_note}</p>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <StatusText status={r.status} />
                {scope !== 'mine' && me?.permissions.includes('leave.approve') && r.status === 'pending' && <><Button size="sm" onClick={() => decide.mutate({ id: r.id, approve: true })}>Approve</Button><Button size="sm" variant="danger-soft" onClick={() => decide.mutate({ id: r.id, approve: false })}>Reject</Button></>}
                {scope === 'mine' && ['pending', 'approved'].includes(r.status) && <ConfirmButton variant="outline" label="Cancel" title="Cancel this leave request?" message="Your balance is restored when you cancel." confirmLabel="Cancel request" onConfirm={() => cancel.mutate(r.id)} />}
              </div>
            </li>))}</ul></Card>)}
    </>
  )
}

export function MyLeavePage() {
  const [sp, update] = useViewQuery()
  const [open, setOpen] = React.useState(false)
  React.useEffect(() => { if (sp.get('apply') === '1') { setOpen(true); update({ apply: null }) } }, [sp])
  return (
    <>
      <PageHeader title="My leave" description="Balances, requests and their status." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Apply for leave</Button>} />
      <Balances /><Requests scope="mine" /><ApplyDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

interface CalReq { id: string; employee: string | null; employee_id: string; leave_type: string | null; start_date: string; end_date: string; status: string }
interface Holiday { id: string; name: string; holiday_date: string; branch_id: string | null }
interface Branch { id: string; name: string }
function HolidayCalendar() {
  const { data: me } = useMe()
  const canManage = !!me?.permissions.includes('org.manage')
  const [month, setMonth] = React.useState(today().slice(0, 7))
  const [branchId, setBranchId] = React.useState('')
  const [selected, setSelected] = React.useState<string | null>(null)
  const [name, setName] = React.useState('')
  const [year, index] = month.split('-').map(Number)
  const holidays = useGet<Holiday[]>('/holidays', { year })
  const branches = useGet<Branch[]>('/branches')
  const add = useSend<{ holiday_date: string; name: string; branch_id: string | null }>('POST', '/holidays', { invalidate: ['/holidays', '/leave', '/attendance'], success: 'Holiday added', onSuccess: () => { setSelected(null); setName('') } })
  const remove = useSend<string>('DELETE', id => `/holidays/${id}`, { invalidate: ['/holidays', '/leave', '/attendance'], success: 'Holiday removed' })
  const shift = (offset: number) => { const date = new Date(year, index - 1 + offset, 1); setMonth(`${date.getFullYear()}-${String(date.getMonth() + 1).padStart(2, '0')}`) }
  const visible = (holidays.data ?? []).filter(h => h.holiday_date.startsWith(month) && (!branchId || !h.branch_id || h.branch_id === branchId))
  const onDate = (date: string) => visible.filter(h => h.holiday_date === date)
  const count = new Date(year, index, 0).getDate()
  const offset = new Date(year, index - 1, 1).getDay()
  return <Card className="mb-5">
    <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-4"><div><h2 className="font-display text-lg font-bold">Public holidays</h2><p className="text-xs text-muted">Holidays apply to leave calculations and attendance.</p></div><div className="flex gap-2"><Select aria-label="Filter holidays by branch" className="w-40" value={branchId} onChange={e => setBranchId(e.target.value)}><option value="">All branches</option>{branches.data?.map(b => <option key={b.id} value={b.id}>{b.name}</option>)}</Select><Input type="month" aria-label="Holiday month" className="w-40" value={month} onChange={e => e.target.value && setMonth(e.target.value)} /></div></div>
    <div className="flex items-center justify-between px-5 py-3"><Button size="sm" variant="ghost" aria-label="Previous month" onClick={() => shift(-1)}><ChevronLeft className="h-4 w-4" /></Button><strong className="text-sm">{new Date(year, index - 1, 1).toLocaleDateString(undefined, { month: 'long', year: 'numeric' })}</strong><Button size="sm" variant="ghost" aria-label="Next month" onClick={() => shift(1)}><ChevronRight className="h-4 w-4" /></Button></div>
    {holidays.isError ? <ErrorState message={errorMessage(holidays.error)} /> : <div className="grid grid-cols-7 border-t border-border">{['Sun', 'Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat'].map(d => <div key={d} className="border-b border-border py-2 text-center text-xs font-semibold text-muted">{d}</div>)}{Array.from({ length: offset }, (_, i) => <div key={`blank-${i}`} className="min-h-20 border-b border-r border-border bg-surface-2/30" />)}{Array.from({ length: count }, (_, i) => { const date = `${month}-${String(i + 1).padStart(2, '0')}`; const items = onDate(date); return <button key={date} type="button" onClick={() => { setSelected(date); setName('') }} className={cn('min-h-20 border-b border-r border-border p-2 text-left hover:bg-primary-soft/40', items.length && 'bg-warning/10', date === today() && 'ring-1 ring-inset ring-primary')}><span className="text-xs font-medium">{i + 1}</span>{items.map(h => <span key={h.id} className="mt-1 block truncate rounded bg-warning/20 px-1.5 py-1 text-[10px] font-medium" title={h.name}>{h.name}</span>)}</button> })}</div>}
    <p className="px-5 py-3 text-xs text-muted">Select a day to {canManage ? 'add or review' : 'review'} holidays.</p>
    <Dialog open={!!selected} onOpenChange={open => !open && setSelected(null)}><DialogContent title={selected ? `Public holidays · ${formatDate(selected)}` : 'Public holidays'}><div className="space-y-3">{selected && onDate(selected).map(h => <div key={h.id} className="flex items-center justify-between gap-3 rounded-lg border border-border px-3 py-2"><div><p className="text-sm font-medium">{h.name}</p><p className="text-xs text-muted">{h.branch_id ? branches.data?.find(b => b.id === h.branch_id)?.name ?? 'Branch' : 'All branches'}</p></div>{canManage && <ConfirmButton label="Remove" title="Remove holiday?" message={`Remove ${h.name}?`} onConfirm={() => remove.mutate(h.id)} />}</div>)}{selected && !onDate(selected).length && <p className="text-sm text-muted">No public holiday on this day.</p>}{canManage && selected && <div className="space-y-3 border-t border-border pt-4"><Field id="holiday-name" label="New holiday">{a => <Input {...a} value={name} onChange={e => setName(e.target.value)} placeholder="Holiday name" />}</Field><p className="text-xs text-muted">{branchId ? `For ${branches.data?.find(b => b.id === branchId)?.name ?? 'selected branch'}` : 'For all branches'}</p><Button loading={add.isPending} disabled={name.trim().length < 2} onClick={() => add.mutate({ name: name.trim(), holiday_date: selected, branch_id: branchId || null })}>Add holiday</Button></div>}</div></DialogContent></Dialog>
  </Card>
}
function Planner() {
  const [month, setMonth] = React.useState(today().slice(0, 7))
  const q = useGet<CalReq[]>('/leave/calendar', { month })
  const holidays = useGet<{ id: string; name: string; holiday_date: string }[]>('/holidays', { year: Number(month.slice(0, 4)) })
  const googleEvent = (title: string, start: string, end: string) => {
    const next = new Date(`${end}T12:00:00Z`); next.setUTCDate(next.getUTCDate() + 1)
    const dates = `${start.replaceAll('-', '')}/${next.toISOString().slice(0, 10).replaceAll('-', '')}`
    return `https://calendar.google.com/calendar/render?action=TEMPLATE&text=${encodeURIComponent(title)}&dates=${dates}`
  }
  const [y, m] = month.split('-').map(Number)
  const count = new Date(y, m, 0).getDate()
  const byEmp = new Map<string, { name: string; reqs: CalReq[] }>()
  for (const r of q.data ?? []) { const e = byEmp.get(r.employee_id) ?? { name: r.employee ?? '', reqs: [] }; e.reqs.push(r); byEmp.set(r.employee_id, e) }
  const iso = (d: number) => `${month}-${String(d).padStart(2, '0')}`
  const weekend = (d: number) => [0, 6].includes(new Date(y, m - 1, d).getDay())
  return (
    <Card>
      <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3">
        <div className="flex gap-4 text-xs text-muted"><span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded bg-success" />Approved</span><span className="flex items-center gap-1.5"><i className="h-3 w-3 rounded bg-warning/70" />Pending</span></div>
        <Input type="month" aria-label="Month" className="w-44" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} />
      </div>
      {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} /> : byEmp.size === 0 ? <EmptyState title="Nobody is on leave this month" icon={CalendarDays} /> : (
        <div className="overflow-x-auto"><table className="w-full border-collapse text-xs">
          <thead><tr><th className="sticky left-0 z-10 min-w-44 bg-surface px-5 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted">Employee</th>
            {Array.from({ length: count }, (_, i) => <th key={i} className={cn('min-w-7 px-0.5 py-2.5 font-medium', weekend(i + 1) ? 'text-subtle' : 'text-muted')}>{i + 1}</th>)}</tr></thead>
          <tbody>{[...byEmp.entries()].map(([id, e]) => (
            <tr key={id} className="border-t border-border"><td className="sticky left-0 z-10 bg-surface px-5 py-2 text-sm font-medium">{e.name}</td>
              {Array.from({ length: count }, (_, i) => {
                const r = e.reqs.find((x) => x.start_date <= iso(i + 1) && x.end_date >= iso(i + 1))
                return <td key={i} className={cn('p-0.5', weekend(i + 1) && 'bg-surface-2/50')} title={r ? `${r.leave_type} (${r.status})` : undefined}><div className={cn('h-6 rounded', r?.status === 'approved' && 'bg-success', r?.status === 'pending' && 'bg-warning/70')} /></td>
              })}</tr>))}</tbody></table></div>)}
      <div className="border-t border-border p-5"><h3 className="text-sm font-semibold">Calendar events</h3><p className="mt-1 text-xs text-muted">Open an approved leave or holiday in Google Calendar to add it to your calendar. This does not share private employee leave automatically.</p><div className="mt-3 grid gap-2 sm:grid-cols-2">{(holidays.data ?? []).filter(h => h.holiday_date.startsWith(month)).map(h => <a key={h.id} href={googleEvent(h.name, h.holiday_date, h.holiday_date)} target="_blank" rel="noreferrer" className="rounded-lg border border-border px-3 py-2 text-sm hover:border-primary">{h.holiday_date} · {h.name} <span className="text-primary">Add to Google Calendar</span></a>)}{(q.data ?? []).filter(r => r.status === 'approved').map(r => <a key={r.id} href={googleEvent(`${r.employee ?? 'Employee'}: ${r.leave_type ?? 'Leave'}`, r.start_date, r.end_date)} target="_blank" rel="noreferrer" className="rounded-lg border border-border px-3 py-2 text-sm hover:border-primary">{r.start_date} · {r.employee} · {r.leave_type} <span className="text-primary">Add to Google Calendar</span></a>)}</div></div>
    </Card>
  )
}

export function LeaveAdminPage() {
  const { data: me } = useMe()
  const all = !!me?.permissions.includes('leave.manage')
  type T = 'approvals' | 'planner'
  const [tab, setTab] = useViewTab<T>(['approvals', 'planner'], 'approvals')
  const pending = useGet<Req[]>('/leave/requests', { scope: all ? 'all' : 'team', status: 'pending' })
  return (
    <>
      <PageHeader title="Leave" description={all ? 'Approve requests and see who is away across the organization.' : 'Approve requests and see who is away in your team.'} />
      <Tabs tabs={[{ id: 'approvals', label: 'Requests', count: pending.data?.length }, { id: 'planner', label: 'Leave planner' }]} value={tab} onChange={setTab} />
      {tab === 'approvals' ? <Requests scope={all ? 'all' : 'team'} /> : <><HolidayCalendar /><Planner /></>}
    </>
  )
}
