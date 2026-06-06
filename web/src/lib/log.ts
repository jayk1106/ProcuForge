/**
 * Debug logger for the WebSocket layer.
 *
 * Gated on `NEXT_PUBLIC_WS_DEBUG=1` so production builds carry no overhead.
 * Set the env var in `web/.env.local` (and restart `next dev`) to enable
 * verbose [ws][scope] traces in the browser console.
 */
const WS_DEBUG = process.env.NEXT_PUBLIC_WS_DEBUG === '1'

export function wsLog(scope: string, msg: string, data?: unknown): void {
  if (!WS_DEBUG) return
  if (data !== undefined) {
    // eslint-disable-next-line no-console
    console.debug(`[ws][${scope}] ${msg}`, data)
  } else {
    // eslint-disable-next-line no-console
    console.debug(`[ws][${scope}] ${msg}`)
  }
}

export function isWsDebug(): boolean {
  return WS_DEBUG
}
