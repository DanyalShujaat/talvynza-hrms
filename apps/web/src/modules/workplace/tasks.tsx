import { useRecordFocus, useViewQuery } from '@/lib/view-state'
import { AlertCircle, CalendarDays, CircleCheck, CircleDashed, Clock3, GripVertical, ListChecks, Plus, Search, Trash2 } from 'lucide-react'
import * as React from 'react'
import { Button } from '@/components/ui/button'
import { Badge, Card, EmptyState, ErrorState, PageHeader, Skeleton } from '@/components/ui/card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from '@/components/ui/dialog'
import { Avatar, ConfirmButton } from '@/components/ui/extras'
import { Field, Input, Select, Textarea } from '@/components/ui/form'
import { errorMessage } from '@/lib/api'
import { useGet, useSend } from '@/lib/hooks'
import { cn, formatDate } from '@/lib/utils'
import { Opts, type EmpRow } from '@/modules/people/employees'

type Status = 'todo' | 'in_progress' | 'blocked' | 'done'
interface Task { id: string; title: string; description: string | null; assignee_id: string; assignee: string | null; due_date: string | null; status: Status; priority: 'low' | 'normal' | 'high'; overdue: boolean }
const COLUMNS = [
  { id: 'todo', label: 'To do', icon: CircleDashed, tone: 'text-muted', surface: 'bg-surface-2/70', border: 'border-border-strong' },
  { id: 'in_progress', label: 'In progress', icon: Clock3, tone: 'text-primary', surface: 'bg-primary-soft/55', border: 'border-primary/30' },
  { id: 'blocked', label: 'Blocked', icon: AlertCircle, tone: 'text-warning', surface: 'bg-warning-soft/65', border: 'border-warning/35' },
  { id: 'done', label: 'Done', icon: CircleCheck, tone: 'text-success', surface: 'bg-success-soft/55', border: 'border-success/30' },
] as const
const blank = { title: '', description: '', assignee_id: '', due_date: '', priority: 'normal' }

function TaskForm({ task, canAssign, onClose }: { task?: Task; canAssign: boolean; onClose: () => void }) {
  const [form, setForm] = React.useState(() => task ? { title: task.title, description: task.description || '', assignee_id: task.assignee_id, due_date: task.due_date || '', priority: task.priority } : blank)
  const people = useGet<{ items: EmpRow[] }>('/employees', { status: 'active', page_size: 100 }, canAssign)
  const save = useSend<Record<string, unknown>>(task ? 'PATCH' : 'POST', task ? `/tasks/${task.id}` : '/tasks', { invalidate: ['/tasks', '/dashboard'], success: task ? 'Task updated' : 'Task created', onSuccess: onClose })
  return <div className="space-y-4">
    <Field id="task-title" label="Title">{a => <Input value={form.title} onChange={e => setForm({ ...form, title: e.target.value })} {...a} />}</Field>
    <Field id="task-description" label="Details (optional)">{a => <Textarea rows={4} value={form.description} onChange={e => setForm({ ...form, description: e.target.value })} {...a} />}</Field>
    {canAssign && <Field id="task-assignee" label="Assign to">{a => <Select value={form.assignee_id} onChange={e => setForm({ ...form, assignee_id: e.target.value })} {...a}><Opts list={(people.data?.items || []).map(p => ({ id: p.id, name: p.full_name }))} blank={task ? 'Select an employee' : 'Myself'} /></Select>}</Field>}
    <div className="grid grid-cols-2 gap-3"><Field id="task-due" label="Due date">{a => <Input type="date" value={form.due_date} onChange={e => setForm({ ...form, due_date: e.target.value })} {...a} />}</Field><Field id="task-priority" label="Priority">{a => <Select value={form.priority} onChange={e => setForm({ ...form, priority: e.target.value as Task['priority'] })} {...a}><option value="low">Low</option><option value="normal">Normal</option><option value="high">High</option></Select>}</Field></div>
    <DialogFooter><DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose><Button loading={save.isPending} disabled={form.title.trim().length < 2 || !!(task && canAssign && !form.assignee_id)} onClick={() => save.mutate({ title: form.title.trim(), description: form.description || null, ...(canAssign && form.assignee_id ? { assignee_id: form.assignee_id } : {}), due_date: form.due_date || null, priority: form.priority })}>{task ? 'Save changes' : 'Create task'}</Button></DialogFooter>
  </div>
}

function TaskCard({ task, selected, canAssign, onMove }: { task: Task; selected: boolean; canAssign: boolean; onMove: (id: string, status: Status) => void }) {
  const [editing, setEditing] = React.useState(false)
  const focusTask = useRecordFocus(selected ? task.id : null)
  const del = useSend<string>('DELETE', id => `/tasks/${id}`, { invalidate: ['/tasks', '/dashboard'], success: 'Task deleted' })
  return <article ref={selected ? focusTask : undefined} tabIndex={selected ? -1 : undefined} draggable onDragStart={event => { event.dataTransfer.setData('text/plain', task.id); event.dataTransfer.effectAllowed = 'move' }} className={cn('group scroll-mt-28 rounded-xl border bg-surface p-3.5 shadow-card transition-shadow hover:shadow-pop', selected ? 'border-primary ring-2 ring-primary/30' : 'border-border')} aria-label={task.title}>
    <div className="flex items-start gap-1"><GripVertical className="mt-0.5 h-4 w-4 shrink-0 cursor-grab text-subtle" aria-hidden /><button type="button" className="min-w-0 flex-1 cursor-pointer text-left text-sm font-semibold leading-snug hover:text-primary" onClick={() => setEditing(true)}>{task.title}</button>{task.priority === 'high' && <Badge tone="danger">High</Badge>}{task.priority === 'low' && <Badge tone="neutral">Low</Badge>}</div>
    {task.description && <p className="mt-2 line-clamp-2 pl-5 text-xs leading-relaxed text-muted">{task.description}</p>}
    <div className="mt-3 flex items-center gap-2 border-t border-border pt-3">{task.assignee && <><Avatar name={task.assignee} size="sm" /><span className="min-w-0 flex-1 truncate text-xs text-muted">{task.assignee}</span></>}{task.due_date && <span className={cn('ml-auto flex shrink-0 items-center gap-1 text-[11px]', task.overdue ? 'font-bold text-danger' : 'text-muted')}><CalendarDays className="h-3.5 w-3.5" />{formatDate(task.due_date, { month: 'short', day: 'numeric' })}</span>}</div>
    <div className="mt-3 flex items-center justify-between gap-2"><Select aria-label="Status" className="h-8 min-w-0 text-xs" value={task.status} onChange={e => onMove(task.id, e.target.value as Status)}>{COLUMNS.map(c => <option key={c.id} value={c.id}>{c.label}</option>)}</Select><ConfirmButton variant="ghost" label={<Trash2 className="h-4 w-4" />} title="Delete this task?" message={`“${task.title}” will be removed.`} confirmLabel="Delete" onConfirm={() => del.mutate(task.id)} /></div>
    <Dialog open={editing} onOpenChange={setEditing}><DialogContent title="Task details" description="Update the task and its assignee."><TaskForm task={task} canAssign={canAssign} onClose={() => setEditing(false)} /></DialogContent></Dialog>
  </article>
}

function Board({ scope }: { scope: 'mine' | 'team' }) {
  const [params, update] = useViewQuery()
  const search = params.get('q') ?? ''
  const priority = params.get('priority') ?? 'all'
  const [creating, setCreating] = React.useState(false)
  const [target, setTarget] = React.useState<Status | null>(null)
  const q = useGet<Task[]>('/tasks', { scope })
  const move = useSend<{ id: string; status: Status }>('PATCH', b => `/tasks/${b.id}`, { invalidate: ['/tasks', '/dashboard'], success: 'Task moved' })
  const rows = (q.data || []).filter(t => `${t.title} ${t.description || ''} ${t.assignee || ''}`.toLowerCase().includes(search.toLowerCase())).filter(t => priority === 'all' || t.priority === priority)
  const moveTo = (id: string, status: Status) => { const task = q.data?.find(t => t.id === id); if (task && task.status !== status) move.mutate({ id, status }) }
  return <>
    <PageHeader title={scope === 'mine' ? 'My tasks' : 'Team tasks'} description="Drag cards between columns to keep work moving. Open a card to edit its details." actions={<Button onClick={() => setCreating(true)}><Plus className="h-4 w-4" />New task</Button>} />
    <div className="mb-5 flex flex-wrap items-center gap-2"><div className="relative min-w-52 flex-1 sm:max-w-sm"><Search className="absolute left-3 top-2.5 h-4 w-4 text-subtle" /><Input aria-label="Search tasks" placeholder="Search tasks or people" className="pl-9" value={search} onChange={e => update({ q: e.target.value, record: null })} /></div><Select aria-label="Filter priority" className="w-40" value={priority} onChange={e => update({ priority: e.target.value, record: null })}><option value="all">All priorities</option><option value="high">High priority</option><option value="normal">Normal priority</option><option value="low">Low priority</option></Select><span className="ml-auto text-xs text-muted">{rows.length} tasks</span></div>
    {q.isLoading ? <Skeleton className="h-72 w-full rounded-xl" /> : q.isError ? <Card><ErrorState message={errorMessage(q.error)} onRetry={() => q.refetch()} /></Card> : <div data-tour="primary-content" className="grid items-start gap-4 md:grid-cols-2 xl:grid-cols-4">{COLUMNS.map(col => { const items = rows.filter(t => t.status === col.id); const Icon = col.icon; return <section key={col.id} aria-label={col.label} onDragOver={e => { e.preventDefault(); e.dataTransfer.dropEffect = 'move'; setTarget(col.id) }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setTarget(null) }} onDrop={e => { e.preventDefault(); const id = e.dataTransfer.getData('text/plain'); setTarget(null); if (id) moveTo(id, col.id) }} className={cn('min-h-[300px] rounded-2xl border p-3 transition-all', col.surface, target === col.id ? 'border-primary ring-2 ring-primary/20' : col.border)}><h2 className={cn('mb-3 flex items-center gap-2 rounded-xl bg-surface px-3 py-2.5 font-display text-sm font-bold shadow-card', col.tone)}><Icon className="h-4 w-4" />{col.label}<span className="ml-auto rounded-full bg-surface-2 px-2 py-0.5 text-xs text-muted">{items.length}</span></h2><div className="space-y-2.5">{items.map(task => <TaskCard key={task.id} task={task} selected={task.id === params.get('record')} canAssign={scope === 'team'} onMove={moveTo} />)}{items.length === 0 && <div className="rounded-xl border border-dashed border-border-strong bg-surface/60 p-6 text-center text-xs text-muted">Drop a task here</div>}</div></section> })}</div>}
    {!q.isLoading && !q.isError && !q.data?.length && <div className="mt-4"><Card><EmptyState title="No tasks yet" description="Create a task to get your board started." icon={ListChecks} /></Card></div>}
    <Dialog open={creating} onOpenChange={setCreating}><DialogContent title="New task" description={scope === 'team' ? 'Assign a task and notify its owner.' : 'Add work to your board.'}><TaskForm canAssign={scope === 'team'} onClose={() => setCreating(false)} /></DialogContent></Dialog>
  </>
}

export function MyTasksPage() { return <Board scope="mine" /> }
export function TasksPage() { return <Board scope="team" /> }
