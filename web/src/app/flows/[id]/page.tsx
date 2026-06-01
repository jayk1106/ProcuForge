import React from 'react'
import { FlowDetailClient } from '@/components/flow-detail/FlowDetailClient'

interface FlowDetailPageProps {
  params: Promise<{ id: string }>
}

export default async function FlowDetailPage({ params }: FlowDetailPageProps) {
  const { id } = await params
  return <FlowDetailClient workflowId={id} />
}
