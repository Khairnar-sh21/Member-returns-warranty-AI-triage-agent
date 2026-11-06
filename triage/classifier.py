"""AI classifier: turns a member's message into a validated LLMClassification.

Flow:
  1. Send the versioned prompt + message to the configured provider.
  2. Validate the JSON against the pydantic schema.
  3. If invalid, retry ONCE, telling the model exactly what was wrong.
  4. Rate limits / outages get one retry after a short wait; a bad API key
     does not.
  5. If still invalid (or the provider fails), return a safe fallback with
     confidence 0. The rules engine then escalates the case to a human, so an
     AI failure can never auto-approve anything.

The AI only sees the message text, never the member's account data, so it has
nothing to base an eligibility decision on even if it tried.
"""

from __future__ import annotations

import json
import time
from functools import lru_cache
from typing import Literal

from pydantic import BaseModel, ValidationError

from triage.config import PROJECT_ROOT
from triage.llm import LLMError, LLMProvider
from triage.schemas import LLMClassification

PROMPT_VERSION = "classifier_v1"
PROMPT_PATH = PROJECT_ROOT / "prompts" / f"{PROMPT_VERSION}.md"
MAX_MESSAGE_CHARS = 2000
TRANSIENT_ERRORS = {"rate_limited", "unavailable"}
TRANSIENT_RETRY_DELAY_SECONDS = 8.0

FRIENDLY_ERRORS = {
    "rate_limited": "The AI service is busy right now (free-tier rate limit).",
    "auth": "The AI service rejected the API key.",
    "unavailable": "The AI service couldn't be reached.",
    "bad_request": "The AI service rejected the request (check the model name).",
    "invalid_output": "The AI returned an unreadable answer twice.",
}


class ClassificationResult(BaseModel):
    classification: LLMClassification
    status: Literal["ok", "retried", "fallback"]
    attempts: int
    provider: str
    model: str
    prompt_version: str
    latency_ms: int
    error_kind: str | None = None
    error: str | None = None
    error_detail: str | None = None  # raw provider message, for logs only
    raw_responses: list[str] = []


@lru_cache(maxsize=1)
def load_prompt() -> str:
    return PROMPT_PATH.read_text()


@lru_cache(maxsize=1)
def response_schema() -> dict:
    """JSON schema sent to the model: every field required, facts as strings."""
    schema = LLMClassification.model_json_schema()
    schema.pop("title", None)
    for prop in schema["properties"].values():
        prop.pop("title", None)
        prop.pop("default", None)
    schema["properties"]["extracted_facts"] = {
        "type": "object",
        "additionalProperties": {"type": "string"},
    }
    schema["required"] = list(schema["properties"])
    return schema


def parse_response(raw: str) -> LLMClassification:
    """Validate the model's text as an LLMClassification (tolerates ```json fences)."""
    text = raw.strip()
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end < start:
        raise ValueError("Response did not contain a JSON object.")
    return LLMClassification.model_validate_json(text[start : end + 1])


def fallback_classification(reason: str) -> LLMClassification:
    return LLMClassification(
        category="other",
        sub_category="unclassified",
        sentiment="neutral",
        urgency="normal",
        extracted_facts={},
        member_already_troubleshot=False,
        confidence=0.0,
        reasoning_summary=f"AI classification unavailable ({reason}). Routed to a human.",
    )


def _user_content(message: str) -> str:
    return f"<member_message>\n{message}\n</member_message>"


def _retry_content(message: str, bad_response: str, error: str) -> str:
    return (
        f"{_user_content(message)}\n\n"
        f"Your previous response was not valid:\n{bad_response[:1500]}\n\n"
        f"Validation error: {error}\n"
        "Return ONLY a corrected JSON object that matches the schema."
    )


def _short_error(exc: Exception) -> str:
    if isinstance(exc, ValidationError):
        return "; ".join(
            f"{'.'.join(str(p) for p in e['loc']) or 'response'}: {e['msg']}" for e in exc.errors()
        )
    return str(exc)


def classify(message: str, provider: LLMProvider) -> ClassificationResult:
    message = message.strip()
    if not message:
        raise ValueError("Message is empty.")
    message = message[:MAX_MESSAGE_CHARS]

    system, schema = load_prompt(), response_schema()
    started = time.perf_counter()
    raw_responses: list[str] = []

    calls = 0

    def result(classification, status, error_kind=None, detail=None) -> ClassificationResult:
        return ClassificationResult(
            classification=classification,
            status=status,
            attempts=calls,
            provider=provider.name,
            model=provider.model,
            prompt_version=PROMPT_VERSION,
            latency_ms=int((time.perf_counter() - started) * 1000),
            error_kind=error_kind,
            error=FRIENDLY_ERRORS.get(error_kind) if error_kind else None,
            error_detail=detail,
            raw_responses=raw_responses,
        )

    def call(user: str) -> str:
        nonlocal calls
        try:
            calls += 1
            return provider.complete_json(system, user, schema)
        except LLMError as exc:
            if exc.kind not in TRANSIENT_ERRORS:
                raise
            time.sleep(TRANSIENT_RETRY_DELAY_SECONDS)
            calls += 1
            return provider.complete_json(system, user, schema)

    user = _user_content(message)
    for attempt in (1, 2):
        try:
            raw = call(user)
        except LLMError as exc:
            return result(fallback_classification(FRIENDLY_ERRORS[exc.kind]), "fallback",
                          exc.kind, str(exc)[:500])
        raw_responses.append(raw)
        try:
            classification = parse_response(raw)
            return result(classification, "ok" if attempt == 1 else "retried")
        except (ValidationError, ValueError, json.JSONDecodeError) as exc:
            user = _retry_content(message, raw, _short_error(exc))

    return result(
        fallback_classification(FRIENDLY_ERRORS["invalid_output"]), "fallback", "invalid_output"
    )
