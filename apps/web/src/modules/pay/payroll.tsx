import { Banknote, Download, ExternalLink, Info, Landmark, Plus, Printer, Receipt, ShieldCheck, Wallet } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, DataTable, Person, StatTile, StatusText, Tabs } from '@/components/ui/extras'
import { Checkbox, Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { money, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { SalaryTemplates } from './salary-templates'

interface Run { id: string; period_start: string; period_end: string; proration: string; status: string; currency: string; total_gross: string; total_deductions: string; total_net: string; statutory_status: string; statutory_notice: string; finalized_at: string | null }
interface Entry { id: string; employee: string; employee_code: string; department: string | null; gross: string; deductions: string; net: string; income_tax: string; unpaid_days: string; exceptions: string[] }
interface RunDetail extends Run { entries: Entry[]; total_income_tax: string; total_employer_contributions: string }
interface Line { name: string; amount: string }
export interface Slip { organization: string; employee: string; employee_code: string; department: string | null; designation: string | null; joining_date: string; period_start: string; period_end: string; currency: string; gross: string; deductions: string; net: string; taxable_income: string; income_tax: string; unpaid_days: string; status: string; earnings: Line[]; deduction_lines: Line[]; employer_contributions: Line[]; statutory_notice: string }

const monthOf = (r: { period_start: string; period_end: string }) => {
  const s = new Date(r.period_start + 'T00:00:00'), e = new Date(r.period_end + 'T00:00:00')
  const full = s.getDate() === 1 && s.getMonth() === e.getMonth() && new Date(e.getFullYear(), e.getMonth() + 1, 0).getDate() === e.getDate()
  return full ? s.toLocaleDateString(undefined, { month: 'long', year: 'numeric' }) : `${formatDate(r.period_start, { dateStyle: 'medium' })} to ${formatDate(r.period_end, { dateStyle: 'medium' })}`
}

export function SlipView({ slip }: { slip: Slip }) {
  const c = slip.currency
  const Lines = ({ title, rows, total }: { title: string; rows: Line[]; total: string }) => (
    <div className="overflow-hidden rounded-xl border border-border">
      <p className="bg-surface-2 px-4 py-2 text-[11px] font-semibold uppercase tracking-wider text-muted">{title}</p>
      <ul className="divide-y divide-border">
        {rows.length === 0 && <li className="px-4 py-2.5 text-sm text-muted">None</li>}
        {rows.map((r) => <li key={r.name} className="flex justify-between px-4 py-2.5 text-sm"><span>{r.name}</span><span className="tabular-nums">{money(r.amount)}</span></li>)}
      </ul>
      <p className="flex justify-between border-t border-border bg-surface-2/60 px-4 py-2.5 text-sm font-semibold"><span>Total</span><span className="tabular-nums">{money(total)}</span></p>
    </div>
  )
  return (
    <div className="space-y-5 text-sm">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-4">
        <div><p className="font-display text-lg font-bold">{slip.organization}</p><p className="text-muted">Payslip for {monthOf(slip)}</p></div>
        {slip.status !== 'finalized' && <Badge tone="warning">Draft, not final</Badge>}
      </div>
      <dl className="grid grid-cols-2 gap-x-6 gap-y-2 sm:grid-cols-4">
        {[['Employee', slip.employee], ['Employee ID', slip.employee_code], ['Designation', slip.designation ?? 'Not set'], ['Department', slip.department ?? 'Not set']].map(([k, v]) => (
          <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="font-medium">{v}</dd></div>))}
      </dl>
      <div className="grid gap-4 sm:grid-cols-2"><Lines title="Earnings" rows={slip.earnings} total={slip.gross} /><Lines title="Deductions" rows={slip.deduction_lines} total={slip.deductions} /></div>
      <div className="brand-gradient flex items-center justify-between rounded-xl px-5 py-4 text-white">
        <span className="text-sm font-medium opacity-90">Net pay</span><span className="font-display text-2xl font-extrabold tabular-nums">{money(slip.net, c)}</span>
      </div>
      <dl className="grid gap-2 text-[13px] text-muted sm:grid-cols-2">
        <div className="flex justify-between gap-4"><dt>Taxable income this period</dt><dd className="tabular-nums text-fg">{money(slip.taxable_income)}</dd></div>
        {Number(slip.unpaid_days) > 0 && <div className="flex justify-between gap-4"><dt>Unpaid leave days</dt><dd className="text-fg">{Number(slip.unpaid_days)}</dd></div>}
        {slip.employer_contributions.map((e) => <div key={e.name} className="flex justify-between gap-4"><dt>{e.name}, paid by the employer</dt><dd className="tabular-nums text-fg">{money(e.amount)}</dd></div>)}
      </dl>
      <p className="border-t border-border pt-3 text-xs text-muted">{slip.statutory_notice}</p>
    </div>
  )
}

function SlipDialog({ path, onClose }: { path: string | null; onClose: () => void }) {
  const q = useGet<Slip>(path ?? '/payslips/none', undefined, !!path)
  return (
    <Dialog open={!!path} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-2xl" title="Payslip">
        {q.isLoading ? <Skeleton className="h-64 w-full" /> : q.isError || !q.data ? <ErrorState message={errorMessage(q.error)} /> : (<><SlipView slip={q.data} /><div className="no-print mt-5 flex justify-end"><Button variant="outline" onClick={() => window.print()}><Printer className="h-4 w-4" />Print</Button></div></>)}
      </DialogContent>
    </Dialog>
  )
}

function NewRunDialog() {
  const nav = useNavigate()
  const now = new Date()
  const iso = (d: Date) => new Date(d.getTime() - d.getTimezoneOffset() * 60000).toISOString().slice(0, 10)
  const [open, setOpen] = React.useState(false)
  const [f, setF] = React.useState({ period_start: iso(new Date(now.getFullYear(), now.getMonth() - 1, 1)), period_end: iso(new Date(now.getFullYear(), now.getMonth(), 0)), proration: 'calendar_days' })
  const m = useSend<typeof f, Run>('POST', '/payroll/runs', { invalidate: ['/payroll'], success: 'Payroll run created', onSuccess: (r) => nav(`/payroll/runs/${r.id}`) })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New payroll run</Button>
      <DialogContent title="New payroll run" description="One run per pay period. Income tax is calculated for periods that cover a full calendar month.">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field id="r-s" label="Period start">{(a) => <Input type="date" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} {...a} />}</Field>
            <Field id="r-e" label="Period end">{(a) => <Input type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} {...a} />}</Field>
          </div>
          <Field id="r-p" label="Proration" hint="How pay is split for people who join, leave or get a raise during the period.">{(a) => <Select value={f.proration} onChange={(e) => setF({ ...f, proration: e.target.value })} {...a}><option value="calendar_days">Calendar days</option><option value="working_days">Working days</option></Select>}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate(f)}>Create run</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Runs() {
  const q = useGet<Run[]>('/payroll/runs')
  const nav = useNavigate()
  return (
    <Card>
      <DataTable rows={q.data} rowKey={(r) => r.id} query={q} empty="No payroll runs yet" emptyHint="Add salaries to employees, then create the first run." emptyIcon={Wallet} onRowClick={(r) => nav(`/payroll/runs/${r.id}`)} cols={[
        { header: 'Pay period', cell: (r) => <span className="font-semibold">{monthOf(r)}</span> },
        { header: 'Status', cell: (r) => <StatusText status={r.status} /> },
        { header: 'Gross', right: true, cell: (r) => money(r.total_gross) },
        { header: 'Deductions', right: true, cell: (r) => money(r.total_deductions) },
        { header: 'Net pay', right: true, cell: (r) => <span className="font-semibold">{money(r.total_net, r.currency)}</span> },
      ]} />
    </Card>
  )
}

interface Comp { id: string; name: string; kind: string; calc: string; default_value: string; taxable: boolean; exempt_percent_of_basic: string | null; is_active: boolean }
function Components() {
  const q = useGet<Comp[]>('/payroll/components')
  const { data: me } = useMe()
  const [open, setOpen] = React.useState(false)
  const blank = { name: '', kind: 'earning', calc: 'fixed', default_value: '0', taxable: true, exempt: '' }
  const [f, setF] = React.useState(blank)
  const m = useSend<Record<string, unknown>>('POST', '/payroll/components', { invalidate: ['/payroll'], success: 'Component added', onSuccess: () => { setOpen(false); setF(blank) } })
  const treatment = (c: Comp) => (c.kind === 'deduction' ? '' : !c.taxable ? 'Not taxable' : c.exempt_percent_of_basic ? `Exempt up to ${Number(c.exempt_percent_of_basic)}% of basic` : 'Taxable')
  return (
    <>
      {me?.permissions.includes('salary.manage') && <div className="mb-4 flex justify-end"><Dialog open={open} onOpenChange={setOpen}><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add component</Button>
        <DialogContent title="Add a salary component" description="Allowances and deductions that are attached to an employee's salary. Basic salary needs no component.">
          <div className="space-y-4">
            <Field id="c-n" label="Name">{(a) => <Input placeholder="House rent allowance" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} {...a} />}</Field>
            <div className="grid grid-cols-2 gap-3">
              <Field id="c-k" label="Type">{(a) => <Select value={f.kind} onChange={(e) => setF({ ...f, kind: e.target.value })} {...a}><option value="earning">Earning</option><option value="deduction">Deduction</option></Select>}</Field>
              <Field id="c-c" label="Calculation">{(a) => <Select value={f.calc} onChange={(e) => setF({ ...f, calc: e.target.value })} {...a}><option value="fixed">Fixed amount</option><option value="percent_of_basic">Percent of basic</option></Select>}</Field>
            </div>
            <Field id="c-v" label={f.calc === 'fixed' ? 'Default amount per period' : 'Default percent of basic'}>{(a) => <Input type="number" min={0} step="0.01" value={f.default_value} onChange={(e) => setF({ ...f, default_value: e.target.value })} {...a} />}</Field>
            {f.kind === 'earning' && <>
              <Checkbox label="Counts as taxable income" checked={f.taxable} onChange={(e) => setF({ ...f, taxable: e.target.checked })} />
              {f.taxable && <Field id="c-x" label="Exempt up to this percent of basic (optional)" hint="Example: a medical allowance is exempt up to 10% of basic salary. Leave blank if the whole amount is taxable.">{(a) => <Input type="number" min={0} max={100} step="0.5" value={f.exempt} onChange={(e) => setF({ ...f, exempt: e.target.value })} {...a} />}</Field>}
            </>}
          </div>
          <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button loading={m.isPending} disabled={f.name.trim().length < 2} onClick={() => m.mutate({ name: f.name, kind: f.kind, calc: f.calc, default_value: f.default_value, taxable: f.taxable, exempt_percent_of_basic: f.kind === 'earning' && f.taxable && f.exempt ? f.exempt : null })}>Add component</Button></DialogFooter>
        </DialogContent></Dialog></div>}
      <Card><DataTable rows={q.data} rowKey={(c) => c.id} query={q} empty="No salary components" emptyHint="Add allowances and deductions here, then attach them to salaries." emptyIcon={Banknote} cols={[
        { header: 'Component', cell: (c) => <span className="font-semibold">{c.name}</span> },
        { header: 'Type', cell: (c) => <Badge tone={c.kind === 'earning' ? 'success' : 'danger'}>{c.kind === 'earning' ? 'Earning' : 'Deduction'}</Badge> },
        { header: 'Default', cell: (c) => (c.calc === 'fixed' ? money(c.default_value) : `${Number(c.default_value)}% of basic`) },
        { header: 'Income tax', cell: (c) => treatment(c) },
      ]} /></Card>
    </>
  )
}

interface TaxYear { tax_year: number; period: string; law: string; verification: string; sources: string[]; slabs: { from: string; to: string | null; fixed: string; rate_percent: string }[]; surcharge: null | { over: string; rate_percent: string } }
interface Statutory { country: string; supported: boolean; income_tax: boolean; eobi_enabled: boolean; eobi_wage_base: string | null; eobi_employee_percent: string; eobi_employer_percent: string; current_tax_year: number; current_rules_loaded: boolean; tax_years: TaxYear[] }

function StatutorySettings() {
  const q = useGet<Statutory>('/payroll/statutory')
  const { data: me } = useMe()
  const canEdit = !!me?.permissions.includes('salary.manage')
  const [f, setF] = React.useState<{ income_tax: boolean; eobi_enabled: boolean; eobi_wage_base: string; eobi_employee_percent: string; eobi_employer_percent: string } | null>(null)
  const [year, setYear] = React.useState<number | null>(null)
  React.useEffect(() => { if (q.data) { setF({ income_tax: q.data.income_tax, eobi_enabled: q.data.eobi_enabled, eobi_wage_base: q.data.eobi_wage_base ?? '', eobi_employee_percent: q.data.eobi_employee_percent, eobi_employer_percent: q.data.eobi_employer_percent }); setYear((y) => y ?? q.data.current_tax_year) } }, [q.data])
  const save = useSend<Record<string, unknown>>('PUT', '/payroll/statutory', { invalidate: ['/payroll'], success: 'Statutory settings saved' })
  if (q.isLoading || !f) return <Skeleton className="h-64 w-full rounded-xl" />
  if (q.isError || !q.data) return <Card><ErrorState message={errorMessage(q.error)} /></Card>
  const s = q.data
  if (!s.supported) return <Card><EmptyState icon={Landmark} title="Statutory rules are not available for this country" description={`Tax and social security rules are loaded for Pakistan only. Payroll for ${s.country} runs without statutory deductions, and every payslip says so.`} /></Card>
  const ty = s.tax_years.find((t) => t.tax_year === year) ?? s.tax_years[0]
  const n = (v: string | null) => (v === null ? 'and above' : Number(v).toLocaleString())
  return (
    <div className="grid gap-6 xl:grid-cols-5">
      <div className="space-y-6 xl:col-span-2">
        <Card><CardHeader><CardTitle>Income tax on salary</CardTitle><StatusText status={f.income_tax ? 'active' : 'draft'} /></CardHeader><CardBody className="space-y-4">
          <p className="text-sm text-muted">Tax is withheld every month under section 149 of the Income Tax Ordinance 2001. Each month the year's salary is projected, the year's tax is worked out from the table, and what is still owed is spread over the remaining months of the tax year.</p>
          <Checkbox label="Withhold income tax from salaries" disabled={!canEdit} checked={f.income_tax} onChange={(e) => setF({ ...f, income_tax: e.target.checked })} />
          {!s.current_rules_loaded && <Notice tone="warning" icon={Info}>No verified rates are loaded for tax year {s.current_tax_year}. Runs in that year are calculated without income tax until the new Finance Act table is added.</Notice>}
        </CardBody></Card>
        <Card><CardHeader><CardTitle>EOBI</CardTitle><StatusText status={f.eobi_enabled ? 'active' : 'draft'} /></CardHeader><CardBody className="space-y-4">
          <p className="text-sm text-muted">Employees' Old-Age Benefits contributions are a percentage of the notified minimum wage, not of actual salary. Enter the wage base your EOBI office currently applies. It is not filled in for you because it changes with each minimum wage notification.</p>
          <Checkbox label="Deduct EOBI from salaries" disabled={!canEdit} checked={f.eobi_enabled} onChange={(e) => setF({ ...f, eobi_enabled: e.target.checked })} />
          <Field id="e-b" label="Monthly wage base (PKR)">{(a) => <Input type="number" min={0} disabled={!canEdit} value={f.eobi_wage_base} onChange={(e) => setF({ ...f, eobi_wage_base: e.target.value })} {...a} />}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="e-e" label="Employee share (%)">{(a) => <Input type="number" min={0} step="0.1" disabled={!canEdit} value={f.eobi_employee_percent} onChange={(e) => setF({ ...f, eobi_employee_percent: e.target.value })} {...a} />}</Field>
            <Field id="e-r" label="Employer share (%)">{(a) => <Input type="number" min={0} step="0.1" disabled={!canEdit} value={f.eobi_employer_percent} onChange={(e) => setF({ ...f, eobi_employer_percent: e.target.value })} {...a} />}</Field>
          </div>
          {f.eobi_wage_base && <p className="text-[13px] text-muted">Per employee each month: {money(Number(f.eobi_wage_base) * Number(f.eobi_employee_percent) / 100, 'PKR')} deducted, {money(Number(f.eobi_wage_base) * Number(f.eobi_employer_percent) / 100, 'PKR')} paid by the employer.</p>}
        </CardBody></Card>
        {canEdit && <Button loading={save.isPending} onClick={() => save.mutate({ income_tax: f.income_tax, eobi_enabled: f.eobi_enabled, eobi_wage_base: f.eobi_wage_base || null, eobi_employee_percent: f.eobi_employee_percent || '0', eobi_employer_percent: f.eobi_employer_percent || '0' })}>Save statutory settings</Button>}
      </div>

      <Card className="xl:col-span-3">
        <CardHeader><CardTitle>Salaried tax rates</CardTitle>
          <Select aria-label="Tax year" className="w-64" value={ty.tax_year} onChange={(e) => setYear(Number(e.target.value))}>{s.tax_years.map((t) => <option key={t.tax_year} value={t.tax_year}>Tax year {t.tax_year} ({t.law})</option>)}</Select></CardHeader>
        <DataTable rows={ty.slabs} rowKey={(r) => r.from} empty="" cols={[
          { header: 'Annual taxable income (PKR)', cell: (r) => (r.to ? `${n(r.from)} to ${n(r.to)}` : `Above ${n(r.from)}`) },
          { header: 'Tax', cell: (r) => (Number(r.rate_percent) === 0 ? 'Nil' : `${Number(r.fixed) ? `${n(r.fixed)} + ` : ''}${Number(r.rate_percent)}% of the amount above ${n(r.from)}`) },
        ]} />
        <CardBody className="space-y-3 border-t border-border text-[13px]">
          <p><span className="font-semibold">Period:</span> {ty.period}. {ty.surcharge ? `A surcharge of ${Number(ty.surcharge.rate_percent)}% of the tax applies above PKR ${n(ty.surcharge.over)}.` : 'No surcharge applies to salaried individuals.'}</p>
          <p className="flex items-start gap-2"><ShieldCheck className="mt-0.5 h-4 w-4 shrink-0 text-success" aria-hidden /><span>{ty.verification}</span></p>
          <p className="flex flex-wrap gap-x-4 gap-y-1">{ty.sources.map((u) => <a key={u} href={u} target="_blank" rel="noreferrer" className="inline-flex items-center gap-1 text-primary hover:underline"><ExternalLink className="h-3.5 w-3.5" />{new URL(u).hostname}</a>)}</p>
          <p className="text-muted">Not included: tax credits and reductions, income from another employer in the same year, and the valuation of perquisites such as vehicles or accommodation. Have your tax adviser confirm the setup before the first live run.</p>
        </CardBody>
      </Card>
    </div>
  )
}

export function PayrollPage() {
  const { data: me } = useMe()
  const p = new Set(me?.permissions ?? [])
  type T = 'runs' | 'templates' | 'components' | 'statutory'
  const tabs: { id: T; label: string }[] = []
  if (p.has('payroll.read')) tabs.push({ id: 'runs', label: 'Payroll runs' })
  if (p.has('salary.read')) tabs.push({ id: 'templates', label: 'Salary templates' })
  if (p.has('salary.read')) tabs.push({ id: 'components', label: 'Salary components' })
  if (p.has('payroll.read')) tabs.push({ id: 'statutory', label: 'Tax and statutory' })
  const [tab, setTab] = React.useState<T>(tabs[0]?.id ?? 'runs')
  return (
    <>
      <PageHeader title="Payroll" description="Pay runs, reusable salary templates, components and statutory deductions." actions={tab === 'runs' && p.has('payroll.process') ? <NewRunDialog /> : undefined} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'runs' && <Runs />}{tab === 'templates' && <SalaryTemplates />}{tab === 'components' && <Components />}{tab === 'statutory' && <StatutorySettings />}
    </>
  )
}

const STEPS = ['draft', 'calculated', 'approved', 'finalized']

export function PayrollRunPage() {
  const { id } = useParams()
  const nav = useNavigate()
  const { data: me } = useMe()
  const p = new Set(me?.permissions ?? [])
  const q = useGet<RunDetail>(`/payroll/runs/${id}`)
  const variance = useGet<{ employee: string; net: string; previous_net: string | null; change_percent: number | null }[]>(`/payroll/runs/${id}/variance`)
  const [slip, setSlip] = React.useState<string | null>(null)
  const inv = ['/payroll', '/loans', '/expenses']
  const calc = useSend<undefined, { entries: number; skipped: { employee: string; reason: string }[] }>('POST', `/payroll/runs/${id}/calculate`, { invalidate: inv, onSuccess: (r) => { toast.success(`${r.entries} employees calculated`); r.skipped.slice(0, 4).forEach((s) => toast.warning(`${s.employee}: ${s.reason}`)) } })
  const approve = useSend<undefined>('POST', `/payroll/runs/${id}/approve`, { invalidate: inv, success: 'Run approved' })
  const finalize = useSend<undefined>('POST', `/payroll/runs/${id}/finalize`, { invalidate: inv, success: 'Run finalized. Payslips are published.' })
  const del = useSend<undefined>('DELETE', `/payroll/runs/${id}`, { invalidate: inv, success: 'Run deleted', onSuccess: () => nav('/payroll') })
  if (q.isLoading) return <Skeleton className="h-64 w-full rounded-xl" />
  if (q.isError || !q.data) return <Card><ErrorState message={errorMessage(q.error)} /></Card>
  const r = q.data
  const bad = r.entries.filter((e) => e.exceptions.length)
  const go = (fn: { mutate: (v: never) => void }) => fn.mutate(undefined as never)
  const step = STEPS.indexOf(r.status)
  const changed = (variance.data ?? []).filter((v) => v.previous_net)
  return (
    <>
      <PageHeader title={`Payroll for ${monthOf(r)}`} description={<Link to="/payroll" className="text-primary hover:underline">Back to all runs</Link>} actions={<>
        {p.has('payroll.process') && ['draft', 'calculated'].includes(r.status) && <ConfirmButton variant="ghost" size="md" label="Delete run" title="Delete this run?" message="Its calculated figures are discarded. Loan installments and expense claims it picked up are released." confirmLabel="Delete run" onConfirm={() => go(del)} />}
        {p.has('payroll.process') && ['draft', 'calculated'].includes(r.status) && <Button variant={r.status === 'draft' ? 'primary' : 'outline'} loading={calc.isPending} onClick={() => go(calc)}>{r.status === 'draft' ? 'Calculate' : 'Recalculate'}</Button>}
        {p.has('payroll.approve') && r.status === 'calculated' && <ConfirmButton variant="primary" size="md" label="Approve" title="Approve this payroll?" message="Approval locks the figures. The person who created a run cannot approve it." confirmLabel="Approve" onConfirm={() => go(approve)} loading={approve.isPending} />}
        {p.has('payroll.approve') && r.status === 'approved' && <ConfirmButton variant="primary" size="md" label="Finalize and publish payslips" title="Finalize this payroll?" message="A finalized run can never be recalculated or edited. Employees are told their payslip is ready, loan installments are marked paid and expense claims reimbursed." confirmLabel="Finalize" onConfirm={() => go(finalize)} loading={finalize.isPending} />}
        {r.status === 'finalized' && p.has('bank.read') && <Button asChild variant="outline"><a href={`/api/v1/payroll/runs/${r.id}/export.csv`}><Download className="h-4 w-4" />Bank payment file</a></Button>}
      </>} />

      <ol className="mb-6 flex flex-wrap items-center gap-2 text-[13px]" aria-label="Run progress">
        {STEPS.map((s, i) => (
          <li key={s} className="flex items-center gap-2">
            <span className={cn('flex items-center gap-2 rounded-full px-3 py-1 font-medium capitalize', i < step ? 'bg-success-soft text-success' : i === step ? 'bg-primary text-white dark:text-navy' : 'bg-surface-2 text-muted')}>
              <span className="flex h-4 w-4 items-center justify-center rounded-full bg-white/25 text-[10px] font-bold">{i + 1}</span>{s}</span>
            {i < STEPS.length - 1 && <span className="h-px w-5 bg-border-strong" aria-hidden />}
          </li>))}
      </ol>

      <div className="mb-6 grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
        <StatTile icon={Banknote} label="Gross pay" value={money(r.total_gross)} tone="primary" hint={`${r.entries.length} employees`} />
        <StatTile icon={Landmark} label="Income tax withheld" value={money(r.total_income_tax)} tone="amber" />
        <StatTile icon={Receipt} label="All deductions" value={money(r.total_deductions)} tone="rose" />
        <StatTile icon={Wallet} label={`Net pay (${r.currency})`} value={money(r.total_net)} tone="teal" hint={Number(r.total_employer_contributions) > 0 ? `Plus ${money(r.total_employer_contributions)} employer contributions` : undefined} />
      </div>

      <div className="mb-6 space-y-3">
        <Notice tone={r.statutory_status.startsWith('pk:ty') ? 'info' : 'warning'} icon={Info}>{r.statutory_notice}</Notice>
        {bad.length > 0 && <Notice tone="danger" icon={Info}>{bad.length} {bad.length === 1 ? 'entry has' : 'entries have'} a problem that blocks approval. Fix the cause, then recalculate.</Notice>}
      </div>

      <Card className="mb-6">
        <CardHeader><CardTitle>Employees</CardTitle></CardHeader>
        <DataTable rows={r.entries} rowKey={(e) => e.id} empty="No entries yet" emptyHint="Calculate the run to generate an entry for each employee with a salary." emptyIcon={Wallet} onRowClick={(e) => setSlip(`/payroll/runs/${r.id}/entries/${e.id}`)} cols={[
          { header: 'Employee', cell: (e) => <div><Person name={e.employee} sub={[e.employee_code, e.department].filter(Boolean).join(' · ')} size="sm" />{e.exceptions.map((x) => <Badge key={x} tone="danger" className="ml-9 mt-1">{x.replace(/_/g, ' ')}</Badge>)}</div> },
          { header: 'Gross', right: true, cell: (e) => money(e.gross) },
          { header: 'Income tax', right: true, cell: (e) => (Number(e.income_tax) ? money(e.income_tax) : <span className="text-subtle">Nil</span>) },
          { header: 'Deductions', right: true, cell: (e) => money(e.deductions) },
          { header: 'Net pay', right: true, cell: (e) => <span className="font-semibold">{money(e.net)}</span> },
          { header: '', right: true, cell: () => <span className="text-[13px] font-medium text-primary">Payslip</span> },
        ]} />
      </Card>

      {changed.length > 0 && <Card><CardHeader><CardTitle>Change from the previous finalized run</CardTitle></CardHeader>
        <DataTable rows={changed} rowKey={(v) => v.employee} empty="" cols={[
          { header: 'Employee', cell: (v) => v.employee }, { header: 'Previous net', right: true, cell: (v) => money(v.previous_net) }, { header: 'This run', right: true, cell: (v) => money(v.net) },
          { header: 'Change', right: true, cell: (v) => <span className={cn('font-medium', (v.change_percent ?? 0) > 0 ? 'text-success' : (v.change_percent ?? 0) < 0 ? 'text-danger' : 'text-muted')}>{(v.change_percent ?? 0) > 0 ? '+' : ''}{v.change_percent}%</span> },
        ]} /></Card>}
      <SlipDialog path={slip} onClose={() => setSlip(null)} />
    </>
  )
}

export function PayslipsPage() {
  const q = useGet<{ entry_id: string; period_start: string; period_end: string; gross: string; deductions: string; income_tax: string; net: string; currency: string }[]>('/payslips')
  const [slip, setSlip] = React.useState<string | null>(null)
  return (
    <>
      <PageHeader title="My payslips" description="Published when payroll for a period is finalized." />
      <Card><DataTable rows={q.data} rowKey={(s) => s.entry_id} query={q} empty="No payslips yet" emptyHint="Your payslip appears here once payroll for the month is finalized." emptyIcon={Receipt} onRowClick={(s) => setSlip(`/payslips/${s.entry_id}`)} cols={[
        { header: 'Pay period', cell: (s) => <span className="font-semibold">{monthOf(s)}</span> },
        { header: 'Gross', right: true, cell: (s) => money(s.gross) },
        { header: 'Income tax', right: true, cell: (s) => (Number(s.income_tax) ? money(s.income_tax) : 'Nil') },
        { header: 'Deductions', right: true, cell: (s) => money(s.deductions) },
        { header: 'Net pay', right: true, cell: (s) => <span className="font-semibold">{money(s.net, s.currency)}</span> },
        { header: '', right: true, cell: () => <span className="text-[13px] font-medium text-primary">View</span> },
      ]} /></Card>
      <SlipDialog path={slip} onClose={() => setSlip(null)} />
    </>
  )
}
