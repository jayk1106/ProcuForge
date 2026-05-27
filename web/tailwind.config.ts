import type { Config } from 'tailwindcss'

const config: Config = {
  content: ['./src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        cream: '#F2EAD0',
        rust: {
          DEFAULT: '#7C3010',
          dark: '#5F240C',
          active: '#8B3A0F',
        },
        ink: '#1C1816',
        muted: '#7A6E5C',
        border: '#CBBF9F',
        dot: {
          filled: '#3A2E22',
          active: '#8B3A0F',
          empty: '#C4B898',
        },
        complete: '#1A5C30',
      },
      fontFamily: {
        mono: ['var(--font-space-mono)', 'ui-monospace', 'monospace'],
      },
    },
  },
  plugins: [],
}

export default config
