import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, Check, Clock, FileUp, Plus, X } from 'lucide-react'
import * as React from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { DataTable, Detail, Pager, Person, StatusText, Tabs } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { hhmm, timeOf, today, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { CheckInCard } from '@/modules/platform/dashboard'
import { Opts, useOrgLists, type EmpRow } from '@/modules/people/employees'
import { AttendanceAccess } from './attendance-access'
import { useRecordFocus, useViewQuery } from '@/lib/view-state'

interface Day { work_date: string; status: string; first_in: string | null; last_out: string | null; worked_minutes: number; late_minutes: number; early_leave_minutes: number; overtime_minutes: number }
interface Month { month: string; days: Day[]; totals: { worked_minutes: number; late_minutes: number; overtime_minutes: number; present_days: number; late_days: number } }
interface Adj { id: string; employee: string | null; work_date: string; requested_in: string | null; requested_out: string | null; reason: string; status: string; review_note: string | null }
const reportMonth = (value: string | null) => value && /^\d{4}-(0[1-9]|1[0-2])$/.test(value) ? value : today().slice(0, 7)

function MyMonth() {
  const [view, update] = useViewQuery()
  const month = reportMonth(view.get('month'))
  const q = useGet<Month>('/attendance/me', { month })
  const data = (q.data?.days ?? []).map((d) => ({ day: Number(d.work_date.slice(8)), Worked: +((d.worked_minutes - d.overtime_minutes) / 60).toFixed(2), Overtime: +(d.overtime_minutes / 60).toFixed(2) }))
  const t = q.data?.totals
  return (
    <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
      <div className="space-y-6">
        <CheckInCard />
        <Card><CardHeader><CardTitle>Monthly totals</CardTitle></CardHeader><CardBody className="pt-2">
          {!t ? <Skeleton className="h-32 w-full" /> : <Detail rows={[['Days present', t.present_days], ['Late days', t.late_days || '0'], ['Hours worked', hhmm(t.worked_minutes)], ['Late minutes', t.late_minutes || '0'], ['Overtime', hhmm(t.overtime_minutes)]]} />}
        </CardBody></Card>
      </div>
      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>Daily hours</CardTitle><Input type="month" aria-label="Month" className="w-44" value={month} onChange={(e) => e.target.value && update({ month: e.target.value })} /></CardHeader>
        <CardBody>
          {q.isLoading ? <Skeleton className="h-60 w-full" /> : q.isError ? <ErrorState message={errorMessage(q.error)} /> : !data.length ? <EmptyState title="No attendance recorded this month" icon={Clock} /> : (
            <div className="h-60" role="img" aria-label="Hours worked and overtime per day"><ResponsiveContainer width="100%" height="100%">
              <BarChart data={data} margin={{ left: -22, right: 4, top: 4 }}>
                <CartesianGrid vertical={false} stroke="var(--color-border)" />
                <XAxis dataKey="day" tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: 'var(--color-muted)' }} />
                <YAxis tickLine={false} axisLine={false} tick={{ fontSize: 12, fill: 'var(--color-muted)' }} />
                <Tooltip cursor={{ fill: 'var(--color-surface-2)' }} contentStyle={{ background: 'var(--color-surface)', border: '1px solid var(--color-border)', borderRadius: 10, fontSize: 13 }} />
                <Bar dataKey="Worked" stackId="a" fill="#0f4bb5" radius={[0, 0, 3, 3]} maxBarSize={18} /><Bar dataKey="Overtime" stackId="a" fill="#06b3a2" radius={[3, 3, 0, 0]} maxBarSize={18} />
              </BarChart></ResponsiveContainer></div>)}
        </CardBody>
        {!!q.data?.days.length && (
          <div className="max-h-80 overflow-auto border-t border-border">
            <DataTable rows={[...q.data.days].reverse()} rowKey={(d) => d.work_date} empty="" cols={[
              { header: 'Date', cell: (d) => formatDate(d.work_date, { weekday: 'short', day: 'numeric', month: 'short' }) },
              { header: 'In', cell: (d) => timeOf(d.first_in) }, { header: 'Out', cell: (d) => timeOf(d.last_out) },
              { header: 'Worked', cell: (d) => hhmm(d.worked_minutes) },
              { header: 'Late', cell: (d) => (d.late_minutes ? <span className="font-medium text-warning">{d.late_minutes} min</span> : <span className="text-subtle">On time</span>) },
              { header: 'Status', cell: (d) => <StatusText status={d.status} /> },
            ]} />
          </div>)}
      </Card>
    </div>
  )
}

function AdjustmentDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [f, setF] = React.useState({ work_date: today(), in_time: '09:00', out_time: '18:00', reason: '' })
  const m = useSend<typeof f>('POST', '/attendance/adjustments', { invalidate: ['/attendance', '/dashboard'], success: 'Sent for approval', onSuccess: () => { onOpenChange(false); setF({ ...f, reason: '' }) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Request a time adjustment" description="For a missed check-in or check-out, or a device failure. Your manager or HR approves it.">
        <div className="space-y-4">
          <Field id="a-d" label="Date">{(a) => <Input type="date" max={today()} value={f.work_date} onChange={(e) => setF({ ...f, work_date: e.target.value })} {...a} />}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="a-i" label="In time">{(a) => <Input type="time" value={f.in_time} onChange={(e) => setF({ ...f, in_time: e.target.value })} {...a} />}</Field>
            <Field id="a-o" label="Out time">{(a) => <Input type="time" value={f.out_time} onChange={(e) => setF({ ...f, out_time: e.target.value })} {...a} />}</Field>
          </div>
          <Field id="a-r" label="Reason">{(a) => <Input value={f.reason} placeholder="What happened?" onChange={(e) => setF({ ...f, reason: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={f.reason.trim().length < 3 || (!f.in_time && !f.out_time)} onClick={() => m.mutate({ ...f, in_time: f.in_time || undefined, out_time: f.out_time || undefined } as never)}>Submit request</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const FILTERS = [['', 'All requests'], ['pending', 'Pending'], ['approved', 'Accepted'], ['rejected', 'Rejected']]

function Adjustments({ scope }: { scope: 'mine' | 'team' | 'all' }) {
  const [params, update] = useViewQuery()
  const chosen = params.get('status') ?? (scope === 'mine' ? 'all' : 'pending')
  const status = chosen === 'all' ? '' : chosen
  const record = params.get('record')
  const focusRow = useRecordFocus(record)
  const [open, setOpen] = React.useState(false)
  const q = useGet<Adj[]>('/attendance/adjustments', { scope, status: status || undefined })
  const decide = useSend<{ id: string; approve: boolean }>('POST', (b) => `/attendance/adjustments/${b.id}/decision`, { invalidate: ['/attendance', '/dashboard'], success: 'Decision saved' })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Select aria-label="Filter by status" className="w-44" value={status} onChange={(e) => update({ status: e.target.value || 'all', record: null })}>{FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
        {scope === 'mine' && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New request</Button>}
      </div>
      {q.isLoading ? <Skeleton className="h-32 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
        : !q.data?.length ? <Card><EmptyState title={scope === 'mine' ? 'No adjustment requests' : 'Nothing waiting for a decision'} icon={CalendarDays} /></Card> : (
          <div className="space-y-3">{q.data.map((a) => (
            <Card key={a.id} ref={a.id === record ? focusRow : undefined} tabIndex={a.id === record ? -1 : undefined} className={cn(a.id === record && 'scroll-mt-28 border-primary bg-primary-soft')}><CardBody className="flex flex-wrap items-center justify-between gap-4 py-4">
              <div className="flex min-w-0 gap-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><CalendarDays className="h-5 w-5" aria-hidden /></span>
                <div className="min-w-0">
                  <p className="font-semibold">{formatDate(a.work_date, { weekday: 'short', day: 'numeric', month: 'long', year: 'numeric' })}{scope !== 'mine' && <span className="ml-2 font-normal text-muted">{a.employee}</span>}</p>
                  <p className="text-sm text-muted">{a.reason}</p>
                  <p className="mt-1 text-[13px]">Requested <span className="font-medium">in {timeOf(a.requested_in)}</span>, <span className="font-medium">out {timeOf(a.requested_out)}</span></p>
                  {a.review_note && <p className="mt-1 text-xs text-muted">Note: {a.review_note}</p>}
                </div>
              </div>
              <div className="flex items-center gap-2">
                <StatusText status={a.status === 'approved' ? 'accepted' : a.status} />
                {scope !== 'mine' && a.status === 'pending' && <>
                  <Button size="sm" onClick={() => decide.mutate({ id: a.id, approve: true })}><Check className="h-4 w-4" />Accept</Button>
                  <Button size="sm" variant="danger-soft" onClick={() => decide.mutate({ id: a.id, approve: false })}><X className="h-4 w-4" />Reject</Button></>}
              </div>
            </CardBody></Card>))}</div>)}
      <AdjustmentDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

export function MyAttendancePage() {
  const [sp, setSp] = useSearchParams()
  const tab = sp.get('tab') === 'adjust' ? 'adjust' : 'month'
  return (
    <>
      <PageHeader title="My attendance" description="Your check-ins, hours and correction requests." />
      <Tabs tabs={[{ id: 'month', label: 'Attendance' }, { id: 'adjust', label: 'Time adjustments' }]} value={tab} onChange={(t) => setSp(t === 'adjust' ? { tab: 'adjust' } : {})} />
      {tab === 'month' ? <MyMonth /> : <Adjustments scope="mine" />}
    </>
  )
}

interface Daily extends Day { employee_id: string; employee_code: string; full_name: string; department: string | null }
function DailyView({ everyone }: { everyone: boolean }) {
  const [view, update] = useViewQuery()
  const { branches, departments } = useOrgLists()
  const requested = view.get('date') ?? ''
  const date = /^\d{4}-\d{2}-\d{2}$/.test(requested) ? requested : today()
  const branch = view.get('branch_id') ?? ''
  const department = view.get('department_id') ?? ''
  const page = Math.max(1, parseInt(view.get('page') ?? '1', 10) || 1)
  const q = useGet<{ items: Daily[]; total: number; page_size: number }>('/attendance/daily', {
    date, branch_id: branch || undefined, department_id: department || undefined, page, paginated: 'true',
  })
  React.useEffect(() => {
    if (q.data && page > Math.max(1, Math.ceil(q.data.total / q.data.page_size))) update({ page: null })
  }, [q.data, page])
  const rows = q.data?.items ?? []
  const count = (s: string[]) => rows.filter((r) => s.includes(r.status)).length
  return (
    <Card>
      <CardHeader>
        <div><CardTitle>{everyone ? 'All employees' : 'My team'}</CardTitle>
          {!!rows.length && <p className="text-xs text-muted">{q.data && q.data.total > q.data.page_size ? 'On this page · ' : ''}{count(['present', 'incomplete'])} present · {rows.filter((r) => r.late_minutes > 0).length} late · {count(['absent'])} absent · {count(['leave'])} on leave</p>}</div>
        <div className="flex flex-wrap gap-2">
          <Select aria-label="Branch" className="w-40" value={branch} onChange={e => update({ branch_id: e.target.value, page: null })}><Opts list={branches} blank="All branches" /></Select>
          <Select aria-label="Department" className="w-40" value={department} onChange={e => update({ department_id: e.target.value, page: null })}><Opts list={departments} blank="All departments" /></Select>
          <Input type="date" aria-label="Date" className="w-44" value={date} onChange={(e) => e.target.value && update({ date: e.target.value, page: null })} />
        </div>
      </CardHeader>
      <DataTable rows={rows} rowKey={(d) => d.employee_id} query={q} empty="No employees to show" cols={[
        { header: 'Employee', cell: (d) => <Person name={d.full_name} sub={d.employee_code} size="sm" /> },
        { header: 'Department', cell: (d) => d.department ?? <span className="text-subtle">None</span> },
        { header: 'In', cell: (d) => timeOf(d.first_in) }, { header: 'Out', cell: (d) => timeOf(d.last_out) },
        { header: 'Worked', cell: (d) => hhmm(d.worked_minutes) },
        { header: 'Late', cell: (d) => (d.late_minutes ? <span className="font-medium text-warning">{d.late_minutes} min</span> : '') },
        { header: 'Status', cell: (d) => <StatusText status={d.status} /> },
      ]} />
      {q.data && <Pager page={page} pageSize={q.data.page_size} total={q.data.total} onPage={next => update({ page: next }, false)} />}
    </Card>
  )
}

export function EmployeeReport({ fixedEmployeeId }: { fixedEmployeeId?: string }) {
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, !fixedEmployeeId)
  const [view, update] = useViewQuery()
  const employeeId = fixedEmployeeId ?? view.get('employee_id') ?? ''
  const month = reportMonth(view.get('month'))
  const q = useGet<Month>('/attendance/me', { employee_id: employeeId, month }, !!employeeId)
  const totals = q.data?.totals
  return (
    <Card>
      <CardHeader>
        <CardTitle>Monthly attendance</CardTitle>
        <div className="flex flex-wrap items-end gap-3">
          {!fixedEmployeeId && <Field id="report-person" label="Employee">{a => (
            <Select className="w-60" {...a} value={employeeId} onChange={e => update({ employee_id: e.target.value })}>
              <Opts list={(people.data?.items ?? []).map(p => ({ id: p.id, name: `${p.full_name} (${p.employee_code})` }))} blank="Choose an employee" />
            </Select>
          )}</Field>}
          <Field id="report-month" label="Month">{a => <Input type="month" className="w-44" {...a} value={month} onChange={e => e.target.value && update({ month: e.target.value })} />}</Field>
        </div>
      </CardHeader>
      {!!employeeId && <>
        {totals && <CardBody className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {[
            ['Present days', totals.present_days],
            ['Worked hours', hhmm(totals.worked_minutes)],
            ['Late minutes', totals.late_minutes],
            ['Overtime', hhmm(totals.overtime_minutes)],
          ].map(([label, value]) => <div key={label} className="rounded-lg bg-surface-2 p-3"><p className="text-xs text-muted">{label}</p><p className="mt-1 text-xl font-semibold">{value}</p></div>)}
        </CardBody>}
        <DataTable rows={q.data?.days} query={q} rowKey={d => d.work_date} empty="No attendance recorded for this month" cols={[
          { header: 'Date', cell: d => formatDate(d.work_date) },
          { header: 'In', cell: d => timeOf(d.first_in) },
          { header: 'Out', cell: d => timeOf(d.last_out) },
          { header: 'Worked', cell: d => hhmm(d.worked_minutes) },
          { header: 'Late', cell: d => `${d.late_minutes} min` },
          { header: 'Status', cell: d => <StatusText status={d.status} /> },
        ]} />
      </>}
    </Card>
  )
}

function Tools() {
  const queryClient = useQueryClient()
  const [params, update] = useViewQuery()
  const { branches } = useOrgLists()
  const branch = params.get('branch_id') ?? ''
  const biometric = params.get('import_mode') !== 'employee'
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const [emp, setEmp] = React.useState('')
  const [kind, setKind] = React.useState<'in' | 'out'>('in')
  const [at, setAt] = React.useState('')
  const [file, setFile] = React.useState<File | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [errors, setErrors] = React.useState<{ row: number; error: string }[]>([])
  const [errorCount, setErrorCount] = React.useState(0)
  const manual = useSend<unknown>('POST', '/attendance/manual', { invalidate: ['/attendance', '/dashboard'], success: 'Punch recorded', onSuccess: () => setAt('') })
  const run = async () => {
    if (!file || (biometric && !branch)) return
    const f = new FormData()
    f.append('file', file)
    if (biometric) f.append('branch_id', branch)
    setErrors([])
    setErrorCount(0)
    setBusy(true)
    try {
      const r = await uploadFile<{ imported: number; duplicates_ignored: number; error_count: number; errors: { row: number; error: string }[] }>('/attendance/import', f)
      toast.success(`${r.imported} ${r.imported === 1 ? 'punch' : 'punches'} imported, ${r.duplicates_ignored} duplicates ignored`)
      setErrors(r.errors)
      setErrorCount(r.error_count)
      void queryClient.invalidateQueries({ predicate: q => ['/attendance', '/dashboard'].some(prefix => String(q.queryKey[0]).startsWith(prefix)) })
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <div className="grid gap-6 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Record a punch by hand</CardTitle></CardHeader><CardBody className="space-y-4">
        <Field id="m-e" label="Employee">{(a) => <Select value={emp} onChange={(e) => setEmp(e.target.value)} {...a}><Opts list={(people.data?.items ?? []).map((p) => ({ id: p.id, name: `${p.full_name} (${p.employee_code})` }))} blank="Select employee" /></Select>}</Field>
        <div className="grid grid-cols-2 gap-3">
          <Field id="m-k" label="Type">{(a) => <Select value={kind} onChange={(e) => setKind(e.target.value as 'in' | 'out')} {...a}><option value="in">Check in</option><option value="out">Check out</option></Select>}</Field>
          <Field id="m-t" label="Date and time">{(a) => <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} {...a} />}</Field>
        </div>
        <Button disabled={!emp || !at} loading={manual.isPending} onClick={() => manual.mutate({ employee_id: emp, kind, occurred_at: new Date(at).toISOString() })}>Record punch</Button>
      </CardBody></Card>
      <Card><CardHeader><CardTitle>Import punches</CardTitle></CardHeader><CardBody className="space-y-4">
        <Field id="attendance-import-mode" label="Import source">{a => <Select {...a} value={biometric ? 'device' : 'employee'} onChange={e => update({ import_mode: e.target.value })}>
          <option value="device">Branch biometric device</option><option value="employee">Administrative employee-code CSV</option>
        </Select>}</Field>
        {biometric ? <>
          <Field id="device-branch" label="Device branch">{a => <Select {...a} value={branch} onChange={e => update({ branch_id: e.target.value })}><Opts list={branches} blank="Choose the branch where the device is installed" /></Select>}</Field>
          <p className="text-sm text-muted">Use a CSV with <code>bio_id</code>, <code>timestamp</code>, and preferably <code>kind</code> (in or out). IDs match employees in this branch with premises attendance enabled. Timestamps without an offset use the organization’s time zone.</p>
        </> : <p className="text-sm text-muted">Use <code>employee_code</code>, <code>timestamp</code>, and preferably <code>kind</code> (in or out). Timestamps without an offset use UTC.</p>}
        <Input type="file" accept=".csv" aria-label="Punch file" className="pt-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button disabled={!file || (biometric && !branch)} loading={busy} onClick={run}><FileUp className="h-4 w-4" />Import punches</Button>
        {!!errors.length && <div role="status" className="rounded-lg bg-warning-soft p-3 text-sm">
          <p className="font-semibold">{errorCount} CSV {errorCount === 1 ? 'row needs' : 'rows need'} attention</p>
          {errorCount > errors.length && <p>Showing the first {errors.length} rows with errors.</p>}
          <ul className="mt-1 max-h-40 space-y-1 overflow-auto">{errors.map(row => <li key={row.row}>Row {row.row} - {row.error}</li>)}</ul>
        </div>}
      </CardBody></Card>
    </div>
  )
}

export function AttendancePage() {
  const { data: me } = useMe()
  const p = new Set(me?.permissions ?? [])
  const all = p.has('attendance.manage')
  type T = 'daily' | 'individual' | 'approvals' | 'tools' | 'access'
  const [sp, setSp] = useSearchParams()
  const requested = sp.get('tab')
  const tab: T = requested === 'approvals' || requested === 'individual' ? requested
    : all && (requested === 'tools' || requested === 'access') ? requested : 'daily'
  const setTab = (t: T) => { const next = new URLSearchParams(sp); next.set('tab', t); setSp(next) }
  const pending = useGet<Adj[]>('/attendance/adjustments', { scope: all ? 'all' : 'team', status: 'pending' })
  const tabs: { id: T; label: string; count?: number }[] = [{ id: 'daily', label: 'Daily attendance' }, { id: 'individual', label: 'Individual report' }, { id: 'approvals', label: 'Corrections', count: pending.data?.length }]
  if (all) tabs.push({ id: 'access', label: 'Attendance access' }, { id: 'tools', label: 'Biometric import and manual entry' })
  return (
    <>
      <PageHeader title="Attendance" description={all ? 'Daily attendance, correction requests and punch imports for the whole organization.' : 'Attendance and correction requests for your team.'} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'daily' && <DailyView everyone={all} />}{tab === 'individual' && <EmployeeReport />}{tab === 'approvals' && <Adjustments scope={all ? 'all' : 'team'} />}{tab === 'tools' && <Tools />}
      {tab === 'access' && <AttendanceAccess />}
    </>
  )
}
