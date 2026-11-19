import * as DropdownMenu from '@radix-ui/react-dropdown-menu'
import * as React from 'react'
import { cn } from '@/lib/utils'

export const Menu = DropdownMenu.Root
export const MenuTrigger = DropdownMenu.Trigger
export const MenuSeparator = () => <DropdownMenu.Separator className="my-1 h-px bg-border" />
export const MenuLabel = ({ className, ...p }: React.ComponentProps<typeof DropdownMenu.Label>) => (
  <DropdownMenu.Label className={cn('px-2.5 py-1.5 text-[11px] font-semibold uppercase tracking-wide text-subtle', className)} {...p} />
)
export const MenuContent = ({ className, align = 'end', ...p }: React.ComponentProps<typeof DropdownMenu.Content>) => (
  <DropdownMenu.Portal>
    <DropdownMenu.Content
      align={align}
      sideOffset={8}
      className={cn('z-50 min-w-52 rounded-xl border border-border bg-surface p-1.5 text-sm shadow-pop', className)}
      {...p}
    />
  </DropdownMenu.Portal>
)
export const MenuItem = ({ className, ...p }: React.ComponentProps<typeof DropdownMenu.Item>) => (
  <DropdownMenu.Item
    className={cn('flex cursor-pointer items-center gap-2.5 rounded-lg px-2.5 py-2 outline-none data-[disabled]:pointer-events-none data-[highlighted]:bg-surface-2 data-[disabled]:opacity-50', className)}
    {...p}
  />
)
