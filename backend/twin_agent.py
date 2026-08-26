import os
import json
import logging
from langchain_core.messages import HumanMessage
from supabase import create_client
from dotenv import load_dotenv
from backend.llm_factory import get_llm

load_dotenv('.env')
log = logging.getLogger(__name__)

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_ANON_KEY = os.environ.get("SUPABASE_ANON_KEY")
_supabase = create_client(SUPABASE_URL, SUPABASE_ANON_KEY)
llm_client = get_llm()

async def update_travel_twin(user_id: str, new_event: str):
    """
    Background observer function that updates a user's Travel Twin based on recent actions.
    """
    try:
        # Fetch current profile to get current twin via RPC (bypassing RLS)
        resp = _supabase.rpc("bot_get_travel_twin", {"p_user_id": user_id}).execute()
        current_profile = resp.data if resp.data else {}
        if not current_profile:
            current_profile = {
                "budget_sensitivity": 50,
                "hotel_preference_stars": 3.0,
                "walking_tolerance": "moderate",
                "adventure_preference": "moderate",
                "early_mornings": "moderate",
                "night_travel": "neutral",
                "food_preference": "local",
                "insights": []
            }
        
        prompt = f"""You are the Travel Twin Observer AI.
The user's current Travel Twin profile is:
{json.dumps(current_profile, indent=2)}

New event to analyze: "{new_event}"

Update the profile based on this event. 
Rules: 
1. budget_sensitivity is 0 to 100. (100 = very sensitive/cheap)
2. hotel_preference_stars is 1.0 to 5.0.
3. Keep other string values sensible.
4. Add exactly 1 new short, insightful string to the 'insights' array (max 5 insights total, remove oldest if needed) explaining what you learned.
5. Return ONLY a valid JSON object matching this schema. NO markdown wrapping, NO extra text.
"""
        print(f"DEBUG: Sending prompt to Gemini...")
        response = await llm_client.ainvoke(
            [HumanMessage(content=prompt)]
        )
        print(f"DEBUG: Received response from Gemini")
        
        content_val = response.content
        if isinstance(content_val, list):
            content_val = " ".join(item.get("text", "") for item in content_val if isinstance(item, dict) and "text" in item)
        output = str(content_val).strip()
        # Clean markdown if present
        if output.startswith("```"):
            output = output.split("```")[1]
            if output.startswith("json"):
                output = output[4:]
            output = output.strip()
            
        new_twin = json.loads(output)
        
        # Update DB using an RPC since this might run in a context where RLS blocks update
        # Actually, user profile update by anon key might be blocked. Let's create an RPC.
        # For now, let's just use the Supabase update (it requires auth, but since we are bot, let's use an RPC).
        _supabase.rpc("bot_update_travel_twin", {"p_user_id": user_id, "p_twin_data": new_twin}).execute()
        
        print(f"DEBUG: Successfully executed RPC bot_update_travel_twin for {user_id}")
        log.info(f"Travel Twin updated for {user_id}")
    except Exception as e:
        print(f"DEBUG: Exception in update_travel_twin: {e}")
        log.error(f"Travel Twin update failed: {e}")

def run_twin_update_sync(user_id: str, new_event: str):
    import asyncio
    try:
        print(f"DEBUG: Starting asyncio.run for twin update...")
        asyncio.run(update_travel_twin(user_id, new_event))
        print(f"DEBUG: Finished asyncio.run")
    except Exception as e:
        print(f"DEBUG: Exception in run_twin_update_sync: {e}")
        log.error(f"Sync twin update failed: {e}")

