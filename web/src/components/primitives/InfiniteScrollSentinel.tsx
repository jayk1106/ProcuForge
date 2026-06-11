'use client'
import React, { useEffect, useRef } from 'react'

interface InfiniteScrollSentinelProps {
  onVisible: () => void
  disabled?: boolean
  rootMargin?: string
}

/**
 * Renders a 1px div and calls onVisible when it scrolls into view. Parents
 * are expected to gate firing with `disabled` when there's nothing left to
 * fetch (no more pages or a load is already in flight). For table layouts,
 * wrap this inside a <tr><td colSpan={N}>...</td></tr>.
 */
export function InfiniteScrollSentinel({
  onVisible,
  disabled = false,
  rootMargin = '200px',
}: InfiniteScrollSentinelProps) {
  const ref = useRef<HTMLDivElement | null>(null)
  const cbRef = useRef(onVisible)
  cbRef.current = onVisible

  useEffect(() => {
    if (disabled) return
    const el = ref.current
    if (!el) return
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            cbRef.current()
          }
        }
      },
      { rootMargin },
    )
    observer.observe(el)
    return () => observer.disconnect()
  }, [disabled, rootMargin])

  return <div ref={ref} aria-hidden style={{ height: 1, width: '100%' }} />
}
