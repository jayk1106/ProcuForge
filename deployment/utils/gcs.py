"""Google Cloud Storage helpers for Agent Engine deployment."""

from __future__ import annotations

from google.cloud import storage
from google.cloud.exceptions import Conflict


def create_bucket_if_not_exists(
    bucket_name: str, project: str, location: str
) -> storage.Bucket:
    """Create a GCS bucket if it does not already exist.

    The bucket is used by Agent Engine to store artifacts/logs for a deployed
    agent. Re-running deployment is safe: an existing bucket is returned as-is.

    Args:
        bucket_name: Name of the bucket (globally unique, no ``gs://`` prefix).
        project: Google Cloud project ID that owns the bucket.
        location: Region for the bucket (e.g. ``us-central1``).

    Returns:
        The existing or newly created ``storage.Bucket``.
    """
    client = storage.Client(project=project)

    bucket = client.bucket(bucket_name)
    if bucket.exists():
        print(f"ℹ️  Bucket already exists: gs://{bucket_name}")
        return bucket

    try:
        bucket = client.create_bucket(bucket_name, location=location)
        print(f"✅ Created bucket: gs://{bucket_name} ({location})")
    except Conflict:
        # Raced with another create (or owned elsewhere) — reuse it.
        bucket = client.bucket(bucket_name)
        print(f"ℹ️  Bucket already exists (conflict): gs://{bucket_name}")

    return bucket
