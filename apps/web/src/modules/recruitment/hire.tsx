import { Download, ExternalLink, Plus } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent } from '@/components/ui/dialog'
import { StatusText, Tabs, downloadCsv } from '@/components/ui/extras'
import { Field, Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { today, uploadFile, useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { formatDate } from '@/lib/utils'
import { Opts, useOrgLists } from '@/modules/people/employees'

interface Job { id: string; title: string; status: string; openings: number; applicants: number; description: string | null; branch_id: string | null; department_id: string | null; designation_id: string | null }
interface App { id: string; job_id: string; full_name: string | null; email: string | null; phone: string | null; has_resume: boolean; stage: string; cover_note: string | null; employee_id: string | null; source: string | null; created_at: string }
interface Interview { id: string; scheduled_at: string; interviewer: string; rating: number | null; notes: string | null }
interface CareerSettings { headline: string; introduction: string; accent_color: string; cover_url: string | null; logo_url: string | null }

function CareerSettingsDialog() {
  const [open, setOpen] = React.useState(false)
  const q = useGet<CareerSettings>('/recruitment/career-settings')
  const [form, setForm] = React.useState<CareerSettings>({ headline: 'Build your future with us', introduction: 'Explore our open roles and find your next opportunity.', accent_color: '#2563eb', cover_url: null, logo_url: null })
  React.useEffect(() => { if (open && q.data) setForm(q.data) }, [open, q.data])
  const save = useSend<CareerSettings>('PUT', '/recruitment/career-settings', { invalidate: ['/recruitment/career-settings'], success: 'Careers page saved', onSuccess: () => setOpen(false) })
  return <Dialog open={open} onOpenChange={setOpen}>
    <Button variant="outline" onClick={() => setOpen(true)}>Career page settings</Button>
    <DialogContent className="max-w-2xl" title="Design your career page" description="These settings appear on your public vacancy page.">
      <div className="grid gap-4 sm:grid-cols-2"><div className="space-y-3"><Field id="career-headline" label="Headline">{a => <Input {...a} maxLength={120} value={form.headline} onChange={e => setForm({ ...form, headline: e.target.value })} />}</Field><Field id="career-intro" label="Introduction">{a => <textarea {...a} rows={3} maxLength={600} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={form.introduction} onChange={e => setForm({ ...form, introduction: e.target.value })} />}</Field><Field id="career-accent" label="Accent color">{a => <Input {...a} type="color" className="h-10 w-20 p-1" value={form.accent_color} onChange={e => setForm({ ...form, accent_color: e.target.value })} />}</Field><Field id="career-cover" label="Cover image URL (optional)">{a => <Input {...a} type="url" placeholder="https://..." value={form.cover_url ?? ''} onChange={e => setForm({ ...form, cover_url: e.target.value || null })} />}</Field><Field id="career-logo" label="Logo image URL (optional)">{a => <Input {...a} type="url" placeholder="https://..." value={form.logo_url ?? ''} onChange={e => setForm({ ...form, logo_url: e.target.value || null })} />}</Field></div><div><p className="mb-2 text-xs font-semibold uppercase tracking-wider text-muted">Live preview</p><div className="overflow-hidden rounded-xl border border-border"><div className="flex h-12 items-center gap-2 bg-white px-4">{form.logo_url && <img src={form.logo_url} alt="" className="h-7 max-w-20 object-contain" />}<span className="text-xs font-semibold">Your organization · Careers</span></div><div className="flex min-h-44 flex-col justify-end bg-[#10233f] bg-cover bg-center p-5 text-white" style={form.cover_url ? { backgroundImage: `linear-gradient(0deg, rgba(6,18,38,.85), rgba(6,18,38,.35)), url(${JSON.stringify(form.cover_url)})` } : undefined}><h3 className="font-display text-xl font-bold">{form.headline || 'Your headline'}</h3><p className="mt-2 text-xs text-white/80">{form.introduction}</p></div><div className="p-4"><span className="inline-flex rounded-md px-3 py-1.5 text-xs font-semibold text-white" style={{ backgroundColor: form.accent_color }}>Explore open roles</span></div></div></div></div>
      <div className="mt-5 flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={save.isPending} disabled={form.headline.trim().length < 3} onClick={() => save.mutate({ ...form, headline: form.headline.trim(), introduction: form.introduction.trim() })}>Save career page</Button></div>
    </DialogContent>
  </Dialog>
}

function JobDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const { branches, departments, designations } = useOrgLists()
  const [f, setF] = React.useState({ title: '', description: '', department_id: '', branch_id: '', designation_id: '', employment_type: 'full_time', openings: 1 })
  const m = useSend<Record<string, unknown>>('POST', '/recruitment/jobs', { invalidate: ['/recruitment'], success: 'Job created as a draft', onSuccess: () => { onOpenChange(false); setF({ ...f, title: '', description: '' }) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New job">
        <div className="space-y-3">
          <Field id="j-t" label="Title">{(a) => <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} {...a} />}</Field>
          <div className="grid grid-cols-2 gap-3"><Field id="j-d" label="Department">{(a) => <Select value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value, designation_id: '' })} {...a}><Opts list={departments} /></Select>}</Field><Field id="j-b" label="Branch">{a => <Select {...a} value={f.branch_id} onChange={e => setF({ ...f, branch_id: e.target.value })}><Opts list={branches} /></Select>}</Field><Field id="j-role" label="Designation">{a => <Select {...a} value={f.designation_id} onChange={e => setF({ ...f, designation_id: e.target.value })}><Opts list={designations.filter(d => !f.department_id || !d.department_id || d.department_id === f.department_id)} /></Select>}</Field><Field id="j-type" label="Employment type">{a => <Select {...a} value={f.employment_type} onChange={e => setF({ ...f, employment_type: e.target.value })}><option value="full_time">Full time</option><option value="part_time">Part time</option><option value="contract">Contract</option><option value="intern">Internship</option></Select>}</Field><Field id="j-o" label="Openings">{(a) => <Input type="number" min={1} max={500} value={f.openings} onChange={(e) => setF({ ...f, openings: Number(e.target.value) })} {...a} />}</Field></div>
          <Field id="j-ds" label="Description">{(a) => <textarea rows={5} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} {...a} />}</Field>
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button loading={m.isPending} disabled={f.title.trim().length < 3 || f.openings < 1} onClick={() => m.mutate({ title: f.title.trim(), description: f.description || null, department_id: f.department_id || null, branch_id: f.branch_id || null, designation_id: f.designation_id || null, employment_type: f.employment_type, openings: f.openings })}>Create job</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function CandidateDialog({ jobId }: { jobId: string }) {
  const [open, setOpen] = React.useState(false)
  const [f, setF] = React.useState({ full_name: '', email: '', phone: '', cover_note: '' })
  const m = useSend<Record<string, unknown>>('POST', '/recruitment/applications', { invalidate: ['/recruitment'], success: 'Candidate added', onSuccess: () => { setOpen(false); setF({ full_name: '', email: '', phone: '', cover_note: '' }) } })
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant="outline" onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Add candidate</Button>
      <DialogContent title="Add a candidate">
        <div className="space-y-3">
          <Field id="c-n" label="Full name">{(a) => <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} {...a} />}</Field>
          <Field id="c-e" label="Email">{(a) => <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} {...a} />}</Field>
          <Field id="c-p" label="Phone">{(a) => <Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} {...a} />}</Field>
          <Field id="c-note" label="Cover note (optional)">{a => <textarea {...a} rows={3} className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={f.cover_note} onChange={e => setF({ ...f, cover_note: e.target.value })} />}</Field>
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
            <Button loading={m.isPending} disabled={f.full_name.length < 2 || !f.email} onClick={() => m.mutate({ job_id: jobId, full_name: f.full_name, email: f.email, phone: f.phone || null, cover_note: f.cover_note || null })}>Add</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function InterviewDialog({ app, canManage, onClose }: { app: App | null; canManage: boolean; onClose: () => void }) {
  const q = useGet<Interview[]>(`/recruitment/applications/${app?.id}/interviews`, undefined, !!app)
  const [f, setF] = React.useState({ scheduled_at: '', interviewer: '', rating: '', notes: '' })
  const m = useSend<Record<string, unknown>>('POST', `/recruitment/applications/${app?.id}/interviews`, { invalidate: [`/recruitment/applications/${app?.id}`], success: 'Interview recorded', onSuccess: () => setF({ scheduled_at: '', interviewer: '', rating: '', notes: '' }) })
  return (
    <Dialog open={!!app} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" title={`Interviews: ${app?.full_name ?? ''}`}>
        <ul className="mb-4 divide-y divide-border rounded-lg border border-border text-sm">
          {!q.data?.length && <li className="px-3 py-3 text-muted">No interviews yet.</li>}
          {q.data?.map((i) => <li key={i.id} className="px-3 py-2"><p className="font-medium">{formatDate(i.scheduled_at)} with {i.interviewer} {i.rating && <Badge tone="primary">{i.rating}/5</Badge>}</p>{i.notes && <p className="text-muted">{i.notes}</p>}</li>)}</ul>
        {canManage && <div className="grid gap-3 sm:grid-cols-2">
          <Field id="i-d" label="Date and time">{(a) => <Input type="datetime-local" value={f.scheduled_at} onChange={(e) => setF({ ...f, scheduled_at: e.target.value })} {...a} />}</Field>
          <Field id="i-i" label="Interviewer">{(a) => <Input value={f.interviewer} onChange={(e) => setF({ ...f, interviewer: e.target.value })} {...a} />}</Field>
          <Field id="i-r" label="Score (1 to 5)">{(a) => <Select value={f.rating} onChange={(e) => setF({ ...f, rating: e.target.value })} {...a}><option value="">Not scored</option>{[1, 2, 3, 4, 5].map((n) => <option key={n}>{n}</option>)}</Select>}</Field>
          <Field id="i-n" label="Notes">{(a) => <Input value={f.notes} onChange={(e) => setF({ ...f, notes: e.target.value })} {...a} />}</Field>
          <div className="sm:col-span-2"><Button loading={m.isPending} disabled={!f.scheduled_at || f.interviewer.length < 2} onClick={() => m.mutate({ scheduled_at: new Date(f.scheduled_at).toISOString(), interviewer: f.interviewer, rating: f.rating ? Number(f.rating) : null, notes: f.notes || null })}>Save interview</Button></div>
        </div>}
      </DialogContent>
    </Dialog>
  )
}

function CandidateDetailDialog({ app, job, canHire, onClose, onInterview, onHire }: { app: App | null; job?: Job; canHire: boolean; onClose: () => void; onInterview: () => void; onHire: () => void }) {
  return <Dialog open={!!app} onOpenChange={open => !open && onClose()}><DialogContent title={app?.full_name ?? 'Candidate'} description={job ? `Applied for ${job.title}` : undefined}>
    {app && <div className="space-y-4"><div className="flex flex-wrap items-center gap-2"><StatusText status={app.stage} /><span className="text-xs text-muted">Applied {formatDate(app.created_at, { dateStyle: 'medium' })}</span></div><dl className="grid gap-3 rounded-lg bg-surface-2 p-4 text-sm sm:grid-cols-2"><div><dt className="text-xs text-muted">Email</dt><dd className="font-medium">{app.email ?? '—'}</dd></div><div><dt className="text-xs text-muted">Phone</dt><dd className="font-medium">{app.phone ?? '—'}</dd></div><div><dt className="text-xs text-muted">Source</dt><dd className="font-medium capitalize">{app.source?.replaceAll('_', ' ') ?? '—'}</dd></div><div><dt className="text-xs text-muted">Vacancy</dt><dd className="font-medium">{job?.title ?? 'Unknown'}</dd></div></dl>{app.cover_note && <div><h3 className="text-sm font-semibold">Cover note</h3><p className="mt-1 whitespace-pre-wrap text-sm text-muted">{app.cover_note}</p></div>}<div className="flex flex-wrap gap-2 border-t border-border pt-4">{app.has_resume && <Button asChild variant="outline" size="sm"><a href={`/api/v1/recruitment/applications/${app.id}/resume`}><Download className="h-4 w-4" />Download CV</a></Button>}<Button variant="outline" size="sm" onClick={onInterview}>Interviews</Button>{app.employee_id ? <Button asChild size="sm"><Link to={`/employees/${app.employee_id}?tab=checklist`}>Open onboarding</Link></Button> : canHire && app.stage !== 'Rejected' && <Button size="sm" onClick={onHire}>Hire candidate</Button>}</div></div>}
  </DialogContent></Dialog>
}

function HireDialog({ app, job, onClose }: { app: App | null; job?: Job; onClose: () => void }) {
  const navigate = useNavigate()
  const { branches, departments, designations } = useOrgLists()
  const managers = useGet<{ items: { id: string; full_name: string }[] }>('/employees', { status: 'active', page_size: 100 }, !!app)
  const [date, setDate] = React.useState(today())
  const [placement, setPlacement] = React.useState({ branch_id: '', department_id: '', designation_id: '', manager_id: '' })
  React.useEffect(() => { if (app) setPlacement({ branch_id: job?.branch_id ?? '', department_id: job?.department_id ?? '', designation_id: job?.designation_id ?? '', manager_id: '' }) }, [app?.id, job?.id])
  const m = useSend<{ joining_date: string; branch_id: string | null; department_id: string | null; designation_id: string | null; manager_id: string | null }, { employee_id: string; employee_code: string }>('POST', `/recruitment/applications/${app?.id}/hire`, { invalidate: ['/recruitment', '/employees', '/checklists', '/dashboard'], onSuccess: (r) => { toast.success(`Employee ${r.employee_code} created. Complete the onboarding checklist.`); onClose(); navigate(`/employees/${r.employee_id}?tab=checklist`) } })
  return (
    <Dialog open={!!app} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Hire ${app?.full_name ?? ''}`} description="Create the employee record, assign its reporting line, and start onboarding.">
        <div className="space-y-3">
          <Field id="h-d" label="Joining date">{(a) => <Input type="date" value={date} onChange={(e) => setDate(e.target.value)} {...a} />}</Field>
          <div className="grid gap-3 sm:grid-cols-2"><Field id="h-branch" label="Branch">{a => <Select {...a} value={placement.branch_id} onChange={e => setPlacement({ ...placement, branch_id: e.target.value })}><Opts list={branches} /></Select>}</Field><Field id="h-dept" label="Department">{a => <Select {...a} value={placement.department_id} onChange={e => setPlacement({ ...placement, department_id: e.target.value, designation_id: '' })}><Opts list={departments} /></Select>}</Field><Field id="h-desig" label="Designation">{a => <Select {...a} value={placement.designation_id} onChange={e => setPlacement({ ...placement, designation_id: e.target.value })}><Opts list={designations.filter(d => !placement.department_id || !d.department_id || d.department_id === placement.department_id)} /></Select>}</Field><Field id="h-manager" label="Reporting manager">{a => <Select {...a} value={placement.manager_id} onChange={e => setPlacement({ ...placement, manager_id: e.target.value })}><Opts list={(managers.data?.items ?? []).map(p => ({ id: p.id, name: p.full_name }))} /></Select>}</Field></div>
          <p className="rounded-lg bg-primary-soft p-3 text-xs text-muted">Next: collect documents, assign equipment, set up access, and finish the onboarding checklist in the employee profile.</p>
          <div className="flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate({ joining_date: date, branch_id: placement.branch_id || null, department_id: placement.department_id || null, designation_id: placement.designation_id || null, manager_id: placement.manager_id || null })}>Create employee</Button></div>
        </div>
      </DialogContent>
    </Dialog>
  )
}

function PipelineDialog({ stages }: { stages: string[] }) {
  const [open, setOpen] = React.useState(false)
  const [text, setText] = React.useState(stages.join('\n'))
  const m = useSend<{ stages: string[] }>('PUT', '/recruitment/pipeline', { invalidate: ['/recruitment'], success: 'Pipeline updated', onSuccess: () => setOpen(false) })
  return (
    <Dialog open={open} onOpenChange={(o) => { setOpen(o); if (o) setText(stages.join('\n')) }}>
      <Button variant="outline" onClick={() => setOpen(true)}>Edit stages</Button>
      <DialogContent title="Hiring pipeline" description="One stage per line, in order. Applied, Hired and Rejected must stay. A stage with candidates in it cannot be removed.">
        <textarea rows={8} aria-label="Stages" className="w-full rounded-lg border border-border bg-surface px-3 py-2 text-sm" value={text} onChange={(e) => setText(e.target.value)} />
        <div className="mt-3 flex justify-end gap-2"><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} onClick={() => m.mutate({ stages: text.split('\n').map((s) => s.trim()).filter(Boolean) })}>Save</Button></div>
      </DialogContent>
    </Dialog>
  )
}

export function HirePage() {
  const { data: me } = useMe()
  const manage = me?.permissions.includes('recruitment.manage')
  const jobs = useGet<Job[]>('/recruitment/jobs')
  const stages = useGet<{ stages: string[] }>('/recruitment/pipeline')
  const [jobId, setJobId] = React.useState('')
  const [view, setView] = React.useState<'vacancies' | 'talent' | 'reports'>('vacancies')
  const [search, setSearch] = React.useState('')
  const [reportStage, setReportStage] = React.useState('')
  const [reportJob, setReportJob] = React.useState('')
  const [newJob, setNewJob] = React.useState(false)
  const [interview, setInterview] = React.useState<App | null>(null)
  const [hire, setHire] = React.useState<App | null>(null)
  const [candidate, setCandidate] = React.useState<App | null>(null)
  const job = jobs.data?.find((j) => j.id === jobId) ?? jobs.data?.[0]
  const apps = useGet<App[]>('/recruitment/applications', { job_id: job?.id }, !!job)
  const allApps = useGet<App[]>('/recruitment/applications', undefined, view !== 'vacancies')
  const move = useSend<{ id: string; stage: string }>('POST', (b) => `/recruitment/applications/${b.id}/stage`, { invalidate: ['/recruitment'] })
  const status = useSend<{ stage: string }>('POST', `/recruitment/jobs/${job?.id}/status`, { invalidate: ['/recruitment'], success: 'Job updated' })
  const cols = stages.data?.stages ?? []
  const reportApps = (allApps.data ?? []).filter(a => `${a.full_name} ${a.email}`.toLowerCase().includes(search.toLowerCase()) && (view !== 'reports' || ((!reportStage || a.stage === reportStage) && (!reportJob || a.job_id === reportJob))))
  const careers = `${window.location.origin}/careers/${me?.active_organization?.slug}`

  return (
    <>
      <PageHeader title="Hire" description="Vacancies, applicants and hiring reports in one place." actions={manage ? <><CareerSettingsDialog /><Button onClick={() => setNewJob(true)}><Plus className="h-4 w-4" />New job</Button></> : undefined} />
      <Tabs tabs={[{ id: 'vacancies', label: 'Vacancies and pipeline' }, { id: 'talent', label: 'Talent pool' }, { id: 'reports', label: 'Reports' }]} value={view} onChange={setView} />
      {view === 'reports' && <div className="mb-5 grid gap-3 sm:grid-cols-2 lg:grid-cols-4">{cols.map(stage => <Card key={stage}><CardBody className="py-4"><p className="text-xs font-medium text-muted">{stage}</p><p className="mt-1 font-display text-2xl font-bold">{(allApps.data ?? []).filter(a => a.stage === stage).length}</p></CardBody></Card>)}</div>}
      {view !== 'vacancies' && <Card className="mb-5"><CardBody className="flex flex-wrap items-center gap-3"><Input aria-label="Search candidates" placeholder="Search candidates" className="max-w-xs" value={search} onChange={e => setSearch(e.target.value)} />{view === 'reports' && <><Select aria-label="Report stage" className="w-40" value={reportStage} onChange={e => setReportStage(e.target.value)}><option value="">All stages</option>{cols.map(c => <option key={c} value={c}>{c}</option>)}</Select><Select aria-label="Report vacancy" className="w-52" value={reportJob} onChange={e => setReportJob(e.target.value)}><option value="">All vacancies</option>{jobs.data?.map(j => <option key={j.id} value={j.id}>{j.title}</option>)}</Select></>}<span className="text-sm text-muted">{reportApps.length} candidates</span><Button variant="outline" className="ml-auto" disabled={!reportApps.length} onClick={() => downloadCsv('recruitment-report.csv', [['Candidate', 'Email', 'Phone', 'Vacancy', 'Stage', 'Source'], ...reportApps.map(a => [a.full_name, a.email, a.phone, jobs.data?.find(j => j.id === a.job_id)?.title, a.stage, a.source])])}><Download className="h-4 w-4" />Export CSV</Button></CardBody></Card>}
      {view !== 'vacancies' && <Card className="mb-5"><div className="overflow-x-auto"><table className="w-full text-left text-sm"><thead className="bg-surface-2 text-xs uppercase text-muted"><tr>{['Candidate', 'Vacancy', 'Stage', 'Email', 'Action'].map(h => <th key={h} className="px-4 py-3">{h}</th>)}</tr></thead><tbody className="divide-y divide-border">{reportApps.map(a => <tr key={a.id}><td className="px-4 py-3 font-medium">{a.full_name}</td><td className="px-4 py-3">{jobs.data?.find(j => j.id === a.job_id)?.title ?? 'Unknown'}</td><td className="px-4 py-3"><StatusText status={a.stage} /></td><td className="px-4 py-3">{a.email}</td><td className="px-4 py-3"><Button size="sm" variant="outline" onClick={() => setCandidate(a)}>View candidate</Button></td></tr>)}</tbody></table></div></Card>}
      {view === 'vacancies' && <>
      {jobs.isLoading ? <Skeleton className="h-40 w-full" /> : jobs.isError ? <ErrorState message={errorMessage(jobs.error)} onRetry={() => jobs.refetch()} /> : !jobs.data?.length ? <Card><EmptyState title="No jobs yet" description="Create a job, open it, and share your careers page." /></Card> : (
        <>
          <Card className="mb-5"><CardBody className="flex flex-wrap items-center gap-3">
            <Select aria-label="Job" className="w-72" value={job?.id ?? ''} onChange={(e) => setJobId(e.target.value)}>{jobs.data.map((j) => <option key={j.id} value={j.id}>{j.title} ({j.applicants})</option>)}</Select>
            {job && <StatusText status={job.status} />}
            {manage && job && job.status !== 'open' && <Button size="sm" onClick={() => status.mutate({ stage: 'open' })}>Open job</Button>}
            {manage && job && job.status === 'open' && <Button size="sm" variant="outline" onClick={() => status.mutate({ stage: 'closed' })}>Close job</Button>}
            <div className="ml-auto flex flex-wrap items-center gap-2">
              <Button asChild variant="ghost" size="sm"><a href={careers} target="_blank" rel="noreferrer"><ExternalLink className="h-4 w-4" />Careers page</a></Button>
              {manage && job && <CandidateDialog jobId={job.id} />}{manage && <PipelineDialog stages={cols} />}
            </div>
          </CardBody></Card>
          {apps.isLoading ? <Skeleton className="h-64 w-full" /> : (
            <div className="flex gap-4 overflow-x-auto pb-3">{cols.map((stage) => {
              const items = (apps.data ?? []).filter((a) => a.stage === stage)
              return (
                <section key={stage} aria-label={stage} className="w-72 shrink-0 rounded-2xl bg-surface-2 p-3">
                  <h2 className="mb-3 flex items-center justify-between px-2 text-sm font-semibold">{stage}<Badge>{items.length}</Badge></h2>
                  <div className="space-y-3">{items.map((a) => (
                    <Card key={a.id}><CardBody className="space-y-2 p-4">
                      <div><button className="text-left font-medium hover:text-primary hover:underline" onClick={() => setCandidate(a)}>{a.full_name}</button><p className="text-xs text-muted">{a.email}</p></div>
                      {a.employee_id ? <Button asChild size="sm" variant="soft"><Link to={`/employees/${a.employee_id}?tab=checklist`}>Open onboarding</Link></Button> : manage && (
                        <Select aria-label={`Move ${a.full_name}`} className="h-8 text-xs" value={a.stage} onChange={(e) => move.mutate({ id: a.id, stage: e.target.value })}>{cols.filter((c) => c !== 'Hired').map((c) => <option key={c}>{c}</option>)}</Select>)}
                      <div className="flex flex-wrap gap-1.5">
                        <Button size="sm" variant="outline" onClick={() => setInterview(a)}>Interviews</Button>
                        {a.has_resume && <Button asChild size="sm" variant="ghost"><a href={`/api/v1/recruitment/applications/${a.id}/resume`}><Download className="h-3.5 w-3.5" />CV</a></Button>}
                        {manage && !a.employee_id && me?.permissions.includes('employees.manage') && a.stage !== 'Rejected' && <Button size="sm" onClick={() => setHire(a)}>Hire</Button>}
                      </div>
                    </CardBody></Card>))}</div>
                </section>)
            })}</div>)}
        </>)}
      </>}
      <JobDialog open={newJob} onOpenChange={setNewJob} /><CandidateDetailDialog app={candidate} job={jobs.data?.find(j => j.id === candidate?.job_id)} canHire={!!manage && !!me?.permissions.includes('employees.manage')} onClose={() => setCandidate(null)} onInterview={() => { setInterview(candidate); setCandidate(null) }} onHire={() => { setHire(candidate); setCandidate(null) }} /><InterviewDialog app={interview} canManage={!!manage} onClose={() => setInterview(null)} /><HireDialog app={hire} job={jobs.data?.find(j => j.id === hire?.job_id)} onClose={() => setHire(null)} />
    </>
  )
}

export function CareersPage() {
  const { slug } = useParams()
  const q = useGet<{ organization: string; settings: CareerSettings; jobs: { id: string; title: string; description: string | null; employment_type: string }[] }>(`/public/careers/${slug}`)
  const [applyTo, setApplyTo] = React.useState<string | null>(null)
  const [f, setF] = React.useState({ full_name: '', email: '', phone: '', cover_note: '' })
  const [file, setFile] = React.useState<File | null>(null)
  const [busy, setBusy] = React.useState(false)
  const [done, setDone] = React.useState(false)
  const submit = async () => {
    const form = new FormData()
    Object.entries(f).forEach(([k, v]) => v && form.append(k, v))
    if (file) form.append('resume', file)
    setBusy(true)
    try { await uploadFile(`/public/careers/${slug}/jobs/${applyTo}/apply`, form); setDone(true) } catch (e) { toast.error(errorMessage(e)) } finally { setBusy(false) }
  }
  return (
    <div className="min-h-screen bg-[#f5f8fc] text-[#14253d]">
      <header className="border-b border-slate-200 bg-white"><div className="mx-auto flex h-16 max-w-6xl items-center gap-3 px-5">{q.data?.settings.logo_url && <img src={q.data.settings.logo_url} alt="" className="h-9 max-w-28 object-contain" />}<span className="font-display text-lg font-bold">{q.data?.organization ?? 'Careers'}</span><span className="ml-auto text-xs font-semibold uppercase tracking-widest text-slate-400">Careers</span></div></header>
      <section className="bg-[#10233f] bg-cover bg-center text-white" style={q.data?.settings.cover_url ? { backgroundImage: `linear-gradient(90deg, rgba(7,24,49,.95), rgba(7,24,49,.5)), url(${JSON.stringify(q.data.settings.cover_url)})` } : undefined}><div className="mx-auto max-w-6xl px-5 py-16 sm:py-24"><span className="rounded-full border border-white/25 px-3 py-1 text-xs font-semibold">Join our team</span><h1 className="mt-5 max-w-2xl font-display text-4xl font-extrabold tracking-tight sm:text-5xl">{q.data?.settings.headline ?? 'Build your future with us'}</h1><p className="mt-4 max-w-xl text-sm leading-7 text-slate-200 sm:text-base">{q.data?.settings.introduction ?? 'Explore our open roles and find your next opportunity.'}</p><a href="#open-roles" className="mt-7 inline-flex rounded-lg px-5 py-3 text-sm font-semibold text-white" style={{ backgroundColor: q.data?.settings.accent_color ?? '#2563eb' }}>Explore open roles</a></div></section>
      <main id="open-roles" className="mx-auto max-w-6xl px-5 py-12"><div className="mb-6"><p className="text-xs font-semibold uppercase tracking-widest text-blue-600">Opportunities</p><h2 className="mt-1 font-display text-2xl font-bold">{applyTo ? 'Apply for this role' : 'Open roles'}</h2></div>
      {q.isLoading ? <Skeleton className="h-32 w-full" /> : q.isError ? <ErrorState message="This careers page is not available." /> : done ? <p role="status" className="rounded-lg bg-emerald-50 p-5 text-sm font-medium text-emerald-800">Thank you. Your application has been received.</p> : applyTo ? (
        <div className="max-w-2xl space-y-3 rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
          <Field id="a-n" label="Full name">{(a) => <Input value={f.full_name} onChange={(e) => setF({ ...f, full_name: e.target.value })} {...a} />}</Field>
          <Field id="a-e" label="Email">{(a) => <Input type="email" value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} {...a} />}</Field>
          <Field id="a-p" label="Phone">{(a) => <Input value={f.phone} onChange={(e) => setF({ ...f, phone: e.target.value })} {...a} />}</Field>
          <Field id="a-c" label="Cover note">{(a) => <Input value={f.cover_note} onChange={(e) => setF({ ...f, cover_note: e.target.value })} {...a} />}</Field>
          <Field id="a-r" label="Resume (PDF or Word, max 10 MB)">{(a) => <Input type="file" className="pt-1.5" onChange={(e) => setFile(e.target.files?.[0] ?? null)} {...a} />}</Field>
          <div className="flex gap-2"><Button loading={busy} disabled={f.full_name.length < 2 || !f.email} onClick={submit}>Submit application</Button><Button variant="outline" onClick={() => setApplyTo(null)}>Back</Button></div>
        </div>
      ) : !q.data?.jobs.length ? <p className="text-sm text-muted">There are no open positions right now.</p> : (
        <ul className="grid gap-4 md:grid-cols-2">{q.data.jobs.map((j) => (
          <li key={j.id}><Card className="h-full"><CardHeader><CardTitle>{j.title}</CardTitle><Badge>{j.employment_type.replace('_', ' ')}</Badge></CardHeader><CardBody className="space-y-4"><p className="line-clamp-4 whitespace-pre-wrap text-sm text-muted">{j.description || 'Learn more about this opportunity and apply to join our team.'}</p><Button onClick={() => setApplyTo(j.id)}>Apply</Button></CardBody></Card></li>))}</ul>)}
      </main><footer className="border-t border-slate-200 bg-white px-5 py-6 text-center text-xs text-slate-500">{q.data?.organization ?? 'Careers'} · Powered by Talvynza</footer>
    </div>
  )
}
