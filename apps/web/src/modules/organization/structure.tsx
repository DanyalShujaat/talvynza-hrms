import { Plus } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { toast } from 'sonner'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { ConfirmButton, SlideOver, Tabs, Td, Th } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { formatDate } from '@/lib/utils'

interface Dept { id: string; name: string; description: string | null; parent_id: string | null; employee_count: number; designation_count: number; is_active: boolean }
interface Desig { id: string; name: string; department_id: string | null; grade: string | null; employee_count: number }
interface Branch { id: string; name: string; code: string | null; city: string | null; address: string | null; phone: string | null; employee_count: number; is_active: boolean }

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
  const [editing, setEditing] = React.useState<Dept | 'new' | null>(null)
  const [newParent, setNewParent] = React.useState('')
  const [viewing, setViewing] = React.useState<Dept | null>(null)
  const { register, handleSubmit, reset } = useForm<{ name: string; description: string; parent_id: string }>()
  React.useEffect(() => { reset(editing && editing !== 'new' ? { name: editing.name, description: editing.description ?? '', parent_id: editing.parent_id ?? '' } : { name: '', description: '', parent_id: newParent }) }, [editing, newParent, reset])
  const isEdit = editing && editing !== 'new'
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/departments/${editing.id}` : '/departments', { invalidate: ['/departments', '/dashboard'], success: 'Saved', onSuccess: () => setEditing(null) })
  const del = useSend<string>('DELETE', (id) => `/departments/${id}`, { invalidate: ['/departments', '/dashboard'], success: 'Department deleted' })
  const names = Object.fromEntries((q.data ?? []).map((d) => [d.id, d.name]))
  const descendants = (id: string): string[] => (q.data ?? []).filter(d => d.parent_id === id).flatMap(d => [d.id, ...descendants(d.id)])
  return (
    <>
      <PageHeader title="Manage Departments" description="Build nested teams and open the people assigned to each department." actions={<Button onClick={() => { setNewParent(''); setEditing('new') }}><Plus className="h-4 w-4" />Add Department</Button>} />
      <Card>
        {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="No departments yet" description="Create the first department to start organizing employees." /> : (
          <div className="overflow-x-auto"><table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Dept name</Th><Th>Description</Th><Th>Parent</Th><Th>Employees</Th><Th>Designations</Th><Th className="text-right">Actions</Th></tr></thead>
            <tbody className="divide-y divide-border">{q.data.map((d) => (
              <tr key={d.id}><Td className="font-semibold">{d.name}</Td><Td className="max-w-xs truncate text-muted">{d.description ?? '-'}</Td><Td>{d.parent_id ? names[d.parent_id] : 'Top level'}</Td>
                <Td><Link className="font-medium text-primary hover:underline" to={`/employees?department_id=${d.id}`} title={`View employees in ${d.name}`}>{d.employee_count} employees</Link></Td><Td><button className="cursor-pointer text-primary hover:underline" onClick={() => setViewing(d)}>{d.designation_count} view</button></Td>
                <Td className="space-x-2 text-right"><Button size="sm" variant="outline" onClick={() => { setNewParent(d.id); setEditing('new') }}>Add subdepartment</Button><EditBtn onClick={() => setEditing(d)} /><ConfirmButton label="Delete" title="Delete department" message={`Delete ${d.name}? This only works when it has no employees.`} onConfirm={() => del.mutate(d.id)} /></Td></tr>))}</tbody></table></div>)}
      </Card>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent title={isEdit ? 'Edit department' : 'Add department'}>
          <form onSubmit={handleSubmit((v) => save.mutate({ name: v.name, description: v.description || null, parent_id: v.parent_id || null }))} className="space-y-3">
            <Field id="dp-n" label="Name">{(a) => <Input {...a} {...register('name', { required: true })} />}</Field>
            <Field id="dp-d" label="Description">{(a) => <Input {...a} {...register('description')} />}</Field>
            <Field id="dp-p" label="Parent department">{(a) => <Select {...a} {...register('parent_id')}><option value="">None (top level)</option>{q.data?.filter((d) => !isEdit || (d.id !== editing.id && !descendants(editing.id).includes(d.id))).map((d) => <option key={d.id} value={d.id}>{d.name}</option>)}</Select>}</Field>
            <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending}>Save</Button></div>
          </form>
        </DialogContent>
      </Dialog>
      <Designations dept={viewing} onClose={() => setViewing(null)} />
    </>
  )
}

export function BranchesPage() {
  const q = useGet<Branch[]>('/branches')
  const [editing, setEditing] = React.useState<Branch | 'new' | null>(null)
  const { register, handleSubmit, reset } = useForm<{ name: string; code: string; city: string; address: string; phone: string }>()
  React.useEffect(() => { reset(editing && editing !== 'new' ? { name: editing.name, code: editing.code ?? '', city: editing.city ?? '', address: editing.address ?? '', phone: editing.phone ?? '' } : { name: '', code: '', city: '', address: '', phone: '' }) }, [editing, reset])
  const isEdit = editing && editing !== 'new'
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/branches/${editing.id}` : '/branches', { invalidate: ['/branches', '/dashboard'], success: 'Saved', onSuccess: () => setEditing(null) })
  const del = useSend<string>('DELETE', (id) => `/branches/${id}`, { invalidate: ['/branches', '/dashboard'], success: 'Branch deleted' })
  return (
    <>
      <PageHeader title="Branches" description="Offices and locations" actions={<Button onClick={() => setEditing('new')}><Plus className="h-4 w-4" />Add Branch</Button>} />
      <Card>
        {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /> : !q.data?.length ? <EmptyState title="No branches yet" /> : (
          <div className="overflow-x-auto"><table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Branch</Th><Th>Code</Th><Th>City</Th><Th>Phone</Th><Th>Employees</Th><Th className="text-right">Actions</Th></tr></thead>
            <tbody className="divide-y divide-border">{q.data.map((b) => (
              <tr key={b.id}><Td className="font-semibold">{b.name}<p className="text-xs font-normal text-muted">{b.address}</p></Td><Td>{b.code ?? '-'}</Td><Td>{b.city ?? '-'}</Td><Td>{b.phone ?? '-'}</Td><Td><Badge tone="warning">{b.employee_count}</Badge></Td>
                <Td className="space-x-2 text-right"><EditBtn onClick={() => setEditing(b)} /><ConfirmButton label="Delete" title="Delete branch" message={`Delete ${b.name}?`} onConfirm={() => del.mutate(b.id)} /></Td></tr>))}</tbody></table></div>)}
      </Card>
      <Dialog open={!!editing} onOpenChange={(o) => !o && setEditing(null)}>
        <DialogContent title={isEdit ? 'Edit branch' : 'Add branch'}>
          <form onSubmit={handleSubmit((v) => save.mutate(Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x || null]))))} className="grid gap-3 sm:grid-cols-2">
            <Field id="b-n" label="Name">{(a) => <Input {...a} {...register('name', { required: true })} />}</Field>
            <Field id="b-c" label="Code">{(a) => <Input {...a} {...register('code')} />}</Field>
            <Field id="b-ci" label="City">{(a) => <Input {...a} {...register('city')} />}</Field>
            <Field id="b-p" label="Phone">{(a) => <Input {...a} {...register('phone')} />}</Field>
            <div className="sm:col-span-2"><Field id="b-a" label="Address">{(a) => <Input {...a} {...register('address')} />}</Field></div>
            <div className="flex justify-end gap-2 sm:col-span-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending}>Save</Button></div>
          </form>
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
  const save = useSend<Policy>('PUT', '/attendance/policy', { invalidate: ['/attendance', '/dashboard'], success: 'Attendance policy saved' })
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
  const save = useSend<Record<string, unknown>>(isEdit ? 'PUT' : 'POST', isEdit ? `/leave/types/${editing.id}` : '/leave/types', { invalidate: ['/leave'], success: 'Saved', onSuccess: () => setEditing(null) })
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
  const [tab, setTab] = React.useState<'attendance' | 'leave' | 'holidays'>('attendance')
  return (
    <>
      <PageHeader title="HR Policies" description="Rules that drive attendance, lateness, leave and payroll calculations." />
      <Tabs tabs={[{ id: 'attendance', label: 'Attendance' }, { id: 'leave', label: 'Leave types' }, { id: 'holidays', label: 'Holidays' }]} value={tab} onChange={setTab} />
      {tab === 'attendance' && <AttendancePolicy />}{tab === 'leave' && <LeaveTypes />}{tab === 'holidays' && <Holidays />}
    </>
  )
}
