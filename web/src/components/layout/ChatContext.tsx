'use client'
import React, { createContext, useContext } from 'react'

interface ChatContextValue {
  openChat: (workflowId?: string) => void
  workflowId: string | null
}

export const ChatContext = createContext<ChatContextValue>({
  openChat: () => {},
  workflowId: null,
})

export function useChatContext() {
  return useContext(ChatContext)
}
