import { ArrowLeft, CheckCircle2, CircleAlert, DoorOpen, Plus } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, CardBody, CardHeader, CardTitle, ErrorState, Notice, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, DataTable, Detail, Person, Progress, StatusText } from '@/components/ui/extras'
import { Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { money, today, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { Opts, type EmpRow } from '@/modules/people/employees'

interface Row { id: string; employee_id: string; employee: string | null; employee_code: string | null; kind: string; notice_date: string; last_working_day: string; reason: string | null; status: string; items_done: number; items_total: number }
interface Item { id: string; department: string; title: string; done: boolean }
interface Detail_ extends Row {
  exit_interview: string | null; settlement: Record<string, string | null>; items: Item[]
  open_assets: { asset_id: string; name: string; serial_number: string | null }[]; loan_balance: string; pending_expense_claims: number; approved_unpaid_expenses: string
  leave_balances: { name: string; available: string }[]
}
const day = (d: string) => formatDate(d, { dateStyle: 'medium' })

function StartDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const nav = useNavigate()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, open)
  const [f, setF] = React.useState({ employee_id: '', kind: 'resignation', notice_date: today(), last_working_day: '', reason: '' })
  const m = useSend<Record<string, unknown>, Row>('POST', '/offboarding', { invalidate: ['/offboarding'], success: 'Exit process started', onSuccess: (r) => { onOpenChange(false); nav(`/offboarding/${r.id}`) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Start an exit" description="Opens a clearance checklist. The employee keeps their access until the exit is completed.">
        <div className="space-y-4">
          <Field id="of-e" label="Employee">{(a) => <Select value={f.employee_id} onChange={(e) => setF({ ...f, employee_id: e.target.value })} {...a}><Opts list={(people.data?.items ?? []).map((p) => ({ id: p.id, name: `${p.full_name} (${p.employee_code})` }))} blank="Select an employee" /></Select>}</Field>
          <Field id="of-k" label="Reason for leaving">{(a) => <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} {...a}><option value="resignation">Resignation</option><option value="termination">Termination</option><option value="retirement">Retirement</option></Select>}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="of-n" label="Notice given on">{(a) => <Input type="date" value={f.notice_date} onChange={(e) => setF({ ...f, notice_date: e.target.value })} {...a} />}</Field>
            <Field id="of-l" label="Last working day">{(a) => <Input type="date" min={f.notice_date} value={f.last_working_day} onChange={(e) => setF({ ...f, last_working_day: e.target.value })} {...a} />}</Field>
          </div>
          <Field id="of-r" label="Notes (optional)">{(a) => <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={!f.employee_id || !f.last_working_day} onClick={() => m.mutate({ ...f, reason: f.reason || null })}>Start exit</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function OffboardingPage() {
  const nav = useNavigate()
  const q = useGet<Row[]>('/offboarding')
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <PageHeader title="Offboarding" description="Exits in progress: clearance, asset return, final settlement and access removal." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Start an exit</Button>} />
      <Card><DataTable rows={q.data} rowKey={(r) => r.id} query={q} empty="No exits in progress" emptyHint="Start an exit when someone resigns, retires or is let go." emptyIcon={DoorOpen} onRowClick={(r) => nav(`/offboarding/${r.id}`)} cols={[
        { header: 'Employee', cell: (r) => <Person name={r.employee ?? 'Unknown'} sub={r.employee_code} size="sm" /> },
        { header: 'Type', cell: (r) => <span className="capitalize">{r.kind}</span> },
        { header: 'Last working day', cell: (r) => day(r.last_working_day) },
        { header: 'Clearance', cell: (r) => <div className="flex w-40 items-center gap-2"><Progress value={r.items_total ? (r.items_done / r.items_total) * 100 : 0} tone="success" className="flex-1" /><span className="text-xs text-muted">{r.items_done}/{r.items_total}</span></div> },
        { header: 'Status', cell: (r) => <StatusText status={r.status} /> },
      ]} /></Card>
      <StartDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

export function OffboardingDetailPage() {
  const { id } = useParams()
  const { data: me } = useMe()
  const q = useGet<Detail_>(`/offboarding/${id}`)
  const inv = ['/offboarding', '/employees', '/dashboard']
  const toggle = useSend<{ item: string; done: boolean }>('PATCH', (b) => `/offboarding/${id}/items/${b.item}`, { invalidate: inv })
  const addItem = useSend<{ department: string; title: string }>('POST', `/offboarding/${id}/items`, { invalidate: inv, onSuccess: (_, item) => setNewItem(current => current.trim() === item.title ? '' : current) })
  const save = useSend<Record<string, unknown>>('PATCH', `/offboarding/${id}`, { invalidate: inv, success: 'Saved' })
  const complete = useSend<undefined>('POST', `/offboarding/${id}/complete`, { invalidate: inv, success: 'Exit completed. Access has been removed.' })
  const cancel = useSend<undefined>('POST', `/offboarding/${id}/cancel`, { invalidate: inv, success: 'Exit cancelled' })
  const [interview, setInterview] = React.useState('')
  const [s, setS] = React.useState({ leave_encashment_days: '0', notice_pay: '0', other_additions: '0', other_deductions: '0', remarks: '' })
  const [newItem, setNewItem] = React.useState('')
  const [itemDepartment, setItemDepartment] = React.useState('HR')
  React.useEffect(() => {
    if (q.data) { setInterview(q.data.exit_interview ?? ''); setS((x) => ({ ...x, ...Object.fromEntries(Object.entries(q.data.settlement).map(([k, v]) => [k, v ?? ''])) })) }
  }, [q.data])
  if (q.isLoading) return <Skeleton className="h-64 w-full rounded-xl" />
  if (q.isError || !q.data) return <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
  const o = q.data
  const open = o.status === 'in_progress'
  const permissions = new Set(me?.permissions ?? [])
  const expenseTab = permissions.has('expenses.finance_approve') ? 'all' : 'team'
  const profileBack = { to: `/offboarding/${o.id}`, label: 'Employee exit' }
  const blockers = [o.items.some((i) => !i.done) && 'Clearance items are still open', o.open_assets.length > 0 && 'Company assets have not been returned', Number(o.loan_balance) > 0 && 'A loan balance is outstanding'].filter(Boolean) as string[]
  return (
    <>
      <Link to="/offboarding" className="mb-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" />All exits</Link>
      <PageHeader title={`${o.employee}: ${o.kind}`} description={`Notice on ${day(o.notice_date)} · last working day ${day(o.last_working_day)}`} actions={<>
        <StatusText status={o.status} className="text-sm" />
        {open && <ConfirmButton variant="ghost" size="md" label="Cancel exit" title="Cancel this exit?" message="The employee stays active and nothing else changes." confirmLabel="Cancel exit" onConfirm={() => cancel.mutate(undefined as never)} />}
        {open && <ConfirmButton variant="primary" size="md" label="Complete exit" title="Complete this exit?" message={`${o.employee} is marked as left on ${day(o.last_working_day)} and loses access to this organization. Their records are kept.`} confirmLabel="Complete exit" onConfirm={() => complete.mutate(undefined as never)} loading={complete.isPending} />}
      </>} />
      {open && blockers.length > 0 && <div className="mb-6"><Notice tone="warning" icon={CircleAlert}><p className="font-medium">Before this exit can be completed:</p><ul className="mt-1 list-disc pl-5">{blockers.map((b) => <li key={b}>{b}</li>)}</ul></Notice></div>}
      {open && blockers.length === 0 && <div className="mb-6"><Notice tone="success" icon={CheckCircle2}>Clearance is done. You can complete the exit.</Notice></div>}
      <ol className="mb-6 grid gap-3 sm:grid-cols-4" aria-label="Exit progress">{[['1', 'Notice recorded', true], ['2', 'Clearance', o.items_done === o.items_total], ['3', 'Settlement review', blockers.length === 0], ['4', 'Access removed', o.status === 'completed']].map(([n, label, done]) => <li key={n as string} className={cn('rounded-xl border p-3 text-sm', done ? 'border-success/40 bg-success-soft' : 'border-border bg-surface')}><span className="mr-2 font-bold">{n}.</span>{label}</li>)}</ol>

      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-2">
          <Card><CardHeader><CardTitle>Clearance checklist</CardTitle><span className="text-xs text-muted">{o.items_done} of {o.items_total} done</span></CardHeader>
            <ul className="divide-y divide-border">{o.items.map((i) => (
              <li key={i.id}><label className={cn('flex items-center gap-3 px-5 py-3 text-sm', open && 'cursor-pointer hover:bg-surface-2/50')}>
                <input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" disabled={!open} checked={i.done} onChange={(e) => toggle.mutate({ item: i.id, done: e.target.checked })} />
                <span className={cn('flex-1', i.done && 'text-muted line-through')}>{i.title}</span><span className="rounded bg-surface-2 px-2 py-0.5 text-xs text-muted">{i.department}</span>
              </label></li>))}</ul>
            {open && <CardBody className="flex flex-wrap gap-2 border-t border-border"><Select aria-label="Clearance owner" className="w-36" value={itemDepartment} onChange={e => setItemDepartment(e.target.value)}>{['HR', 'IT', 'Finance', 'Manager', 'Facilities'].map(d => <option key={d}>{d}</option>)}</Select><Input className="min-w-0 basis-44 flex-1" aria-label="New clearance item" placeholder="Add another step" value={newItem} onChange={(e) => setNewItem(e.target.value)} /><Button variant="outline" loading={addItem.isPending} disabled={newItem.trim().length < 3} onClick={() => addItem.mutate({ department: itemDepartment, title: newItem.trim() })}>Add</Button></CardBody>}
          </Card>

          <Card><CardHeader><CardTitle>Exit interview</CardTitle></CardHeader><CardBody className="space-y-3">
            <Textarea rows={5} aria-label="Exit interview notes" disabled={!open} placeholder="Why are they leaving? What would they change?" value={interview} onChange={(e) => setInterview(e.target.value)} />
            {open && <Button variant="outline" loading={save.isPending} onClick={() => save.mutate({ exit_interview: interview })}>Save notes</Button>}
          </CardBody></Card>

          <Card><CardHeader><CardTitle>Final settlement inputs</CardTitle></CardHeader><CardBody className="space-y-4">
            <p className="text-sm text-muted">Record the figures agreed for the final pay. They are kept with the exit for finance. The final amount itself is paid through payroll or directly.</p>
            <div className="grid gap-4 sm:grid-cols-2">
              {([['leave_encashment_days', 'Leave days to encash'], ['notice_pay', 'Notice pay (negative if recovered)'], ['other_additions', 'Other additions'], ['other_deductions', 'Other deductions']] as const).map(([k, l]) => (
                <Field key={k} id={`st-${k}`} label={l}>{(a) => <Input type="number" step="0.01" disabled={!open} value={s[k]} onChange={(e) => setS({ ...s, [k]: e.target.value })} {...a} />}</Field>))}
              <Field id="st-r" label="Remarks" className="sm:col-span-2">{(a) => <Input disabled={!open} value={s.remarks} onChange={(e) => setS({ ...s, remarks: e.target.value })} {...a} />}</Field>
            </div>
            {open && <Button variant="outline" loading={save.isPending} onClick={() => save.mutate({ settlement: { ...s, remarks: s.remarks || null } })}>Save settlement inputs</Button>}
          </CardBody></Card>
        </div>

        <div className="space-y-6">
          <Card><CardHeader><CardTitle>To settle</CardTitle></CardHeader><CardBody className="pt-2">
            <Detail rows={[
              ['Assets to return', o.open_assets.length ? <span key="a" className="text-danger">{o.open_assets.length}</span> : 'None'],
              ['Loan balance', Number(o.loan_balance) > 0 ? <span key="l" className="text-danger">{money(o.loan_balance)}</span> : 'None'],
              ['Open expense claims', o.pending_expense_claims || 'None'],
              ['Approved, unpaid expenses', Number(o.approved_unpaid_expenses) > 0 ? money(o.approved_unpaid_expenses) : 'None'],
            ]} />
            {o.open_assets.length > 0 && <ul className="mt-3 space-y-1 text-[13px]">{o.open_assets.map((a) => <li key={a.asset_id} className="flex justify-between rounded-lg bg-surface-2 px-3 py-1.5"><span>{a.name}</span><span className="text-muted">{a.serial_number}</span></li>)}</ul>}
            <div className="mt-3 flex flex-wrap gap-3 text-[13px]">
              {permissions.has('assets.manage') && <Link to={`/assets?holder_id=${o.employee_id}`} className="font-medium text-primary hover:underline">Assigned assets</Link>}
              {permissions.has('loans.manage') && <Link to={`/loans?employee_id=${o.employee_id}`} className="font-medium text-primary hover:underline">Employee loans</Link>}
              {(permissions.has('expenses.finance_approve') || permissions.has('expenses.approve')) && <Link to={`/expenses?tab=${expenseTab}&employee_id=${o.employee_id}`} className="font-medium text-primary hover:underline">Employee expenses</Link>}
              {permissions.has('employees.read') && permissions.has('payroll.read') && <Link to={`/employees/${o.employee_id}?tab=payslips`} state={{ profileBack }} className="font-medium text-primary hover:underline">Employee payslips</Link>}
            </div>
          </CardBody></Card>
          <Card><CardHeader><CardTitle>Unused leave</CardTitle></CardHeader><CardBody className="pt-2">
            {o.leave_balances.length ? <Detail rows={o.leave_balances.map((b) => [b.name, `${Number(b.available)} days`])} /> : <p className="py-2 text-sm text-muted">No leave balance this year.</p>}
          </CardBody></Card>
          {permissions.has('employees.read') && <Link to={`/employees/${o.employee_id}?tab=official`} state={{ profileBack }} className="block text-center text-[13px] font-medium text-primary hover:underline">Open employee profile</Link>}
        </div>
      </div>
    </>
  )
}
