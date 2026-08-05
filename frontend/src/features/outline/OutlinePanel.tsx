import { useEffect, useMemo, useState } from 'react'
import { Button } from '@/components/ui/Button'
import {
  useConfirmOutline,
  useGenerateOutline,
  useOutline,
  useUnconfirmOutline,
  useUpdateOutline,
} from '@/features/outline/api'
import type { Outline, OutlinePage } from '@/features/outline/types'
import { useOutlineProgress } from '@/features/outline/useOutlineProgress'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'
import { layouts } from '@/render/design'

const LAYOUT_OPTIONS = [...layouts.values()].map((layout) => ({
  id: layout.id,
  name: layout.name,
}))

export function OutlinePanel({
  projectId,
  pageCount,
  hasSources,
}: {
  projectId: string
  pageCount: number
  hasSources: boolean
}) {
  const outlineQuery = useOutline(projectId)
  const generate = useGenerateOutline(projectId)
  const outline = outlineQuery.data
  const progress = useOutlineProgress(projectId, outline?.status === 'generating')

  return (
    <section className="border-t border-line py-16">
      <div className="mb-10 flex items-end justify-between gap-8">
        <div>
          <p className="mb-3 text-xs tracking-[0.2em] text-accent uppercase">大纲规划</p>
          <h2 className="font-display text-3xl">先把每一页为什么存在说清楚。</h2>
          <p className="mt-3 max-w-2xl text-sm leading-relaxed text-ink-muted">
            大纲只规划页面目标与关键要点，不提前生成完整正文。确认后才能进入页面生成。
          </p>
        </div>
        {(outline == null || outline.status === 'failed') && (
          <Button
            variant="accent"
            disabled={!hasSources || generate.isPending}
            onClick={() => generate.mutate()}
          >
            {generate.isPending ? '正在提交…' : outline ? '重新生成大纲' : '生成大纲'}
          </Button>
        )}
      </div>

      {outlineQuery.isPending && <p className="text-sm text-ink-muted">正在读取大纲…</p>}
      {outlineQuery.isError && <p className="text-sm text-negative">大纲读取失败，请刷新重试。</p>}
      {outline == null && !outlineQuery.isPending && (
        <EmptyOutline hasSources={hasSources} error={generate.error} />
      )}
      {outline?.status === 'generating' && (
        <GeneratingOutline
          progress={progress.event?.progress ?? 0}
          message={progress.event?.message ?? '等待任务开始'}
          connectionError={progress.connectionError}
        />
      )}
      {outline?.status === 'failed' && (
        <p role="alert" className="border-l-2 border-negative py-2 pl-4 text-sm text-negative">
          {outline.error ?? '大纲生成失败，请重试。'}
        </p>
      )}
      {outline && (outline.status === 'draft' || outline.status === 'confirmed') && (
        <OutlineEditor outline={outline} targetPageCount={pageCount} />
      )}
    </section>
  )
}

function EmptyOutline({ hasSources, error }: { hasSources: boolean; error: Error | null }) {
  return (
    <div className="border border-dashed border-line-strong bg-surface px-8 py-10">
      <p className="text-sm text-ink-soft">
        {hasSources ? '输入材料已就绪，可以开始生成大纲。' : '先添加至少一份输入材料。'}
      </p>
      {error && <p className="mt-3 text-sm text-negative">{errorMessage(error)}</p>}
    </div>
  )
}

function GeneratingOutline({
  progress,
  message,
  connectionError,
}: {
  progress: number
  message: string
  connectionError: boolean
}) {
  return (
    <div className="border border-line bg-surface px-8 py-8">
      <div className="mb-4 flex items-baseline justify-between">
        <span className="text-sm font-medium">{message}</span>
        <span className="font-display text-2xl text-accent tabular-nums">{progress}%</span>
      </div>
      <div className="h-1 overflow-hidden bg-line">
        <div
          className="h-full bg-accent transition-[width] duration-500"
          style={{ width: `${progress}%` }}
        />
      </div>
      {connectionError && (
        <p className="mt-3 text-xs text-ink-muted">进度连接暂时中断，正在自动重连…</p>
      )}
    </div>
  )
}

function OutlineEditor({
  outline,
  targetPageCount,
}: {
  outline: Outline
  targetPageCount: number
}) {
  const locked = outline.status === 'confirmed'
  const [pages, setPages] = useState<OutlinePage[]>(outline.pages)
  const update = useUpdateOutline(outline.project_id)
  const confirm = useConfirmOutline(outline.project_id)
  const unconfirm = useUnconfirmOutline(outline.project_id)

  useEffect(() => setPages(outline.pages), [outline.pages, outline.revision])

  const dirty = useMemo(
    () => JSON.stringify(pages) !== JSON.stringify(outline.pages),
    [outline.pages, pages],
  )
  const countValid = pages.length === targetPageCount
  const actionError = update.error ?? confirm.error ?? unconfirm.error

  const changePage = (index: number, next: OutlinePage) => {
    setPages((current) => current.map((page, pageIndex) => (pageIndex === index ? next : page)))
  }

  const movePage = (index: number, direction: -1 | 1) => {
    const target = index + direction
    if (target < 0 || target >= pages.length) return
    setPages((current) => {
      const next = [...current]
      ;[next[index], next[target]] = [next[target], next[index]]
      return next
    })
  }

  const removePage = (index: number) => {
    setPages((current) => current.filter((_, pageIndex) => pageIndex !== index))
  }

  const addPage = () => {
    setPages((current) => [...current, newOutlinePage(current.length + 1)])
  }

  return (
    <div>
      <div className="mb-7 flex flex-wrap items-center justify-between gap-5 border-y border-line py-4">
        <div className="flex items-baseline gap-4">
          <span className="text-sm font-medium">
            {locked ? '已确认，只读' : '草稿，可调整'}
          </span>
          <span className={cn('text-xs', countValid ? 'text-ink-muted' : 'text-negative')}>
            {pages.length} / {targetPageCount} 页
          </span>
          <span className="text-xs text-ink-muted">版本 {outline.revision}</span>
        </div>
        <div className="flex items-center gap-3">
          {locked ? (
            <Button
              variant="ghost"
              disabled={unconfirm.isPending}
              onClick={() => unconfirm.mutate(outline.revision)}
            >
              取消确认并继续编辑
            </Button>
          ) : (
            <>
              <Button variant="ghost" onClick={addPage}>
                添加一页
              </Button>
              <Button
                variant="ghost"
                disabled={!dirty || !countValid || update.isPending}
                onClick={() => update.mutate({ revision: outline.revision, pages })}
              >
                {update.isPending ? '保存中…' : '保存大纲'}
              </Button>
              <Button
                variant="accent"
                disabled={dirty || !countValid || confirm.isPending}
                onClick={() => confirm.mutate(outline.revision)}
              >
                {confirm.isPending ? '确认中…' : '确认大纲'}
              </Button>
            </>
          )}
        </div>
      </div>

      {!countValid && (
        <p className="mb-5 text-sm text-negative">
          目标页数为 {targetPageCount}，调整到一致后才能保存和确认。
        </p>
      )}
      {actionError && (
        <p role="alert" className="mb-5 text-sm text-negative">
          {errorMessage(actionError)}
        </p>
      )}

      <ol className="space-y-4">
        {pages.map((page, index) => (
          <OutlinePageItem
            key={page.id}
            page={page}
            index={index}
            count={pages.length}
            locked={locked}
            onChange={(next) => changePage(index, next)}
            onMove={(direction) => movePage(index, direction)}
            onRemove={() => removePage(index)}
          />
        ))}
      </ol>
    </div>
  )
}

function OutlinePageItem({
  page,
  index,
  count,
  locked,
  onChange,
  onMove,
  onRemove,
}: {
  page: OutlinePage
  index: number
  count: number
  locked: boolean
  onChange: (page: OutlinePage) => void
  onMove: (direction: -1 | 1) => void
  onRemove: () => void
}) {
  return (
    <li className="grid gap-6 border border-line bg-surface p-6 md:grid-cols-[3rem_1fr_auto]">
      <span className="font-display text-3xl text-line-strong tabular-nums">
        {String(index + 1).padStart(2, '0')}
      </span>
      <div className="min-w-0 space-y-5">
        <input
          aria-label={`第 ${index + 1} 页标题`}
          value={page.title}
          readOnly={locked}
          maxLength={100}
          onChange={(event) => onChange({ ...page, title: event.target.value })}
          className="w-full border-b border-line-strong bg-transparent pb-2 text-lg font-medium focus:border-accent focus:outline-none read-only:border-transparent"
        />
        <textarea
          aria-label={`第 ${index + 1} 页目标`}
          value={page.objective}
          readOnly={locked}
          rows={2}
          maxLength={300}
          onChange={(event) => onChange({ ...page, objective: event.target.value })}
          className="w-full resize-y border border-line bg-canvas p-3 text-sm leading-relaxed text-ink-soft focus:border-accent focus:outline-none read-only:resize-none read-only:border-transparent read-only:bg-transparent read-only:p-0"
        />
        <div className="space-y-2">
          {page.key_points.map((point, pointIndex) => (
            <div key={pointIndex} className="flex items-start gap-3">
              <span className="mt-2 size-1.5 shrink-0 rounded-full bg-accent" />
              <input
                aria-label={`第 ${index + 1} 页要点 ${pointIndex + 1}`}
                value={point}
                readOnly={locked}
                maxLength={200}
                onChange={(event) => {
                  const keyPoints = [...page.key_points]
                  keyPoints[pointIndex] = event.target.value
                  onChange({ ...page, key_points: keyPoints })
                }}
                className="w-full border-b border-line bg-transparent pb-1 text-sm focus:border-accent focus:outline-none read-only:border-transparent"
              />
              {!locked && page.key_points.length > 2 && (
                <button
                  type="button"
                  aria-label={`删除第 ${index + 1} 页要点 ${pointIndex + 1}`}
                  onClick={() =>
                    onChange({
                      ...page,
                      key_points: page.key_points.filter(
                        (_, currentIndex) => currentIndex !== pointIndex,
                      ),
                    })
                  }
                  className="text-xs text-ink-muted hover:text-negative"
                >
                  ×
                </button>
              )}
            </div>
          ))}
          {!locked && page.key_points.length < 5 && (
            <button
              type="button"
              onClick={() => onChange({ ...page, key_points: [...page.key_points, '新要点'] })}
              className="ml-4 text-xs text-ink-muted hover:text-accent"
            >
              + 添加要点
            </button>
          )}
        </div>
        {page.source_refs.length > 0 && (
          <p className="text-[11px] text-ink-muted">来源：{page.source_refs.join(' · ')}</p>
        )}
      </div>
      <div className="flex items-start gap-3 md:flex-col md:items-end">
        <select
          aria-label={`第 ${index + 1} 页布局`}
          value={page.layout_id}
          disabled={locked}
          onChange={(event) => onChange({ ...page, layout_id: event.target.value })}
          className="h-8 border-b border-line bg-transparent text-xs text-ink-soft focus:border-accent focus:outline-none disabled:appearance-none disabled:border-transparent"
        >
          {LAYOUT_OPTIONS.map((layout) => (
            <option key={layout.id} value={layout.id}>
              {layout.name}
            </option>
          ))}
        </select>
        {!locked && (
          <div className="flex gap-2">
            <button
              type="button"
              aria-label={`第 ${index + 1} 页上移`}
              disabled={index === 0}
              onClick={() => onMove(-1)}
              className="text-xs text-ink-muted hover:text-accent disabled:opacity-25"
            >
              ↑
            </button>
            <button
              type="button"
              aria-label={`第 ${index + 1} 页下移`}
              disabled={index === count - 1}
              onClick={() => onMove(1)}
              className="text-xs text-ink-muted hover:text-accent disabled:opacity-25"
            >
              ↓
            </button>
            <button
              type="button"
              onClick={onRemove}
              className="text-xs text-ink-muted hover:text-negative"
            >
              删除
            </button>
          </div>
        )}
      </div>
    </li>
  )
}

function newOutlinePage(index: number): OutlinePage {
  return {
    id: crypto.randomUUID(),
    title: `第 ${index} 页`,
    objective: '',
    key_points: ['要点一', '要点二'],
    source_refs: [],
    layout_id: 'bullets',
  }
}
