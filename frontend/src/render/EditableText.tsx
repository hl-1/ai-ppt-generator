import {
  type CSSProperties,
  type ClipboardEvent,
  type KeyboardEvent,
  useEffect,
  useLayoutEffect,
  useRef,
} from 'react'
import { cn } from '@/lib/utils'

const SAVE_IDLE_MS = 800

interface EditableTextProps {
  value: string
  ariaLabel: string
  /** false 时 Enter 提交并失焦，不插入换行 */
  multiline?: boolean
  style?: CSSProperties
  className?: string
  onCommit: (next: string) => void
}

/**
 * 受约束的 contenteditable：纯文本、主题样式原样继承，
 * 停止输入后自动提交，失焦立即提交，无变化不回调。
 *
 * 不用 React children 驱动文本，避免重渲染冲掉光标与草稿。
 */
export function EditableText({
  value,
  ariaLabel,
  multiline = false,
  style,
  className,
  onCommit,
}: EditableTextProps) {
  const ref = useRef<HTMLSpanElement>(null)
  const focusedRef = useRef(false)
  const valueRef = useRef(value)
  const draftRef = useRef(value)
  const timerRef = useRef<number | null>(null)
  const onCommitRef = useRef(onCommit)
  onCommitRef.current = onCommit

  const clearTimer = () => {
    if (timerRef.current != null) {
      window.clearTimeout(timerRef.current)
      timerRef.current = null
    }
  }

  const commitIfChanged = () => {
    const next = draftRef.current
    if (next === valueRef.current) return
    onCommitRef.current(next)
  }

  const scheduleCommit = () => {
    clearTimer()
    timerRef.current = window.setTimeout(() => {
      timerRef.current = null
      commitIfChanged()
    }, SAVE_IDLE_MS)
  }

  useLayoutEffect(() => {
    valueRef.current = value
    if (!focusedRef.current && ref.current && ref.current.textContent !== value) {
      ref.current.textContent = value
      draftRef.current = value
    }
  }, [value])

  useEffect(() => () => clearTimer(), [])

  const onPaste = (event: ClipboardEvent<HTMLSpanElement>) => {
    event.preventDefault()
    const text = event.clipboardData.getData('text/plain')
    const normalized = multiline ? text : text.replace(/[\r\n]+/g, ' ')
    document.execCommand('insertText', false, normalized)
  }

  const onKeyDown = (event: KeyboardEvent<HTMLSpanElement>) => {
    if (event.key === 'Escape') {
      event.preventDefault()
      event.stopPropagation()
      clearTimer()
      draftRef.current = valueRef.current
      if (ref.current) ref.current.textContent = valueRef.current
      ref.current?.blur()
      return
    }
    if (!multiline && event.key === 'Enter') {
      event.preventDefault()
      clearTimer()
      commitIfChanged()
      ref.current?.blur()
    }
  }

  return (
    <span
      ref={ref}
      role="textbox"
      aria-label={ariaLabel}
      aria-multiline={multiline || undefined}
      contentEditable="plaintext-only"
      suppressContentEditableWarning
      className={cn(
        // 透明描边占位，避免 focus 时布局跳动；颜色跟当前文字走，不引入额外主题色块
        'shadow-[inset_0_0_0_1px_transparent]',
        'hover:shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_22%,transparent)]',
        'focus:shadow-[inset_0_0_0_1px_color-mix(in_oklab,currentColor_40%,transparent)]',
        className,
      )}
      style={{
        ...style,
        outline: 'none',
        cursor: 'text',
        borderRadius: 0,
        minWidth: '0.5em',
        // 单行用 inline，避免表格单元格 / KPI 数值被 inline-block 撑成独立块导致跳动
        display: multiline ? 'block' : 'inline',
        whiteSpace: multiline ? 'pre-wrap' : undefined,
        wordBreak: multiline ? 'break-word' : undefined,
      }}
      onFocus={() => {
        focusedRef.current = true
      }}
      onBlur={() => {
        focusedRef.current = false
        clearTimer()
        commitIfChanged()
      }}
      onInput={() => {
        draftRef.current = ref.current?.textContent ?? ''
        scheduleCommit()
      }}
      onPaste={onPaste}
      onKeyDown={onKeyDown}
    />
  )
}
