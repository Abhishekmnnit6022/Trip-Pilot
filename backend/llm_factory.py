"""
LLM Factory — Centralized provider resolution.

This module exports `get_llm()`, which returns the appropriate LangChain Chat Model
based on the `LLM_PROVIDER` environment variable. This allows the entire project
to switch LLMs instantly without changing code anywhere else.

SELF-HEALING GROQ MODEL SELECTION
-----------------------------------
For Groq, instead of hardcoding a model name (which can 404 if your account
doesn't have access), the factory queries the Groq /v1/models endpoint at
startup and picks the best available model from a priority list.
This means the app will NEVER crash due to a model being unavailable again.
"""

import logging
import requests
from backend.config import (
    LLM_PROVIDER, GEMINI_API_KEY, GROQ_API_KEY,
    OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
)

log = logging.getLogger(__name__)

# ── Groq model priority list ─────────────────────────────────────────────────
# Ordered from most capable → fastest. The factory picks the first one that
# is actually available on your Groq account.
# Models that use <think> blocks are flagged so the JSON cleaner stays alert.
_GROQ_PRIORITY = [
    # Production models (stable, never deprecated without notice)
    "llama-3.3-70b-versatile",       # Best quality, production
    "llama-3.1-8b-instant",          # Fast, production
    # Preview models (available but may be removed at short notice)
    "qwen/qwen3.8-27b",              # Has <think> blocks — handled by clean_llm_json
    "qwen/qwen3.6-27b",              # Has <think> blocks — handled by clean_llm_json
    "moonshotai/kimi-k2-instruct",   # Preview fallback
]

# Cache so we only query the API once per process startup
_groq_model_cache: str | None = None


def _resolve_groq_model() -> str:
    """
    Query the Groq /v1/models API and return the best available model
    from the priority list. Caches the result for the process lifetime.
    """
    global _groq_model_cache
    if _groq_model_cache:
        return _groq_model_cache

    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={
                "Authorization": f"Bearer {GROQ_API_KEY}",
                "Content-Type": "application/json",
            },
            timeout=10,
        )
        resp.raise_for_status()
        available_ids = {m["id"] for m in resp.json().get("data", [])}
        log.info("[LLMFactory] Groq available models: %s", sorted(available_ids))

        for candidate in _GROQ_PRIORITY:
            if candidate in available_ids:
                log.info("[LLMFactory] Selected Groq model: %s", candidate)
                _groq_model_cache = candidate
                return candidate

        # Nothing from priority list matched — use whatever is first
        if available_ids:
            fallback = next(iter(sorted(available_ids)))
            log.warning(
                "[LLMFactory] No priority model available. Falling back to: %s", fallback
            )
            _groq_model_cache = fallback
            return fallback

    except Exception as exc:
        log.warning(
            "[LLMFactory] Could not query Groq models API (%s). "
            "Using default: llama-3.3-70b-versatile", exc
        )

    # Hard fallback if the API call itself fails
    _groq_model_cache = "llama-3.3-70b-versatile"
    return _groq_model_cache


# ── Public factory function ──────────────────────────────────────────────────

def get_llm(model_override: str = None):
    """
    Returns a configured LangChain ChatModel instance.

    Providers supported:
    - \"groq\":       Auto-detects best available model on your account (self-healing)
    - \"gemini\":     Uses Google Gemini (ChatGoogleGenerativeAI)
    - \"openai\":     Uses OpenAI GPT models (ChatOpenAI)
    - \"anthropic\":  Uses Anthropic Claude models (ChatAnthropic)
    - \"ollama\":     Uses local Ollama models (ChatOllama)
    - \"openrouter\": Uses OpenRouter free tier (ChatOpenAI)
    """
    provider = LLM_PROVIDER.lower()

    if provider == "groq":
        from langchain_groq import ChatGroq
        model = model_override or _resolve_groq_model()
        log.info("[LLMFactory] Initializing Groq LLM (model=%s)", model)
        return ChatGroq(model=model, api_key=GROQ_API_KEY, temperature=0)

    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        model = model_override or "gpt-4o-mini"
        log.info("[LLMFactory] Initializing OpenAI LLM (model=%s)", model)
        return ChatOpenAI(model=model, api_key=OPENAI_API_KEY, temperature=0)

    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = model_override or "claude-3-5-sonnet-20240620"
        log.info("[LLMFactory] Initializing Anthropic LLM (model=%s)", model)
        return ChatAnthropic(model=model, api_key=ANTHROPIC_API_KEY, temperature=0)

    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        model = model_override or "llama3"
        log.info("[LLMFactory] Initializing Ollama LLM (model=%s)", model)
        return ChatOllama(model=model)

    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        model = model_override or "nvidia/nemotron-3.5-lightning:free"
        log.info("[LLMFactory] Initializing OpenRouter LLM (model=%s)", model)
        return ChatOpenAI(
            model=model,
            api_key=OPENROUTER_API_KEY,
            base_url="https://openrouter.ai/api/v1",
            temperature=0,
        )

    else:
        # Default to Gemini
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = model_override or "gemini-1.5-flash"
        log.info("[LLMFactory] Initializing Gemini LLM (model=%s)", model)
        return ChatGoogleGenerativeAI(
            model=model,
            google_api_key=GEMINI_API_KEY,
            temperature=0,
        )
