import { GraduationCap, Plus, Trash2, Upload } from 'lucide-react'
import * as React from 'react'
import { useForm } from 'react-hook-form'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { Avatar, ConfirmButton, StatusText, Tabs, Td, Th } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { money, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { formatDate } from '@/lib/utils'
import { Opts, useOrgLists, type EmpRow } from '@/modules/people/employees'

interface Detail extends EmpRow {
  emergency_contacts: { name?: string; phone?: string; relationship?: string }[]
  preferred_name: string | null; gender: string | null; date_of_birth: string | null; nationality: string | null; address: string | null
  employment_type: string; contract_type: string | null; contract_end: string | null; work_location: string | null; probation_end: string | null
  confirmation_date: string | null; exit_date: string | null; payment_method: string | null; national_id: string | null; bank_name: string | null; bank_account: string | null
}

function EditMyProfile({ emp }: { emp: Detail }) {
  const [open, setOpen] = React.useState(false)
  const [f, setF] = React.useState({ preferred_name: '', phone: '', address: '', emergency_contacts: emp.emergency_contacts ?? [] })
  const save = useSend<typeof f>('PATCH', '/me/employee', { invalidate: ['/me/employee', '/employees'], success: 'Your contact details have been updated', onSuccess: () => setOpen(false) })
  return <Dialog open={open} onOpenChange={setOpen}><Button onClick={() => { setF({ preferred_name: emp.preferred_name ?? '', phone: emp.phone ?? '', address: emp.address ?? '', emergency_contacts: emp.emergency_contacts ?? [] }); setOpen(true) }}>Edit my details</Button><DialogContent title="My contact details" description="Update your personal contact information. Ask HR to change employment or banking details.">
    <form className="space-y-4" onSubmit={e => { e.preventDefault(); save.mutate(f) }}>
      <Field id="self-name" label="Preferred name">{a => <Input {...a} maxLength={80} value={f.preferred_name} onChange={e => setF({ ...f, preferred_name: e.target.value })} />}</Field>
      <Field id="self-phone" label="Mobile number">{a => <Input {...a} type="tel" maxLength={40} value={f.phone} onChange={e => setF({ ...f, phone: e.target.value })} />}</Field>
      <Field id="self-address" label="Home address">{a => <Input {...a} maxLength={400} value={f.address} onChange={e => setF({ ...f, address: e.target.value })} />}</Field>
      <fieldset className="space-y-3 rounded-lg border border-border p-3"><legend className="px-1 text-sm font-semibold">Emergency contacts</legend>
        {f.emergency_contacts.map((c, i) => <div key={i} className="space-y-2 border-b border-border pb-3 last:border-0">{(['name', 'relationship', 'phone'] as const).map(key => <Field key={key} id={`contact-${i}-${key}`} label={`${key === 'name' ? 'Name' : key === 'phone' ? 'Phone' : 'Relationship'} ${i + 1}`}>{a => <Input {...a} required={key !== 'relationship'} maxLength={key === 'phone' ? 40 : 100} value={c[key] ?? ''} onChange={e => setF({ ...f, emergency_contacts: f.emergency_contacts.map((v, n) => n === i ? { ...v, [key]: e.target.value } : v) })} />}</Field>)}<Button type="button" size="sm" variant="ghost" onClick={() => setF({ ...f, emergency_contacts: f.emergency_contacts.filter((_, n) => n !== i) })}>Remove contact</Button></div>)}
        <Button type="button" variant="outline" size="sm" disabled={f.emergency_contacts.length >= 5} onClick={() => setF({ ...f, emergency_contacts: [...f.emergency_contacts, { name: '', phone: '', relationship: '' }] })}>Add emergency contact</Button>
      </fieldset>
      <div className="flex justify-end gap-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={save.isPending}>Save my details</Button></div>
    </form></DialogContent></Dialog>
}
const LIFECYCLE = [
  ['confirmation', 'Confirm after probation'], ['probation_extension', 'Extend probation'], ['promotion', 'Promotion'], ['transfer', 'Transfer'],
  ['contract_renewal', 'Renew contract'], ['suspension', 'Suspend'], ['reinstatement', 'Reinstate'], ['resignation', 'Resignation'],
  ['termination', 'Termination'], ['retirement', 'Retirement'], ['rehire', 'Rehire'],
]

function LifecycleDialog({ emp }: { emp: Detail }) {
  const [open, setOpen] = React.useState(false)
  const [kind, setKind] = React.useState('confirmation')
  const [date, setDate] = React.useState(new Date().toISOString().slice(0, 10))
  const [d, setD] = React.useState<Record<string, string>>({})
  const { branches, departments, designations } = useOrgLists()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const set = (k: string, v: string) => setD((x) => ({ ...x, [k]: v }))
  const m = useSend<unknown>('POST', `/employees/${emp.id}/lifecycle`, { invalidate: ['/employees', '/dashboard'], success: 'Recorded', onSuccess: () => { setOpen(false); setD({}) } })
  const details = Object.fromEntries(Object.entries(d).filter(([, v]) => v))
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="outline" onClick={() => setOpen(true)}>Lifecycle action</Button>
      <DialogContent title="Record a lifecycle event" description="Every event is dated and written to the audit log.">
        <div className="space-y-4">
          <Field id="lc-kind" label="Event">{(a) => <Select value={kind} onChange={(e) => { setKind(e.target.value); setD({}) }} {...a}>{LIFECYCLE.map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}</Field>
          <Field id="lc-date" label="Effective date">{(a) => <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} {...a} />}</Field>
          {kind === 'promotion' && <Field id="lc-des" label="New designation">{(a) => <Select value={d.designation_id ?? ''} onChange={(e) => set('designation_id', e.target.value)} {...a}><Opts list={designations} blank="Select" /></Select>}</Field>}
          {kind === 'transfer' && <>
            <Field id="lc-br" label="New branch">{(a) => <Select value={d.branch_id ?? ''} onChange={(e) => set('branch_id', e.target.value)} {...a}><Opts list={branches} blank="Keep current" /></Select>}</Field>
            <Field id="lc-dp" label="New department">{(a) => <Select value={d.department_id ?? ''} onChange={(e) => set('department_id', e.target.value)} {...a}><Opts list={departments} blank="Keep current" /></Select>}</Field>
            <Field id="lc-mg" label="New manager">{(a) => <Select value={d.manager_id ?? ''} onChange={(e) => set('manager_id', e.target.value)} {...a}><Opts list={(people.data?.items ?? []).filter((p) => p.id !== emp.id).map((p) => ({ id: p.id, name: p.full_name }))} blank="Keep current" /></Select>}</Field></>}
          {kind === 'probation_extension' && <Field id="lc-pe" label="New probation end">{(a) => <Input type="date" value={d.probation_end ?? ''} onChange={(e) => set('probation_end', e.target.value)} {...a} />}</Field>}
          {kind === 'contract_renewal' && <Field id="lc-ce" label="New contract end">{(a) => <Input type="date" value={d.contract_end ?? ''} onChange={(e) => set('contract_end', e.target.value)} {...a} />}</Field>}
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate({ event_type: kind, effective_date: date, details } as never)}>Record</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function EditDialog({ emp }: { emp: Detail }) {
  const [open, setOpen] = React.useState(false)
  const { branches, departments, designations } = useOrgLists()
  const { data: me } = useMe()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 })
  const canBank = me?.permissions.includes('bank.read')
  const { register, handleSubmit } = useForm({ values: {
    first_name: emp.first_name, last_name: emp.last_name, email: emp.email ?? '', phone: emp.phone ?? '', bio_id: emp.bio_id ?? '', address: emp.address ?? '', gender: emp.gender ?? '',
    date_of_birth: emp.date_of_birth ?? '', national_id: emp.national_id ?? '', branch_id: emp.branch_id ?? '', department_id: emp.department_id ?? '', designation_id: emp.designation_id ?? '',
    manager_id: emp.manager_id ?? '', work_location: emp.work_location ?? '', contract_end: emp.contract_end ?? '', bank_name: emp.bank_name ?? '', bank_account: emp.bank_account ?? '', payment_method: emp.payment_method ?? '',
  } })
  const m = useSend<Record<string, unknown>>('PATCH', `/employees/${emp.id}`, { invalidate: ['/employees'], success: 'Saved', onSuccess: () => setOpen(false) })
  const submit = (v: Record<string, string>) => {
    const body: Record<string, unknown> = {}
    for (const [k, val] of Object.entries(v)) {
      if (!canBank && ['bank_name', 'bank_account', 'payment_method'].includes(k)) continue
      body[k] = val === '' ? null : val
    }
    m.mutate(body)
  }
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}>Edit profile</Button>
      <DialogContent className="max-h-[90vh] max-w-2xl overflow-auto" title="Edit employee">
        <form onSubmit={handleSubmit(submit)} className="grid gap-3 sm:grid-cols-2">
          <Field id="e-fn" label="First name">{(a) => <Input {...a} {...register('first_name')} />}</Field>
          <Field id="e-ln" label="Last name">{(a) => <Input {...a} {...register('last_name')} />}</Field>
          <Field id="e-em" label="Email">{(a) => <Input type="email" {...a} {...register('email')} />}</Field>
          <Field id="e-ph" label="Mobile">{(a) => <Input {...a} {...register('phone')} />}</Field>
          <Field id="e-bio" label="Biometric ID">{(a) => <Input {...a} {...register('bio_id')} />}</Field>
          <Field id="e-dob" label="Date of birth">{(a) => <Input type="date" {...a} {...register('date_of_birth')} />}</Field>
          <Field id="e-nid" label="National ID">{(a) => <Input {...a} {...register('national_id')} />}</Field>
          <Field id="e-g" label="Gender">{(a) => <Select {...a} {...register('gender')}><option value="">Not set</option><option value="female">Female</option><option value="male">Male</option><option value="other">Other</option></Select>}</Field>
          <Field id="e-br" label="Branch">{(a) => <Select {...a} {...register('branch_id')}><Opts list={branches} /></Select>}</Field>
          <Field id="e-dp" label="Department">{(a) => <Select {...a} {...register('department_id')}><Opts list={departments} /></Select>}</Field>
          <Field id="e-ds" label="Designation">{(a) => <Select {...a} {...register('designation_id')}><Opts list={designations} /></Select>}</Field>
          <Field id="e-mg" label="Reporting manager">{(a) => <Select {...a} {...register('manager_id')}><Opts list={(people.data?.items ?? []).filter((p) => p.id !== emp.id).map((p) => ({ id: p.id, name: p.full_name }))} /></Select>}</Field>
          <Field id="e-wl" label="Work location">{(a) => <Input {...a} {...register('work_location')} />}</Field>
          <Field id="e-ce" label="Contract ends">{(a) => <Input type="date" {...a} {...register('contract_end')} />}</Field>
          <div className="sm:col-span-2"><Field id="e-ad" label="Address">{(a) => <Input {...a} {...register('address')} />}</Field></div>
          {canBank && <>
            <Field id="e-pm" label="Payment method">{(a) => <Select {...a} {...register('payment_method')}><option value="">Not set</option><option value="bank_transfer">Bank transfer</option><option value="cash">Cash</option><option value="cheque">Cheque</option></Select>}</Field>
            <Field id="e-bn" label="Bank name">{(a) => <Input {...a} {...register('bank_name')} />}</Field>
            <div className="sm:col-span-2"><Field id="e-ba" label="Account number / IBAN">{(a) => <Input {...a} {...register('bank_account')} />}</Field></div></>}
          <div className="flex justify-end gap-2 sm:col-span-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={m.isPending}>Save</Button></div>
        </form>
      </DialogContent>
    </Dialog>
  )
}

const Row = ({ k, v }: { k: string; v: React.ReactNode }) => <div className="flex justify-between gap-4 border-b border-border py-2.5 text-sm last:border-0"><dt className="text-muted">{k}</dt><dd className="text-right font-medium">{v || '-'}</dd></div>

function Overview({ e }: { e: Detail }) {
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Personal</CardTitle></CardHeader><CardBody><dl>
        <Row k="Email" v={e.email} /><Row k="Mobile" v={e.phone} /><Row k="Gender" v={e.gender} /><Row k="Date of birth" v={e.date_of_birth && formatDate(e.date_of_birth, { dateStyle: 'medium' })} />
        <Row k="National ID" v={e.national_id} /><Row k="Address" v={e.address} /><Row k="Preferred name" v={e.preferred_name} /></dl></CardBody></Card>
      <Card><CardHeader><CardTitle>Employment</CardTitle></CardHeader><CardBody><dl>
        <Row k="Employee ID" v={e.employee_code} /><Row k="Biometric ID" v={e.bio_id} /><Row k="Branch" v={e.branch} /><Row k="Department" v={e.department} /><Row k="Designation" v={e.designation} />
        <Row k="Type" v={e.employment_type.replace('_', ' ')} /><Row k="Joined" v={formatDate(e.joining_date, { dateStyle: 'medium' })} /><Row k="Probation ends" v={e.probation_end && formatDate(e.probation_end, { dateStyle: 'medium' })} />
        <Row k="Contract ends" v={e.contract_end && formatDate(e.contract_end, { dateStyle: 'medium' })} /><Row k="Left on" v={e.exit_date && formatDate(e.exit_date, { dateStyle: 'medium' })} /></dl></CardBody></Card>
      {(e.bank_name || e.bank_account) && <Card><CardHeader><CardTitle>Payment</CardTitle></CardHeader><CardBody><dl><Row k="Method" v={e.payment_method?.replace('_', ' ')} /><Row k="Bank" v={e.bank_name} /><Row k="Account" v={e.bank_account} /></dl></CardBody></Card>}
      <Card><CardHeader><CardTitle>Emergency contacts</CardTitle></CardHeader><CardBody>{e.emergency_contacts?.length ? e.emergency_contacts.map((c, i) => <div key={i} className="border-b border-border py-2 last:border-0"><p className="font-semibold">{c.name}</p><p className="text-sm text-muted">{[c.relationship, c.phone].filter(Boolean).join(' · ')}</p></div>) : <p className="text-sm text-muted">No emergency contact on file.</p>}</CardBody></Card>
    </div>
  )
}

interface Hist { assignments: { branch: string | null; department: string | null; designation: string | null; effective_from: string; effective_to: string | null }[]; events: { id: string; event_type: string; effective_date: string; details: Record<string, string> }[] }
function History({ id }: { id: string }) {
  const q = useGet<Hist>(`/employees/${id}/history`)
  if (q.isLoading) return <Skeleton className="h-40 w-full" />
  if (q.isError || !q.data) return <ErrorState message="Could not load history." />
  return (
    <div className="grid gap-5 lg:grid-cols-2">
      <Card><CardHeader><CardTitle>Placement history</CardTitle></CardHeader><ul className="divide-y divide-border text-sm">
        {q.data.assignments.map((a, i) => <li key={i} className="px-5 py-3"><p className="font-medium">{[a.designation, a.department, a.branch].filter(Boolean).join(' · ') || 'Unassigned'}</p><p className="text-xs text-muted">{formatDate(a.effective_from, { dateStyle: 'medium' })} to {a.effective_to ? formatDate(a.effective_to, { dateStyle: 'medium' }) : 'present'}</p></li>)}</ul></Card>
      <Card><CardHeader><CardTitle>Lifecycle events</CardTitle></CardHeader><ul className="divide-y divide-border text-sm">
        {q.data.events.map((v) => <li key={v.id} className="flex justify-between px-5 py-3"><span className="font-medium capitalize">{v.event_type.replace('_', ' ')}</span><span className="text-muted">{formatDate(v.effective_date, { dateStyle: 'medium' })}</span></li>)}</ul></Card>
    </div>
  )
}

interface Edu { id: string; level: string; degree: string; institute: string | null; obtained_marks: string | null; total_marks: string | null; grade: string | null; division: string | null; remarks: string | null }
function Education({ id, canEdit }: { id: string; canEdit: boolean }) {
  const q = useGet<Edu[]>(`/employees/${id}/education`)
  const [open, setOpen] = React.useState(false)
  const { register, handleSubmit, reset } = useForm<Omit<Edu, 'id'>>()
  const add = useSend<Omit<Edu, 'id'>>('POST', `/employees/${id}/education`, { invalidate: [`/employees/${id}/education`], success: 'Added', onSuccess: () => { setOpen(false); reset() } })
  const del = useSend<string>('DELETE', (eid) => `/employees/${id}/education/${eid}`, { invalidate: [`/employees/${id}/education`], success: 'Removed' })
  return (
    <>
      {canEdit && <div className="mb-4 flex justify-end"><Dialog open={open} onOpenChange={setOpen}><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add qualification</Button>
        <DialogContent title="Add qualification"><form onSubmit={handleSubmit((v) => add.mutate(Object.fromEntries(Object.entries(v).map(([k, x]) => [k, x || null])) as never))} className="grid gap-3 sm:grid-cols-2">
          <Field id="q-lv" label="Level">{(a) => <Input placeholder="Intermediate, Bachelor..." {...a} {...register('level', { required: true })} />}</Field>
          <Field id="q-dg" label="Degree or certificate">{(a) => <Input {...a} {...register('degree', { required: true })} />}</Field>
          <Field id="q-in" label="Board or university">{(a) => <Input {...a} {...register('institute')} />}</Field>
          <Field id="q-gr" label="Grade">{(a) => <Input {...a} {...register('grade')} />}</Field>
          <Field id="q-om" label="Obtained marks">{(a) => <Input {...a} {...register('obtained_marks')} />}</Field>
          <Field id="q-tm" label="Total marks">{(a) => <Input {...a} {...register('total_marks')} />}</Field>
          <Field id="q-dv" label="Division">{(a) => <Input {...a} {...register('division')} />}</Field>
          <Field id="q-rm" label="Remarks">{(a) => <Input {...a} {...register('remarks')} />}</Field>
          <div className="flex justify-end gap-2 sm:col-span-2"><DialogClose asChild><Button type="button" variant="outline">Cancel</Button></DialogClose><Button type="submit" loading={add.isPending}>Save</Button></div>
        </form></DialogContent></Dialog></div>}
      {q.isLoading ? <Skeleton className="h-32 w-full" /> : !q.data?.length ? <Card><EmptyState title="No qualifications recorded" /></Card> : (
        <div className="grid gap-4 md:grid-cols-2">{q.data.map((e) => (
          <Card key={e.id}><CardBody>
            <div className="flex items-start justify-between"><div className="flex gap-3"><GraduationCap className="mt-1 h-6 w-6 text-primary" aria-hidden /><div><p className="font-semibold">{e.degree}</p><p className="text-sm text-muted">{e.level}</p></div></div>
              {canEdit && <ConfirmButton label={<Trash2 className="h-4 w-4" />} title="Remove qualification" message={`Remove ${e.degree}?`} onConfirm={() => del.mutate(e.id)} />}</div>
            <dl className="mt-3 border-t border-dashed border-border pt-3"><Row k="Board / University" v={e.institute} /><Row k="Marks" v={e.obtained_marks && `${e.obtained_marks} / ${e.total_marks ?? '?'}`} /><Row k="Grade" v={e.grade} /><Row k="Division" v={e.division} /><Row k="Remarks" v={e.remarks} /></dl>
          </CardBody></Card>))}</div>)}
    </>
  )
}

interface Doc { id: string; title: string; category: string; filename: string; size_bytes: number; expires_on: string | null; created_at: string }
function Documents({ id }: { id: string }) {
  const q = useGet<Doc[]>(`/employees/${id}/documents`)
  const [title, setTitle] = React.useState('')
  const [category, setCategory] = React.useState('other')
  const [expires, setExpires] = React.useState('')
  const [file, setFile] = React.useState<File | null>(null)
  const [busy, setBusy] = React.useState(false)
  const del = useSend<string>('DELETE', (d) => `/documents/${d}`, { invalidate: [`/employees/${id}/documents`], success: 'Document deleted' })
  const upload = async () => {
    const f = new FormData()
    f.append('file', file!); f.append('title', title); f.append('category', category); if (expires) f.append('expires_on', expires)
    setBusy(true)
    try { await uploadFile(`/employees/${id}/documents`, f); toast.success('Uploaded'); setFile(null); setTitle(''); q.refetch() } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <div className="space-y-5">
      <Card><CardHeader><CardTitle>Upload a document</CardTitle></CardHeader><CardBody className="flex flex-wrap items-end gap-3">
        <Field id="d-t" label="Title">{(a) => <Input value={title} onChange={(e) => setTitle(e.target.value)} {...a} />}</Field>
        <Field id="d-c" label="Category">{(a) => <Select value={category} onChange={(e) => setCategory(e.target.value)} {...a}>{['contract', 'offer_letter', 'identification', 'certificate', 'experience_letter', 'other'].map((c) => <option key={c} value={c}>{c.replace('_', ' ')}</option>)}</Select>}</Field>
        <Field id="d-e" label="Expires (optional)">{(a) => <Input type="date" value={expires} onChange={(e) => setExpires(e.target.value)} {...a} />}</Field>
        <Field id="d-f" label="File (PDF, image, Word, Excel; max 10 MB)">{(a) => <Input type="file" className="pt-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} {...a} />}</Field>
        <Button onClick={upload} loading={busy} disabled={!file || title.length < 2}><Upload className="h-4 w-4" />Upload</Button>
      </CardBody></Card>
      <Card>{q.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} /> : !q.data?.length ? <EmptyState title="No documents" /> : (
        <table className="w-full text-left"><thead className="border-b border-border"><tr><Th>Title</Th><Th>Category</Th><Th>Expires</Th><Th>Uploaded</Th><Th /></tr></thead>
          <tbody className="divide-y divide-border">{q.data.map((d) => (
            <tr key={d.id}><Td><p className="font-medium">{d.title}</p><p className="text-xs text-muted">{d.filename} · {(d.size_bytes / 1024).toFixed(0)} KB</p></Td><Td className="capitalize">{d.category.replace('_', ' ')}</Td>
              <Td>{d.expires_on ? formatDate(d.expires_on, { dateStyle: 'medium' }) : '-'}</Td><Td>{formatDate(d.created_at, { dateStyle: 'medium' })}</Td>
              <Td className="space-x-2 text-right"><Button asChild variant="outline" size="sm"><a href={`/api/v1/documents/${d.id}/download`}>Download</a></Button>
                <ConfirmButton label="Delete" title="Delete document" message={`Permanently delete ${d.title}?`} onConfirm={() => del.mutate(d.id)} /></Td></tr>))}</tbody></table>)}</Card>
    </div>
  )
}

interface Rev { id: string; effective_from: string; basic: string; reason: string | null; lines: { name: string; amount: string }[] }
function Salary({ id, canManage, currency }: { id: string; canManage: boolean; currency: string }) {
  const q = useGet<Rev[]>(`/employees/${id}/salary`)
  const comps = useGet<{ id: string; name: string; kind: string }[]>('/payroll/components')
  const [open, setOpen] = React.useState(false)
  const [from, setFrom] = React.useState(new Date().toISOString().slice(0, 10))
  const [basic, setBasic] = React.useState('')
  const [reason, setReason] = React.useState('')
  const [picked, setPicked] = React.useState<Record<string, string>>({})
  const add = useSend<unknown, { warning: string | null }>('POST', `/employees/${id}/salary`, { invalidate: [`/employees/${id}/salary`], success: 'Salary revision saved', onSuccess: (r) => { if (r.warning) toast.warning(r.warning); setOpen(false); setBasic(''); setPicked({}) } })
  return (
    <>
      {canManage && <div className="mb-4 flex justify-end"><Dialog open={open} onOpenChange={setOpen}><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New salary revision</Button>
        <DialogContent title="New salary revision" description="Revisions are never overwritten. The old salary stays on record and applies up to the day before this date.">
          <div className="space-y-3">
            <Field id="s-f" label="Effective from">{(a) => <Input type="date" value={from} onChange={(e) => setFrom(e.target.value)} {...a} />}</Field>
            <Field id="s-b" label={`Basic salary per pay period (${currency})`}>{(a) => <Input inputMode="decimal" value={basic} onChange={(e) => setBasic(e.target.value)} {...a} />}</Field>
            <Field id="s-r" label="Reason">{(a) => <Input value={reason} onChange={(e) => setReason(e.target.value)} {...a} />}</Field>
            {(comps.data ?? []).length > 0 && <fieldset className="space-y-2"><legend className="text-sm font-medium">Allowances and deductions</legend>
              {comps.data!.map((c) => (
                <div key={c.id} className="flex items-center gap-3 text-sm"><label className="flex w-56 cursor-pointer items-center gap-2"><input type="checkbox" checked={c.id in picked} onChange={(e) => setPicked((p) => { const n = { ...p }; if (e.target.checked) n[c.id] = ''; else delete n[c.id]; return n })} />{c.name} <Badge tone={c.kind === 'earning' ? 'success' : 'danger'}>{c.kind}</Badge></label>
                  {c.id in picked && <Input className="h-8 w-32" placeholder="Default" aria-label={`${c.name} amount override`} value={picked[c.id]} onChange={(e) => setPicked((p) => ({ ...p, [c.id]: e.target.value }))} />}</div>))}</fieldset>}
            <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
              <Button loading={add.isPending} disabled={!basic} onClick={() => add.mutate({ effective_from: from, basic, reason: reason || null, lines: Object.entries(picked).map(([component_id, amount]) => ({ component_id, amount: amount || null })) })}>Save revision</Button></div>
          </div></DialogContent></Dialog></div>}
      <Card>{q.isLoading ? <CardBody><Skeleton className="h-16 w-full" /></CardBody> : q.isError ? <ErrorState message={errorMessage(q.error)} /> : !q.data?.length ? <EmptyState title="No salary on file" description="Payroll skips employees without a salary revision." /> : (
        <ul className="divide-y divide-border">{q.data.map((r, i) => (
          <li key={r.id} className="px-5 py-4 text-sm"><div className="flex items-center justify-between"><span className="font-semibold">{money(r.basic, currency)}</span><span className="text-muted">from {formatDate(r.effective_from, { dateStyle: 'medium' })} {i === 0 && <Badge tone="success" className="ml-2">current</Badge>}</span></div>
            {r.reason && <p className="text-muted">{r.reason}</p>}{r.lines.length > 0 && <p className="mt-1 text-muted">{r.lines.map((l) => `${l.name} ${money(l.amount)}`).join(' · ')}</p>}</li>))}</ul>)}</Card>
    </>
  )
}

interface Item { id: string; title: string; done: boolean }
function Checklist({ id }: { id: string }) {
  const q = useGet<Item[]>(`/employees/${id}/checklist`)
  const { data: me } = useMe()
  const [title, setTitle] = React.useState('')
  const toggle = useSend<{ id: string; done: boolean }>('PATCH', (b) => `/employees/${id}/checklist/${b.id}`, { invalidate: [`/employees/${id}/checklist`, '/checklists'] })
  const add = useSend<{ title: string }>('POST', `/employees/${id}/checklist`, { invalidate: [`/employees/${id}/checklist`, '/checklists'], onSuccess: () => setTitle('') })
  const sequence = ['Collect identification documents', 'Sign employment contract', 'Create work email account', 'Assign equipment', 'Orientation session', 'Add to payroll']
  const items = [...(q.data ?? [])].sort((a, b) => (sequence.indexOf(a.title) < 0 ? 99 : sequence.indexOf(a.title)) - (sequence.indexOf(b.title) < 0 ? 99 : sequence.indexOf(b.title)))
  const completed = items.filter(item => item.done).length
  const next = items.find(item => !item.done)
  const destination = (item: Item) => {
    const title = item.title.toLowerCase()
    if (title.includes('document') || title.includes('contract')) return { to: `/employees/${id}?tab=documents`, label: 'Open documents' }
    if (title.includes('equipment') || title.includes('asset')) return me?.permissions.includes('assets.manage') ? { to: `/assets?employee_id=${id}`, label: 'Assign an asset' } : null
    if (title.includes('orientation') || title.includes('training')) return me?.permissions.includes('training.manage') ? { to: '/training', label: 'Open training' } : null
    if (title.includes('payroll') || title.includes('salary')) return me?.permissions.includes('salary.read') ? { to: `/employees/${id}?tab=salary`, label: 'Open salary' } : null
    if (title.includes('email') || title.includes('access')) return { to: `/employees/${id}?tab=overview`, label: 'Open profile access' }
    return null
  }
  return (
    <Card className="max-w-3xl"><CardHeader><div><CardTitle>Onboarding checklist</CardTitle><p className="mt-1 text-xs text-muted">Follow the steps from the hire through the employee’s first working days.</p></div><Badge tone={completed === items.length && items.length > 0 ? 'success' : 'primary'}>{completed} of {items.length} complete</Badge></CardHeader>
      {q.isLoading ? <CardBody><Skeleton className="h-24 w-full" /></CardBody> : <><CardBody className="border-b border-border"><div className="h-2 overflow-hidden rounded-full bg-surface-2" role="progressbar" aria-label="Onboarding progress" aria-valuenow={completed} aria-valuemax={items.length}><div className="h-full rounded-full bg-success transition-all" style={{ width: items.length ? `${completed / items.length * 100}%` : '0%' }} /></div>{next ? <div className="mt-4 flex flex-wrap items-center justify-between gap-3 rounded-lg bg-primary-soft p-3"><div><p className="text-xs font-semibold uppercase tracking-wide text-primary">Next step</p><p className="mt-1 text-sm font-semibold">{next.title}</p></div>{destination(next) && <Button asChild size="sm" variant="outline"><Link to={destination(next)!.to}>{destination(next)!.label}</Link></Button>}</div> : items.length ? <p className="mt-3 text-sm font-medium text-success">Onboarding complete. The employee’s records remain available in the profile.</p> : <p className="mt-3 text-sm text-muted">Add the first onboarding step below.</p>}</CardBody><ul className="divide-y divide-border">{items.map((c) => {
        const action = destination(c)
        return <li key={c.id} className="flex flex-wrap items-center justify-between gap-2 px-5 py-3"><label className="flex min-w-0 cursor-pointer items-center gap-3 text-sm"><input type="checkbox" checked={c.done} onChange={(e) => toggle.mutate({ id: c.id, done: e.target.checked })} /><span className={c.done ? 'text-muted line-through' : ''}>{c.title}</span></label>{action && <Link to={action.to} className="text-xs font-semibold text-primary hover:underline">{action.label}</Link>}</li>
      })}</ul></>}
      <CardBody className="flex gap-2 border-t border-border"><Input placeholder="Add a step" aria-label="New checklist step" value={title} onChange={(e) => setTitle(e.target.value)} /><Button disabled={title.trim().length < 2} loading={add.isPending} onClick={() => add.mutate({ title: title.trim() })}>Add</Button></CardBody>
    </Card>
  )
}

function PortalAccess({ emp }: { emp: Detail }) {
  const [open, setOpen] = React.useState(false)
  const [role, setRole] = React.useState('employee')
  const roles = useGet<{ key: string; name: string }[]>('/roles', undefined, open)
  const m = useSend<{ role_key: string }, { message: string }>('POST', `/employees/${emp.id}/invite`, { onSuccess: (r) => { toast.success(r.message); setOpen(false) } })
  if (emp.has_login) return <Badge tone="success">Has portal login</Badge>
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="outline" onClick={() => setOpen(true)}>Invite to portal</Button>
      <DialogContent title={`Invite ${emp.full_name}`} description={emp.email ? `An email goes to ${emp.email} with a link to set a password. The login is linked to this employee record.` : 'Add a work email to this employee first.'}>
        <Field id="pi-r" label="Access level" hint="Employee gives access to their own space only. You can only grant roles whose permissions you hold.">{(a) => (
          <Select value={role} onChange={(e) => setRole(e.target.value)} {...a}>{(roles.data ?? [{ key: 'employee', name: 'Employee' }]).filter((r) => r.key !== 'owner').map((r) => <option key={r.key} value={r.key}>{r.name}</option>)}</Select>)}</Field>
        <div className="mt-6 flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={!emp.email} onClick={() => m.mutate({ role_key: role })}>Send invitation</Button></div>
      </DialogContent>
    </Dialog>
  )
}

export function EmployeeDetailPage({ own = false }: { own?: boolean }) {
  const params = useParams()
  const [sp, setSp] = useSearchParams()
  const { data: me } = useMe()
  const mine = useGet<Detail>('/me/employee')
  const other = useGet<Detail>(`/employees/${params.id}`, undefined, !own)
  const q = own ? mine : other
  const perms = new Set(me?.permissions ?? [])
  const e = q.data
  const isSelf = own || (!!e && e.id === mine.data?.id)
  type TabId = 'overview' | 'history' | 'education' | 'documents' | 'salary' | 'checklist'
  const requestedTab = (sp.get('tab') as TabId) || 'overview'
  if (q.isLoading) return <Skeleton className="h-64 w-full" />
  if (q.isError || !e) return <Card><ErrorState message={errorMessage(q.error)} /></Card>
  const manage = perms.has('employees.manage')
  const tabs: { id: TabId; label: string }[] = [{ id: 'overview', label: 'Overview' }, { id: 'history', label: 'History' }, { id: 'education', label: 'Education' }]
  if (manage || own) tabs.push({ id: 'documents', label: 'Documents' })
  if (!own && perms.has('salary.read')) tabs.push({ id: 'salary', label: 'Salary' })
  if (manage) tabs.push({ id: 'checklist', label: 'Checklist' })
  const tab = tabs.some(t => t.id === requestedTab) ? requestedTab : 'overview'
  return (
    <>
      <PageHeader title={e.full_name} description={`${e.designation ?? 'No designation'} · ${e.employee_code}`}
        actions={<><StatusText status={e.status} />{own && <EditMyProfile emp={e} />}{manage && !own && perms.has('members.manage') && <PortalAccess emp={e} />}{manage && !own && <><LifecycleDialog emp={e} /><EditDialog emp={e} /></>}</>} />
      <div className="mb-5 flex items-center gap-4"><Avatar name={e.full_name} size="xl" />
        <p className="text-sm text-muted">{[e.department, e.branch].filter(Boolean).join(' · ') || 'No placement yet'}</p></div>
      <Tabs tabs={tabs} value={tab} onChange={(t) => setSp({ tab: t })} />
      {tab === 'overview' && <Overview e={e} />}{tab === 'history' && <History id={e.id} />}
      {tab === 'education' && <Education id={e.id} canEdit={manage || isSelf || own} />}{tab === 'documents' && <Documents id={e.id} />}
      {tab === 'salary' && <Salary id={e.id} canManage={perms.has('salary.manage')} currency={me?.active_organization?.currency ?? ''} />}{tab === 'checklist' && <Checklist id={e.id} />}
    </>
  )
}
