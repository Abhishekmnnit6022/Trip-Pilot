"""
Budget-related nodes:
  - budget_check_node     — extracts estimated trip cost from the itinerary
  - budget_optimizer_node — rewrites itinerary to fit within budget
  - _parse_budget_to_inr  — helper: converts human-readable budget string -> int INR
"""

import json
import logging
import re

from langchain_core.messages import AIMessage, HumanMessage, SystemMessage

from backend.agents.state import TravelState
from backend.agents.nodes.utils import extract_text, clean_llm_json
from backend.llm_factory import get_llm

log = logging.getLogger(__name__)
llm = get_llm()

# ─────────────────────────────────────────────────────────────────────────────
# Prompts
# ─────────────────────────────────────────────────────────────────────────────

_COST_EXTRACT_PROMPT = """You are a financial analyst. Given a travel itinerary, extract the TOTAL
estimated trip cost in Indian Rupees (INR).

Rules:
1. Sum up ALL costs: transport (flights/trains), hotels, food, activities, misc.
2. If exact prices are not listed, estimate reasonable prices for India.
3. Return ONLY a JSON object: {"total_cost_inr": <integer>}
4. No markdown, no explanation, just the JSON.

Example: {"total_cost_inr": 18500}
"""

_OPTIMIZER_PROMPT = """You are an expert budget travel optimizer. The user's trip costs {total_cost} INR
but their budget is only {budget_limit} INR.

You need to reduce the cost by {overshoot} INR.

Current itinerary:
{itinerary}

Available transport data:
Flights: {flights}
Trains: {trains}
Hotels: {hotels}

The user's Travel Twin Profile is:
{travel_twin}

OPTIMIZATION STRATEGIES (apply in order):
1. Replace flights with trains (saves 40-60%)
2. Replace luxury/5-star hotels with budget/3-star hotels (saves 50-70%)
3. Suggest cheaper dining options (local dhabas vs restaurants)
4. Recommend free/low-cost tourist activities over paid ones
5. Optimize travel dates if flexibility exists

Respond with ONLY valid JSON (no markdown):
{
    "optimized_itinerary": "<complete re-written itinerary with cheaper options>",
    "cost_savings": "<explanation of what was changed and estimated savings>",
    "new_estimated_cost": <integer in INR>,
    "changes_made": ["<change 1>", "<change 2>", ...]
}
"""


# ─────────────────────────────────────────────────────────────────────────────
# Helper
# ─────────────────────────────────────────────────────────────────────────────

def _parse_budget_to_inr(budget_str: str) -> int:
    """
    Parse a human-readable budget string into an integer INR value.
    Handles formats like: "15000", "15k", "15,000", "budget", "luxury"
    """
    text = (
        budget_str.lower().strip()
        .replace(",", "").replace("\u20b9", "").replace("rs", "").replace("inr", "")
    )

    BUDGET_TIERS = {
        "budget": 10000,
        "cheap": 8000,
        "economy": 12000,
        "moderate": 20000,
        "mid-range": 25000,
        "luxury": 50000,
        "premium": 75000,
        "flexible": 0,
    }
    for keyword, amount in BUDGET_TIERS.items():
        if keyword in text:
            return amount

    match = re.search(r"(\d+)\s*k", text)
    if match:
        return int(match.group(1)) * 1000

    match = re.search(r"(\d+)", text)
    if match:
        return int(match.group(1))

    return 0


# ─────────────────────────────────────────────────────────────────────────────
# Budget check node
# ─────────────────────────────────────────────────────────────────────────────

def budget_check_node(state: TravelState) -> dict:
    """
    Extract total estimated cost from the itinerary using the LLM.

    Sits between itinerary_agent and the conditional budget routing edge.
    The extracted cost is stored in `total_estimated_cost` for routing.
    """
    itinerary = state.get("itinerary", "")
    budget = state.get("budget", "")
    budget_limit = state.get("budget_limit", 0)

    if not budget_limit and not budget:
        log.info("[BudgetCheck] No budget specified — skipping cost estimation")
        return {
            "total_estimated_cost": 0,
            "llm_calls": state.get("llm_calls", 0),
        }

    if budget and not budget_limit:
        budget_limit = _parse_budget_to_inr(budget)
        log.info("[BudgetCheck] Parsed budget '%s' -> %d INR", budget, budget_limit)

    try:
        response = llm.invoke([
            SystemMessage(content=_COST_EXTRACT_PROMPT),
            HumanMessage(content=f"Extract the total cost from this itinerary:\n\n{itinerary}"),
        ])
        content = clean_llm_json(extract_text(response.content))
        parsed = json.loads(content)
        total_cost = int(parsed.get("total_cost_inr", 0))
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[BudgetCheck] Could not parse cost from LLM: %s", exc)
        total_cost = 0

    log.info(
        "[BudgetCheck] Estimated: %d INR | Budget: %d INR | Optimization #%d",
        total_cost, budget_limit, state.get("optimization_count", 0),
    )

    return {
        "total_estimated_cost": total_cost,
        "budget_limit": budget_limit,
        "messages": [AIMessage(content=f"Estimated trip cost: {total_cost:,} INR")],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Budget optimizer node
# ─────────────────────────────────────────────────────────────────────────────

def budget_optimizer_node(state: TravelState) -> dict:
    """Autonomously optimize the trip to fit within the user's budget."""
    total_cost = state.get("total_estimated_cost", 0)
    budget_limit = state.get("budget_limit", 0)
    overshoot = total_cost - budget_limit
    itinerary = state.get("itinerary", "")
    optimization_count = state.get("optimization_count", 0)
    flights_text = state.get("flight_results", "[]")
    trains_text = state.get("train_results", "[]")
    hotels_text = state.get("hotel_results", "[]")

    log.info(
        "[BudgetOptimizer] Optimizing (attempt #%d): %d -> %d INR (overshoot: %d)",
        optimization_count + 1, total_cost, budget_limit, overshoot,
    )

    prompt = _OPTIMIZER_PROMPT.format(
        total_cost=f"{total_cost:,}",
        budget_limit=f"{budget_limit:,}",
        overshoot=f"{overshoot:,}",
        itinerary=itinerary,
        flights=flights_text,
        trains=trains_text,
        hotels=hotels_text,
        travel_twin=json.dumps(state.get("travel_twin_profile", {}), indent=2),
    )

    try:
        response = llm.invoke([
            SystemMessage(content="You are an expert budget travel optimizer. Reduce trip costs while maintaining a great experience."),
            HumanMessage(content=prompt),
        ])
        content = extract_text(response.content).strip()
        if content.startswith("```json"):
            content = content[7:-3]
        elif content.startswith("```"):
            content = content[3:-3]
        parsed = json.loads(content.strip())
        optimized_itinerary = parsed.get("optimized_itinerary", itinerary)
        new_cost = int(parsed.get("new_estimated_cost", total_cost))
        changes = parsed.get("changes_made", [])
        savings_text = parsed.get("cost_savings", "")
    except (json.JSONDecodeError, ValueError, TypeError) as exc:
        log.warning("[BudgetOptimizer] Could not parse optimizer response: %s", exc)
        optimized_itinerary = itinerary
        new_cost = total_cost
        changes = []
        savings_text = ""

    changes_str = "\n".join(f"  - {c}" for c in changes) if changes else "  - Minor adjustments made"
    msg = (
        f"**Budget Optimization (Round {optimization_count + 1})**\n\n"
        f"Previous cost: {total_cost:,} INR\n"
        f"Target budget: {budget_limit:,} INR\n"
        f"New estimated cost: {new_cost:,} INR\n\n"
        f"**Changes made:**\n{changes_str}"
    )
    if savings_text:
        msg += f"\n\n{savings_text}"

    return {
        "itinerary": optimized_itinerary,
        "total_estimated_cost": new_cost,
        "optimization_count": optimization_count + 1,
        "messages": [AIMessage(content=msg)],
        "llm_calls": state.get("llm_calls", 0) + 1,
    }
