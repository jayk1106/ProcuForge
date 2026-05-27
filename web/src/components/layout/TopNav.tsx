'use client'
import React from 'react'
import { useRouter, usePathname } from 'next/navigation'

interface TopNavProps {
  onNewRequest: () => void
}

const tabs = [
  { id: 'flows',    label: 'Flows',    href: '/flows' },
  { id: 'vendors',  label: 'Vendors',  href: '/vendors' },
  { id: 'settings', label: 'Settings', href: '/settings' },
]

export function TopNav({ onNewRequest }: TopNavProps) {
  const pathname = usePathname()
  const router = useRouter()

  function isActive(id: string) {
    if (id === 'flows') return pathname.startsWith('/flows')
    if (id === 'vendors') return pathname.startsWith('/vendors')
    if (id === 'settings') return pathname.startsWith('/settings')
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
          <span className="t-xs faint">press ⌘K to search</span>
          <button className="btn accent" onClick={onNewRequest}>
            [ + new request ]
          </button>
          <div className="nav-user">
            <span className="dot" />
            <span>m.okafor</span>
            <span className="faint">·</span>
            <span className="faint">acme manuf.</span>
          </div>
        </div>
      </div>
    </nav>
  )
}
