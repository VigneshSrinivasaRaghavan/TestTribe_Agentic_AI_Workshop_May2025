from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, cast
import xml.etree.ElementTree as ET

from src.graph.ui_executor.state import UIExecState


# ---------- Node 1: prepare config ----------
def prepare_config(state: UIExecState) -> UIExecState:
    # Make a mutable copy and keep its type as UIExecState for Pylance
    s = cast(UIExecState, dict(state))

    s.setdefault("project", "ui")
    s.setdefault("cwd", ".")
    s.setdefault("cmd", ["npm", "run", "test:ui"])
    s.setdefault("junit_path", "results/junit-ui.xml")
    s.setdefault("env", {})
    s.setdefault("attempt", 1)
    s.setdefault("max_attempts", 2)
    # Keep default approve=True for non-interactive runs; you’ll demo the gate
    s.setdefault("approved", True)

    s.setdefault("results", [])
    s.setdefault("summary", {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
    s.setdefault("errors", [])

    # Policy knobs
    s.setdefault("policy", "flaky_only")  # "always" | "flaky_only" | "none"
    s.setdefault("retry_scope", "full")   # "full" | "failed_only"
    return s


# ---------- Node 2: execute tests ----------
def execute_tests(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))

    cwd_str: str = cast(str, s.get("cwd", "."))
    cwd_path = Path(cwd_str)
    if not cwd_path.exists():
        errors: List[str] = cast(List[str], s.setdefault("errors", []))
        errors.append(f"[execute_tests] cwd not found: {cwd_path}")
        s["run_rc"], s["stdout"], s["stderr"] = 2, "", f"Directory not found: {cwd_path}"
        return s

    env = os.environ.copy()
    extra_env: Dict[str, str] = cast(Dict[str, str], s.get("env", {}))
    env.update(extra_env)

    cmd: List[str] = cast(List[str], s.get("cmd", []))
    try:
        proc = subprocess.run(
            cmd,
            cwd=str(cwd_path),
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=False,
        )
        s["run_rc"] = proc.returncode
        s["stdout"] = proc.stdout
        s["stderr"] = proc.stderr
    except Exception as e:
        errors: List[str] = cast(List[str], s.setdefault("errors", []))
        s["run_rc"] = 2
        s["stdout"] = ""
        s["stderr"] = f"[execute_tests] Exception: {e}"
        errors.append(str(e))
    return s


# ---------- Node 3: parse results (JUnit) ----------
def parse_results(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))

    cwd_str: str = cast(str, s.get("cwd", "."))
    junit_rel: str = cast(str, s.get("junit_path", "results/junit-ui.xml"))
    junit_path = Path(cwd_str) / junit_rel

    if not junit_path.exists():
        errors: List[str] = cast(List[str], s.setdefault("errors", []))
        errors.append(f"[parse_results] JUnit not found at: {junit_path}")
        return s

    try:
        root = ET.parse(str(junit_path)).getroot()
        # JUnit can be <testsuite> or <testsuites> → iterate all <testcase>
        testcases = list(root.iter("testcase"))

        total = len(testcases)
        passed = failed = skipped = 0
        cases: List[Dict[str, Any]] = []

        for tc in testcases:
            name = tc.attrib.get("name", "")
            suite = tc.attrib.get("classname", "")
            time_s = float(tc.attrib.get("time", "0") or 0.0)

            status = "passed"
            message = ""

            failure_el = tc.find("failure")
            skipped_el = tc.find("skipped")
            if failure_el is not None:
                status = "failed"
                message = (failure_el.attrib.get("message") or "").strip()
            elif skipped_el is not None:
                status = "skipped"

            if status == "passed":
                passed += 1
            elif status == "failed":
                failed += 1
            else:
                skipped += 1

            cases.append({
                "name": name,
                "suite": suite,
                "time_s": time_s,
                "status": status,
                "message": message,
                "attempt": int(s.get("attempt", 1) or 1),
                "project": "UI",
            })

        # accumulate results across attempts
        results: List[Dict[str, Any]] = cast(List[Dict[str, Any]], s.setdefault("results", []))
        results.extend(cases)
        s["summary"] = {"total": total, "passed": passed, "failed": failed, "skipped": skipped}

    except Exception as e:
        errors: List[str] = cast(List[str], s.setdefault("errors", []))
        errors.append(f"[parse_results] Exception: {e}")
    return s


# ---------- Node 4: approval checkpoint (human-in-the-loop) ----------
def approval_checkpoint(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))
    # If students are running non-interactively, keep approved=True by default.
    try:
        ans = input("Approve retry if failures > 0? (approve/deny) [approve]: ").strip().lower()
        if ans in ("approve", "deny"):
            s["approved"] = (ans == "approve")
    except EOFError:
        # Non-interactive environment; keep previous value
        pass
    return s


# ---------- Helper: simple flaky classifier ----------
def _is_retry_eligible_ui(case: Dict[str, Any]) -> bool:
    """
    Transparent heuristic:
    - Title includes '@flaky' OR
    - Common transient patterns in message (locator not visible, timeout)
    """
    title = (case.get("name") or "").lower()
    msg = (case.get("message") or "").lower()
    if "@flaky" in title:
        return True
    transient_signals = ("not visible", "timeout", "timed out", "network", "navigation")
    return any(sig in msg for sig in transient_signals)


# ---------- Router: decide after approval ----------
def decide_after_approval(state: UIExecState) -> str:
    """
    Return 'retry' or 'end' for the graph's conditional edge.
    """
    failed = int(state.get("summary", {}).get("failed", 0) or 0)
    if failed == 0:
        return "end"
    if state.get("policy") == "none":
        return "end"
    if state.get("approved") is False:
        return "end"
    if int(state.get("attempt", 1) or 1) >= int(state.get("max_attempts", 1) or 1):
        return "end"

    if state.get("policy") == "always":
        return "retry"

    # flaky_only: check if there exists at least one retry-eligible failed case (this attempt)
    attempt_now = int(state.get("attempt", 1) or 1)
    results: List[Dict[str, Any]] = cast(List[Dict[str, Any]], state.get("results", []))
    failed_cases = [c for c in results if c.get("attempt") == attempt_now and c.get("status") == "failed"]
    if any(_is_retry_eligible_ui(c) for c in failed_cases):
        return "retry"
    return "end"


# ---------- Node 5: retry bookkeeping ----------
def retry_once(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))
    current_attempt = int(s.get("attempt", 1) or 1)
    s["attempt"] = current_attempt + 1
    # For simplicity, we keep the same cmd and rerun the full suite.
    # (Later you can scope to failed-only using Playwright --grep.)
    return s
