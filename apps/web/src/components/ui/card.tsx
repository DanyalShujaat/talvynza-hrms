import { AlertTriangle, CircleHelp, Inbox } from 'lucide-react'
import type { LucideIcon } from 'lucide-react'
import * as React from 'react'
import { useLocation } from 'react-router-dom'
import { guideFor } from '@/components/layout/guides'
import { cn } from '@/lib/utils'
import { Button } from './button'

export const Card = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('rounded-xl border border-border bg-surface shadow-card', className)} {...p} />
)
export const CardHeader = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('flex min-h-14 flex-wrap items-center justify-between gap-3 border-b border-border px-5 py-3', className)} {...p} />
)
export const CardTitle = ({ className, ...p }: React.HTMLAttributes<HTMLHeadingElement>) => (
  <h2 className={cn('text-[15px] font-semibold', className)} {...p} />
)
export const CardBody = ({ className, ...p }: React.HTMLAttributes<HTMLDivElement>) => (
  <div className={cn('p-5', className)} {...p} />
)

const tones = {
  neutral: 'bg-surface-2 text-muted',
  primary: 'bg-primary-soft text-primary',
  success: 'bg-success-soft text-success',
  warning: 'bg-warning-soft text-warning',
  danger: 'bg-danger-soft text-danger',
  info: 'bg-info-soft text-cyan',
}
export type Tone = keyof typeof tones
export const Badge = ({ tone = 'neutral', className, ...p }: React.HTMLAttributes<HTMLSpanElement> & { tone?: Tone }) => (
  <span className={cn('inline-flex items-center gap-1 rounded-md px-2 py-0.5 text-xs font-medium', tones[tone], className)} {...p} />
)

export const Skeleton = ({ className }: { className?: string }) => (
  <div aria-hidden className={cn('animate-pulse rounded-md bg-surface-2', className)} />
)

export function EmptyState({ title, description, action, icon: Icon = Inbox }: {
  title: string; description?: string; action?: React.ReactNode; icon?: LucideIcon
}) {
  return (
    <div className="flex flex-col items-center gap-1.5 px-6 py-14 text-center">
      <span className="mb-2 flex h-12 w-12 items-center justify-center rounded-full bg-surface-2 text-subtle"><Icon className="h-5 w-5" aria-hidden /></span>
      <p className="font-semibold">{title}</p>
      {description && <p className="max-w-sm text-sm text-muted">{description}</p>}
      {action && <div className="mt-3">{action}</div>}
    </div>
  )
}

export function ErrorState({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <div role="alert" className="flex flex-col items-center gap-2 px-6 py-12 text-center">
      <span className="flex h-12 w-12 items-center justify-center rounded-full bg-danger-soft text-danger"><AlertTriangle className="h-5 w-5" aria-hidden /></span>
      <p className="max-w-md text-sm">{message}</p>
      {onRetry && <Button variant="outline" size="sm" onClick={onRetry}>Try again</Button>}
    </div>
  )
}

export function PageHeader({ title, description, actions }: { title: string; description?: React.ReactNode; actions?: React.ReactNode }) {
  const { pathname } = useLocation()
  const guide = guideFor(pathname)
  const [showHelp, setShowHelp] = React.useState(false)
  return (
    <div data-tour="page-header" className="mb-6 flex flex-wrap items-start justify-between gap-x-4 gap-y-3">
      <div className="min-w-0">
        <div className="flex items-center gap-2"><h1 className="text-[22px] font-bold leading-tight tracking-tight">{title}</h1>{guide && <button aria-label={`About ${title}`} aria-expanded={showHelp} title={`What can I do in ${title}?`} onClick={() => setShowHelp(!showHelp)} className="rounded-full p-1 text-muted hover:bg-primary-soft hover:text-primary"><CircleHelp className="h-4 w-4" /></button>}</div>
        {description && <p className="mt-1 text-sm text-muted">{description}</p>}
        {showHelp && guide && <div className="mt-3 max-w-xl rounded-lg border border-primary/20 bg-primary-soft p-3 text-sm"><p>{guide.intro}</p><ul className="mt-2 list-disc space-y-1 pl-5">{guide.steps.map(step => <li key={step.title}><strong>{step.title}:</strong> {step.body}</li>)}</ul></div>}
      </div>
      {actions && <div data-tour="page-actions" className="flex flex-wrap items-center gap-2">{actions}</div>}
    </div>
  )
}

/** Inline notice banner. */
export function Notice({ tone = 'info', children, icon: Icon }: { tone?: 'info' | 'warning' | 'danger' | 'success'; children: React.ReactNode; icon?: LucideIcon }) {
  const cls = { info: 'border-primary/20 bg-primary-soft text-fg', warning: 'border-warning/25 bg-warning-soft text-fg', danger: 'border-danger/25 bg-danger-soft text-fg', success: 'border-success/25 bg-success-soft text-fg' }[tone]
  return (
    <div className={cn('flex items-start gap-3 rounded-xl border px-4 py-3 text-sm', cls)}>
      {Icon && <Icon className="mt-0.5 h-4 w-4 shrink-0 opacity-80" aria-hidden />}
      <div className="min-w-0">{children}</div>
    </div>
  )
}
