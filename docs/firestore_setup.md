# Firestore setup (ProcuForge)

This project uses the official [Google Cloud Firestore](https://cloud.google.com/firestore) Python client (`google-cloud-firestore`) with **Application Default Credentials (ADC)**.

## Prerequisites

- A Google Cloud or Firebase project with **Firestore enabled** (Native mode).
- Python **3.13+** and dependencies installed: `uv sync`.

## Environment variables

| Variable | Required | Description |
|----------|----------|-------------|
| `GOOGLE_CLOUD_PROJECT` | Yes (unless emulator) | GCP project ID used for Firestore. **`GOOGLE_PROJECT_ID` is also accepted** (alias) for compatibility with other tooling in this repo. |
| `FIRESTORE_DATABASE_ID` | Optional | Firestore **database** id (multi-DB). Leave unset to use the project’s **default** database. Set to `(default)` to force default explicitly. |
| `GOOGLE_APPLICATION_CREDENTIALS` | For local key-based auth | Absolute path to a **service account JSON** key with Firestore access (e.g. `roles/datastore.user` or a Firebase Admin–style role that includes Firestore). |
| `FIRESTORE_EMULATOR_HOST` | Optional | e.g. `127.0.0.1:8080` — points the client at the [Firestore emulator](https://firebase.google.com/docs/emulator-suite/connect_firestore). |
| `FIRESTORE_EMULATOR_PROJECT_ID` | Optional | Used only when the emulator is active and `GOOGLE_CLOUD_PROJECT` / `GOOGLE_PROJECT_ID` are unset. Defaults to `demo-procuforge`. |

Optional: put values in a **`.env`** file in the project root. `FirestoreSettings` loads `.env` via `pydantic-settings`.

## Authentication

**Local development (recommended):**

1. Install [Google Cloud CLI](https://cloud.google.com/sdk/docs/install).
2. Run:

   ```bash
   gcloud auth application-default login
   ```

3. Set `GOOGLE_CLOUD_PROJECT` to your project ID.

**Service account (CI, servers, explicit key file):**

1. Create a service account in IAM with Firestore permissions.
2. Download a JSON key and set:

   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/key.json
   export GOOGLE_CLOUD_PROJECT=your-project-id
   ```

**On Google Cloud (Cloud Run, GKE, Compute Engine):** attach a service account to the workload; do not commit keys. Prefer **Secret Manager** for any secrets.

## Code layout

- `db/firestore/config.py` — env / project resolution.
- `db/firestore/client.py` — `get_firestore_client()` (lazy singleton).
- `db/firestore/serialization.py` — Pydantic → Firestore dict (camelCase, server timestamps).
- `db/firestore/repositories/categories.py` — `CategoryRepository` (sync).
- `db/firestore/repositories/products.py` — `ProductRepository` (sync).
- `db/firestore/async_repositories/` — `AsyncCategoryRepository`, `AsyncProductRepository` (wrap sync calls with `asyncio.to_thread` for FastAPI).

Document **IDs** are the same as model `id` (`cat_it`, `prod_dell_5440`, …). The `id` field is **not** duplicated inside the stored document body by default.

## FastAPI (async HTTP API)

The Google Firestore Python client is **synchronous**. For FastAPI, repositories run blocking work in the **default thread pool** via [`asyncio.to_thread`](https://docs.python.org/3/library/asyncio-task.html#asyncio.to_thread) so the event loop stays responsive. This is a common, production-safe pattern until you adopt a fully async Firestore stack.

Run locally:

```bash
uv run uvicorn api.main:app --reload --host 0.0.0.0 --port 8000
```

- **OpenAPI:** [http://127.0.0.1:8000/docs](http://127.0.0.1:8000/docs)
- **Routes:** `POST/GET/PATCH/PUT/DELETE` under `/api/v1/categories` and `/api/v1/products`; `GET /health`.
- **Duplicate create:** HTTP **409** (`Conflict` from Firestore).

Optional CORS (comma-separated origins; default `*`):

| Variable | Description |
|----------|-------------|
| `CORS_ALLOW_ORIGINS` | e.g. `http://localhost:3000,https://app.example.com` or `*` |
| `CORS_ALLOW_CREDENTIALS` | `true` only when origins are **not** `*` (browser security restriction). |

## Usage example

```python
from datetime import datetime, timezone

from google.cloud import firestore

from db.collections import Category, DocumentMetadata, Product, EstimatedPriceRange
from db.firestore import CategoryRepository, ProductRepository, get_firestore_client

client: firestore.Client = get_firestore_client()
categories = CategoryRepository(client)
products = ProductRepository(client)

now = datetime.now(timezone.utc)
meta = DocumentMetadata(created_at=now, updated_at=now)

cat = Category(
    id="cat_it",
    name="IT & Electronics",
    description="Technology related products",
    icon="laptop",
    active=True,
    metadata=meta,
)
categories.create(cat)

product = Product(
    id="prod_dell_5440",
    category_id="cat_it",
    name="Dell Latitude 5440",
    brand="Dell",
    type="physical",
    description="14-inch business laptop",
    specifications={"cpu": "Intel i7"},
    unit_of_measure="piece",
    estimated_price_range=EstimatedPriceRange(currency="USD", range_min=950, range_max=1200),
    aliases=["dell business laptop"],
    active=True,
    metadata=meta,
)
products.create(product)

categories.update("cat_it", {"active": False})
products.delete("prod_dell_5440")
categories.delete("cat_it")
```

- **`create`**: fails with `google.api_core.exceptions.Conflict` if the document ID already exists.
- **`update`**: merges fields and sets `metadata.updatedAt` to the server timestamp.
- **`replace`**: overwrites the full document; use when you have a complete model from `get()` with edits.

## Emulator quick note

Start the Firebase emulator suite (Firestore), then:

```bash
export FIRESTORE_EMULATOR_HOST=127.0.0.1:8080
export GOOGLE_CLOUD_PROJECT=demo-local   # or rely on FIRESTORE_EMULATOR_PROJECT_ID
```

Run your script with `uv run python ...`.

## Troubleshooting

- **`503` / `ServiceUnavailable` / “Could not contact DNS servers” when resolving `firestore.googleapis.com`:** your environment has no working DNS or no route to Google (offline, VPN, firewall, or a sandbox without network). Fix connectivity, then retry. The verify script prints a short hint for this case.
- **Python/gRPC DNS works in `dig` but not in the app:** set `export GRPC_DNS_RESOLVER=native` (macOS / odd resolvers). You can add it to `.env` if your process loads env before gRPC initializes.
- **`400` / “Firestore API data access is disabled”:** enable the **Cloud Firestore API** for the project in [Google Cloud Console → APIs & Services](https://console.cloud.google.com/apis/library/firestore.googleapis.com), confirm the Firestore database exists (Native mode) and that `FIRESTORE_DATABASE_ID` matches the database id. Organization policies can also block API access.
- **`KeyboardInterrupt` during long retries:** the default Firestore client can retry for a long time on `UNAVAILABLE`. The `scripts/verify_firestore_category.py` script uses a **short retry budget** (see `--deadline-sec`, default ~20s) so broken DNS/network fails faster.

## Security

- Never commit service account JSON or `.env` with real credentials.
- Lock down Firestore with [security rules](https://firebase.google.com/docs/firestore/security/get-started) for client SDKs; server SDKs using Admin credentials bypass rules—enforce authorization in your application layer.
