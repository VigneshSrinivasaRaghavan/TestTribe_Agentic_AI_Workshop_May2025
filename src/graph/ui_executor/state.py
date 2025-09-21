from __future__ import annotations

from typing import Any, Dict, List, Literal, TypedDict


class UIExecState(TypedDict, total=False):
    """
    Execution state carried across the UI Executor graph.
    Keep fields simple & explainable for students.
    """

    # Identity
    project: Literal["ui"]            # Fixed tag for summaries/logging

    # Execution config
    cwd: str                          # Playwright project directory
    cmd: List[str]                    # Command array to run tests
    junit_path: str                   # Path to JUnit XML (e.g., results/junit-ui.xml)
    env: Dict[str, str]               # Extra env vars (e.g., {"FLAKE_P": "1"})

    # Attempts / approval
    attempt: int                      # Current attempt number (1..max_attempts)
    max_attempts: int                 # Max attempts (e.g., 2)
    approved: bool                    # Human-in-the-loop gate to allow retry

    # Process outputs
    run_rc: int                       # Last process return code
    stdout: str                       # Last stdout
    stderr: str                       # Last stderr

    # Parsed results (normalized)
    results: List[Dict[str, Any]]     # Flattened test cases with status, name, duration, etc.
    summary: Dict[str, int]           # {"total": int, "passed": int, "failed": int, "skipped": int}
    errors: List[str]                 # Non-test errors (e.g., file missing, parse failure)

    # Policy toggles (optional; defaults set in nodes)
    policy: Literal["always", "flaky_only", "none"]
    retry_scope: Literal["full", "failed_only"]

    # LLM outputs
    llm_summary:str                # LLM-generated summary of test results

    # Memory Output
    memory_notes: List[str]         # Insights from the memory


__all__ = ["UIExecState"]
