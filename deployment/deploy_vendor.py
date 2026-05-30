"""Deploy the ProcuForge vendor agent to Vertex AI Agent Engine.

Run from the repository root:

    uv run python -m deployment.deploy_vendor
"""

from __future__ import annotations

from deployment.agent_engine_app import deploy_agent_engine_app
from deployment.config import (
    build_config,
    initialize_vertex_ai,
    print_config_summary,
)
from procu_forge_vendor.agent import root_agent

VENDOR_DEPLOYMENT_NAME = "procu-forge-vendor"
VENDOR_DESCRIPTION = (
    "Vendor sales agent: issues quotes for RFQs, negotiates pricing, and "
    "handles purchase-order acknowledgement and invoicing."
)
VENDOR_EXTRA_PACKAGES = ["./procu_forge_vendor", "./communication", "./db"]


def main() -> None:
    print(
        """
    ╔═══════════════════════════════════════════════════════════╗
    ║   🤖 DEPLOYING PROCUFORGE VENDOR TO AGENT ENGINE 🤖       ║
    ╚═══════════════════════════════════════════════════════════╝
    """
    )

    config = build_config(
        deployment_name=VENDOR_DEPLOYMENT_NAME,
        extra_packages=VENDOR_EXTRA_PACKAGES,
        description=VENDOR_DESCRIPTION,
    )
    print_config_summary(config)

    initialize_vertex_ai(config)
    deploy_agent_engine_app(root_agent=root_agent, deployment_config=config)


if __name__ == "__main__":
    main()
