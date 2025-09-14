from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Dict, cast

from src.graph.ui_executor.graph import build_ui_app
from src.graph.ui_executor.state import UIExecState


def _parse_env_kv(items: list[str]) -> Dict[str, str]:
    env: Dict[str, str] = {}
    for it in items:
        if "=" in it:
            k, v = it.split("=", 1)
            env[k.strip()] = v.strip()
    return env


def main():
    ap = argparse.ArgumentParser(description="Run the UI Executor agent (Playwright).")
    ap.add_argument("--cwd", default="./playwright-demo-for-agentic-ai", help="Path to the Playwright project.")
    ap.add_argument("--junit", default="results/junit-ui.xml", help="Relative path to JUnit XML inside --cwd.")
    ap.add_argument("--max-retries", type=int, default=2, help="Max attempts including the first run.")
    ap.add_argument(
        "--policy",
        choices=("always", "flaky_only", "none"),
        default="flaky_only",
        help="Retry policy: always | flaky_only | none",
    )
    ap.add_argument(
        "--retry-scope",
        choices=("full", "failed_only"),
        default="full",
        help="What to rerun on retry (teaching toggle; we keep 'full' for now).",
    )
    ap.add_argument(
        "--env",
        action="append",
        default=[],
        help='Extra env vars (repeatable), e.g., --env FLAKE_P=1 --env BASE_URL=https://...',
    )
    args = ap.parse_args()

    env_overrides = _parse_env_kv(args.env)

    print("🔹 ✅ UI Executor graph built successfully")
    app = build_ui_app()

    # Initial state (defaults will be completed by prepare_config)
    state = {
        "project": "ui",
        "cwd": args.cwd,
        "junit_path": args.junit,
        "max_attempts": args.max_retries,
        "policy": args.policy,
        "retry_scope": args.retry_scope,
        "env": env_overrides,
    }

    print(f"▶ Running UI tests via agent (cwd={args.cwd})")
    final = app.invoke(cast(UIExecState, state))

    summary = final.get("summary", {}) or {}
    total = int(summary.get("total", 0) or 0)
    passed = int(summary.get("passed", 0) or 0)
    failed = int(summary.get("failed", 0) or 0)
    skipped = int(summary.get("skipped", 0) or 0)

    print(f"📊 Final Summary: total={total}  ✅={passed}  ❌={failed}  ⚠️={skipped}")

    # Save a tiny unified report for later (e.g., Slack/email in Day-7/8)
    report = {
        "project": "UI",
        "cwd": args.cwd,
        "junit_path": args.junit,
        "policy": args.policy,
        "max_attempts": args.max_retries,
        "summary": summary,
        "results": final.get("results", []),
        "errors": final.get("errors", []),
    }
    out_path = Path("ui_execution_report.json")
    out_path.write_text(json.dumps(report, indent=2))
    print(f"💾 Saved {out_path}")

    # Exit code mirrors the Playwright outcome after retries (0 = success)
    # If any failures remain in the final summary, return non-zero for CI gating.
    exit_code = 0 if failed == 0 else 1
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
