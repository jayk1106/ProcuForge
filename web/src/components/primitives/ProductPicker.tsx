'use client'

import React, { useCallback, useEffect, useId, useRef, useState } from 'react'
import { searchProducts } from '@/lib/api-client'
import { useDebouncedValue } from '@/lib/useDebouncedValue'
import type { ProductOption } from '@/types/product'
import { Field } from '@/components/primitives/Field'

interface ProductPickerProps {
  value: string
  selected: ProductOption | null
  onChange: (productId: string, product: ProductOption | null) => void
  disabled?: boolean
}

function formatPriceHint(product: ProductOption): string {
  const { currency, min, max } = product.estimatedPriceRange
  return `${currency} ${min.toLocaleString()}–${max.toLocaleString()} / unit`
}

function optionLabel(product: ProductOption): string {
  return `${product.name} · ${product.brand}`
}

export function ProductPicker({ value, selected, onChange, disabled }: ProductPickerProps) {
  const listId = useId()
  const containerRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<ProductOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const debouncedQuery = useDebouncedValue(query, 300)

  const displayValue = open ? query : selected ? optionLabel(selected) : query

  const load = useCallback(async (q: string) => {
    setLoading(true)
    setError(null)
    try {
      const items = await searchProducts(q)
      setOptions(items)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Failed to load products')
      setOptions([])
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    if (!open) return
    load(debouncedQuery)
  }, [open, debouncedQuery, load])

  useEffect(() => {
    function onDocClick(e: MouseEvent) {
      if (!containerRef.current?.contains(e.target as Node)) {
        setOpen(false)
      }
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [])

  function handleFocus() {
    if (disabled) return
    setOpen(true)
    if (selected && !query) {
      setQuery('')
    }
  }

  function handleSelect(product: ProductOption) {
    onChange(product.id, product)
    setQuery('')
    setOpen(false)
  }

  function handleClear() {
    onChange('', null)
    setQuery('')
    setOpen(true)
    load('')
  }

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <Field label="Product" required hint="Search catalog by name or brand">
        <input
          type="text"
          role="combobox"
          aria-expanded={open}
          aria-controls={listId}
          aria-autocomplete="list"
          disabled={disabled}
          value={displayValue}
          placeholder="Search products…"
          onFocus={handleFocus}
          onChange={(e) => {
            setQuery(e.target.value)
            setOpen(true)
            if (value) onChange('', null)
          }}
          style={{
            flex: 1,
            border: 0,
            outline: 0,
            background: 'transparent',
            fontFamily: 'inherit',
            fontSize: 'inherit',
            padding: '6px 0',
            minWidth: 0,
          }}
        />
      </Field>

      {value && !open && (
        <button
          type="button"
          className="btn tiny"
          style={{ marginTop: 4 }}
          onClick={handleClear}
          disabled={disabled}
        >
          [ clear selection ]
        </button>
      )}

      {open && (
        <div
          id={listId}
          role="listbox"
          className="box box-pad"
          style={{
            position: 'absolute',
            zIndex: 20,
            left: 0,
            right: 0,
            marginTop: 4,
            maxHeight: 220,
            overflowY: 'auto',
            background: 'var(--surface)',
            border: '1px solid var(--border)',
          }}
        >
          {loading && <div className="t-sm muted">loading…</div>}
          {error && <div className="t-sm accent">{error}</div>}
          {!loading && !error && options.length === 0 && (
            <div className="t-sm muted">No products match.</div>
          )}
          {!loading &&
            options.map((p) => (
              <button
                key={p.id}
                type="button"
                role="option"
                aria-selected={p.id === value}
                className="btn"
                style={{
                  display: 'block',
                  width: '100%',
                  textAlign: 'left',
                  marginBottom: 4,
                  fontWeight: p.id === value ? 600 : 400,
                }}
                onMouseDown={(e) => e.preventDefault()}
                onClick={() => handleSelect(p)}
              >
                <div>{optionLabel(p)}</div>
                <div className="t-xs faint">{formatPriceHint(p)}</div>
              </button>
            ))}
        </div>
      )}
    </div>
  )
}
