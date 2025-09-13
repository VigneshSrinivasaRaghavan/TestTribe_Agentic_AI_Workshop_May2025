"""
Day 5 - Driver for Log Analyzer Pipeline
----------------------------------------
This script runs the LangGraph Log Analyzer pipeline.

Usage:
  python -m src.graph.drivers.run_log_analyzer_pipeline --inputs data/logs/runtime_errors.log
  python -m src.graph.drivers.run_log_analyzer_pipeline --inputs data/logs/runtime_errors.log data/logs/app_startup.log
"""

import logging
import argparse
from pprint import pprint

from src.graph.log_analyzer.graph import build_graph
from src.graph.log_analyzer.state import LogAnalyzerState

# Configure logger
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--inputs",
        nargs="+",
        help="One or more log file paths",
        default=None,
    )
    args = parser.parse_args()

    logger.info("🚀 Starting Log Analyzer pipeline...")

    # Build pipeline graph
    app = build_graph()

    # Initialize state
    init_state: LogAnalyzerState = {}
    if args.inputs:
        init_state["log_paths"] = args.inputs

    # Run pipeline
    final_state = app.invoke(init_state)

    # Summarize results
    issues = final_state.get("jira_issues", [])
    slack = final_state.get("slack_notifications", [])
    logger.info(
        f"✅ Finished: {len(final_state.get('groups', []))} groups analyzed, "
        f"{len(issues)} Jira issues created, Slack sent={bool(slack)}"
    )

    # Debugging/teaching: print full state
    pprint(final_state)


if __name__ == "__main__":
    main()
