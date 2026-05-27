'use client'
import React, { useState } from 'react'
import { TopNav } from './TopNav'
import { Footer } from './Footer'
import { ChatPanel } from './ChatPanel'
import { PRModal } from './PRModal'
import { ChatContext } from './ChatContext'
import { PRModalContext } from './PRModalContext'

interface ClientShellProps {
  children: React.ReactNode
}

export function ClientShell({ children }: ClientShellProps) {
  const [chatOpen, setChatOpen] = useState(false)
  const [prModalOpen, setPrModalOpen] = useState(false)

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
