import * as LabelPrimitive from '@radix-ui/react-label'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Label = ({ className, ...p }: React.ComponentProps<typeof LabelPrimitive.Root>) => (
  <LabelPrimitive.Root className={cn('block text-[13px] font-medium text-fg', className)} {...p} />
)

const fieldBase =
  'w-full rounded-lg border border-border-strong bg-surface px-3 text-sm text-fg shadow-sm transition-shadow placeholder:text-subtle focus:border-primary focus:outline-none focus:ring-3 focus:ring-primary/15 disabled:cursor-not-allowed disabled:bg-surface-2 disabled:opacity-70 aria-[invalid=true]:border-danger aria-[invalid=true]:ring-danger/15'

export const Input = React.forwardRef<HTMLInputElement, React.InputHTMLAttributes<HTMLInputElement>>(
  ({ className, ...p }, ref) => <input ref={ref} className={cn(fieldBase, 'h-9', className)} {...p} />,
)
Input.displayName = 'Input'

export const Select = React.forwardRef<HTMLSelectElement, React.SelectHTMLAttributes<HTMLSelectElement>>(
  ({ className, ...p }, ref) => <select ref={ref} className={cn(fieldBase, 'h-9 pr-8', className)} {...p} />,
)
Select.displayName = 'Select'

export const Textarea = React.forwardRef<HTMLTextAreaElement, React.TextareaHTMLAttributes<HTMLTextAreaElement>>(
  ({ className, rows = 4, ...p }, ref) => <textarea ref={ref} rows={rows} className={cn(fieldBase, 'py-2', className)} {...p} />,
)
Textarea.displayName = 'Textarea'

type ControlProps = { id: string; 'aria-invalid': boolean; 'aria-describedby'?: string }

/** Label, control and an inline error or hint, wired with the right aria attributes. */
export function Field({ label, error, hint, children, id, className }: {
  label: string; error?: string; hint?: string; id: string; className?: string; children: (a: ControlProps) => React.ReactNode
}) {
  const describedBy = error ? `${id}-err` : hint ? `${id}-hint` : undefined
  return (
    <div className={cn('space-y-1.5', className)}>
      <Label htmlFor={id}>{label}</Label>
      {children({ id, 'aria-invalid': !!error, 'aria-describedby': describedBy })}
      {error ? (
        <p id={`${id}-err`} role="alert" className="text-xs text-danger">{error}</p>
      ) : hint ? (
        <p id={`${id}-hint`} className="text-xs text-muted">{hint}</p>
      ) : null}
    </div>
  )
}

export function Checkbox({ label, hint, ...p }: React.InputHTMLAttributes<HTMLInputElement> & { label: React.ReactNode; hint?: string }) {
  return (
    <label className="flex cursor-pointer items-start gap-2.5 text-sm">
      <input type="checkbox" className="mt-0.5 h-4 w-4 rounded border-border-strong accent-[var(--color-primary)]" {...p} />
      <span>{label}{hint && <span className="block text-xs text-muted">{hint}</span>}</span>
    </label>
  )
}
