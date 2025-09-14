import logging
import time  # add this import at the top with others
from pathlib import Path
from typing import List

from .state import TestCaseState
from src.core import pick_requirement, chat, parse_json_safely, to_rows, write_csv
from src.integrations.testrail import (
    map_case_to_testrail_payload,
    create_case,
    list_cases,
    add_result,
    get_stats,
)


# Configure logger (teaching-friendly output)
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)

# ---------------- Path Setup ----------------
# nodes.py is at: <project-root>/src/graph/test_case_generator/nodes.py
# Step up 3 levels → <project-root>
ROOT = Path(__file__).resolve().parents[3]

# Data folders (relative to project root)
REQ_DIR = ROOT / "data" / "requirements"
OUT_DIR = ROOT / "outputs" / "testcase_generated"
OUT_DIR.mkdir(parents=True, exist_ok=True)

# Output files
OUT_CSV = OUT_DIR / "test_cases.csv"
LAST_RAW_JSON = OUT_DIR / "last_raw.json"

# Prompt files (inside src/core/prompts)
PROMPTS_DIR = ROOT / "src" / "core" / "prompts"
SYSTEM_PROMPT = (PROMPTS_DIR / "testcase_system.txt").read_text(encoding="utf-8")
USER_PROMPT_TEMPLATE = (PROMPTS_DIR / "testcase_user.txt").read_text(encoding="utf-8")

# Node 1
def read_requirements(state: TestCaseState) -> TestCaseState:
    """Read requirements text into state."""
    # Use CLI-provided path if available
    if "requirement_path" in state:
        req_path = Path(state["requirement_path"])
    else:
        req_path = pick_requirement(None, REQ_DIR)

    logger.info(f"📄 Reading requirements from {req_path.name}")
    state["requirements"] = req_path.read_text(encoding="utf-8").strip()
    return state

# Node 2

def generate_tests_with_llm(state: TestCaseState) -> TestCaseState:
    """Generate test cases using LLM with retry logic."""
    logger.info("🤖 Generating test cases with LLM...")

    user_prompt = USER_PROMPT_TEMPLATE.format(
        requirement_text=state.get("requirements", "")
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    cases = []
    max_retries = 3
    for attempt in range(1, max_retries + 1):
        try:
            logger.info(f"🔄 Attempt {attempt}/{max_retries} to call LLM...")
            raw = chat(messages)
            cases = parse_json_safely(raw, LAST_RAW_JSON)
            if cases:  # success
                break
        except Exception as e:
            logger.warning(f"⚠️ LLM call failed on attempt {attempt}: {e}")
        time.sleep(2 * attempt)  # exponential backoff

    if not cases:
        logger.error("❌ All retries failed. No valid test cases generated.")
        cases = [
            {"title": "Canned dummy test of Login with valid credentials", "steps": ["Enter username", "Enter password", "Click login"], "expected": "User is logged in"},
            {"title": "Canned dummy test of Login with invalid password", "steps": ["Enter username", "Enter wrong password", "Click login"], "expected": "Error message displayed"},
        ]

    rows = to_rows(cases)
    write_csv(rows, OUT_CSV)
    logger.info(f"✅ Wrote {len(rows)} test cases to {OUT_CSV}")

    state["tests"] = [c.get("title", "Untitled Test") for c in cases]
    return state

# Node 3
def push_to_testrail(state: TestCaseState) -> TestCaseState:
    """Push generated test cases into TestRail."""
    logger.info("📤 Pushing test cases to TestRail...")

    tests = state.get("tests", [])
    if not tests:
        logger.warning("⚠️ No tests found in state; skipping push")
        return state

    created_ids: List[int] = []
    for title in tests:
        payload = map_case_to_testrail_payload({"title": title})
        try:
            res = create_case(payload)
            cid = res.get("id")
            if cid:
                created_ids.append(cid)
                add_result(cid, status_id=3, comment="Seeded by LangGraph pipeline")
        except Exception as e:
            logger.error(f"❌ Failed to create TestRail case '{title}': {e}")

    state["testrail_case_ids"] = [str(cid) for cid in created_ids]
    logger.info(f"✅ Created {len(created_ids)} TestRail cases: {created_ids}")

    # Optional: quick project stats
    try:
        stats = get_stats()
        total = stats.get("total_cases")
        logger.info(f"📊 TestRail now has {total} total cases")
    except Exception as e:
        logger.warning(f"⚠️ Could not fetch TestRail stats: {e}")

    return state