from __future__ import annotations

from langgraph.graph import StateGraph, END

from src.graph.ui_executor.state import UIExecState
from src.graph.ui_executor import nodes


def build_ui_app():
    """
    Wire the UI Executor graph with five small nodes:
      prepare -> run -> parse -> approve -> (retry|END)
    """
    g = StateGraph(UIExecState)

    # Nodes
    g.add_node("prepare", nodes.prepare_config)
    g.add_node("run", nodes.execute_tests)
    g.add_node("parse", nodes.parse_results)
    g.add_node("approve", nodes.approval_checkpoint)
    g.add_node("retry", nodes.retry_once)

    # Linear edges
    g.set_entry_point("prepare")
    g.add_edge("prepare", "run")
    g.add_edge("run", "parse")
    g.add_edge("parse", "approve")

    # Conditional branch after approval
    g.add_conditional_edges(
        "approve",
        nodes.decide_after_approval,
        {
            "retry": "retry",
            "end": END,
        },
    )

    # Retry loops back to execute again
    g.add_edge("retry", "run")

    return g.compile()


__all__ = ["build_ui_app"]
