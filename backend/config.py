"""
Centralized configuration — loads all environment variables once.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env from project root (one level up from backend/)
_env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(_env_path)

# ── API Keys ─────────────────────────────────────────────────────────────────
GROQ_API_KEY: str = os.getenv("GROQ_API_KEY", "").strip()
AVIATIONSTACK_API_KEY: str = os.getenv("AVIATIONSTACK_API_KEY", "").strip()
TAVILY_API_KEY: str = os.getenv("TAVILY_API_KEY", "").strip()
RAPIDAPI_KEY: str = os.getenv("RAPIDAPI", "").strip()
RAILRADAR_API_KEY: str = os.getenv("RAILRADAR_API_KEY", "").strip()

# ── Supabase ─────────────────────────────────────────────────────────────────
SUPABASE_URL: str = os.getenv("SUPABASE_URL", "").strip()
SUPABASE_ANON_KEY: str = os.getenv("SUPABASE_ANON_KEY", "").strip()
SUPABASE_DB_URL: str = os.getenv("SUPABASE_DB_URL", "").strip()

# ── LLM ──────────────────────────────────────────────────────────────────────
LLM_MODEL: str = "llama-3.3-70b-versatile"
