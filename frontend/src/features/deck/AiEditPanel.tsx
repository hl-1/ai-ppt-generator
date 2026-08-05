import { useEffect, useId, useState } from 'react'
import { ApiError } from '@/api/client'
import { Button } from '@/components/ui/Button'
import { useApplyAiEdit, useProposeAiEdit } from '@/features/deck/api'
import type {
  AiEditAction,
  AiEditOperation,
  AiEditPatch,
  AiEditProposal,
  DeckSlide,
} from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

const ACTIONS: { action: AiEditAction; label: string }[] = [
  { action: 'rewrite', label: '改写' },
  { action: 'condense', label: '压缩' },
  { action: 'expand', label: '扩写' },
]

const TYPE_LABEL: Record<AiEditOperation['type'], string> = {
  text: '文字',
  bullets: '列表',
  kpi: '指标',
  table: '表格',
}

export function AiEditPanel({
  projectId,
  slide,
}: {
  projectId: string
  slide: DeckSlide
}) {
  const titleId = useId()
  const instructionId = useId()
  const [instruction, setInstruction] = useState('')
  const [proposal, setProposal] = useState<AiEditProposal | null>(null)
  const [selected, setSelected] = useState<Set<string>>(new Set())
  const [lastAction, setLastAction] = useState<AiEditAction | null>(null)

  const propose = useProposeAiEdit(projectId, slide.id)
  const apply = useApplyAiEdit(projectId, slide.id)

  const generating = slide.status === 'generating'
  const busy = propose.isPending || apply.isPending
  const canPropose = !generating && !busy

  useEffect(() => {
    // 换页时清掉上一次提案，避免把旧页操作套到新页
    setProposal(null)
    setSelected(new Set())
    setLastAction(null)
  }, [slide.id])

  const runPropose = (action: AiEditAction) => {
    if (!canPropose) return
    setLastAction(action)
    apply.reset()
    const trimmed = instruction.trim()
    propose.mutate(
      {
        action,
        revision: slide.revision,
        ...(trimmed ? { instruction: trimmed.slice(0, 500) } : {}),
      },
      {
        onSuccess: (data) => {
          setProposal(data)
          setSelected(new Set(data.operations.map((op) => op.block_id)))
        },
      },
    )
  }

  const discardProposal = () => {
    setProposal(null)
    setSelected(new Set())
    apply.reset()
    propose.reset()
  }

  const toggle = (blockId: string) => {
    setSelected((current) => {
      const next = new Set(current)
      if (next.has(blockId)) next.delete(blockId)
      else next.add(blockId)
      return next
    })
  }

  const selectedOps =
    proposal?.operations.filter((op) => selected.has(op.block_id)) ?? []

  const runApply = () => {
    if (!proposal || selectedOps.length === 0 || apply.isPending) return
    apply.mutate(
      {
        revision: proposal.revision,
        operations: selectedOps.map((op) => op.after),
      },
      { onSuccess: () => discardProposal() },
    )
  }

  const applyConflict =
    apply.isError && apply.error instanceof ApiError && apply.error.status === 409

  return (
    <aside
      aria-labelledby={titleId}
      className="flex w-full shrink-0 flex-col border-t border-line bg-canvas md:w-96 md:border-t-0 md:border-l"
    >
      <div className="border-b border-line px-5 py-4">
        <p className="mb-1 text-[10px] tracking-[0.2em] text-accent uppercase">AI 修改</p>
        <h3 id={titleId} className="font-display text-xl">
          单页局部调整
        </h3>
        <p className="mt-1 text-[11px] leading-relaxed text-ink-muted">
          先预览再确认；人工改过的块不会被覆盖
        </p>
      </div>

      <div className="flex flex-1 flex-col gap-5 overflow-auto px-5 py-5">
        <div className="flex flex-wrap gap-2">
          {ACTIONS.map(({ action, label }) => (
            <button
              key={action}
              type="button"
              disabled={!canPropose}
              onClick={() => runPropose(action)}
              className={cn(
                'border border-line px-3 py-1.5 text-xs tracking-wide transition-colors',
                'hover:border-accent hover:text-accent',
                'disabled:cursor-not-allowed disabled:opacity-40',
                lastAction === action && propose.isPending && 'border-accent text-accent',
              )}
            >
              {propose.isPending && lastAction === action ? `${label}中…` : label}
            </button>
          ))}
        </div>

        <div className="flex flex-col gap-2">
          <label
            htmlFor={instructionId}
            className="text-[10px] tracking-[0.2em] text-ink-soft uppercase"
          >
            自由指令
          </label>
          <textarea
            id={instructionId}
            value={instruction}
            maxLength={500}
            rows={2}
            disabled={busy || generating}
            placeholder="可选：把语气改得更专业"
            onChange={(event) => setInstruction(event.target.value)}
            className={cn(
              'border border-line bg-surface px-3 py-2 text-sm leading-relaxed text-ink',
              'placeholder:text-ink-muted/60 focus:border-accent focus:outline-none',
              'resize-y disabled:opacity-40',
            )}
          />
        </div>

        {generating && (
          <p className="text-xs text-ink-muted">页面生成中，暂不可发起 AI 修改</p>
        )}

        {propose.isPending && (
          <p className="text-xs text-ink-muted" aria-live="polite">
            正在生成提案，请稍候…
          </p>
        )}

        {propose.isError && (
          <p role="alert" className="border-l-2 border-negative py-1 pl-3 text-xs text-negative">
            {errorMessage(propose.error)}
          </p>
        )}

        {proposal && (
          <ProposalPreview
            proposal={proposal}
            selected={selected}
            selectedCount={selectedOps.length}
            applying={apply.isPending}
            applyError={apply.isError ? errorMessage(apply.error) : null}
            applyConflict={applyConflict}
            lastAction={lastAction}
            onToggle={toggle}
            onApply={runApply}
            onDiscard={discardProposal}
            onRegenerate={() => lastAction && runPropose(lastAction)}
            canRegenerate={canPropose && lastAction != null}
          />
        )}
      </div>
    </aside>
  )
}

function ProposalPreview({
  proposal,
  selected,
  selectedCount,
  applying,
  applyError,
  applyConflict,
  lastAction,
  onToggle,
  onApply,
  onDiscard,
  onRegenerate,
  canRegenerate,
}: {
  proposal: AiEditProposal
  selected: Set<string>
  selectedCount: number
  applying: boolean
  applyError: string | null
  applyConflict: boolean
  lastAction: AiEditAction | null
  onToggle: (blockId: string) => void
  onApply: () => void
  onDiscard: () => void
  onRegenerate: () => void
  canRegenerate: boolean
}) {
  const listId = useId()
  const empty = proposal.operations.length === 0

  return (
    <section aria-labelledby={listId} className="flex flex-col gap-4">
      <h4 id={listId} className="text-[10px] tracking-[0.2em] text-ink-soft uppercase">
        变更预览
      </h4>

      {empty ? (
        <p className="border border-dashed border-line px-3 py-4 text-xs leading-relaxed text-ink-muted">
          模型没有提出需要修改的内容
          {proposal.discarded.length > 0
            ? '（部分块因已人工修改等原因被跳过）'
            : '。可调整指令后重试。'}
        </p>
      ) : (
        <ul className="flex flex-col gap-3">
          {proposal.operations.map((op) => (
            <OperationCard
              key={op.block_id}
              operation={op}
              checked={selected.has(op.block_id)}
              onToggle={() => onToggle(op.block_id)}
              disabled={applying}
            />
          ))}
        </ul>
      )}

      {proposal.warnings.length > 0 && (
        <div className="border-l-2 border-warning py-1 pl-3">
          <p className="mb-1 text-[10px] tracking-[0.2em] text-warning uppercase">
            应用后可能出现
          </p>
          <ul className="flex flex-col gap-1">
            {proposal.warnings.map((issue, index) => (
              <li key={`${issue.slot_id ?? 'page'}-${index}`} className="text-xs text-warning">
                {issue.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {proposal.discarded.length > 0 && (
        <div className="border-l-2 border-line-strong py-1 pl-3">
          <p className="mb-1 text-[10px] tracking-[0.2em] text-ink-soft uppercase">
            未改动的块
          </p>
          <ul className="flex flex-col gap-1.5">
            {proposal.discarded.map((item) => (
              <li key={item.block_id} className="text-xs leading-relaxed text-ink-muted">
                {item.reason}
              </li>
            ))}
          </ul>
        </div>
      )}

      {!empty && (
        <p className="text-xs text-ink-muted">
          已选 {selectedCount} / {proposal.operations.length} 条
        </p>
      )}

      {applyError && (
        <div role="alert" className="border-l-2 border-negative py-1 pl-3">
          <p className="text-xs text-negative">{applyError}</p>
          {applyConflict && (
            <button
              type="button"
              disabled={!canRegenerate}
              onClick={onRegenerate}
              className="mt-2 text-xs text-ink-muted underline-offset-2 hover:text-accent hover:underline disabled:opacity-40"
            >
              重新生成提案
              {lastAction ? `（${ACTIONS.find((item) => item.action === lastAction)?.label}）` : ''}
            </button>
          )}
        </div>
      )}

      <div className="flex flex-wrap items-center gap-3">
        {!empty && (
          <Button
            variant="accent"
            disabled={selectedCount === 0 || applying}
            onClick={onApply}
            className="h-9 px-4 text-xs"
          >
            {applying ? '应用中…' : '应用所选'}
          </Button>
        )}
        <Button
          variant="ghost"
          disabled={applying}
          onClick={onDiscard}
          className="h-9 px-3 text-xs"
        >
          放弃
        </Button>
      </div>
    </section>
  )
}

function OperationCard({
  operation,
  checked,
  onToggle,
  disabled,
}: {
  operation: AiEditOperation
  checked: boolean
  onToggle: () => void
  disabled?: boolean
}) {
  const checkboxId = useId()
  const labelId = `${checkboxId}-label`

  return (
    <li className="border border-line">
      <div className="flex items-center gap-3 border-b border-line px-3 py-2">
        <input
          id={checkboxId}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          onChange={onToggle}
          aria-labelledby={labelId}
          className="size-3.5 shrink-0 accent-[var(--color-accent)]"
        />
        <label id={labelId} htmlFor={checkboxId} className="min-w-0 flex-1 cursor-pointer">
          <span className="text-[10px] tracking-[0.16em] text-accent uppercase">
            {TYPE_LABEL[operation.type]}
          </span>
          <span className="ml-2 text-[11px] text-ink-soft">{operation.slot_id}</span>
        </label>
      </div>
      <div className="grid gap-0 sm:grid-cols-2">
        <PatchSide label="改动前" tone="before" patch={operation.before} type={operation.type} />
        <PatchSide label="改动后" tone="after" patch={operation.after} type={operation.type} />
      </div>
    </li>
  )
}

function PatchSide({
  label,
  tone,
  patch,
  type,
}: {
  label: string
  tone: 'before' | 'after'
  patch: AiEditPatch
  type: AiEditOperation['type']
}) {
  return (
    <div
      className={cn(
        'px-3 py-3',
        tone === 'before' && 'border-b border-line sm:border-r sm:border-b-0',
        tone === 'after' && 'sm:border-l-2 sm:border-l-accent/40',
      )}
    >
      <p
        className={cn(
          'mb-2 text-[10px] tracking-[0.16em] uppercase',
          tone === 'before' ? 'text-ink-muted' : 'text-accent',
        )}
      >
        {label}
      </p>
      <div
        className={cn(
          'text-xs leading-relaxed',
          tone === 'before' && 'text-ink-muted line-through decoration-ink-muted/50 opacity-70',
          tone === 'after' && 'text-ink',
        )}
      >
        <PatchContent patch={patch} type={type} />
      </div>
    </div>
  )
}

function PatchContent({
  patch,
  type,
}: {
  patch: AiEditPatch
  type: AiEditOperation['type']
}) {
  if (type === 'text' && patch.type === 'text') {
    return <p className="whitespace-pre-wrap">{patch.text || '（空）'}</p>
  }

  if (type === 'bullets' && patch.type === 'bullets') {
    if (patch.items.length === 0) return <p>（空列表）</p>
    return (
      <ul className="flex flex-col gap-1">
        {patch.items.map((item, index) => (
          <li key={`${index}-${item.slice(0, 12)}`} className="flex gap-2">
            <span className="text-ink-soft tabular-nums">{String(index + 1).padStart(2, '0')}</span>
            <span className="min-w-0 flex-1 whitespace-pre-wrap">{item}</span>
          </li>
        ))}
      </ul>
    )
  }

  if (type === 'kpi' && patch.type === 'kpi') {
    return (
      <dl className="flex flex-col gap-1.5">
        <div>
          <dt className="text-[10px] text-ink-soft">数值</dt>
          <dd>{patch.value || '—'}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-ink-soft">标签</dt>
          <dd>{patch.label || '—'}</dd>
        </div>
        <div>
          <dt className="text-[10px] text-ink-soft">备注</dt>
          <dd>{patch.note?.trim() ? patch.note : '—'}</dd>
        </div>
      </dl>
    )
  }

  if (type === 'table' && patch.type === 'table') {
    return (
      <div className="overflow-x-auto">
        <table className="w-full border-collapse text-left">
          <thead>
            <tr>
              {patch.header.map((cell, index) => (
                <th
                  key={`h-${index}`}
                  className="border-b border-line px-1.5 py-1 font-medium"
                >
                  {cell || '—'}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {patch.rows.map((row, rowIndex) => (
              <tr key={`r-${rowIndex}`}>
                {row.map((cell, cellIndex) => (
                  <td key={`c-${rowIndex}-${cellIndex}`} className="border-b border-line/60 px-1.5 py-1">
                    {cell || '—'}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    )
  }

  return <p>（无法展示）</p>
}
