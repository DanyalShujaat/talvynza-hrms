import { useMutation, useQueryClient } from '@tanstack/react-query'
import { Bell, CheckCheck, RefreshCw } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Avatar, SlideOver } from '@/components/ui/extras'
import { api, errorMessage } from '@/lib/api'
import { useGet } from '@/lib/hooks'
import { cn, formatDate } from '@/lib/utils'

interface NotificationItem { id: string; kind: string; title: string; body: string | null; link: string | null; created_at: string; read: boolean }
interface NotificationsResponse { unread: number; items: NotificationItem[] }

export function Notifications() {
  const [open, setOpen] = useState(false)
  const [filter, setFilter] = useState<'all' | 'unread'>('all')
  const qc = useQueryClient()
  const navigate = useNavigate()
  const query = useGet<NotificationsResponse>('/notifications')
  useEffect(() => { const timer = setInterval(() => qc.invalidateQueries({ queryKey: ['/notifications'] }), 15_000); return () => clearInterval(timer) }, [qc])
  const refresh = () => qc.invalidateQueries({ queryKey: ['/notifications'] })
  const readAll = useMutation({ mutationFn: () => api('/notifications/read-all', { method: 'POST' }), onSuccess: refresh, onError: e => toast.error(errorMessage(e)) })
  const readOne = useMutation({ mutationFn: (id: string) => api(`/notifications/${id}/read`, { method: 'POST' }), onSuccess: refresh, onError: e => toast.error(errorMessage(e)) })
  const unread = query.data?.unread || 0
  const items = (query.data?.items || []).filter(n => filter === 'all' || !n.read)
  return <>
    <Button variant="ghost" size="icon" aria-label={`Notifications, ${unread} unread`} className="relative" onClick={() => setOpen(true)}><Bell className="h-[18px] w-[18px]" />{unread > 0 && <span className="absolute right-0 top-0 flex h-4 min-w-4 items-center justify-center rounded-full bg-cyan px-1 text-[10px] font-bold text-white">{unread > 9 ? '9+' : unread}</span>}</Button>
    <SlideOver open={open} onOpenChange={setOpen} title="Notifications">
      <div className="-m-5 flex h-full flex-col">
        <div className="border-b border-border bg-gradient-to-br from-primary-soft via-surface to-info-soft px-5 py-4"><div className="flex items-center justify-between gap-3"><div><p className="text-xs font-semibold text-teal">Live updates</p><p className="mt-1 font-display text-lg font-bold">{unread} unread</p></div><span className="brand-gradient flex h-10 w-10 items-center justify-center rounded-xl text-white"><Bell className="h-5 w-5" /></span></div><div className="mt-4 flex items-center justify-between gap-2"><div className="flex gap-1 rounded-lg border border-border bg-surface p-1">{(['all', 'unread'] as const).map(value => <button key={value} type="button" onClick={() => setFilter(value)} className={cn('cursor-pointer rounded-md px-3 py-1.5 text-xs font-semibold capitalize', filter === value ? 'bg-primary-soft text-primary' : 'text-muted hover:bg-surface-2')}>{value}</button>)}</div><div className="flex gap-1"><Button variant="ghost" size="icon" aria-label="Refresh notifications" title="Refresh" onClick={refresh}><RefreshCw className="h-4 w-4" /></Button>{unread > 0 && <Button variant="outline" size="sm" onClick={() => readAll.mutate()} loading={readAll.isPending}><CheckCheck className="h-4 w-4" />Mark all read</Button>}</div></div></div>
        <div className="flex-1 overflow-y-auto">{query.isError ? <p className="p-6 text-sm text-danger">{errorMessage(query.error)}</p> : query.isLoading ? <p className="p-6 text-sm text-muted">Loading notifications…</p> : items.length ? items.map(n => <button key={n.id} type="button" onClick={() => { if (!n.read) readOne.mutate(n.id); if (n.link) { setOpen(false); navigate(n.link) } }} className={cn('flex w-full cursor-pointer gap-3 border-b border-border p-4 text-left transition-colors hover:bg-surface-2', !n.read && 'bg-primary-soft/30')}><Avatar name={n.kind || 'Update'} size="sm" /><span className="min-w-0 flex-1"><span className="flex items-start gap-2"><span className={cn('text-sm', !n.read ? 'font-bold text-primary' : 'font-semibold')}>{n.title}</span>{!n.read && <span className="mt-1.5 ml-auto h-2 w-2 shrink-0 rounded-full bg-cyan" />}</span>{n.body && <span className="mt-1 line-clamp-3 block text-xs leading-relaxed text-muted">{n.body}</span>}<span className="mt-2 flex items-center gap-2 text-[11px] font-medium text-subtle"><span className="rounded-full bg-info-soft px-2 py-0.5 capitalize text-cyan">{n.kind.replace(/_/g, ' ')}</span>{formatDate(n.created_at, { dateStyle: 'medium', timeStyle: 'short' })}</span></span></button>) : <div className="px-6 py-20 text-center"><span className="mx-auto flex h-16 w-16 items-center justify-center rounded-2xl bg-info-soft text-cyan"><Bell className="h-8 w-8" /></span><p className="mt-4 font-display font-bold">All caught up</p><p className="mt-1 text-sm text-muted">{filter === 'unread' ? 'No unread notifications.' : 'Updates from your HR modules will appear here.'}</p></div>}</div>
      </div>
    </SlideOver>
  </>
}
