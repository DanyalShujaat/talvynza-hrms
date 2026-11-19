import * as DialogPrimitive from '@radix-ui/react-dialog'
import { CornerDownLeft, Search } from 'lucide-react'
import * as React from 'react'
import { useNavigate } from 'react-router-dom'
import { Avatar } from '@/components/ui/extras'
import { useGet } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn } from '@/lib/utils'
import { ADMIN, MY_SPACE, visibleGroups } from './nav'

interface Hit { key: string; label: string; sub: string; to: string; icon?: React.ReactNode }

/** Ctrl+K search over the pages this person can open and, for HR and managers, the people they can see. */
export function CommandPalette({ open, onOpenChange }: { open: boolean; onOpenChange: (o: boolean) => void }) {
  const nav = useNavigate()
  const { data: me } = useMe()
  const [q, setQ] = React.useState('')
  const [debounced, setDebounced] = React.useState('')
  const [index, setIndex] = React.useState(0)
  React.useEffect(() => { const t = setTimeout(() => setDebounced(q.trim()), 200); return () => clearTimeout(t) }, [q])
  React.useEffect(() => { if (open) { setQ(''); setIndex(0) } }, [open])

  const perms = React.useMemo(() => new Set(me?.permissions ?? []), [me])
  const canSearchPeople = perms.has('employees.read') || perms.has('employees.read_team')
  const people = useGet<{ items: { id: string; full_name: string; employee_code: string; designation: string | null; department: string | null }[] }>(
    '/employees', { q: debounced, status: 'active', page_size: 6 }, open && canSearchPeople && debounced.length >= 2)

  const pages: Hit[] = React.useMemo(() => {
    const groups = [...(me?.employee ? MY_SPACE.map((g) => ({ ...g, label: 'My Space' })) : []), ...visibleGroups(ADMIN, perms).map((g) => ({ ...g, label: 'Admin' }))]
    return groups.flatMap((g) => g.items.map((i) => ({ key: i.to, label: i.label, sub: g.label, to: i.to, icon: <i.icon className="h-4 w-4" aria-hidden /> })))
  }, [me, perms])

  const term = q.trim().toLowerCase()
  const hits: Hit[] = [
    ...pages.filter((p) => !term || p.label.toLowerCase().includes(term)).slice(0, term ? 8 : 7),
    ...(people.data?.items ?? []).map((e) => ({ key: e.id, label: e.full_name, sub: [e.designation, e.department, e.employee_code].filter(Boolean).join(' · '), to: `/employees/${e.id}`, icon: <Avatar name={e.full_name} size="sm" /> })),
  ]
  const go = (h: Hit | undefined) => { if (h) { onOpenChange(false); nav(h.to) } }

  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-navy/45 backdrop-blur-[2px]" />
        <DialogPrimitive.Content className="fixed left-1/2 top-[14vh] z-50 w-[calc(100vw-2rem)] max-w-xl -translate-x-1/2 overflow-hidden rounded-2xl border border-border bg-surface shadow-pop">
          <DialogPrimitive.Title className="sr-only">Search</DialogPrimitive.Title>
          <DialogPrimitive.Description className="sr-only">Search pages and people</DialogPrimitive.Description>
          <div className="flex items-center gap-3 border-b border-border px-4">
            <Search className="h-4 w-4 text-subtle" aria-hidden />
            <input autoFocus value={q} onChange={(e) => { setQ(e.target.value); setIndex(0) }} placeholder={canSearchPeople ? 'Search pages and people' : 'Search pages'} aria-label="Search"
              className="h-12 flex-1 bg-transparent text-sm outline-none placeholder:text-subtle"
              onKeyDown={(e) => {
                if (e.key === 'ArrowDown') { e.preventDefault(); setIndex((i) => Math.min(i + 1, hits.length - 1)) }
                if (e.key === 'ArrowUp') { e.preventDefault(); setIndex((i) => Math.max(i - 1, 0)) }
                if (e.key === 'Enter') go(hits[index])
              }} />
          </div>
          <ul className="max-h-80 overflow-auto p-1.5" role="listbox">
            {hits.length === 0 && <li className="px-3 py-8 text-center text-sm text-muted">No matches</li>}
            {hits.map((h, i) => (
              <li key={h.key} role="option" aria-selected={i === index}>
                <button onClick={() => go(h)} onMouseEnter={() => setIndex(i)} className={cn('flex w-full cursor-pointer items-center gap-3 rounded-lg px-3 py-2 text-left text-sm', i === index && 'bg-surface-2')}>
                  <span className="flex h-7 w-7 shrink-0 items-center justify-center text-muted">{h.icon}</span>
                  <span className="min-w-0 flex-1"><span className="block truncate font-medium">{h.label}</span><span className="block truncate text-xs text-muted">{h.sub}</span></span>
                  {i === index && <CornerDownLeft className="h-3.5 w-3.5 text-subtle" aria-hidden />}
                </button>
              </li>
            ))}
          </ul>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}
