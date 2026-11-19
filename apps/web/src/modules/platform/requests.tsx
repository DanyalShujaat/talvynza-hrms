import { CheckCheck, Inbox, RefreshCw, Search } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { Button } from '@/components/ui/button'
import { Card, ErrorState, Skeleton } from '@/components/ui/card'
import { Avatar, StatusText } from '@/components/ui/extras'
import { Input, Select } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { cn, formatDate } from '@/lib/utils'
import { requestDetail, requestKey, requestTitle, requestTones, seenStorageKey, useRequestRows, waiting } from './request-data'

export function RequestsPage({ own = false }: { own?: boolean }) {
  const { rows: allRows, configs, loading, failed, refresh, me } = useRequestRows(own)
  const [filter, setFilter] = React.useState('open')
  const [type, setType] = React.useState('all')
  const [search, setSearch] = React.useState('')
  const [seen, setSeen] = React.useState<string[]>([])
  const key = seenStorageKey(me?.identity?.id, me?.active_organization?.id, own)
  React.useEffect(() => { try { setSeen(JSON.parse(localStorage.getItem(key) || '[]')) } catch { setSeen([]) } }, [key])
  const markSeen = () => { const next = [...new Set([...seen, ...rows.map(requestKey)])]; localStorage.setItem(key, JSON.stringify(next)); setSeen(next) }
  const rows = allRows.filter(r => filter === 'all' || (filter === 'open' ? waiting.has(r.status) : !waiting.has(r.status)))
    .filter(r => type === 'all' || r.categoryLabel === type)
    .filter(r => `${r.employee} ${requestTitle(r)} ${requestDetail(r)}`.toLowerCase().includes(search.toLowerCase()))
  const open = allRows.filter(r => waiting.has(r.status)).length
  return <div className="space-y-5">
    <div data-tour="page-header" className="flex flex-wrap items-end justify-between gap-3"><div><p className="text-xs font-bold uppercase tracking-[0.16em] text-cyan">Work queue</p><h1 className="mt-1 font-display text-2xl font-extrabold">{own ? 'My requests' : 'Request inbox'}</h1><p className="mt-1 text-sm text-muted">{own ? 'Track requests you have submitted across HR modules.' : 'Review requests from your teams in one place.'}</p></div><Button variant="outline" onClick={refresh} aria-label="Refresh requests"><RefreshCw className="h-4 w-4" />Refresh</Button></div>
    <div className="grid gap-3 sm:grid-cols-3"><div className="rounded-xl border border-primary/20 bg-primary-soft p-4"><p className="text-xs font-semibold text-primary">Open requests</p><p className="mt-1 font-display text-2xl font-extrabold text-primary">{open}</p></div><div className="rounded-xl border border-success/20 bg-success-soft p-4"><p className="text-xs font-semibold text-success">Completed</p><p className="mt-1 font-display text-2xl font-extrabold text-success">{allRows.length - open}</p></div><div className="rounded-xl border border-cyan/20 bg-info-soft p-4"><p className="text-xs font-semibold text-cyan">All requests</p><p className="mt-1 font-display text-2xl font-extrabold text-cyan">{allRows.length}</p></div></div>
    {failed && <Card className="p-4"><ErrorState message={`Some requests could not be loaded: ${errorMessage(failed.error)}`} onRetry={refresh} /></Card>}
    <Card data-tour="primary-content" className="overflow-hidden"><div className="flex flex-wrap items-center gap-2 border-b border-border bg-gradient-to-r from-primary-soft via-surface to-info-soft p-4"><span className="brand-gradient mr-1 flex h-9 w-9 items-center justify-center rounded-xl text-white"><Inbox className="h-5 w-5" /></span><div className="relative min-w-48 flex-1 sm:max-w-sm"><Search className="absolute left-3 top-2.5 h-4 w-4 text-subtle" /><Input aria-label="Search requests" placeholder="Search people or requests" className="pl-9" value={search} onChange={e => setSearch(e.target.value)} /></div><Select aria-label="Request status" className="w-40" value={filter} onChange={e => setFilter(e.target.value)}><option value="open">Open</option><option value="closed">Completed</option><option value="all">All statuses</option></Select><Select aria-label="Request type" className="w-40" value={type} onChange={e => setType(e.target.value)}><option value="all">All types</option>{configs.filter(c => c.enabled).map(c => <option key={c.label}>{c.label}</option>)}</Select><Button variant="outline" size="sm" onClick={markSeen}><CheckCheck className="h-4 w-4" />Mark read</Button></div>
      {loading ? <div className="space-y-3 p-4">{[1,2,3].map(i => <Skeleton key={i} className="h-20 rounded-xl" />)}</div> : rows.length ? <div className="divide-y divide-border">{rows.map(row => <Link key={requestKey(row)} to={`${own ? '/me/requests' : '/inbox'}/${row.slug}/${row.id}`} className="group flex items-start gap-3 px-4 py-4 transition-colors hover:bg-primary-soft/40 sm:items-center"><Avatar name={row.employee || 'Employee'} /><div className="min-w-0 flex-1"><div className="flex flex-wrap items-center gap-2"><span className="font-semibold group-hover:text-primary">{own ? requestTitle(row) : row.employee || 'Employee'}</span>{!seen.includes(requestKey(row)) && <span className="h-2 w-2 rounded-full bg-cyan" aria-label="Unread" />}</div><p className="mt-0.5 truncate text-xs text-muted">{own ? requestDetail(row) : requestTitle(row)}</p></div><span className={cn('hidden rounded-full px-2.5 py-1 text-xs font-semibold sm:inline-flex', requestTones[row.categoryLabel])}>{row.categoryLabel}</span><StatusText status={row.status} /><span className="hidden shrink-0 text-xs text-muted md:inline">{formatDate(row.created_at, { dateStyle: 'medium' })}</span><span className="text-primary">→</span></Link>)}</div> : <div className="px-5 py-16 text-center"><Inbox className="mx-auto h-9 w-9 text-cyan" /><h2 className="mt-3 font-display font-bold">No requests found</h2><p className="mt-1 text-sm text-muted">Try another filter or search.</p></div>}</Card>
    <p className="text-xs text-muted">Open a request to review it on its own page. Decisions update the source HR record.</p>
  </div>
}
