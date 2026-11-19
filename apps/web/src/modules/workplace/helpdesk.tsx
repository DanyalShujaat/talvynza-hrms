import { ArrowLeft, LifeBuoy, Lock, Plus, Send } from 'lucide-react'
import * as React from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, CardHeader, CardTitle, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { Avatar, DataTable, Detail, Person, Stars, StatusText } from '@/components/ui/extras'
import { Checkbox, Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { Opts, type EmpRow } from '@/modules/people/employees'

interface Ticket { id: string; number: number; employee: string | null; category: string; priority: string; subject: string; description: string; status: string; assignee_id: string | null; assignee: string | null; due_at: string; overdue: boolean; rating: number | null; created_at: string }
interface Comment { id: string; author: string; body: string; internal: boolean; created_at: string }
interface TicketDetail extends Ticket { comments: Comment[] }

const CATEGORY: Record<string, string> = { payroll: 'Payroll', attendance: 'Attendance', leave: 'Leave', profile_update: 'Profile update', benefits: 'Benefits', policy: 'HR policy', general: 'General' }
const PRIORITY_TONE: Record<string, 'neutral' | 'info' | 'warning' | 'danger'> = { low: 'neutral', normal: 'info', high: 'warning', urgent: 'danger' }
const Priority = ({ p }: { p: string }) => <Badge tone={PRIORITY_TONE[p]} className="capitalize">{p}</Badge>

function NewTicketDialog({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const nav = useNavigate()
  const blank = { category: 'general', priority: 'normal', subject: '', description: '' }
  const [f, setF] = React.useState(blank)
  const m = useSend<typeof f, Ticket>('POST', '/tickets', { invalidate: ['/tickets'], success: 'Ticket sent to HR', onSuccess: (t) => { onOpenChange(false); setF(blank); nav(`/me/helpdesk/${t.id}`) } })
  return (
    <Dialog open={open} onOpenChange={onOpenChange}>
      <DialogContent title="Ask HR" description="Only you and the HR help desk can see this ticket.">
        <div className="space-y-4">
          <div className="grid grid-cols-2 gap-3">
            <Field id="tk-c" label="About">{(a) => <Select value={f.category} onChange={(e) => setF({ ...f, category: e.target.value })} {...a}>{Object.entries(CATEGORY).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select>}</Field>
            <Field id="tk-p" label="Priority">{(a) => <Select value={f.priority} onChange={(e) => setF({ ...f, priority: e.target.value })} {...a}>{['low', 'normal', 'high', 'urgent'].map((p) => <option key={p} value={p} className="capitalize">{p}</option>)}</Select>}</Field>
          </div>
          <Field id="tk-s" label="Subject">{(a) => <Input value={f.subject} onChange={(e) => setF({ ...f, subject: e.target.value })} {...a} />}</Field>
          <Field id="tk-d" label="Details">{(a) => <Textarea rows={5} value={f.description} onChange={(e) => setF({ ...f, description: e.target.value })} {...a} />}</Field>
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={m.isPending} disabled={f.subject.trim().length < 3 || f.description.trim().length < 3} onClick={() => m.mutate(f)}>Send ticket</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function MyHelpdeskPage() {
  const [sp, setSp] = useSearchParams()
  const [open, setOpen] = React.useState(sp.get('new') === '1')
  React.useEffect(() => { if (sp.get('new')) setSp({}, { replace: true }) }, [sp, setSp])
  const nav = useNavigate()
  const q = useGet<Ticket[]>('/tickets', { scope: 'mine' })
  return (
    <>
      <PageHeader title="Help desk" description="Questions and requests you have sent to HR." actions={<Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New ticket</Button>} />
      <Card><DataTable rows={q.data} rowKey={(t) => t.id} query={q} empty="You have not raised any tickets" emptyHint="Ask HR about payroll, leave, attendance or anything else." emptyIcon={LifeBuoy} onRowClick={(t) => nav(`/me/helpdesk/${t.id}`)} cols={[
        { header: 'Ticket', cell: (t) => <div><p className="font-medium">{t.subject}</p><p className="text-xs text-muted">#{t.number} · {CATEGORY[t.category]} · {formatDate(t.created_at, { dateStyle: 'medium' })}</p></div> },
        { header: 'Priority', cell: (t) => <Priority p={t.priority} /> },
        { header: 'Status', cell: (t) => <StatusText status={t.status} /> },
      ]} /></Card>
      <NewTicketDialog open={open} onOpenChange={setOpen} />
    </>
  )
}

export function HelpdeskPage() {
  const [status, setStatus] = React.useState('active')
  const nav = useNavigate()
  const q = useGet<Ticket[]>('/tickets', { scope: 'all', status: status || undefined })
  return (
    <>
      <PageHeader title="Help desk" description="Tickets raised by employees. Each has a response target based on its priority." />
      <div className="mb-4"><Select aria-label="Filter by status" className="w-44" value={status} onChange={(e) => setStatus(e.target.value)}>{[['active', 'Open tickets'], ['', 'All tickets'], ['resolved', 'Resolved'], ['closed', 'Closed']].map(([v, l]) => <option key={v} value={v}>{l}</option>)}</Select></div>
      <Card><DataTable rows={q.data} rowKey={(t) => t.id} query={q} empty="No tickets here" emptyIcon={LifeBuoy} onRowClick={(t) => nav(`/helpdesk/${t.id}`)} cols={[
        { header: 'Ticket', cell: (t) => <div><p className="font-medium">{t.subject}</p><p className="text-xs text-muted">#{t.number} · {CATEGORY[t.category]}</p></div> },
        { header: 'Raised by', cell: (t) => <Person name={t.employee ?? 'Unknown'} size="sm" /> },
        { header: 'Priority', cell: (t) => <Priority p={t.priority} /> },
        { header: 'Assigned to', cell: (t) => t.assignee ?? <span className="text-subtle">Unassigned</span> },
        { header: 'Respond by', cell: (t) => <span className={cn(t.overdue && 'font-semibold text-danger')}>{formatDate(t.due_at)}{t.overdue && ' (overdue)'}</span> },
        { header: 'Status', cell: (t) => <StatusText status={t.status} /> },
      ]} /></Card>
    </>
  )
}

export function TicketPage({ staff = false }: { staff?: boolean }) {
  const { id } = useParams()
  const { data: me } = useMe()
  const isStaff = staff && !!me?.permissions.includes('helpdesk.manage')
  const q = useGet<TicketDetail>(`/tickets/${id}`)
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, isStaff)
  const [body, setBody] = React.useState('')
  const [internal, setInternal] = React.useState(false)
  const inv = ['/tickets', '/dashboard']
  const reply = useSend<{ body: string; internal: boolean }>('POST', `/tickets/${id}/comments`, { invalidate: inv, onSuccess: () => setBody('') })
  const patch = useSend<Record<string, unknown>>('PATCH', `/tickets/${id}`, { invalidate: inv, success: 'Ticket updated' })
  const close = useSend<undefined>('POST', `/tickets/${id}/close`, { invalidate: inv, success: 'Ticket closed' })
  const rate = useSend<{ rating: number }>('POST', `/tickets/${id}/rating`, { invalidate: inv, success: 'Thanks for the feedback' })
  if (q.isLoading) return <Skeleton className="h-64 w-full rounded-xl" />
  if (q.isError || !q.data) return <Card><ErrorState message={errorMessage(q.error)} /></Card>
  const t = q.data
  const back = isStaff ? '/helpdesk' : '/me/helpdesk'
  return (
    <>
      <Link to={back} className="mb-3 inline-flex items-center gap-1.5 text-[13px] font-medium text-muted hover:text-fg"><ArrowLeft className="h-4 w-4" />All tickets</Link>
      <PageHeader title={t.subject} description={`Ticket #${t.number} · ${CATEGORY[t.category]} · opened ${formatDate(t.created_at)}`} actions={<StatusText status={t.status} className="text-sm" />} />
      <div className="grid gap-6 lg:grid-cols-3">
        <div className="space-y-4 lg:col-span-2">
          <Card><CardBody><div className="mb-3"><Person name={t.employee ?? 'Unknown'} sub={formatDate(t.created_at)} /></div><p className="whitespace-pre-wrap text-sm leading-relaxed">{t.description}</p></CardBody></Card>
          {t.comments.map((c) => (
            <Card key={c.id} className={cn(c.internal && 'border-warning/40 bg-warning-soft/40')}><CardBody className="flex gap-3">
              <Avatar name={c.author} size="sm" />
              <div className="min-w-0 flex-1">
                <p className="flex flex-wrap items-center gap-2 text-sm"><span className="font-semibold">{c.author}</span><span className="text-xs text-muted">{formatDate(c.created_at)}</span>{c.internal && <Badge tone="warning"><Lock className="h-3 w-3" />Internal note</Badge>}</p>
                <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">{c.body}</p>
              </div>
            </CardBody></Card>))}
          {t.status !== 'closed' ? (
            <Card><CardBody className="space-y-3">
              <Textarea rows={3} aria-label="Reply" placeholder={isStaff ? 'Write a reply to the employee' : 'Write a reply to HR'} value={body} onChange={(e) => setBody(e.target.value)} />
              <div className="flex flex-wrap items-center justify-between gap-3">
                {isStaff ? <Checkbox label="Internal note, hidden from the employee" checked={internal} onChange={(e) => setInternal(e.target.checked)} /> : <span className="text-xs text-muted">{t.status === 'resolved' ? 'Replying reopens the ticket.' : ''}</span>}
                <Button loading={reply.isPending} disabled={!body.trim()} onClick={() => reply.mutate({ body, internal: isStaff && internal })}><Send className="h-4 w-4" />Send</Button>
              </div>
            </CardBody></Card>) : <p className="text-center text-sm text-muted">This ticket is closed.</p>}
        </div>

        <div className="space-y-4">
          <Card><CardHeader><CardTitle>Details</CardTitle></CardHeader><CardBody className="pt-2">
            <Detail rows={[['Priority', <Priority key="p" p={t.priority} />], ['Assigned to', t.assignee ?? 'Not yet assigned'], ['Respond by', <span key="d" className={cn(t.overdue && 'text-danger')}>{formatDate(t.due_at)}</span>]]} />
          </CardBody></Card>
          {isStaff && t.status !== 'closed' && (
            <Card><CardHeader><CardTitle>Manage</CardTitle></CardHeader><CardBody className="space-y-4">
              <Field id="tm-s" label="Status">{(a) => <Select value={t.status} onChange={(e) => patch.mutate({ status: e.target.value })} {...a}><option value="open">Open</option><option value="in_progress">In progress</option><option value="resolved">Resolved</option><option value="closed">Closed</option></Select>}</Field>
              <Field id="tm-a" label="Assign to">{(a) => <Select value={t.assignee_id ?? ''} onChange={(e) => patch.mutate({ assignee_id: e.target.value || null })} {...a}><Opts list={(people.data?.items ?? []).map((p) => ({ id: p.id, name: p.full_name }))} blank="Unassigned" /></Select>}</Field>
              <Field id="tm-p" label="Priority">{(a) => <Select className="capitalize" value={t.priority} onChange={(e) => patch.mutate({ priority: e.target.value })} {...a}>{['low', 'normal', 'high', 'urgent'].map((p) => <option key={p} value={p}>{p}</option>)}</Select>}</Field>
            </CardBody></Card>)}
          {!isStaff && ['resolved', 'closed'].includes(t.status) && (
            <Card><CardHeader><CardTitle>How did we do?</CardTitle></CardHeader><CardBody><Stars value={t.rating} size={6} onChange={(n) => rate.mutate({ rating: n })} /></CardBody></Card>)}
          {isStaff && t.rating && <Card><CardBody className="flex items-center justify-between text-sm"><span className="text-muted">Employee rating</span><Stars value={t.rating} /></CardBody></Card>}
          {!isStaff && !['closed'].includes(t.status) && <Button variant="outline" className="w-full" loading={close.isPending} onClick={() => close.mutate(undefined as never)}>Close this ticket</Button>}
        </div>
      </div>
    </>
  )
}
