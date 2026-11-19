import { CalendarDays, Megaphone, Plus, Trash2 } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Card, CardBody, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { ConfirmButton } from '@/components/ui/extras'
import { Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn, formatDate } from '@/lib/utils'
import { Opts, useOrgLists } from '@/modules/people/employees'

interface NoticeRow { id: string; title: string; body: string; audience: string; published_at: string }

function NoticeDialog() {
  const [open, setOpen] = React.useState(false)
  const { branches, departments } = useOrgLists()
  const blank = { title: '', body: '', target: 'all', branch_id: '', department_id: '' }
  const [f, setF] = React.useState(blank)
  const m = useSend<Record<string, unknown>>('POST', '/notices', { invalidate: ['/notices'], success: 'Notice published', onSuccess: () => { setOpen(false); setF(blank) } })
  const invalid = f.title.length < 3 || f.body.length < 3 || (f.target === 'branch' && !f.branch_id) || (f.target === 'department' && !f.department_id)
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button onClick={() => setOpen(true)}><Plus className="h-4 w-4" />New notice</Button>
      <DialogContent title="Publish a notice" description="Everyone in the audience is notified in the app.">
        <div className="space-y-4">
          <Field id="n-t" label="Title">{(a) => <Input value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} {...a} />}</Field>
          <Field id="n-b" label="Message">{(a) => <Textarea rows={5} value={f.body} onChange={(e) => setF({ ...f, body: e.target.value })} {...a} />}</Field>
          <Field id="n-a" label="Audience">{(a) => <Select value={f.target} onChange={(e) => setF({ ...f, target: e.target.value })} {...a}><option value="all">Everyone</option><option value="branch">One branch</option><option value="department">One department</option></Select>}</Field>
          {f.target === 'branch' && <Field id="n-br" label="Branch">{(a) => <Select value={f.branch_id} onChange={(e) => setF({ ...f, branch_id: e.target.value })} {...a}><Opts list={branches} blank="Select a branch" /></Select>}</Field>}
          {f.target === 'department' && <Field id="n-dp" label="Department">{(a) => <Select value={f.department_id} onChange={(e) => setF({ ...f, department_id: e.target.value })} {...a}><Opts list={departments} blank="Select a department" /></Select>}</Field>}
        </div>
        <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button loading={m.isPending} disabled={invalid} onClick={() => m.mutate({ title: f.title, body: f.body, branch_id: f.target === 'branch' ? f.branch_id : null, department_id: f.target === 'department' ? f.department_id : null })}>Publish</Button></DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

export function NoticesPage({ manage = false }: { manage?: boolean }) {
  const { data: me } = useMe()
  const canManage = manage && !!me?.permissions.includes('notices.manage')
  const q = useGet<NoticeRow[]>('/notices')
  const [open, setOpen] = React.useState<string | null>(null)
  const del = useSend<string>('DELETE', (id) => `/notices/${id}`, { invalidate: ['/notices'], success: 'Notice deleted' })
  return (
    <>
      <PageHeader title="Notices" description={canManage ? 'Announcements you have published to the organization.' : 'Announcements from your organization.'} actions={canManage ? <NoticeDialog /> : undefined} />
      {q.isLoading ? <Skeleton className="h-40 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card>
        : !q.data?.length ? <Card><EmptyState title="No notices yet" icon={Megaphone} /></Card> : (
          <div className="mx-auto max-w-3xl space-y-3">{q.data.map((n) => (
            <Card key={n.id}><CardBody className="flex gap-4">
              <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-lg bg-primary-soft text-primary"><Megaphone className="h-5 w-5" aria-hidden /></span>
              <div className="min-w-0 flex-1">
                <div className="flex items-start justify-between gap-3">
                  <h2 className="font-display text-base font-bold">{n.title}</h2>
                  {canManage && <ConfirmButton variant="ghost" label={<Trash2 className="h-4 w-4" />} title="Delete this notice?" message={`"${n.title}" will be removed for everyone.`} confirmLabel="Delete" onConfirm={() => del.mutate(n.id)} />}
                </div>
                <p className="mt-0.5 flex flex-wrap items-center gap-2 text-xs text-muted"><CalendarDays className="h-3.5 w-3.5" aria-hidden />{formatDate(n.published_at, { dateStyle: 'long' })}<Badge>{n.audience}</Badge></p>
                <p className={cn('mt-2 whitespace-pre-wrap text-sm leading-relaxed', open !== n.id && 'line-clamp-3')}>{n.body}</p>
                {n.body.length > 200 && <button className="mt-1 cursor-pointer text-[13px] font-medium text-primary hover:underline" onClick={() => setOpen(open === n.id ? null : n.id)}>{open === n.id ? 'Show less' : 'Read more'}</button>}
              </div>
            </CardBody></Card>))}</div>)}
    </>
  )
}
