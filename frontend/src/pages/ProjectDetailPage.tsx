import { type FormEvent, useState } from 'react'
import { Link, useParams } from 'react-router'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { TextField } from '@/components/ui/TextField'
import { DeckPanel } from '@/features/deck/DeckPanel'
import { useOutline } from '@/features/outline/api'
import { OutlinePanel } from '@/features/outline/OutlinePanel'
import { useProject, useUpdateProject } from '@/features/projects/api'
import { SourceComposer } from '@/features/projects/SourceComposer'
import { SourceList } from '@/features/projects/SourceList'
import { PAGE_COUNT_OPTIONS, THEME_OPTIONS, TONE_OPTIONS } from '@/features/projects/options'
import { STATUS_LABEL, type ProjectDetail, type Tone } from '@/features/projects/types'

export default function ProjectDetailPage() {
  const { projectId = '' } = useParams()
  const project = useProject(projectId)
  // 锁定以大纲状态为准而不是项目状态：页面开始生成后项目状态会变成
  // generating/ready，但设置和输入材料同样不该再改
  const outline = useOutline(projectId)
  const outlineConfirmed = outline.data?.status === 'confirmed'

  if (project.isPending) {
    return <p className="py-24 text-sm text-ink-muted">正在加载…</p>
  }

  if (project.isError || !project.data) {
    return (
      <div className="py-24">
        <p className="text-sm text-negative">项目不存在，或你没有访问权限。</p>
        <Link to="/projects" className="mt-4 inline-block text-sm text-accent underline">
          返回列表
        </Link>
      </div>
    )
  }

  return (
    <>
      <section className="border-b border-line py-14">
        <Link to="/projects" className="text-xs text-ink-muted transition-colors hover:text-accent">
          ← PPT
        </Link>
        <h1 className="mt-5 font-display text-[clamp(1.75rem,3.5vw,2.5rem)] leading-[1.3]">
          {project.data.title}
        </h1>
        <p className="mt-4 text-sm text-ink-muted">
          {STATUS_LABEL[project.data.status]} · 目标 {project.data.page_count} 页
        </p>
      </section>

      {/* min-w-0：栅格子项默认 min-width:auto，内部 truncate 的 nowrap 文本
          会把整列顶宽，进而撑出横向滚动条 */}
      <div className="grid gap-16 py-16 lg:grid-cols-[1fr_1.4fr] [&>*]:min-w-0">
        <SettingsForm project={project.data} locked={outlineConfirmed} />
        <div className="flex flex-col gap-16">
          {outlineConfirmed ? (
            <p className="border-l-2 border-accent py-2 pl-4 text-sm text-ink-soft">
              大纲已确认。取消确认后才能修改设置和输入材料。
            </p>
          ) : (
            <SourceComposer projectId={projectId} />
          )}
          <SourceList
            projectId={projectId}
            sources={project.data.sources}
            locked={outlineConfirmed}
          />
        </div>
      </div>
      <OutlinePanel
        projectId={projectId}
        pageCount={project.data.page_count}
        hasSources={project.data.sources.some((source) => source.char_count > 0)}
      />
      <DeckPanel
        projectId={projectId}
        themeId={project.data.theme_id}
        outlineConfirmed={outlineConfirmed}
      />
    </>
  )
}

function SettingsForm({ project, locked }: { project: ProjectDetail; locked: boolean }) {
  const update = useUpdateProject(project.id)
  const [title, setTitle] = useState(project.title)
  const [audience, setAudience] = useState(project.audience ?? '')
  const [tone, setTone] = useState<Tone>(project.tone)
  const [pageCount, setPageCount] = useState(project.page_count)
  const [themeId, setThemeId] = useState(project.theme_id)

  const dirty =
    title !== project.title ||
    audience !== (project.audience ?? '') ||
    tone !== project.tone ||
    pageCount !== project.page_count ||
    themeId !== project.theme_id

  const submit = (event: FormEvent) => {
    event.preventDefault()
    update.mutate({
      title: title.trim(),
      audience: audience.trim() || null,
      tone,
      page_count: pageCount,
      theme_id: themeId,
    })
  }

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold tracking-wide">生成设置</h2>
      <p className="mb-6 text-sm text-ink-muted">大纲生成时读取这里的取值。</p>

      <form onSubmit={submit} className="flex flex-col gap-7">
        <TextField
          label="标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          maxLength={200}
          required
          disabled={locked}
        />
        <TextField
          label="受众（可选）"
          value={audience}
          onChange={(event) => setAudience(event.target.value)}
          maxLength={100}
          placeholder="例如：管理层"
          disabled={locked}
        />
        <Select
          label="语气"
          value={tone ?? 'professional'}
          onChange={(event) => setTone(event.target.value as Tone)}
          options={TONE_OPTIONS}
          disabled={locked}
        />
        <Select
          label="页数"
          value={pageCount}
          onChange={(event) => setPageCount(Number(event.target.value))}
          options={PAGE_COUNT_OPTIONS}
          disabled={locked}
        />
        <Select
          label="主题"
          value={themeId}
          onChange={(event) => setThemeId(event.target.value)}
          options={THEME_OPTIONS}
          disabled={locked}
        />

        <div className="flex items-center gap-5">
          <Button type="submit" disabled={locked || !dirty || update.isPending || !title.trim()}>
            {update.isPending ? '保存中…' : '保存设置'}
          </Button>
          {update.isError && <span className="text-sm text-negative">保存失败。</span>}
        </div>
      </form>
    </section>
  )
}
