"""Stateless per-request Q&A over a buyer workflow's session snapshot.

Reads the live buyer Vertex session (read-only), packages a compact JSON
snapshot, and runs the lightweight ``workflow_qa_agent`` against the user's
question inside a throwaway ``InMemorySessionService``. Nothing is persisted —
the in-memory session is discarded when the request returns.
"""

from __future__ import annotations

import logging
import uuid
from typing import Any

from fastapi import HTTPException, status

from api.config import APISettings
from api.schemas.workflow_chat import ChatTurn
from api.services.session_reader import BuyerSessionReader
from procu_forge_buyer.state_keys import (
    APPROVAL_REQUIRED_KEY,
    APPROVED_STEPS_KEY,
    GRN_KEY,
    INVOICE_KEY,
    NEGOTIATION_CONFIG_KEY,
    PENDING_APPROVAL_KEY,
    PO_KEY,
    PR_STATUS_KEY,
    PREVIOUS_PR_STATUS_KEY,
    PRODUCT_KEY,
    REQUEST_KEY,
    SELECTED_VENDOR_KEY,
    VENDOR_OFFERS_KEY,
)

logger = logging.getLogger(__name__)

CHAT_APP_NAME = "workflow_qa"
MAX_HISTORY_TURNS = 6
MAX_ANSWER_FALLBACK = "I couldn't generate a response. Please try again."


class WorkflowChatService:
    """One request = one fresh in-memory session, one Runner invocation."""

    def __init__(self, settings: APISettings) -> None:
        self._settings = settings
        self._session_reader = BuyerSessionReader(settings)

    async def ask(
        self,
        workflow_id: str,
        question: str,
        history: list[ChatTurn],
    ) -> str:
        self._ensure_vertex_configured()

        buyer_session = await self._session_reader.get_session(workflow_id)
        if buyer_session is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Workflow '{workflow_id}' not found.",
            )

        state: dict[str, Any] = (
            buyer_session.state if isinstance(buyer_session.state, dict) else {}
        )
        snapshot = _build_snapshot(state)

        # Lazy imports keep test/cli surfaces light.
        from google.adk.runners import Runner
        from google.adk.sessions import InMemorySessionService
        from google.genai import types as genai_types

        from procu_forge_buyer.subagents.workflow_qa import workflow_qa_agent

        session_service = InMemorySessionService()
        chat_session_id = uuid.uuid4().hex
        await session_service.create_session(
            app_name=CHAT_APP_NAME,
            user_id=workflow_id,
            session_id=chat_session_id,
            state={"workflow_snapshot": snapshot},
        )

        runner = Runner(
            agent=workflow_qa_agent,
            app_name=CHAT_APP_NAME,
            session_service=session_service,
        )

        prompt_text = _compose_prompt(question=question, history=history)
        message = genai_types.Content(
            role="user",
            parts=[genai_types.Part(text=prompt_text)],
        )

        logger.info(
            "workflow_chat.ask workflow_id=%s question_chars=%s history_turns=%s",
            workflow_id,
            len(question),
            min(len(history), MAX_HISTORY_TURNS),
        )

        final_text: str | None = None
        async for event in runner.run_async(
            user_id=workflow_id,
            session_id=chat_session_id,
            new_message=message,
        ):
            if not event.is_final_response():
                continue
            content = getattr(event, "content", None)
            parts = getattr(content, "parts", None) or []
            text_chunks = [p.text for p in parts if getattr(p, "text", None)]
            if text_chunks:
                final_text = "".join(text_chunks).strip()

        return final_text or MAX_ANSWER_FALLBACK

    def _ensure_vertex_configured(self) -> None:
        missing: list[str] = []
        if not self._settings.vertex_project_id:
            missing.append("GOOGLE_CLOUD_PROJECT")
        if not self._settings.reasoning_engine_app_name:
            missing.append("BUYER_REASONING_ENGINE")
        if missing:
            raise HTTPException(
                status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
                detail=(
                    "Workflow chat runtime is not configured. Missing env vars: "
                    + ", ".join(missing)
                ),
            )


def _build_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Pick only the slices a chat model needs and strip heavy sub-arrays.

    Notably drops per-vendor ``communications`` history to keep the prompt
    small; full negotiation transcripts live in the vendor-thread view.
    """
    vendor_offers = state.get(VENDOR_OFFERS_KEY) or {}
    trimmed_offers = _trim_vendor_offers(vendor_offers)

    negotiation_config = state.get(NEGOTIATION_CONFIG_KEY) or {}
    nego_summary = _summarize_negotiation_config(negotiation_config)

    return {
        "request": state.get(REQUEST_KEY),
        "product": state.get(PRODUCT_KEY),
        "pr_status": state.get(PR_STATUS_KEY),
        "previous_pr_status": state.get(PREVIOUS_PR_STATUS_KEY),
        "approval_required": state.get(APPROVAL_REQUIRED_KEY),
        "approved_steps": state.get(APPROVED_STEPS_KEY),
        "pending_approval": state.get(PENDING_APPROVAL_KEY),
        "vendor_offers": trimmed_offers,
        "selected_vendor": state.get(SELECTED_VENDOR_KEY),
        "po": state.get(PO_KEY),
        "grn": state.get(GRN_KEY),
        "invoice": state.get(INVOICE_KEY),
        "negotiation_config": nego_summary,
    }


def _trim_vendor_offers(vendor_offers: Any) -> Any:
    """Drop per-offer ``communications`` arrays — they can be huge."""
    if not isinstance(vendor_offers, dict):
        return vendor_offers
    offers = vendor_offers.get("offers")
    if not isinstance(offers, list):
        return vendor_offers
    trimmed_list = []
    for offer in offers:
        if isinstance(offer, dict):
            trimmed_list.append({k: v for k, v in offer.items() if k != "communications"})
        else:
            trimmed_list.append(offer)
    return {**vendor_offers, "offers": trimmed_list}


def _summarize_negotiation_config(cfg: Any) -> Any:
    """Keep only top-level negotiation targets; per-vendor tracker rows would
    duplicate vendor_offers and bloat the prompt."""
    if not isinstance(cfg, dict):
        return cfg
    keep_keys = {
        "target_total",
        "target_unit_price",
        "anchor_unit_price",
        "walk_away_pct",
        "max_rounds",
        "currency",
    }
    return {k: v for k, v in cfg.items() if k in keep_keys}


def _compose_prompt(*, question: str, history: list[ChatTurn]) -> str:
    """Attach a short transcript of prior turns above the new question."""
    recent = history[-MAX_HISTORY_TURNS:] if history else []
    if not recent:
        return question

    lines = ["Prior conversation (most recent last):"]
    for turn in recent:
        speaker = "User" if turn.role == "user" else "Assistant"
        lines.append(f"{speaker}: {turn.text}")
    lines.append("")
    lines.append(f"User question: {question}")
    return "\n".join(lines)
