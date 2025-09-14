"""
Test Case Generator (LangGraph)
---------------------------------------
This file defines the State class for our pipeline.
The State represents the "data backpack" that moves
through each node of the graph.
"""

from typing import List, Dict, TypedDict, Optional


class TestCaseState(TypedDict, total=False):
    """
    State for the Test Case Generator pipeline.
    Fields here are carried across all nodes in the graph.
    """
    # path to a requirement file (CLI input)
    requirement_path: str

    # Input: requirements text
    requirements: str

    # Output: list of generated test cases
    tests: List[str]

    # Output: TestRail case IDs after pushing
    testrail_case_ids: List[str]

    # Execution report (optional, future use)
    execution_report: Dict

    # Errors (if any) collected during pipeline
    errors: List[str]

    # HITL decision (approved/rejected)
    approval_decision: Optional[str]