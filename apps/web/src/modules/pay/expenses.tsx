import { useViewQuery, useViewTab } from '@/lib/view-state'
import { Paperclip, Plus, ReceiptText } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, PageHeader } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, DataTable, Person, StatusText, Tabs, type Col } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { money, today, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { useQueryClient } from '@tanstack/react-query'
import { formatDate } from '@/lib/utils'

interface Category { id: string; name: string; max_amount: string | null; requires_receipt: boolean; is_active: boolean }
interface Claim { id: string; employee: string | null; category: string | null; amount: string; approved_amount: string | null; expense_date: string; description: string; status: string; reimburse_via: string | null; manager_note: string | null; finance_note: string | null; has_receipt: boolean; in_payroll: boolean }

function ClaimDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const qc = useQueryClient()
  const cats = useGet<Category[]>('/expenses/categories')
  const [f, setF] = React.useState({ category_id: '', amount: '', expense_date: today(), description: '' })
  const [file, setFile] = React.useState<File | null>(null)
  const [busy, setBusy] = React.useState(false)
  const cat = cats.data?.find((c) => c.id === f.category_id)
  const submit = async () => {
    const form = new FormData()
    Object.entries(f).forEach(([k, v]) => form.append(k, v))
    if (file) form.append('receipt', file)
    setBusy(true)
    try {
      await uploadFile('/expenses', form)
      toast.success('Claim submitted')
      qc.invalidateQueries({ predicate: (q) => String(q.queryKey[0]).startsWith('/expenses') })
      onOpenChange(false); setF({ ...f, amount: '', description: '' }); setFile(null)
    } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Claim an expense" description="Your manager approves the claim first, then finance. You are told at each step.">
        <div className="space-y-4">
          <Field id="x-c" label="Category" hint={cat ? [cat.max_amount && `Limit ${money(cat.max_amount)} per claim`, cat.requires_receipt && 'Receipt required'].filter(Boolean).join(' · ') || undefined : undefined}>{(a) => (
            <Select value={f.category_id} onChange={(e) => setF({ ...f, category_id: e.target.value })} {...a}><option value="">Select a category</option>{cats.data?.filter((c) => c.is_active).map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</Select>)}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="x-a" label="Amount">{(a) => <Input type="number" min={0} step="0.01" value={f.amount} onChange={(e) => setF({ ...f, amount: e.target.value })} {...a} />}</Field>
            <Field id="x-d" label="Date of expense">{(a) => <Input type="date" max={today()} value={f.expense_date} onChange={(e) => setF({ ...f, expense_date: e.target.value })} {...a} />}</Field>
          </div>
          <Field id="x-n" label="What was it for?">{(a) => <Input value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} {...a} />}</Field>
          <Field id="x-f" label={cat?.requires_receipt ? 'Receipt' : 'Receipt (optional)'} hint="PDF or image, up to 10 MB.">{(a) => <Input type="file" accept=".pdf,image/png,image/jpeg" className="pt-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={busy} disabled={!f.category_id || !Number(f.amount) || f.description.trim().length < 3 || (!!cat?.requires_receipt && !file)} onClick={submit}>Submit claim</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const amountCell = (c: Claim) => (
  <span className="tabular-nums">{money(c.approved_amount ?? c.amount)}{c.approved_amount && Number(c.approved_amount) !== Number(c.amount) && <span className="ml-1.5 text-xs text-muted line-through">{money(c.amount)}</span>}</span>
)
const receiptCell = (c: Claim) => (c.has_receipt ? <a href={`/api/v1/expenses/${c.id}/receipt`} onClick={(e) => e.stopPropagation()} className="inline-flex items-center gap-1 text-[13px] text-primary hover:underline"><Paperclip className="h-3.5 w-3.5" />Receipt</a> : <span className="text-subtle">None</span>)

export function MyExpensesPage() {
  const [sp, update] = useViewQuery()
  const [open, setOpen] = React.useState(false)
  React.useEffect(() => { if (sp.get('new') === '1') { setOpen(true); update({ new: null }) } }, [sp])
  const q = useGet<Claim[]>('/expenses', { scope: 'mine' })
  const cancel = useSend<string>('POST', (id) => `/expenses/${id}/cancel`, { invalidate: ['/expenses'], success: 'Claim cancelled' })
  return (
    <>
      <PageHeader title="My expenses" description="Claims you have submitted and where each one stands." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New claim</Button>} />
      <Card><DataTable rows={q.data} rowKey={(c) => c.id} query={q} empty="No expense claims yet" emptyHint="Submit a claim with its receipt to be reimbursed." emptyIcon={ReceiptText} focusKey={sp.get('record')} cols={[
        { header: 'Date', cell: (c) => formatDate(c.expense_date, { dateStyle: 'medium' }) },
        { header: 'Expense', cell: (c) => <div><p className="font-medium">{c.description}</p><p className="text-xs text-muted">{c.category}{(c.finance_note || c.manager_note) && ` · Note: ${c.finance_note || c.manager_note}`}</p></div> },
        { header: 'Amount', right: true, cell: amountCell },
        { header: 'Receipt', cell: receiptCell },
        { header: 'Status', cell: (c) => <div className="flex items-center gap-2"><StatusText status={c.status} />{c.status === 'approved' && <span className="text-xs text-muted">{c.reimburse_via === 'payroll' ? 'Paid with next salary' : 'Paid directly'}</span>}</div> },
        { header: '', right: true, cell: (c) => (['submitted', 'manager_approved'].includes(c.status) ? <ConfirmButton variant="ghost" label="Cancel" title="Cancel this claim?" message="The claim is withdrawn and will not be paid." confirmLabel="Cancel claim" onConfirm={() => cancel.mutate(c.id)} /> : null) },
      ]} /></Card>
      <ClaimDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

function FinanceDialog({ claim, onClose }: { claim: Claim | null; onClose: () => void }) {
  const [amount, setAmount] = React.useState('')
  const [via, setVia] = React.useState('payroll')
  const [note, setNote] = React.useState('')
  React.useEffect(() => { if (claim) { setAmount(claim.amount); setNote('') } }, [claim])
  const m = useSend<Record<string, unknown>>('POST', `/expenses/${claim?.id}/finance-decision`, { invalidate: ['/expenses', '/dashboard'], success: 'Decision saved', onSuccess: onClose })
  return (
    <Dialog open={!!claim} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title="Finance decision" description={claim ? `${claim.employee}: ${claim.description}, claimed ${money(claim.amount)}` : undefined}>
        <div className="space-y-4">
          <Field id="fd-a" label="Approved amount" hint="Lower this to approve part of the claim.">{(a) => <Input type="number" min={0} max={claim?.amount} step="0.01" value={amount} onChange={(e) => setAmount(e.target.value)} {...a} />}</Field>
          <Field id="fd-v" label="Reimburse through">{(a) => <Select value={via} onChange={(e) => setVia(e.target.value)} {...a}><option value="payroll">Next payroll run (added to the payslip, not taxed)</option><option value="direct">Direct payment (mark as paid by hand)</option></Select>}</Field>
          <Field id="fd-n" label="Note to the employee (optional)">{(a) => <Input value={note} onChange={(e) => setNote(e.target.value)} {...a} />}</Field>
        </div>
        <DialogFooter>
          <Button variant="danger-soft" loading={m.isPending} onClick={() => m.mutate({ approve: false, note: note || null })}>Reject</Button>
          <Button loading={m.isPending} disabled={!Number(amount)} onClick={() => m.mutate({ approve: true, approved_amount: amount, reimburse_via: via, note: note || null })}>Approve</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Categories() {
  const q = useGet<Category[]>('/expenses/categories')
  const [open, setOpen] = React.useState(false)
  const [f, setF] = React.useState({ name: '', max_amount: '', requires_receipt: false })
  const m = useSend<Record<string, unknown>>('POST', '/expenses/categories', { invalidate: ['/expenses'], success: 'Category added', onSuccess: () => { setOpen(false); setF({ name: '', max_amount: '', requires_receipt: false }) } })
  return (
    <>
      <div className="mb-4 flex justify-end"><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add category</Button></div>
      <Card><DataTable rows={q.data} rowKey={(c) => c.id} query={q} empty="No categories" cols={[
        { header: 'Category', cell: (c) => <span className="font-semibold">{c.name}</span> },
        { header: 'Limit per claim', cell: (c) => (c.max_amount ? money(c.max_amount) : 'No limit') },
        { header: 'Receipt', cell: (c) => (c.requires_receipt ? <Badge tone="warning">Required</Badge> : 'Optional') },
      ]} /></Card>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent title="Add an expense category">
        <div className="space-y-4">
          <Field id="ec-n" label="Name">{(a) => <Input value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} {...a} />}</Field>
          <Field id="ec-m" label="Limit per claim (optional)">{(a) => <Input type="number" min={0} value={f.max_amount} onChange={(e) => setF({ ...f, max_amount: e.target.value })} {...a} />}</Field>
          <label className="flex cursor-pointer items-center gap-2.5 text-sm"><input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" checked={f.requires_receipt} onChange={(e) => setF({ ...f, requires_receipt: e.target.checked })} />A receipt is required</label>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={f.name.trim().length < 2} onClick={() => m.mutate({ name: f.name, max_amount: f.max_amount || null, requires_receipt: f.requires_receipt })}>Add category</Button></DialogFooter>
      </DialogContent></Dialog>
    </>
  )
}

export function ExpensesPage() {
  const { data: me } = useMe()
  const finance = !!me?.permissions.includes('expenses.finance_approve')
  const manager = !!me?.permissions.includes('expenses.approve')
  type T = 'team' | 'finance' | 'all' | 'categories'
  const tabs: { id: T; label: string }[] = []
  if (manager) tabs.push({ id: 'team', label: 'My team' })
  if (finance) tabs.push({ id: 'finance', label: 'Finance queue' }, { id: 'all', label: 'All claims' }, { id: 'categories', label: 'Categories' })
  const [tab, setTab] = useViewTab(tabs.map(item => item.id), finance ? 'finance' : 'team')
  const [params, update] = useViewQuery()
  const employeeId = params.get('employee_id')
  const [deciding, setDeciding] = React.useState<Claim | null>(null)
  const q = useGet<Claim[]>('/expenses', { scope: tab === 'team' ? 'team' : 'all', employee_id: employeeId || undefined }, tab !== 'categories')
  const managerDecide = useSend<{ id: string; approve: boolean }>('POST', (b) => `/expenses/${b.id}/manager-decision`, { invalidate: ['/expenses', '/dashboard'], success: 'Decision saved' })
  const paid = useSend<string>('POST', (id) => `/expenses/${id}/reimburse`, { invalidate: ['/expenses'], success: 'Marked as reimbursed' })
  const rows = tab === 'finance' ? (q.data ?? []).filter((c) => ['submitted', 'manager_approved', 'approved'].includes(c.status)) : q.data
  const cols: Col<Claim>[] = [
    { header: 'Employee', cell: (c) => <Person name={c.employee ?? 'Unknown'} sub={formatDate(c.expense_date, { dateStyle: 'medium' })} size="sm" /> },
    { header: 'Expense', cell: (c) => <div><p className="font-medium">{c.description}</p><p className="text-xs text-muted">{c.category}</p></div> },
    { header: 'Amount', right: true, cell: amountCell },
    { header: 'Receipt', cell: receiptCell },
    { header: 'Status', cell: (c) => <div className="flex flex-wrap items-center gap-1.5"><StatusText status={c.status} />{c.in_payroll && <Badge tone="info">In payroll run</Badge>}</div> },
    { header: '', right: true, cell: (c) => (
      <div className="flex justify-end gap-2">
        {tab === 'team' && c.status === 'submitted' && <><Button size="sm" onClick={() => managerDecide.mutate({ id: c.id, approve: true })}>Approve</Button><Button size="sm" variant="danger-soft" onClick={() => managerDecide.mutate({ id: c.id, approve: false })}>Reject</Button></>}
        {tab !== 'team' && finance && ['submitted', 'manager_approved'].includes(c.status) && <Button size="sm" onClick={() => setDeciding(c)}>Review</Button>}
        {tab !== 'team' && finance && c.status === 'approved' && c.reimburse_via === 'direct' && <ConfirmButton variant="outline" label="Mark as paid" title="Mark this claim as reimbursed?" message={`Confirm that ${money(c.approved_amount)} has been paid to ${c.employee}. This cannot be repeated.`} confirmLabel="Mark as paid" onConfirm={() => paid.mutate(c.id)} />}
        {tab !== 'team' && c.status === 'approved' && c.reimburse_via === 'payroll' && <span className="text-xs text-muted">Paid with next salary</span>}
      </div>) },
  ]
  return (
    <>
      <PageHeader title="Expenses" description="Review and reimburse expense claims. Claims paid through payroll are settled when the run is finalized." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {employeeId && tab !== 'categories' && <Button className="mb-4" variant="ghost" onClick={() => update({ employee_id: null, record: null })}>Show all employees’ expenses</Button>}
      {tab === 'categories' ? <Categories /> : <Card><DataTable rows={rows} rowKey={(c) => c.id} query={q} empty="No claims here" emptyIcon={ReceiptText} focusKey={params.get('record')} cols={cols} /></Card>}
      <FinanceDialog claim={deciding} onClose={() => setDeciding(null)} />
    </>
  )
}
