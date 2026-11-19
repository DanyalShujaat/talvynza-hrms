import * as DialogPrimitive from '@radix-ui/react-dialog'
import { X } from 'lucide-react'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Dialog = DialogPrimitive.Root
export const DialogTrigger = DialogPrimitive.Trigger
export const DialogClose = DialogPrimitive.Close

export function DialogContent({ title, description, children, className }: { title: string; description?: string; children: React.ReactNode; className?: string }) {
  return (
    <DialogPrimitive.Portal>
      <DialogPrimitive.Overlay className="fixed inset-0 z-50 bg-navy/45 backdrop-blur-[2px]" />
      <DialogPrimitive.Content
        className={cn('fixed left-1/2 top-1/2 z-50 max-h-[92vh] w-[calc(100vw-2rem)] max-w-lg -translate-x-1/2 -translate-y-1/2 overflow-y-auto rounded-2xl border border-border bg-surface p-6 shadow-pop', className)}
      >
        <DialogPrimitive.Title className="pr-8 font-display text-lg font-bold">{title}</DialogPrimitive.Title>
        <DialogPrimitive.Description className={cn('mt-1 text-sm text-muted', !description && 'sr-only')}>
          {description ?? title}
        </DialogPrimitive.Description>
        <div className="mt-5">{children}</div>
        <DialogPrimitive.Close className="absolute right-4 top-4 cursor-pointer rounded-md p-1.5 text-muted hover:bg-surface-2 hover:text-fg" aria-label="Close">
          <X className="h-4 w-4" />
        </DialogPrimitive.Close>
      </DialogPrimitive.Content>
    </DialogPrimitive.Portal>
  )
}

export const DialogFooter = ({ children }: { children: React.ReactNode }) => (
  <div className="mt-6 flex flex-wrap justify-end gap-2">{children}</div>
)
