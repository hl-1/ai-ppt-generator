import { ChevronDown } from 'lucide-react'
import type { SelectHTMLAttributes } from 'react'
import { cn } from '@/lib/utils'

interface PillSelectProps extends Omit<SelectHTMLAttributes<HTMLSelectElement>, 'children'> {
  label: string
  options: ReadonlyArray<{ value: string | number; label: string }>
}

/** 参数胶囊：与输入框同屏可见、随时可改，不进设置页 */
export function PillSelect({ label, options, className, ...props }: PillSelectProps) {
  return (
    <div className="relative">
      <select
        {...props}
        aria-label={label}
        className={cn(
          'h-9 appearance-none rounded-full border border-line bg-surface pr-8 pl-3.5',
          'text-[13px] font-medium text-ink-soft transition-colors',
          'hover:border-line-strong focus:border-accent focus:outline-none',
          'disabled:cursor-not-allowed disabled:opacity-50',
          className,
        )}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      <ChevronDown className="pointer-events-none absolute top-1/2 right-3 size-3.5 -translate-y-1/2 text-ink-muted" />
    </div>
  )
}
