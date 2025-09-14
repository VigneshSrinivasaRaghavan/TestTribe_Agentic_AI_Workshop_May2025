"""
Day 5 - Test Case Generator (LangGraph with HITL)
-------------------------------------------------
Pipeline flow:
  1. read_requirements
  2. generate_tests_with_llm
  3. approval_checkpoint (human approve/reject)
  4. push_to_testrail (only if approved)
"""

import logging
from langgraph.graph import StateGraph, END

from .state import TestCaseState
from .nodes import read_requirements, generate_tests_with_llm, push_to_testrail

# Logger
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)


def approval_checkpoint(state: TestCaseState) -> TestCaseState:
    """
    Human-in-the-Loop approval checkpoint.
    Explicitly asks for 'approve' or 'reject' and records decision in state.
    """
    tests = state.get("tests", [])
    logger.info("⏸️ Pausing for human approval. Generated tests:")
    for i, t in enumerate(tests, 1):
        logger.info(f"   {i}. {t}")

    # Loop until we get a clear decision
    while True:
        choice = input(
            "\nType 'approve' to continue or 'reject' to stop: "
        ).strip().lower()
        if choice in {"approve", "approved"}:
            state["approval_decision"] = "approved"
            logger.info("✅ Human approved test cases.")
            return state
        if choice in {"reject", "rejected", "deny", "denied"}:
            state["approval_decision"] = "rejected"
            logger.warning("🚫 Human rejected test cases.")
            return state
        print("Please type 'approve' or 'reject'.")

    # unreachable
    # return state


def _route_after_approval(state: TestCaseState) -> str:
    """
    Router for conditional edges after approval node.
    Must return one of the keys we wire below.
    """
    return "approved" if state.get("approval_decision") == "approved" else "rejected"


def build_graph():
    """Build and return the compiled Test Case Generator pipeline with HITL."""

    workflow = StateGraph(TestCaseState)

    # Nodes
    workflow.add_node("read_requirements", read_requirements)
    workflow.add_node("generate_tests_with_llm", generate_tests_with_llm)
    workflow.add_node("approval_checkpoint", approval_checkpoint)
    workflow.add_node("push_to_testrail", push_to_testrail)

    # Edges
    workflow.set_entry_point("read_requirements")
    workflow.add_edge("read_requirements", "generate_tests_with_llm")

    # Conditional routing based on approval decision
    workflow.add_conditional_edges(
        "approval_checkpoint",
        _route_after_approval,
        {
            "approved": "push_to_testrail",
            "rejected": END,
        },
    )

    # After LLM, always go to approval
    workflow.add_edge("generate_tests_with_llm", "approval_checkpoint")

    # Push goes to END
    workflow.add_edge("push_to_testrail", END)

    app = workflow.compile()
    logger.info("✅ Test Case Generator pipeline (with approve/reject) built successfully")
    return app
