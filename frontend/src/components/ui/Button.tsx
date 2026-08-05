import type { ButtonHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

type Variant = 'primary' | 'accent' | 'ghost'

const VARIANT_STYLE: Record<Variant, string> = {
  primary:
    'bg-ink text-canvas hover:bg-accent disabled:hover:bg-ink shadow-[0_1px_0_0_rgba(0,0,0,0.04)]',
  accent: 'bg-accent text-canvas hover:bg-ink disabled:hover:bg-accent',
  ghost: 'text-ink-soft hover:text-accent',
}

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
}

export function Button({ variant = 'primary', className, ...props }: ButtonProps) {
  return (
    <button
      {...props}
      className={cn(
        'inline-flex h-11 items-center justify-center gap-2 px-5 text-sm font-medium',
        'transition-colors duration-150 disabled:cursor-not-allowed disabled:opacity-45',
        VARIANT_STYLE[variant],
        className,
      )}
    />
  )
}
