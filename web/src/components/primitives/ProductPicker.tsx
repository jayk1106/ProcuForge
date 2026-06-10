'use client'

import React, { useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
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
  const anchorRef = useRef<HTMLDivElement>(null)
  const [query, setQuery] = useState('')
  const [open, setOpen] = useState(false)
  const [options, setOptions] = useState<ProductOption[]>([])
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const [anchorRect, setAnchorRect] = useState<{ left: number; top: number; width: number } | null>(null)
  const [mounted, setMounted] = useState(false)

  const debouncedQuery = useDebouncedValue(query, 300)

  const displayValue = open ? query : selected ? optionLabel(selected) : query

  useEffect(() => {
    setMounted(true)
  }, [])

  useLayoutEffect(() => {
    if (!open) return
    function updateRect() {
      const el = anchorRef.current
      if (!el) return
      const r = el.getBoundingClientRect()
      setAnchorRect({ left: r.left, top: r.bottom, width: r.width })
    }
    updateRect()
    window.addEventListener('resize', updateRect)
    window.addEventListener('scroll', updateRect, true)
    return () => {
      window.removeEventListener('resize', updateRect)
      window.removeEventListener('scroll', updateRect, true)
    }
  }, [open])

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
      const target = e.target as Node
      if (containerRef.current?.contains(target)) return
      if (
        target instanceof Element &&
        target.closest(`[data-product-picker-list="${listId}"]`)
      ) {
        return
      }
      setOpen(false)
    }
    document.addEventListener('mousedown', onDocClick)
    return () => document.removeEventListener('mousedown', onDocClick)
  }, [listId])

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

  const dropdown = open && anchorRect && mounted ? createPortal(
    <div
      id={listId}
      role="listbox"
      data-product-picker-list={listId}
      className="box box-pad"
      style={{
        position: 'fixed',
        zIndex: 1000,
        left: anchorRect.left,
        top: anchorRect.top + 4,
        width: anchorRect.width,
        maxHeight: 260,
        overflowY: 'auto',
        background: 'var(--bg)',
        border: '1px solid var(--rule-strong)',
        boxShadow: '0 8px 24px rgba(0,0,0,0.18)',
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
    </div>,
    document.body,
  ) : null

  return (
    <div ref={containerRef} style={{ position: 'relative' }}>
      <div ref={anchorRef}>
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
      </div>

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

      {dropdown}
    </div>
  )
}
