'use client'

import React, { useEffect, useState } from 'react'
import { useRouter } from 'next/navigation'
import { startWorkflow } from '@/lib/api-client'
import { Field } from '@/components/primitives/Field'
import { PfSelect } from '@/components/primitives/PfSelect'
import { ProductPicker } from '@/components/primitives/ProductPicker'
import { AsciiRule } from '@/components/primitives/AsciiRule'
import type { ProductOption } from '@/types/product'

interface PRModalProps {
  open: boolean
  onClose: () => void
}

type Urgency = 'low' | 'normal' | 'high' | 'emergency'

interface DeliveryState {
  address: string
  city: string
  state: string
  country: string
  pincode: string
}

interface FormState {
  productId: string
  selectedProduct: ProductOption | null
  quantity: number
  purpose: string
  requiredBy: string
  urgency: Urgency
  budgetCeiling: number
  currency: string
  delivery: DeliveryState
  buyerNotes: string
  approvalRequired: boolean
}

function defaultNeedBy(): string {
  return new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10)
}

function initialForm(): FormState {
  return {
    productId: '',
    selectedProduct: null,
    quantity: 1,
    purpose: '',
    requiredBy: defaultNeedBy(),
    urgency: 'normal',
    budgetCeiling: 0,
    currency: 'USD',
    delivery: {
      address: '',
      city: '',
      state: '',
      country: 'US',
      pincode: '',
    },
    buyerNotes: '',
    approvalRequired: false,
  }
}

function suggestBudget(product: ProductOption, quantity: number): number {
  return Math.ceil(product.estimatedPriceRange.max * quantity)
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10)
}

export function PRModal({ open, onClose }: PRModalProps) {
  const router = useRouter()
  const [step, setStep] = useState(1)
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState<string | null>(null)
  const [stepError, setStepError] = useState<string | null>(null)
  const [form, setForm] = useState<FormState>(initialForm)

  useEffect(() => {
    if (!open) {
      setStep(1)
      setForm(initialForm())
      setSubmitError(null)
      setStepError(null)
    }
  }, [open])

  function set<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  function setDelivery<K extends keyof DeliveryState>(k: K, v: DeliveryState[K]) {
    setForm((f) => ({ ...f, delivery: { ...f.delivery, [k]: v } }))
  }

  function handleProductChange(productId: string, product: ProductOption | null) {
    setForm((f) => {
      const next: FormState = { ...f, productId, selectedProduct: product }
      if (product) {
        next.currency = product.estimatedPriceRange.currency
        next.budgetCeiling = suggestBudget(product, f.quantity > 0 ? f.quantity : 1)
      }
      return next
    })
  }

  function handleQuantityChange(raw: number) {
    const quantity = Number.isFinite(raw) && raw > 0 ? raw : 1
    setForm((f) => {
      const next = { ...f, quantity }
      if (f.selectedProduct) {
        next.budgetCeiling = suggestBudget(f.selectedProduct, quantity)
      }
      return next
    })
  }

  function validateStep(targetStep: number): string | null {
    if (targetStep >= 2) {
      if (!form.productId || !form.selectedProduct) return 'Select a product.'
      if (!Number.isFinite(form.quantity) || form.quantity <= 0) return 'Quantity must be greater than 0.'
    }
    if (targetStep >= 3) {
      const d = form.delivery
      if (!d.address.trim() || !d.city.trim() || !d.state.trim() || !d.country.trim() || !d.pincode.trim()) {
        return 'Complete all delivery location fields.'
      }
      if (!form.requiredBy || form.requiredBy < todayIso()) {
        return 'Need-by date must be today or later.'
      }
      if (!Number.isFinite(form.budgetCeiling) || form.budgetCeiling <= 0) {
        return 'Budget ceiling must be greater than 0.'
      }
      if (!form.currency.trim() || form.currency.length !== 3) {
        return 'Currency must be a 3-letter ISO code.'
      }
    }
    return null
  }

  function goNext() {
    const err = validateStep(step + 1)
    if (err) {
      setStepError(err)
      return
    }
    setStepError(null)
    setStep(step + 1)
  }

  async function handleSubmit() {
    const err = validateStep(3)
    if (err) {
      setStepError(err)
      return
    }
    setSubmitting(true)
    setSubmitError(null)
    setStepError(null)
    try {
      const purpose = form.purpose.trim()
      const notes = form.buyerNotes.trim()
      const result = await startWorkflow({
        product_id: form.productId,
        quantity: form.quantity,
        required_by: form.requiredBy,
        delivery_location: {
          address: form.delivery.address.trim(),
          city: form.delivery.city.trim(),
          state: form.delivery.state.trim(),
          country: form.delivery.country.trim(),
          pincode: form.delivery.pincode.trim(),
        },
        urgency: form.urgency,
        budget_ceiling: form.budgetCeiling,
        currency: form.currency.trim().toUpperCase(),
        purpose: purpose || undefined,
        buyer_notes: notes ? [notes] : undefined,
        approval_required: form.approvalRequired,
      })
      onClose()
      router.push(`/flows/${result.workflow_id}`)
    } catch (e) {
      setSubmitError(e instanceof Error ? e.message : 'Failed to start workflow')
    } finally {
      setSubmitting(false)
    }
  }

  if (!open) return null

  const product = form.selectedProduct
  const urgencyLabels: Record<Urgency, string> = {
    low: 'low',
    normal: 'normal',
    high: 'high',
    emergency: 'emergency',
  }

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="t-xs upper muted">New purchase request</div>
            <div className="page-title" style={{ fontSize: 'var(--t-xl)', marginTop: 4 }}>
              Create request
            </div>
            <div className="t-sm muted" style={{ marginTop: 4 }}>
              Submit to start the buyer agent workflow for this procurement.
            </div>
          </div>
          <button type="button" className="btn ghost" onClick={onClose}>
            [ × close ]
          </button>
        </div>

        <div className="row" style={{ gap: 6, fontSize: 'var(--t-xs)', color: 'var(--muted)', marginBottom: 18 }}>
          <span className={step >= 1 ? 'ink' : ''}>① product</span>
          <span className="sep-dot">────</span>
          <span className={step >= 2 ? 'ink' : ''}>② terms</span>
          <span className="sep-dot">────</span>
          <span className={step >= 3 ? 'ink' : ''}>③ review</span>
        </div>

        {step === 1 && (
          <div className="col" style={{ gap: 18 }}>
            <ProductPicker
              value={form.productId}
              selected={form.selectedProduct}
              onChange={handleProductChange}
            />
            {product && (
              <div className="box box-pad box-tint t-sm">
                <div className="t-xs upper muted" style={{ marginBottom: 4 }}>
                  Catalog description
                </div>
                {product.description}
              </div>
            )}
            <Field label="Quantity" required>
              <input
                type="number"
                min={1}
                value={form.quantity}
                onChange={(e) => handleQuantityChange(+e.target.value)}
              />
            </Field>
            <div className="field">
              <label>
                Business purpose
                <span className="opt">&nbsp;&nbsp;(optional)</span>
              </label>
              <div className="ctl tall">
                <span className="br">[</span>
                <textarea
                  rows={3}
                  placeholder="Why this purchase is needed…"
                  value={form.purpose}
                  onChange={(e) => set('purpose', e.target.value)}
                  style={{
                    flex: 1,
                    border: 0,
                    outline: 0,
                    background: 'transparent',
                    fontFamily: 'inherit',
                    fontSize: 'inherit',
                    padding: '6px 0',
                    resize: 'vertical',
                    minHeight: 60,
                  }}
                />
                <span className="br">]</span>
              </div>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="col" style={{ gap: 18 }}>
            <div className="t-xs upper muted">Delivery location</div>
            <Field label="Address" required>
              <input
                value={form.delivery.address}
                onChange={(e) => setDelivery('address', e.target.value)}
              />
            </Field>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <Field label="City" required>
                  <input
                    value={form.delivery.city}
                    onChange={(e) => setDelivery('city', e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="State / region" required>
                  <input
                    value={form.delivery.state}
                    onChange={(e) => setDelivery('state', e.target.value)}
                  />
                </Field>
              </div>
            </div>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <Field label="Country" required hint="2+ letter code or full name">
                  <input
                    value={form.delivery.country}
                    onChange={(e) => setDelivery('country', e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="Pincode / ZIP" required>
                  <input
                    value={form.delivery.pincode}
                    onChange={(e) => setDelivery('pincode', e.target.value)}
                  />
                </Field>
              </div>
            </div>

            <AsciiRule />

            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <Field label="Budget ceiling" required>
                  <input
                    type="number"
                    min={0}
                    step="0.01"
                    value={form.budgetCeiling || ''}
                    onChange={(e) => set('budgetCeiling', +e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="Currency" required hint="ISO 4217, e.g. USD">
                  <input
                    value={form.currency}
                    maxLength={3}
                    onChange={(e) => set('currency', e.target.value.toUpperCase())}
                  />
                </Field>
              </div>
            </div>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <Field label="Need by" required>
                  <input
                    type="date"
                    min={todayIso()}
                    value={form.requiredBy}
                    onChange={(e) => set('requiredBy', e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <label className="t-xs upper muted">
                  Urgency <span className="req">*</span>
                </label>
                <PfSelect
                  value={form.urgency}
                  onChange={(e) => set('urgency', e.target.value as Urgency)}
                >
                  <option value="low">low</option>
                  <option value="normal">normal</option>
                  <option value="high">high</option>
                  <option value="emergency">emergency</option>
                </PfSelect>
              </div>
            </div>
            <div className="field">
              <label>
                Notes for agents
                <span className="opt">&nbsp;&nbsp;(optional)</span>
              </label>
              <div className="ctl tall">
                <span className="br">[</span>
                <textarea
                  rows={3}
                  placeholder="Preferences, restrictions, or context for agents…"
                  value={form.buyerNotes}
                  onChange={(e) => set('buyerNotes', e.target.value)}
                  style={{
                    flex: 1,
                    border: 0,
                    outline: 0,
                    background: 'transparent',
                    fontFamily: 'inherit',
                    fontSize: 'inherit',
                    padding: '6px 0',
                    resize: 'vertical',
                    minHeight: 60,
                  }}
                />
                <span className="br">]</span>
              </div>
            </div>

            <AsciiRule />

            <div className="field">
              <label
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  gap: 8,
                  cursor: 'pointer',
                }}
              >
                <input
                  type="checkbox"
                  checked={form.approvalRequired}
                  onChange={(e) => set('approvalRequired', e.target.checked)}
                />
                <span>
                  Require my approval before each step
                  <span className="opt">
                    &nbsp;&nbsp;(pauses for confirmation before PO, GRN, and completion)
                  </span>
                </span>
              </label>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="col" style={{ gap: 14 }}>
            <div className="t-xs upper muted">Review &amp; submit</div>
            <div className="kv box box-pad box-tint">
              <div className="k">Product</div>
              <div className="v">
                {product ? `${product.name} · ${product.brand}` : form.productId}
              </div>
              <div className="k">Quantity</div>
              <div className="v tnum">{form.quantity}</div>
              {form.purpose.trim() && (
                <>
                  <div className="k">Purpose</div>
                  <div className="v">{form.purpose.trim()}</div>
                </>
              )}
              <div className="k">Deliver to</div>
              <div className="v">
                {form.delivery.address}, {form.delivery.city}, {form.delivery.state}{' '}
                {form.delivery.country} {form.delivery.pincode}
              </div>
              <div className="k">Need by</div>
              <div className="v tnum">{form.requiredBy}</div>
              <div className="k">Urgency</div>
              <div className="v">{urgencyLabels[form.urgency]}</div>
              <div className="k">Budget ceiling</div>
              <div className="v tnum">
                {form.currency} {form.budgetCeiling.toLocaleString()}
              </div>
              {form.buyerNotes.trim() && (
                <>
                  <div className="k">Notes</div>
                  <div className="v">{form.buyerNotes.trim()}</div>
                </>
              )}
              <div className="k">Approval gate</div>
              <div className="v">
                {form.approvalRequired
                  ? 'pause for my approval at PO, GRN, and completion'
                  : 'automated end-to-end'}
              </div>
            </div>
          </div>
        )}

        <AsciiRule />

        <div className="row between" style={{ marginTop: 14 }}>
          <span className="t-xs faint">step {step} of 3</span>
          <div className="row" style={{ gap: 6 }}>
            {step > 1 && (
              <button type="button" className="btn" onClick={() => { setStepError(null); setStep(step - 1) }}>
                [ ← back ]
              </button>
            )}
            {step < 3 && (
              <button type="button" className="btn primary" onClick={goNext}>
                [ next → ]
              </button>
            )}
            {step === 3 && (
              <button
                type="button"
                className="btn accent"
                onClick={handleSubmit}
                disabled={submitting}
              >
                [ {submitting ? 'starting…' : 'submit & start agents'} ]
              </button>
            )}
          </div>
        </div>
        {(stepError || submitError) && (
          <div className="t-sm accent" style={{ marginTop: 8 }}>
            {stepError ?? submitError}
          </div>
        )}
      </div>
    </div>
  )
}
