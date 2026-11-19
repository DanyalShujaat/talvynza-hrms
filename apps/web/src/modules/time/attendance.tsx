import { CalendarDays, Check, Clock, FileUp, Plus, X } from 'lucide-react'
import * as React from 'react'
import { Bar, BarChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { DataTable, Detail, Person, StatusText, Tabs } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { hhmm, timeOf, today, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { formatDate } from '@/lib/utils'
import { CheckInCard } from '@/modules/platform/dashboard'
import { Opts, type EmpRow } from '@/modules/people/employees'

interface Day { work_date: string; status: string; first_in: string | null; last_out: string | null; worked_minutes: number; late_minutes: number; early_leave_minutes: number; overtime_minutes: number }
interface Month { month: string; days: Day[]; totals: { worked_minutes: number; late_minutes: number; overtime_minutes: number; present_days: number; late_days: number } }
interface Adj { id: string; employee: string | null; work_date: string; requested_in: string | null; requested_out: string | null; reason: string; status: string; review_note: string | null }

function MyMonth() {
  const [month, setMonth] = React.useState(today().slice(0, 7))
  const q = useGet<Month>('/attendance/me', { month })
  const data = (q.data?.days ?? []).map((d) => ({ day: Number(d.work_date.slice(8)), Worked: +((d.worked_minutes - d.overtime_minutes) / 60).toFixed(2), Overtime: +(d.overtime_minutes / 60).toFixed(2) }))
  const t = q.data?.totals
  return (
    <div className="grid gap-6 lg:grid-cols-3">
      <div className="space-y-6">
        <CheckInCard />
        <Card><CardHeader><CardTitle>This month</CardTitle></CardHeader><CardBody className="pt-2">
          {!t ? <Skeleton className="h-32 w-full" /> : <Detail rows={[['Days present', t.present_days], ['Late days', t.late_days || '0'], ['Hours worked', hhmm(t.worked_minutes)], ['Late minutes', t.late_minutes || '0'], ['Overtime', hhmm(t.overtime_minutes)]]} />}
        </CardBody></Card>
      </div>
      <Card className="lg:col-span-2">
        <CardHeader><CardTitle>Daily hours</CardTitle><Input type="month" aria-label="Month" className="w-44" value={month} onChange={(e) => e.target.value && setMonth(e.target.value)} /></CardHeader>
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
  const [status, setStatus] = React.useState(scope === 'mine' ? '' : 'pending')
  const [open, setOpen] = React.useState(false)
  const q = useGet<Adj[]>('/attendance/adjustments', { scope, status: status || undefined })
  const decide = useSend<{ id: string; approve: boolean }>('POST', (b) => `/attendance/adjustments/${b.id}/decision`, { invalidate: ['/attendance', '/dashboard'], success: 'Decision saved' })
  return (
    <>
      <div className="mb-4 flex flex-wrap items-center justify-between gap-3">
        <Select aria-label="Filter by status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>{FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>
        {scope === 'mine' && <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New request</Button>}
      </div>
      {q.isLoading ? <Skeleton className="h-32 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
        : !q.data?.length ? <Card><EmptyState title={scope === 'mine' ? 'No adjustment requests' : 'Nothing waiting for a decision'} icon={CalendarDays} /></Card> : (
          <div className="space-y-3">{q.data.map((a) => (
            <Card key={a.id}><CardBody className="flex flex-wrap items-center justify-between gap-4 py-4">
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
  const [date, setDate] = React.useState(today())
  const q = useGet<Daily[]>('/attendance/daily', { date })
  const rows = q.data ?? []
  const count = (s: string[]) => rows.filter((r) => s.includes(r.status)).length
  return (
    <Card>
      <CardHeader>
        <div><CardTitle>{everyone ? 'All employees' : 'My team'}</CardTitle>
          {!!rows.length && <p className="text-xs text-muted">{count(['present', 'incomplete'])} present · {rows.filter((r) => r.late_minutes > 0).length} late · {count(['absent'])} absent · {count(['leave'])} on leave</p>}</div>
        <Input type="date" aria-label="Date" className="w-44" value={date} onChange={(e) => e.target.value && setDate(e.target.value)} />
      </CardHeader>
      <DataTable rows={rows} rowKey={(d) => d.employee_id} query={q} empty="No employees to show" cols={[
        { header: 'Employee', cell: (d) => <Person name={d.full_name} sub={d.employee_code} size="sm" /> },
        { header: 'Department', cell: (d) => d.department ?? <span className="text-subtle">None</span> },
        { header: 'In', cell: (d) => timeOf(d.first_in) }, { header: 'Out', cell: (d) => timeOf(d.last_out) },
        { header: 'Worked', cell: (d) => hhmm(d.worked_minutes) },
        { header: 'Late', cell: (d) => (d.late_minutes ? <span className="font-medium text-warning">{d.late_minutes} min</span> : '') },
        { header: 'Status', cell: (d) => <StatusText status={d.status} /> },
      ]} />
    </Card>
  )
}

function EmployeeReport() {
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const [employeeId, setEmployeeId] = React.useState('')
  const [month, setMonth] = React.useState(today().slice(0, 7))
  const q = useGet<Month>('/attendance/me', { employee_id: employeeId, month }, !!employeeId)
  const days = q.data?.days ?? []
  return <div className="space-y-5"><Card><CardBody className="flex flex-wrap items-end gap-4"><Field id="report-person" label="Employee">{a => <Select className="w-72" {...a} value={employeeId} onChange={e => setEmployeeId(e.target.value)}><Opts list={(people.data?.items ?? []).map(p => ({ id: p.id, name: `${p.full_name} (${p.employee_code})` }))} blank="Choose an employee" /></Select>}</Field><Field id="report-month" label="Month">{a => <Input type="month" className="w-44" {...a} value={month} onChange={e => setMonth(e.target.value)} />}</Field></CardBody></Card>{employeeId && <Card><CardHeader><CardTitle>Monthly attendance</CardTitle></CardHeader><CardBody><div className="mb-5 grid gap-3 sm:grid-cols-4">{[['Present days', q.data?.totals.present_days], ['Worked hours', q.data && hhmm(q.data.totals.worked_minutes)], ['Late minutes', q.data?.totals.late_minutes], ['Overtime', q.data && hhmm(q.data.totals.overtime_minutes)]].map(([label, value]) => <div key={label} className="rounded-lg bg-surface-2 p-3"><p className="text-xs text-muted">{label}</p><p className="mt-1 text-xl font-semibold">{value ?? '—'}</p></div>)}</div><DataTable rows={days} query={q} rowKey={d => d.work_date} empty="No attendance recorded for this month" cols={[{ header: 'Date', cell: d => formatDate(d.work_date) }, { header: 'In', cell: d => timeOf(d.first_in) }, { header: 'Out', cell: d => timeOf(d.last_out) }, { header: 'Worked', cell: d => hhmm(d.worked_minutes) }, { header: 'Late', cell: d => `${d.late_minutes} min` }, { header: 'Status', cell: d => <StatusText status={d.status} /> }]} /></CardBody></Card>}</div>
}

function Tools() {
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const [emp, setEmp] = React.useState('')
  const [kind, setKind] = React.useState<'in' | 'out'>('in')
  const [at, setAt] = React.useState('')
  const [file, setFile] = React.useState<File | null>(null)
  const [busy, setBusy] = React.useState(false)
  const manual = useSend<unknown>('POST', '/attendance/manual', { invalidate: ['/attendance', '/dashboard'], success: 'Punch recorded', onSuccess: () => setAt('') })
  const run = async () => {
    const f = new FormData(); f.append('file', file!); setBusy(true)
    try {
      const r = await uploadFile<{ imported: number; duplicates_ignored: number; errors: { row: number; error: string }[] }>('/attendance/import', f)
      toast.success(`${r.imported} punches imported, ${r.duplicates_ignored} duplicates ignored`)
      if (r.errors.length) toast.warning(`${r.errors.length} rows were skipped. First: row ${r.errors[0].row}, ${r.errors[0].error}`)
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
      <Card><CardHeader><CardTitle>Import from a biometric device</CardTitle></CardHeader><CardBody className="space-y-4">
        <p className="text-sm text-muted">Upload a CSV export with the columns <code className="rounded bg-surface-2 px-1">employee_code</code> or <code className="rounded bg-surface-2 px-1">bio_id</code>, <code className="rounded bg-surface-2 px-1">timestamp</code> and, if the device records it, <code className="rounded bg-surface-2 px-1">kind</code> (in or out). Repeated reads of the same punch are ignored.</p>
        <Input type="file" accept=".csv" aria-label="Punch file" className="pt-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} />
        <Button disabled={!file} loading={busy} onClick={run}><FileUp className="h-4 w-4" />Import punches</Button>
      </CardBody></Card>
    </div>
  )
}

export function AttendancePage() {
  const { data: me } = useMe()
  const p = new Set(me?.permissions ?? [])
  const all = p.has('attendance.manage')
  type T = 'daily' | 'individual' | 'approvals' | 'tools'
  const [sp, setSp] = useSearchParams()
  const tab: T = sp.get('tab') === 'approvals' ? 'approvals' : sp.get('tab') === 'individual' ? 'individual' : sp.get('tab') === 'tools' && all ? 'tools' : 'daily'
  const setTab = (t: T) => setSp({ tab: t })
  const pending = useGet<Adj[]>('/attendance/adjustments', { scope: all ? 'all' : 'team', status: 'pending' })
  const tabs: { id: T; label: string; count?: number }[] = [{ id: 'daily', label: 'Daily attendance' }, { id: 'individual', label: 'Individual report' }, { id: 'approvals', label: 'Corrections', count: pending.data?.length }]
  if (all) tabs.push({ id: 'tools', label: 'Manual entry and import' })
  return (
    <>
      <PageHeader title="Attendance" description={all ? 'Daily attendance, correction requests and punch imports for the whole organization.' : 'Attendance and correction requests for your team.'} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'daily' && <DailyView everyone={all} />}{tab === 'individual' && <EmployeeReport />}{tab === 'approvals' && <Adjustments scope={all ? 'all' : 'team'} />}{tab === 'tools' && <Tools />}
    </>
  )
}
