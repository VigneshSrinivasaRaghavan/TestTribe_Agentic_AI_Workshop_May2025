"""
Core LLM client (thin wrapper).

This module provides a single high-level function `chat(messages)` used by
agents to call an LLM provider and return assistant text. The implementation
keeps things intentionally small for Day‑1 teaching: it supports two providers
(`ollama` and `openai`) via a provider switch driven by environment
variables (loaded from `.env`).

Design goals (Day-1):
- Minimal, readable code students can extend.
- Provider-agnostic caller API: callers pass OpenAI-style `messages` and get
  back assistant text.
- Avoid advanced per-model knobs (e.g., `temperature`) to reduce student
  friction and 400/compatibility errors during demos.

Environment configuration (loaded via `python-dotenv`):
- `PROVIDER` (default: "ollama") — which provider to use. Values: "ollama" or "openai".
- `MODEL` — model id to request (e.g. `gpt-4o-mini`, `gpt-5-nano`, or `mistral:latest`).
- `OLLAMA_HOST` — base URL for local Ollama (default: `http://localhost:11434`).
- `OPENAI_API_KEY` — required when `PROVIDER=openai`.
- `LLM_TIMEOUT_S` — request timeout in seconds (default: 60).

Usage (examples):

```py
from src.core import chat

messages = [
    {"role": "system", "content": "You are a helpful QA assistant."},
    {"role": "user", "content": "Summarize the requirement"},
]
out = chat(messages)
```

The function returns the assistant's text (string). For JSON outputs the
caller should validate/parse the returned text (see `src.core.utils` helpers
for parsing and cleanup).
"""

from __future__ import annotations
import os
from typing import List, Dict
import httpx
from dotenv import load_dotenv
from langchain_openai import ChatOpenAI
from langchain_ollama import ChatOllama
from langchain.schema import SystemMessage, HumanMessage, AIMessage
import logging

import logging

# Visibility / logging flags (class-friendly defaults)
LLM_LOG = os.getenv("LLM_LOG", "1").strip().lower() in ("1", "true", "yes")
LLM_DEBUG = os.getenv("LLM_DEBUG", "0").strip().lower() in ("1", "true", "yes")

# module logger (agents should configure logging.basicConfig in their entrypoints)
logger = logging.getLogger(__name__)

load_dotenv(override=True)

PROVIDER = (os.getenv("PROVIDER") or "ollama").strip().lower()
MODEL = (os.getenv("MODEL") or "mistral:latest").strip()
OLLAMA_HOST = (os.getenv("OLLAMA_HOST") or "http://localhost:11434").strip()
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY") or ""
TIMEOUT_S = int(os.getenv("LLM_TIMEOUT_S") or "60")
# No temperature handling for Day-1: keep payloads simple and compatible.
LLM_TEMPERATURE = None

Message = Dict[str, str]

def _to_lc_messages(messages: List[Message]):
    """Convert [{'role','content'}] into LangChain BaseMessages."""
    lc_msgs = []
    for m in messages:
        role = (m.get("role") or "").lower()
        content = m.get("content") or ""
        if role == "system":
            lc_msgs.append(SystemMessage(content=content))
        elif role == "assistant":
            lc_msgs.append(AIMessage(content=content))
        else:
            # treat 'user' and anything else as human input
            lc_msgs.append(HumanMessage(content=content))
    return lc_msgs

def _make_llm():
    """
    Create the LangChain chat model according to PROVIDER/MODEL envs.

    Note: We do NOT pass a `timeout` kwarg here for maximum compatibility
    across LangChain versions/backends (e.g., ChatOllama often has no such arg).
    """
    if PROVIDER == "ollama":
        # LangChain's Ollama wrapper reads OLLAMA_HOST from env.
        os.environ["OLLAMA_HOST"] = OLLAMA_HOST
        return ChatOllama(model=MODEL)
    elif PROVIDER == "openai":
        if not OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is missing but PROVIDER=openai.")
        # Keep temperature=0 for deterministic teaching runs
        return ChatOpenAI(model=MODEL, temperature=0)
    else:
        raise NotImplementedError("Unsupported PROVIDER. Use 'ollama' or 'openai'.")

def chat(messages: List[Message], timeout: int = TIMEOUT_S) -> str:
    if not isinstance(messages, list) or not messages:
        raise ValueError("messages must be a non-empty list of {'role','content'} dicts.")

    # ---- progress: start
    if LLM_LOG:
        n_sys = sum(1 for m in messages if (m.get("role") or "").lower() == "system")
        n_usr = sum(1 for m in messages if (m.get("role") or "").lower() in ("user", "human"))
        n_ast = sum(1 for m in messages if (m.get("role") or "").lower() in ("assistant", "ai"))
        msg_count = len(messages)

        size_info = ""
        if LLM_DEBUG:
            lengths = [len(m.get("content") or "") for m in messages]
            size_info = f" | chars={sum(lengths)} total, per_msg={lengths}"

        logger.info(
            "[LLM] ▶ start provider=%s model=%s msgs=%d (sys=%d, user=%d, asst=%d)%s",
            PROVIDER,
            MODEL,
            msg_count,
            n_sys,
            n_usr,
            n_ast,
            size_info,
        )

    # ---- call model
    import time
    t0 = time.perf_counter()
    llm = _make_llm()
    lc_msgs = _to_lc_messages(messages)

    try:
        resp = llm.invoke(lc_msgs)
        out = getattr(resp, "content", "") or ""
        dt = time.perf_counter() - t0
        if LLM_LOG:
            logger.info("[LLM] ✔ done in %.2fs", dt)
        if LLM_DEBUG:
            logger.debug("[LLM] response length=%d", len(out))
        return out
    except Exception as e:
        dt = time.perf_counter() - t0
        # log exception with stacktrace
        logger.exception("[LLM] ✖ error after %.2fs: %s", dt, type(e).__name__)
        raise
