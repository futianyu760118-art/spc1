import { useEffect, useRef } from 'react'
import { notificationStream } from '@/services/notificationStream'
import { useAuthStore } from '@/store/auth'

const POLL_INTERVAL_MS = 60_000

export function useNotificationRefresh(enabled: boolean, refresh: () => void) {
  const originalToken = useAuthStore((s) => s.originalToken)
  const refreshRef = useRef(refresh)
  refreshRef.current = refresh

  useEffect(() => {
    if (!enabled || !originalToken) return
    let pollTimer: ReturnType<typeof setInterval> | null = null
    const refreshNow = () => refreshRef.current()
    const stopPolling = () => {
      if (pollTimer) {
        clearInterval(pollTimer)
        pollTimer = null
      }
    }
    const startPolling = () => {
      if (pollTimer) return
      pollTimer = setInterval(refreshNow, POLL_INTERVAL_MS)
    }
    const unsubscribe = notificationStream.subscribe(originalToken, (ev) => {
      if (ev.type === 'unread') refreshNow()
      else if (ev.type === 'degraded') startPolling()
      else stopPolling()
    })
    return () => {
      unsubscribe()
      stopPolling()
    }
  }, [enabled, originalToken])
}
