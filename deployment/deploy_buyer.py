"""Deploy the ProcuForge buyer agent to Vertex AI Agent Engine.

Run from the repository root:

    uv run python -m deployment.deploy_buyer
"""

from __future__ import annotations

from deployment.agent_engine_app import deploy_agent_engine_app
from deployment.config import (
    build_config,
    initialize_vertex_ai,
    print_config_summary,
)
from procu_forge_buyer.agent import root_agent

BUYER_DEPLOYMENT_NAME = "procu-forge-buyer"
BUYER_DESCRIPTION = (
    "Buyer procurement orchestrator: runs vendor search, negotiation, "
    "decision, and purchase-order management as a loop until the request "
    "reaches a terminal or human-gated status."
)
BUYER_EXTRA_PACKAGES = [
    "./adk_vertex_model",
    "./procu_forge_buyer",
    "./communication",
    "./db",
]


def main() -> None:
    print(
        """
    ╔═══════════════════════════════════════════════════════════╗
    ║   🤖 DEPLOYING PROCUFORGE BUYER TO AGENT ENGINE 🤖        ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    )

    config = build_config(
        deployment_name=BUYER_DEPLOYMENT_NAME,
        extra_packages=BUYER_EXTRA_PACKAGES,
        description=BUYER_DESCRIPTION,
    )
    print_config_summary(config)

    initialize_vertex_ai(config)
    deploy_agent_engine_app(root_agent=root_agent, deployment_config=config)


if __name__ == "__main__":
    main()
