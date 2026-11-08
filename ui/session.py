"""Session state: mode, live-call limits, and triage history."""

from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone

import streamlit as st

from triage.llm import LLMError, LLMProvider, get_provider
from triage.pipeline import TriageResult
from ui.settings import LIVE_CALLS_PER_DAY, LIVE_CALLS_PER_SESSION

log = logging.getLogger(__name__)


@st.cache_resource
def provider() -> LLMProvider | None:
    try:
        return get_provider()
    except LLMError:
        log.exception("LLM provider misconfigured; falling back to demo mode")
        return None


@st.cache_resource
def _daily_counter() -> dict:
    """Shared by every visitor of this server process."""
    return {"day": None, "count": 0, "lock": threading.Lock()}


def _today_utc() -> str:
    return datetime.now(timezone.utc).date().isoformat()


def init() -> None:
    st.session_state.setdefault("mode", "demo")  # live is opt-in to protect the free quota
    st.session_state.setdefault("live_used", 0)
    st.session_state.setdefault("history", [])
    st.session_state.setdefault("result", None)
    st.session_state.setdefault("notice", None)


def live_available() -> bool:
    return provider() is not None


def is_live() -> bool:
    return st.session_state.mode == "live" and live_available()


def session_remaining() -> int:
    return max(0, LIVE_CALLS_PER_SESSION - st.session_state.live_used)


def daily_remaining() -> int:
    counter = _daily_counter()
    if counter["day"] != _today_utc():
        return LIVE_CALLS_PER_DAY
    return max(0, LIVE_CALLS_PER_DAY - counter["count"])


def try_consume_live_call() -> str | None:
    """Reserve one live call. Returns a friendly message if a limit is reached."""
    if session_remaining() <= 0:
        return (f"You've used all {LIVE_CALLS_PER_SESSION} live AI calls for this session. "
                "Switch to Demo mode to keep exploring the sample scenarios.")
    counter = _daily_counter()
    with counter["lock"]:
        today = _today_utc()
        if counter["day"] != today:
            counter["day"], counter["count"] = today, 0
        if counter["count"] >= LIVE_CALLS_PER_DAY:
            return ("The demo has reached its daily limit of live AI calls. Demo mode still works, "
                    "and live mode resets at 00:00 UTC.")
        counter["count"] += 1
    st.session_state.live_used += 1
    return None


def record(result: TriageResult) -> None:
    st.session_state.result = result
    st.session_state.history.append(result)
