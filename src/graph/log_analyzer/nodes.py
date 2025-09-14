"""
Day 5 - Log Analyzer (LangGraph)
--------------------------------
This file defines the node functions for the Log Analyzer pipeline.
Each node updates the shared LogAnalyzerState.
"""

import logging
import json
import re
from pathlib import Path
from typing import List

from .state import LogAnalyzerState
from src.core import chat, write_json
from src.integrations.jira import create_issue, JIRA_BASE
from src.integrations.slack import post_message
from src.integrations.dedupe import seen_today, mark_today

# Configure logger
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)

# Paths
ROOT = Path(__file__).resolve().parents[3]
LOG_DIR = ROOT / "data" / "logs"
OUT_DIR = ROOT / "outputs" / "log_analyzer"
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_JSON = OUT_DIR / "log_findings.json"
OUT_MD = OUT_DIR / "log_summary.md"


def read_logs(state: LogAnalyzerState) -> LogAnalyzerState:
    """Read log files into state.logs"""
    paths = state.get("log_paths") or [str(LOG_DIR / "app_startup_short.log")]
    lines: List[str] = []
    for p in paths:
        path = Path(p)
        if not path.exists():
            logger.warning(f"⚠️ Log file not found: {path}")
            continue
        lines.extend(path.read_text(encoding="utf-8").splitlines())
    logger.info(f"📄 Read {len(lines)} log lines from {len(paths)} file(s)")
    state["logs"] = lines
    return state


def group_events(state: LogAnalyzerState) -> LogAnalyzerState:
    """Group log lines into signatures"""
    groups: dict = {}
    for line in state.get("logs", []):
        m = re.match(r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\s+\[(?P<level>INFO|WARN|ERROR)\]\s+(?P<msg>.*)", line)
        if not m:
            continue
        _, level, msg = m.group("ts"), m.group("level"), m.group("msg")
        sig = msg.lower().split()[:4]
        sig = " ".join(sig) if sig else msg[:32]
        g = groups.get(sig)
        if not g:
            g = {"signature": sig, "count": 0, "levels": {"INFO": 0, "WARN": 0, "ERROR": 0}, "examples": []}
            groups[sig] = g
        g["count"] += 1
        g["levels"][level] = g["levels"].get(level, 0) + 1
        if len(g["examples"]) < 3:
            g["examples"].append(line)
    sorted_groups = sorted(groups.values(), key=lambda x: x["count"], reverse=True)
    logger.info(f"🔎 Grouped into {len(sorted_groups)} signatures")
    state["groups"] = sorted_groups
    return state


def analyze_with_llm(state: LogAnalyzerState) -> LogAnalyzerState:
    """Send grouped logs to LLM for analysis using prompt files"""
    groups = state.get("groups", [])
    total = sum(g["count"] for g in groups)

    # Load prompts from src/core/prompts
    PROMPTS_DIR = ROOT / "src" / "core" / "prompts"
    system_prompt = (PROMPTS_DIR / "log_system.txt").read_text(encoding="utf-8")
    user_template = (PROMPTS_DIR / "log_user.txt").read_text(encoding="utf-8")

    payload_json = json.dumps({"groups": groups[:3], "total_events": total}, indent=2)
    user_prompt = user_template.format(payload_json=payload_json)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]

    raw = chat(messages)

    try:
        findings = json.loads(raw)
    except Exception:
        logger.warning("⚠️ Could not parse LLM JSON. Saving raw output.")
        (OUT_DIR / "last_raw.json").write_text(raw, encoding="utf-8")
        findings = {"groups": [], "summary": {"total_events": total}}

    write_json(findings, OUT_JSON)
    OUT_MD.write_text("# Summary\n" + json.dumps(findings.get("summary", {}), indent=2), encoding="utf-8")

    logger.info(f"📝 Analysis written to {OUT_JSON} and {OUT_MD}")
    state["findings"] = findings
    return state

def create_jira_tickets(state: LogAnalyzerState) -> LogAnalyzerState:
    """Create Jira tickets for ERROR groups"""
    findings = state.get("findings", {})
    groups = findings.get("groups", [])
    total = findings.get("summary", {}).get("total_events", 0)

    created: List[str] = []
    for g in groups:
        errors = g.get("levels", {}).get("ERROR", 0)
        if errors <= 0:
            continue
        sig = g.get("signature", "unknown")
        if seen_today(sig):
            logger.info(f"↪️ Signature '{sig}' already reported today, skipping.")
            continue
        summary = f"[Auto] {sig} ({errors} errors)"
        description = f"h2. Auto Log Analysis\n\nSignature: {sig}\nErrors: {errors} of {total}\nExamples:\n" + "\n".join(g.get("examples", []))
        try:
            jres = create_issue(summary=summary, description=description, issuetype="Bug")
            key = jres.get("key") or "UNKNOWN"
            created.append(str(key))
            mark_today(sig, str(key))
            logger.info(f"🐞 Created Jira issue {key} for '{sig}'")
        except Exception as e:
            logger.error(f"❌ Jira create failed for '{sig}': {e}")
    state["jira_issues"] = created
    return state


def send_slack_summary(state: LogAnalyzerState) -> LogAnalyzerState:
    """Send one Slack summary message"""
    findings = state.get("findings", {})
    groups = findings.get("groups", [])
    summary = findings.get("summary", {})

    if not groups:
        logger.info("No groups found, skipping Slack notification.")
        return state

    lines = [":rotating_light: *Log Analyzer Summary*",
             f"*Total events:* {summary.get('total_events', 0)}  •  *Error rate:* {summary.get('error_rate', 0):.2f}"]

    for g in groups[:3]:
        sig = g.get("signature", "unknown")
        rec = g.get("recommendation", "No recommendation")
        jira_link = f"{JIRA_BASE}/browse/{state.get('jira_issues', [])[-1]}" if state.get("jira_issues") else "No Jira"
        lines.append(f"• {sig} — errors: {g.get('levels', {}).get('ERROR', 0)}  •  Jira: {jira_link}")
        lines.append(f"   ↳ _Recommendation:_ {rec}")

    text = "\n".join(lines)
    try:
        post_message(text=text)
        logger.info("📢 Slack summary posted")
        state["slack_notifications"] = ["SENT"]
    except Exception as e:
        logger.error(f"❌ Slack post failed: {e}")
    return state
