#!/usr/bin/env python3
"""
Import dev seed JSON under data/dev/ into Firestore.

Behavior:
- Default: create documents; if a document already exists, it is skipped and import continues.
- Optional: --upsert to set(merge=True) for every doc (idempotent overwrite/merge).

Run:
  uv run python scripts/import_dev_seed_data.py
  uv run python scripts/import_dev_seed_data.py --upsert

Tip (macOS gRPC resolver quirks):
  export GRPC_DNS_RESOLVER=native
"""

from __future__ import annotations

import json
import os
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

# gRPC reads this env very early; set it before importing Google clients.
if "--grpc-dns-native" in sys.argv and not os.environ.get("GRPC_DNS_RESOLVER"):
    os.environ["GRPC_DNS_RESOLVER"] = "native"

from dotenv import load_dotenv
from google.api_core import retry as google_retry
from google.api_core.exceptions import Conflict
from google.cloud.firestore import SERVER_TIMESTAMP

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.collections.category import COLLECTION_ID as CATEGORIES_COLLECTION
from db.collections.organisation import COLLECTION_ID as ORGS_COLLECTION
from db.collections.product import COLLECTION_ID as PRODUCTS_COLLECTION
from db.collections.user import COLLECTION_ID as USERS_COLLECTION
from db.collections.vendor import COLLECTION_ID as VENDORS_COLLECTION
from db.collections.vendor_org_relation import COLLECTION_ID as VENDOR_ORG_REL_COLLECTION
from db.collections.vendor_product import COLLECTION_ID as VENDOR_PRODUCTS_COLLECTION
from db.firestore import get_firestore_client

DATA_DIR = ROOT / "data" / "initial_data"


@dataclass
class ImportStats:
    created: int = 0
    skipped_exists: int = 0
    upserted: int = 0
    errors: int = 0


def _load(path: Path) -> list[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, list):
        raise TypeError(f"{path} must be a JSON array")
    return data


def _fail_fast_retry(deadline_sec: float) -> google_retry.Retry:
    return google_retry.Retry(
        deadline=deadline_sec,
        initial=0.5,
        maximum=6.0,
        multiplier=1.7,
    )

def _parse_iso_datetime(value: str) -> datetime | None:
    # Accept `...Z` and `...+00:00` styles
    raw = value.strip()
    if not raw:
        return None
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        return datetime.fromisoformat(raw)
    except ValueError:
        return None


def _coerce_firestore_timestamps(body: Any) -> Any:
    """
    Convert ISO-8601 strings in *At fields to datetime so Firestore stores Timestamps.
    Also converts metadata.createdAt/updatedAt to SERVER_TIMESTAMP so seed imports
    don't store them as strings.
    """
    if isinstance(body, list):
        return [_coerce_firestore_timestamps(x) for x in body]
    if not isinstance(body, dict):
        return body

    out: dict[str, Any] = {}
    for k, v in body.items():
        if k == "metadata" and isinstance(v, dict):
            meta = dict(v)
            # Prefer server timestamps for seed imports
            if "createdAt" in meta:
                meta["createdAt"] = SERVER_TIMESTAMP
            if "updatedAt" in meta:
                meta["updatedAt"] = SERVER_TIMESTAMP
            out[k] = meta
            continue

        if isinstance(v, str) and k.endswith("At"):
            dt = _parse_iso_datetime(v)
            out[k] = dt if dt is not None else v
            continue

        out[k] = _coerce_firestore_timestamps(v)

    return out


def _import_collection(
    *,
    collection_name: str,
    docs: list[dict[str, Any]],
    upsert: bool,
    client,
    deadline_sec: float,
    rpc_timeout_sec: float,
    stats: ImportStats,
) -> None:
    col = client.collection(collection_name)
    retry = _fail_fast_retry(deadline_sec)

    for doc in docs:
        doc_id = doc.get("id")
        if not isinstance(doc_id, str) or not doc_id:
            stats.errors += 1
            print(f"[ERROR] {collection_name}: missing/invalid id in doc: {doc!r}")
            continue

        body = dict(doc)
        body.pop("id", None)  # doc id is stored as document name
        body = _coerce_firestore_timestamps(body)

        try:
            if upsert:
                col.document(doc_id).set(body, merge=True, retry=retry, timeout=rpc_timeout_sec)
                stats.upserted += 1
            else:
                col.document(doc_id).create(body, retry=retry, timeout=rpc_timeout_sec)
                stats.created += 1
        except Conflict:
            stats.skipped_exists += 1
        except Exception as e:
            stats.errors += 1
            print(f"[ERROR] {collection_name}/{doc_id}: {e}")


def main() -> int:
    load_dotenv()

    upsert = "--upsert" in sys.argv
    deadline_sec = float(os.environ.get("FIRESTORE_IMPORT_DEADLINE_SEC", "20"))
    rpc_timeout_sec = float(os.environ.get("FIRESTORE_IMPORT_RPC_TIMEOUT_SEC", "12"))

    files = {
        CATEGORIES_COLLECTION: DATA_DIR / "categories.json",
        PRODUCTS_COLLECTION: DATA_DIR / "products.json",
        VENDORS_COLLECTION: DATA_DIR / "vendors.json",
        ORGS_COLLECTION: DATA_DIR / "organisations.json",
        USERS_COLLECTION: DATA_DIR / "users.json",
        VENDOR_PRODUCTS_COLLECTION: DATA_DIR / "vendorProducts.json",
        VENDOR_ORG_REL_COLLECTION: DATA_DIR / "vendorOrgRelations.json",
    }

    missing = [str(p) for p in files.values() if not p.exists()]
    if missing:
        print(f"Missing seed files: {missing}", file=sys.stderr)
        return 2

    # Order matters only for human sanity; Firestore itself doesn't enforce FK constraints.
    ordered_collections = [
        CATEGORIES_COLLECTION,
        PRODUCTS_COLLECTION,
        VENDORS_COLLECTION,
        ORGS_COLLECTION,
        USERS_COLLECTION,
        VENDOR_PRODUCTS_COLLECTION,
        VENDOR_ORG_REL_COLLECTION,
    ]

    stats = ImportStats()

    client = get_firestore_client()

    print(
        f"Import mode: {'UPSERT (merge=True)' if upsert else 'CREATE (skip if exists)'}",
        flush=True,
    )
    for col_name in ordered_collections:
        docs = _load(files[col_name])
        print(f"- {col_name}: {len(docs)} docs", flush=True)
        _import_collection(
            collection_name=col_name,
            docs=docs,
            upsert=upsert,
            client=client,
            deadline_sec=deadline_sec,
            rpc_timeout_sec=rpc_timeout_sec,
            stats=stats,
        )

    print("\nDone.")
    print(f"  created: {stats.created}")
    print(f"  skipped_exists: {stats.skipped_exists}")
    print(f"  upserted: {stats.upserted}")
    print(f"  errors: {stats.errors}")

    return 0 if stats.errors == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())

