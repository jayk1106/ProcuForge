#!/usr/bin/env python3
"""Backfill the rfq_index Firestore collection from existing buyer sessions.

For every entry in ``workflow_index``, read the corresponding buyer Vertex
session and emit an ``rfq_index`` document for each
``negotiations_config[vendor_id].rfq_id`` found.

Safe to re-run: upserts are idempotent (write key is ``rfq_id``).

Run:
    uv run python scripts/backfill_rfq_index.py
    uv run python scripts/backfill_rfq_index.py --organization <org_id>
"""

from __future__ import annotations

import argparse
import asyncio
import logging
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

logging.basicConfig(level=os.environ.get("LOG_LEVEL", "INFO"))
logger = logging.getLogger("backfill_rfq_index")


async def _run(organization_id: str | None) -> None:
    from api.config import get_api_settings
    from api.services.session_reader import BuyerSessionReader
    from db.collections.rfq_index import RfqIndexEntry
    from db.firestore.client import get_firestore_client
    from db.firestore.repositories.rfq_index import RfqIndexRepository
    from db.firestore.repositories.workflow_index import WorkflowIndexRepository
    from procu_forge_buyer.state_keys import NEGOTIATION_CONFIG_KEY

    settings = get_api_settings()
    client = get_firestore_client()
    index_repo = WorkflowIndexRepository(client)
    rfq_repo = RfqIndexRepository(client)
    reader = BuyerSessionReader(settings)

    org = organization_id or settings.workflow_default_organization_id
    if not org:
        raise SystemExit(
            "organization_id required: pass --organization or set WORKFLOW_DEFAULT_ORGANIZATION_ID"
        )

    entries = await index_repo.list_by_org(org)
    logger.info("backfill.start org=%s workflows=%d", org, len(entries))

    written = 0
    skipped = 0
    for entry in entries:
        session = await reader.get_session(entry.workflow_id)
        if session is None:
            logger.warning("backfill.session_missing workflow_id=%s", entry.workflow_id)
            continue
        state = session.state if isinstance(session.state, dict) else {}
        neg = state.get(NEGOTIATION_CONFIG_KEY)
        if not isinstance(neg, dict):
            skipped += 1
            continue

        for vendor_id_key, cfg in neg.items():
            if not isinstance(cfg, dict):
                continue
            rfq_id = str(cfg.get("rfq_id") or "")
            if not rfq_id:
                continue
            vendor_id = str(cfg.get("vendor_id") or vendor_id_key)
            doc = RfqIndexEntry(
                id=rfq_id,
                rfqId=rfq_id,
                workflowId=entry.workflow_id,
                vendorId=vendor_id,
                organizationId=entry.organization_id,
                createdAt=entry.started_at or datetime.now(timezone.utc),
            )
            await rfq_repo.upsert(doc)
            written += 1

    logger.info(
        "backfill.complete org=%s written=%d skipped_workflows=%d",
        org,
        written,
        skipped,
    )


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--organization",
        help="Override WORKFLOW_DEFAULT_ORGANIZATION_ID for this run.",
    )
    args = parser.parse_args()
    asyncio.run(_run(args.organization))


if __name__ == "__main__":
    main()
