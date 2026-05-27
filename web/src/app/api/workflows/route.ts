import { NextRequest, NextResponse } from 'next/server'
import { mockWorkflows } from '@/lib/mock-data'
import { randomUUID } from 'crypto'

export async function GET() {
  return NextResponse.json(mockWorkflows)
}

export async function POST(request: NextRequest) {
  let body: unknown

  try {
    body = await request.json()
  } catch {
    return NextResponse.json(
      { error: 'Invalid JSON body' },
      { status: 400 }
    )
  }

  const { productId, quantity, requestedBy } = body as Record<string, unknown>

  if (!productId || quantity === undefined || !requestedBy) {
    return NextResponse.json(
      {
        error:
          'Missing required fields: productId, quantity, requestedBy are all required.',
      },
      { status: 422 }
    )
  }

  if (typeof quantity !== 'number' || quantity <= 0) {
    return NextResponse.json(
      { error: 'quantity must be a positive number' },
      { status: 422 }
    )
  }

  const sessionId = randomUUID()

  return NextResponse.json(
    { sessionId, status: 'INITIATED' },
    { status: 201 }
  )
}
