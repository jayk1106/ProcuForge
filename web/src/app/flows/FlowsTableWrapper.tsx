'use client'
import React from 'react'
import { FlowsTable } from '@/components/flows/FlowsTable'
import { usePRModalContext } from '@/components/layout/PRModalContext'

export function FlowsTableWrapper() {
  const { openPRModal } = usePRModalContext()
  return <FlowsTable onNewRequest={openPRModal} />
}
