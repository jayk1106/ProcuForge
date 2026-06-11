'use client'
import React, { useState } from 'react'
import { usePathname } from 'next/navigation'
import { AuthGate } from '@/components/auth/AuthGate'
import { TopNav } from './TopNav'
import { Footer } from './Footer'
import { PRModal } from './PRModal'
import { PRModalContext } from './PRModalContext'

interface ClientShellProps {
  children: React.ReactNode
}

const UNCHROMED_PATHS = ['/login']

export function ClientShell({ children }: ClientShellProps) {
  const [prModalOpen, setPrModalOpen] = useState(false)
  const pathname = usePathname() ?? ''
  const unchromed = UNCHROMED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  )

  if (unchromed) {
    return <div className="app-shell">{children}</div>
  }

  return (
    <AuthGate>
      <PRModalContext.Provider value={{ openPRModal: () => setPrModalOpen(true) }}>
        <div className="app-shell">
          <TopNav onNewRequest={() => setPrModalOpen(true)} />
          <main style={{ flex: 1 }}>{children}</main>
          <Footer />
          <PRModal open={prModalOpen} onClose={() => setPrModalOpen(false)} />
        </div>
      </PRModalContext.Provider>
    </AuthGate>
  )
}
