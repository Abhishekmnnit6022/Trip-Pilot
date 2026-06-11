"""
FastAPI application — serves the travel-planning chat API.

Endpoints
---------
POST /api/chat          SSE-streamed chat (sends agent updates in real time)
GET  /api/health        Health check
POST /api/new-session   Create a new conversation thread
"""

import json
import queue
import logging
import threading
import uuid
from contextlib import asynccontextmanager

from fastapi import FastAPI, Depends, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from sse_starlette.sse import EventSourceResponse
from langchain_core.messages import HumanMessage, AIMessage

from backend.auth import get_current_user
from backend.agents.graph import compile_app

log = logging.getLogger(__name__)
logging.basicConfig(level=logging.INFO, format="%(asctime)s  %(name)s  %(message)s")

# ── Globals (set during lifespan) ────────────────────────────────────────────
_compiled_app = None
_db_conn = None


@asynccontextmanager
async def lifespan(application: FastAPI):
    """Startup: compile graph + connect DB.  Shutdown: close DB connection."""
    global _compiled_app, _db_conn
    log.info("Starting up — compiling LangGraph pipeline…")
    _compiled_app, _db_conn = compile_app()
    log.info("Pipeline ready.")
    yield
    if _db_conn:
        _db_conn.close()
        log.info("Database connection closed.")


app = FastAPI(
    title="AI Travel Planner API",
    version="1.0.0",
    lifespan=lifespan,
)

# ── CORS (allow the Next.js frontend) ────────────────────────────────────────
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://localhost:5173",
        "http://127.0.0.1:5173",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ── Request / Response models ────────────────────────────────────────────────

class ChatRequest(BaseModel):
    message: str
    thread_id: str = ""


class NewSessionResponse(BaseModel):
    thread_id: str


# ── Endpoints ────────────────────────────────────────────────────────────────

@app.get("/api/health")
async def health():
    return {"status": "ok", "pipeline": _compiled_app is not None}


@app.post("/api/new-session", response_model=NewSessionResponse)
async def new_session(user: dict = Depends(get_current_user)):
    """Create a fresh conversation thread tied to the authenticated user."""
    thread_id = f"{user['user_id']}_{uuid.uuid4().hex[:8]}"
    return NewSessionResponse(thread_id=thread_id)


@app.post("/api/chat")
async def chat(req: ChatRequest, user: dict = Depends(get_current_user)):
    """
    Main chat endpoint.  Streams Server-Sent Events as agents execute:

    Events emitted
    ~~~~~~~~~~~~~~
    ``agent_start``   — an agent node has begun executing
    ``agent_result``  — an agent produced structured data (flights / trains / hotels)
    ``message``       — a text message for the chat bubble
    ``done``          — pipeline finished
    ``error``         — something went wrong
    """
    if not _compiled_app:
        raise HTTPException(status_code=503, detail="Pipeline not ready")
    if not req.message.strip():
        raise HTTPException(status_code=400, detail="Message cannot be empty")

    thread_id = req.thread_id or f"{user['user_id']}_{uuid.uuid4().hex[:8]}"
    config = {"configurable": {"thread_id": thread_id}}

    # Determine if this is the first message (no checkpoint yet)
    try:
        existing = _compiled_app.get_state(config)
        is_first = not existing.values
    except Exception:
        is_first = True

    if is_first:
        input_state = {
            "messages": [HumanMessage(content=req.message)],
            "user_query": req.message,
            "origin": "",
            "destination": "",
            "start_date": "",
            "end_date": "",
            "num_days": 0,
            "budget": "",
            "travel_mode": "",
            "flight_results": "",
            "train_results": "",
            "hotel_results": "",
            "return_results": "",
            "itinerary": "",
            "phase": "intake",
            "needs_input": "",
            "llm_calls": 0,
        }
    else:
        input_state = {
            "messages": [HumanMessage(content=req.message)],
            "user_query": req.message,
        }

    async def event_stream():
        q: queue.Queue = queue.Queue()

        def _run_graph():
            try:
                for chunk in _compiled_app.stream(
                    input_state,
                    config=config,
                    stream_mode="updates",
                ):
                    q.put(("chunk", chunk))
                q.put(("done", None))
            except Exception as exc:
                q.put(("error", str(exc)))

        thread = threading.Thread(target=_run_graph, daemon=True)
        thread.start()

        while True:
            try:
                kind, payload = q.get(timeout=120)
            except queue.Empty:
                yield {"event": "error", "data": json.dumps({"detail": "Timeout"})}
                break

            if kind == "error":
                yield {"event": "error", "data": json.dumps({"detail": payload})}
                break

            if kind == "done":
                # Send final state snapshot
                try:
                    final_state = _compiled_app.get_state(config)
                    state_vals = final_state.values or {}
                    snapshot = {
                        "thread_id": thread_id,
                        "origin": state_vals.get("origin", ""),
                        "destination": state_vals.get("destination", ""),
                        "start_date": state_vals.get("start_date", ""),
                        "end_date": state_vals.get("end_date", ""),
                        "num_days": state_vals.get("num_days", 0),
                        "phase": state_vals.get("phase", ""),
                    }
                    yield {
                        "event": "state",
                        "data": json.dumps(snapshot),
                    }
                except Exception:
                    pass
                yield {"event": "done", "data": "{}"}
                break

            if kind == "chunk":
                for node_name, state_update in payload.items():
                    # Notify that this agent started
                    yield {
                        "event": "agent_start",
                        "data": json.dumps({"agent": node_name}),
                    }

                    # Extract structured results
                    for key, evt_type in [
                        ("flight_results", "flights"),
                        ("train_results", "trains"),
                        ("hotel_results", "hotels"),
                        ("return_results", "return_transport"),
                    ]:
                        raw = state_update.get(key, "")
                        if raw:
                            try:
                                parsed_data = json.loads(raw)
                                if parsed_data:
                                    yield {
                                        "event": "agent_result",
                                        "data": json.dumps({
                                            "agent": node_name,
                                            "type": evt_type,
                                            "data": parsed_data,
                                        }),
                                    }
                            except (json.JSONDecodeError, TypeError):
                                pass

                    # Extract itinerary
                    itin = state_update.get("itinerary", "")
                    if itin:
                        yield {
                            "event": "itinerary",
                            "data": json.dumps({"content": itin}),
                        }

                    # Extract text messages
                    msgs = state_update.get("messages", [])
                    for msg in msgs:
                        if isinstance(msg, AIMessage):
                            yield {
                                "event": "message",
                                "data": json.dumps({
                                    "content": msg.content,
                                    "agent": node_name,
                                }),
                            }

    return EventSourceResponse(event_stream())
