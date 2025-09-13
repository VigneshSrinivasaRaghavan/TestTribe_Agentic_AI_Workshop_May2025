import logging
from langgraph.graph import StateGraph, END

from .state import TestCaseState
from .nodes import read_requirements, generate_tests_with_llm, push_to_testrail

# Logger setup (inherits from nodes.py but repeat here for clarity)
logging.basicConfig(level=logging.INFO, format="🔹 %(message)s")
logger = logging.getLogger(__name__)

def build_graph():
    """Build and return the compiled LangGraph pipeline."""

    # Create a graph object with our state type
    workflow = StateGraph(TestCaseState)

    # Register nodes
    workflow.add_node("read_requirements", read_requirements)
    workflow.add_node("generate_tests_with_llm", generate_tests_with_llm)
    workflow.add_node("push_to_testrail", push_to_testrail)

    # Define edges (order of execution)
    workflow.set_entry_point("read_requirements")
    workflow.add_edge("read_requirements", "generate_tests_with_llm")
    workflow.add_edge("generate_tests_with_llm", "push_to_testrail")
    workflow.add_edge("push_to_testrail", END)

    # Compile the graph into an executable app
    app = workflow.compile()
    logger.info("✅ Test Case Generator pipeline built successfully")
    return app