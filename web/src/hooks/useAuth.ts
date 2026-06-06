'use client'

import { useCallback, useEffect, useState } from 'react'
import { getMe, logout as apiLogout, UnauthorizedError } from '@/lib/api-client'
import type { MeResponse } from '@/types/auth'

interface UseAuthResult {
  me: MeResponse | null
  loading: boolean
  logout: () => Promise<void>
}

export function useAuth(): UseAuthResult {
  const [me, setMe] = useState<MeResponse | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    getMe()
      .then((next) => {
        if (!cancelled) setMe(next)
      })
      .catch((err) => {
        if (cancelled) return
        if (!(err instanceof UnauthorizedError)) {
          // Non-401 errors (network etc.) — surface to console but don't
          // bounce; the middleware will still redirect on next navigation.
          // eslint-disable-next-line no-console
          console.warn('[auth] getMe failed', err)
        }
        setMe(null)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [])

  const logout = useCallback(async () => {
    try {
      await apiLogout()
    } finally {
      setMe(null)
      if (typeof window !== 'undefined') {
        window.location.href = '/login'
      }
    }
  }, [])

  return { me, loading, logout }
}
