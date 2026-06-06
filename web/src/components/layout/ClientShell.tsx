'use client'
import React, { useState } from 'react'
import { usePathname } from 'next/navigation'
import { TopNav } from './TopNav'
import { Footer } from './Footer'
import { ChatPanel } from './ChatPanel'
import { PRModal } from './PRModal'
import { ChatContext } from './ChatContext'
import { PRModalContext } from './PRModalContext'

interface ClientShellProps {
  children: React.ReactNode
}

const UNCHROMED_PATHS = ['/login']

export function ClientShell({ children }: ClientShellProps) {
  const [chatOpen, setChatOpen] = useState(false)
  const [prModalOpen, setPrModalOpen] = useState(false)
  const pathname = usePathname() ?? ''
  const unchromed = UNCHROMED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  )

  if (unchromed) {
    return <div className="app-shell">{children}</div>
  }

  return (
    <ChatContext.Provider value={{ openChat: () => setChatOpen(true) }}>
      <PRModalContext.Provider value={{ openPRModal: () => setPrModalOpen(true) }}>
        <div className="app-shell">
          <TopNav onNewRequest={() => setPrModalOpen(true)} />
          <main style={{ flex: 1 }}>{children}</main>
          <Footer />
          <ChatPanel open={chatOpen} onClose={() => setChatOpen(false)} />
          <PRModal open={prModalOpen} onClose={() => setPrModalOpen(false)} />
        </div>
      </PRModalContext.Provider>
    </ChatContext.Provider>
  )
}
