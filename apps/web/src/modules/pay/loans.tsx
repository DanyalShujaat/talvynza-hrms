import { useRecordFocus, useViewQuery } from '@/lib/view-state'
import { HandCoins, Plus } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, DataTable, Person, Progress, SlideOver, StatusText } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { money, today, useGet, useSend } from '@/lib/hooks'
import { formatDate } from '@/lib/utils'

interface Loan { id: string; employee: string | null; kind: string; principal: string; installments: number; reason: string | null; status: string; decision_note: string | null; disbursed_on: string | null; outstanding: string | null; created_at: string }
interface Installment { id: string; seq: number; due_date: string; amount: string; status: string; method: string | null; paid_on: string | null; in_payroll: boolean }
interface LoanDetail extends Loan { schedule: Installment[] }

const kindLabel = (k: string) => (k === 'advance' ? 'Salary advance' : 'Loan')

function RequestDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const [f, setF] = React.useState({ kind: 'advance', principal: '', installments: 1, reason: '' })
  const m = useSend<Record<string, unknown>>('POST', '/loans', { invalidate: ['/loans'], success: 'Request submitted', onSuccess: () => { onOpenChange(false); setF({ kind: 'advance', principal: '', installments: 1, reason: '' }) } })
  const each = Number(f.principal) && f.installments ? Number(f.principal) / f.installments : 0
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Request a loan or advance" description="Repayments are deducted from your salary each month once the amount is paid out.">
        <div className="space-y-4">
          <Field id="ln-k" label="Type">{(a) => <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value, installments: e.target.value === 'advance' ? Math.min(f.installments, 3) : f.installments })} {...a}><option value="advance">Salary advance (repaid within 3 months)</option><option value="loan">Loan (repaid over up to 60 months)</option></Select>}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="ln-p" label="Amount">{(a) => <Input type="number" min={0} value={f.principal} onChange={(e) => setF({ ...f, principal: e.target.value })} {...a} />}</Field>
            <Field id="ln-i" label="Monthly installments">{(a) => <Input type="number" min={1} max={f.kind === 'advance' ? 3 : 60} value={f.installments} onChange={(e) => setF({ ...f, installments: Number(e.target.value) })} {...a} />}</Field>
          </div>
          {each > 0 && <p className="rounded-lg bg-surface-2 px-3 py-2 text-[13px]">About <span className="font-semibold">{money(each)}</span> deducted from each salary for {f.installments} month{f.installments === 1 ? '' : 's'}.</p>}
          <Field id="ln-r" label="Reason">{(a) => <Input value={f.reason} onChange={(e) => setF({ ...f, reason: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={!Number(f.principal) || f.installments < 1} onClick={() => m.mutate({ kind: f.kind, principal: f.principal, installments: f.installments, reason: f.reason || null })}>Submit request</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Schedule({ loan, manage }: { loan: LoanDetail; manage: boolean }) {
  const repay = useSend<Record<string, unknown>>('POST', `/loans/${loan.id}/repay`, { invalidate: ['/loans'], success: 'Repayment recorded' })
  const paid = loan.schedule.filter((i) => i.status === 'paid').reduce((a, i) => a + Number(i.amount), 0)
  return (
    <div className="space-y-5">
      <div>
        <div className="flex items-baseline justify-between"><span className="text-sm text-muted">Repaid</span><span className="font-display text-xl font-bold">{money(paid)} <span className="font-sans text-sm font-normal text-muted">of {money(loan.principal)}</span></span></div>
        <Progress className="mt-2" tone="success" value={(paid / Number(loan.principal)) * 100} />
      </div>
      <ul className="divide-y divide-border rounded-xl border border-border">
        {loan.schedule.map((i) => (
          <li key={i.id} className="flex items-center justify-between gap-3 px-4 py-2.5 text-sm">
            <span><span className="font-medium">{formatDate(i.due_date, { month: 'long', year: 'numeric' })}</span><span className="ml-2 text-muted tabular-nums">{money(i.amount)}</span></span>
            <span className="flex items-center gap-2">
              {i.in_payroll && i.status === 'due' && <Badge tone="info">In payroll run</Badge>}
              {i.status === 'paid' && <span className="text-xs text-muted">{i.method === 'payroll' ? 'From salary' : 'Paid directly'}</span>}
              <StatusText status={i.status} />
              {manage && i.status === 'due' && !i.in_payroll && <ConfirmButton variant="outline" label="Mark paid" title="Record this installment as paid?" message={`${money(i.amount)} was repaid outside payroll. It will not be deducted from salary.`} confirmLabel="Record payment" onConfirm={() => repay.mutate({ installment_ids: [i.id] })} />}
            </span>
          </li>))}
      </ul>
      {manage && loan.status === 'active' && <ConfirmButton variant="outline" size="md" label="Settle the whole balance" title="Settle this loan?" message={`Records ${money(loan.outstanding)} as repaid outside payroll and closes the loan.`} confirmLabel="Settle loan" onConfirm={() => repay.mutate({ settle_all: true })} />}
    </div>
  )
}

function LoanPanel({ id, manage, onClose }: { id: string | null; manage: boolean; onClose: () => void }) {
  const q = useGet<LoanDetail>(`/loans/${id}`, undefined, !!id)
  return (
    <SlideOver open={!!id} onOpenChange={(o) => !o && onClose()} title={q.data ? `${kindLabel(q.data.kind)} of ${money(q.data.principal)}` : 'Loan'}>
      {q.isLoading ? <Skeleton className="h-48 w-full" /> : q.isError || !q.data ? <ErrorState message={errorMessage(q.error)} /> : (
        <div className="space-y-5">
          <div className="flex flex-wrap items-center gap-2 text-sm"><StatusText status={q.data.status} />{q.data.employee && <span className="text-muted">{q.data.employee}</span>}{q.data.disbursed_on && <span className="text-muted">Paid out {formatDate(q.data.disbursed_on, { dateStyle: 'medium' })}</span>}</div>
          {q.data.reason && <p className="text-sm">{q.data.reason}</p>}
          {q.data.schedule.length ? <Schedule loan={q.data} manage={manage} /> : <p className="rounded-lg bg-surface-2 px-3 py-3 text-sm text-muted">The repayment schedule is created when the amount is paid out.</p>}
        </div>)}
    </SlideOver>
  )
}

export function MyLoansPage() {
  const [params] = useViewQuery()
  const record = params.get('record')
  const focusRow = useRecordFocus(record)
  const [open, setOpen] = React.useState(false)
  const [view, setView] = React.useState<string | null>(null)
  const q = useGet<Loan[]>('/loans', { scope: 'mine' })
  const cancel = useSend<string>('POST', (id) => `/loans/${id}/cancel`, { invalidate: ['/loans'], success: 'Request cancelled' })
  return (
    <>
      <PageHeader title="Loans and advances" description="Your requests, balances and repayment schedules." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New request</Button>} />
      {q.isLoading ? <Skeleton className="h-32 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} /></Card> : !q.data?.length ? <Card><EmptyState title="No loans or advances" description="Request a salary advance or a loan and follow its repayment here." icon={HandCoins} /></Card> : (
        <div className="grid gap-4 md:grid-cols-2">{q.data.map((l) => (
          <Card key={l.id} ref={l.id === record ? focusRow : undefined} tabIndex={l.id === record ? -1 : undefined} className={l.id === record ? 'scroll-mt-28 border-primary bg-primary-soft' : undefined}><CardBody className="space-y-3">
            <div className="flex items-start justify-between gap-3"><div><p className="text-[13px] text-muted">{kindLabel(l.kind)} · requested {formatDate(l.created_at, { dateStyle: 'medium' })}</p><p className="font-display text-2xl font-bold">{money(l.principal)}</p></div><StatusText status={l.status} /></div>
            {l.outstanding !== null && <><Progress tone="success" value={(1 - Number(l.outstanding) / Number(l.principal)) * 100} /><p className="text-[13px] text-muted">{money(l.outstanding)} still to repay over {l.installments} installment{l.installments === 1 ? '' : 's'}</p></>}
            {l.decision_note && <p className="text-[13px] text-muted">Note: {l.decision_note}</p>}
            <div className="flex gap-2">
              {['active', 'closed'].includes(l.status) && <Button variant="outline" size="sm" onClick={() => setView(l.id)}>Repayment schedule</Button>}
              {['requested', 'approved'].includes(l.status) && <ConfirmButton variant="ghost" label="Cancel request" title="Cancel this request?" message="The request is withdrawn." confirmLabel="Cancel request" onConfirm={() => cancel.mutate(l.id)} />}
            </div>
          </CardBody></Card>))}</div>)}
      <RequestDialog open={open} onOpenChange={setOpen} /><LoanPanel id={view} manage={false} onClose={() => setView(null)} />
    </>
  )
}

function DisburseDialog({ loan, onClose }: { loan: Loan | null; onClose: () => void }) {
  const next = new Date(); next.setMonth(next.getMonth() + 1)
  const [on, setOn] = React.useState(today())
  const [first, setFirst] = React.useState(next.toISOString().slice(0, 7))
  const m = useSend<Record<string, unknown>>('POST', `/loans/${loan?.id}/disburse`, { invalidate: ['/loans'], success: 'Loan paid out and schedule created', onSuccess: onClose })
  return (
    <Dialog open={!!loan} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Pay out" description={loan ? `${money(loan.principal)} to ${loan.employee}, repaid in ${loan.installments} monthly installment${loan.installments === 1 ? '' : 's'} through payroll.` : undefined}>
        <div className="grid grid-cols-2 gap-3">
          <Field id="ds-o" label="Paid out on">{(a) => <Input type="date" value={on} onChange={(e) => setOn(e.target.value)} {...a} />}</Field>
          <Field id="ds-f" label="First deduction in">{(a) => <Input type="month" value={first} onChange={(e) => setFirst(e.target.value)} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate({ disbursed_on: on, first_due_month: first })}>Confirm payout</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function LoansPage() {
  const [query, update] = useViewQuery()
  const status = query.get('status') ?? ''
  const employeeId = query.get('employee_id')
  const [view, setView] = React.useState<string | null>(null)
  const [paying, setPaying] = React.useState<Loan | null>(null)
  const q = useGet<Loan[]>('/loans', { scope: 'all', status: status || undefined, employee_id: employeeId || undefined })
  const decide = useSend<{ id: string; approve: boolean }>('POST', (b) => `/loans/${b.id}/decision`, { invalidate: ['/loans', '/dashboard'], success: 'Decision saved' })
  return (
    <>
      <PageHeader title="Loans and advances" description="Approve requests, pay them out and follow repayment. Installments are deducted in payroll automatically." />
      <div className="mb-4 flex flex-wrap items-center gap-3"><Select aria-label="Filter by status" className="w-48" value={status} onChange={(e) => update({ status: e.target.value, record: null })}>{[['', 'All statuses'], ['requested', 'Waiting for approval'], ['approved', 'Approved, not paid out'], ['active', 'Being repaid'], ['closed', 'Closed'], ['rejected', 'Rejected'], ['cancelled', 'Cancelled']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>{employeeId && <Button variant="ghost" onClick={() => update({ employee_id: null, record: null })}>Show all employees’ loans</Button>}</div>
      <Card><DataTable rows={q.data} rowKey={(l) => l.id} query={q} empty="No loans or advances" emptyIcon={HandCoins} focusKey={query.get('record')} cols={[
        { header: 'Employee', cell: (l) => <Person name={l.employee ?? 'Unknown'} sub={`${kindLabel(l.kind)} · ${formatDate(l.created_at, { dateStyle: 'medium' })}`} size="sm" /> },
        { header: 'Reason', cell: (l) => <span className="line-clamp-1 max-w-56 text-muted">{l.reason ?? ''}</span> },
        { header: 'Amount', right: true, cell: (l) => <span className="font-semibold">{money(l.principal)}</span> },
        { header: 'Installments', right: true, cell: (l) => l.installments },
        { header: 'Outstanding', right: true, cell: (l) => (l.outstanding !== null ? money(l.outstanding) : '') },
        { header: 'Status', cell: (l) => <StatusText status={l.status} /> },
        { header: '', right: true, cell: (l) => (
          <div className="flex justify-end gap-2">
            {l.status === 'requested' && <><Button size="sm" onClick={() => decide.mutate({ id: l.id, approve: true })}>Approve</Button><Button size="sm" variant="danger-soft" onClick={() => decide.mutate({ id: l.id, approve: false })}>Reject</Button></>}
            {l.status === 'approved' && <Button size="sm" onClick={() => setPaying(l)}>Pay out</Button>}
            {['active', 'closed'].includes(l.status) && <Button size="sm" variant="outline" onClick={() => setView(l.id)}>Schedule</Button>}
          </div>) },
      ]} /></Card>
      <DisburseDialog loan={paying} onClose={() => setPaying(null)} /><LoanPanel id={view} manage onClose={() => setView(null)} />
    </>
  )
}
