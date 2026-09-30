import { ArrowLeft, ChevronLeft, ChevronRight, Download, RotateCcw } from 'lucide-react'
import { useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router'
import sample from '../../../shared/financial-tech-sample.json'
import { mergeBlockCommit } from '@/features/deck/mergeBlockCommit'
import type { DeckSlide } from '@/features/deck/types'
import { themeList } from '@/render/design'
import { SlideView } from '@/render/SlideView'
import type { Deck, EditableBlockCommit } from '@/render/types'

export default function ThemePreviewPage() {
  const { themeId = 'financial-tech' } = useParams()
  const navigate = useNavigate()
  const [deck, setDeck] = useState<Deck>(() => structuredClone(sample) as unknown as Deck)
  const [index, setIndex] = useState(0)
  const [editable, setEditable] = useState(false)
  const [selected, setSelected] = useState<string | null>(null)
  const [exporting, setExporting] = useState(false)
  const [error, setError] = useState('')
  const theme = themeList.find((item) => item.id === themeId)
  if (!theme)
    return (
      <main className="p-8">
        <h1 className="text-lg">主题不存在</h1>
        <Link to="/projects">返回项目</Link>
      </main>
    )
  const slide = deck.slides[index]
  const commit = (blockId: string, body: EditableBlockCommit) => {
    setDeck((current) => ({
      ...current,
      slides: current.slides.map((page, position) => {
        if (position !== index) return page
        const update = mergeBlockCommit(page as unknown as DeckSlide, blockId, body)
        return update
          ? {
              ...page,
              blocks: page.blocks.map((block) =>
                block.id === blockId ? { ...block, ...update } : block,
              ),
            }
          : page
      }),
    }))
  }
  const download = async () => {
    setExporting(true)
    setError('')
    try {
      const response = await fetch(`/api/v1/design/themes/${theme.id}/preview.pptx`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ ...deck, theme_id: theme.id }),
      })
      if (!response.ok) throw new Error('导出失败，请稍后重试')
      const url = URL.createObjectURL(await response.blob())
      const link = document.createElement('a')
      link.href = url
      link.download = `${deck.title}.pptx`
      link.click()
      setTimeout(() => URL.revokeObjectURL(url), 1000)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : '导出失败')
    } finally {
      setExporting(false)
    }
  }
  const iconClass =
    'inline-flex size-9 shrink-0 items-center justify-center rounded border border-line bg-surface disabled:opacity-40'
  return (
    <main className="min-h-screen bg-canvas">
      <header className="border-b border-line bg-surface">
        <div className="mx-auto flex max-w-[1280px] flex-wrap items-center gap-3 px-4 py-3 sm:px-6">
          <Link className={iconClass} to="/projects" title="返回项目" aria-label="返回项目">
            <ArrowLeft size={16} />
          </Link>
          <h1 className="mr-auto text-base font-semibold">{theme.name}</h1>
          <select
            className="h-9 max-w-full rounded border border-line bg-surface px-2 text-sm"
            aria-label="主题"
            value={theme.id}
            onChange={(event) => navigate(`/themes/${event.target.value}`)}
          >
            {themeList.map((item) => (
              <option key={item.id} value={item.id}>
                {item.name}
              </option>
            ))}
          </select>
          <label className="flex items-center gap-2 text-sm">
            <input
              type="checkbox"
              checked={editable}
              onChange={(event) => {
                setEditable(event.target.checked)
                setSelected(null)
              }}
            />
            编辑
          </label>
          <button
            className={iconClass}
            title="重置示例"
            aria-label="重置示例"
            onClick={() => {
              setDeck(structuredClone(sample) as unknown as Deck)
              setSelected(null)
            }}
          >
            <RotateCcw size={16} />
          </button>
          <button
            className={iconClass}
            title="导出 PPTX"
            aria-label="导出 PPTX"
            disabled={exporting}
            onClick={() => void download()}
          >
            <Download size={16} />
          </button>
        </div>
      </header>
      {error && (
        <p role="alert" className="mx-auto max-w-[1280px] px-6 pt-3 text-sm text-negative">
          {error}
        </p>
      )}
      <section className="mx-auto max-w-[1280px] px-4 py-5 sm:px-6">
        <div className="mb-4 flex items-center justify-between gap-3">
          <h2 className="text-sm font-medium">{deck.title}</h2>
          <div className="flex shrink-0 items-center gap-2">
            <button
              className={iconClass}
              title="上一页"
              aria-label="上一页"
              disabled={index === 0}
              onClick={() => {
                setIndex(index - 1)
                setSelected(null)
              }}
            >
              <ChevronLeft size={16} />
            </button>
            <span className="w-10 text-center text-xs tabular-nums">
              {index + 1} / {deck.slides.length}
            </span>
            <button
              className={iconClass}
              title="下一页"
              aria-label="下一页"
              disabled={index === deck.slides.length - 1}
              onClick={() => {
                setIndex(index + 1)
                setSelected(null)
              }}
            >
              <ChevronRight size={16} />
            </button>
          </div>
        </div>
        <SlideView
          slide={slide}
          theme={theme}
          slideIndex={index}
          editable={editable}
          selectedBlockId={selected}
          onSelectBlock={setSelected}
          onCommit={commit}
        />
        <nav aria-label="示例页面" className="mt-4 grid grid-cols-3 gap-3">
          {deck.slides.map((page, position) => (
            <button
              key={page.id}
              type="button"
              aria-label={`第 ${position + 1} 页`}
              aria-pressed={position === index}
              className={`min-w-0 overflow-hidden rounded border ${index === position ? 'border-accent ring-1 ring-accent' : 'border-line'}`}
              onClick={() => {
                setIndex(position)
                setSelected(null)
              }}
            >
              <div className="pointer-events-none">
                <SlideView slide={page} theme={theme} slideIndex={position} />
              </div>
            </button>
          ))}
        </nav>
      </section>
    </main>
  )
}
