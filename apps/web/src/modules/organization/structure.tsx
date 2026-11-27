import { Ellipsis, MapPin, Plus } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { Link, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, Notice, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { ConfirmButton, SlideOver, Tabs, Td, Th } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { Menu, MenuContent, MenuItem, MenuTrigger } from '@/components/ui/menu'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { formatDate } from '@/lib/utils'
import { useViewQuery } from '@/lib/view-state'

interface Dept { id: string; name: string; description: string | null; parent_id: string | null; employee_count: number; designation_count: number; is_active: boolean }
interface Desig { id: string; name: string; department_id: string | null; grade: string | null; employee_count: number }
interface Branch {
  id: string; name: string; code: string | null; city: string | null; address: string | null; phone: string | null
  email: string | null; premise_count: number; created_at: string; employee_count: number; is_active: boolean
}
const BranchPremises = React.lazy(() => import('./branch-premises'))

const EditBtn = ({ onClick }: { onClick: () => void }) => <button onClick={onClick} className="cursor-pointer rounded-md bg-primary/15 px-3 py-1 text-xs font-semibold text-primary hover:bg-primary/25">Edit</button>

// ------------------------------------------------------------------ Designations (slide-over)
function Designations({ dept, onClose }: { dept: Dept | null; onClose: () => void }) {
  const list = useGet<Desig[]>('/designations', { department_id: dept?.id }, !!dept)
  const [editing, setEditing] = React.useState<Desig | 'new' | null>(null)
  const [name, setName] = React.useState('')
  const [grade, setGrade] = React.useState('')
  const startEdit = (item: Desig | 'new') => { setEditing(item); setName(item === 'new' ? '' : item.name); setGrade(item === 'new' ? '' : item.grade ?? '') }
  const save = useSend<{ name: string; grade: string }>(editing && editing !== 'new' ? 'PUT' : 'POST', editing && editing !== 'new' ? `/designations/${editing.id}` : '/designations', { invalidate: ['/designations', '/departments', '/dashboard'], success: 'Saved', onSuccess: () => setEditing(null) })
  const del = useSend<string>('DELETE', (id) => `/designations/${id}`, { invalidate: ['/designations', '/departments', '/dashboard'], success: 'Deleted' })
  return (
    <SlideOver open={!!dept} onOpenChange={(o) => !o && onClose()} title={`Designations${dept ? ` in ${dept.name}` : ''}`}>
      <div className="mb-4 flex justify-end"><Button size="sm" onClick={() => startEdit('new')}><Plus className="h-4 w-4" />Add New Designation</Button></div>
      {editing && (
        <form onSubmit={e => { e.preventDefault(); if (name.trim()) save.mutate({ name: name.trim(), department_id: dept?.id, grade: grade.trim() || null } as never) }} className="mb-5 grid gap-3 rounded-xl border border-border p-4 sm:grid-cols-2">
          <Field id="ds-n" label="Designation">{(a) => <Input autoFocus {...a} required value={name} onChange={e => setName(e.target.value)} />}</Field>
          <Field id="ds-g" label="Grade (optional)">{(a) => <Input {...a} value={grade} onChange={e => setGrade(e.target.value)} />}</Field>
          <div className="flex gap-2 sm:col-span-2"><Button type="submit" size="sm" loading={save.isPending}>Save</Button><Button type="button" size="sm" variant="outline" onClick={() => setEditing(null)}>Cancel</Button></div>
        </form>)}
      {list.isLoading ? <Skeleton className="h-24 w-full" /> : !list.data?.length ? <EmptyState title="No designations yet" /> : (
        <table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Designation</Th><Th>Grade</Th><Th>Employees</Th><Th className="text-right">Actions</Th></tr></thead>
          <tbody className="divide-y divide-border">{list.data.map((d) => (
            <tr key={d.id}><Td className="font-medium">{d.name}</Td><Td>{d.grade ?? '-'}</Td><Td>{d.employee_count}</Td>
              <Td className="space-x-2 text-right"><EditBtn onClick={() => startEdit(d)} /><ConfirmButton label="Delete" title="Delete designation" message={`Delete ${d.name}?`} onConfirm={() => del.mutate(d.id)} /></Td></tr>))}</tbody></table>)}
    </SlideOver>
  )
}

export function DepartmentsPage() {
  const q = useGet<Dept[]>('/departments')
  const { data: me } = useMe()
  const canReadEmployees = me?.permissions.includes('employees.read')
  const canManageAttendance = me?.permissions.includes('attendance.manage')
  const branches = useGet<Branch[]>('/branches')
  const canAdd = branches.isSuccess && branches.data.some(b => b.is_active)
  const [editing, setEditing] = React.useState<Dept | 'new' | null>(null)
  const [newParent, setNewParent] = React.useState('')
  const [viewing, setViewing] = React.useState<Dept | null>(null)
  const { register, handleSubmit, reset } = useForm<{ name: string; description: string; parent_id: string }>()
  React.useEffect(() => { reset(editing && editing !== 'new' ? { name: editing.name, description: editing.description ?? '', parent_id: editing.parent_id ?? '' } : { name: '', description: '', parent_id: newParent }) }, [editing, newParent, reset])
  const isEdit = editing && editing !== 'new'
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/departments/${editing.id}` : '/departments', { invalidate: ['/departments', '/dashboard', '/employees/setup'], success: 'Saved', onSuccess: () => setEditing(null) })
  const del = useSend<string>('DELETE', (id) => `/departments/${id}`, { invalidate: ['/departments', '/dashboard', '/employees/setup'], success: 'Department deleted' })
  const names = Object.fromEntries((q.data ?? []).map((d) => [d.id, d.name]))
  const descendants = (id: string): string[] => (q.data ?? []).filter(d => d.parent_id === id).flatMap(d => [d.id, ...descendants(d.id)])
  return (
    <>
      <PageHeader title="Manage Departments" description="Build nested teams and open the people assigned to each department." actions={<Button disabled={!canAdd} onClick={() => { setNewParent(''); setEditing('new') }}><Plus className="h-4 w-4" />Add Department</Button>} />
      {branches.isError && <ErrorState message={errorMessage(branches.error)} onRetry={() => branches.refetch()} />}
      {branches.isSuccess && !canAdd && <div className="mb-4"><Notice tone="warning"><Link className="font-medium underline" to="/branches">Add an active branch</Link> before creating departments.</Notice></div>}
      <Card>
        {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="No departments yet" description="Create the first department to start organizing employees." /> : (
          <div className="overflow-x-auto"><table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Dept name</Th><Th>Description</Th><Th>Parent</Th><Th>Employees</Th><Th>Designations</Th><Th className="text-right">Actions</Th></tr></thead>
            <tbody className="divide-y divide-border">{q.data.map((d) => (
              <tr key={d.id}><Td className="font-semibold">{d.name}</Td><Td className="max-w-xs truncate text-muted">{d.description ?? '-'}</Td><Td>{d.parent_id ? names[d.parent_id] : 'Top level'}</Td>
                <Td>{canReadEmployees ? <Link className="font-medium text-primary hover:underline" to={`/employees?department_id=${d.id}&status=all`} title={`View employees in ${d.name}`}>{d.employee_count} employees</Link> : `${d.employee_count} employees`}</Td><Td><button className="cursor-pointer text-primary hover:underline" onClick={() => setViewing(d)}>{d.designation_count} view</button></Td>
                <Td><div className="flex flex-wrap justify-end gap-2">
                  {canManageAttendance && <Button asChild size="sm" variant="outline"><Link to={`/attendance?tab=access&department_id=${d.id}`}>Attendance access</Link></Button>}
                  <Button size="sm" variant="outline" disabled={!canAdd} onClick={() => { setNewParent(d.id); setEditing('new') }}>Add subdepartment</Button><EditBtn onClick={() => setEditing(d)} /><ConfirmButton label="Delete" title="Delete department" message={`Delete ${d.name}? This only works when it has no employees.`} onConfirm={() => del.mutate(d.id)} />
                </div></Td></tr>))}</tbody></table></div>)}
      </Card>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent title={isEdit ? 'Edit department' : 'Add department'}>
          <form onSubmit={handleSubmit((v) => save.mutate({ name: v.name, description: v.description || null, parent_id: v.parent_id || null }))} className="space-y-3">
            <Field id="dp-n" label="Name">{(a) => <Input {...a} {...register('name', { required: true })} />}</Field>
            <Field id="dp-d" label="Description">{(a) => <Input {...a} {...register('description')} />}</Field>
            <Field id="dp-p" label="Parent department">{(a) => <Select {...a} {...register('parent_id')}><option value="">None (top level)</option>{q.data?.filter((d) => !isEdit || (d.id !== editing.id && !descendants(editing.id).includes(d.id))).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select>}</Field>
            <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending} disabled={!isEdit && !canAdd}>Save</Button></div>
          </form>
        </DialogContent>
      </Dialog>
      <Designations dept={viewing} onClose={() => setViewing(null)} />
    </>
  )
}

export function BranchesPage() {
  const q = useGet<Branch[]>('/branches')
  const { data: me } = useMe()
  const [editing, setEditing] = React.useState<Branch | 'new' | null>(null)
  const [view, updateView] = useViewQuery()
  const premises = q.data?.find(branch => branch.id === view.get('premises'))
  const setPremises = (branch: Branch | null) => updateView({ premises: branch?.id ?? null })
  const requestedStatus = view.get('status')
  const status = requestedStatus === 'inactive' || requestedStatus === 'all' ? requestedStatus : 'active'
  const search = view.get('q') ?? ''
  const [action, setAction] = React.useState<{ branch: Branch; type: 'status' | 'delete' } | null>(null)
  const { register, handleSubmit, reset } = useForm<{ name: string; code: string; city: string; address: string; phone: string; email: string }>()
  React.useEffect(() => { reset(editing && editing !== 'new' ? {
    name: editing.name, code: editing.code ?? '', city: editing.city ?? '', address: editing.address ?? '',
    phone: editing.phone ?? '', email: editing.email ?? '',
  } : { name: '', code: '', city: '', address: '', phone: '', email: '' }) }, [editing, reset])
  const isEdit = editing && editing !== 'new'
  const invalidate = ['/branches', '/dashboard', '/employees/setup', '/attendance']
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/branches/${editing.id}` : '/branches', { invalidate, success: 'Saved', onSuccess: () => { if (!isEdit) updateView({ status: null, q: null }); setEditing(null) } })
  const del = useSend<string>('DELETE', (id) => `/branches/${id}`, { invalidate, success: 'Branch deleted', onSuccess: () => setAction(null) })
  const toggle = useSend<{ name: string; is_active: boolean }>('PUT', `/branches/${action?.branch.id}`, {
    invalidate, success: 'Branch status updated', onSuccess: () => setAction(null),
  })
  const query = search.trim().toLowerCase()
  const rows = (q.data ?? []).filter(b => (status === 'all' || b.is_active === (status === 'active'))
    && [b.name, b.code, b.city, b.address, b.email].some(value => value?.toLowerCase().includes(query)))
  return (
    <>
      <PageHeader title="Branches" description="Manage branch details and the locations where employees can punch." actions={<Button onClick={() => setEditing('new')}><Plus className="h-4 w-4" />Add Branch</Button>} />
      <Card>
        <CardHeader>
          <CardTitle>Branch directory</CardTitle>
          <div className="flex flex-wrap items-center gap-2">
            <Select aria-label="Branch status" value={status} onChange={e => updateView({ status: e.target.value })} className="w-40">
              <option value="active">Active branches</option><option value="inactive">Inactive branches</option><option value="all">All branches</option>
            </Select>
            <Input aria-label="Search branches" placeholder="Search branches" value={search} onChange={e => updateView({ q: e.target.value })} className="w-44" />
          </div>
        </CardHeader>
        {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : !rows.length ? <EmptyState title={q.data?.length ? 'No branches match' : 'No branches yet'} /> : (
          <div className="overflow-x-auto"><table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Branch</Th><Th>Actions</Th><Th>Contact</Th><Th>Attendance premises</Th><Th>Employees</Th><Th>Created</Th></tr></thead>
            <tbody className="divide-y divide-border">{rows.map(b => (
              <tr key={b.id}>
                <Td><p className="font-semibold">{b.name}</p><p className="text-xs text-muted">{[b.code, b.city, b.address].filter(Boolean).join(' · ')}</p>{!b.is_active && <Badge className="mt-1">Inactive</Badge>}</Td>
                <Td>
                  <Menu><MenuTrigger asChild><Button variant="outline" size="sm" aria-label={`Actions for ${b.name}`}><Ellipsis className="h-4 w-4" />Actions</Button></MenuTrigger>
                    <MenuContent align="start">
                      <MenuItem onSelect={() => setEditing(b)}>Edit branch</MenuItem>
                      <MenuItem onSelect={() => setPremises(b)}>Manage premises</MenuItem>
                      {me?.permissions.includes('attendance.manage') && <MenuItem asChild><Link to={`/attendance?tab=access&branch_id=${b.id}`}>Bulk attendance settings</Link></MenuItem>}
                      {me?.permissions.includes('attendance.manage') && <MenuItem asChild><Link to={`/attendance?tab=tools&branch_id=${b.id}`}>Import biometric punches</Link></MenuItem>}
                      <MenuItem onSelect={() => setAction({ branch: b, type: 'status' })}>{b.is_active ? 'Deactivate' : 'Reactivate'}</MenuItem>
                      {!b.employee_count && <MenuItem className="text-danger" onSelect={() => setAction({ branch: b, type: 'delete' })}>Delete branch</MenuItem>}
                    </MenuContent>
                  </Menu>
                </Td>
                <Td><p>{b.phone ?? '-'}</p>{b.email && <p className="text-xs text-muted">{b.email}</p>}</Td>
                <Td><Button variant="ghost" size="sm" onClick={() => setPremises(b)}><MapPin className="h-4 w-4" />{b.premise_count ? `${b.premise_count} saved` : 'Anywhere'}</Button></Td>
                <Td>{me?.permissions.includes('employees.read') ? <Link className="font-medium text-primary hover:underline" to={`/employees?branch_id=${b.id}&status=all`} aria-label={`View employees in ${b.name}`}>{b.employee_count}</Link> : <Badge>{b.employee_count}</Badge>}</Td>
                <Td>{formatDate(b.created_at, { dateStyle: 'medium' })}</Td>
              </tr>))}</tbody></table></div>)}
      </Card>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent title={isEdit ? 'Edit branch' : 'Add branch'}>
          <form onSubmit={handleSubmit((v) => save.mutate(Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x || null]))))} className="grid gap-3 sm:grid-cols-2">
            <Field id="b-n" label="Name">{(a) => <Input {...a} {...register('name', { required: true })} />}</Field>
            <Field id="b-c" label="Code">{(a) => <Input {...a} {...register('code')} />}</Field>
            <Field id="b-ci" label="City">{(a) => <Input {...a} {...register('city')} />}</Field>
            <Field id="b-p" label="Phone">{(a) => <Input {...a} {...register('phone')} />}</Field>
            <Field id="b-email" label="Email">{(a) => <Input type="email" {...a} {...register('email')} />}</Field>
            <div className="sm:col-span-2"><Field id="b-a" label="Address">{(a) => <Input {...a} {...register('address')} />}</Field></div>
            <div className="flex justify-end gap-2 sm:col-span-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending}>Save</Button></div>
          </form>
        </DialogContent>
      </Dialog>
      {premises && <React.Suspense fallback={<p role="status" className="mt-3 text-sm text-muted">Loading premises…</p>}>
        <BranchPremises key={premises.id} branch={premises} onClose={() => setPremises(null)} />
      </React.Suspense>}
      <Dialog open={!!action} onOpenChange={open => { if (!open) setAction(null) }}>
        <DialogContent title={action ? `${action.type === 'delete' ? 'Delete' : action.branch.is_active ? 'Deactivate' : 'Reactivate'} ${action.branch.name}?` : 'Branch action'}
          description={action?.type === 'delete' ? 'The branch and its saved premises will be removed.' : action?.branch.is_active
            ? 'This branch will become unavailable for new employee assignments.' : 'This branch will be available for employee assignments again.'}>
          <div className="flex justify-end gap-2">
            <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button variant={action?.type === 'delete' || action?.branch.is_active ? 'danger' : 'primary'} loading={del.isPending || toggle.isPending} onClick={() => {
              if (!action) return
              if (action.type === 'delete') del.mutate(action.branch.id)
              else toggle.mutate({ name: action.branch.name, is_active: !action.branch.is_active })
            }}>{action?.type === 'delete' ? 'Delete branch' : action?.branch.is_active ? 'Deactivate branch' : 'Reactivate branch'}</Button>
          </div>
        </DialogContent>
      </Dialog>
    </>
  )
}

// ------------------------------------------------------------------ HR policies
interface Policy { grace_minutes: number; late_mode: 'full' | 'grace_exempt'; overtime_threshold_minutes: number; weekend_days: number[]; default_start: string; default_end: string; default_break_minutes: number }
const DAYS = ['Mon', 'Tue', 'Wed', 'Thu', 'Fri', 'Sat', 'Sun']

function AttendancePolicy() {
  const q = useGet<Policy>('/attendance/policy')
  const [p, setP] = React.useState<Policy | null>(null)
  React.useEffect(() => { if (q.data) setP(q.data) }, [q.data])
  const save = useSend<Policy>('PUT', '/attendance/policy', { invalidate: ['/attendance', '/dashboard', '/employees/setup'], success: 'Attendance policy saved' })
  if (q.isError) return <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
  if (!p) return <Skeleton className="h-48 w-full" />
  const num = (k: keyof Policy) => (e: React.ChangeEvent<HTMLInputElement>) => setP({ ...p, [k]: Number(e.target.value) })
  return (
    <Card className="max-w-3xl"><CardBody className="space-y-5">
      <div className="grid gap-4 sm:grid-cols-3">
        <Field id="p-s" label="Default shift start">{(a) => <Input type="time" value={p.default_start} onChange={(e) => setP({ ...p, default_start: e.target.value })} {...a} />}</Field>
        <Field id="p-e" label="Default shift end">{(a) => <Input type="time" value={p.default_end} onChange={(e) => setP({ ...p, default_end: e.target.value })} {...a} />}</Field>
        <Field id="p-b" label="Unpaid break (minutes)">{(a) => <Input type="number" min={0} value={p.default_break_minutes} onChange={num('default_break_minutes')} {...a} />}</Field>
        <Field id="p-g" label="Grace period (minutes)">{(a) => <Input type="number" min={0} value={p.grace_minutes} onChange={num('grace_minutes')} {...a} />}</Field>
        <Field id="p-m" label="Late counting" hint={p.late_mode === 'full' ? 'Past the grace window, all minutes from shift start count as late.' : 'Grace minutes are always excused; only the minutes beyond them count.'}>
          {(a) => <Select value={p.late_mode} onChange={(e) => setP({ ...p, late_mode: e.target.value as Policy['late_mode'] })} {...a}><option value="grace_exempt">Grace exempt</option><option value="full">Full lateness</option></Select>}</Field>
        <Field id="p-o" label="Overtime starts after (minutes)">{(a) => <Input type="number" min={0} value={p.overtime_threshold_minutes} onChange={num('overtime_threshold_minutes')} {...a} />}</Field>
      </div>
      <fieldset><legend className="mb-2 text-sm font-medium">Weekly off days</legend><div className="flex flex-wrap gap-2">
        {DAYS.map((d, i) => { const on = p.weekend_days.includes(i); return <button key={d} type="button" aria-pressed={on} onClick={() => setP({ ...p, weekend_days: on ? p.weekend_days.filter((x) => x !== i) : [...p.weekend_days, i] })} className={`cursor-pointer rounded-full px-4 py-1.5 text-sm font-medium ${on ? 'bg-primary text-white' : 'bg-surface-2 text-muted'}`}>{d}</button> })}</div></fieldset>
      <Button loading={save.isPending} onClick={() => save.mutate(p)}>Save policy</Button>
    </CardBody></Card>
  )
}

interface LType { id: string; name: string; days_per_year: string; is_paid: boolean; allow_negative: boolean; allow_half_day: boolean; after_probation: boolean; carry_forward_max: string; is_active: boolean }
function LeaveTypes() {
  const q = useGet<LType[]>('/leave/types')
  const [editing, setEditing] = React.useState<LType | 'new' | null>(null)
  const year = new Date().getFullYear()
  const { register, handleSubmit, reset } = useForm<{ name: string; days_per_year: string; carry_forward_max: string; is_paid: boolean; allow_negative: boolean; allow_half_day: boolean; after_probation: boolean }>()
  React.useEffect(() => { reset(editing && editing !== 'new' ? { ...editing } : { name: '', days_per_year: '0', carry_forward_max: '0', is_paid: true, allow_negative: false, allow_half_day: true, after_probation: false }) }, [editing, reset])
  const isEdit = editing && editing !== 'new'
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/leave/types/${editing.id}` : '/leave/types', { invalidate: ['/leave', '/employees/setup'], success: 'Saved', onSuccess: () => setEditing(null) })
  const grant = useSend<number, { entries_created: number }>('POST', (y) => `/leave/grants/run?year=${y}`, { invalidate: ['/leave'], onSuccess: (r, y) => toast.success(r.entries_created ? `${r.entries_created} entitlements granted for ${y}` : `Nothing new to grant for ${y}`) })
  const carry = useSend<number, { entries_created: number }>('POST', (y) => `/leave/carry-forward?from_year=${y}`, { invalidate: ['/leave'], onSuccess: (r, y) => toast.success(`${r.entries_created} balances carried from ${y}`) })
  return (
    <>
      <div className="mb-4 flex flex-wrap justify-end gap-2">
        <ConfirmButton variant="outline" size="md" label={`Grant ${year} entitlements`} title={`Grant ${year} entitlements`} message="Adds each employee's yearly entitlement (pro-rated for mid-year joiners). Safe to repeat: existing grants are never duplicated." onConfirm={() => grant.mutate(year)} />
        <ConfirmButton variant="outline" size="md" label={`Carry forward ${year - 1} to ${year}`} title="Carry forward unused leave" message="Carries unused balance into the new year, capped per leave type. Safe to repeat." onConfirm={() => carry.mutate(year - 1)} />
        <Button onClick={() => setEditing('new')}><Plus className="h-4 w-4" />Add leave type</Button>
      </div>
      <Card>{q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} /> : (
        <table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Type</Th><Th>Days / year</Th><Th>Carry max</Th><Th>Rules</Th><Th className="text-right">Actions</Th></tr></thead>
          <tbody className="divide-y divide-border">{q.data!.map((t) => (
            <tr key={t.id}><Td className="font-semibold">{t.name}</Td><Td>{Number(t.days_per_year)}</Td><Td>{Number(t.carry_forward_max)}</Td>
              <Td><div className="flex flex-wrap gap-1">{!t.is_paid && <Badge tone="warning">unpaid</Badge>}{t.allow_negative && <Badge>can go negative</Badge>}{t.after_probation && <Badge>after probation</Badge>}{!t.allow_half_day && <Badge>no half days</Badge>}</div></Td>
              <Td className="text-right"><EditBtn onClick={() => setEditing(t)} /></Td></tr>))}</tbody></table>)}</Card>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent title={isEdit ? 'Edit leave type' : 'Add leave type'}>
          <form onSubmit={handleSubmit((v) => save.mutate(v))} className="space-y-3">
            <Field id="lt-n" label="Name">{(a) => <Input {...a} {...register('name', { required: true })} />}</Field>
            <div className="grid grid-cols-2 gap-3"><Field id="lt-d" label="Days per year">{(a) => <Input type="number" step="0.5" min={0} {...a} {...register('days_per_year')} />}</Field><Field id="lt-c" label="Carry forward max">{(a) => <Input type="number" step="0.5" min={0} {...a} {...register('carry_forward_max')} />}</Field></div>
            {([['is_paid', 'Paid leave'], ['allow_negative', 'Allow negative balance'], ['allow_half_day', 'Allow half days'], ['after_probation', 'Only after probation']] as const).map(([k, l]) => <label key={k} className="flex cursor-pointer items-center gap-2 text-sm"><input type="checkbox" {...register(k)} />{l}</label>)}
            <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending}>Save</Button></div>
          </form>
        </DialogContent>
      </Dialog>
    </>
  )
}

function Holidays() {
  const [year, setYear] = React.useState(new Date().getFullYear())
  const q = useGet<{ id: string; holiday_date: string; name: string }[]>('/holidays', { year })
  const [date, setDate] = React.useState('')
  const [name, setName] = React.useState('')
  const add = useSend<{ holiday_date: string; name: string }>('POST', '/holidays', { invalidate: ['/holidays'], success: 'Holiday added', onSuccess: () => { setDate(''); setName('') } })
  const del = useSend<string>('DELETE', (id) => `/holidays/${id}`, { invalidate: ['/holidays'], success: 'Removed' })
  return (
    <div className="max-w-2xl space-y-4">
      <Card><CardBody className="flex flex-wrap items-end gap-3">
        <Field id="h-d" label="Date">{(a) => <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} {...a} />}</Field>
        <Field id="h-n" label="Name">{(a) => <Input value={name} onChange={(e) => setName(e.target.value)} {...a} />}</Field>
        <Button disabled={!date || name.length < 2} loading={add.isPending} onClick={() => add.mutate({ holiday_date: date, name })}>Add holiday</Button>
      </CardBody></Card>
      <Card><CardHeader><CardTitle>Holidays in {year}</CardTitle><div className="flex gap-1"><Button variant="outline" size="sm" onClick={() => setYear(year - 1)}>{year - 1}</Button><Button variant="outline" size="sm" onClick={() => setYear(year + 1)}>{year + 1}</Button></div></CardHeader>
        {!q.data?.length ? <EmptyState title="No holidays set for this year" /> : <ul className="divide-y divide-border">{q.data.map((h) => (
          <li key={h.id} className="flex items-center justify-between px-5 py-3 text-sm"><span><span className="font-medium">{h.name}</span><span className="ml-3 text-muted">{formatDate(h.holiday_date, { dateStyle: 'full' })}</span></span><ConfirmButton label="Remove" title="Remove holiday" message={`Remove ${h.name}?`} onConfirm={() => del.mutate(h.id)} /></li>))}</ul>}</Card>
    </div>
  )
}

export function PoliciesPage() {
  const [sp, setSp] = useSearchParams()
  const requestedTab = sp.get('tab')
  const tab = requestedTab === 'leave' || requestedTab === 'holidays' ? requestedTab : 'attendance'
  return (
    <>
      <PageHeader title="HR Policies" description="Rules that drive attendance, lateness, leave and payroll calculations." />
      <Tabs tabs={[{ id: 'attendance', label: 'Attendance' }, { id: 'leave', label: 'Leave types' }, { id: 'holidays', label: 'Holidays' }]} value={tab} onChange={id => setSp({ tab: id }, { replace: true })} />
      {tab === 'attendance' && <AttendancePolicy />}{tab === 'leave' && <LeaveTypes />}{tab === 'holidays' && <Holidays />}
    </>
  )
}
