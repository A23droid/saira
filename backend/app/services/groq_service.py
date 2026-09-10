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


# Hard ceiling for the single budget retry below.
_MAX_TOKEN_CEILING = 8192


class GroqServiceError(Exception):
    """Raised for any error from the Groq service layer."""
    pass


# ── Evaluation-mode payload logging ───────────────────────────────────────────

def _log_llm_payload(
    model: str,
    messages: List[Dict[str, str]],
    temperature: float,
    max_tokens: int,
) -> None:
    """Log the exact messages sent to the model, immediately before the call.

    Enabled only by SAIRA_LOG_LLM_PAYLOAD / SAIRA_EVAL_MODE. This is the single
    point where the final payload can be observed, which is what makes claims
    about "what the model actually saw" checkable rather than assumed.

    Only the message array is logged — never the API key, which lives on the
    client object and is never part of `messages`.
    """
    if not (settings.SAIRA_LOG_LLM_PAYLOAD or settings.SAIRA_EVAL_MODE):
        return
    try:
        payload = {
            "model": model,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "message_count": len(messages),
            "total_chars": sum(len(m.get("content", "")) for m in messages),
            "messages": [
                {"role": m.get("role"), "content": m.get("content", "")}
                for m in messages
            ],
        }
        logger.info("LLM_PAYLOAD %s", json.dumps(payload, ensure_ascii=False))
    except Exception as exc:  # never let debug logging break a request
        logger.debug("Failed to log LLM payload: %s", exc)


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
        _allow_budget_retry: bool = True,
    ) -> str:
        """
        Send a chat completion request to Groq.

        Returns:
            The cleaned, user-facing assistant message content (reasoning stripped).

        Raises:
            GroqServiceError: On API errors, rate limits, timeouts, or config issues.
        """
        client = self._get_client()
        _log_llm_payload(model, messages, temperature, max_tokens)
        try:
            response = await client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens,
            )
            choice = response.choices[0]
            content = choice.message.content
            finish_reason = getattr(choice, "finish_reason", None)

            if not content:
                # `openai/gpt-oss-120b` is a reasoning model: its chain of
                # thought is billed against max_tokens and returned in a
                # separate `reasoning` field. If the budget is exhausted while
                # still reasoning, the API returns finish_reason="length" with
                # an EMPTY content string — a successful HTTP 200 that carries
                # no answer. Reporting that as a bare "empty response" hid the
                # cause, so distinguish it and say what to do about it.
                if finish_reason == "length":
                    reasoning = getattr(choice.message, "reasoning", None) or ""
                    # Retry once with a doubled budget. Bounded to a single
                    # extra attempt so a pathological prompt fails loudly
                    # instead of looping and burning quota.
                    if _allow_budget_retry and max_tokens < _MAX_TOKEN_CEILING:
                        retry_budget = min(max_tokens * 2, _MAX_TOKEN_CEILING)
                        logger.warning(
                            "Empty content (finish_reason=length, reasoning_chars=%d); "
                            "retrying once with max_tokens=%d",
                            len(reasoning), retry_budget,
                        )
                        return await self.chat_complete(
                            model=model,
                            messages=messages,
                            temperature=temperature,
                            max_tokens=retry_budget,
                            _allow_budget_retry=False,
                        )
                    raise GroqServiceError(
                        "Model exhausted its token budget while reasoning and "
                        f"returned no answer (finish_reason=length, "
                        f"max_tokens={max_tokens}, reasoning_chars={len(reasoning)}). "
                        "Raise max_tokens for this task."
                    )
                raise GroqServiceError(
                    f"Groq returned an empty response (finish_reason={finish_reason!r})."
                )

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
                # Distinguish the per-minute ceiling (wait and retry) from the
                # per-day quota (retrying is futile until the window rolls).
                # Collapsing both into one message made an exhausted daily
                # budget look like transient throttling.
                if "per day" in exc_str.lower() or "tpd" in exc_str.lower():
                    raise GroqServiceError(
                        "Groq daily token quota (TPD) exhausted for this "
                        f"account. Retrying will not help until it resets. "
                        f"Provider detail: {exc_str[:300]}"
                    ) from exc
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
        max_tokens: int = 4096,
        _allow_truncation_retry: bool = True,
    ) -> Dict[str, Any]:
        """
        Like chat_complete but expects JSON output and parses + validates it.
        Reasoning blocks are stripped before JSON parsing.

        A reply that does not close its top-level object was cut off by the
        token budget, not malformed by the model. `chat_complete` only retries
        when the budget is exhausted before ANY content is produced; a
        half-written JSON object is a successful call whose output happens to
        be unusable, so it needs its own retry. Without it the caller sees
        "not valid JSON" and has no way to tell a truncation from a model that
        genuinely cannot follow the schema.

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
            truncated = bool(cleaned) and not cleaned.rstrip().endswith(("}", "]"))
            if truncated and _allow_truncation_retry and max_tokens < _MAX_TOKEN_CEILING:
                retry_budget = min(int(max_tokens * 1.6), _MAX_TOKEN_CEILING)
                logger.warning(
                    "JSON reply truncated at max_tokens=%d (%d chars, no closing "
                    "brace); retrying once with max_tokens=%d",
                    max_tokens, len(cleaned), retry_budget,
                )
                return await self.chat_complete_json(
                    model=model,
                    messages=messages,
                    temperature=temperature,
                    max_tokens=retry_budget,
                    _allow_truncation_retry=False,
                )
            logger.warning("Groq returned non-JSON: %s", raw[:200])
            hint = " (reply appears truncated — raise max_tokens)" if truncated else ""
            raise GroqServiceError(
                f"Groq response was not valid JSON{hint}. Raw (truncated): {raw[:200]}"
            ) from exc


# Module-level singleton — imported by the AI Router
groq_service = GroqService()
