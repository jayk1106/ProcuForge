'use client'
import React from 'react'
import { FlowsTable } from '@/components/flows/FlowsTable'
import { usePRModalContext } from '@/components/layout/PRModalContext'
import type { WorkflowRow } from '@/types/workflow'

interface FlowsTableWrapperProps {
  onLoaded?: (rows: WorkflowRow[]) => void
}

export function FlowsTableWrapper({ onLoaded }: FlowsTableWrapperProps) {
  const { openPRModal } = usePRModalContext()
  return <FlowsTable onNewRequest={openPRModal} onLoaded={onLoaded} />
}
