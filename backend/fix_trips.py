import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.config import SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY
from supabase import create_client

client = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
resp = client.table("trips").select("*").execute()
for trip in resp.data:
    name = trip["name"]
    if name.lower().startswith("plan a trip to"):
        dest = name[14:].strip().title()
        new_name = f"Trip to {dest}"
        client.table("trips").update({"name": new_name}).eq("id", trip["id"]).execute()
        print(f"Updated '{name}' to '{new_name}'")
