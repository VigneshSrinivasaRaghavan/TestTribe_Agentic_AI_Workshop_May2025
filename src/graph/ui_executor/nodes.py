from __future__ import annotations

import os
from pathlib import Path
import subprocess
from typing import Any, Dict, List, Optional, cast
import xml.etree.ElementTree as ET

from src.graph.ui_executor.state import UIExecState
from src.core.llm_client import chat
import json

from src.memory import memory_store


# ---------- Node 1: prepare config ----------
def prepare_config(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))

    s.setdefault("project", "ui")
    s.setdefault("cwd", ".")
    # Only set default if not already present (allow CLI override)
    if "cmd" not in s:
        s["cmd"] = ["npm", "run", "test:ui"]
    s.setdefault("junit_path", "results/junit-ui.xml")
    s.setdefault("env", {})
    s.setdefault("attempt", 1)
    s.setdefault("max_attempts", 2)
    s.setdefault("approved", True)

    s.setdefault("results", [])
    s.setdefault("summary", {"total": 0, "passed": 0, "failed": 0, "skipped": 0})
    s.setdefault("errors", [])

    # Policy knobs
    s.setdefault("policy", "flaky_only")  # "always" | "flaky_only" | "none"
    s.setdefault("retry_scope", "full")   # "full" | "failed_only"

    # LLM outputs (added in this step)
    s.setdefault("llm_summary", "")
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


# ---------- Node 3: parse results (JUnit, now captures full failure text) ----------
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
        testcases = list(root.iter("testcase"))

        total = len(testcases)
        passed = failed = skipped = 0
        cases: List[Dict[str, Any]] = []

        for tc in testcases:
            name = tc.attrib.get("name", "")
            suite = tc.attrib.get("classname", "")
            time_s = float(tc.attrib.get("time", "0") or 0.0)

            status = "passed"
            message_attr = ""
            details_text = ""

            failure_el = tc.find("failure")
            skipped_el = tc.find("skipped")
            if failure_el is not None:
                status = "failed"
                # short attribute seen in Playwright JUnit (often file:line title)
                message_attr = (failure_el.attrib.get("message") or "").strip()
                # rich details (CDATA/text, sometimes nested); join text+tail just in case
                parts: List[str] = []
                if failure_el.text:
                    parts.append(str(failure_el.text))
                for child in list(failure_el):
                    if child.text:
                        parts.append(str(child.text))
                    if child.tail:
                        parts.append(str(child.tail))
                details_text = "\n".join(p.strip() for p in parts if p and p.strip())
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
                "message": message_attr,     # short message (attribute)
                "details": details_text,     # full text (for LLM + classifier)
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


# ---------- Node 3.5: LLM triage (summarize & label failures as transient vs real) ----------
def llm_triage(state: UIExecState) -> UIExecState:
    """
    Uses the UI Execution prompts to:
      - produce a short plain-English summary of failures
      - label each failed test as 'transient' or 'real' with a brief rationale
    Adds fields to each failed case: llm_label, llm_reason
    Saves a run-level 'llm_summary' string in state for Slack/Jira later.
    """
    s = cast(UIExecState, dict(state))
    attempt_now = int(s.get("attempt", 1) or 1)
    results: List[Dict[str, Any]] = cast(List[Dict[str, Any]], s.get("results", []))
    failed_now = [c for c in results if c.get("attempt") == attempt_now and c.get("status") == "failed"]

    # If nothing failed, skip quietly
    if not failed_now:
        return s

    # Resolve prompt files relative to repo layout: src/graph/ui_executor/nodes.py → parents[2] == src/
    src_root = Path(__file__).resolve().parents[2]
    sys_path = src_root / "core" / "prompts" / "ui_exec_system.txt"
    usr_path = src_root / "core" / "prompts" / "ui_exec_user.txt"

    try:
        system_prompt = sys_path.read_text(encoding="utf-8")
    except Exception:
        system_prompt = "You are a UI test failure triage assistant. Classify failures."

    # Build compact JSON payload for the LLM
    payload = {
        "attempt": attempt_now,
        "policy": s.get("policy", "flaky_only"),
        "failed_cases": [
            {
                "name": c.get("name", ""),
                "suite": c.get("suite", ""),
                "message": c.get("message", ""),
                "details": c.get("details", ""),
            }
            for c in failed_now
        ],
        "task": "Summarize failures (2-3 lines) and label each case as 'transient' or 'real' with a brief reason. Return JSON.",
        "format": {
            "summary": "string",
            "labels": [{"name": "string", "label": "transient|real", "reason": "string"}],
        },
    }

    try:
        user_template = ""
        try:
            user_template = usr_path.read_text(encoding="utf-8")
        except Exception:
            pass

        if user_template.strip():
            # Safe payload injection without str.format (which breaks on {} in the template)
            payload_json = json.dumps(payload, ensure_ascii=False)
            if "{payload}" in user_template:
                user_content = user_template.replace("{payload}", payload_json)
            else:
                user_content = user_template + "\n\nPAYLOAD\n" + payload_json
        else:
            # Simple fallback message
            user_content = (
                "Given the following failed UI test cases, summarize and classify them.\n"
                "Return strict JSON with keys: summary (string), labels (array of {name,label,reason}).\n\n"
                + json.dumps(payload, ensure_ascii=False)
            )

        # Call your Day-5 LLM client (no temperature kwarg)
        llm_raw = chat(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ]
        )

        # Parse strict JSON; fallback to empty on any error
        try:
            data = json.loads(llm_raw)
        except Exception:
            data = {"summary": "", "labels": []}

        summary_text: str = cast(str, data.get("summary", "") or "")
        labels: List[Dict[str, str]] = cast(List[Dict[str, str]], data.get("labels", []) or [])

        # Map labels back to cases in this attempt
        by_name = {lbl.get("name", ""): lbl for lbl in labels if isinstance(lbl, dict)}
        for c in failed_now:
            name = c.get("name", "")
            lbl = by_name.get(name)
            if lbl:
                c["llm_label"] = (lbl.get("label", "") or "").strip()
                c["llm_reason"] = (lbl.get("reason", "") or "").strip()

        # Save run-level summary for Slack/Jira later
        s["llm_summary"] = summary_text

    except Exception as e:
        errors: List[str] = cast(List[str], s.setdefault("errors", []))
        errors.append(f"[llm_triage] Exception: {e}")

    return s


# ---------- Helper: simple flaky classifier (rule-based fallback) ----------
def _is_retry_eligible_ui(case: Dict[str, Any]) -> bool:
    title = (case.get("name") or "").lower()
    msg = (case.get("message") or "").lower()
    details = (case.get("details") or "").lower()
    if "@flaky" in title:
        return True
    transient_signals = ("not visible", "timeout", "timed out", "network", "navigation", "to be visible")
    return any(sig in msg for sig in transient_signals) or any(sig in details for sig in transient_signals)


# ---------- Router: decide after approval (now prefers LLM labels) ----------
def decide_after_approval(state: UIExecState) -> str:
    """
    Return 'retry' or 'end' for the graph's conditional edge.
    Preference order:
      1) LLM labels (if present): retry if any failed case is labeled 'transient'
      2) Fallback to rule-based classifier
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

    attempt_now = int(state.get("attempt", 1) or 1)
    results: List[Dict[str, Any]] = cast(List[Dict[str, Any]], state.get("results", []))
    failed_cases = [c for c in results if c.get("attempt") == attempt_now and c.get("status") == "failed"]

    if state.get("policy") == "always":
        return "retry"

    # Prefer LLM classification if available
    has_llm = any("llm_label" in c for c in failed_cases)
    if has_llm:
        if any((c.get("llm_label") or "").lower() == "transient" for c in failed_cases):
            return "retry"
        return "end"

    # Fallback to rule-based classification
    if any(_is_retry_eligible_ui(c) for c in failed_cases):
        return "retry"
    return "end"


# ---------- Node 5: retry bookkeeping ----------
def retry_once(state: UIExecState) -> UIExecState:
    s = cast(UIExecState, dict(state))
    current_attempt = int(s.get("attempt", 1) or 1)
    s["attempt"] = current_attempt + 1
    return s

# ---------- Node 6: approval checkpoint ----------

def approval_checkpoint(state: UIExecState) -> UIExecState:
    """
    Human-in-the-loop gate.
    Polished: skip prompting when a retry is impossible or disallowed.
    """
    s = cast(UIExecState, dict(state))

    # If nothing failed, or policy forbids retry, or we're at the last attempt → skip prompt
    failed = int(s.get("summary", {}).get("failed", 0) or 0)
    if failed == 0:
        return s
    if s.get("policy") == "none":
        return s
    if int(s.get("attempt", 1) or 1) >= int(s.get("max_attempts", 1) or 1):
        return s

    # Otherwise, ask once. Default remains approve=True for non-interactive runs.
    try:
        ans = input("Approve retry if failures > 0? (approve/deny) [approve]: ").strip().lower()
        if ans in ("approve", "deny"):
            s["approved"] = (ans == "approve")
    except EOFError:
        # Non-interactive environment (CI): keep existing value
        pass

    return s


# ---------- Node 7: persist to memory ----------

def persist_to_memory(state: UIExecState) -> UIExecState:
    """
    Save the current run into SQLite memory and annotate failures
    with recurrence information (scoped to recent days).
    """
    s = cast(UIExecState, dict(state))

    summary = s.get("summary", {}) or {}
    results: List[Dict] = s.get("results", []) or []
    llm_summary = s.get("llm_summary", "") or ""

    # Save run + results into SQLite
    try:
        memory_store.save_run(
            project="UI",
            summary=summary,
            results=results,
            llm_summary=llm_summary,
        )
    except Exception as e:
        errs: List[str] = s.setdefault("errors", [])
        errs.append(f"[persist_to_memory] Save error: {e}")
        return s

    # Check recurrence for each failed test (last 7 days only)
    notes: List[str] = []
    for case in results:
        if case.get("status") == "failed":
            name = case.get("name", "")
            msg = case.get("message", "")
            try:
                count = memory_store.find_recurrences(name, msg, days=7)
                if count > 1:
                    notes.append(f"{name}: seen {count} times in last 7 days")
                else:
                    notes.append(f"{name}: NEW failure")
            except Exception as e:
                notes.append(f"{name}: memory lookup error {e}")

    s["memory_notes"] = notes
    return s
