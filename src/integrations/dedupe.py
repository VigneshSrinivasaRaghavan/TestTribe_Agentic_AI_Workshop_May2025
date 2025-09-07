from __future__ import annotations
from pathlib import Path
import json
from datetime import datetime

CACHE = Path("outputs") / "log_analyzer" / "created_bugs.json"
CACHE.parent.mkdir(parents=True, exist_ok=True)

def _today_key(signature: str) -> str:
    day = datetime.utcnow().strftime("%Y-%m-%d")
    return f"{day}|{signature}"

def seen_today(signature: str) -> bool:
    if not CACHE.exists(): return False
    data = json.loads(CACHE.read_text(encoding="utf-8"))
    return _today_key(signature) in data

def mark_today(signature: str, issue_key: str) -> None:
    data = {}
    if CACHE.exists():
        data = json.loads(CACHE.read_text(encoding="utf-8"))
    data[_today_key(signature)] = issue_key
    CACHE.write_text(json.dumps(data, indent=2), encoding="utf-8")
