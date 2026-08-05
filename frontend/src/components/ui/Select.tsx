import { type SelectHTMLAttributes, useId } from 'react'
import { cn } from '@/lib/utils'

interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label: string
  options: ReadonlyArray<{ value: string | number; label: string }>
}

export function Select({ label, options, className, id, ...props }: SelectProps) {
  const generatedId = useId()
  const selectId = id ?? generatedId

  return (
    <div className="flex flex-col gap-2">
      <label htmlFor={selectId} className="text-xs font-medium tracking-wide text-ink-soft">
        {label}
      </label>
      <select
        {...props}
        id={selectId}
        className={cn(
          'h-11 appearance-none border-b border-line-strong bg-transparent pr-6 text-[15px]',
          'text-ink transition-colors focus:border-accent focus:outline-none',
          className,
        )}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
    </div>
  )
}
