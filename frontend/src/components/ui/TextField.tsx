import { type InputHTMLAttributes, useId } from 'react'
import { cn } from '@/lib/utils'

interface TextFieldProps extends InputHTMLAttributes<HTMLInputElement> {
  label: string
  hint?: string
}

export function TextField({ label, hint, className, id, ...props }: TextFieldProps) {
  const generatedId = useId()
  const inputId = id ?? generatedId
  const hintId = hint ? `${inputId}-hint` : undefined

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={inputId} className="text-xs font-medium tracking-wide text-ink-soft">
        {label}
      </label>
      <input
        {...props}
        id={inputId}
        aria-describedby={hintId}
        className={cn(
          'h-11 border-b border-line-strong bg-transparent text-[15px] text-ink',
          'placeholder:text-ink-muted/60 focus:border-accent focus:outline-none',
          'transition-colors duration-150',
          className,
        )}
      />
      {hint && (
        <span id={hintId} className="text-xs text-ink-muted">
          {hint}
        </span>
      )}
    </div>
  )
}
