"""LLM provider adapters.

The classifier talks to one tiny interface (`complete_json`), so the AI vendor
is a configuration choice, not an architectural one. Gemini is the default
(free tier); Anthropic is available with LLM_PROVIDER=anthropic.
"""

from __future__ import annotations

import json
import os
from typing import Literal, Protocol

from dotenv import load_dotenv

from triage.config import PROJECT_ROOT

load_dotenv(PROJECT_ROOT / ".env")

TIMEOUT_SECONDS = 30
DEFAULT_MODELS = {"gemini": "gemini-3.5-flash-lite", "anthropic": "claude-sonnet-5-5"}
KEY_NAMES = {"gemini": "GEMINI_API_KEY", "anthropic": "ANTHROPIC_API_KEY"}

ErrorKind = Literal["rate_limited", "auth", "unavailable", "bad_request"]


class LLMError(RuntimeError):
    """Provider failure, translated into something the UI can explain."""

    def __init__(self, kind: ErrorKind, message: str) -> None:
        super().__init__(message)
        self.kind = kind


class LLMProvider(Protocol):
    name: str
    model: str

    def complete_json(self, system: str, user: str, schema: dict) -> str: ...


def get_setting(name: str, default: str | None = None) -> str | None:
    """Environment / .env first (local), then Streamlit secrets (deployed)."""
    value = os.environ.get(name)
    if value:
        return value
    try:
        import streamlit as st

        value = st.secrets.get(name)
    except Exception:  # no secrets file, or not running under Streamlit
        value = None
    return value or default


class GeminiProvider:
    name = "gemini"

    def __init__(self, api_key: str, model: str) -> None:
        from google import genai
        from google.genai import types

        self.model = model
        self._types = types
        self._client = genai.Client(
            api_key=api_key, http_options=types.HttpOptions(timeout=TIMEOUT_SECONDS * 1000)
        )

    def complete_json(self, system: str, user: str, schema: dict) -> str:
        from google.genai import errors

        config = self._types.GenerateContentConfig(
            system_instruction=system,
            response_mime_type="application/json",
            response_json_schema=schema,
            temperature=0,
        )
        try:
            response = self._client.models.generate_content(
                model=self.model, contents=user, config=config
            )
        except errors.APIError as exc:
            raise _http_error(exc.code, str(exc)) from exc
        except Exception as exc:
            raise LLMError("unavailable", f"Could not reach Gemini: {exc}") from exc
        return response.text or ""


class AnthropicProvider:
    name = "anthropic"

    def __init__(self, api_key: str, model: str) -> None:
        import anthropic

        self.model = model
        self._anthropic = anthropic
        self._client = anthropic.Anthropic(api_key=api_key, timeout=TIMEOUT_SECONDS)

    def complete_json(self, system: str, user: str, schema: dict) -> str:
        a = self._anthropic
        system_with_schema = f"{system}\n\nJSON schema:\n{json.dumps(schema)}"
        try:
            message = self._client.messages.create(
                model=self.model,
                max_tokens=1024,
                temperature=0,
                system=system_with_schema,
                messages=[{"role": "user", "content": user}],
            )
        except a.RateLimitError as exc:
            raise LLMError("rate_limited", str(exc)) from exc
        except (a.AuthenticationError, a.PermissionDeniedError) as exc:
            raise LLMError("auth", str(exc)) from exc
        except (a.BadRequestError, a.NotFoundError) as exc:
            raise LLMError("bad_request", str(exc)) from exc
        except a.APIError as exc:
            raise LLMError("unavailable", str(exc)) from exc
        return "".join(block.text for block in message.content if block.type == "text")


def _http_error(code: int | None, message: str) -> LLMError:
    if code == 429:
        return LLMError("rate_limited", message)
    if code in (401, 403):
        return LLMError("auth", message)
    if code in (400, 404):
        return LLMError("bad_request", message)
    return LLMError("unavailable", message)


def get_provider() -> LLMProvider | None:
    """The configured provider, or None when no API key is set (→ demo mode)."""
    name = (get_setting("LLM_PROVIDER", "gemini") or "gemini").strip().lower()
    if name not in KEY_NAMES:
        raise LLMError("bad_request", f"Unknown LLM_PROVIDER '{name}'. Use gemini or anthropic.")
    api_key = get_setting(KEY_NAMES[name])
    if not api_key:
        return None
    model = get_setting(f"{name.upper()}_MODEL", DEFAULT_MODELS[name])
    provider_cls = GeminiProvider if name == "gemini" else AnthropicProvider
    return provider_cls(api_key=api_key, model=model)
