'use client'
import React, { useState } from 'react'
import { Field } from '@/components/primitives/Field'
import { PfSelect } from '@/components/primitives/PfSelect'
import { AsciiRule } from '@/components/primitives/AsciiRule'

interface PRModalProps {
  open: boolean
  onClose: () => void
}

interface FormState {
  title: string
  sku: string
  qty: number
  target: number
  needBy: string
  costCenter: string
  spec: string
  priority: string
  region: string
  payment: string
  notes: string
}

export function PRModal({ open, onClose }: PRModalProps) {
  const [step, setStep] = useState(1)
  const [form, setForm] = useState<FormState>({
    title: 'CNC spindle motors, 7.5kW',
    sku: 'CNC-SPINDLE-7K5-IP65',
    qty: 24,
    target: 186400,
    needBy: '2026-05-22',
    costCenter: 'PROD-EAST-04',
    spec: 'Siemens 1FK7-equivalent, IP65, water-cooled. Compatible with HAAS VF-2 retrofit.',
    priority: 'standard',
    region: 'NA + DE + JP',
    payment: 'NET-30',
    notes: '',
  })

  function set<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }))
  }

  if (!open) return null

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="t-xs upper muted">New purchase request</div>
            <div className="page-title" style={{ fontSize: 'var(--t-xl)', marginTop: 4 }}>
              draft · <span className="tnum muted">PR-2026-0419</span>
            </div>
            <div className="t-sm muted" style={{ marginTop: 4 }}>
              Once submitted, the IntakeAgent classifies and routes. Standard requests under $250k auto-approve.
            </div>
          </div>
          <button className="btn ghost" onClick={onClose}>
            [ × close ]
          </button>
        </div>

        <div className="row" style={{ gap: 6, fontSize: 'var(--t-xs)', color: 'var(--muted)', marginBottom: 18 }}>
          <span className={step >= 1 ? 'ink' : ''}>① what</span>
          <span className="sep-dot">────</span>
          <span className={step >= 2 ? 'ink' : ''}>② constraints</span>
          <span className="sep-dot">────</span>
          <span className={step >= 3 ? 'ink' : ''}>③ review</span>
        </div>

        {step === 1 && (
          <div className="col" style={{ gap: 18 }}>
            <Field label="Request title" required>
              <input value={form.title} onChange={(e) => set('title', e.target.value)} />
            </Field>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 2 }}>
                <Field
                  label="SKU / catalog ref"
                  required
                  hint="exact match preferred — agents will validate"
                >
                  <input value={form.sku} onChange={(e) => set('sku', e.target.value)} />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="Quantity" required>
                  <input
                    type="number"
                    value={form.qty}
                    onChange={(e) => set('qty', +e.target.value)}
                  />
                </Field>
              </div>
            </div>
            <div className="field">
              <label>
                Specification
                <span className="opt">&nbsp;&nbsp;(optional)</span>
              </label>
              <div className="ctl tall">
                <span className="br">[</span>
                <textarea
                  rows={4}
                  value={form.spec}
                  onChange={(e) => set('spec', e.target.value)}
                  style={{ flex: 1, border: 0, outline: 0, background: 'transparent', fontFamily: 'inherit', fontSize: 'inherit', padding: '6px 0', resize: 'vertical', minHeight: 80 }}
                />
                <span className="br">]</span>
              </div>
              <span className="hint">markdown ok · attachments via drag &amp; drop</span>
            </div>
          </div>
        )}

        {step === 2 && (
          <div className="col" style={{ gap: 18 }}>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <Field label="Target total (USD)" required>
                  <input
                    type="number"
                    value={form.target}
                    onChange={(e) => set('target', +e.target.value)}
                  />
                </Field>
              </div>
              <div style={{ flex: 1 }}>
                <Field label="Need by" required>
                  <input
                    type="date"
                    value={form.needBy}
                    onChange={(e) => set('needBy', e.target.value)}
                  />
                </Field>
              </div>
            </div>
            <div className="row" style={{ gap: 14 }}>
              <div style={{ flex: 1 }}>
                <label className="t-xs upper muted">
                  Priority <span className="req">*</span>
                </label>
                <PfSelect value={form.priority} onChange={(e) => set('priority', e.target.value)}>
                  <option value="standard">standard</option>
                  <option value="expedited">expedited (+8% budget)</option>
                  <option value="critical">critical (line down)</option>
                </PfSelect>
              </div>
              <div style={{ flex: 1 }}>
                <label className="t-xs upper muted">
                  Payment terms <span className="req">*</span>
                </label>
                <PfSelect value={form.payment} onChange={(e) => set('payment', e.target.value)}>
                  <option>NET-30</option>
                  <option>NET-45</option>
                  <option>NET-60</option>
                  <option>2/10 NET-30</option>
                </PfSelect>
              </div>
            </div>
            <Field label="Cost center" required>
              <input value={form.costCenter} onChange={(e) => set('costCenter', e.target.value)} />
            </Field>
            <Field label="Vendor sourcing region" optional>
              <input value={form.region} onChange={(e) => set('region', e.target.value)} />
            </Field>
            <div className="field">
              <label>
                Notes for agents
                <span className="opt">&nbsp;&nbsp;(optional)</span>
              </label>
              <div className="ctl tall">
                <span className="br">[</span>
                <textarea
                  rows={3}
                  placeholder="any preferences, restrictions, or context the agents should know…"
                  value={form.notes}
                  onChange={(e) => set('notes', e.target.value)}
                  style={{ flex: 1, border: 0, outline: 0, background: 'transparent', fontFamily: 'inherit', fontSize: 'inherit', padding: '6px 0', resize: 'vertical', minHeight: 60 }}
                />
                <span className="br">]</span>
              </div>
            </div>
          </div>
        )}

        {step === 3 && (
          <div className="col" style={{ gap: 14 }}>
            <div className="t-xs upper muted">Review &amp; submit</div>
            <div className="kv box box-pad box-tint">
              <div className="k">Title</div><div className="v">{form.title}</div>
              <div className="k">SKU</div><div className="v tnum">{form.sku}</div>
              <div className="k">Quantity</div><div className="v tnum">{form.qty} units</div>
              <div className="k">Target total</div><div className="v tnum">${form.target.toLocaleString()}</div>
              <div className="k">Need by</div><div className="v tnum">{form.needBy}</div>
              <div className="k">Priority</div><div className="v">{form.priority}</div>
              <div className="k">Payment</div><div className="v">{form.payment}</div>
              <div className="k">Cost center</div><div className="v">{form.costCenter}</div>
              <div className="k">Region</div><div className="v">{form.region}</div>
            </div>
            <div className="box box-pad" style={{ background: 'var(--accent-soft)', borderColor: 'var(--accent)' }}>
              <div className="t-xs upper accent" style={{ fontWeight: 600 }}>
                auto-classification preview
              </div>
              <div className="t-sm" style={{ marginTop: 4 }}>
                Class B · auto-approves · estimated 6 vendors in cohort · expected RFQ window 24h.
              </div>
            </div>
          </div>
        )}

        <AsciiRule />

        <div className="row between" style={{ marginTop: 14 }}>
          <span className="t-xs faint">draft saved · {new Date().toLocaleTimeString()}</span>
          <div className="row" style={{ gap: 6 }}>
            {step > 1 && (
              <button className="btn" onClick={() => setStep(step - 1)}>
                [ ← back ]
              </button>
            )}
            {step < 3 && (
              <button className="btn primary" onClick={() => setStep(step + 1)}>
                [ next → ]
              </button>
            )}
            {step === 3 && (
              <button className="btn accent" onClick={onClose}>
                [ submit &amp; start agents ]
              </button>
            )}
          </div>
        </div>
      </div>
    </div>
  )
}
