import * as DialogPrimitive from '@radix-ui/react-dialog'
import { Star, X } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { errorMessage } from '@/lib/api'
import { cn, initials } from '@/lib/utils'
import { Button } from './button'
import { EmptyState, ErrorState, Skeleton } from './card'
import { Dialog, DialogClose, DialogContent, DialogFooter } from './dialog'

/** Underlined tabs for switching between views of one page. */
export function Tabs<T extends string>({ tabs, value, onChange }: { tabs: { id: T; label: string; count?: number }[]; value: T; onChange: (v: T) => void }) {
  if (tabs.length < 2) return null
  return (
    <div role="tablist" className="mb-5 flex gap-1 overflow-x-auto border-b border-border">
      {tabs.map((t) => (
        <button
          key={t.id} role="tab" aria-selected={value === t.id} onClick={() => onChange(t.id)}
          className={cn('-mb-px flex cursor-pointer items-center gap-2 whitespace-nowrap border-b-2 px-3 pb-2.5 pt-1 text-sm font-medium transition-colors',
            value === t.id ? 'border-primary text-primary' : 'border-transparent text-muted hover:text-fg')}
        >
          {t.label}
          {!!t.count && <span className="rounded-full bg-primary-soft px-1.5 text-[11px] font-semibold text-primary">{t.count}</span>}
        </button>
      ))}
    </div>
  )
}

/** Panel that slides in from the right for a secondary list or detail. */
export function SlideOver({ open, onOpenChange, title, children, wide }: { open: boolean; onOpenChange: (o: boolean) => void; title: string; children: React.ReactNode; wide?: boolean }) {
  return (
    <DialogPrimitive.Root open={open} onOpenChange={onOpenChange}>
      <DialogPrimitive.Portal>
        <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-navy/45 backdrop-blur-[2px]" />
        <DialogPrimitive.Content className={cn('fixed inset-y-0 right-0 z-50 flex w-full flex-col border-l border-border bg-surface shadow-pop', wide ? 'max-w-2xl' : 'max-w-xl')}>
          <div className="flex items-center justify-between border-b border-border px-5 py-4">
            <DialogPrimitive.Title className="font-display text-base font-bold">{title}</DialogPrimitive.Title>
            <DialogPrimitive.Close aria-label="Close" className="cursor-pointer rounded-md p-1.5 text-muted hover:bg-surface-2"><X className="h-4 w-4" /></DialogPrimitive.Close>
          </div>
          <DialogPrimitive.Description className="sr-only">{title}</DialogPrimitive.Description>
          <div className="flex-1 overflow-auto p-5">{children}</div>
        </DialogPrimitive.Content>
      </DialogPrimitive.Portal>
    </DialogPrimitive.Root>
  )
}

/** Button that asks for confirmation before running an action. */
export function ConfirmButton({ label, title, message, onConfirm, variant = 'danger-soft', size = 'sm', loading, confirmLabel = 'Confirm' }: {
  label: React.ReactNode; title: string; message: string; onConfirm: () => void; loading?: boolean; confirmLabel?: string
  variant?: 'danger' | 'danger-soft' | 'primary' | 'outline' | 'ghost' | 'soft'; size?: 'sm' | 'md'
}) {
  const [open, setOpen] = React.useState(false)
  const solid = variant === 'danger' || variant === 'danger-soft' ? 'danger' : 'primary'
  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <Button variant={variant} size={size} loading={loading} onClick={() => setOpen(true)}>{label}</Button>
      <DialogContent title={title} description={message}>
        <DialogFooter>
          <DialogClose asChild><Button variant="outline">Cancel</Button></DialogClose>
          <Button variant={solid} onClick={() => { onConfirm(); setOpen(false) }}>{confirmLabel}</Button>
        </DialogFooter>
      </DialogContent>
    </Dialog>
  )
}

const TONE: Record<string, string> = {
  success: 'bg-success-soft text-success', warning: 'bg-warning-soft text-warning', danger: 'bg-danger-soft text-danger',
  info: 'bg-primary-soft text-primary', neutral: 'bg-surface-2 text-muted',
}
const STATUS_TONE: Record<string, keyof typeof TONE> = {
  approved: 'success', accepted: 'success', active: 'success', present: 'success', finalized: 'success', done: 'success', open: 'info', hired: 'success',
  reimbursed: 'success', completed: 'success', achieved: 'success', resolved: 'success', available: 'success', paid: 'success', closed: 'neutral',
  pending: 'warning', probation: 'warning', calculated: 'warning', incomplete: 'warning', in_progress: 'info', submitted: 'warning', requested: 'warning',
  manager_approved: 'info', pending_self: 'warning', pending_manager: 'info', assigned: 'info', due: 'warning', maintenance: 'warning',
  rejected: 'danger', absent: 'danger', terminated: 'danger', suspended: 'danger', overdue: 'danger', dropped: 'neutral', retired: 'neutral',
  leave: 'info', holiday: 'info', weekend: 'neutral', draft: 'neutral', todo: 'neutral', cancelled: 'neutral', resigned: 'neutral', scheduled: 'neutral',
}
const STATUS_LABEL: Record<string, string> = {
  manager_approved: 'Manager approved', pending_self: 'Self-review due', pending_manager: 'With manager', in_progress: 'In progress',
  todo: 'To do', not_checked_in: 'Not checked in',
}
export function StatusText({ status, className }: { status: string; className?: string }) {
  const tone = TONE[STATUS_TONE[status] ?? 'neutral']
  const label = STATUS_LABEL[status] ?? status.replace(/_/g, ' ')
  return (
    <span className={cn('inline-flex items-center gap-1.5 whitespace-nowrap rounded-full px-2 py-0.5 text-xs font-medium capitalize', tone, className)}>
      <span className="h-1.5 w-1.5 rounded-full bg-current" aria-hidden />{label}
    </span>
  )
}

const AVATAR = ['bg-primary-soft text-primary', 'bg-success-soft text-success', 'bg-warning-soft text-warning', 'bg-info-soft text-cyan', 'bg-danger-soft text-danger']
export function Avatar({ name, size = 'md', className }: { name: string; size?: 'sm' | 'md' | 'lg' | 'xl'; className?: string }) {
  const tone = AVATAR[[...name].reduce((a, c) => a + c.charCodeAt(0), 0) % AVATAR.length]
  const dim = { sm: 'h-7 w-7 text-[11px]', md: 'h-9 w-9 text-xs', lg: 'h-12 w-12 text-sm', xl: 'h-16 w-16 text-lg' }[size]
  return <span aria-hidden className={cn('flex shrink-0 items-center justify-center rounded-full font-semibold', dim, tone, className)}>{initials(name) || '?'}</span>
}

export function Person({ name, sub, size = 'md' }: { name: string; sub?: React.ReactNode; size?: 'sm' | 'md' }) {
  return (
    <span className="flex min-w-0 items-center gap-2.5">
      <Avatar name={name} size={size} />
      <span className="min-w-0"><span className="block truncate font-medium text-fg">{name}</span>{sub && <span className="block truncate text-xs text-muted">{sub}</span>}</span>
    </span>
  )
}

const TILE = { primary: 'bg-primary-soft text-primary', teal: 'bg-success-soft text-success', cyan: 'bg-info-soft text-cyan', amber: 'bg-warning-soft text-warning', rose: 'bg-danger-soft text-danger', slate: 'bg-surface-2 text-muted' }
export function StatTile({ icon: Icon, label, value, hint, tone = 'primary', progress }: {
  icon: LucideIcon; label: string; value: React.ReactNode; hint?: React.ReactNode; tone?: keyof typeof TILE; progress?: number
}) {
  return (
    <div className="rounded-xl border border-border bg-surface p-4 shadow-card">
      <div className="flex items-center gap-3">
        <span className={cn('flex h-10 w-10 shrink-0 items-center justify-center rounded-lg', TILE[tone])}><Icon className="h-5 w-5" aria-hidden /></span>
        <div className="min-w-0">
          <p className="truncate text-[13px] text-muted">{label}</p>
          <p className="font-display text-2xl font-bold leading-tight">{value}</p>
        </div>
      </div>
      {progress !== undefined && <Progress value={progress} className="mt-3" />}
      {hint && <p className="mt-2 text-xs text-muted">{hint}</p>}
    </div>
  )
}

export function Progress({ value, className, tone = 'primary' }: { value: number; className?: string; tone?: 'primary' | 'success' | 'warning' }) {
  const v = Math.max(0, Math.min(100, value))
  const bar = { primary: 'brand-gradient', success: 'bg-success', warning: 'bg-warning' }[tone]
  return (
    <div className={cn('h-1.5 overflow-hidden rounded-full bg-surface-2', className)} role="progressbar" aria-valuenow={Math.round(v)} aria-valuemin={0} aria-valuemax={100}>
      <div className={cn('h-full rounded-full', bar)} style={{ width: `${v}%` }} />
    </div>
  )
}

export function Stars({ value, onChange, size = 4 }: { value: number | null; onChange?: (v: number) => void; size?: number }) {
  return (
    <span className="inline-flex gap-0.5" role={onChange ? 'radiogroup' : 'img'} aria-label={`${value ?? 0} out of 5`}>
      {[1, 2, 3, 4, 5].map((n) => {
        const star = <Star className={cn((value ?? 0) >= n ? 'fill-warning text-warning' : 'text-border-strong')} style={{ height: size * 4, width: size * 4 }} aria-hidden />
        return onChange
          ? <button key={n} type="button" role="radio" aria-checked={value === n} aria-label={`${n} of 5`} className="cursor-pointer rounded p-0.5" onClick={() => onChange(n)}>{star}</button>
          : <span key={n}>{star}</span>
      })}
    </span>
  )
}

export function Pager({ page, pageSize, total, onPage }: { page: number; pageSize: number; total: number; onPage: (p: number) => void }) {
  const from = total === 0 ? 0 : (page - 1) * pageSize + 1
  return (
    <div className="flex items-center justify-between border-t border-border px-5 py-3 text-[13px] text-muted">
      <span>{from} to {Math.min(page * pageSize, total)} of {total}</span>
      <div className="flex gap-2">
        <Button variant="outline" size="sm" disabled={page <= 1} onClick={() => onPage(page - 1)}>Previous</Button>
        <Button variant="outline" size="sm" disabled={page * pageSize >= total} onClick={() => onPage(page + 1)}>Next</Button>
      </div>
    </div>
  )
}

export const Th = ({ children, className }: { children?: React.ReactNode; className?: string }) => (
  <th className={cn('whitespace-nowrap bg-surface-2/60 px-4 py-2.5 text-left text-[11px] font-semibold uppercase tracking-wider text-muted first:pl-5 last:pr-5', className)}>{children}</th>
)
export const Td = ({ children, className }: { children?: React.ReactNode; className?: string }) => (
  <td className={cn('px-4 py-3 align-middle text-sm first:pl-5 last:pr-5', className)}>{children}</td>
)

export interface Col<T> { header: string; cell: (row: T) => React.ReactNode; className?: string; right?: boolean }
interface QueryLike { isLoading: boolean; isError: boolean; error: unknown; refetch?: () => unknown }

/** Table with built-in loading, error and empty states. */
export function DataTable<T>({ rows, cols, rowKey, query, empty, emptyHint, emptyIcon, onRowClick }: {
  rows: T[] | undefined; cols: Col<T>[]; rowKey: (row: T) => string; query?: QueryLike
  empty: string; emptyHint?: string; emptyIcon?: LucideIcon; onRowClick?: (row: T) => void
}) {
  if (query?.isLoading) return <div className="space-y-2.5 p-5">{[0, 1, 2, 3].map((i) => <Skeleton key={i} className="h-9 w-full" />)}</div>
  if (query?.isError) return <ErrorState message={errorMessage(query.error)} onRetry={query.refetch ? () => query.refetch?.() : undefined} />
  if (!rows?.length) return <EmptyState title={empty} description={emptyHint} icon={emptyIcon} />
  return (
    <div className="overflow-x-auto">
      <table className="w-full border-collapse">
        <thead><tr className="border-b border-border">{cols.map((c) => <Th key={c.header} className={c.right ? 'text-right' : undefined}>{c.header}</Th>)}</tr></thead>
        <tbody className="divide-y divide-border">
          {rows.map((r) => (
            <tr key={rowKey(r)} tabIndex={onRowClick ? 0 : undefined} onKeyDown={onRowClick ? e => { if (e.target === e.currentTarget && (e.key === 'Enter' || e.key === ' ')) { e.preventDefault(); onRowClick(r) } } : undefined} onClick={onRowClick ? () => onRowClick(r) : undefined} className={cn('transition-colors hover:bg-surface-2/50', onRowClick && 'cursor-pointer')}>
              {cols.map((c) => <Td key={c.header} className={cn(c.right && 'text-right', c.className)}>{c.cell(r)}</Td>)}
            </tr>))}
        </tbody>
      </table>
    </div>
  )
}

/** Label and value rows for detail panels. */
export function Detail({ rows }: { rows: [string, React.ReactNode][] }) {
  return (
    <dl className="divide-y divide-border">
      {rows.map(([k, v]) => (
        <div key={k} className="flex justify-between gap-6 py-2.5 text-sm"><dt className="shrink-0 text-muted">{k}</dt><dd className="min-w-0 text-right font-medium">{v || <span className="font-normal text-subtle">Not set</span>}</dd></div>
      ))}
    </dl>
  )
}

export function downloadCsv(filename: string, rows: (string | number | null | undefined)[][]) {
  const esc = (v: string | number | null | undefined) => {
    let value = String(v ?? '')
    if (typeof v === 'string' && /^[\s]*[=+@\-]/.test(value)) value = "'" + value
    return `"${value.replace(/"/g, '""')}"`
  }
  const blob = new Blob([rows.map((r) => r.map(esc).join(',')).join('\n')], { type: 'text/csv;charset=utf-8' })
  const a = document.createElement('a')
  a.href = URL.createObjectURL(blob)
  a.download = filename
  a.click()
  URL.revokeObjectURL(a.href)
}
