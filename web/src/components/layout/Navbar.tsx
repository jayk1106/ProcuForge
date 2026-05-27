'use client'

import Link from 'next/link'
import { usePathname } from 'next/navigation'
import { cn } from '@/lib/utils'

const NAV_LINKS = [
  { label: 'Flows', href: '/flows' },
  { label: 'Vendors', href: '/vendors' },
  { label: 'Settings', href: '/settings' },
]

export function Navbar() {
  const pathname = usePathname()

  return (
    <nav
      className="w-full border-b font-mono"
      style={{
        backgroundColor: '#F2EAD0',
        borderColor: '#CBBF9F',
      }}
    >
      <div className="mx-auto flex h-12 max-w-[1400px] items-center justify-between px-6">
        {/* Left: logo + nav links */}
        <div className="flex items-center gap-8">
          <Link
            href="/flows"
            className="text-base font-bold tracking-tight"
            style={{ color: '#7C3010' }}
          >
            procuforge~
          </Link>
          <div className="flex items-center gap-6">
            {NAV_LINKS.map((link) => {
              const isActive = pathname.startsWith(link.href)
              return (
                <Link
                  key={link.href}
                  href={link.href}
                  className={cn(
                    'text-sm transition-colors',
                    isActive
                      ? 'border-b border-current font-bold'
                      : 'hover:opacity-70'
                  )}
                  style={{
                    color: isActive ? '#1C1816' : '#7A6E5C',
                    textDecoration: 'none',
                  }}
                >
                  {link.label}
                </Link>
              )
            })}
          </div>
        </div>

        {/* Right: search hint + new request button + user chip */}
        <div className="flex items-center gap-4">
          <span className="text-xs" style={{ color: '#7A6E5C' }}>
            press ⌘K to search
          </span>
          <button
            className="cursor-pointer border px-3 py-1 text-xs font-bold text-white transition-colors"
            style={{
              backgroundColor: '#7C3010',
              borderColor: '#7C3010',
            }}
            onMouseEnter={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.backgroundColor =
                '#5F240C'
            }}
            onMouseLeave={(e) => {
              ;(e.currentTarget as HTMLButtonElement).style.backgroundColor =
                '#7C3010'
            }}
          >
            [ + new request ]
          </button>
          <div
            className="flex items-center gap-1.5 border px-2.5 py-1 text-xs"
            style={{
              borderColor: '#CBBF9F',
              color: '#1C1816',
            }}
          >
            <span className="text-[10px]" style={{ color: '#1A5C30' }}>
              •
            </span>
            <span>m.okafor · acme manuf.</span>
          </div>
        </div>
      </div>
    </nav>
  )
}
