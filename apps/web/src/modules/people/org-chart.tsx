import { ChevronDown, ChevronRight, Network, Pencil } from 'lucide-react'
import * as React from 'react'
import { Link } from 'react-router-dom'
import { toast } from 'sonner'
import { Button } from '@/components/ui/button'
import { Card, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Avatar } from '@/components/ui/extras'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { useMe } from '@/lib/queries'
import { cn } from '@/lib/utils'

interface Node { id: string; name: string; designation: string | null; department: string | null; manager_id: string | null }

function Branch({ node, kids, depth, onEdit }: { node: Node; kids: Map<string | null, Node[]>; depth: number; onEdit?: (node: Node) => void }) {
  const children = kids.get(node.id) ?? []
  const [open, setOpen] = React.useState(depth < 2)
  return (
    <li>
      <div className="flex items-center gap-2 py-1.5">
        {children.length > 0
          ? <button onClick={() => setOpen(!open)} aria-expanded={open} aria-label={open ? `Collapse ${node.name}` : `Expand ${node.name}`} className="flex h-6 w-6 cursor-pointer items-center justify-center rounded text-muted hover:bg-surface-2">{open ? <ChevronDown className="h-4 w-4" /> : <ChevronRight className="h-4 w-4" />}</button>
          : <span className="w-6" />}
        <Link to={`/employees/${node.id}`} className="flex min-w-0 flex-1 items-center gap-3 rounded-xl border border-border bg-surface px-3 py-2 shadow-card transition-colors hover:border-primary/40 sm:max-w-sm">
          <Avatar name={node.name} size="md" />
          <span className="min-w-0"><span className="block truncate text-sm font-semibold">{node.name}</span><span className="block truncate text-xs text-muted">{[node.designation, node.department].filter(Boolean).join(' · ') || 'No designation'}</span></span>
          {children.length > 0 && <span className="ml-auto shrink-0 rounded-full bg-primary-soft px-2 py-0.5 text-[11px] font-semibold text-primary">{children.length}</span>}
        </Link>
        {onEdit && <Button variant="ghost" size="icon" aria-label={`Change reporting manager for ${node.name}`} title="Change reporting manager" onClick={() => onEdit(node)}><Pencil className="h-4 w-4" /></Button>}
      </div>
      {open && children.length > 0 && (
        <ul className={cn('ml-3 border-l border-border-strong pl-5')}>{children.map((c) => <Branch key={c.id} node={c} kids={kids} depth={depth + 1} onEdit={onEdit} />)}</ul>)}
    </li>
  )
}

export function OrgChartPage() {
  const q = useGet<Node[]>('/org-chart')
  const { data: me } = useMe()
  const [editing, setEditing] = React.useState<Node | null>(null)
  const [managerId, setManagerId] = React.useState('')
  const save = useSend<{ manager_id: string | null }>('PATCH', `/employees/${editing?.id}`, { invalidate: ['/org-chart', '/employees'], success: 'Reporting manager updated', onSuccess: () => setEditing(null) })
  const edit = (node: Node) => { setEditing(node); setManagerId(node.manager_id ?? '') }
  const { roots, kids } = React.useMemo(() => {
    const nodes = q.data ?? []
    const ids = new Set(nodes.map((n) => n.id))
    const kids = new Map<string | null, Node[]>()
    for (const n of nodes) { const key = n.manager_id && ids.has(n.manager_id) ? n.manager_id : null; kids.set(key, [...(kids.get(key) ?? []), n]) }
    for (const list of kids.values()) list.sort((a, b) => a.name.localeCompare(b.name))
    return { roots: kids.get(null) ?? [], kids }
  }, [q.data])
  return (
    <>
      <PageHeader title="Org chart" description="See reporting lines and update a manager directly from the chart." />
      {q.isLoading ? <Skeleton className="h-64 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} /></Card>
        : roots.length === 0 ? <Card><EmptyState title="No employees yet" icon={Network} /></Card>
        : <ul>{roots.map((r) => <Branch key={r.id} node={r} kids={kids} depth={0} onEdit={me?.permissions.includes('employees.manage') ? edit : undefined} />)}</ul>}
      {editing && <div className="fixed inset-0 z-50 flex items-center justify-center bg-navy/45 p-4" role="presentation" onMouseDown={(e) => { if (e.target === e.currentTarget) setEditing(null) }}><div role="dialog" aria-modal="true" aria-label="Change reporting manager" className="w-full max-w-md rounded-xl bg-surface p-6 shadow-pop"><h2 className="text-lg font-bold">Reporting manager for {editing.name}</h2><p className="mt-1 text-sm text-muted">Changing this line also updates the employee profile.</p><label htmlFor="org-manager" className="mt-5 block text-sm font-medium">Manager</label><select id="org-manager" className="mt-1 h-10 w-full rounded-lg border border-border bg-surface px-3" value={managerId} onChange={e => setManagerId(e.target.value)}><option value="">No manager</option>{(q.data ?? []).filter(n => n.id !== editing.id).map(n => <option key={n.id} value={n.id}>{n.name}</option>)}</select><div className="mt-5 flex justify-end gap-2"><Button variant="outline" onClick={() => setEditing(null)}>Cancel</Button><Button loading={save.isPending} onClick={() => { const descendants = new Set<string>(); const visit = (id: string) => { for (const child of kids.get(id) ?? []) { descendants.add(child.id); visit(child.id) } }; visit(editing.id); if (descendants.has(managerId)) { toast.error('A person cannot report to someone below them in the chart'); return } save.mutate({ manager_id: managerId || null }) }}>Save manager</Button></div></div></div>}
    </>
  )
}
