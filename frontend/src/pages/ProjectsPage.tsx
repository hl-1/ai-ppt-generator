import { type FormEvent, useState } from 'react'
import { Link } from 'react-router'
import { Button } from '@/components/ui/Button'
import { Select } from '@/components/ui/Select'
import { TextField } from '@/components/ui/TextField'
import { useCreateProject, useDeleteProject, useProjects } from '@/features/projects/api'
import { PAGE_COUNT_OPTIONS, THEME_OPTIONS, TONE_OPTIONS } from '@/features/projects/options'
import { STATUS_LABEL, type Project, type Tone } from '@/features/projects/types'

const DATE_FORMAT = new Intl.DateTimeFormat('zh-CN', {
  month: 'numeric',
  day: 'numeric',
  hour: '2-digit',
  minute: '2-digit',
})

export default function ProjectsPage() {
  const projects = useProjects()
  const [composing, setComposing] = useState(false)

  return (
    <>
      <section className="flex items-end justify-between border-b border-line py-16">
        <div>
          <p className="mb-4 text-xs tracking-[0.2em] text-accent uppercase">演示文稿</p>
          <h1 className="font-display text-[clamp(2rem,4vw,2.75rem)] leading-[1.3]">
            从一句主题或一份文档开始。
          </h1>
        </div>
        <Button onClick={() => setComposing((open) => !open)} aria-expanded={composing}>
          {composing ? '收起' : '新建演示文稿'}
        </Button>
      </section>

      {composing && <CreateForm onDone={() => setComposing(false)} />}

      <section className="pt-4 pb-20">
        {projects.isPending && <p className="pt-8 text-sm text-ink-muted">正在加载…</p>}
        {projects.isError && (
          <p className="pt-8 text-sm text-negative">加载失败，请刷新重试。</p>
        )}
        {projects.data?.length === 0 && (
          <p className="pt-8 text-sm text-ink-muted">还没有演示文稿，点右上角新建一个。</p>
        )}
        {projects.data && projects.data.length > 0 && (
          <ul>
            {projects.data.map((project) => (
              <ProjectRow key={project.id} project={project} />
            ))}
          </ul>
        )}
      </section>
    </>
  )
}

function ProjectRow({ project }: { project: Project }) {
  const remove = useDeleteProject()

  return (
    <li className="group flex items-center gap-6 border-b border-line py-5">
      <Link to={`/projects/${project.id}`} className="min-w-0 flex-1">
        <span className="block truncate text-[15px] font-medium transition-colors group-hover:text-accent">
          {project.title}
        </span>
        <span className="mt-1 block text-xs text-ink-muted">
          {project.page_count} 页 · {STATUS_LABEL[project.status]}
          {project.audience && ` · 面向${project.audience}`}
        </span>
      </Link>
      <span className="shrink-0 text-xs text-ink-muted tabular-nums">
        {DATE_FORMAT.format(new Date(project.updated_at))}
      </span>
      <Button
        variant="ghost"
        className="h-8 shrink-0 px-0 text-xs opacity-0 transition-opacity group-hover:opacity-100 focus-visible:opacity-100"
        disabled={remove.isPending}
        onClick={() => remove.mutate(project.id)}
      >
        删除
      </Button>
    </li>
  )
}

function CreateForm({ onDone }: { onDone: () => void }) {
  const create = useCreateProject()
  const [title, setTitle] = useState('')
  const [audience, setAudience] = useState('')
  const [tone, setTone] = useState<Tone>('professional')
  const [pageCount, setPageCount] = useState(10)
  const [themeId, setThemeId] = useState(THEME_OPTIONS[0]?.value ?? 'ivory')

  const submit = (event: FormEvent) => {
    event.preventDefault()
    create.mutate(
      {
        title: title.trim(),
        audience: audience.trim() || null,
        tone,
        page_count: pageCount,
        theme_id: themeId,
      },
      { onSuccess: onDone },
    )
  }

  return (
    <section className="border-b border-line py-10">
      <form onSubmit={submit} className="grid gap-8 md:grid-cols-2">
        <TextField
          label="标题"
          value={title}
          onChange={(event) => setTitle(event.target.value)}
          placeholder="例如：2026 上半年产品复盘"
          maxLength={200}
          required
          autoFocus
        />
        <TextField
          label="受众（可选）"
          value={audience}
          onChange={(event) => setAudience(event.target.value)}
          placeholder="例如：管理层、客户、团队内部"
          maxLength={100}
        />
        <div className="grid grid-cols-3 gap-6 md:col-span-2">
          <Select
            label="语气"
            value={tone ?? 'professional'}
            onChange={(event) => setTone(event.target.value as Tone)}
            options={TONE_OPTIONS}
          />
          <Select
            label="页数"
            value={pageCount}
            onChange={(event) => setPageCount(Number(event.target.value))}
            options={PAGE_COUNT_OPTIONS}
          />
          <Select
            label="主题"
            value={themeId}
            onChange={(event) => setThemeId(event.target.value)}
            options={THEME_OPTIONS}
          />
        </div>

        <div className="flex items-center gap-6 md:col-span-2">
          <Button type="submit" disabled={create.isPending || !title.trim()}>
            {create.isPending ? '创建中…' : '创建'}
          </Button>
          {create.isError && <span className="text-sm text-negative">创建失败，请重试。</span>}
          <span className="text-xs text-ink-muted">
            这些设置随时可改，大纲生成时才会真正生效。
          </span>
        </div>
      </form>
    </section>
  )
}
