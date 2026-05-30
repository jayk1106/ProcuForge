"""Configuration for ProcuForge ADK Agent Engine deployments.

This module is shared by both the buyer and vendor deploy scripts. Unlike a
single-agent template, it has **no import-time side effects**: each deploy
script explicitly calls :func:`build_config` (passing its own agent name,
extra packages, and description) and then :func:`initialize_vertex_ai`.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

import google.auth
import vertexai


def load_environment_variables() -> None:
    """Load environment variables from the repo-root ``.env`` if present."""
    try:
        from dotenv import load_dotenv

        env_file = Path(__file__).resolve().parent.parent / ".env"
        if env_file.exists():
            load_dotenv(env_file)
            print(f"✅ Loaded environment variables from {env_file}")
        else:
            print(f"ℹ️  No .env file found at {env_file}")
    except ImportError:
        print("ℹ️  python-dotenv not installed, skipping .env file loading")


@dataclass
class DeploymentConfiguration:
    """Resolved configuration needed to deploy one agent to Agent Engine."""

    project: str
    location: str
    staging_bucket: str
    agent_name: str
    description: str
    extra_packages: list[str]
    requirements_file: str
    model: str


def _resolve_project_id() -> str:
    """Resolve the Google Cloud project ID from env or gcloud defaults."""
    project_id = os.environ.get("GOOGLE_CLOUD_PROJECT") or os.environ.get(
        "GOOGLE_PROJECT_ID"
    )
    if not project_id:
        try:
            _, project_id = google.auth.default()
        except Exception:
            project_id = None

    if not project_id:
        raise ValueError(
            "❌ Missing GOOGLE_CLOUD_PROJECT environment variable!\n"
            "Please set it in your .env file or run:\n"
            "  gcloud config set project YOUR_PROJECT_ID"
        )
    return project_id


def build_config(
    deployment_name: str,
    extra_packages: list[str],
    description: str,
) -> DeploymentConfiguration:
    """Build and validate the deployment configuration for a single agent.

    Args:
        deployment_name: Display name in Agent Engine (hyphens allowed).
        extra_packages: Local package directories to bundle (e.g. ``./db``).
        description: Human-readable agent description shown in Agent Engine.

    Returns:
        A validated :class:`DeploymentConfiguration`.

    Raises:
        ValueError: If any required setting is missing or invalid.
    """
    load_environment_variables()

    project_id = _resolve_project_id()

    location = os.environ.get("GOOGLE_CLOUD_LOCATION") or os.environ.get(
        "GOOGLE_BUCKET_REGION", "us-central1"
    )
    if not location:
        raise ValueError(
            "❌ Missing GOOGLE_CLOUD_LOCATION environment variable!\n"
            "Please set it in your .env file (e.g., 'us-central1')"
        )

    staging_bucket = os.environ.get("GOOGLE_CLOUD_STAGING_BUCKET")
    if not staging_bucket:
        raise ValueError(
            "❌ Missing GOOGLE_CLOUD_STAGING_BUCKET environment variable!\n"
            "This is required for Agent Engine deployment.\n"
            "Please add it to your .env file (bucket name, without 'gs://')."
        )
    # Normalise: callers may set it with or without the gs:// prefix.
    staging_bucket = staging_bucket.removeprefix("gs://").rstrip("/")

    if not deployment_name:
        raise ValueError("❌ deployment_name must be a non-empty string.")

    extra_packages = [pkg.strip() for pkg in extra_packages if pkg.strip()]
    if not extra_packages:
        raise ValueError("❌ extra_packages must contain at least one path.")

    for pkg in extra_packages:
        if not Path(pkg).exists():
            raise ValueError(
                f"❌ extra_package path does not exist: {pkg}\n"
                "Run the deploy script from the repository root."
            )

    requirements_file = os.environ.get("REQUIREMENTS_FILE", ".requirements.txt")
    if not Path(requirements_file).exists():
        raise ValueError(
            f"❌ Requirements file not found: {requirements_file}\n"
            "Please run 'uv export --no-hashes > .requirements.txt' to generate it."
        )

    model = os.environ.get("MODEL", "gemini-flash-latest")

    return DeploymentConfiguration(
        project=project_id,
        location=location,
        staging_bucket=staging_bucket,
        agent_name=deployment_name,
        description=description,
        extra_packages=extra_packages,
        requirements_file=requirements_file,
        model=model,
    )


def initialize_vertex_ai(config: DeploymentConfiguration) -> None:
    """Initialise Vertex AI for the given deployment configuration."""
    print("\n🔧 Initializing Vertex AI...")
    print(f"  Project: {config.project}")
    print(f"  Location: {config.location}")
    print(f"  Staging Bucket: gs://{config.staging_bucket}")

    try:
        vertexai.init(
            project=config.project,
            location=config.location,
            staging_bucket=f"gs://{config.staging_bucket}",
        )
        print("✅ Vertex AI initialized successfully!")
    except Exception as exc:
        print(f"❌ Failed to initialize Vertex AI: {exc}")
        print("\n🔧 Setup checklist:")
        print("  1. Set GOOGLE_CLOUD_PROJECT in .env file")
        print("  2. Run: gcloud auth application-default login")
        print("  3. Run: gcloud config set project YOUR_PROJECT_ID")
        print("  4. Enable required APIs in Google Cloud Console")
        raise


def print_config_summary(config: DeploymentConfiguration) -> None:
    """Print a human-readable summary of the resolved configuration."""
    print("\n📋 Configuration Summary:")
    print(f"  Agent Name: {config.agent_name}")
    print(f"  Description: {config.description}")
    print(f"  Model: {config.model}")
    print(f"  Project: {config.project}")
    print(f"  Location: {config.location}")
    print(f"  Staging Bucket: gs://{config.staging_bucket}")
    print(f"  Extra Packages: {', '.join(config.extra_packages)}")
    print(f"  Requirements File: {config.requirements_file}")
    print("=" * 50)
