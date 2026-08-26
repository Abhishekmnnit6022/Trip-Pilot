"""
LLM Factory — Centralized provider resolution.

This module exports `get_llm()`, which returns the appropriate LangChain Chat Model
based on the `LLM_PROVIDER` environment variable. This allows the entire project
to switch LLMs instantly without changing code anywhere else.
"""

import logging
from backend.config import LLM_PROVIDER, GEMINI_API_KEY, GROQ_API_KEY, OPENROUTER_API_KEY, OPENAI_API_KEY, ANTHROPIC_API_KEY

log = logging.getLogger(__name__)

def get_llm(model_override: str = None):
    """
    Returns a configured LangChain ChatModel instance.
    
    Providers supported:
    - "gemini": Uses Google Gemini (ChatGoogleGenerativeAI)
    - "groq": Uses Groq Llama 3/Qwen (ChatGroq)
    - "openai": Uses OpenAI GPT models (ChatOpenAI)
    - "anthropic": Uses Anthropic Claude models (ChatAnthropic)
    - "ollama": Uses local Ollama models (ChatOllama)
    - "openrouter": Uses OpenRouter free tier (ChatOpenAI)
    """
    provider = LLM_PROVIDER.lower()

    if provider == "groq":
        from langchain_groq import ChatGroq
        model = model_override or "qwen/qwen3.8-27b"
        log.info("Initializing LLM with Groq (Model: %s)", model)
        return ChatGroq(model=model, api_key=GROQ_API_KEY)
        
    elif provider == "openai":
        from langchain_openai import ChatOpenAI
        model = model_override or "gpt-4o-mini"
        log.info("Initializing LLM with OpenAI (Model: %s)", model)
        return ChatOpenAI(model=model, api_key=OPENAI_API_KEY)
        
    elif provider == "anthropic":
        from langchain_anthropic import ChatAnthropic
        model = model_override or "claude-3-5-sonnet-20240620"
        log.info("Initializing LLM with Anthropic (Model: %s)", model)
        return ChatAnthropic(model=model, api_key=ANTHROPIC_API_KEY)
        
    elif provider == "ollama":
        from langchain_community.chat_models import ChatOllama
        model = model_override or "llama3"
        log.info("Initializing LLM with local Ollama (Model: %s)", model)
        return ChatOllama(model=model)
        
    elif provider == "openrouter":
        from langchain_openai import ChatOpenAI
        # OpenRouter uses the OpenAI SDK format under the hood
        model = model_override or "nvidia/nemotron-3.5-lightning:free"
        log.info("Initializing LLM with OpenRouter (Model: %s)", model)
        return ChatOpenAI(
            model=model, 
            api_key=OPENROUTER_API_KEY, 
            base_url="https://openrouter.ai/api/v1"
        )
        
    else:
        # Default to Gemini
        from langchain_google_genai import ChatGoogleGenerativeAI
        model = model_override or "gemini-1.5-flash"
        log.info("Initializing LLM with Google Gemini (Model: %s)", model)
        return ChatGoogleGenerativeAI(model=model, google_api_key=GEMINI_API_KEY)
