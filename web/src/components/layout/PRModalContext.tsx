'use client'
import React, { createContext, useContext } from 'react'

interface PRModalContextValue {
  openPRModal: () => void
}

export const PRModalContext = createContext<PRModalContextValue>({ openPRModal: () => {} })

export function usePRModalContext() {
  return useContext(PRModalContext)
}
