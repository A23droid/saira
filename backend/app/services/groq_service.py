"""
Centralized Groq API client.

This is the ONLY place in SAIRA that initializes and calls the Groq SDK.
All other services go through this module — never call Groq directly elsewhere.

Responsibilities:
- Load API key and model IDs from settings (never hardcoded)
- Send chat completion requests
- Sanitize model responses (remove <think> / <analysis> blocks)
- Handle all Groq/network errors and normalize them
- Expose a clean async interface to the AI Router
"""

import json
import logging
import re
from typing import Any, Dict, List, Optional, Tuple

from app.core.config import settings

logger = logging.getLogger(__name__)

# ── Reasoning Block Sanitizer ─────────────────────────────────────────────────

# Tags that models may use for internal reasoning that must never reach the user.
_REASONING_TAGS = ["think", "analysis", "reasoning", "internal", "scratchpad"]
_REASONING_PATTERN = re.compile(
    r"<(?:" + "|".join(_REASONING_TAGS) + r")>.*?</(?:" + "|".join(_REASONING_TAGS) + r")>",
    re.DOTALL | re.IGNORECASE,
)


def clean_model_response(text: str) -> str:
    """
    Remove all internal reasoning blocks from a model response.

    Handles:
    - <think>...</think>
    - <analysis>...</analysis>
    - <reasoning>...</reasoning>
    - Any equivalent block listed in _REASONING_TAGS
    - Multiple occurrences, in any order relative to the answer
    - Reasoning blocks that appear before OR after the final answer

    Returns only the user-facing answer with surrounding whitespace stripped.

    Examples:
        "<think>reasoning</think>\\nFinal answer." -> "Final answer."
        "Final answer.\\n<think>reasoning</think>" -> "Final answer."
        "<think>r1</think>Answer.<think>r2</think>" -> "Answer."
        "Plain answer." -> "Plain answer."
    """
    cleaned = _REASONING_PATTERN.sub("", text)
    # Collapse runs of blank lines left behind after stripping blocks
    cleaned = re.sub(r"\n{3,}", "\n\n", cleaned)
    return cleaned.strip()


class GroqServiceError(Exception):
    """Raised for any error from the Groq service layer."""
    pass


class GroqService:
    """
    Thin async wrapper around the Groq Python SDK.
    Uses lazy initialization so the app boots even without an API key set,
    and the missing-key error surfaces only when AI features are called.
    """

    def __init__(self) -> None:
        self._client: Optional[Any] = None

    def _get_client(self) -> Any:
        """Lazily initialize and return the Groq client."""
        if not settings.GROQ_API_KEY:
            raise GroqServiceError(
                "GROQ_API_KEY is not configured. Set it in .env to enable AI features."
            )
        if self._client is None:
            try:
                from groq import AsyncGroq  # type: ignore
                self._client = AsyncGroq(api_key=settings.GROQ_API_KEY)
            except ImportError as exc:
                raise GroqServiceError(
                    "The 'groq' package is not installed. Run: pip install groq"
                ) from exc
        return self._client

    async def chat_complete(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        max_tokens: int = 2048,
    ) -> str:
        """
        Send a chat completion request to Groq.

        Returns:
            The cleaned, user-facing assistant message content (reasoning stripped).

        Raises:
            GroqServiceError: On API errors, rate limits, timeouts, or config issues.
        """
        client = self._get_client()
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            content = response.choices[0].message.content
            if not content:
                raise GroqServiceError("Groq returned an empty response.")
            # ── Sanitize at the provider boundary ──────────────────────────────
            # Remove any <think>/<analysis>/etc. blocks before the content
            # ever leaves this service. The AI Router and all callers above
            # receive only the cleaned, user-facing text.
            return clean_model_response(content)
        except GroqServiceError:
            raise
        except Exception as exc:
            exc_str = str(exc)
            if "429" in exc_str or "rate_limit" in exc_str.lower():
                raise GroqServiceError(
                    "Groq rate limit reached. Please wait and try again."
                ) from exc
            if "401" in exc_str or "invalid_api_key" in exc_str.lower():
                raise GroqServiceError(
                    "Invalid GROQ_API_KEY. Check your .env configuration."
                ) from exc
            if "timeout" in exc_str.lower():
                raise GroqServiceError(
                    "Groq request timed out. Please try again."
                ) from exc
            logger.error("Groq API error: %s", exc_str)
            raise GroqServiceError(f"Groq API error: {exc_str}") from exc

    async def chat_complete_json(
        self,
        model: str,
        messages: List[Dict[str, str]],
        temperature: float = 0.2,
        max_tokens: int = 2048,
    ) -> Dict[str, Any]:
        """
        Like chat_complete but expects JSON output and parses + validates it.
        Reasoning blocks are stripped before JSON parsing.

        Returns:
            Parsed JSON dict.

        Raises:
            GroqServiceError: If the response cannot be parsed as JSON.
        """
        raw = await self.chat_complete(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
        )
        # chat_complete already ran clean_model_response; strip markdown fences next
        cleaned = raw
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            if lines[-1].strip() == "```":
                lines = lines[1:-1]
            else:
                lines = lines[1:]
            cleaned = "\n".join(lines).strip()

        try:
            return json.loads(cleaned)
        except json.JSONDecodeError as exc:
            logger.warning("Groq returned non-JSON: %s", raw[:200])
            raise GroqServiceError(
                f"Groq response was not valid JSON. Raw (truncated): {raw[:200]}"
            ) from exc


# Module-level singleton — imported by the AI Router
groq_service = GroqService()
