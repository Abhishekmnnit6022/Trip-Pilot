"""
nodes package — modular agent functions for the LangGraph travel-planning pipeline.

Sub-modules
-----------
utils           — shared helpers (text extraction, JSON cleaning, booking helpers)
router_node     — router_agent
transport_nodes — flight_agent, train_agent, return_agent,
                  auto_book_train_agent, auto_book_flight_agent, offer_alternate_agent
hotel_node      — hotel_agent, auto_book_hotel_agent
itinerary_nodes — itinerary_agent, final_agent
budget_nodes    — budget_check_node, budget_optimizer_node
results_node    — present_results

All public symbols are re-exported here so that existing code that does:
    from backend.agents.nodes import router_agent, ...
continues to work without any modification.
"""

from backend.agents.nodes.utils import extract_text, clean_llm_json
from backend.agents.nodes.router_node import router_agent
from backend.agents.nodes.transport_nodes import (
    flight_agent,
    train_agent,
    return_agent,
    auto_book_train_agent,
    auto_book_flight_agent,
    offer_alternate_agent,
)
from backend.agents.nodes.hotel_node import hotel_agent, auto_book_hotel_agent
from backend.agents.nodes.itinerary_nodes import itinerary_agent, final_agent
from backend.agents.nodes.budget_nodes import budget_check_node, budget_optimizer_node
from backend.agents.nodes.results_node import present_results

__all__ = [
    "extract_text",
    "clean_llm_json",
    "router_agent",
    "flight_agent",
    "train_agent",
    "return_agent",
    "auto_book_train_agent",
    "auto_book_flight_agent",
    "offer_alternate_agent",
    "hotel_agent",
    "auto_book_hotel_agent",
    "itinerary_agent",
    "final_agent",
    "budget_check_node",
    "budget_optimizer_node",
    "present_results",
]
