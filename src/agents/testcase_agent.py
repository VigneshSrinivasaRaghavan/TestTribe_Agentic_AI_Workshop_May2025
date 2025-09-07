"""
Agent entrypoint: testcase_agent

Run via module mode for reliable imports:
  python -m src.agents.testcase_agent --input data/requirements/login.txt

This file is intentionally small and imports core helpers from `src.core`.
"""

from __future__ import annotations

from pathlib import Path
import json
from typing import List, Dict, Optional
import argparse

from src.core import chat, pick_requirement, parse_json_safely, to_rows, write_csv
from langchain.prompts import PromptTemplate
from src.integrations.testrail import map_case_to_testrail_payload, create_case, list_cases, add_result, get_stats
import re

# The functions imported from `src.core` are small, dependency-free helpers
# used to keep this agent focused on orchestration (easy for students to read
# and extend): `chat` (LLM call), `pick_requirement` (choose input file),
# `parse_json_safely` (robust JSON parsing), `to_rows` and `write_csv`.

# Paths (easy-to-change constants for students)
ROOT = Path(__file__).resolve().parents[2]
REQ_DIR = ROOT / "data" / "requirements"  # directory with .txt requirement files
OUT_DIR = ROOT / "outputs" / "testcase_generated"  # where outputs are written
OUT_DIR.mkdir(parents=True, exist_ok=True)
OUT_CSV = OUT_DIR / "test_cases.csv"  # CSV output path
LAST_RAW_JSON = OUT_DIR / "last_raw.json"  # file where raw LLM text is saved

# Classroom note: these constants are intentionally simple and visible so
# students can easily change input/output locations when experimenting.

PROMPTS_DIR = ROOT / "src" / "core" / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "testcase_system.txt").read_text(encoding="utf-8")
USER_TEMPLATE_STR = (PROMPTS_DIR / "testcase_user.txt").read_text(encoding="utf-8")
USER_TEMPLATE = PromptTemplate.from_template(USER_TEMPLATE_STR)

# `USER_TEMPLATE` wraps the requirement text so the model sees a clear input
# block; we keep it simple for students to inspect and modify.

Message = Dict[str, str]
"""Type alias for message dicts sent to the `chat` helper.

Each message is a dict with `role` and `content` strings, matching the
minimal interface used by provider-agnostic chat helpers in the exercises.
"""

def _norm(title: str | None) -> str:
    """
    Normalize a title for stable dedupe.
    - case-insensitive
    - trims
    - removes non-alphanumeric (keeps [a-z0-9] only)
    - collapses whitespace
    """
    s = (title or "").lower().strip()
    s = re.sub(r"[^a-z0-9]+", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s

def main(argv: Optional[list] = None) -> None:
    """Run the testcase agent end-to-end.

    Flow:
    1. Pick a requirement file (CLI arg or first file in `data/requirements`).
    2. Read the requirement text.
    3. Build a system + user message pair and call `chat(messages)`.
    4. Save raw model output to `outputs/last_raw.json` and parse it as JSON.
    5. Convert parsed cases to CSV rows and write `outputs/test_cases.csv`.

    Error handling and teaching hooks:
    - We save the raw model text to `LAST_RAW_JSON` so students can inspect
      model failures or formatting issues.
    - If parsing fails, we perform a single "nudge" retry that reminds the
      model to return pure JSON. If it still fails we raise a helpful error
      pointing to the raw file.
    - The agent is deliberately thin: it focuses on orchestration. Students
      can extend it later to add retries, rate-limiting, human-in-the-loop
      review pages, or direct integrations with Jira/TestRail.
    """

    # Parse CLI: accept `--input PATH` for clarity in teaching demos
    parser = argparse.ArgumentParser()
    parser.add_argument("--input", help="Path to a requirement .txt file")
    args = parser.parse_args(argv)

    # Configure logging for the process (simple default; agents may override)
    import logging

    logging.basicConfig(
        level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s"
    )
    logger = logging.getLogger(__name__)

    req_path = pick_requirement(args.input if args.input else None, REQ_DIR)
    requirement_text = req_path.read_text(encoding="utf-8").strip()

    messages: List[Message] = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {
            "role": "user",
            "content": USER_TEMPLATE.format(requirement_text=requirement_text),
        },
    ]

    # Call the LLM via the provider-agnostic `chat` function. The returned
    # `raw` is the assistant's text; for Day-1 we expect the model to return
    # a pure JSON array (see SYSTEM_PROMPT) so downstream parsing is simple.
    logger.debug("Calling chat: provider payload msgs=%d (sys=1,user=1)", len(messages))
    raw = chat(messages)

    try:
        cases = parse_json_safely(raw, LAST_RAW_JSON)
    except Exception as e:
        # gentle retry nudge — a pragmatic teaching technique: show how a
        # small reminder can correct common model format mistakes.
        logger.exception(
            "Initial parse_json_safely failed; will nudge and retry. Raw saved at %s",
            LAST_RAW_JSON,
        )
        nudge = (
            raw + "\n\nREMINDER: Return a pure JSON array only, matching the schema."
        )
        try:
            cases = parse_json_safely(nudge, LAST_RAW_JSON)
        except Exception:
            # Surface a clear runtime error with a pointer to the saved raw
            # output so students can debug model responses during the session.
            logger.error(
                "Could not parse model output after nudge; see %s", LAST_RAW_JSON
            )
            raise RuntimeError(
                f"Could not parse model output as JSON. See {LAST_RAW_JSON}.\nError: {e}"
            )

    rows = to_rows(cases)
    write_csv(rows, OUT_CSV)

    logger.info("✅ Wrote %d test cases to: %s", len(rows), OUT_CSV.relative_to(ROOT))
    logger.info("ℹ️  Raw model output saved at: %s", LAST_RAW_JSON.relative_to(ROOT))

    # --- Day-4: Act step → push to TestRail mock ---
    logger.info("ℹ️  Starting TestRail push step")

    # Map once → collect payloads (so we dedupe on the exact titles we will POST)
    payloads: list[dict] = []
    for idx, c in enumerate(cases, start=1):
        try:
            p = map_case_to_testrail_payload(c)
            payloads.append(p)
        except Exception as e:
            logger.warning("Skipping case %s (mapping error): %s", c.get("id") or idx, e)

    # Build once: incoming titles from *mapped* payloads
    incoming_titles = { _norm(p.get("title")) for p in payloads }

    # Build once: existing titles from TestRail (project-wide)
    try:
        existing = list_cases()  # returns list[dict]
        existing_titles = { _norm(case.get("title")) for case in existing }
    except Exception as e:
        logger.warning("Could not fetch existing titles; proceeding without dedupe: %s", e)
        existing_titles = set()

    logger.info("📚 Loaded %d existing titles from TestRail (project-wide)", len(existing_titles))

    # One-shot duplicate report (informational)
    dupes = incoming_titles & existing_titles
    if dupes:
        logger.info(
            "🚧 Detected %d duplicate title(s) in this batch; they will be skipped: %s",
            len(dupes), sorted(list(dupes))[:5]  # show first few only
        )
    else:
        logger.info("✅ No duplicates detected for this batch")

    created_ids: list[int] = []
    for p in payloads:
        title_norm = _norm(p.get("title"))

        # Skip if already exists (pre-existing or created earlier in this run)
        if title_norm in existing_titles:
            logger.info("↪️  Skipping existing case: %s", p.get("title"))
            continue

        try:
            res = create_case(p)
            cid = res.get("id")
            if cid is not None:
                created_ids.append(int(cid))         # ✅ safe append
                existing_titles.add(title_norm)      # prevent same-batch duplicates
                try:
                    _ = add_result(int(cid),status_id=1, comment="Auto-passed by TestCase Agent")
                except Exception as e:
                    logger.warning("Could not add result for case id %d: %s", int(cid), e)
            else:
                logger.warning("Create case response missing 'id': %s", res)
        except Exception as e:
            logger.error("Create case failed for '%s': %s", p.get("title"), e)

    logger.info("📌 Created %d TestRail cases: %s", len(created_ids), created_ids)

    # Quick verification
    try:
        all_cases = list_cases()
        logger.info("🧾 TestRail now has %d cases in project", len(all_cases))
    except Exception as e:
        logger.warning("Could not list TestRail cases: %s", e)

    logger.info("✅ Test cases pushed to TestRail successfully with id %s", created_ids)

    try:
        stats = get_stats()
        total = stats.get("total_cases")
        logger.info("📊 Project stats → total_cases: %s", total)
        for s in stats.get("sections", []):
            logger.info("   • %s: %s case(s)", s.get("section_name"), s.get("case_count"))
    except Exception as e:
        logger.warning("Could not fetch project stats: %s", e)

if __name__ == "__main__":
    main()
