'use client'

import { useEffect } from 'react'
import { usePathname, useRouter } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'

const PUBLIC_PATHS = ['/login']

function isPublic(pathname: string): boolean {
  return PUBLIC_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  )
}

interface AuthGateProps {
  children: React.ReactNode
}

export function AuthGate({ children }: AuthGateProps) {
  const pathname = usePathname() ?? ''
  const router = useRouter()
  const { me, loading } = useAuth()

  useEffect(() => {
    if (loading || isPublic(pathname)) return
    if (!me) {
      const next = encodeURIComponent(pathname || '/flows')
      router.replace(`/login?next=${next}`)
    }
  }, [loading, me, pathname, router])

  if (isPublic(pathname)) {
    return <>{children}</>
  }

  if (loading) {
    return (
      <div
        className="app-shell"
        style={{
          minHeight: '100vh',
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
        }}
      >
        <span className="t-xs faint">loading…</span>
      </div>
    )
  }

  if (!me) {
    return null
  }

  return <>{children}</>
}
