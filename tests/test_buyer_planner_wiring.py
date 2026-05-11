"""Wiring checks for buyer planner (no live LLM or A2A)."""

import unittest

from google.adk.tools.agent_tool import AgentTool

from procu_forge_buyer.agent import root_agent
from procu_forge_buyer.subagents.planner import PlannerPlan


class TestBuyerPlannerWiring(unittest.TestCase):
    def test_root_agent_exposes_planner_tool(self) -> None:
        self.assertTrue(root_agent.tools)
        planner_tools = [
            t
            for t in root_agent.tools
            if isinstance(t, AgentTool) and getattr(t.agent, "name", None) == "planner_agent"
        ]
        self.assertEqual(len(planner_tools), 1)

    def test_planner_plan_round_trip(self) -> None:
        raw = {
            "next_action": "search_vendors",
            "agent_to_invoke": "vendor_search_agent",
            "reasoning": "No vendor list in thread yet; need Firestore search.",
            "other_context": {"product_id": "p1"},
            "confidence": 0.9,
        }
        plan = PlannerPlan.model_validate(raw)
        dumped = plan.model_dump(mode="json")
        again = PlannerPlan.model_validate(dumped)
        self.assertEqual(again.next_action, "search_vendors")
        self.assertEqual(again.agent_to_invoke, "vendor_search_agent")

    def test_complete_allows_null_agent(self) -> None:
        plan = PlannerPlan(
            next_action="complete",
            agent_to_invoke=None,
            reasoning="PO and verification finished.",
            other_context={},
            confidence=1.0,
        )
        self.assertIsNone(plan.agent_to_invoke)


if __name__ == "__main__":
    unittest.main()
