from __future__ import annotations
import os
from typing import Any, Dict
from src.core.utils import http_post_json

JIRA_BASE = os.getenv("JIRA_BASE", "http://localhost:4001")
JIRA_PROJECT_KEY = os.getenv("JIRA_PROJECT_KEY", "QA")
JIRA_BEARER = os.getenv("JIRA_BEARER") or "demo-token"

def create_issue(summary: str, description: str, issuetype: str = "Bug") -> Dict[str, Any]:
    url = f"{JIRA_BASE}/rest/api/3/issue"
    payload = {
        "fields": {
            "project": {"key": JIRA_PROJECT_KEY},
            "summary": summary,
            "description": description,
            "issuetype": {"name": issuetype},
        }
    }
    headers = {"Authorization": f"Bearer {JIRA_BEARER}"}
    return http_post_json(url, payload, headers=headers)