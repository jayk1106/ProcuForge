"use client";

import React, { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { startWorkflow } from "@/lib/api-client";
import { Field } from "@/components/primitives/Field";
import { ProductPicker } from "@/components/primitives/ProductPicker";
import { AsciiRule } from "@/components/primitives/AsciiRule";
import { useAuth } from "@/hooks/useAuth";
import type { ProductOption } from "@/types/product";
import type { OrgAddress } from "@/types/auth";

interface PRModalProps {
  open: boolean;
  onClose: () => void;
}

const DEFAULT_CURRENCY = "USD";
const DEFAULT_URGENCY = "normal" as const;

interface FormState {
  productId: string;
  selectedProduct: ProductOption | null;
  quantity: number;
  quantityInput: string;
  requiredBy: string;
  budgetCeiling: number;
  approvalRequired: boolean;
}

function defaultNeedBy(): string {
  return new Date(Date.now() + 30 * 86400000).toISOString().slice(0, 10);
}

function initialForm(): FormState {
  return {
    productId: "",
    selectedProduct: null,
    quantity: 1,
    quantityInput: "1",
    requiredBy: defaultNeedBy(),
    budgetCeiling: 0,
    approvalRequired: false,
  };
}

function formatOrgAddress(addr: OrgAddress | null | undefined): string {
  if (!addr) return "";
  const parts = [
    addr.address,
    addr.city,
    addr.state,
    addr.country,
    addr.pincode,
  ]
    .map((p) => (p ?? "").trim())
    .filter(Boolean);
  return parts.join(", ");
}

function suggestBudget(product: ProductOption, quantity: number): number {
  const total = product.estimatedPriceRange.max * (quantity > 0 ? quantity : 1);
  return Math.round(total * 100) / 100;
}

function todayIso(): string {
  return new Date().toISOString().slice(0, 10);
}

export function PRModal({ open, onClose }: PRModalProps) {
  const router = useRouter();
  const { me } = useAuth();
  const orgAddress = me?.org.address ?? null;
  const orgCurrency = (me?.org.currency || DEFAULT_CURRENCY).toUpperCase();
  const orgAddressDisplay = formatOrgAddress(orgAddress);

  const [step, setStep] = useState(1);
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [stepError, setStepError] = useState<string | null>(null);
  const [form, setForm] = useState<FormState>(initialForm);

  useEffect(() => {
    if (!open) {
      setStep(1);
      setForm(initialForm());
      setSubmitError(null);
      setStepError(null);
    }
  }, [open]);

  function set<K extends keyof FormState>(k: K, v: FormState[K]) {
    setForm((f) => ({ ...f, [k]: v }));
  }

  function handleProductChange(
    productId: string,
    product: ProductOption | null,
  ) {
    setForm((f) => {
      const next: FormState = { ...f, productId, selectedProduct: product };
      if (product) {
        next.budgetCeiling = suggestBudget(
          product,
          f.quantity > 0 ? f.quantity : 1,
        );
      }
      return next;
    });
  }

  function handleQuantityInput(raw: string) {
    const cleaned = raw.replace(/[^0-9]/g, "");
    setForm((f) => {
      const parsed = parseInt(cleaned, 10);
      const quantity = Number.isFinite(parsed) && parsed > 0 ? parsed : 1;
      const next: FormState = { ...f, quantityInput: cleaned, quantity };
      if (f.selectedProduct && cleaned !== "") {
        next.budgetCeiling = suggestBudget(f.selectedProduct, quantity);
      }
      return next;
    });
  }

  function handleQuantityBlur() {
    setForm((f) => {
      if (f.quantityInput !== "" && parseInt(f.quantityInput, 10) > 0) return f;
      const next: FormState = { ...f, quantityInput: "1", quantity: 1 };
      if (f.selectedProduct) {
        next.budgetCeiling = suggestBudget(f.selectedProduct, 1);
      }
      return next;
    });
  }

  function validateStep(targetStep: number): string | null {
    if (targetStep >= 2) {
      if (!form.productId || !form.selectedProduct) return "Select a product.";
      if (!Number.isFinite(form.quantity) || form.quantity <= 0)
        return "Quantity must be greater than 0.";
    }
    if (targetStep >= 3) {
      if (
        !orgAddress ||
        !orgAddress.address ||
        !orgAddress.city ||
        !orgAddress.country
      ) {
        return "Your organisation address is not configured. Contact an admin.";
      }
      if (!form.requiredBy || form.requiredBy < todayIso()) {
        return "Need-by date must be today or later.";
      }
      if (!Number.isFinite(form.budgetCeiling) || form.budgetCeiling <= 0) {
        return "Budget ceiling must be greater than 0.";
      }
    }
    return null;
  }

  function goNext() {
    const err = validateStep(step + 1);
    if (err) {
      setStepError(err);
      return;
    }
    setStepError(null);
    setStep(step + 1);
  }

  async function handleSubmit() {
    const err = validateStep(3);
    if (err) {
      setStepError(err);
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    setStepError(null);
    try {
      if (!orgAddress) {
        throw new Error("Your organisation address is not configured.");
      }
      const result = await startWorkflow({
        product_id: form.productId,
        quantity: form.quantity,
        required_by: form.requiredBy,
        delivery_location: {
          address: orgAddress.address.trim(),
          city: orgAddress.city.trim(),
          state: orgAddress.state.trim(),
          country: orgAddress.country.trim(),
          pincode: orgAddress.pincode.trim(),
        },
        urgency: DEFAULT_URGENCY,
        budget_ceiling: form.budgetCeiling,
        currency: orgCurrency || DEFAULT_CURRENCY,
        approval_required: form.approvalRequired,
      });
      onClose();
      router.push(`/flows/${result.workflow_id}`);
    } catch (e) {
      setSubmitError(
        e instanceof Error ? e.message : "Failed to start workflow",
      );
    } finally {
      setSubmitting(false);
    }
  }

  if (!open) return null;

  const product = form.selectedProduct;

  return (
    <div className="modal-overlay" onClick={onClose}>
      <div className="modal" onClick={(e) => e.stopPropagation()}>
        <div className="modal-head">
          <div>
            <div className="t-xs upper muted">New purchase request</div>
            <div
              className="page-title"
              style={{ fontSize: "var(--t-xl)", marginTop: 4 }}
            >
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

        <div className="modal-body">
          <div
            className="row"
            style={{
              gap: 6,
              fontSize: "var(--t-xs)",
              color: "var(--muted)",
              marginBottom: 18,
            }}
          >
            <span className={step >= 1 ? "ink" : ""}>① product</span>
            <span className="sep-dot">────</span>
            <span className={step >= 2 ? "ink" : ""}>② terms</span>
            <span className="sep-dot">────</span>
            <span className={step >= 3 ? "ink" : ""}>③ review</span>
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
                  type="text"
                  inputMode="numeric"
                  pattern="[0-9]*"
                  value={form.quantityInput}
                  onChange={(e) => handleQuantityInput(e.target.value)}
                  onBlur={handleQuantityBlur}
                />
              </Field>
            </div>
          )}

          {step === 2 && (
            <div className="col" style={{ gap: 18 }}>
              <div>
                <div className="t-xs upper muted" style={{ marginBottom: 6 }}>
                  Delivery location{" "}
                  <span className="opt">
                    &nbsp;&nbsp;(from your organisation)
                  </span>
                </div>
                <div
                  className="box box-pad box-tint t-sm"
                  style={{ lineHeight: 1.55 }}
                >
                  {orgAddressDisplay ? (
                    <span>{orgAddressDisplay}</span>
                  ) : (
                    <span className="accent">
                      Your organisation address is not configured. Contact an
                      admin to set it before starting a procurement.
                    </span>
                  )}
                </div>
              </div>

              <div>
                <div className="t-xs upper muted" style={{ marginBottom: 6 }}>
                  Currency{" "}
                  <span className="opt">
                    &nbsp;&nbsp;(from your organisation)
                  </span>
                </div>
                <div
                  className="box box-pad box-tint"
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 12,
                    letterSpacing: "0.08em",
                  }}
                >
                  <span
                    style={{
                      fontSize: "var(--t-lg, 18px)",
                      fontWeight: 600,
                    }}
                  >
                    {orgCurrency}
                  </span>
                  <span className="t-xs muted">
                    all amounts in this request are denominated in {orgCurrency}
                  </span>
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
                      value={form.budgetCeiling || ""}
                      onChange={(e) => set("budgetCeiling", +e.target.value)}
                    />
                  </Field>
                </div>
                <div style={{ flex: 1 }}>
                  <Field label="Need by" required>
                    <input
                      type="date"
                      min={todayIso()}
                      value={form.requiredBy}
                      onChange={(e) => set("requiredBy", e.target.value)}
                    />
                  </Field>
                </div>
              </div>
              <AsciiRule />

              <label
                className="box box-pad"
                style={{
                  display: "flex",
                  alignItems: "flex-start",
                  gap: 14,
                  padding: "18px 20px",
                  marginTop: 6,
                  cursor: "pointer",
                  borderLeft: "4px solid var(--accent, #c08a3a)",
                  background: form.approvalRequired
                    ? "rgba(192, 138, 58, 0.08)"
                    : undefined,
                  transition: "background 120ms ease",
                }}
              >
                <input
                  type="checkbox"
                  checked={form.approvalRequired}
                  onChange={(e) => set("approvalRequired", e.target.checked)}
                  style={{
                    marginTop: 4,
                    width: 18,
                    height: 18,
                    cursor: "pointer",
                    accentColor: "var(--accent, #c08a3a)",
                  }}
                />
                <div
                  style={{ display: "flex", flexDirection: "column", gap: 4 }}
                >
                  <span
                    className="t-xs upper"
                    style={{ letterSpacing: "0.08em" }}
                  >
                    Human-in-the-loop · approval gate
                  </span>
                  <span className="t-sm">
                    Require my approval before each step
                  </span>
                  <span className="t-xs muted">
                    When enabled, the buyer agent pauses for confirmation before
                    sending the PO, before sending the GRN, and before closing
                    the procurement. You approve each step in the flow detail
                    page.
                  </span>
                </div>
              </label>
            </div>
          )}

          {step === 3 && (
            <div className="col" style={{ gap: 14 }}>
              <div className="t-xs upper muted">Review &amp; submit</div>
              <div className="kv box box-pad box-tint">
                <div className="k">Product</div>
                <div className="v">
                  {product
                    ? `${product.name} · ${product.brand}`
                    : form.productId}
                </div>
                <div className="k">Quantity</div>
                <div className="v tnum">{form.quantity}</div>
                <div className="k">Deliver to</div>
                <div className="v">{orgAddressDisplay || "—"}</div>
                <div className="k">Need by</div>
                <div className="v tnum">{form.requiredBy}</div>
                <div className="k">Budget ceiling</div>
                <div className="v tnum">
                  {orgCurrency} {form.budgetCeiling.toLocaleString()}
                </div>
                <div className="k">Approval gate</div>
                <div className="v">
                  {form.approvalRequired
                    ? "pause for my approval at PO, GRN, and completion"
                    : "automated end-to-end"}
                </div>
              </div>
            </div>
          )}
        </div>

        <div className="modal-foot">
          <div className="row between">
            <span className="t-xs faint">step {step} of 3</span>
            <div className="row" style={{ gap: 6 }}>
              {step > 1 && (
                <button
                  type="button"
                  className="btn"
                  onClick={() => {
                    setStepError(null);
                    setStep(step - 1);
                  }}
                >
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
                  [ {submitting ? "starting…" : "submit & start agents"} ]
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
    </div>
  );
}
