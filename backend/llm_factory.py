"""
LLM Factory — Centralized provider resolution with multi-provider fallback.

HOW IT WORKS
------------
1. Primary:  Uses LLM_PROVIDER from .env (default: groq)
2. Fallback chain (auto, no config needed):
      Groq → Gemini → OpenRouter
   The app tries each provider in order. If one fails (404, auth error,
   rate limit), it silently moves to the next.
3. Groq model selection is self-healing: queries /v1/models at startup
   and picks the best available model from the priority list.

This means the app will NEVER crash due to a single provider being down,
deprecated, or rate-limited. You never need to touch this file again.
"""

import logging
import requests
from backend.config import (
    LLM_PROVIDER, GEMINI_API_KEY, GROQ_API_KEY,
    OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY,
    CEREBRAS_API_KEY,
)

log = logging.getLogger(__name__)

# ── Groq model priority list ──────────────────────────────────────────────────
# Ordered best → fastest. Factory picks the first one YOUR key can access.
_GROQ_PRIORITY = [
    "llama-3.3-70b-versatile",    # Production — best quality
    "llama-3.1-8b-instant",       # Production — fastest
    "qwen/qwen3.8-27b",           # Preview — has <think> blocks (handled)
    "qwen/qwen3.6-27b",           # Preview — has <think> blocks (handled)
    "moonshotai/kimi-k2-instruct",# Preview — fallback
]

# ── Provider fallback chain ───────────────────────────────────────────────────
# When the primary provider fails, the factory tries these in order.
# Only providers with a non-empty API key are attempted.
_FALLBACK_CHAIN = [
    "groq",
    "cerebras",   # ~2000 tok/s — fastest free inference available
    "gemini",
    "openrouter",
]

# Cache resolved Groq model for the process lifetime
_groq_model_cache: str | None = None

# Track which provider+model is currently active (for logging)
_active_provider: str = "unknown"
_active_model: str = "unknown"

def get_active_llm_info() -> str:
    """Returns a human-readable string of the active LLM for use in logs."""
    return f"{_active_provider} / {_active_model}"


# ── Groq: auto-detect best available model ────────────────────────────────────

def _resolve_groq_model() -> str:
    """Query Groq /v1/models and return the best available model from priority list."""
    global _groq_model_cache
    if _groq_model_cache:
        return _groq_model_cache

    try:
        resp = requests.get(
            "https://api.groq.com/openai/v1/models",
            headers={"Authorization": f"Bearer {GROQ_API_KEY}"},
            timeout=10,
        )
        resp.raise_for_status()
        available = {m["id"] for m in resp.json().get("data", [])}
        log.info("[LLMFactory] Groq models available on this key: %s", sorted(available))

        for candidate in _GROQ_PRIORITY:
            if candidate in available:
                log.info("[LLMFactory] ✅ Selected Groq model: %s", candidate)
                _groq_model_cache = candidate
                return candidate

        # Nothing matched — use first available
        if available:
            fallback = sorted(available)[0]
            log.warning("[LLMFactory] No priority model found, using: %s", fallback)
            _groq_model_cache = fallback
            return fallback

    except Exception as exc:
        log.warning("[LLMFactory] Groq model API query failed (%s). Using default.", exc)

    _groq_model_cache = "llama-3.3-70b-versatile"
    return _groq_model_cache


# ── Individual provider constructors ─────────────────────────────────────────

def _make_groq(model_override=None):
    global _active_provider, _active_model
    if not GROQ_API_KEY:
        raise ValueError("GROQ_API_KEY not set")
    from langchain_groq import ChatGroq
    model = model_override or _resolve_groq_model()
    _active_provider, _active_model = "groq", model
    log.info("[LLMFactory] 🤖 ACTIVE LLM → Groq / %s", model)
    return ChatGroq(model=model, api_key=GROQ_API_KEY, temperature=0)


def _make_gemini(model_override=None):
    global _active_provider, _active_model
    if not GEMINI_API_KEY:
        raise ValueError("GEMINI_API_KEY not set")
    from langchain_google_genai import ChatGoogleGenerativeAI
    model = model_override or "gemini-1.5-flash"
    _active_provider, _active_model = "gemini", model
    log.info("[LLMFactory] 🤖 ACTIVE LLM → Gemini / %s", model)
    return ChatGoogleGenerativeAI(model=model, google_api_key=GEMINI_API_KEY, temperature=0)


def _make_openrouter(model_override=None):
    global _active_provider, _active_model
    if not OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY not set")
    from langchain_openai import ChatOpenAI
    model = model_override or "meta-llama/llama-3.1-8b-instruct:free"
    _active_provider, _active_model = "openrouter", model
    log.info("[LLMFactory] 🤖 ACTIVE LLM → OpenRouter / %s", model)
    return ChatOpenAI(
        model=model,
        api_key=OPENROUTER_API_KEY,
        base_url="https://openrouter.ai/api/v1",
        temperature=0,
    )


def _make_cerebras(model_override=None):
    global _active_provider, _active_model
    if not CEREBRAS_API_KEY:
        raise ValueError("CEREBRAS_API_KEY not set")
    from langchain_openai import ChatOpenAI
    # Cerebras Cloud is OpenAI-compatible. llama-3.3-70b runs at ~2000 tok/s.
    model = model_override or "llama-3.3-70b"
    _active_provider, _active_model = "cerebras", model
    log.info("[LLMFactory] 🤖 ACTIVE LLM → Cerebras / %s", model)
    return ChatOpenAI(
        model=model,
        api_key=CEREBRAS_API_KEY,
        base_url="https://api.cerebras.ai/v1",
        temperature=0,
    )


def _make_openai(model_override=None):
    if not OPENAI_API_KEY or OPENAI_API_KEY == "your_openai_api_key_here":
        raise ValueError("OPENAI_API_KEY not set")
    from langchain_openai import ChatOpenAI
    model = model_override or "gpt-4o-mini"
    log.info("[LLMFactory] OpenAI → %s", model)
    return ChatOpenAI(model=model, api_key=OPENAI_API_KEY, temperature=0)


def _make_anthropic(model_override=None):
    if not ANTHROPIC_API_KEY or ANTHROPIC_API_KEY == "your_anthropic_api_key_here":
        raise ValueError("ANTHROPIC_API_KEY not set")
    from langchain_anthropic import ChatAnthropic
    model = model_override or "claude-3-5-sonnet-20240620"
    log.info("[LLMFactory] Anthropic → %s", model)
    return ChatAnthropic(model=model, api_key=ANTHROPIC_API_KEY, temperature=0)


def _make_ollama(model_override=None):
    from langchain_community.chat_models import ChatOllama
    model = model_override or "llama3"
    log.info("[LLMFactory] Ollama → %s", model)
    return ChatOllama(model=model)


_PROVIDER_MAP = {
    "groq":       _make_groq,
    "cerebras":   _make_cerebras,
    "gemini":     _make_gemini,
    "openrouter": _make_openrouter,
    "openai":     _make_openai,
    "anthropic":  _make_anthropic,
    "ollama":     _make_ollama,
}


# ── Public factory with fallback chain ───────────────────────────────────────

def get_llm(model_override: str = None):
    """
    Returns a configured LangChain ChatModel instance.

    Tries LLM_PROVIDER first, then falls back through:
      Groq → Gemini → OpenRouter
    until one succeeds. Raises RuntimeError only if ALL providers fail.
    """
    primary = LLM_PROVIDER.lower()

    # Build ordered list: primary first, then fallbacks (skip duplicates)
    ordered = [primary] + [p for p in _FALLBACK_CHAIN if p != primary]

    last_err = None
    for provider in ordered:
        maker = _PROVIDER_MAP.get(provider)
        if not maker:
            continue
        try:
            return maker(model_override)
        except Exception as exc:
            log.warning(
                "[LLMFactory] Provider '%s' failed (%s). Trying next fallback...",
                provider, exc,
            )
            last_err = exc

    raise RuntimeError(
        f"All LLM providers failed. Last error: {last_err}. "
        "Please check your API keys in .env"
    )
