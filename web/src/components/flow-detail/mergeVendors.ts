import type { ActiveVendor } from '@/types'

const TERMINAL_STATUSES: ReadonlySet<ActiveVendor['status']> = new Set([
  'WON',
  'LOST',
  'WALKED_AWAY',
])

function pickFreshest(prev: ActiveVendor, next: ActiveVendor): ActiveVendor {
  // A terminal status can't be undone by a stale snapshot from a sibling
  // parallel tool that didn't observe the terminating write yet.
  if (TERMINAL_STATUSES.has(prev.status) && !TERMINAL_STATUSES.has(next.status)) {
    return prev
  }
  // Thread length grows monotonically per vendor; a shorter incoming thread
  // means the snapshot predates the latest turn we've already rendered.
  if (next.thread.length < prev.thread.length) return prev
  return next
}

/**
 * Union `prev` and `next` by `vendor.id`, preserving prev's order and
 * appending vendors that are new in `next`. Used to defend the negotiation
 * board against WS frames where one of the buyer's parallel negotiator tools
 * broadcast a snapshot that omits a sibling tool's vendor.
 */
export function mergeVendorsById(
  prev: ActiveVendor[],
  next: ActiveVendor[],
): ActiveVendor[] {
  const nextById = new Map(next.map((v) => [v.id, v]))
  const prevIds = new Set(prev.map((v) => v.id))

  const merged: ActiveVendor[] = prev.map((p) => {
    const n = nextById.get(p.id)
    return n === undefined ? p : pickFreshest(p, n)
  })

  for (const n of next) {
    if (!prevIds.has(n.id)) merged.push(n)
  }

  return merged
}
