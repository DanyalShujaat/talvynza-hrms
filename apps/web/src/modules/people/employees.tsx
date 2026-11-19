import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { Download, FileSpreadsheet, LayoutGrid, List, Search, Upload } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Avatar, Pager, Person, StatusText, Tabs, Td, Th, downloadCsv } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/menu'
import { errorMessage } from '@/lib/api'
import { uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'

export interface EmpRow {
  id: string; employee_code: string; bio_id: string | null; first_name: string; last_name: string; full_name: string; email: string | null
  phone: string | null; branch_id: string | null; branch: string | null; department_id: string | null; department: string | null
  designation_id: string | null; designation: string | null; manager_id: string | null; status: string; joining_date: string; has_login: boolean
}
export interface Named { id: string; name: string; department_id?: string | null }

export function useOrgLists() {
  const branches = useGet<Named[]>('/branches')
  const departments = useGet<Named[]>('/departments')
  const designations = useGet<Named[]>('/designations')
  return { branches: branches.data ?? [], departments: departments.data ?? [], designations: designations.data ?? [] }
}

export const Opts = ({ list, blank = 'None' }: { list: { id: string; name: string }[]; blank?: string }) => (
  <>{blank && <option value="">{blank}</option>}{list.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</>
)

const STATUS_FILTERS = [['active', 'Active Employees'], ['probation', 'On probation'], ['suspended', 'Suspended'], ['former', 'Former Employees']]

function AllEmployees() {
  const [sp] = useSearchParams()
  const department = sp.get('department_id') ?? ''
  const [branch, setBranch] = React.useState('')
  const [status, setStatus] = React.useState('active')
  const [q, setQ] = React.useState('')
  const [letter, setLetter] = React.useState('')
  const [page, setPage] = React.useState(1)
  const [grid, setGrid] = React.useState(false)
  const { branches, departments } = useOrgLists()
  const list = useGet<{ items: EmpRow[]; total: number; page_size: number }>('/employees', { branch_id: branch || undefined, department_id: department || undefined, status, q: q || undefined, letter: letter || undefined, page })
  const nav = useNavigate()
  const items = list.data?.items ?? []
  const reset = (fn: () => void) => { fn(); setPage(1) }

  return (
    <>
      {department && <p className="mb-4 text-sm text-muted">Showing employees in <strong>{departments.find(d => d.id === department)?.name ?? 'this department'}</strong>. <Link to="/employees" className="font-medium text-primary hover:underline">Clear filter</Link></p>}
      <Card className="mb-5"><CardBody className="flex flex-wrap items-end gap-4">
        <Field id="f-branch" label="Branch">{(a) => <Select className="w-48" value={branch} onChange={(e) => reset(() => setBranch(e.target.value))} {...a}><Opts list={branches} blank="All Branches" /></Select>}</Field>
        <Field id="f-status" label="Status">{(a) => <Select className="w-48" value={status} onChange={(e) => reset(() => setStatus(e.target.value))} {...a}>{STATUS_FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}</Field>
        <Field id="f-q" label="Search">{(a) => (
          <div className="relative"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden /><Input className="w-64 pl-9" placeholder="Search by name, ID, etc..." value={q} onChange={(e) => reset(() => setQ(e.target.value))} {...a} /></div>)}</Field>
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" onClick={() => downloadCsv('employees.csv', [['Employee ID', 'Name', 'Email', 'Phone', 'Branch', 'Department', 'Designation', 'Status', 'Joined'], ...items.map((e) => [e.employee_code, e.full_name, e.email, e.phone, e.branch, e.department, e.designation, e.status, e.joining_date])])} disabled={!items.length}><Download className="h-4 w-4" />Export CSV</Button>
          <div className="flex rounded-lg bg-surface-2 p-1" role="group" aria-label="View">
            <Button variant={grid ? 'ghost' : 'outline'} size="icon" aria-label="List view" aria-pressed={!grid} onClick={() => setGrid(false)}><List className="h-4 w-4" /></Button>
            <Button variant={grid ? 'outline' : 'ghost'} size="icon" aria-label="Grid view" aria-pressed={grid} onClick={() => setGrid(true)}><LayoutGrid className="h-4 w-4" /></Button>
          </div>
        </div>
      </CardBody></Card>

      <Card className="mb-5"><CardBody className="flex flex-wrap items-center gap-1" role="group" aria-label="Filter by first letter">
        {['', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => (
          <button key={l || 'all'} onClick={() => reset(() => setLetter(l))} aria-pressed={letter === l}
            className={`flex h-8 min-w-8 cursor-pointer items-center justify-center rounded-full px-2 text-xs font-medium ${letter === l ? 'bg-primary text-white' : 'text-muted hover:bg-surface-2'}`}>{l || 'All'}</button>))}
      </CardBody></Card>

      {list.isLoading ? <Card><CardBody className="space-y-3"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></CardBody></Card>
        : list.isError ? <Card><ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} /></Card>
        : items.length === 0 ? <Card><EmptyState title="No employees found" description="Change the filters, or add an employee." /></Card>
        : grid ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {items.map((e) => (
              <Link key={e.id} to={`/employees/${e.id}`} className="rounded-2xl border border-border bg-surface p-5 text-center shadow-card transition-shadow hover:shadow-md">
                <Avatar name={e.full_name} size="xl" className="mx-auto" />
                <p className="mt-3 font-semibold">{e.full_name}</p><p className="text-sm text-muted">{e.designation ?? e.department ?? 'No designation'}</p>
                <p className="mt-1 text-xs text-muted">{e.employee_code}</p><div className="mt-2"><StatusText status={e.status} /></div>
              </Link>))}
          </div>)
        : (
          <Card><div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-border"><tr><Th>Employee ID</Th><Th>Bio ID</Th><Th>Name</Th><Th>Branch</Th><Th>Department</Th><Th>Mobile</Th><Th>Status</Th><Th className="text-right">Action</Th></tr></thead>
              <tbody className="divide-y divide-border">
                {items.map((e) => (
                  <tr key={e.id} className="hover:bg-surface-2/50">
                    <Td>{e.employee_code}</Td><Td>{e.bio_id ?? '-'}</Td>
                    <Td><Link to={`/employees/${e.id}`} className="hover:text-primary"><Person name={e.full_name} sub={e.email} size="sm" /></Link></Td>
                    <Td>{e.branch ?? ''}<p className="text-xs text-muted">{e.designation}</p></Td>
                    <Td>{e.department ? <Badge>{e.department}</Badge> : '-'}</Td><Td>{e.phone ?? '-'}</Td><Td><StatusText status={e.status} /></Td>
                    <Td className="text-right">
                      <Menu><MenuTrigger asChild><Button variant="outline" size="sm">Actions</Button></MenuTrigger>
                        <MenuContent><MenuItem onSelect={() => nav(`/employees/${e.id}`)}>View profile</MenuItem><MenuItem onSelect={() => nav(`/employees/${e.id}?tab=documents`)}>Documents</MenuItem><MenuItem onSelect={() => nav(`/employees/${e.id}?tab=checklist`)}>Onboarding checklist</MenuItem></MenuContent></Menu>
                    </Td>
                  </tr>))}
              </tbody>
            </table>
          </div>
          <Pager page={page} pageSize={list.data!.page_size} total={list.data!.total} onPage={setPage} /></Card>)}
    </>
  )
}

const addSchema = z.object({
  first_name: z.string().min(1, 'Required'), last_name: z.string().min(1, 'Required'), email: z.string().email('Enter a valid email').or(z.literal('')),
  phone: z.string().optional(), employee_code: z.string().optional(), joining_date: z.string().min(1, 'Required'),
  branch_id: z.string().optional(), department_id: z.string().optional(), designation_id: z.string().optional(), manager_id: z.string().optional(),
  employment_type: z.string(), probation_end: z.string().optional(),
})

function AddEmployee() {
  const nav = useNavigate()
  const { branches, departments, designations } = useOrgLists()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const { register, handleSubmit, watch, formState: { errors } } = useForm<z.infer<typeof addSchema>>({ resolver: zodResolver(addSchema), defaultValues: { employment_type: 'full_time', joining_date: new Date().toISOString().slice(0, 10) } })
  const dept = watch('department_id')
  const create = useSend<Record<string, unknown>, { id: string }>('POST', '/employees', { invalidate: ['/employees', '/dashboard', '/departments', '/branches'], success: 'Employee created', onSuccess: (r) => nav(`/employees/${r.id}`) })
  const clean = (v: z.infer<typeof addSchema>) => Object.fromEntries(Object.entries(v).filter(([, x]) => x !== '' && x !== undefined))
  return (
    <Card className="max-w-4xl"><CardBody>
      <form onSubmit={handleSubmit((v) => create.mutate(clean(v)))} className="grid gap-4 sm:grid-cols-2" noValidate>
        <Field id="first_name" label="First name" error={errors.first_name?.message}>{(a) => <Input {...a} {...register('first_name')} />}</Field>
        <Field id="last_name" label="Last name" error={errors.last_name?.message}>{(a) => <Input {...a} {...register('last_name')} />}</Field>
        <Field id="email" label="Work email" error={errors.email?.message} hint="Used to link their login when they accept an invitation.">{(a) => <Input type="email" {...a} {...register('email')} />}</Field>
        <Field id="phone" label="Mobile">{(a) => <Input {...a} {...register('phone')} />}</Field>
        <Field id="employee_code" label="Employee ID" hint="Leave blank to generate the next number.">{(a) => <Input {...a} {...register('employee_code')} />}</Field>
        <Field id="joining_date" label="Joining date" error={errors.joining_date?.message}>{(a) => <Input type="date" {...a} {...register('joining_date')} />}</Field>
        <Field id="branch_id" label="Branch">{(a) => <Select {...a} {...register('branch_id')}><Opts list={branches} /></Select>}</Field>
        <Field id="department_id" label="Department">{(a) => <Select {...a} {...register('department_id')}><Opts list={departments} /></Select>}</Field>
        <Field id="designation_id" label="Designation">{(a) => <Select {...a} {...register('designation_id')}><Opts list={designations.filter((d) => !dept || !d.department_id || d.department_id === dept)} /></Select>}</Field>
        <Field id="manager_id" label="Reporting manager">{(a) => <Select {...a} {...register('manager_id')}><Opts list={(people.data?.items ?? []).map((p) => ({ id: p.id, name: p.full_name }))} /></Select>}</Field>
        <Field id="employment_type" label="Employment type">{(a) => <Select {...a} {...register('employment_type')}>{['full_time', 'part_time', 'contract', 'intern'].map((t) => <option key={t} value={t}>{t.replace('_', ' ')}</option>)}</Select>}</Field>
        <Field id="probation_end" label="Probation ends" hint="Set a date to start the employee on probation.">{(a) => <Input type="date" {...a} {...register('probation_end')} />}</Field>
        <div className="sm:col-span-2"><Button type="submit" loading={create.isPending}>Create employee</Button></div>
      </form>
    </CardBody></Card>
  )
}

interface Preview { rows: { row: number; errors: string[]; data: Record<string, string | null> }[]; summary: { total: number; valid: number; invalid: number } }

function BulkImport({ onDone }: { onDone: () => void }) {
  const qc = useQueryClient()
  const [file, setFile] = React.useState<File | null>(null)
  const [preview, setPreview] = React.useState<Preview | null>(null)
  const [skip, setSkip] = React.useState(false)
  const [busy, setBusy] = React.useState(false)
  const send = async (path: string) => {
    const f = new FormData()
    f.append('file', file!)
    if (path.endsWith('commit')) f.append('skip_invalid', String(skip))
    setBusy(true)
    try { return await uploadFile<Preview & { created?: number; skipped?: number }>(path, f) } catch (e) { toast.error(errorMessage(e)); return null } finally { setBusy(false) }
  }
  return (
    <div className="max-w-5xl space-y-5">
      <Card><CardHeader><CardTitle>Upload a spreadsheet</CardTitle><a className="inline-flex items-center gap-1.5 text-sm text-primary hover:underline" href="/api/v1/employees/template.csv"><FileSpreadsheet className="h-4 w-4" />Download template</a></CardHeader>
        <CardBody className="space-y-4">
          <p className="text-sm text-muted">Accepts .csv or .xlsx up to 5 MB. Branch, department and designation names must already exist. Nothing is saved until you confirm the preview.</p>
          <div className="flex flex-wrap items-center gap-3">
            <Input type="file" accept=".csv,.xlsx" aria-label="Employee file" className="max-w-sm pt-1.5" onChange={(e) => { setFile(e.target.files?.[0] ?? null); setPreview(null) }} />
            <Button disabled={!file} loading={busy} onClick={async () => setPreview(await send('/employees/import/preview'))}><Upload className="h-4 w-4" />Preview</Button>
          </div>
        </CardBody></Card>
      {preview && (
        <Card>
          <CardHeader><CardTitle>Preview</CardTitle><div className="flex gap-2"><Badge tone="success">{preview.summary.valid} valid</Badge>{preview.summary.invalid > 0 && <Badge tone="danger">{preview.summary.invalid} with errors</Badge>}</div></CardHeader>
          <div className="max-h-96 overflow-auto"><table className="w-full text-left"><thead className="sticky top-0 border-b border-border bg-surface"><tr><Th>Row</Th><Th>Name</Th><Th>Email</Th><Th>Joined</Th><Th>Result</Th></tr></thead>
            <tbody className="divide-y divide-border">{preview.rows.map((r) => (
              <tr key={r.row}><Td>{r.row}</Td><Td>{r.data.first_name} {r.data.last_name}</Td><Td>{r.data.email ?? '-'}</Td><Td>{r.data.joining_date ?? '-'}</Td>
                <Td>{r.errors.length ? <ul className="text-danger">{r.errors.map((e) => <li key={e}>{e}</li>)}</ul> : <span className="text-success">Ready</span>}</Td></tr>))}</tbody></table></div>
          <CardBody className="flex flex-wrap items-center gap-4 border-t border-border">
            {preview.summary.invalid > 0 && <label className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" checked={skip} onChange={(e) => setSkip(e.target.checked)} />Skip rows with errors and import the rest</label>}
            <Button disabled={preview.summary.valid === 0 || (preview.summary.invalid > 0 && !skip)} loading={busy}
              onClick={async () => { const r = await send('/employees/import/commit'); if (r) { toast.success(`${r.created} employees imported`); await qc.invalidateQueries(); onDone() } }}>Import {preview.summary.valid} employees</Button>
          </CardBody>
        </Card>)}
    </div>
  )
}

interface Overview { employee_id: string; full_name: string; employee_code: string; done: number; total: number }
function ChecklistOverview() {
  const q = useGet<Overview[]>('/checklists/overview')
  return (
    <Card className="max-w-3xl">
      <CardHeader><CardTitle>Onboarding in progress</CardTitle></CardHeader>
      {q.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} />
        : !q.data?.length ? <EmptyState title="No open checklists" description="Every employee has completed onboarding." />
        : <ul className="divide-y divide-border">{q.data.map((o) => (
          <li key={o.employee_id} className="flex items-center gap-4 px-5 py-3 text-sm">
            <Link to={`/employees/${o.employee_id}?tab=checklist`} className="w-48 truncate font-medium hover:text-primary">{o.full_name}<span className="ml-2 text-xs text-muted">{o.employee_code}</span></Link>
            <div className="h-2 flex-1 rounded-full bg-surface-2" role="progressbar" aria-valuenow={o.done} aria-valuemax={o.total}><div className="h-full rounded-full bg-success" style={{ width: `${(o.done / o.total) * 100}%` }} /></div>
            <span className="w-14 text-right text-muted">{o.done}/{o.total}</span></li>))}</ul>}
    </Card>
  )
}

export function EmployeesPage() {
  const { data: me } = useMe()
  const manage = me?.permissions.includes('employees.manage')
  const [sp] = useSearchParams()
  const [tab, setTab] = React.useState<'all' | 'add' | 'bulk' | 'checklist'>(sp.get('tab') === 'add' ? 'add' : 'all')
  const tabs = [{ id: 'all' as const, label: 'All employees' }, ...(manage ? [{ id: 'add' as const, label: 'Add employee' }, { id: 'bulk' as const, label: 'Bulk import' }, { id: 'checklist' as const, label: 'Onboarding' }] : [])]
  return (
    <>
      <PageHeader title="Employees" description="Everyone in the organization, with their placement and status." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'all' && <AllEmployees />}{tab === 'add' && <AddEmployee />}{tab === 'bulk' && <BulkImport onDone={() => setTab('all')} />}{tab === 'checklist' && <ChecklistOverview />}
    </>
  )
}

