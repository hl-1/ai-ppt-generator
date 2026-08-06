import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import {
  commitSlideToCache,
  deckKey,
  updateSlideBlock,
  updateSlideBlockStyle,
} from '@/features/deck/api'
import {
  applyContentBody,
  contentBodyFromBlock,
  sameContent,
  sameStyle,
  styleFromBlock,
} from '@/features/deck/blockSnapshot'
import { mergeBlockCommit } from '@/features/deck/mergeBlockCommit'
import type { BlockUpdateBody, Deck, DeckSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import type { BlockStyle } from '@/render/blockStyle'
import type { EditableBlockCommit } from '@/render/types'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'conflict' | 'error'

type PendingJob =
  | { kind: 'content'; blockId: string; body: BlockUpdateBody }
  | { kind: 'style'; blockId: string; style: BlockStyle | null }

type HistoryEntry =
  | {
      kind: 'content'
      blockId: string
      before: BlockUpdateBody
      after: BlockUpdateBody
    }
  | {
      kind: 'style'
      blockId: string
      before: BlockStyle | null
      after: BlockStyle | null
    }

const MAX_HISTORY = 50

/**
 * 同一页的块保存必须串行：每次成功 revision +1，并发必然 409。
 * 内容与样式共用队列；同块同 kind 多次提交合并为最新载荷。
 * 同时维护本页撤销/重做栈。
 */
export function useSlideSaveQueue(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  const queueRef = useRef<PendingJob[]>([])
  const runningRef = useRef(false)
  const contentOverridesRef = useRef(new Map<string, BlockUpdateBody>())
  const styleOverridesRef = useRef(new Map<string, BlockStyle | null>())
  const undoStackRef = useRef<HistoryEntry[]>([])
  const redoStackRef = useRef<HistoryEntry[]>([])
  const applyingHistoryRef = useRef(false)
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const [historyTick, setHistoryTick] = useState(0)
  const savedTimerRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (savedTimerRef.current != null) window.clearTimeout(savedTimerRef.current)
    },
    [],
  )

  // 换页时清空历史：撤销栈按页隔离
  useEffect(() => {
    undoStackRef.current = []
    redoStackRef.current = []
    setHistoryTick((n) => n + 1)
  }, [slideId])

  const readSlide = useCallback((): DeckSlide | undefined => {
    const deck = queryClient.getQueryData<Deck>(deckKey(projectId))
    return deck?.slides.find((slide) => slide.id === slideId)
  }, [projectId, queryClient, slideId])

  const bumpHistory = () => setHistoryTick((n) => n + 1)

  const pushHistory = (entry: HistoryEntry) => {
    if (applyingHistoryRef.current) return
    undoStackRef.current = [...undoStackRef.current.slice(-(MAX_HISTORY - 1)), entry]
    redoStackRef.current = []
    bumpHistory()
  }

  const paintBlock = useCallback(
    (blockId: string, recipe: (block: DeckSlide['blocks'][number]) => DeckSlide['blocks'][number]) => {
      queryClient.setQueryData<Deck>(deckKey(projectId), (current) => {
        if (!current) return current
        return {
          ...current,
          slides: current.slides.map((slide) => {
            if (slide.id !== slideId) return slide
            return {
              ...slide,
              blocks: slide.blocks.map((block) =>
                block.id === blockId ? recipe(block) : block,
              ),
            }
          }),
        }
      })
    },
    [projectId, queryClient, slideId],
  )

  const enqueue = (job: PendingJob) => {
    const existing = queueRef.current.findIndex(
      (item) => item.kind === job.kind && item.blockId === job.blockId,
    )
    if (existing >= 0) queueRef.current[existing] = job
    else queueRef.current.push(job)
  }

  const pump = useCallback(async () => {
    if (runningRef.current) return
    runningRef.current = true

    while (queueRef.current.length > 0) {
      const job = queueRef.current.shift()
      if (!job) break

      const slide = readSlide()
      if (!slide) continue

      setStatus('saving')
      setError(null)

      try {
        let updated: DeckSlide
        if (job.kind === 'content') {
          const raw = contentOverridesRef.current.get(job.blockId) ?? job.body
          const body =
            raw.type === 'bullets'
              ? { ...raw, items: raw.items.filter((item) => item.trim().length > 0) }
              : raw
          updated = await updateSlideBlock(projectId, slideId, job.blockId, {
            ...body,
            revision: slide.revision,
          })
          if (
            !queueRef.current.some(
              (item) => item.kind === 'content' && item.blockId === job.blockId,
            )
          ) {
            contentOverridesRef.current.delete(job.blockId)
          }
        } else {
          const style = styleOverridesRef.current.has(job.blockId)
            ? styleOverridesRef.current.get(job.blockId)!
            : job.style
          updated = await updateSlideBlockStyle(projectId, slideId, job.blockId, {
            revision: slide.revision,
            style,
          })
          if (
            !queueRef.current.some(
              (item) => item.kind === 'style' && item.blockId === job.blockId,
            )
          ) {
            styleOverridesRef.current.delete(job.blockId)
          }
        }

        commitSlideToCache(queryClient, projectId, updated)
        if (savedTimerRef.current != null) window.clearTimeout(savedTimerRef.current)
        setStatus('saved')
        savedTimerRef.current = window.setTimeout(() => {
          setStatus((current) => (current === 'saved' ? 'idle' : current))
          savedTimerRef.current = null
        }, 1600)
      } catch (cause) {
        const message = errorMessage(cause instanceof Error ? cause : null)
        const conflict =
          cause instanceof ApiError &&
          cause.status === 409 &&
          message.includes('其他操作更新')
        setStatus(conflict ? 'conflict' : 'error')
        setError(conflict ? '页面已被其他操作更新' : message)
        if (conflict) {
          queueRef.current = []
          break
        }
      }
    }

    runningRef.current = false
  }, [projectId, queryClient, readSlide, slideId])

  const applyContent = useCallback(
    (blockId: string, body: BlockUpdateBody, record: boolean) => {
      const slide = readSlide()
      const block = slide?.blocks.find((item) => item.id === blockId)
      if (block && record) {
        const before =
          contentOverridesRef.current.get(blockId) ?? contentBodyFromBlock(block)
        if (before && !sameContent(before, body)) {
          pushHistory({ kind: 'content', blockId, before, after: body })
        }
      }

      contentOverridesRef.current.set(blockId, body)
      paintBlock(blockId, (current) => applyContentBody(current, body))
      enqueue({ kind: 'content', blockId, body })
      void pump()
    },
    [paintBlock, pump, readSlide],
  )

  const applyStyle = useCallback(
    (blockId: string, style: BlockStyle | null, record: boolean) => {
      const slide = readSlide()
      const block = slide?.blocks.find((item) => item.id === blockId)
      if (block && record) {
        const before = styleOverridesRef.current.has(blockId)
          ? styleOverridesRef.current.get(blockId)!
          : styleFromBlock(block)
        if (!sameStyle(before, style)) {
          pushHistory({ kind: 'style', blockId, before, after: style })
        }
      }

      styleOverridesRef.current.set(blockId, style)
      paintBlock(blockId, (current) => ({ ...current, style }))
      enqueue({ kind: 'style', blockId, style })
      void pump()
    },
    [paintBlock, pump, readSlide],
  )

  const commit = useCallback(
    (blockId: string, change: EditableBlockCommit) => {
      if (change.type === 'style') {
        applyStyle(blockId, change.style, true)
        return
      }

      const slide = readSlide()
      if (!slide) return
      const body = mergeBlockCommit(
        slide,
        blockId,
        change,
        contentOverridesRef.current.get(blockId),
      )
      if (!body) return
      applyContent(blockId, body, true)
    },
    [applyContent, applyStyle, readSlide],
  )

  const commitStyle = useCallback(
    (blockId: string, style: BlockStyle | null) => {
      applyStyle(blockId, style, true)
    },
    [applyStyle],
  )

  const applyEntry = useCallback(
    (entry: HistoryEntry, side: 'before' | 'after') => {
      applyingHistoryRef.current = true
      try {
        if (entry.kind === 'content') {
          applyContent(entry.blockId, entry[side], false)
        } else {
          applyStyle(entry.blockId, entry[side], false)
        }
      } finally {
        applyingHistoryRef.current = false
      }
    },
    [applyContent, applyStyle],
  )

  const undo = useCallback((): boolean => {
    const entry = undoStackRef.current.pop()
    if (!entry) return false
    redoStackRef.current.push(entry)
    bumpHistory()
    applyEntry(entry, 'before')
    return true
  }, [applyEntry])

  const redo = useCallback((): boolean => {
    const entry = redoStackRef.current.pop()
    if (!entry) return false
    undoStackRef.current.push(entry)
    bumpHistory()
    applyEntry(entry, 'after')
    return true
  }, [applyEntry])

  const refresh = useCallback(() => {
    contentOverridesRef.current.clear()
    styleOverridesRef.current.clear()
    queueRef.current = []
    undoStackRef.current = []
    redoStackRef.current = []
    setError(null)
    setStatus('idle')
    bumpHistory()
    void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
  }, [projectId, queryClient])

  return {
    commit,
    commitStyle,
    undo,
    redo,
    canUndo: undoStackRef.current.length > 0,
    canRedo: redoStackRef.current.length > 0,
    historyTick,
    status,
    error,
    refresh,
  }
}
