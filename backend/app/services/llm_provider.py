"""
LLM provider abstraction.

Everything in SAIRA that talks to a language model goes through `llm_provider`.
Provider-specific code lives here and nowhere else, so switching Groq for
Bedrock is a config change rather than a refactor.

Two implementations:

* `GroqProvider` — delegates to the existing `groq_service` singleton. That
  module carries hard-won behaviour (reasoning-block sanitisation, the
  finish_reason="length" budget retry, per-day vs per-minute 429 handling) and
  this wrapper deliberately does not reimplement any of it.
* `BedrockProvider` — the AWS deployment target. Uses the Anthropic SDK's
  Bedrock client rather than raw `bedrock-runtime`.

`LLMError` is an alias of `GroqServiceError` rather than a new exception type.
Every caller and every test already catches that name, and introducing a
parallel hierarchy would mean touching error handling in endpoints this
migration is otherwise not changing.

ponytail: no retry/backoff layer here — the Groq path already has one and
botocore has its own. Add a shared one only if a third provider appears.
"""

from __future__ import annotations

import json
import logging
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional

from app.core.config import settings
from app.services.groq_service import GroqServiceError, clean_model_response, groq_service

logger = logging.getLogger(__name__)

#: Callers catch this. It is the same class the pre-migration code raised.
LLMError = GroqServiceError


class LLMProvider(ABC):
    """Text in, text out. Messages use the OpenAI-style role/content shape
    the rest of the application already builds."""

    name: str = "abstract"

    @abstractmethod
    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """Return the assistant's user-facing text."""

    @abstractmethod
    async def generate_json(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        """Return parsed JSON. Raises LLMError if the reply is not JSON."""

    @abstractmethod
    def model_for(self, role: str) -> str:
        """Resolve a logical role (`primary` | `extraction`) to a model id."""


def _parse_json_reply(raw: str) -> Dict[str, Any]:
    """Strip markdown fences and parse. Shared by every provider so JSON
    handling cannot diverge between them."""
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        lines = lines[1:-1] if lines[-1].strip() == "```" else lines[1:]
        cleaned = "\n".join(lines).strip()
    try:
        return json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise LLMError(
            f"Model response was not valid JSON. Raw (truncated): {raw[:200]}"
        ) from exc


class GroqProvider(LLMProvider):
    """Delegates to `groq_service`, which stays the single Groq client."""

    name = "groq"

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        return await groq_service.chat_complete(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    async def generate_json(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        return await groq_service.chat_complete_json(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )

    def model_for(self, role: str) -> str:
        if role == "extraction":
            return settings.GROQ_EXTRACTION_MODEL
        return settings.GROQ_PRIMARY_MODEL


class BedrockProvider(LLMProvider):
    """Claude on Amazon Bedrock, via the Anthropic SDK's Bedrock client.

    NOT EXERCISED BY THIS MIGRATION — there are no AWS credentials in this
    environment, so it has never made a live call. It is here because §11 and
    §20 of the migration brief name Bedrock as the deployment direction, and
    because writing it now is what proves the abstraction is real rather than
    a single-implementation interface. Treat it as unverified until someone
    runs it against a real account.
    """

    name = "bedrock"

    def __init__(self) -> None:
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        if self._client is None:
            try:
                from anthropic import AnthropicBedrockMantle  # type: ignore
            except ImportError as exc:
                raise LLMError(
                    "LLM_PROVIDER=bedrock requires the anthropic SDK. "
                    "Install it (pip install anthropic) or set LLM_PROVIDER=groq."
                ) from exc
            self._client = AnthropicBedrockMantle(aws_region=settings.BEDROCK_REGION)
        return self._client

    @staticmethod
    def _split_system(messages: List[Dict[str, str]]) -> tuple[str, List[Dict[str, str]]]:
        """Anthropic takes the system prompt as its own parameter, while the
        rest of SAIRA builds an OpenAI-style array with a leading system role."""
        system_parts: List[str] = []
        turns: List[Dict[str, str]] = []
        for m in messages:
            if m.get("role") == "system":
                system_parts.append(m.get("content", ""))
            else:
                turns.append({"role": m["role"], "content": m.get("content", "")})
        if not turns:
            # The API requires at least one user turn.
            turns = [{"role": "user", "content": "Proceed."}]
        return "\n\n".join(p for p in system_parts if p), turns

    async def generate(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        client = self._get_client()
        system, turns = self._split_system(messages)
        try:
            response = await client.messages.create(
                model=model,
                max_tokens=max_tokens,
                system=system or None,
                messages=turns,
            )
        except Exception as exc:
            raise LLMError(f"Bedrock request failed: {exc}") from exc

        text = "".join(b.text for b in response.content if getattr(b, "type", None) == "text")
        if not text.strip():
            raise LLMError(
                f"Bedrock returned no text (stop_reason={getattr(response, 'stop_reason', None)!r})."
            )
        # Same sanitisation the Groq path applies, so callers above cannot tell
        # the providers apart.
        return clean_model_response(text)

    async def generate_json(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 4096,
    ) -> Dict[str, Any]:
        raw = await self.generate(
            model=model, messages=messages,
            temperature=temperature, max_tokens=max_tokens,
        )
        return _parse_json_reply(raw)

    def model_for(self, role: str) -> str:
        if role == "extraction":
            return settings.BEDROCK_EXTRACTION_MODEL
        return settings.BEDROCK_PRIMARY_MODEL


def _build_provider() -> LLMProvider:
    provider = (settings.LLM_PROVIDER or "groq").lower()
    if provider == "bedrock":
        logger.info("llm_provider=bedrock region=%s", settings.BEDROCK_REGION)
        return BedrockProvider()
    if provider != "groq":
        raise LLMError(f"Unknown LLM_PROVIDER: {provider!r}")
    logger.info("llm_provider=groq")
    return GroqProvider()


llm_provider: LLMProvider = _build_provider()
