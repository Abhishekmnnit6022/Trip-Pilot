"""
LangGraph pipeline definition.

The graph uses a **router pattern**: every user message enters the `router`
node first.  The router decides whether to ask the user for more info,
kick off a full search pipeline, search return tickets, generate an
itinerary, or simply respond.

Pipeline paths
--------------
ask_user:           router → END  (wait for next user message)
respond:            router → END  (direct reply, no search needed)
search_all:         router → flight → train → hotel → present → END
search_return:      router → return → END
generate_itinerary: router → itinerary → final → END
"""

import logging
import psycopg
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.postgres import PostgresSaver

from backend.config import SUPABASE_DB_URL
from backend.agents.state import TravelState
from backend.agents.nodes import (
    router_agent,
    flight_agent,
    train_agent,
    hotel_agent,
    return_agent,
    itinerary_agent,
    final_agent,
    present_results,
)

log = logging.getLogger(__name__)


# ── Routing function ─────────────────────────────────────────────────────────

def _route_after_router(state: TravelState) -> str:
    """Decide which branch to take after the router node."""
    phase = state.get("phase", "")
    if phase == "search_all":
        return "search_all"
    if phase == "search_return":
        return "search_return"
    if phase == "generate_itinerary":
        return "generate_itinerary"
    # ask_user, respond, results_shown, complete → stop
    return "end"


# ── Build graph ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct the LangGraph StateGraph (not yet compiled)."""
    graph = StateGraph(TravelState)

    # Register nodes
    graph.add_node("router", router_agent)
    graph.add_node("flight_agent", flight_agent)
    graph.add_node("train_agent", train_agent)
    graph.add_node("hotel_agent", hotel_agent)
    graph.add_node("return_agent", return_agent)
    graph.add_node("itinerary_agent", itinerary_agent)
    graph.add_node("final_agent", final_agent)
    graph.add_node("present_results", present_results)

    # Entry: always start at router
    graph.add_edge(START, "router")

    # Conditional branching from router
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "search_all": "flight_agent",
            "search_return": "return_agent",
            "generate_itinerary": "itinerary_agent",
            "end": END,
        },
    )

    # search_all pipeline
    graph.add_edge("flight_agent", "train_agent")
    graph.add_edge("train_agent", "hotel_agent")
    graph.add_edge("hotel_agent", "present_results")
    graph.add_edge("present_results", END)

    # return pipeline
    graph.add_edge("return_agent", END)

    # itinerary pipeline
    graph.add_edge("itinerary_agent", "final_agent")
    graph.add_edge("final_agent", END)

    return graph


# ── Compile with Supabase PostgreSQL checkpointer ────────────────────────────

def compile_app():
    """
    Compile the graph with a PostgreSQL-backed checkpointer.
    Returns (compiled_app, connection) so the caller can manage the connection
    lifecycle.
    """
    if not SUPABASE_DB_URL:
        log.warning("SUPABASE_DB_URL not set — running WITHOUT checkpointer (no memory)")
        graph = build_graph()
        return graph.compile(), None

    log.info("Connecting to Supabase PostgreSQL for LangGraph checkpointing…")
    conn = psycopg.connect(SUPABASE_DB_URL, autocommit=True)
    checkpointer = PostgresSaver(conn)

    try:
        checkpointer.setup()
        log.info("LangGraph checkpoint tables ready.")
    except Exception as exc:
        # Tables may already exist from a previous run
        log.warning("Checkpointer setup note: %s", exc)

    graph = build_graph()
    compiled = graph.compile(checkpointer=checkpointer)
    return compiled, conn
