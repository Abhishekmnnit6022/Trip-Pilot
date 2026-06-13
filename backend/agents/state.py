"""
LangGraph state definition for the travel planning pipeline.
"""

from typing import TypedDict, Annotated
import operator
from langchain_core.messages import AnyMessage


class TravelState(TypedDict):
    """
    Shared state passed through every node in the LangGraph pipeline.

    Fields accumulated across conversation turns (via checkpointer):
    - messages:          Full conversation history (appended via operator.add)
    - user_query:        The latest user message text
    - origin:            Traveler's departure city
    - destination:       Destination city
    - start_date:        Trip start date (YYYY-MM-DD)
    - end_date:          Trip end date (YYYY-MM-DD)
    - num_days:          Number of trip days
    - budget:            Budget description
    - travel_mode:       "flight" | "train" | "both"
    - flight_results:    JSON string — list of flight dicts
    - train_results:     JSON string — list of train dicts
    - hotel_results:     JSON string — list of hotel dicts
    - return_results:    JSON string — list of return-transport dicts
    - itinerary:         Generated itinerary text
    - phase:             Current pipeline phase
    - needs_input:       What info is still missing (empty = ready to proceed)
    - llm_calls:         Counter of LLM invocations
    """

    messages: Annotated[list[AnyMessage], operator.add]
    user_query: str
    origin: str
    destination: str
    start_date: str
    end_date: str
    num_days: int
    budget: str
    travel_mode: str
    flight_results: str          # JSON string
    train_results: str           # JSON string
    hotel_results: str           # JSON string
    return_results: str          # JSON string
    itinerary: str
    phase: str
    needs_input: str
    llm_calls: int
