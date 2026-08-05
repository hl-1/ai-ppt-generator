import { useId, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useDeckQuality, useExportDeck } from '@/features/deck/api'
import { classifyExportError, type ExportFailure } from '@/features/deck/exportErrors'
import type {
  Deck,
  DeckSlide,
  ExportCheckReport,
  ExportVerifyIssue,
  StructureIssue,
} from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import { cn } from '@/lib/utils'

function slideLabel(slides: DeckSlide[], slideId: string): string {
  const index = slides.findIndex((slide) => slide.id === slideId)
  if (index < 0) return '未知页面'
  const slide = slides[index]!
  return `第 ${slide.position} 页 · ${slide.title}`
}

export function QualityExportPanel({
  projectId,
  deck,
}: {
  projectId: string
  deck: Deck
}) {
  const headingId = useId()
  const issuesId = useId()
  const [issuesOpen, setIssuesOpen] = useState(true)

  // 生成结束后再拉一次质量报告；生成中不请求
  const settled = deck.status === 'ready' || deck.status === 'partial'
  const qualityQuery = useDeckQuality(projectId, settled)
  const exporter = useExportDeck(projectId, `${deck.title}.pptx`)

  const report = qualityQuery.data
  const issues = report?.issues ?? []
  const errors = issues.filter((issue) => issue.severity === 'error')
  const warnings = issues.filter((issue) => issue.severity === 'warning')
  const exportAllowed = report?.export_allowed === true
  const exporting = exporter.isPending
  const exportFailure = exporter.isError ? classifyExportError(exporter.error) : null

  const runExport = () => {
    if (exporting || !exportAllowed) return
    exporter.mutate()
  }

  return (
    <section
      aria-labelledby={headingId}
      className="mt-12 border border-line bg-surface px-8 py-7"
    >
      <div className="flex flex-wrap items-end justify-between gap-6">
        <div>
          <p className="mb-2 text-[10px] tracking-[0.2em] text-accent uppercase">导出</p>
          <h3 id={headingId} className="font-display text-2xl">
            质量检查与导出
          </h3>
          <p className="mt-2 max-w-xl text-sm leading-relaxed text-ink-muted">
            导出前会检查结构与溢出；通过后同步生成可编辑的 PPTX。
          </p>
        </div>

        <div className="flex flex-col items-end gap-2">
          <Button
            variant="accent"
            disabled={!exportAllowed || exporting || qualityQuery.isPending}
            onClick={runExport}
            aria-disabled={!exportAllowed || exporting}
          >
            {exporting ? '正在导出…' : '导出 PPTX'}
          </Button>
          {!qualityQuery.isPending && report && !exportAllowed && (
            <p className="max-w-xs text-right text-xs text-negative">
              存在必须修复的错误，暂时无法导出
            </p>
          )}
          {settled && deck.status === 'partial' && (
            <p className="max-w-xs text-right text-xs text-ink-muted">
              仍有页面未成功生成，导出前请先重试失败页
            </p>
          )}
        </div>
      </div>

      {exporting && (
        <p className="mt-5 text-xs text-ink-muted" aria-live="polite">
          正在检查、渲染并验证 PPTX，请稍候…
        </p>
      )}

      {exportFailure && <ExportFailureAlert failure={exportFailure} slides={deck.slides} />}

      <div className="mt-8 border-t border-line pt-6">
        {qualityQuery.isPending && (
          <p className="text-xs text-ink-muted" aria-live="polite">
            正在检查质量…
          </p>
        )}

        {qualityQuery.isError && (
          <p role="alert" className="border-l-2 border-negative py-1 pl-3 text-xs text-negative">
            {errorMessage(qualityQuery.error, '质量报告加载失败，请稍后重试')}
          </p>
        )}

        {report && (
          <QualitySummary
            report={report}
            errors={errors}
            warnings={warnings}
            issuesOpen={issuesOpen}
            issuesId={issuesId}
            onToggleIssues={() => setIssuesOpen((open) => !open)}
            slides={deck.slides}
          />
        )}
      </div>
    </section>
  )
}

function QualitySummary({
  report,
  errors,
  warnings,
  issuesOpen,
  issuesId,
  onToggleIssues,
  slides,
}: {
  report: ExportCheckReport
  errors: StructureIssue[]
  warnings: StructureIssue[]
  issuesOpen: boolean
  issuesId: string
  onToggleIssues: () => void
  slides: DeckSlide[]
}) {
  const totalIssues = errors.length + warnings.length

  return (
    <div>
      <div className="flex flex-wrap items-baseline justify-between gap-4">
        <div className="flex flex-wrap items-baseline gap-x-6 gap-y-2 text-sm">
          <span>
            <span className="text-ink-muted">错误 </span>
            <span className={cn('font-display text-xl tabular-nums', errors.length > 0 ? 'text-negative' : 'text-ink')}>
              {errors.length}
            </span>
          </span>
          <span>
            <span className="text-ink-muted">告警 </span>
            <span className={cn('font-display text-xl tabular-nums', warnings.length > 0 ? 'text-warning' : 'text-ink')}>
              {warnings.length}
            </span>
          </span>
          <span className="text-sm">
            {report.export_allowed ? (
              <span className="text-accent">允许导出</span>
            ) : (
              <span className="text-negative">禁止导出</span>
            )}
          </span>
        </div>

        {totalIssues > 0 && (
          <button
            type="button"
            aria-expanded={issuesOpen}
            aria-controls={issuesId}
            onClick={onToggleIssues}
            className="text-xs tracking-wide text-ink-soft transition-colors hover:text-accent"
          >
            {issuesOpen ? '收起问题' : '展开问题'}
          </button>
        )}
      </div>

      {!report.fonts_precise && (
        <p className="mt-3 border-l-2 border-warning py-1 pl-3 text-xs leading-relaxed text-warning">
          度量字体未就绪，文字溢出为估算值，并非精确结论。
        </p>
      )}

      {totalIssues === 0 ? (
        <p className="mt-4 text-sm text-ink-muted">未发现问题，可以导出 PPTX。</p>
      ) : (
        issuesOpen && (
          <div id={issuesId} className="mt-5 flex flex-col gap-5">
            {errors.length > 0 && (
              <IssueGroup
                label="必须修复"
                tone="error"
                issues={errors}
                slides={slides}
              />
            )}
            {warnings.length > 0 && (
              <IssueGroup
                label="建议关注"
                tone="warning"
                issues={warnings}
                slides={slides}
              />
            )}
          </div>
        )
      )}
    </div>
  )
}

function IssueGroup({
  label,
  tone,
  issues,
  slides,
}: {
  label: string
  tone: 'error' | 'warning'
  issues: StructureIssue[]
  slides: DeckSlide[]
}) {
  return (
    <div
      className={cn(
        'border-l-2 py-1 pl-3',
        tone === 'error' ? 'border-negative' : 'border-warning',
      )}
    >
      <p
        className={cn(
          'mb-2 text-[10px] tracking-[0.2em] uppercase',
          tone === 'error' ? 'text-negative' : 'text-warning',
        )}
      >
        {label}
      </p>
      <ul className="flex flex-col gap-2">
        {issues.map((issue, index) => (
          <li
            key={`${issue.slide_id}-${issue.slot_id ?? 'page'}-${index}`}
            className={cn(
              'text-xs leading-relaxed',
              tone === 'error' ? 'text-negative' : 'text-warning',
            )}
          >
            <span className="text-ink-soft">
              {slideLabel(slides, issue.slide_id)}
              {issue.slot_id ? ` · ${issue.slot_id}` : ''}
            </span>
            <span className="mx-1.5 text-line-strong">·</span>
            <span>{issue.message}</span>
          </li>
        ))}
      </ul>
    </div>
  )
}

function ExportFailureAlert({
  failure,
  slides,
}: {
  failure: ExportFailure
  slides: DeckSlide[]
}) {
  if (failure.kind === 'check') {
    const blockers = (failure.report.issues ?? []).filter((issue) => issue.severity === 'error')
    return (
      <div role="alert" className="mt-5 border-l-2 border-negative py-1 pl-3">
        <p className="text-sm text-negative">{failure.message}</p>
        <p className="mt-1 text-xs text-ink-muted">请按下列阻断项修改后再导出。</p>
        {blockers.length > 0 && (
          <ul className="mt-3 flex flex-col gap-1.5">
            {blockers.map((issue, index) => (
              <li key={`${issue.slide_id}-${index}`} className="text-xs text-negative">
                {slideLabel(slides, issue.slide_id)}
                {issue.slot_id ? ` · ${issue.slot_id}` : ''}
                <span className="mx-1.5 text-line-strong">·</span>
                {issue.message}
              </li>
            ))}
          </ul>
        )}
      </div>
    )
  }

  if (failure.kind === 'verify') {
    return (
      <div role="alert" className="mt-5 border-l-2 border-negative py-1 pl-3">
        <p className="text-sm text-negative">{failure.message}</p>
        <p className="mt-1 text-xs text-ink-muted">
          文件没有生成。下列可编辑性检查未通过，可直接重试导出。
        </p>
        <VerifyIssueList issues={failure.issues} />
      </div>
    )
  }

  if (failure.kind === 'incomplete') {
    return (
      <div role="alert" className="mt-5 border-l-2 border-negative py-1 pl-3">
        <p className="text-sm text-negative">{failure.message}</p>
      </div>
    )
  }

  if (failure.kind === 'server') {
    return (
      <div role="alert" className="mt-5 border-l-2 border-negative py-1 pl-3">
        <p className="text-sm text-negative">{failure.message}</p>
        <p className="mt-1 text-xs text-ink-muted">可直接再次点击导出重试。</p>
      </div>
    )
  }

  return (
    <div role="alert" className="mt-5 border-l-2 border-negative py-1 pl-3">
      <p className="text-sm text-negative">{failure.message}</p>
    </div>
  )
}

function VerifyIssueList({ issues }: { issues: ExportVerifyIssue[] }) {
  if (issues.length === 0) return null
  return (
    <ul className="mt-3 flex flex-col gap-1.5">
      {issues.map((issue, index) => (
        <li key={`${issue.check}-${issue.slide_index ?? 'x'}-${index}`} className="text-xs text-negative">
          <span className="text-ink-soft">
            {issue.slide_index != null ? `第 ${issue.slide_index} 页` : '整份文稿'}
            {issue.shape ? ` · ${issue.shape}` : ''}
            {` · ${issue.check}`}
          </span>
          <span className="mx-1.5 text-line-strong">·</span>
          {issue.message}
        </li>
      ))}
    </ul>
  )
}
