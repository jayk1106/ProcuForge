'use client'
import React, { createContext, useContext } from 'react'

interface ChatContextValue {
  openChat: () => void
}

export const ChatContext = createContext<ChatContextValue>({ openChat: () => {} })

export function useChatContext() {
  return useContext(ChatContext)
}
