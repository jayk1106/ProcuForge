import React from 'react'
import { VendorDetailClient } from '@/components/vendors/VendorDetailClient'

interface VendorDetailPageProps {
  params: Promise<{ id: string }>
}

export default async function VendorDetailPage({ params }: VendorDetailPageProps) {
  const { id } = await params
  return <VendorDetailClient rfqId={id} />
}
