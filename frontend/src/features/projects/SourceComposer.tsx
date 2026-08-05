import { type ChangeEvent, type FormEvent, useRef, useState } from 'react'
import { Button } from '@/components/ui/Button'
import { Textarea } from '@/components/ui/Textarea'
import { useAddTextSource, useUploadSource } from '@/features/projects/api'
import { ACCEPTED_UPLOAD } from '@/features/projects/types'
import { cn } from '@/lib/utils'

type Mode = 'topic' | 'text' | 'document'

const MODES: ReadonlyArray<{ id: Mode; label: string; hint: string }> = [
  { id: 'topic', label: '一句主题', hint: '只给方向，正文全部由模型展开。' },
  { id: 'text', label: '长文本', hint: '粘贴已有素材，按空行切分成小节。' },
  { id: 'document', label: '上传文档', hint: '支持 PDF、DOCX、Markdown、TXT，单个不超过 10 MB。' },
]

export function SourceComposer({ projectId }: { projectId: string }) {
  const [mode, setMode] = useState<Mode>('topic')
  const active = MODES.find((item) => item.id === mode)!

  return (
    <section>
      <h2 className="mb-1 text-sm font-semibold tracking-wide">添加输入材料</h2>
      <p className="mb-6 text-sm text-ink-muted">{active.hint}</p>

      <div role="tablist" aria-label="输入方式" className="mb-8 flex gap-1 border-b border-line">
        {MODES.map((item) => (
          <button
            key={item.id}
            role="tab"
            type="button"
            aria-selected={mode === item.id}
            onClick={() => setMode(item.id)}
            className={cn(
              '-mb-px border-b-2 px-4 py-2.5 text-sm transition-colors',
              mode === item.id
                ? 'border-accent text-ink'
                : 'border-transparent text-ink-muted hover:text-accent',
            )}
          >
            {item.label}
          </button>
        ))}
      </div>

      {mode === 'document' ? (
        <UploadPanel projectId={projectId} />
      ) : (
        <TextPanel projectId={projectId} mode={mode} />
      )}
    </section>
  )
}

function TextPanel({ projectId, mode }: { projectId: string; mode: 'topic' | 'text' }) {
  const [content, setContent] = useState('')
  const add = useAddTextSource(projectId)

  const submit = (event: FormEvent) => {
    event.preventDefault()
    add.mutate(
      { kind: mode, content: content.trim() },
      { onSuccess: () => setContent('') },
    )
  }

  return (
    <form onSubmit={submit} className="flex flex-col gap-5">
      <Textarea
        label={mode === 'topic' ? '主题' : '正文'}
        value={content}
        onChange={(event) => setContent(event.target.value)}
        rows={mode === 'topic' ? 2 : 10}
        maxLength={200_000}
        placeholder={
          mode === 'topic'
            ? '例如：如何把内部工具沉淀成平台能力'
            : '把调研笔记、会议纪要或已有文稿粘贴到这里。'
        }
      />
      <div className="flex items-center gap-6">
        <Button type="submit" disabled={add.isPending || !content.trim()}>
          {add.isPending ? '处理中…' : '添加'}
        </Button>
        {add.isError && <span className="text-sm text-negative">添加失败，请重试。</span>}
      </div>
    </form>
  )
}

function UploadPanel({ projectId }: { projectId: string }) {
  const inputRef = useRef<HTMLInputElement>(null)
  const [dragging, setDragging] = useState(false)
  const upload = useUploadSource(projectId)

  const send = (file: File | undefined) => {
    if (file) upload.mutate(file)
  }

  const onPick = (event: ChangeEvent<HTMLInputElement>) => {
    send(event.target.files?.[0])
    // 清空，否则连续选择同一个文件不会再触发 change
    event.target.value = ''
  }

  return (
    <div className="flex flex-col gap-4">
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={(event) => {
          event.preventDefault()
          setDragging(false)
          send(event.dataTransfer.files[0])
        }}
        className={cn(
          'flex flex-col items-center gap-4 border border-dashed px-8 py-14 text-center transition-colors',
          dragging ? 'border-accent bg-accent-soft/40' : 'border-line-strong bg-surface',
        )}
      >
        <p className="text-sm text-ink-soft">
          {upload.isPending ? '正在解析…' : '把文件拖到这里，或者'}
        </p>
        <Button type="button" onClick={() => inputRef.current?.click()} disabled={upload.isPending}>
          选择文件
        </Button>
        <p className="text-xs text-ink-muted">PDF · DOCX · Markdown · TXT，单个不超过 10 MB</p>
        <input
          ref={inputRef}
          type="file"
          accept={ACCEPTED_UPLOAD}
          onChange={onPick}
          className="sr-only"
        />
      </div>
      {upload.isError && (
        <p className="text-sm text-negative">{(upload.error as Error).message}</p>
      )}
    </div>
  )
}
