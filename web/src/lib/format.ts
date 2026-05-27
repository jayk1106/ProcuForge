export function fmtMoney(n: number | null | undefined): string {
  if (n == null) return '—'
  return '$' + n.toLocaleString('en-US')
}

export function fmtDelta(n: number | null | undefined): string {
  if (n == null) return '—'
  const sign = n > 0 ? '+' : n < 0 ? '−' : ''
  return `${sign}${fmtMoney(Math.abs(n))}`
}
