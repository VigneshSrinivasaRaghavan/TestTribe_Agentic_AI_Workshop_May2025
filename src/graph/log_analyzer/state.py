"""
Day 5 - Log Analyzer (LangGraph)
--------------------------------
This file defines the State class for the Log Analyzer pipeline.
The State represents the "data backpack" that moves through each node.
"""

from typing import List, Dict, TypedDict, Optional


class LogAnalyzerState(TypedDict, total=False):
    """
    State for the Log Analyzer pipeline.
    Fields here are carried across all nodes in the graph.
    """

    # Optional: one or more log file paths (CLI input)
    log_paths: List[str]

    # Input: raw log lines
    logs: List[str]

    # Output: grouped log events (signatures, counts, examples)
    groups: List[Dict]

    # Output: LLM-generated findings (summary + enriched groups)
    findings: Dict

    # Output: Jira issues created (keys list)
    jira_issues: List[str]

    # Output: Slack messages posted (IDs or timestamps)
    slack_notifications: List[str]

    # Errors (if any) collected during pipeline
    errors: List[str]
