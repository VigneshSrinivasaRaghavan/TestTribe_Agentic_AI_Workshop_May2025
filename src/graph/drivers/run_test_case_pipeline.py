import logging
from pprint import pprint
import argparse

from src.graph.test_case_generator.graph import build_graph
from src.graph.test_case_generator.state import TestCaseState

logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--input",
        help="Path to a requirement .txt file (default: first in data/requirements/)",
        default=None,
    )
    args = parser.parse_args()

    logger.info("🚀 Starting Test Case Generator pipeline...")

    app = build_graph()

    # Initial state: pass requirement path if provided
    init_state: TestCaseState = {}
    if args.input:
        init_state["requirement_path"] = args.input

    final_state = app.invoke(init_state)

    # Summarized final output
    num_tests = len(final_state.get("tests", []))
    num_ids = len(final_state.get("testrail_case_ids", []))
    logger.info(f"✅ Finished: {num_tests} tests generated, {num_ids} cases pushed to TestRail.")


if __name__ == "__main__":
    main()
