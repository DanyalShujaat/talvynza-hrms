import { zodResolver } from '@hookform/resolvers/zod'
import { useQueryClient } from '@tanstack/react-query'
import { CalendarDays, ClipboardList, Clock, Download, Ellipsis, FileSpreadsheet, FileText, LayoutGrid, List, MessageSquare, Receipt, RefreshCw, Search, Upload, UserRound, UserRoundMinus, Wallet } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { z } from 'zod'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { Avatar, Pager, Person, StatusText, Tabs, Td, Th, downloadCsv } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { Menu, MenuContent, MenuItem, MenuSeparator, MenuTrigger } from '@/components/ui/menu'
import { errorMessage } from '@/lib/api'
import { today, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { useViewQuery, useViewTab } from '@/lib/view-state'
import { EmployeeSetup } from './employee-setup'

export interface EmpRow {
  id: string; employee_code: string; bio_id: string | null; first_name: string; last_name: string; full_name: string; email: string | null
  phone: string | null; branch_id: string | null; branch: string | null; department_id: string | null; department: string | null
  designation_id: string | null; designation: string | null; manager_id: string | null; status: string; joining_date: string; has_login: boolean
}
export interface Named { id: string; name: string; department_id?: string | null; is_active?: boolean }

export function useOrgLists() {
  const branches = useGet<Named[]>('/branches')
  const departments = useGet<Named[]>('/departments')
  const designations = useGet<Named[]>('/designations')
  return { branches: branches.data ?? [], departments: departments.data ?? [], designations: designations.data ?? [] }
}

export const Opts = ({ list, blank = 'None' }: { list: { id: string; name: string }[]; blank?: string }) => (
  <>{blank && <option value="">{blank}</option>}{list.map((x) => <option key={x.id} value={x.id}>{x.name}</option>)}</>
)

const STATUS_FILTERS = [['active', 'Active employees'], ['probation', 'On probation'], ['suspended', 'Suspended'], ['former', 'Former employees'], ['all', 'All statuses']]

function EmployeeActions({ employee, directorySearch, onDeactivate }: { employee: EmpRow; directorySearch: string; onDeactivate: () => void }) {
  const { data: me } = useMe()
  const perms = new Set(me?.permissions ?? [])
  const manage = perms.has('employees.manage')
  const isSelf = me?.employee?.id === employee.id
  const path = `/employees/${employee.id}`
  const state = { directorySearch }
  const phone = employee.phone?.replace(/[\s().-]/g, '')
  return (
    <Menu>
      <MenuTrigger asChild><Button variant="outline" size="sm" aria-label={`Actions for ${employee.full_name}`}><Ellipsis className="h-4 w-4" aria-hidden /> <span className="hidden sm:inline">Actions</span></Button></MenuTrigger>
      <MenuContent>
        <MenuItem asChild><Link to={path} state={state}><UserRound className="h-4 w-4" />View profile</Link></MenuItem>
        <MenuItem asChild><Link to={`${path}?tab=attendance`} state={state}><Clock className="h-4 w-4" />Attendance</Link></MenuItem>
        {perms.has('salary.read') && <MenuItem asChild><Link to={`${path}?tab=salary`} state={state}><Wallet className="h-4 w-4" />Salary details</Link></MenuItem>}
        {(perms.has('payroll.read') || (isSelf && perms.has('payslip.read_own'))) && <MenuItem asChild><Link to={`${path}?tab=payslips`} state={state}><Receipt className="h-4 w-4" />View payslips</Link></MenuItem>}
        <MenuItem asChild><Link to={`${path}?tab=leave`} state={state}><CalendarDays className="h-4 w-4" />{isSelf || perms.has('leave.manage') || perms.has('leave.approve') ? 'Leave applications' : 'Leave balance'}</Link></MenuItem>
        {(manage || isSelf || perms.has('documents.manage')) && <MenuItem asChild><Link to={`${path}?tab=documents`} state={state}><FileText className="h-4 w-4" />Documents</Link></MenuItem>}
        {manage && <MenuItem asChild><Link to={`${path}?tab=checklist`} state={state}><ClipboardList className="h-4 w-4" />Onboarding checklist</Link></MenuItem>}
        {phone && /^\+?\d{3,20}$/.test(phone) && <MenuItem asChild><a href={`sms:${phone}`}><MessageSquare className="h-4 w-4" />Compose SMS</a></MenuItem>}
        {manage && !isSelf && ['active', 'probation', 'suspended'].includes(employee.status) && <>
          <MenuSeparator />
          <MenuItem className="text-danger" onSelect={onDeactivate}><UserRoundMinus className="h-4 w-4" />Deactivate</MenuItem>
        </>}
      </MenuContent>
    </Menu>
  )
}

function AllEmployees() {
  const [sp, update] = useViewQuery()
  const department = sp.get('department_id') ?? ''
  const branch = sp.get('branch_id') ?? ''
  const status = STATUS_FILTERS.find(([key]) => key === sp.get('status'))?.[0] ?? 'active'
  const q = (sp.get('q') ?? '').slice(0, 80)
  const letter = sp.get('letter') ?? ''
  const page = Math.max(1, parseInt(sp.get('page') ?? '1', 10) || 1)
  const grid = sp.get('view') === 'grid'
  const { branches, departments } = useOrgLists()
  const list = useGet<{ items: EmpRow[]; total: number; page_size: number }>('/employees', { branch_id: branch || undefined, department_id: department || undefined, status, q: q || undefined, letter: letter || undefined, page })
  React.useEffect(() => {
    if (list.data && page > Math.max(1, Math.ceil(list.data.total / list.data.page_size))) update({ page: null })
  }, [list.data, page])
  const [deactivating, setDeactivating] = React.useState<EmpRow | null>(null)
  const deactivate = useSend<{ effective_date: string; event_type: 'deactivation' }>(
    'POST', `/employees/${deactivating?.id}/lifecycle`,
    { invalidate: ['/employees', '/branches', '/departments'], success: 'Employee deactivated', onSuccess: () => setDeactivating(null) },
  )
  const directorySearch = sp.toString()
  const items = list.data?.items ?? []
  const filter = (key: string, value: string) => update({ [key]: value, page: null })

  return (
    <>
      <Card className="mb-5"><CardBody className="flex flex-wrap items-end gap-4">
        <Field id="f-branch" label="Branch" className="min-w-0 flex-1 basis-36">{(a) => <Select value={branch} onChange={(e) => filter('branch_id', e.target.value)} {...a}><Opts list={branches} blank="All branches" /></Select>}</Field>
        <Field id="f-department" label="Department" className="min-w-0 flex-1 basis-36">{(a) => <Select value={department} onChange={(e) => filter('department_id', e.target.value)} {...a}><Opts list={departments} blank="All departments" /></Select>}</Field>
        <Field id="f-status" label="Status" className="min-w-0 flex-1 basis-36">{(a) => <Select value={status} onChange={(e) => filter('status', e.target.value)} {...a}>{STATUS_FILTERS.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}</Field>
        <Field id="f-q" label="Search" className="min-w-0 flex-1 basis-48">{(a) => (
          <div className="relative"><Search className="pointer-events-none absolute left-3 top-3 h-4 w-4 text-muted" aria-hidden /><Input className="pl-9" placeholder="Search by name, ID, etc..." maxLength={80} value={q} onChange={(e) => filter('q', e.target.value)} {...a} /></div>)}</Field>
        {(branch || department || status !== 'active' || q || letter) && <Button variant="ghost" onClick={() => update({ branch_id: null, department_id: null, status: null, q: null, letter: null, page: null })}>Reset filters</Button>}
        <div className="ml-auto flex items-center gap-2">
          <Button variant="outline" disabled={list.isFetching} onClick={() => list.refetch()}><RefreshCw className="h-4 w-4" />Refresh</Button>
          <Button variant="outline" onClick={() => downloadCsv('employees.csv', [['Employee ID', 'Name', 'Email', 'Phone', 'Branch', 'Department', 'Designation', 'Status', 'Joined'], ...items.map((e) => [e.employee_code, e.full_name, e.email, e.phone, e.branch, e.department, e.designation, e.status, e.joining_date])])} disabled={!items.length}><Download className="h-4 w-4" />Export CSV</Button>
          <div className="flex rounded-lg bg-surface-2 p-1" role="group" aria-label="View">
            <Button variant={grid ? 'ghost' : 'outline'} size="icon" aria-label="List view" aria-pressed={!grid} onClick={() => update({ view: null })}><List className="h-4 w-4" /></Button>
            <Button variant={grid ? 'outline' : 'ghost'} size="icon" aria-label="Grid view" aria-pressed={grid} onClick={() => update({ view: 'grid' })}><LayoutGrid className="h-4 w-4" /></Button>
          </div>
        </div>
      </CardBody></Card>

      <Card className="mb-5"><CardBody className="flex flex-wrap items-center gap-1" role="group" aria-label="Filter by first letter">
        {['', ...'ABCDEFGHIJKLMNOPQRSTUVWXYZ'].map((l) => (
          <button key={l || 'all'} onClick={() => filter('letter', l)} aria-pressed={letter === l}
            className={`flex h-8 min-w-8 cursor-pointer items-center justify-center rounded-full px-2 text-xs font-medium ${letter === l ? 'bg-primary text-white' : 'text-muted hover:bg-surface-2'}`}>{l || 'All'}</button>))}
      </CardBody></Card>

      {list.isLoading ? <Card><CardBody className="space-y-3"><Skeleton className="h-10 w-full" /><Skeleton className="h-10 w-full" /></CardBody></Card>
        : list.isError ? <Card><ErrorState message={errorMessage(list.error)} onRetry={() => list.refetch()} /></Card>
        : items.length === 0 ? <Card><EmptyState title="No employees found" description="Change the filters, or add an employee." /></Card>
        : grid ? (
          <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
            {items.map((e) => (
              <Card key={e.id} className="p-4 text-center">
                <div className="flex"><EmployeeActions employee={e} directorySearch={directorySearch} onDeactivate={() => setDeactivating(e)} /></div>
                <Link to={`/employees/${e.id}`} state={{ directorySearch }} className="block rounded-lg p-1 hover:text-primary">
                  <Avatar name={e.full_name} size="xl" className="mx-auto" />
                  <p className="mt-3 font-semibold">{e.full_name}</p>
                  <p className="text-sm text-muted">{e.designation ?? e.department ?? 'No designation'}</p>
                  <p className="mt-1 text-xs text-muted">{e.employee_code}</p><div className="mt-2"><StatusText status={e.status} /></div>
                </Link>
              </Card>))}
          </div>)
        : (
          <Card><div className="overflow-x-auto">
            <table className="w-full text-left">
              <thead className="border-b border-border"><tr><Th>Employee ID</Th><Th>Bio ID</Th><Th>Name</Th><Th>Actions</Th><Th>Branch</Th><Th>Department</Th><Th>Mobile</Th><Th>Status</Th></tr></thead>
              <tbody className="divide-y divide-border">
                {items.map((e) => (
                  <tr key={e.id} className="hover:bg-surface-2/50">
                    <Td>{e.employee_code}</Td><Td>{e.bio_id ?? '-'}</Td>
                    <Td><Link to={`/employees/${e.id}`} state={{ directorySearch }} className="hover:text-primary"><Person name={e.full_name} sub={e.email} size="sm" /></Link></Td>
                    <Td><EmployeeActions employee={e} directorySearch={directorySearch} onDeactivate={() => setDeactivating(e)} /></Td>
                    <Td>{e.branch ?? ''}<p className="text-xs text-muted">{e.designation}</p></Td>
                    <Td>{e.department ? <Badge>{e.department}</Badge> : '-'}</Td><Td>{e.phone ?? '-'}</Td><Td><StatusText status={e.status} /></Td>
                  </tr>))}
              </tbody>
            </table>
          </div>
          <Pager page={page} pageSize={list.data!.page_size} total={list.data!.total} onPage={next => update({ page: next }, false)} /></Card>)}
      <Dialog open={!!deactivating} onOpenChange={open => { if (!open) setDeactivating(null) }}>
        <DialogContent title={`Deactivate ${deactivating?.full_name ?? 'employee'}?`} description="This records an exit today and moves the employee to Former Employees. Manage portal access from Account privileges.">
          <DialogFooter>
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button variant="danger" loading={deactivate.isPending} onClick={() => {
              if (deactivating) deactivate.mutate({ effective_date: today(), event_type: 'deactivation' })
            }}>Deactivate employee</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  )
}

const addSchema = z.object({
  first_name: z.string().min(1, 'Required'), last_name: z.string().min(1, 'Required'), email: z.string().email('Enter a valid email').or(z.literal('')),
  phone: z.string().optional(), employee_code: z.string().optional(), joining_date: z.string().min(1, 'Required'),
  branch_id: z.string().min(1, 'Select a branch'), department_id: z.string().min(1, 'Select a department'), designation_id: z.string().optional(), manager_id: z.string().optional(),
  employment_type: z.string(), probation_end: z.string().optional(),
})

function AddEmployee() {
  const nav = useNavigate()
  const { branches, departments, designations } = useOrgLists()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const { register, handleSubmit, watch, setValue, formState: { errors } } = useForm<z.infer<typeof addSchema>>({ resolver: zodResolver(addSchema), defaultValues: { employment_type: 'full_time', joining_date: new Date().toISOString().slice(0, 10) } })
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
        <Field id="branch_id" label="Branch" error={errors.branch_id?.message}>{(a) => <Select {...a} {...register('branch_id')} required><Opts list={branches.filter(b => b.is_active)} blank="Select a branch" /></Select>}</Field>
        <Field id="department_id" label="Department" error={errors.department_id?.message}>{(a) => <Select {...a} {...register('department_id', { onChange: () => setValue('designation_id', '') })} required><Opts list={departments.filter(d => d.is_active)} blank="Select a department" /></Select>}</Field>
        <Field id="designation_id" label="Designation">{(a) => <Select {...a} {...register('designation_id')}><Opts list={designations.filter(d => !d.department_id || d.department_id === dept)} /></Select>}</Field>
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
          <p className="text-sm text-muted">Upload a .csv or .xlsx file up to 5 MB. Each row needs an active branch and department. If you include a designation, use its existing name.</p>
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
  const tabs = [{ id: 'all' as const, label: 'All employees' }, ...(manage ? [{ id: 'add' as const, label: 'Add employee' }, { id: 'bulk' as const, label: 'Bulk import' }, { id: 'checklist' as const, label: 'Onboarding' }] : [])]
  const [tab, setTab] = useViewTab(tabs.map(item => item.id), 'all')
  return (
    <>
      <PageHeader title="Employees" description="Everyone in the organization, with their placement and status." />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'all' && <AllEmployees />}
      {manage && tab === 'add' && <EmployeeSetup><AddEmployee /></EmployeeSetup>}
      {manage && tab === 'bulk' && <EmployeeSetup><BulkImport onDone={() => setTab('all')} /></EmployeeSetup>}
      {tab === 'checklist' && <ChecklistOverview />}
    </>
  )
}

