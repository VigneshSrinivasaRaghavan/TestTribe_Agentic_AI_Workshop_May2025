"""
Day 5 - Log Analyzer (LangGraph)
--------------------------------
This file assembles the pipeline graph using LangGraph.

Flow:
  1. read_logs 
  2. group_events 
  3. analyze_with_llm 
  4. create_jira_tickets 
  5. send_slack_summary
"""

import logging
from langgraph.graph import StateGraph, END

from .state import LogAnalyzerState
from .nodes import (
    read_logs,
    group_events,
    analyze_with_llm,
    create_jira_tickets,
    send_slack_summary,
)

# Logger setup
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)


def build_graph():
    """Build and return the compiled Log Analyzer pipeline."""

    # Create graph with LogAnalyzerState
    workflow = StateGraph(LogAnalyzerState)

    # Register nodes
    workflow.add_node("read_logs", read_logs)
    workflow.add_node("group_events", group_events)
    workflow.add_node("analyze_with_llm", analyze_with_llm)
    workflow.add_node("create_jira_tickets", create_jira_tickets)
    workflow.add_node("send_slack_summary", send_slack_summary)

    # Define edges (execution order)
    workflow.set_entry_point("read_logs")
    workflow.add_edge("read_logs", "group_events")
    workflow.add_edge("group_events", "analyze_with_llm")
    workflow.add_edge("analyze_with_llm", "create_jira_tickets")
    workflow.add_edge("create_jira_tickets", "send_slack_summary")
    workflow.add_edge("send_slack_summary", END)

    # Compile
    app = workflow.compile()
    logger.info("✅ Log Analyzer pipeline built successfully")
    return app
