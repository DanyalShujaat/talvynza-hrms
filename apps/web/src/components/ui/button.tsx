import { Slot } from '@radix-ui/react-slot'
import { cva, type VariantProps } from 'class-variance-authority'
import { Loader2 } from 'lucide-react'
import * as React from 'react'
import { cn } from '@/lib/utils'

const variants = cva(
  'inline-flex shrink-0 cursor-pointer items-center justify-center gap-2 whitespace-nowrap rounded-lg font-medium transition-colors disabled:pointer-events-none disabled:opacity-50',
  {
    variants: {
      variant: {
        primary: 'bg-primary text-white shadow-sm hover:bg-primary-hover dark:text-navy',
        soft: 'bg-primary-soft text-primary hover:bg-primary/15',
        secondary: 'bg-surface-2 text-fg hover:bg-border',
        outline: 'border border-border-strong bg-surface text-fg shadow-sm hover:bg-surface-2',
        ghost: 'text-muted hover:bg-surface-2 hover:text-fg',
        danger: 'bg-danger text-white shadow-sm hover:opacity-90 dark:text-navy',
        'danger-soft': 'bg-danger-soft text-danger hover:bg-danger/15',
      },
      size: { sm: 'h-8 px-3 text-[13px]', md: 'h-9 px-3.5 text-sm', lg: 'h-10 px-4 text-sm', icon: 'h-9 w-9' },
    },
    defaultVariants: { variant: 'primary', size: 'md' },
  },
)

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement>, VariantProps<typeof variants> {
  asChild?: boolean
  loading?: boolean
}

export const Button = React.forwardRef<HTMLButtonElement, ButtonProps>(
  ({ className, variant, size, asChild, loading, children, disabled, ...props }, ref) => {
    const Comp = asChild ? Slot : 'button'
    return (
      <Comp ref={ref} className={cn(variants({ variant, size }), className)} disabled={disabled || loading} {...props}>
        {asChild ? children : (
          <>
            {loading && <Loader2 className="h-4 w-4 animate-spin" aria-hidden />}
            {children}
          </>
        )}
      </Comp>
    )
  },
)
Button.displayName = 'Button'
