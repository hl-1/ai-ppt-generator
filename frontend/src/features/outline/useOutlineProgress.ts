import { useEffect, useState } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { tokenStore } from '@/features/auth/token'
import { outlineKey } from '@/features/outline/api'
import type { OutlineProgressEvent } from '@/features/outline/types'

const RECONNECT_DELAY_MS = 1_000

export function useOutlineProgress(projectId: string, active: boolean) {
  const queryClient = useQueryClient()
  const [event, setEvent] = useState<OutlineProgressEvent | null>(null)
  const [connectionError, setConnectionError] = useState(false)

  useEffect(() => {
    if (!active) {
      setConnectionError(false)
      return
    }

    const controller = new AbortController()

    const connect = async () => {
      while (!controller.signal.aborted) {
        try {
          await consumeEventStream(projectId, controller.signal, (next) => {
            setEvent(next)
            setConnectionError(false)
            if (next.type === 'completed' || next.type === 'failed') {
              void queryClient.invalidateQueries({ queryKey: outlineKey(projectId) })
            }
          })
        } catch {
          if (controller.signal.aborted) return
          setConnectionError(true)
        }

        await delay(RECONNECT_DELAY_MS, controller.signal)
      }
    }

    void connect()
    return () => controller.abort()
  }, [active, projectId, queryClient])

  return { event, connectionError }
}

async function consumeEventStream(
  projectId: string,
  signal: AbortSignal,
  onEvent: (event: OutlineProgressEvent) => void,
) {
  const token = tokenStore.get()
  const response = await fetch(`/api/v1/projects/${projectId}/outline/events`, {
    headers: {
      Accept: 'text/event-stream',
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    signal,
  })
  if (!response.ok || !response.body) {
    throw new Error(`SSE connection failed: ${response.status}`)
  }

  const reader = response.body.getReader()
  const decoder = new TextDecoder()
  let buffer = ''

  while (!signal.aborted) {
    const { done, value } = await reader.read()
    if (done) return
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n/g, '\n')

    let boundary = buffer.indexOf('\n\n')
    while (boundary >= 0) {
      const frame = buffer.slice(0, boundary)
      buffer = buffer.slice(boundary + 2)
      const data = frame
        .split('\n')
        .filter((line) => line.startsWith('data:'))
        .map((line) => line.slice(5).trimStart())
        .join('\n')
      if (data) onEvent(JSON.parse(data) as OutlineProgressEvent)
      boundary = buffer.indexOf('\n\n')
    }
  }
}

function delay(milliseconds: number, signal: AbortSignal) {
  return new Promise<void>((resolve) => {
    if (signal.aborted) {
      resolve()
      return
    }
    const timer = window.setTimeout(resolve, milliseconds)
    signal.addEventListener(
      'abort',
      () => {
        window.clearTimeout(timer)
        resolve()
      },
      { once: true },
    )
  })
}
