"""ADK `session.state` shape for the buyer procurement workflow.

Use `BuyerWorkflowSessionState` as the single contract for keys and types written at
session creation (`VertexAiSessionService.create_session`). When you add mutable
workflow fields later, extend this model and thread them through `WorkflowService`
so state stays documented in one place.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from api.schemas.workflow import BuyerSessionRequestState
from db.collections.product import Product


class BuyerWorkflowSessionState(BaseModel):
    """Initial session.state for a buyer workflow run (canonical keys only).

    Top-level keys are intentionally minimal: `request` (procurement intent) and
    `product` (catalog snapshot). Do not duplicate derived strings here; the model
    is the source of truth for JSON-serializable Vertex state.
    """

    model_config = ConfigDict(extra="forbid")

    request: BuyerSessionRequestState = Field(
        description="Structured procurement payload (ids, qty, delivery, budget, etc.).",
    )
    product: Product = Field(
        description="Firestore product document snapshot at workflow start.",
    )

    def to_vertex_state(self) -> dict[str, object]:
        """Serialize for Vertex ADK session create/update (JSON-compatible)."""
        return self.model_dump(mode="json", by_alias=True)
