'use client'
import React from 'react'
import { useRouter, usePathname } from 'next/navigation'
import { useAuth } from '@/hooks/useAuth'

interface TopNavProps {
  onNewRequest: () => void
}

const tabs = [
  { id: 'flows',    label: 'Requests', href: '/flows' },
  { id: 'vendors',  label: 'Vendors',  href: '/vendors' },
]

export function TopNav({ onNewRequest }: TopNavProps) {
  const pathname = usePathname()
  const router = useRouter()
  const { me, logout } = useAuth()

  function isActive(id: string) {
    if (id === 'flows') return pathname.startsWith('/flows')
    if (id === 'vendors') return pathname.startsWith('/vendors')
    return false
  }

  return (
    <nav className="topnav">
      <div className="viewport topnav-inner">
        <a
          className="wordmark"
          onClick={() => router.push('/flows')}
          style={{ cursor: 'pointer' }}
        >
          procuforge<span className="tilde">~</span>
        </a>
        <div className="nav-tabs">
          {tabs.map((t) => (
            <button
              key={t.id}
              className={isActive(t.id) ? 'active' : ''}
              onClick={() => router.push(t.href)}
            >
              {t.label}
            </button>
          ))}
        </div>
        <div className="nav-right">
          <button className="btn accent" onClick={onNewRequest}>
            [ + new request ]
          </button>
          <div
            className="nav-user"
            title={
              me
                ? `${me.user.name}${me.user.email ? ` <${me.user.email}>` : ''} · ${me.org.name}`
                : 'loading…'
            }
          >
            <span className="dot" />
            <span>{me?.user.name ?? '…'}</span>
            <span className="faint">·</span>
            <span className="faint">{me?.org.name ?? ''}</span>
          </div>
          <button
            className="btn ghost tiny"
            onClick={() => { void logout() }}
            title="sign out"
          >
            [ logout ]
          </button>
        </div>
      </div>
    </nav>
  )
}
