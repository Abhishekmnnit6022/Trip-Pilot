"""
Supabase authentication — verifies JWT tokens sent by the frontend.
"""

from fastapi import HTTPException, Header
from supabase import create_client
from backend.config import SUPABASE_URL, SUPABASE_ANON_KEY

_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)


def get_current_user(authorization: str = Header(default="")) -> dict:
    """
    FastAPI dependency: extract and verify the Supabase JWT from the
    ``Authorization: Bearer <token>`` header.

    Returns ``{"user_id": "...", "email": "..."}`` on success.
    """
    if not authorization.startswith("Bearer "):
        raise HTTPException(
            status_code=401,
            detail="Missing or invalid Authorization header",
        )

    token = authorization.removeprefix("Bearer ").strip()
    try:
        resp = _supabase.auth.get_user(token)
        user = resp.user
        if user is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return {"user_id": str(user.id), "email": user.email or "", "token": token}
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(
            status_code=401,
            detail=f"Authentication failed: {exc}",
        )
