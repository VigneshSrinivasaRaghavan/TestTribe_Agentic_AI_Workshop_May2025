from __future__ import annotations
import os
from typing import Any, Dict
from src.core.utils import http_post_json

SLACK_BASE = os.getenv("SLACK_BASE", "http://localhost:4003")
SLACK_DEFAULT_CHANNEL = os.getenv("SLACK_DEFAULT_CHANNEL", "qa-reports")
SLACK_BEARER = os.getenv("SLACK_BEARER") or "demo-token"

def post_message(text: str, channel: str | None = None) -> Dict[str, Any]:
    url = f"{SLACK_BASE}/api/chat.postMessage"
    payload = {
        "channel": channel or SLACK_DEFAULT_CHANNEL,
        "text": text,
    }
    headers = {"Authorization": f"Bearer {SLACK_BEARER}"}
    return http_post_json(url, payload, headers=headers)