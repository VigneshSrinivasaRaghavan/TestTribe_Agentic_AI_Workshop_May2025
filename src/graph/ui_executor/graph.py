from __future__ import annotations

from langgraph.graph import StateGraph, END

from src.graph.ui_executor.state import UIExecState
# Import node functions explicitly so Pylance recognizes them
from src.graph.ui_executor.nodes import (
    prepare_config,
    execute_tests,
    parse_results,
    llm_triage,
    persist_to_memory,   # 🔹 NEW NODE
    approval_checkpoint,
    retry_once,
    decide_after_approval,
)


def build_ui_app():
    """
    Wire the UI Executor graph with seven small nodes:
      prepare -> run -> parse -> llm_triage -> persist_to_memory -> approve -> (retry|END)
    """
    g = StateGraph(UIExecState)

    # Nodes
    g.add_node("prepare", prepare_config)
    g.add_node("run", execute_tests)
    g.add_node("parse", parse_results)
    g.add_node("llm_triage", llm_triage)
    g.add_node("persist", persist_to_memory)   # 🔹 NEW NODE
    g.add_node("approve", approval_checkpoint)
    g.add_node("retry", retry_once)

    # Linear edges
    g.set_entry_point("prepare")
    g.add_edge("prepare", "run")
    g.add_edge("run", "parse")
    g.add_edge("parse", "llm_triage")
    g.add_edge("llm_triage", "persist")        # 🔹 Inserted persist step
    g.add_edge("persist", "approve")           # 🔹 Persist flows into approval

    # Conditional branch after approval
    g.add_conditional_edges(
        "approve",
        decide_after_approval,
        {
            "retry": "retry",
            "end": END,
        },
    )

    # Retry loops back to execute again
    g.add_edge("retry", "run")

    return g.compile()


__all__ = ["build_ui_app"]
