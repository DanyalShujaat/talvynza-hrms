import { useViewTab } from '@/lib/view-state'
import { BookOpen, Clock, ExternalLink, GraduationCap, Plus } from 'lucide-react'
import * as React from 'react'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { DataTable, Person, Progress, SlideOver, StatusText, Tabs } from '@/components/ui/extras'
import { Checkbox, Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { cn, formatDate } from '@/lib/utils'
import { Opts, useOrgLists, type EmpRow } from '@/modules/people/employees'

interface Course { id: string; title: string; description: string | null; category: string; mandatory: boolean; url: string | null; duration_hours: string | null; is_active: boolean; enrolled: number; completed: number }
interface Enrollment { id: string; course_id: string; course: string | null; category: string | null; mandatory: boolean; url: string | null; duration_hours: string | null; employee: string | null; status: string; due_date: string | null; completed_on: string | null; overdue: boolean }

function MyCourses() {
  const q = useGet<Enrollment[]>('/enrollments', { scope: 'mine' })
  const patch = useSend<{ id: string; status: string }>('PATCH', (b) => `/enrollments/${b.id}`, { invalidate: ['/enrollments', '/courses'] })
  if (q.isLoading) return <Skeleton className="h-40 w-full rounded-xl" />
  if (q.isError) return <Card><ErrorState message={errorMessage(q.error)} /></Card>
  if (!q.data?.length) return <Card><EmptyState title="No training assigned" description="Courses assigned to you, and ones you enroll in from the catalog, appear here." icon={GraduationCap} /></Card>
  return (
    <div className="grid gap-4 md:grid-cols-2">{q.data.map((e) => (
      <Card key={e.id}><CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div><p className="font-semibold">{e.course}</p><p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted">{e.category}{e.duration_hours && <span className="inline-flex items-center gap-1"><Clock className="h-3 w-3" />{Number(e.duration_hours)} h</span>}{e.mandatory && <Badge tone="warning">Mandatory</Badge>}</p></div>
          <StatusText status={e.overdue ? 'overdue' : e.status} />
        </div>
        <p className={cn('text-[13px]', e.overdue ? 'font-medium text-danger' : 'text-muted')}>{e.completed_on ? `Completed ${formatDate(e.completed_on, { dateStyle: 'medium' })}` : e.due_date ? `Due ${formatDate(e.due_date, { dateStyle: 'medium' })}` : 'No deadline'}</p>
        <div className="flex flex-wrap gap-2">
          {e.url && <Button asChild variant="outline" size="sm"><a href={e.url} target="_blank" rel="noreferrer" onClick={() => e.status === 'assigned' && patch.mutate({ id: e.id, status: 'in_progress' })}><ExternalLink className="h-3.5 w-3.5" />Open course</a></Button>}
          {e.status === 'assigned' && !e.url && <Button variant="outline" size="sm" onClick={() => patch.mutate({ id: e.id, status: 'in_progress' })}>Start</Button>}
          {e.status !== 'completed' && <Button size="sm" onClick={() => patch.mutate({ id: e.id, status: 'completed' })}>Mark as completed</Button>}
        </div>
      </CardBody></Card>))}</div>
  )
}

function Catalog() {
  const q = useGet<Course[]>('/courses')
  const mine = useGet<Enrollment[]>('/enrollments', { scope: 'mine' })
  const enroll = useSend<string>('POST', (id) => `/courses/${id}/enroll`, { invalidate: ['/enrollments', '/courses'], success: 'Enrolled' })
  const taken = new Set((mine.data ?? []).map((e) => e.course_id))
  if (q.isLoading) return <Skeleton className="h-40 w-full rounded-xl" />
  if (!q.data?.length) return <Card><EmptyState title="The catalog is empty" icon={BookOpen} /></Card>
  return (
    <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">{q.data.map((c) => (
      <Card key={c.id}><CardBody className="flex h-full flex-col gap-2">
        <p className="flex items-center gap-2 text-xs text-muted">{c.category}{c.mandatory && <Badge tone="warning">Mandatory</Badge>}</p>
        <p className="font-semibold">{c.title}</p>
        {c.description && <p className="line-clamp-3 text-[13px] text-muted">{c.description}</p>}
        <div className="mt-auto flex items-center justify-between pt-2"><span className="text-xs text-muted">{c.duration_hours ? `${Number(c.duration_hours)} hours` : ''}</span>
          {taken.has(c.id) ? <Badge tone="success">Enrolled</Badge> : <Button size="sm" variant="soft" onClick={() => enroll.mutate(c.id)}>Enroll</Button>}</div>
      </CardBody></Card>))}</div>
  )
}

export function MyTrainingPage() {
  const [tab, setTab] = useViewTab(['mine', 'catalog'] as const, 'mine')
  return (
    <>
      <PageHeader title="Training" description="Courses assigned to you and the full catalog." />
      <Tabs tabs={[{ id: 'mine', label: 'My courses' }, { id: 'catalog', label: 'Course catalog' }]} value={tab} onChange={setTab} />
      {tab === 'mine' ? <MyCourses /> : <Catalog />}
    </>
  )
}

function CourseDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const blank = { title: '', description: '', category: 'General', mandatory: false, url: '', duration_hours: '' }
  const [f, setF] = React.useState(blank)
  const m = useSend<Record<string, unknown>>('POST', '/courses', { invalidate: ['/courses'], success: 'Course added', onSuccess: () => { onOpenChange(false); setF(blank) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Add a course">
        <div className="space-y-4">
          <Field id="co-t" label="Title">{(a) => <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} {...a} />}</Field>
          <Field id="co-d" label="Description">{(a) => <Textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} {...a} />}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="co-c" label="Category">{(a) => <Input value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} {...a} />}</Field>
            <Field id="co-h" label="Duration (hours)">{(a) => <Input type="number" min={0} step="0.5" value={f.duration_hours} onChange={(e) => setF({ ...f, duration_hours: e.target.value })} {...a} />}</Field>
          </div>
          <Field id="co-u" label="Link to the material (optional)" hint="A web address starting with https://">{(a) => <Input type="url" placeholder="https://" value={f.url} onChange={(e) => setF({ ...f, url: e.target.value })} {...a} />}</Field>
          <Checkbox label="Mandatory for the people it is assigned to" checked={f.mandatory} onChange={(e) => setF({ ...f, mandatory: e.target.checked })} />
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={f.title.trim().length < 3} onClick={() => m.mutate({ title: f.title, description: f.description || null, category: f.category || 'General', mandatory: f.mandatory, url: f.url || null, duration_hours: f.duration_hours || null })}>Add course</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function AssignDialog({ course, onClose }: { course: Course | null; onClose: () => void }) {
  const { departments } = useOrgLists()
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, !!course)
  const [who, setWho] = React.useState<'everyone' | 'department' | 'people'>('everyone')
  const [dept, setDept] = React.useState('')
  const [sel, setSel] = React.useState<Set<string>>(new Set())
  const [due, setDue] = React.useState('')
  const m = useSend<Record<string, unknown>, { assigned: number }>('POST', `/courses/${course?.id}/assign`, { invalidate: ['/courses', '/enrollments'], onSuccess: (r) => { toast.success(r.assigned ? `Assigned to ${r.assigned} people` : 'Everyone selected already has this course'); onClose(); setSel(new Set()) } })
  return (
    <Dialog open={!!course} onOpenChange={(o) => !o && onClose()}>
      <DialogContent title={`Assign ${course?.title ?? ''}`} description="People who already have the course are skipped.">
        <div className="space-y-4">
          <Field id="ta-w" label="Assign to">{(a) => <Select value={who} onChange={(e) => setWho(e.target.value as typeof who)} {...a}><option value="everyone">Everyone</option><option value="department">A department</option><option value="people">Selected people</option></Select>}</Field>
          {who === 'department' && <Field id="ta-d" label="Department">{(a) => <Select value={dept} onChange={(e) => setDept(e.target.value)} {...a}><Opts list={departments} blank="Select a department" /></Select>}</Field>}
          {who === 'people' && <div className="max-h-52 space-y-0.5 overflow-auto rounded-lg border border-border p-2">{(people.data?.items ?? []).map((p) => (
            <label key={p.id} className="flex cursor-pointer items-center gap-2.5 rounded px-2 py-1.5 text-sm hover:bg-surface-2"><input type="checkbox" className="h-4 w-4 accent-[var(--color-primary)]" checked={sel.has(p.id)} onChange={(e) => setSel((s) => { const n = new Set(s); if (e.target.checked) n.add(p.id); else n.delete(p.id); return n })} />{p.full_name}</label>))}</div>}
          <Field id="ta-u" label="Complete by (optional)">{(a) => <Input type="date" value={due} onChange={(e) => setDue(e.target.value)} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={(who === 'department' && !dept) || (who === 'people' && sel.size === 0)} onClick={() => m.mutate({ everyone: who === 'everyone', department_id: who === 'department' ? dept : null, employee_ids: who === 'people' ? [...sel] : [], due_date: due || null })}>Assign</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Learners({ course, onClose }: { course: Course | null; onClose: () => void }) {
  const q = useGet<Enrollment[]>('/enrollments', { scope: 'all', course_id: course?.id }, !!course)
  return (
    <SlideOver open={!!course} onOpenChange={(o) => !o && onClose()} title={course?.title ?? ''}>
      <DataTable rows={q.data} rowKey={(e) => e.id} query={q} empty="Nobody is enrolled yet" cols={[
        { header: 'Employee', cell: (e) => <Person name={e.employee ?? 'Unknown'} size="sm" /> },
        { header: 'Due', cell: (e) => (e.due_date ? formatDate(e.due_date, { dateStyle: 'medium' }) : '') },
        { header: 'Status', cell: (e) => <StatusText status={e.overdue ? 'overdue' : e.status} /> },
      ]} />
    </SlideOver>
  )
}

export function TrainingPage() {
  const q = useGet<Course[]>('/courses')
  const [adding, setAdding] = React.useState(false)
  const [assigning, setAssigning] = React.useState<Course | null>(null)
  const [viewing, setViewing] = React.useState<Course | null>(null)
  return (
    <>
      <PageHeader title="Training" description="Courses, who they are assigned to and completion." actions={<Button onClick={() => setAdding(true)}><Plus className="h-4 w-4" />Add course</Button>} />
      <Card><DataTable rows={q.data} rowKey={(c) => c.id} query={q} empty="No courses yet" emptyHint="Add a course, then assign it to people or a whole department." emptyIcon={BookOpen} cols={[
        { header: 'Course', cell: (c) => <div><p className="font-semibold">{c.title}</p><p className="flex items-center gap-2 text-xs text-muted">{c.category}{c.duration_hours && ` · ${Number(c.duration_hours)} h`}{c.mandatory && <Badge tone="warning">Mandatory</Badge>}</p></div> },
        { header: 'Completion', cell: (c) => (c.enrolled ? <div className="flex w-52 items-center gap-2"><Progress value={(c.completed / c.enrolled) * 100} tone="success" className="flex-1" /><span className="text-xs text-muted">{c.completed} of {c.enrolled}</span></div> : <span className="text-subtle">Not assigned</span>) },
        { header: '', right: true, cell: (c) => <div className="flex justify-end gap-2"><Button size="sm" variant="outline" onClick={() => setViewing(c)}>Learners</Button><Button size="sm" onClick={() => setAssigning(c)}>Assign</Button></div> },
      ]} /></Card>
      <CourseDialog open={adding} onOpenChange={setAdding} /><AssignDialog course={assigning} onClose={() => setAssigning(null)} /><Learners course={viewing} onClose={() => setViewing(null)} />
    </>
  )
}
