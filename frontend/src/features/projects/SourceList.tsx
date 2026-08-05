import { useState } from 'react'
import { Button } from '@/components/ui/Button'
import { useDeleteSource } from '@/features/projects/api'
import {
  SOURCE_KIND_LABEL,
  type ProjectSource,
  type SourceSection,
} from '@/features/projects/types'

export function SourceList({
  projectId,
  sources,
  locked = false,
}: {
  projectId: string
  sources: ProjectSource[]
  locked?: boolean
}) {
  const totalChars = sources.reduce((sum, source) => sum + source.char_count, 0)

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold tracking-wide">已有材料</h2>
      <p className="mb-6 text-sm text-ink-muted">
        {sources.length === 0
          ? '尚未添加任何材料。'
          : `共 ${sources.length} 份，${totalChars.toLocaleString('zh-CN')} 字将进入大纲规划。`}
      </p>

      {sources.length > 0 && (
        <ul className="border-t border-line">
          {sources.map((source) => (
            <SourceItem
              key={source.id}
              projectId={projectId}
              source={source}
              locked={locked}
            />
          ))}
        </ul>
      )}
    </section>
  )
}

function SourceItem({
  projectId,
  source,
  locked,
}: {
  projectId: string
  source: ProjectSource
  locked: boolean
}) {
  const [expanded, setExpanded] = useState(false)
  const remove = useDeleteSource(projectId)

  const title = source.filename ?? source.sections[0]?.text.slice(0, 40) ?? '（空）'

  return (
    <li className="border-b border-line py-5">
      <div className="flex items-baseline gap-4">
        <span className="w-16 shrink-0 text-xs text-accent">
          {SOURCE_KIND_LABEL[source.kind]}
        </span>
        <div className="min-w-0 flex-1">
          <p className="truncate text-[15px]">{title}</p>
          <p className="mt-1 text-xs text-ink-muted">
            {source.sections.length} 个小节 · {source.char_count.toLocaleString('zh-CN')} 字
          </p>
        </div>
        <Button
          variant="ghost"
          className="h-8 shrink-0 px-0 text-xs"
          onClick={() => setExpanded((open) => !open)}
          aria-expanded={expanded}
          disabled={source.sections.length === 0}
        >
          {expanded ? '收起' : '查看解析结果'}
        </Button>
        <Button
          variant="ghost"
          className="h-8 shrink-0 px-0 text-xs"
          disabled={locked || remove.isPending}
          onClick={() => remove.mutate(source.id)}
        >
          删除
        </Button>
      </div>

      {source.warnings.length > 0 && (
        <ul className="mt-3 ml-20 space-y-1">
          {source.warnings.map((warning) => (
            <li key={warning} className="text-xs text-negative">
              {warning}
            </li>
          ))}
        </ul>
      )}

      {expanded && (
        <ol className="mt-5 ml-20 space-y-4 border-l border-line pl-5">
          {source.sections.map((section, index) => (
            <SectionPreview key={index} section={section} />
          ))}
        </ol>
      )}
    </li>
  )
}

function SectionPreview({ section }: { section: SourceSection }) {
  return (
    <li>
      <div className="flex items-baseline gap-3">
        {section.heading ? (
          <span className="text-[15px] font-medium">{section.heading}</span>
        ) : (
          <span className="text-[15px] text-ink-muted">正文段落</span>
        )}
        <span className="text-[11px] text-ink-muted">
          {section.level > 0 && `H${section.level} · `}
          {section.locator}
        </span>
      </div>
      {section.text && (
        <p className="mt-1.5 line-clamp-3 text-sm leading-relaxed whitespace-pre-line text-ink-soft">
          {section.text}
        </p>
      )}
    </li>
  )
}
