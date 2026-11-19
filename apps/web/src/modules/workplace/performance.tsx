import { Plus, Target, Trash2 } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton, DataTable, Person, Progress, Stars, StatusText, Tabs } from '@/components/ui/extras'
import { Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { Opts, type EmpRow } from '@/modules/people/employees'

interface Goal { id: string; employee_id: string; employee: string | null; title: string; description: string | null; due_date: string | null; progress: number; status: string; overdue: boolean }
interface Review { id: string; cycle: string | null; employee: string | null; reviewer: string | null; status: string; self_rating: number | null; self_comment: string | null; manager_rating: number | null; manager_comment: string | null }
interface Cycle { id: string; name: string; period_start: string; period_end: string; status: string; reviews: number; completed: number }

function GoalDialog({ open, onOpenChange, pickEmployee }: { open: boolean; onOpenChange: (o: boolean) => void; pickEmployee: boolean }) {
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, pickEmployee && open)
  const blank = { title: '', description: '', due_date: '', employee_id: '' }
  const [f, setF] = React.useState(blank)
  const m = useSend<Record<string, unknown>>('POST', '/goals', { invalidate: ['/goals'], success: 'Goal added', onSuccess: () => { onOpenChange(false); setF(blank) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="New goal">
        <div className="space-y-4">
          {pickEmployee && <Field id="g-e" label="For">{(a) => <Select value={f.employee_id} onChange={(e) => setF({ ...f, employee_id: e.target.value })} {...a}><Opts list={(people.data?.items ?? []).map((p) => ({ id: p.id, name: p.full_name }))} blank="Select a team member" /></Select>}</Field>}
          <Field id="g-t" label="Goal">{(a) => <Input placeholder="Launch the new onboarding flow" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} {...a} />}</Field>
          <Field id="g-d" label="How will it be measured? (optional)">{(a) => <Textarea rows={3} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} {...a} />}</Field>
          <Field id="g-u" label="Target date">{(a) => <Input type="date" value={f.due_date} onChange={(e) => setF({ ...f, due_date: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={f.title.trim().length < 3 || (pickEmployee && !f.employee_id)} onClick={() => m.mutate({ title: f.title, description: f.description || null, due_date: f.due_date || null, employee_id: f.employee_id || null })}>Add goal</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function Goals({ scope }: { scope: 'mine' | 'team' | 'all' }) {
  const q = useGet<Goal[]>('/goals', { scope })
  const patch = useSend<{ id: string; progress?: number; status?: string }>('PATCH', (b) => `/goals/${b.id}`, { invalidate: ['/goals'] })
  const del = useSend<string>('DELETE', (id) => `/goals/${id}`, { invalidate: ['/goals'], success: 'Goal removed' })
  if (q.isLoading) return <Skeleton className="h-40 w-full rounded-xl" />
  if (q.isError) return <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
  if (!q.data?.length) return <Card><EmptyState title="No goals yet" description={scope === 'mine' ? 'Set a goal to track what you are working toward.' : 'Goals set for your team appear here.'} icon={Target} /></Card>
  return (
    <div className="grid gap-4 md:grid-cols-2">{q.data.map((g) => (
      <Card key={g.id}><CardBody className="space-y-3">
        <div className="flex items-start justify-between gap-3">
          <div className="min-w-0">{scope !== 'mine' && <p className="mb-1 text-xs font-medium text-primary">{g.employee}</p>}<p className={cn('font-semibold', g.status === 'dropped' && 'text-muted line-through')}>{g.title}</p>{g.description && <p className="mt-0.5 text-[13px] text-muted">{g.description}</p>}</div>
          <StatusText status={g.overdue ? 'overdue' : g.status} />
        </div>
        <div className="flex items-center gap-3"><Progress value={g.progress} tone={g.progress === 100 ? 'success' : 'primary'} className="flex-1" /><span className="w-10 text-right text-sm font-semibold tabular-nums">{g.progress}%</span></div>
        <div className="flex items-center justify-between gap-2">
          <span className="text-xs text-muted">{g.due_date ? `Target ${formatDate(g.due_date, { dateStyle: 'medium' })}` : 'No target date'}</span>
          {g.status === 'active' && <div className="flex items-center gap-1.5">
            <input type="range" min={0} max={100} step={5} aria-label={`Progress on ${g.title}`} defaultValue={g.progress} className="w-28 accent-[var(--color-primary)]" onMouseUp={(e) => patch.mutate({ id: g.id, progress: Number(e.currentTarget.value) })} onKeyUp={(e) => patch.mutate({ id: g.id, progress: Number(e.currentTarget.value) })} onTouchEnd={(e) => patch.mutate({ id: g.id, progress: Number(e.currentTarget.value) })} />
            <ConfirmButton variant="ghost" label={<Trash2 className="h-4 w-4" />} title="Remove this goal?" message={`"${g.title}" will be deleted.`} confirmLabel="Remove" onConfirm={() => del.mutate(g.id)} />
          </div>}
        </div>
      </CardBody></Card>))}</div>
  )
}

function AssessDialog({ review, mode, onClose }: { review: Review | null; mode: 'self' | 'manager'; onClose: () => void }) {
  const [rating, setRating] = React.useState(0)
  const [comment, setComment] = React.useState('')
  React.useEffect(() => { setRating(0); setComment('') }, [review])
  const m = useSend<{ rating: number; comment: string }>('POST', `/reviews/${review?.id}/${mode}`, { invalidate: ['/reviews', '/review-cycles'], success: mode === 'self' ? 'Self-assessment submitted' : 'Review completed', onSuccess: onClose })
  return (
    <Dialog open={!!review} onOpenChange={(o) => !o && onClose()}>
      <DialogContent className="max-w-xl" title={mode === 'self' ? 'Your self-assessment' : `Review for ${review?.employee ?? ''}`} description={review?.cycle ?? undefined}>
        <div className="space-y-4">
          {mode === 'manager' && review?.self_comment && (
            <div className="rounded-xl bg-surface-2 p-4 text-sm"><p className="mb-1 flex items-center gap-2 font-semibold">Their self-assessment <Stars value={review.self_rating} /></p><p className="whitespace-pre-wrap text-muted">{review.self_comment}</p></div>)}
          <div><p className="mb-1.5 text-[13px] font-medium">Overall rating</p><Stars value={rating} size={7} onChange={setRating} /></div>
          <Field id="rv-c" label={mode === 'self' ? 'What did you achieve, and what would you do differently?' : 'Feedback for the employee'}>{(a) => <Textarea rows={6} value={comment} onChange={(e) => setComment(e.target.value)} {...a} />}</Field>
          {mode === 'manager' && <p className="text-xs text-muted">The employee sees your rating and feedback once you submit.</p>}
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={!rating || comment.trim().length < 3} onClick={() => m.mutate({ rating, comment })}>Submit</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

function MyReviews() {
  const q = useGet<Review[]>('/reviews', { scope: 'mine' })
  const [assess, setAssess] = React.useState<Review | null>(null)
  if (q.isLoading) return <Skeleton className="h-32 w-full rounded-xl" />
  if (!q.data?.length) return <Card><EmptyState title="No reviews yet" description="When HR starts a review cycle, your self-assessment appears here." icon={Target} /></Card>
  return (
    <>
      <div className="space-y-4">{q.data.map((r) => (
        <Card key={r.id}>
          <CardHeader><div><CardTitle>{r.cycle}</CardTitle><p className="text-xs text-muted">Reviewer: {r.reviewer ?? 'HR'}</p></div><StatusText status={r.status} /></CardHeader>
          <CardBody className="grid gap-5 md:grid-cols-2">
            <div><p className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">Your assessment {r.self_rating && <Stars value={r.self_rating} />}</p>
              {r.self_comment ? <p className="whitespace-pre-wrap text-sm text-muted">{r.self_comment}</p> : <Button size="sm" onClick={() => setAssess(r)}>Write self-assessment</Button>}</div>
            <div><p className="mb-1.5 flex items-center gap-2 text-[13px] font-semibold">Manager's review {r.manager_rating && <Stars value={r.manager_rating} />}</p>
              <p className="whitespace-pre-wrap text-sm text-muted">{r.manager_comment ?? (r.status === 'completed' ? '' : 'Shared with you when the review is complete.')}</p></div>
          </CardBody>
        </Card>))}</div>
      <AssessDialog review={assess} mode="self" onClose={() => setAssess(null)} />
    </>
  )
}

export function MyPerformancePage() {
  const [tab, setTab] = React.useState<'goals' | 'reviews'>('goals')
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <PageHeader title="Goals and reviews" description="What you are working toward and how your reviews went." actions={tab === 'goals' ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New goal</Button> : undefined} />
      <Tabs tabs={[{ id: 'goals', label: 'My goals' }, { id: 'reviews', label: 'My reviews' }]} value={tab} onChange={setTab} />
      {tab === 'goals' ? <Goals scope="mine" /> : <MyReviews />}
      <GoalDialog open={open} onOpenChange={setOpen} pickEmployee={false} />
    </>
  )
}

function Cycles({ manage }: { manage: boolean }) {
  const q = useGet<Cycle[]>('/review-cycles')
  const [open, setOpen] = React.useState(false)
  const [f, setF] = React.useState({ name: '', period_start: '', period_end: '' })
  const create = useSend<typeof f>('POST', '/review-cycles', { invalidate: ['/review-cycles'], success: 'Cycle created', onSuccess: () => { setOpen(false); setF({ name: '', period_start: '', period_end: '' }) } })
  const launch = useSend<string>('POST', (id) => `/review-cycles/${id}/launch`, { invalidate: ['/review-cycles', '/reviews'], success: 'Cycle launched. Everyone has been asked for a self-assessment.' })
  const close = useSend<string>('POST', (id) => `/review-cycles/${id}/close`, { invalidate: ['/review-cycles', '/reviews'], success: 'Cycle closed' })
  return (
    <>
      {manage && <div className="mb-4 flex justify-end"><Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New review cycle</Button></div>}
      <Card><DataTable rows={q.data} rowKey={(c) => c.id} query={q} empty="No review cycles yet" emptyHint="Create a cycle, then launch it to open self-assessments for every employee." emptyIcon={Target} cols={[
        { header: 'Cycle', cell: (c) => <div><p className="font-semibold">{c.name}</p><p className="text-xs text-muted">{formatDate(c.period_start, { dateStyle: 'medium' })} to {formatDate(c.period_end, { dateStyle: 'medium' })}</p></div> },
        { header: 'Progress', cell: (c) => (c.reviews ? <div className="flex w-48 items-center gap-2"><Progress value={(c.completed / c.reviews) * 100} tone="success" className="flex-1" /><span className="text-xs text-muted">{c.completed}/{c.reviews}</span></div> : <span className="text-subtle">Not launched</span>) },
        { header: 'Status', cell: (c) => <StatusText status={c.status} /> },
        { header: '', right: true, cell: (c) => (manage ? <>
          {c.status === 'draft' && <ConfirmButton variant="primary" label="Launch" title={`Launch ${c.name}?`} message="A review is created for every current employee, with their manager as the reviewer, and everyone is asked for a self-assessment." confirmLabel="Launch cycle" onConfirm={() => launch.mutate(c.id)} />}
          {c.status === 'active' && <ConfirmButton variant="outline" label="Close cycle" title={`Close ${c.name}?`} message="Reviews that are not complete can no longer be submitted." confirmLabel="Close cycle" onConfirm={() => close.mutate(c.id)} />}
        </> : null) },
      ]} /></Card>
      <Dialog open={open} onOpenChange={setOpen}><DialogContent title="New review cycle">
        <div className="space-y-4">
          <Field id="cy-n" label="Name">{(a) => <Input placeholder="Annual review 2026" value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} {...a} />}</Field>
          <div className="grid grid-cols-2 gap-3">
            <Field id="cy-s" label="Period reviewed from">{(a) => <Input type="date" value={f.period_start} onChange={(e) => setF({ ...f, period_start: e.target.value })} {...a} />}</Field>
            <Field id="cy-e" label="To">{(a) => <Input type="date" value={f.period_end} onChange={(e) => setF({ ...f, period_end: e.target.value })} {...a} />}</Field>
          </div>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={create.isPending} disabled={f.name.trim().length < 3 || !f.period_start || !f.period_end} onClick={() => create.mutate(f)}>Create cycle</Button></DialogFooter>
      </DialogContent></Dialog>
    </>
  )
}

function ReviewsTable({ scope }: { scope: 'team' | 'all' }) {
  const q = useGet<Review[]>('/reviews', { scope })
  const [assess, setAssess] = React.useState<Review | null>(null)
  return (
    <>
      <Card><DataTable rows={q.data} rowKey={(r) => r.id} query={q} empty="No reviews to show" emptyHint={scope === 'team' ? 'Reviews for your direct reports appear here when a cycle is launched.' : undefined} emptyIcon={Target} cols={[
        { header: 'Employee', cell: (r) => <Person name={r.employee ?? 'Unknown'} sub={r.cycle} size="sm" /> },
        { header: 'Reviewer', cell: (r) => r.reviewer ?? <Badge>HR</Badge> },
        { header: 'Self', cell: (r) => (r.self_rating ? <Stars value={r.self_rating} /> : <span className="text-subtle">Not submitted</span>) },
        { header: 'Manager', cell: (r) => (r.manager_rating ? <Stars value={r.manager_rating} /> : <span className="text-subtle">Pending</span>) },
        { header: 'Status', cell: (r) => <StatusText status={r.status} /> },
        { header: '', right: true, cell: (r) => (r.status === 'pending_manager' ? <Button size="sm" onClick={() => setAssess(r)}>Write review</Button> : null) },
      ]} /></Card>
      <AssessDialog review={assess} mode="manager" onClose={() => setAssess(null)} />
    </>
  )
}

export function PerformancePage() {
  const { data: me } = useMe()
  const manage = !!me?.permissions.includes('performance.manage')
  const team = !!me?.permissions.includes('performance.review_team')
  type T = 'team' | 'all' | 'cycles' | 'goals'
  const tabs: { id: T; label: string }[] = []
  if (team) tabs.push({ id: 'team', label: 'Reviews I owe' })
  if (manage) tabs.push({ id: 'all', label: 'All reviews' }, { id: 'cycles', label: 'Review cycles' })
  tabs.push({ id: 'goals', label: manage ? 'All goals' : 'Team goals' })
  const [tab, setTab] = React.useState<T>(tabs[0].id)
  const [open, setOpen] = React.useState(false)
  return (
    <>
      <PageHeader title="Performance" description="Review cycles, manager reviews and goals." actions={tab === 'goals' ? <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />Set a goal</Button> : undefined} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />
      {tab === 'team' && <ReviewsTable scope="team" />}{tab === 'all' && <ReviewsTable scope="all" />}{tab === 'cycles' && <Cycles manage={manage} />}
      {tab === 'goals' && <Goals scope={manage ? 'all' : 'team'} />}
      <GoalDialog open={open} onOpenChange={setOpen} pickEmployee />
    </>
  )
}
