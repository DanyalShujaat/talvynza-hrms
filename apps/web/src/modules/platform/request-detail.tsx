import { ArrowLeft, ArrowUpRight, Check, Clock3, FileText, X } from 'lucide-react'
import * as React from 'react'
import { Link, useLocation, useParams } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, ErrorState, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { Avatar, ConfirmButton, StatusText } from '@/components/ui/extras'
import { Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useSend } from '@/lib/hooks'
import { cn, formatDate } from '@/lib/utils'
import { restoreView } from '@/lib/view-state'
import { requestDetail, requestKey, requestTitle, requestTones, seenStorageKey, sourceLink, useRequestRows, type RequestRow } from './request-data'

function Facts({ row }: { row: RequestRow }) {
  const facts = [
    ['From', row.employee || 'Employee'], ['Employee ID', row.employee_code || '-'],
    ['Submitted', formatDate(row.created_at, { dateStyle: 'medium' })], ['Type', row.categoryLabel],
    ...(row.start_date ? [['From date', row.start_date], ['To date', row.end_date || row.start_date]] : []),
    ...(row.days != null ? [['Days', String(row.days)]] : []),
    ...(row.work_date ? [['Work date', row.work_date]] : []),
    ...(row.requested_in ? [['Requested in', formatDate(row.requested_in, { timeStyle: 'short' })]] : []),
    ...(row.requested_out ? [['Requested out', formatDate(row.requested_out, { timeStyle: 'short' })]] : []),
    ...(row.amount ? [['Claimed amount', String(row.amount)]] : []),
    ...(row.principal ? [['Principal', String(row.principal)]] : []),
    ...(row.installments ? [['Installments', String(row.installments)]] : []),
  ]
  return <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">{facts.map(([label, value]) => <div key={label} className="rounded-xl border border-border bg-surface-2/55 p-4"><p className="text-[11px] font-semibold uppercase tracking-wide text-subtle">{label}</p><p className="mt-1 break-words text-sm font-semibold">{value}</p></div>)}</div>
}

export function RequestDetailPage({ own = false }: { own?: boolean }) {
  const { kind, id } = useParams()
  const { pathname, search } = useLocation()
  const { rows, loading, failed, refresh, me, permissions } = useRequestRows(own)
  const row = rows.find(item => item.slug === kind && item.id === id)
  const scope = me?.active_organization ? `${me.identity.id}:${me.active_organization.id}` : undefined
  const back = restoreView(scope, own ? '/me/requests' : '/inbox')
  const profileTab = row?.slug === 'attendance' ? 'attendance' : row?.slug === 'leave' ? 'leave' : 'overview'
  const canOpenProfile = !own && (permissions.has('employees.read') || permissions.has('employees.read_team'))
  const [rejecting, setRejecting] = React.useState(false)
  const [note, setNote] = React.useState('')
  React.useEffect(() => { setRejecting(false); setNote('') }, [kind, id])
  React.useEffect(() => { if (!row) return; const key = seenStorageKey(me?.identity?.id, me?.active_organization?.id, own); try { const seen: string[] = JSON.parse(localStorage.getItem(key) || '[]'); localStorage.setItem(key, JSON.stringify([...new Set([...seen, requestKey(row)])])) } catch { /* optional local read marker */ } }, [row, own, me?.identity?.id, me?.active_organization?.id])
  const canDecide = !!row && !own && (
    row.status === 'pending' && ['Leave', 'Attendance'].includes(row.categoryLabel)
    || row.status === 'requested' && row.categoryLabel === 'Loan'
    || row.status === 'submitted' && row.categoryLabel === 'Expense' && permissions.has('expenses.approve')
  )
  const decisionPath = kind === 'leave' ? `/leave/requests/${id}/decision`
    : kind === 'attendance' ? `/attendance/adjustments/${id}/decision`
      : kind === 'loan' ? `/loans/${id}/decision` : `/expenses/${id}/manager-decision`
  const decision = useSend<{ approve: boolean; note?: string }>('POST', decisionPath, {
    invalidate: kind === 'leave' ? ['/leave', '/attendance'] : [decisionPath.split('/').slice(0, 2).join('/')],
    success: 'Request updated', onSuccess: () => { setRejecting(false); setNote('') },
  })
  if (loading) return <Skeleton className="h-80 w-full rounded-xl" />
  if (failed && !row) return <Card><ErrorState message={errorMessage(failed.error)} onRetry={refresh} /></Card>
  if (!row) return <Card className="p-8 text-center"><h1 className="font-display text-xl font-bold">Request not found</h1><p className="mt-2 text-sm text-muted">It may have been removed or you may not have access.</p><Button asChild variant="outline" className="mt-4"><Link to={back}>Back to inbox</Link></Button></Card>
  return <div className="mx-auto max-w-5xl space-y-5">
    <Link to={back} className="inline-flex items-center gap-2 text-sm font-semibold text-primary hover:underline"><ArrowLeft className="h-4 w-4" />Back to {own ? 'my requests' : 'inbox'}</Link>
    <div data-tour="page-header" className="overflow-hidden rounded-2xl border border-border bg-surface shadow-card"><div className="h-1.5 brand-gradient" /><div className="flex flex-wrap items-start gap-4 p-5 sm:p-6"><Avatar name={row.employee || 'Employee'} size="lg" /><div className="min-w-0 flex-1"><p className="text-xs font-bold uppercase tracking-wider text-cyan">Request details</p><h1 className="mt-1 font-display text-2xl font-extrabold">{requestTitle(row)}</h1><p className="mt-1 text-sm text-muted">{row.employee || 'Employee'} · Submitted {formatDate(row.created_at, { dateStyle: 'medium' })}</p><div className="mt-3 flex flex-wrap gap-2"><span className={cn('rounded-full px-2.5 py-1 text-xs font-semibold', requestTones[row.categoryLabel])}>{row.categoryLabel}</span><StatusText status={row.status} /></div></div>{canDecide && <div className="flex gap-2"><ConfirmButton label={<><Check className="h-4 w-4" />Approve</>} title="Approve this request?" message="The source HR record will be updated." onConfirm={() => decision.mutate({ approve: true })} variant="primary" /><Button variant="danger-soft" onClick={() => setRejecting(true)}><X className="h-4 w-4" />Reject</Button></div>}</div></div>
    <div className="grid items-start gap-5 lg:grid-cols-[minmax(0,1fr)_280px]"><div className="space-y-5"><Card className="p-5 sm:p-6"><div className="mb-4 flex items-center gap-2 text-primary"><FileText className="h-5 w-5" /><h2 className="font-display text-lg font-bold">Application info</h2></div><Facts row={row} />{canOpenProfile && row.employee_id && <Link className="mt-4 inline-flex items-center gap-1.5 text-sm font-medium text-primary hover:underline" to={`/employees/${row.employee_id}?tab=${profileTab}`} state={{ profileBack: { to: pathname + search, label: 'Request details' } }}>Employee profile<ArrowUpRight className="h-4 w-4" /></Link>}{requestDetail(row) && <div className="mt-5 rounded-xl border-l-4 border-cyan bg-info-soft/55 p-4"><p className="text-xs font-bold uppercase tracking-wide text-cyan">Request details</p><p className="mt-1 whitespace-pre-wrap text-sm">{requestDetail(row)}</p></div>}{row.decision_note && <p className="mt-4 text-sm text-muted">Decision note: {row.decision_note}</p>}</Card></div><Card className="p-5"><h2 className="font-display text-base font-bold">Workflow</h2><div className="mt-5 flex gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-success-soft text-success"><Check className="h-4 w-4" /></span><div><p className="text-sm font-semibold">Submitted</p><p className="text-xs text-muted">{formatDate(row.created_at, { dateStyle: 'medium', timeStyle: 'short' })}</p></div></div><div className="ml-4 h-6 border-l border-border" /><div className="flex gap-3"><span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-primary-soft text-primary"><Clock3 className="h-4 w-4" /></span><div><p className="text-sm font-semibold capitalize">{row.status.replace(/_/g, ' ')}</p><p className="text-xs text-muted">Current status</p></div></div><Button asChild className="mt-6 w-full"><Link to={sourceLink(row, permissions.has('expenses.finance_approve'))}>Open in {row.categoryLabel}<ArrowUpRight className="h-4 w-4" /></Link></Button><p className="mt-2 text-xs text-muted">The source module holds the complete record and any additional actions.</p></Card></div>
    <Dialog open={rejecting} onOpenChange={setRejecting}><DialogContent title="Reject request" description="Give the employee a useful reason for the decision."><Textarea aria-label="Reason for rejection" rows={3} value={note} onChange={e => setNote(e.target.value)} placeholder="Explain why the request is being rejected" /><DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button variant="danger" disabled={note.trim().length < 3} loading={decision.isPending} onClick={() => decision.mutate({ approve: false, note: note.trim() })}>Reject request</Button></DialogFooter></DialogContent></Dialog>
  </div>
}
