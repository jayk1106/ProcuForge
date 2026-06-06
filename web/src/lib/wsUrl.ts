const API_URL = process.env.NEXT_PUBLIC_API_URL ?? 'http://localhost:8000'

/** Convert an API path into a ws:// or wss:// URL using the API origin. */
export function buildWsUrl(path: string): string {
  const wsBase = API_URL.replace(/^http/, 'ws')
  return `${wsBase}${path}`
}
