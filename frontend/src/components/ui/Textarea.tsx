import { type TextareaHTMLAttributes, useId } from 'react'
import { cn } from '@/lib/utils'

interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label: string
  hint?: string
}

export function Textarea({ label, hint, className, id, ...props }: TextareaProps) {
  const generatedId = useId()
  const textareaId = id ?? generatedId
  const hintId = hint ? `${textareaId}-hint` : undefined

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={textareaId} className="text-xs font-medium tracking-wide text-ink-soft">
        {label}
      </label>
      <textarea
        {...props}
        id={textareaId}
        aria-describedby={hintId}
        className={cn(
          'border border-line-strong bg-surface p-4 text-[15px] leading-relaxed text-ink',
          'placeholder:text-ink-muted/60 focus:border-accent focus:outline-none',
          'resize-y transition-colors',
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
