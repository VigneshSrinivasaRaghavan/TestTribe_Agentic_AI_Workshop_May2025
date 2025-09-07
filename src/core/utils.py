"""
Shared utilities for Day‑1 agents.

This module contains small, dependency-free helpers used by agents:

- `pick_requirement(path_arg, req_dir)` — select a requirement file from CLI
  argument or the `req_dir` directory.
- `parse_json_safely(text, raw_path)` — robustly parse LLM text into JSON
  (tries a minimal cleanup if the model wraps JSON in fences) and saves the
  raw output to `raw_path` for debugging.
- `to_rows(cases)` — convert a list of JSON case dicts into CSV rows.
- `write_csv(rows, path)` — write rows to a CSV file without external libs.

These are intentionally small helpers designed for teaching. They avoid
heavyweight dependencies and provide clear points where students can
experiment (better parsing, schema validation, CSV libraries, etc.).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Dict
import requests


def pick_requirement(path_arg: str | None, req_dir: Path) -> Path:
    """Return a Path to a requirement `.txt` file.

    Behavior:
    - If `path_arg` is provided, validate it exists and return it.
    - Otherwise, pick the first `.txt` file found in `req_dir` (sorted).

    Args:
        path_arg: Optional CLI path string pointing to a requirement file.
        req_dir: Directory to search for `.txt` files.

    Returns:
        Path: Resolved path to the requirement file.

    Raises:
        FileNotFoundError: If `path_arg` exists but is missing, or if no
            `.txt` files exist under `req_dir`.
    """
    if path_arg:
        p = Path(path_arg)
        if not p.exists():
            raise FileNotFoundError(f"Requirement file not found: {p}")
        return p
    txts = sorted(Path(req_dir).glob("*.txt"))
    if not txts:
        raise FileNotFoundError(f"No .txt files found in {req_dir}")
    return txts[0]


def parse_json_safely(text: str, raw_path: Path) -> List[Dict]:
    """Parse raw LLM text into a list of JSON objects, saving raw output.

    This helper:
    1. Writes the raw LLM output to `raw_path` for debugging.
    2. Attempts `json.loads` directly.
    3. If that fails, does a minimal cleanup (strip, remove Markdown code
       fences and optional language header) and retries parsing.
    4. Ensures the top-level JSON is a list (expected: list of case dicts).

    Args:
        text: Raw string returned by the LLM.
        raw_path: Path to save the raw text for later inspection.

    Returns:
        List[Dict]: Parsed JSON list of case dictionaries.

    Raises:
        ValueError: If the parsed top-level JSON is not a list.
        json.JSONDecodeError: If JSON parsing fails despite cleanup.
    """
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    raw_path.write_text(text, encoding="utf-8")

    try:
        data = json.loads(text)
        if not isinstance(data, list):
            raise ValueError("Top-level JSON is not a list.")
        return data
    except Exception:
        cleaned = text.strip()
        # If the model wrapped JSON in triple-backtick fences, remove them.
        if cleaned.startswith("```"):
            # Strip surrounding backticks; if a language header is present
            # the first line contains it, so drop that line.
            cleaned = cleaned.strip("`")
            if "\n" in cleaned:
                cleaned = cleaned.split("\n", 1)[1]
        data = json.loads(cleaned)
        if not isinstance(data, list):
            raise ValueError("Top-level JSON is not a list after cleanup.")
        return data


def to_rows(cases: List[Dict]) -> List[List[str]]:
    """Convert parsed case dictionaries into CSV-safe rows.

    Expected keys in each case dict (all optional):
      - id: unique identifier
      - title: short title for the test case
      - steps: list of step strings or a single string
      - expected: expected result text
      - priority: priority label (e.g., High/Medium/Low)

    The function normalizes missing values, flattens steps into a single
    string separated by " | ", and returns rows in the order:
    [TestID, Title, Steps, Expected, Priority].

    Args:
        cases: List of dictionaries representing test cases.

    Returns:
        List[List[str]]: Rows ready for CSV writing.
    """
    rows: List[List[str]] = []
    for i, c in enumerate(cases, start=1):
        tid = str(c.get("id") or f"TC-{i:03d}")
        title = str(c.get("title") or "").strip()
        steps_list = c.get("steps") or []
        if not isinstance(steps_list, list):
            steps_list = [str(steps_list)]
        steps = " | ".join(str(s).strip() for s in steps_list if str(s).strip())
        expected = str(c.get("expected") or "").strip()
        priority = str(c.get("priority") or "Medium").strip()
        rows.append([tid, title, steps, expected, priority])
    return rows


def write_csv(rows: List[List[str]], path: Path) -> None:
    """Write rows to a CSV file at `path`, creating parent directories.

    This simple writer:
    - Writes a header row `["TestID","Title","Steps","Expected","Priority"]`.
    - Escapes commas inside fields by replacing them with semicolons to avoid
      adding CSV quoting logic (keeps the helper dependency-free for teaching).

    Args:
        rows: List of rows (each row is list of strings).
        path: Destination file path for the CSV.

    Returns:
        None
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    header = ["TestID", "Title", "Steps", "Expected", "Priority"]
    lines = [",".join(header)]
    for r in rows:
        escaped = [field.replace(",", ";") for field in r]
        lines.append(",".join(escaped))
    path.write_text("\n".join(lines), encoding="utf-8")


def write_json(obj: object, path: Path) -> None:
    """Write an object as pretty JSON to `path`, creating parent dirs.

    Useful shared helper for agents that need to emit JSON outputs.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, ensure_ascii=False), encoding="utf-8")

# --- HTTP helpers (generic JSON) ---

def http_post_json(url: str, payload: dict, headers: dict | None = None, timeout: int = 60) -> dict:
    r = requests.post(url, json=payload, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()

def http_get_json(url: str, headers: dict | None = None, timeout: int = 60) -> dict:
    r = requests.get(url, headers=headers or {}, timeout=timeout)
    r.raise_for_status()
    return r.json()