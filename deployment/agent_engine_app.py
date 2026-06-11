"""Agent Engine app wrapper and generic deploy routine.

Shared by ``deploy_buyer.py`` and ``deploy_vendor.py``. Provides:

- :class:`AgentEngineApp` — an ``AdkApp`` with Cloud Logging, Cloud Trace
  tracing, and user-feedback logging.
- :func:`deploy_agent_engine_app` — create-or-update a deployment for any
  ADK ``root_agent`` using a resolved :class:`DeploymentConfiguration`.
"""

from __future__ import annotations

import copy
import datetime
import json
import os
import sys
from pathlib import Path
from typing import Any

import cloudpickle
import vertexai
from google.adk.agents import BaseAgent
from google.adk.artifacts import GcsArtifactService
from google.cloud import logging as google_cloud_logging
from opentelemetry import trace
from opentelemetry.sdk.trace import TracerProvider, export
from vertexai import agent_engines
from vertexai.preview.reasoning_engines import AdkApp

from deployment.config import DeploymentConfiguration
from deployment.utils.gcs import create_bucket_if_not_exists
from deployment.utils.tracing import CloudTraceLoggingSpanExporter
from deployment.utils.typing import Feedback

# Register every ``deployment.*`` module for value-pickling so cloudpickle ships
# their class/function source inline in the agent snapshot. Without this, the
# Agent Engine container would try to ``import deployment`` at startup, which
# fails with ``ModuleNotFoundError: No module named 'deployment'`` because the
# ``deployment/`` directory is intentionally not shipped via ``extra_packages``
# (it contains deploy-time-only scripts).
def _register_deployment_modules_for_value_pickling() -> None:
    for name, module in list(sys.modules.items()):
        if name == "deployment" or name.startswith("deployment."):
            if module is not None:
                cloudpickle.register_pickle_by_value(module)


_register_deployment_modules_for_value_pickling()


class AgentEngineApp(AdkApp):
    """ADK application wrapper with logging, tracing, and feedback support."""

    def set_up(self) -> None:
        """Set up Cloud Logging and Cloud Trace for the deployed app."""
        super().set_up()
        logging_client = google_cloud_logging.Client()
        self.logger = logging_client.logger(__name__)

        service_name = os.environ.get("AGENT_SERVICE_NAME", "procuforge-agent")
        provider = TracerProvider()
        processor = export.BatchSpanProcessor(
            CloudTraceLoggingSpanExporter(
                project_id=os.environ.get("GOOGLE_CLOUD_PROJECT"),
                service_name=f"{service_name}-service",
            )
        )
        provider.add_span_processor(processor)
        trace.set_tracer_provider(provider)

    def register_feedback(self, feedback: dict[str, Any]) -> None:
        """Validate and log user feedback as a structured Cloud Logging entry."""
        feedback_obj = Feedback.model_validate(feedback)
        self.logger.log_struct(feedback_obj.model_dump(), severity="INFO")

    def register_operations(self) -> dict[str, list[str]]:
        """Expose ``register_feedback`` alongside the default operations."""
        operations = super().register_operations()
        operations[""] = operations[""] + ["register_feedback"]
        return operations

    def clone(self) -> "AgentEngineApp":
        """Create a copy of this application."""
        template_attributes = self._tmpl_attrs

        return self.__class__(
            agent=copy.deepcopy(template_attributes["agent"]),
            enable_tracing=bool(template_attributes.get("enable_tracing", False)),
            session_service_builder=template_attributes.get("session_service_builder"),
            artifact_service_builder=template_attributes.get(
                "artifact_service_builder"
            ),
            env_vars=template_attributes.get("env_vars"),
        )


def deploy_agent_engine_app(
    root_agent: BaseAgent,
    deployment_config: DeploymentConfiguration,
) -> agent_engines.AgentEngine:
    """Create or update a Vertex AI Agent Engine deployment for ``root_agent``.

    Steps:
        1. Create the per-agent artifacts bucket (if missing).
        2. Initialise Vertex AI for deployment.
        3. Read the pinned requirements file.
        4. Build the :class:`AgentEngineApp` with a GCS artifact service.
        5. Create a new agent or update the existing one (matched by name).
        6. Save deployment metadata to ``logs/<agent>_deployment_metadata.json``.

    Returns:
        The deployed ``AgentEngine`` instance.
    """
    print("🚀 Starting Agent Engine deployment...")
    print(f"📋 Deploying agent: {deployment_config.agent_name}")
    print(f"📋 Project: {deployment_config.project}")
    print(f"📋 Location: {deployment_config.location}")
    print(f"📋 Staging bucket: gs://{deployment_config.staging_bucket}")

    env_vars: dict[str, str] = {
        "NUM_WORKERS": "1",
        "AGENT_SERVICE_NAME": deployment_config.agent_name,
        "GOOGLE_CLOUD_AGENT_ENGINE_ENABLE_TELEMETRY": "true",
    }

    # Per-agent artifacts bucket so buyer and vendor never collide.
    safe_agent_name = deployment_config.agent_name.replace("_", "-")
    artifacts_bucket_name = (
        f"{deployment_config.project}-{safe_agent_name}-logs-data"
    )
    print(f"📦 Creating artifacts bucket: gs://{artifacts_bucket_name}")
    create_bucket_if_not_exists(
        bucket_name=artifacts_bucket_name,
        project=deployment_config.project,
        location=deployment_config.location,
    )

    vertexai.init(
        project=deployment_config.project,
        location=deployment_config.location,
        staging_bucket=f"gs://{deployment_config.staging_bucket}",
    )

    with open(deployment_config.requirements_file) as f:
        requirements = [
            line.strip()
            for line in f.read().splitlines()
            if line.strip() and not line.strip().startswith("#")
        ]

    agent_engine = AgentEngineApp(
        agent=root_agent,
        enable_tracing=True,
        artifact_service_builder=lambda: GcsArtifactService(
            bucket_name=artifacts_bucket_name
        ),
    )

    agent_config = {
        "agent_engine": agent_engine,
        "display_name": deployment_config.agent_name,
        "description": deployment_config.description,
        "extra_packages": deployment_config.extra_packages,
        "env_vars": env_vars,
        "requirements": requirements,
    }

    existing_agents = list(
        agent_engines.list(
            filter=f'display_name="{deployment_config.agent_name}"'
        )
    )

    if existing_agents:
        print(f"🔄 Updating existing agent: {deployment_config.agent_name}")
        remote_agent = existing_agents[0].update(**agent_config)
    else:
        print(f"🆕 Creating new agent: {deployment_config.agent_name}")
        remote_agent = agent_engines.create(**agent_config)

    metadata = {
        "remote_agent_engine_id": remote_agent.resource_name,
        "deployment_timestamp": datetime.datetime.now().isoformat(),
        "agent_name": deployment_config.agent_name,
        "project": deployment_config.project,
        "location": deployment_config.location,
        "artifacts_bucket": artifacts_bucket_name,
    }

    logs_dir = Path("logs")
    logs_dir.mkdir(exist_ok=True)
    metadata_file = logs_dir / f"{safe_agent_name}_deployment_metadata.json"
    with open(metadata_file, "w") as f:
        json.dump(metadata, f, indent=2)

    print("✅ Agent deployed successfully!")
    print(f"📄 Deployment metadata saved to: {metadata_file}")
    print(f"🆔 Agent Engine ID: {remote_agent.resource_name}")

    return remote_agent
