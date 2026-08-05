import { useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'
import { ApiError } from '@/api/client'
import { deckKey, updateSlideBlock } from '@/features/deck/api'
import { replaceSlideInDeck } from '@/features/deck/cache'
import { mergeBlockCommit } from '@/features/deck/mergeBlockCommit'
import type { BlockUpdateBody, Deck, DeckSlide } from '@/features/deck/types'
import { errorMessage } from '@/lib/errors'
import type { EditableBlockCommit } from '@/render/types'

export type SaveStatus = 'idle' | 'saving' | 'saved' | 'conflict' | 'error'

interface PendingJob {
  blockId: string
  body: BlockUpdateBody
}

/**
 * 同一页的块保存必须串行：每次成功 revision +1，并发必然 409。
 * 同块多次提交合并为最新载荷，跨块按入队顺序依次发出。
 */
export function useSlideSaveQueue(projectId: string, slideId: string) {
  const queryClient = useQueryClient()
  const queueRef = useRef<PendingJob[]>([])
  const runningRef = useRef(false)
  const overridesRef = useRef(new Map<string, BlockUpdateBody>())
  const [status, setStatus] = useState<SaveStatus>('idle')
  const [error, setError] = useState<string | null>(null)
  const savedTimerRef = useRef<number | null>(null)

  useEffect(
    () => () => {
      if (savedTimerRef.current != null) window.clearTimeout(savedTimerRef.current)
    },
    [],
  )

  const readSlide = useCallback((): DeckSlide | undefined => {
    const deck = queryClient.getQueryData<Deck>(deckKey(projectId))
    return deck?.slides.find((slide) => slide.id === slideId)
  }, [projectId, queryClient, slideId])

  const pump = useCallback(async () => {
    if (runningRef.current) return
    runningRef.current = true

    while (queueRef.current.length > 0) {
      const job = queueRef.current.shift()
      if (!job) break

      const slide = readSlide()
      if (!slide) continue

      const raw = overridesRef.current.get(job.blockId) ?? job.body
      const body =
        raw.type === 'bullets'
          ? { ...raw, items: raw.items.filter((item) => item.trim().length > 0) }
          : raw
      setStatus('saving')
      setError(null)

      try {
        const updated = await updateSlideBlock(projectId, slideId, job.blockId, {
          ...body,
          revision: slide.revision,
        })
        queryClient.setQueryData<Deck>(deckKey(projectId), (current) =>
          replaceSlideInDeck(current, updated),
        )
        if (!queueRef.current.some((item) => item.blockId === job.blockId)) {
          overridesRef.current.delete(job.blockId)
        }
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

  const commit = useCallback(
    (blockId: string, change: EditableBlockCommit) => {
      const slide = readSlide()
      if (!slide) return
      const body = mergeBlockCommit(
        slide,
        blockId,
        change,
        overridesRef.current.get(blockId),
      )
      if (!body) return

      overridesRef.current.set(blockId, body)
      const existing = queueRef.current.findIndex((job) => job.blockId === blockId)
      if (existing >= 0) queueRef.current[existing] = { blockId, body }
      else queueRef.current.push({ blockId, body })
      void pump()
    },
    [pump, readSlide],
  )

  const refresh = useCallback(() => {
    overridesRef.current.clear()
    queueRef.current = []
    setError(null)
    setStatus('idle')
    void queryClient.invalidateQueries({ queryKey: deckKey(projectId) })
  }, [projectId, queryClient])

  return { commit, status, error, refresh }
}
