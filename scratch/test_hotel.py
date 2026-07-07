import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from backend.tools.hotel_tool import _search_rapidapi
import json

res = _search_rapidapi("Pune", "2026-08-20", "2026-08-22")
print(json.dumps(res, indent=2))
