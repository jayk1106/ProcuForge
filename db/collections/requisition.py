from __future__ import annotations

from datetime import datetime

from pydantic import Field

from db.collections.common import DocumentMetadata, FirestoreBaseModel

COLLECTION_ID = "requisitions"


class RequisitionBudget(FirestoreBaseModel):
    currency: str
    estimated_amount: float = Field(alias="estimatedAmount")
    approved_amount: float | None = Field(default=None, alias="approvedAmount")


class RequisitionItem(FirestoreBaseModel):
    product_id: str = Field(alias="productId")
    product_name: str = Field(alias="productName")
    quantity: int
    estimated_unit_price: float = Field(alias="estimatedUnitPrice")
    selected_vendor_id: str | None = Field(default=None, alias="selectedVendorId")
    final_unit_price: float | None = Field(default=None, alias="finalUnitPrice")


class WorkflowPendingWith(FirestoreBaseModel):
    participant_type: str = Field(alias="type")
    id: str


class WorkflowState(FirestoreBaseModel):
    current_stage: str = Field(alias="currentStage")
    completed_stages: list[str] = Field(alias="completedStages")
    pending_with: WorkflowPendingWith | None = Field(default=None, alias="pendingWith")
    sla_due_at: datetime | None = Field(default=None, alias="slaDueAt")
    last_updated_at: datetime | None = Field(default=None, alias="lastUpdatedAt")


class SelectedVendor(FirestoreBaseModel):
    preferred_vendor_id: str = Field(alias="preferredVendorId")
    status: str
    quoted_amount: float | None = Field(default=None, alias="quotedAmount")
    final_amount: float | None = Field(default=None, alias="finalAmount")
    summary: str | None = None


class NegotiationMessage(FirestoreBaseModel):
    role: str
    text: str


class NegotiationStep(FirestoreBaseModel):
    vendor: str
    conversations: list[NegotiationMessage]


class PurchaseOrderBlock(FirestoreBaseModel):
    po_number: str = Field(alias="poNumber")
    issued_at: datetime | None = Field(default=None, alias="issuedAt")
    status: str
    currency: str
    total_amount: float = Field(alias="totalAmount")


class GrnReceivedItem(FirestoreBaseModel):
    product_id: str = Field(alias="productId")
    received_qty: int = Field(alias="receivedQty")


class GrnBlock(FirestoreBaseModel):
    status: str
    received_at: datetime | None = Field(default=None, alias="receivedAt")
    received_items: list[GrnReceivedItem] = Field(alias="receivedItems")
    rejected_quantity: int | None = Field(default=None, alias="rejectedQuantity")
    rejection_reason: str | None = Field(default=None, alias="rejectionReason")


class InvoiceBlock(FirestoreBaseModel):
    invoice_number: str = Field(alias="invoiceNumber")
    status: str
    amount: float
    submitted_at: datetime | None = Field(default=None, alias="submittedAt")
    payment_due_at: datetime | None = Field(default=None, alias="paymentDueAt")


class Requisition(FirestoreBaseModel):
    id: str
    organization_id: str = Field(alias="organizationId")
    title: str
    description: str
    created_by: str = Field(alias="createdBy")
    department: str
    priority: str
    status: str
    budget: RequisitionBudget
    items: list[RequisitionItem]
    workflow_state: WorkflowState = Field(alias="workflowState")
    selected_vendor: SelectedVendor | None = Field(default=None, alias="selectedVendor")
    negotiation_steps: list[NegotiationStep] = Field(alias="negotiationSteps")
    purchase_order: PurchaseOrderBlock | None = Field(default=None, alias="purchaseOrder")
    grn: GrnBlock | None = None
    invoice: InvoiceBlock | None = None
    summary: str | None = None
    metadata: DocumentMetadata
