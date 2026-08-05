import { cn } from '@/lib/utils'

type Tone = 'ok' | 'down' | 'unknown'

const TONE_STYLE: Record<Tone, { dot: string; label: string; text: string }> = {
  ok: { dot: 'bg-positive', label: '正常', text: 'text-ink-soft' },
  down: { dot: 'bg-negative', label: '不可用', text: 'text-negative' },
  unknown: { dot: 'bg-line-strong', label: '检测中', text: 'text-ink-muted' },
}

interface StatusRowProps {
  name: string
  hint: string
  tone: Tone
}

export function StatusRow({ name, hint, tone }: StatusRowProps) {
  const style = TONE_STYLE[tone]

  return (
    <div className="flex items-baseline gap-4 border-b border-line py-4 last:border-b-0">
      <span
        className={cn(
          'size-1.5 shrink-0 translate-y-[-2px] rounded-full',
          style.dot,
          tone === 'unknown' && 'animate-pulse',
        )}
      />
      <span className="w-28 shrink-0 text-sm font-medium tracking-wide">{name}</span>
      <span className="flex-1 text-sm text-ink-muted">{hint}</span>
      <span className={cn('text-sm tabular-nums', style.text)}>{style.label}</span>
    </div>
  )
}
