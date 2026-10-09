import {
  ArrowLeft, ArrowRight, Check, CheckCircle2, Circle, CircleStop, Clock3,
  FileText, Loader2, RefreshCw, TriangleAlert, WifiOff, XCircle,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/Button'
import { outlineErrorMessage, outlineRequestErrorMessage } from '@/features/outline/errors'
import type { Outline, OutlineExecution, OutlineStage, OutlineStageExecution } from '@/features/outline/types'
import type { ProjectDetail } from '@/features/projects/types'
import { TravelPanel } from '@/features/travel/TravelPanel'
import { cn } from '@/lib/utils'

const STAGE_LABELS: Record<OutlineStage, string> = {
  queue: '提交生成任务', load_input: '读取输入材料', travel_research: '查询与核实旅行资料',
  plan_structure: '规划大纲结构', validate: '校验大纲结构', save: '保存大纲',
}
const STATE_LABELS: Record<OutlineStageExecution['status'], string> = {
  pending: '待执行', started: '进行中', succeeded: '已完成', partial: '部分完成',
  retrying: '等待重试', failed: '失败', cancelled: '已取消',
}
const time = (value: string | null | undefined) => value
  ? new Date(value).toLocaleTimeString('zh-CN', { hour12: false }) : '待确认'
const seconds = (start: string, end: number) => Math.max(0, Math.floor((end - Date.parse(start)) / 1000))
const duration = (value: number) => value < 60 ? `${value} 秒` : `${Math.floor(value / 60)} 分 ${value % 60} 秒`

function useNow(active: boolean) {
  const [now, setNow] = useState(Date.now)
  useEffect(() => {
    if (!active) return
    const timer = window.setInterval(() => setNow(Date.now()), 1000)
    return () => window.clearInterval(timer)
  }, [active])
  return now
}

export function OutlineExecutionView({
  project, outline, execution, connectionError, queryError, refreshing, onRefresh,
  onRetry, retryPending, requestError, onCancel, cancelPending, onContinue,
}: {
  project: ProjectDetail
  outline: Outline | null
  execution: OutlineExecution | null
  connectionError: boolean
  queryError: Error | null
  refreshing: boolean
  onRefresh: () => void
  onRetry: () => void
  retryPending: boolean
  requestError: Error | null
  onCancel: () => void
  cancelPending: boolean
  onContinue: () => void
}) {
  const [confirmStop, setConfirmStop] = useState(false)
  const running = outline?.status === 'generating'
  const success = outline?.status === 'draft' || outline?.status === 'confirmed'
  const failed = outline?.status === 'failed'
  const cancelled = outline?.status === 'cancelled'
  const now = useNow(running)
  const stages = execution?.stages ?? []
  const complete = stages.filter((step) => ['succeeded', 'partial'].includes(step.status)).length
  const partial = stages.some((step) => step.status === 'partial')
  const retrying = running && !!execution?.retry_at
  const retryWait = execution?.retry_at ? Math.max(0, Math.ceil((Date.parse(execution.retry_at) - now) / 1000)) : 0
  const age = execution ? seconds(execution.updated_at, now) : null
  const stale = running && age !== null && age >= 45
  const failure = execution?.failure
  const current = execution?.stage
  const title = queryError && !outline ? '暂时无法读取任务状态'
    : success ? partial ? '大纲已生成，仍有资料待核实' : '大纲已生成并保存'
      : failed ? `${current ? STAGE_LABELS[current] : '大纲生成'}失败`
        : cancelled ? '本次生成已取消'
          : retrying ? '执行遇到问题，等待自动重试'
            : running ? current === 'queue' ? '任务已提交，等待执行' : '正在生成大纲' : '准备生成大纲'
  const HeaderIcon = success ? CheckCircle2 : failed ? XCircle : cancelled ? CircleStop : queryError ? WifiOff : running ? Loader2 : FileText
  const headerColor = success ? 'text-positive' : failed ? 'text-negative' : cancelled ? 'text-ink-muted' : 'text-accent'

  return (
    <main className="mx-auto w-full max-w-4xl px-5 py-8 sm:px-8 sm:py-12">
      <section aria-label="大纲生成状态" className="min-w-0">
        <p className="mb-5 text-xs text-ink-muted">大纲生成 · {project.page_count} 页 · {project.report_brief?.scenario === 'travel_plan' ? '旅行规划' : '演示文稿'}</p>
        <div className="flex items-start gap-3" role="status" aria-live="polite">
          <HeaderIcon className={cn('mt-1 size-6 shrink-0', headerColor, running && !retrying && !connectionError && 'animate-spin')} />
          <h2 className="min-w-0 break-words text-2xl leading-snug font-semibold">{title}</h2>
        </div>
        <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-xs text-ink-muted tabular-nums">
          <span>总耗时 <strong className="font-medium text-ink-soft">{execution ? duration(seconds(execution.started_at, execution.finished_at ? Date.parse(execution.finished_at) : now)) : '待确认'}</strong></span>
          <span>最后进展 <strong className="font-medium text-ink-soft">{time(execution?.updated_at)}</strong></span>
          {execution && <span>第 {execution.attempt} / {execution.max_attempts} 次尝试</span>}
        </div>
        {stages.length > 0 && <div className="mt-7">
          <div className="flex flex-wrap justify-between gap-2 text-sm">
            <span>已完成 {complete} / {stages.length} 个阶段</span>
            {partial && <span className="text-xs text-warning">包含部分完成的旅行查询</span>}
          </div>
          <div role="progressbar" aria-label="已完成阶段" aria-valuemin={0} aria-valuemax={stages.length} aria-valuenow={complete} className="mt-3 h-1.5 w-full overflow-hidden rounded-sm bg-line">
            <div className={cn('h-full transition-[width] duration-300', failed ? 'bg-negative' : partial ? 'bg-warning' : success ? 'bg-positive' : 'bg-accent')} style={{ width: `${complete / stages.length * 100}%` }} />
          </div>
        </div>}

        {(failure || failed) && <div role="alert" className="mt-6 border-l-2 border-negative bg-negative/5 px-4 py-3">
          <p className="text-sm font-medium text-negative">{failure?.message ?? outlineErrorMessage(outline?.error_code, outline?.error ?? undefined)}</p>
          <p className="mt-1.5 text-sm leading-relaxed text-ink-soft">{failure?.action ?? '请重新生成；持续失败时提供任务编号联系管理员。'}</p>
          <p className="mt-2 text-xs text-ink-muted">{retrying
            ? retryWait > 0 ? `${retryWait} 秒后进行第 ${Math.min((execution?.attempt ?? 1) + 1, execution?.max_attempts ?? 2)} 次尝试` : '重试时间已到，等待后台开始下一次尝试'
            : failed ? failure?.retryable === false ? '请先处理上述问题，再重新生成。' : `本次任务已结束${(execution?.attempt ?? 1) >= (execution?.max_attempts ?? 2) ? '，自动重试次数已用尽' : ''}。` : ''}</p>
          {failure && <p className="mt-2 text-xs text-ink-muted">阶段：{STAGE_LABELS[failure.stage]} · 错误：{failure.code}</p>}
        </div>}
        {success && <p className="mt-6 flex items-start gap-2 border-y border-line py-4 text-sm text-ink-soft"><Check className="mt-0.5 size-4 shrink-0 text-positive" />已保存 {outline.pages.length} 页大纲，可继续编辑并生成 PPT。{partial && '旅行资料中的待核实项仍需确认。'}</p>}
        {cancelled && <p className="mt-6 border-y border-line py-4 text-sm text-ink-soft">本次任务不会写入新的大纲。输入材料与已获取的旅行资料仍然保留。</p>}
        {running && (connectionError || queryError || stale) && <div role="status" className="mt-6 flex gap-2 border-y border-line py-3 text-warning">
          {connectionError || queryError ? <WifiOff className="mt-0.5 size-4 shrink-0" /> : <Clock3 className="mt-0.5 size-4 shrink-0" />}
          <div className="min-w-0 text-sm"><p>{connectionError || queryError ? '进度连接中断，正在重新获取任务状态' : `${age} 秒未收到新的执行进展`}</p><p className="mt-1 text-xs text-ink-muted">保留最后收到的记录，当前无法确认后台进展。</p></div>
        </div>}
        {queryError && !running && <p role="alert" className="mt-5 text-sm text-negative">{outlineRequestErrorMessage(queryError)}</p>}

        {stages.length > 0 ? <ol className="mt-6" aria-label="执行阶段">
          {stages.map((step) => <StageRow key={step.stage} step={step} now={now} running={running} />)}
        </ol> : running && <p className="py-8 text-sm text-ink-muted">正在获取阶段记录…</p>}

        <details className="mt-4 border-t border-line">
          <summary className="cursor-pointer py-4 text-sm text-ink-soft">输入材料与已有资料</summary>
          <ul className="mb-4 divide-y divide-line text-sm">
            {project.sources.map((source, index) => <li className="flex min-w-0 items-start gap-2 py-3" key={source.id}>
              <FileText className="mt-0.5 size-4 shrink-0 text-ink-muted" />
              <div className="min-w-0"><p className="break-words">{source.filename || (source.kind === 'topic' ? '主题输入' : `输入材料 ${index + 1}`)}</p><p className="mt-1 text-xs text-ink-muted">已保存 · {source.char_count} 字</p></div>
            </li>)}
            {project.sources.length === 0 && <li className="py-3 text-ink-muted">暂无输入材料</li>}
          </ul>
          {project.report_brief?.scenario === 'travel_plan' && <TravelPanel project={project} locked={running} />}
        </details>
        <details className="border-t border-line">
          <summary className="cursor-pointer py-4 text-sm text-ink-soft">执行记录{execution ? ` · ${execution.history.length} 条` : ''}</summary>
          {execution ? <><ol className="mb-3 space-y-3 text-xs">
            {execution.history.map((entry, index) => <li className="grid grid-cols-[4.5rem_minmax(0,1fr)] gap-3" key={`${entry.timestamp}-${index}`}>
              <time className="text-ink-muted tabular-nums">{time(entry.timestamp)}</time>
              <div className="min-w-0 break-words text-ink-soft">{entry.stage && `${STAGE_LABELS[entry.stage]} · `}{entry.message}
                <span className="ml-2 text-ink-muted">第 {entry.attempt} 次{entry.error_code && ` · ${entry.error_code}`}</span>
              </div>
            </li>)}
          </ol><p className="mb-4 break-all text-xs text-ink-muted">任务编号：{execution.job_id}</p></> : <p className="pb-4 text-xs text-ink-muted">该任务没有历史阶段记录。</p>}
        </details>

        <div className="mt-2 flex flex-wrap items-center gap-3 border-t border-line pt-5">
          {success ? <Button className="rounded-md" onClick={onContinue}>查看并编辑大纲<ArrowRight className="size-4" /></Button>
            : !running && !queryError && <Button className="rounded-md" disabled={retryPending} onClick={onRetry}><RefreshCw className={cn('size-4', retryPending && 'animate-spin')} />{retryPending ? '正在提交…' : outline ? '重新生成大纲' : '生成大纲'}</Button>}
          <Button variant="ghost" className="rounded-md" disabled={refreshing} onClick={onRefresh}><RefreshCw className={cn('size-4', refreshing && 'animate-spin')} />重新查询状态</Button>
          <Link to="/projects" className="inline-flex min-h-10 items-center gap-1 text-sm text-ink-muted hover:text-ink"><ArrowLeft className="size-4" />返回我的 PPT</Link>
          {running && <Button variant="ghost" className="rounded-md text-negative sm:ml-auto" disabled={cancelPending || retryPending} onClick={() => setConfirmStop(true)}><CircleStop className="size-4" />{cancelPending ? '正在停止…' : '停止生成'}</Button>}
        </div>
        {confirmStop && running && <div role="alertdialog" aria-labelledby="stop-title" className="mt-5 border-t border-line pt-4">
          <h3 id="stop-title" className="text-sm font-medium">停止本次大纲生成？</h3><p className="mt-2 text-sm text-ink-muted">本次任务的未保存结果将不再写入，已有材料和资料会保留。</p>
          <div className="mt-3 flex gap-3"><Button className="rounded-md" disabled={cancelPending} onClick={onCancel}><CircleStop className="size-4" />确认停止</Button><Button className="rounded-md" variant="ghost" disabled={cancelPending} onClick={() => setConfirmStop(false)}>继续等待</Button></div>
        </div>}
        {requestError && <p role="alert" className="mt-4 text-sm text-negative">{outlineRequestErrorMessage(requestError)}</p>}
      </section>
    </main>
  )
}

function StageRow({ step, now, running }: { step: OutlineStageExecution; now: number; running: boolean }) {
  const done = step.status === 'succeeded'
  const working = step.status === 'started' && running
  const warning = step.status === 'partial' || step.status === 'retrying'
  const Icon = done ? CheckCircle2 : working ? Loader2 : warning ? TriangleAlert : step.status === 'failed' ? XCircle : step.status === 'cancelled' ? CircleStop : Circle
  return (
    <li className="grid grid-cols-[1.5rem_minmax(0,1fr)_4rem] items-start gap-3 border-b border-line/70 py-4">
      <Icon className={cn('mt-0.5 size-5', done ? 'text-positive' : warning ? 'text-warning' : step.status === 'failed' ? 'text-negative' : working ? 'animate-spin text-accent' : 'text-ink-muted')} />
      <div className="min-w-0">
        <p className={cn('text-sm font-medium', step.status === 'pending' && 'text-ink-muted')}>{STAGE_LABELS[step.stage]}</p>
        <p className="mt-1 break-words text-xs leading-relaxed text-ink-muted">{step.message}</p>
        {step.started_at && <p className="mt-1 text-xs text-ink-muted tabular-nums">{step.finished_at ? `耗时 ${duration(seconds(step.started_at, Date.parse(step.finished_at)))}` : working ? `已等待 ${duration(seconds(step.started_at, now))}` : ''}</p>}
        {!!step.issues?.length && <details className="mt-2"><summary className="cursor-pointer text-xs text-warning">{step.issues.length} 项问题待处理</summary><ul className="mt-2 space-y-3">
          {step.issues.map((issue, index) => <li className="text-xs leading-relaxed" key={`${issue.code}-${index}`}><p className="text-warning">{issue.message}</p><p className="text-ink-muted">{issue.action}</p></li>)}
        </ul></details>}
      </div>
      <span className={cn('pt-0.5 text-right text-xs whitespace-nowrap', warning ? 'text-warning' : step.status === 'failed' ? 'text-negative' : done ? 'text-positive' : 'text-ink-muted')}>{step.status === 'pending' && !running ? '未执行' : STATE_LABELS[step.status]}</span>
    </li>
  )
}
