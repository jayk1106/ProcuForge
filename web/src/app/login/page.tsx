'use client'

import { Suspense, useState } from 'react'
import { useRouter, useSearchParams } from 'next/navigation'
import { login, UnauthorizedError } from '@/lib/api-client'

function LoginForm() {
  const router = useRouter()
  const searchParams = useSearchParams()
  const next = searchParams.get('next') || '/flows'

  const [password, setPassword] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [submitting, setSubmitting] = useState(false)

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault()
    if (!password) return
    setSubmitting(true)
    setError(null)
    try {
      await login({ password })
      router.replace(next)
    } catch (err) {
      if (err instanceof UnauthorizedError) {
        setError('invalid credentials')
      } else {
        setError(err instanceof Error ? err.message : 'login failed')
      }
      setSubmitting(false)
    }
  }

  return (
    <div
      style={{
        minHeight: '100vh',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        padding: 24,
      }}
    >
      <form
        onSubmit={handleSubmit}
        className="box box-pad"
        style={{
          width: '100%',
          maxWidth: 360,
          display: 'flex',
          flexDirection: 'column',
          gap: 16,
        }}
      >
        <div>
          <div className="wordmark" style={{ fontSize: 20 }}>
            procuforge<span className="tilde">~</span>
          </div>
          <div className="t-xs faint" style={{ marginTop: 4 }}>
            sign in to continue
          </div>
        </div>

        <div className="field">
          <label htmlFor="password">password</label>
          <div className="ctl">
            <span className="br">[</span>
            <input
              id="password"
              name="password"
              type="password"
              autoComplete="current-password"
              autoFocus
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              disabled={submitting}
            />
            <span className="br">]</span>
          </div>
        </div>

        {error && (
          <div className="t-xs" style={{ color: 'var(--accent-ink)' }}>
            {error}
          </div>
        )}

        <button
          type="submit"
          className="btn primary lg"
          disabled={submitting || !password}
        >
          {submitting ? '[ signing in… ]' : '[ sign in ]'}
        </button>
      </form>
    </div>
  )
}

export default function LoginPage() {
  return (
    <Suspense fallback={null}>
      <LoginForm />
    </Suspense>
  )
}
