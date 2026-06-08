'use client'
import React, { useCallback, useMemo, useState } from 'react'
import { usePathname } from 'next/navigation'
import { AuthGate } from '@/components/auth/AuthGate'
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
  const [chatWorkflowId, setChatWorkflowId] = useState<string | null>(null)
  const [prModalOpen, setPrModalOpen] = useState(false)
  const pathname = usePathname() ?? ''
  const unchromed = UNCHROMED_PATHS.some(
    (p) => pathname === p || pathname.startsWith(p + '/'),
  )

  const openChat = useCallback((workflowId?: string) => {
    setChatWorkflowId(workflowId ?? null)
    setChatOpen(true)
  }, [])

  const closeChat = useCallback(() => {
    setChatOpen(false)
    setChatWorkflowId(null)
  }, [])

  const chatContextValue = useMemo(
    () => ({ openChat, workflowId: chatWorkflowId }),
    [openChat, chatWorkflowId],
  )

  if (unchromed) {
    return <div className="app-shell">{children}</div>
  }

  return (
    <AuthGate>
      <ChatContext.Provider value={chatContextValue}>
        <PRModalContext.Provider value={{ openPRModal: () => setPrModalOpen(true) }}>
          <div className="app-shell">
            <TopNav onNewRequest={() => setPrModalOpen(true)} />
            <main style={{ flex: 1 }}>{children}</main>
            <Footer />
            <ChatPanel
              open={chatOpen}
              onClose={closeChat}
              workflowId={chatWorkflowId}
            />
            <PRModal open={prModalOpen} onClose={() => setPrModalOpen(false)} />
          </div>
        </PRModalContext.Provider>
      </ChatContext.Provider>
    </AuthGate>
  )
}
