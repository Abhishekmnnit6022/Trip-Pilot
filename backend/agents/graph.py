"""
LangGraph pipeline definition.

The graph uses a **guided booking pattern**: every user message enters the
`router` node first. The router guides the user step-by-step through:

1. Collecting trip details (destination, dates, origin)
2. Asking transport preference (train or flight)
3. Auto-booking the best transport option
4. Handling waitlist (offering alternates)
5. Asking about hotel preferences
6. Auto-booking the best hotel
7. Generating a rich visual itinerary

Pipeline paths
--------------
ask_user / ask_hotel:   router → END (wait for next user message)
respond:                router → END (direct reply, no action needed)
auto_book_train:        router → auto_book_train → END
auto_book_flight:       router → auto_book_flight → END
auto_book_hotel:        router → auto_book_hotel → generate_itinerary → END
generate_itinerary:     router → itinerary → budget_check →
                          ├─ (within budget OR no budget) → final → END
                          └─ (over budget, attempts < 2)  → optimizer → budget_check (LOOP)
offer_alternate:        router → offer_alternate → END
search_return:          router → return → END
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
    budget_check_node,
    budget_optimizer_node,
    auto_book_train_agent,
    auto_book_flight_agent,
    auto_book_hotel_agent,
    offer_alternate_agent,
)

log = logging.getLogger(__name__)


# ── Routing function: after router ───────────────────────────────────────────

def _route_after_router(state: TravelState) -> str:
    """Decide which branch to take after the router node."""
    phase = state.get("phase", "")
    if phase == "auto_book_train":
        return "auto_book_train"
    if phase == "auto_book_flight":
        return "auto_book_flight"
    if phase == "auto_book_hotel":
        return "auto_book_hotel"
    if phase == "generate_itinerary":
        return "generate_itinerary"
    if phase == "offer_alternate":
        return "offer_alternate"
    if phase == "search_return":
        return "search_return"
    # ask_user, ask_hotel, respond, results_shown, complete → stop
    return "end"


# ── Routing function: after budget_check ─────────────────────────────────────

def _route_after_budget_check(state: TravelState) -> str:
    """
    Decide whether the trip is within budget or needs optimization.
    
    Routes to:
      - "within_budget"  → final_agent (proceed normally)
      - "over_budget"    → budget_optimizer_node (optimize and loop back)
    """
    total_cost = state.get("total_estimated_cost", 0)
    budget_limit = state.get("budget_limit", 0)
    optimization_count = state.get("optimization_count", 0)

    # No budget specified → skip optimization entirely
    if not budget_limit:
        log.info("[BudgetRoute] No budget limit → proceeding to final agent")
        return "within_budget"

    # Within budget → proceed
    if total_cost <= budget_limit:
        log.info("[BudgetRoute] ₹%d <= ₹%d → within budget!", total_cost, budget_limit)
        return "within_budget"

    # Over budget but already optimized twice → give up, proceed with best effort
    if optimization_count >= 2:
        log.warning(
            "[BudgetRoute] ₹%d > ₹%d but max optimizations reached (%d) → proceeding anyway",
            total_cost, budget_limit, optimization_count,
        )
        return "within_budget"

    # Over budget and has optimization attempts remaining → optimize
    log.info(
        "[BudgetRoute] ₹%d > ₹%d → triggering optimization (attempt #%d)",
        total_cost, budget_limit, optimization_count + 1,
    )
    return "over_budget"


# ── Build graph ──────────────────────────────────────────────────────────────

def build_graph() -> StateGraph:
    """Construct the LangGraph StateGraph (not yet compiled)."""
    graph = StateGraph(TravelState)

    # Register nodes
    graph.add_node("router", router_agent)
    graph.add_node("auto_book_train", auto_book_train_agent)
    graph.add_node("auto_book_flight", auto_book_flight_agent)
    graph.add_node("auto_book_hotel", auto_book_hotel_agent)
    graph.add_node("offer_alternate", offer_alternate_agent)
    graph.add_node("return_agent", return_agent)
    graph.add_node("itinerary_agent", itinerary_agent)
    graph.add_node("budget_check", budget_check_node)
    graph.add_node("budget_optimizer", budget_optimizer_node)
    graph.add_node("final_agent", final_agent)

    # Entry: always start at router
    graph.add_edge(START, "router")

    # Conditional branching from router
    graph.add_conditional_edges(
        "router",
        _route_after_router,
        {
            "auto_book_train": "auto_book_train",
            "auto_book_flight": "auto_book_flight",
            "auto_book_hotel": "auto_book_hotel",
            "generate_itinerary": "itinerary_agent",
            "offer_alternate": "offer_alternate",
            "search_return": "return_agent",
            "end": END,
        },
    )

    # Auto-book agents → END (wait for next user message)
    graph.add_edge("auto_book_train", END)
    graph.add_edge("auto_book_flight", END)
    graph.add_edge("auto_book_hotel", END)

    # Alternate transport → END (wait for user decision)
    graph.add_edge("offer_alternate", END)

    # Return pipeline
    graph.add_edge("return_agent", END)

    # ── Itinerary pipeline with Budget Optimization Loop ──
    graph.add_edge("itinerary_agent", "budget_check")

    graph.add_conditional_edges(
        "budget_check",
        _route_after_budget_check,
        {
            "within_budget": "final_agent",
            "over_budget": "budget_optimizer",
        },
    )

    # Budget optimizer loops back to budget_check for re-evaluation
    graph.add_edge("budget_optimizer", "budget_check")

    # Final agent terminates the pipeline
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
