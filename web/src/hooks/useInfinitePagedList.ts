'use client'
import { useCallback, useEffect, useRef, useState } from 'react'

export interface PagedFetchResult<T> {
  items: T[]
  nextCursor: string | null
}

export interface InfinitePagedListState<T> {
  items: T[]
  loading: boolean
  loadingMore: boolean
  error: string | null
  hasMore: boolean
  loadMore: () => void
  refresh: () => void
}

export function useInfinitePagedList<T, F>(
  fetcher: (opts: { cursor?: string | null; filter: F }) => Promise<PagedFetchResult<T>>,
  filter: F,
): InfinitePagedListState<T> {
  const [items, setItems] = useState<T[]>([])
  const [cursor, setCursor] = useState<string | null>(null)
  const [hasMore, setHasMore] = useState(true)
  const [loading, setLoading] = useState(true)
  const [loadingMore, setLoadingMore] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [refreshTick, setRefreshTick] = useState(0)

  // Stable identity for the filter so we can compare across renders.
  const filterKey = JSON.stringify(filter)

  // Latest in-flight request ID — stale responses are dropped if a newer
  // request has been issued (filter change, refresh, etc.).
  const requestSeq = useRef(0)

  // First-page (or filter-change / refresh) load.
  useEffect(() => {
    const seq = ++requestSeq.current
    setLoading(true)
    setError(null)
    setItems([])
    setCursor(null)
    setHasMore(true)
    fetcher({ cursor: null, filter })
      .then((res) => {
        if (requestSeq.current !== seq) return
        setItems(res.items)
        setCursor(res.nextCursor)
        setHasMore(res.nextCursor !== null)
      })
      .catch((e: unknown) => {
        if (requestSeq.current !== seq) return
        setError(e instanceof Error ? e.message : 'Failed to load')
      })
      .finally(() => {
        if (requestSeq.current !== seq) return
        setLoading(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filterKey, refreshTick])

  const loadMore = useCallback(() => {
    if (loading || loadingMore || !hasMore || !cursor) return
    const seq = ++requestSeq.current
    setLoadingMore(true)
    setError(null)
    fetcher({ cursor, filter })
      .then((res) => {
        if (requestSeq.current !== seq) return
        setItems((prev) => prev.concat(res.items))
        setCursor(res.nextCursor)
        setHasMore(res.nextCursor !== null)
      })
      .catch((e: unknown) => {
        if (requestSeq.current !== seq) return
        setError(e instanceof Error ? e.message : 'Failed to load more')
      })
      .finally(() => {
        if (requestSeq.current !== seq) return
        setLoadingMore(false)
      })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [cursor, hasMore, loading, loadingMore, filterKey])

  const refresh = useCallback(() => setRefreshTick((n) => n + 1), [])

  return { items, loading, loadingMore, error, hasMore, loadMore, refresh }
}
