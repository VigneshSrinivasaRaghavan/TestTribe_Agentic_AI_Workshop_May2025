from __future__ import annotations

from pathlib import Path
from typing import Iterable, Optional, Tuple
import re
import json
import argparse

from src.core import chat
from src.core.utils import write_json
from langchain.prompts import PromptTemplate
from src.integrations.jira import create_issue, JIRA_BASE
from src.integrations.slack import post_message
try:
    from src.integrations.dedupe import seen_today, mark_today
except Exception:
    def seen_today(signature: str) -> bool: return False
    def mark_today(signature: str, issue_key: str) -> None: pass

# ---------- Parsing & Grouping ----------

def load_logs(paths: Iterable[Path]) -> Iterable[str]:
    """Yield lines from given log file paths."""
    for p in paths:
        with p.open("r", encoding="utf-8") as fh:
            for line in fh:
                yield line.rstrip("\n")

def parse_log_line(line: str) -> Optional[Tuple[str, str, str]]:
    """Parse 'YYYY-MM-DD HH:MM:SS [LEVEL] message' into (ts, level, msg)."""
    pattern = (
        r"(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})"
        r"\s+\[(?P<level>INFO|WARN|ERROR)\]\s+"
        r"(?P<msg>.*)"
    )
    m = re.match(pattern, line)
    if not m:
        return None
    return m.group("ts"), m.group("level"), m.group("msg").strip()

def compute_signature(msg: str, max_tokens: int = 4) -> str:
    """Very small normalization to form a short signature."""
    s = msg.lower()
    s = re.sub(r"/[-\w./]+", " ", s)    # strip paths
    s = re.sub(r"\d+", " ", s)          # strip numbers
    s = re.sub(r"[^a-z\s]", " ", s)     # strip punctuation
    s = re.sub(r"\s+", " ", s).strip()
    tokens = s.split()
    return " ".join(tokens[:max_tokens]) if tokens else msg[:32]

def group_events(lines: Iterable[str]) -> list[dict]:
    """Aggregate parsed log lines into groups keyed by signature."""
    groups: dict[str, dict] = {}
    for line in lines:
        parsed = parse_log_line(line)
        if not parsed:
            continue
        _, level, msg = parsed
        sig = compute_signature(msg)
        g = groups.get(sig)
        if not g:
            g = {
                "signature": sig,
                "count": 0,
                "levels": {"INFO": 0, "WARN": 0, "ERROR": 0},
                "examples": [],
            }
            groups[sig] = g
        g["count"] += 1
        g["levels"][level] = g["levels"].get(level, 0) + 1
        if len(g["examples"]) < 3:
            g["examples"].append(line)

    return sorted(groups.values(), key=lambda x: x["count"], reverse=True)

# ---------- LLM I/O ----------

def build_llm_messages(groups: list, total_events: int, top_n: int = 3) -> list:
    """Construct system+user messages to send to the LLM (from prompt files)."""

    # include top_n groups and add extracted exception tokens per group to help LLM
    payload = groups[:top_n]
    for g in payload:
        exs = []
        for ex_line in g.get("examples", []):
            found = re.findall(r"([A-Za-z_]+(?:Error|Exception))", ex_line)
            for f in found:
                if f not in exs:
                    exs.append(f)
        if exs:
            g["exceptions"] = exs

    # Read prompts from files
    ROOT = Path(__file__).resolve().parents[2]
    PROMPTS_DIR = ROOT / "src" / "core" / "prompts"
    system_text = (PROMPTS_DIR / "log_system.txt").read_text(encoding="utf-8")
    user_template_str = (PROMPTS_DIR / "log_user.txt").read_text(encoding="utf-8")
    user_template = PromptTemplate.from_template(user_template_str)

    user_payload = json.dumps({"groups": payload, "total_events": total_events}, indent=2)

    system = system_text
    user = user_template.format(payload_json=user_payload)
    return [{"role": "system", "content": system}, {"role": "user", "content": user}]


def call_llm(messages: list, timeout: int) -> str:
    """Thin wrapper over core chat client (returns raw string)."""
    return chat(messages, timeout=timeout)

def parse_llm_output(raw: str) -> dict:
    """Parse LLM JSON or save raw to outputs/log_analyzer/last_raw.json and raise."""
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        out_dir = Path("outputs") / "log_analyzer"
        out_dir.mkdir(parents=True, exist_ok=True)
        (out_dir / "last_raw.json").write_text(raw, encoding="utf-8")
        raise RuntimeError(
            f"LLM output was not valid JSON. Raw saved to {out_dir / 'last_raw.json'}"
        )
    
def main(argv: Optional[list] = None) -> None:
    """Command-line entry point: read logs, call LLM, and write findings.

    This function wires together the small teaching helpers:
    - load log lines from CLI `--inputs`
    - aggregate groups with `group_events`
    - build messages and call the LLM
    - parse and post-process LLM findings
    - write JSON and a short markdown summary to `outputs/log_analyzer`.

    Args:
        argv: Optional list of CLI arguments (used for testing).
    """
    parser = argparse.ArgumentParser()
    parser.add_argument("--inputs", nargs="+", required=True)
    parser.add_argument("--timeout", type=int, default=60, help="LLM timeout seconds")
    parser.add_argument(
        "--llm-top", type=int, default=3, help="How many top groups to send to LLM"
    )
    args = parser.parse_args(argv)

    # Configure logging for the process (simple default; agents may override)
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger(__name__)

    paths = [Path(p) for p in args.inputs]
    lines = list(load_logs(paths))
    logger.info("Read %d lines from inputs=%s", len(lines), paths)
    logger.debug("First 3 lines: %s", lines[:3])
    groups = group_events(lines)
    logger.info("Grouped into %d signatures", len(groups))
    logger.debug("Top signatures: %s", [g["signature"] for g in groups[:5]])
    total = sum(g["count"] for g in groups)

    messages = build_llm_messages(groups, total, top_n=args.llm_top)
    logger.info("Calling LLM with top_n=%d (total_events=%d)", args.llm_top, total)
    logger.debug(
        "LLM payload size=%d chars",
        len(json.dumps({"groups": groups[: args.llm_top], "total_events": total})),
    )
    raw = call_llm(messages, timeout=args.timeout)
    findings = parse_llm_output(raw)

    # Post-process: ensure `summary.total_events` and `summary.error_rate` are correct
    if "summary" not in findings or not isinstance(findings.get("summary"), dict):
        findings["summary"] = {}
    findings["summary"].setdefault("total_events", total)
    # compute local error rate from our grouped counts
    local_errors = sum(g.get("levels", {}).get("ERROR", 0) for g in groups)
    computed_error_rate = round(local_errors / max(1, total), 3)
    # validate LLM-provided error_rate; override if missing or out-of-range
    er = findings["summary"].get("error_rate")
    if not isinstance(er, (int, float)) or not (0 <= er <= 1):
        findings["summary"]["error_rate"] = computed_error_rate

    # Heuristic: if LLM left probable_root_cause empty, try to extract exception tokens
    for g in findings.get("groups", []):
        pr = g.get("probable_root_cause", "")
        rec = g.get("recommendation", "")
        if not pr:
            exs = []
            for ex_line in g.get("examples", []):
                found = re.findall(r"([A-Za-z_]+(?:Error|Exception))", ex_line)
                for f in found:
                    if f not in exs:
                        exs.append(f)
            if exs:
                g["probable_root_cause"] = ", ".join(exs)
                if not rec:
                    g["recommendation"] = f"Investigate {exs[0]} and related services"

    # write outputs
    out_dir = Path("outputs") / "log_analyzer"
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "log_findings.json"
    out_md = out_dir / "log_summary.md"
    write_json(findings, out_json)
    out_md.write_text(
        "# Summary\n" + json.dumps(findings.get("summary", {}), indent=2),
        encoding="utf-8",
    )
    logger.info("Wrote %s and %s", out_json, out_md)

        # --- Act: create ONE Jira per ERROR group, then ONE Slack summary ---
    groups = findings.get("groups") or []
    if not groups:
        logger.info("No groups to report; skipping Jira/Slack.")
        return

    total_events = int(findings.get("summary", {}).get("total_events", 0) or 0)
    error_rate = findings.get("summary", {}).get("error_rate", 0.0)

    created: list[tuple[str, str, int]] = []  # (signature, issue_key, errors)

    for g in groups:
        levels = g.get("levels", {}) or {}
        errors = int(levels.get("ERROR", 0) or 0)
        if errors <= 0:
            continue

        sig = g.get("signature", "unknown")

        # Optional daily dedupe (skip if same signature already filed today)
        if seen_today(sig):
            logger.info("Signature %r already reported today; skipping Jira create.", sig)
            created.append((sig, "ALREADY_REPORTED", errors))
            continue

        # Prefer exception name for title; else use signature
        exceptions = g.get("exceptions") or []
        title_part = exceptions[0] if exceptions else sig
        summary = f"[Auto] {title_part} ({errors} errors)"

        # Richer description with RCA/recommendation and examples
        rca = g.get("probable_root_cause") or "Not determined"
        rec = g.get("recommendation") or "No recommendation"
        example_block = "\n".join((g.get("examples") or [])[:3])

        description = (
            f"Automated Log Analysis Report\n\n"
            f"*Signature:* {sig}\n"
            f"*Errors:* {errors} of {total_events} events (rate={error_rate:.1%})\n\n"
            f"*Probable Root Cause:* {rca}\n"
            f"*Recommendation:* {rec}\n\n"
            f"*Examples:*\n"
            f"{{code}}\n{example_block}\n{{code}}"
        )

        try:
            jres = create_issue(summary=summary, description=description, issuetype="Bug")
            issue_key = jres.get("key") or jres.get("id") or "UNKNOWN"
            created.append((sig, str(issue_key), errors))
            mark_today(sig, str(issue_key))
            logger.info("Created Jira issue: %s for signature %r", issue_key, sig)
        except Exception as e:
            logger.error("Jira create failed for %r: %s", sig, e)

    # If nothing had errors, stop here
    if not created:
        logger.info("No ERROR groups detected")
        return
    

    # One Slack summary (exception + recommendation + clickable Jira links)
    try:
        rate_pct = f"{float(error_rate) * 100:.1f}%"
        lines = [":rotating_light: *Log Alert Summary*",
                 f"*Total events:* {total_events}  •  *Error rate:* {rate_pct}"]

        for sig, key, errs in created:
            gmatch = next((gx for gx in groups if gx.get("signature") == sig), None)
            exceptions = (gmatch.get("exceptions") if gmatch else []) or []
            title = exceptions[0] if exceptions else sig
            rec = (gmatch.get("recommendation") if gmatch else "") or ""
            exs = (gmatch.get("examples") if gmatch else []) or []
            example_1 = exs[0] if exs else ""

            issue_url = f"{JIRA_BASE}/ui/issue/{key}" if key not in ("UNKNOWN", "ALREADY_REPORTED") else ""
            jira_part = f"*Jira:* <{issue_url}|{key}>" if issue_url else f"*Jira:* {key}"

            lines.append(f"• *{title}* — errors: {errs}  •  {jira_part}")
            if rec:
                lines.append(f"   ↳ _Recommendation:_ {rec}")
            if example_1:
                lines.append(f"```{example_1}```")

        txt = "\n".join(lines)
        _ = post_message(text=txt)
        logger.info("Posted enriched Slack summary for %d issues.", len(created))
    except Exception as e:
        logger.error("Slack post failed: %s", e)


# --- Run as script ---
if __name__ == "__main__":
    main()