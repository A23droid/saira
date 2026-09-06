"""
Token-budget pacing for evaluation runs.

Groq enforces a tokens-per-minute ceiling (8,000 TPM on the free tier). A full
evaluation issues dozens of calls with ~2,000-token prompts, so firing them
back to back exhausts the budget in seconds and every subsequent call fails
with a rate-limit error — which looks exactly like a broken pipeline in the
results.

This throttle spaces calls so the run stays inside the budget. It changes ONLY
timing: the model, the prompts, the parameters, and the responses are
untouched, so the pipeline under test is still the production one. It is
installed only in evaluation mode.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class TokenBucket:
    """Sliding-window limiter over estimated tokens per minute."""

    def __init__(self, tokens_per_minute: int = 8000, safety_factor: float = 0.95):
        # Stay under the ceiling: token estimates are approximate and the
        # response also counts against the budget.
        self.budget = int(tokens_per_minute * safety_factor)
        self.window = 60.0
        self._events: List[tuple[float, int]] = []
        self._lock = asyncio.Lock()

    def _prune(self, now: float) -> None:
        cutoff = now - self.window
        self._events = [(t, n) for t, n in self._events if t > cutoff]

    async def acquire(self, tokens: int) -> float:
        """Block until `tokens` fit in the window. Returns seconds waited."""
        waited = 0.0
        # A single call larger than the whole budget can never "fit". Cap the
        # reservation so such a call proceeds after one window instead of
        # waiting forever — the provider, not the estimate, is the authority.
        tokens = min(tokens, self.budget)
        async with self._lock:
            while True:
                now = time.monotonic()
                self._prune(now)
                used = sum(n for _, n in self._events)
                if used + tokens <= self.budget or not self._events:
                    self._events.append((now, tokens))
                    return waited
                oldest = self._events[0][0]
                sleep_for = max(0.5, (oldest + self.window) - now)
                logger.info(
                    "Rate-limit pacing: waiting %.1fs (window usage %d + %d > %d)",
                    sleep_for, used, tokens, self.budget,
                )
                await asyncio.sleep(sleep_for)
                waited += sleep_for


def estimate_tokens(messages: List[Dict[str, str]], max_tokens: int) -> int:
    """Rough prompt+completion token estimate (~4 chars/token)."""
    prompt_chars = sum(len(m.get("content", "")) for m in messages)
    prompt_tokens = prompt_chars // 4
    # Groq reserves the FULL `max_tokens` against the per-minute budget at
    # admission time — not the tokens actually generated. Estimating from
    # expected output therefore under-counts badly and trips the limit even
    # when real usage is small. Count the whole reservation.
    return prompt_tokens + max_tokens


_installed = False


def install(tokens_per_minute: int = 8000) -> None:
    """Wrap `groq_service.chat_complete` with the pacer. Idempotent.

    Wrapping the single client entry point covers every caller — the router,
    the concept service, and the harness's own question generation — without
    any of them knowing about pacing.
    """
    global _installed
    if _installed:
        return

    from app.services import groq_service as gs

    bucket = TokenBucket(tokens_per_minute)
    original = gs.groq_service.chat_complete

    async def paced(model, messages, temperature=0.3, max_tokens=2048, **kwargs):
        """Pace, and treat a rate-limit rejection as backpressure, not a failure.

        Token accounting is an estimate, so the bucket can still be overtaken
        by the provider's own counter. When that happens the correct response
        is to wait for the window to roll over and retry — reporting it as a
        pipeline error would mean recording a provider quota limit as a SAIRA
        defect.
        """
        last_exc = None
        for attempt in range(4):
            await bucket.acquire(estimate_tokens(messages, max_tokens))
            try:
                return await original(
                    model=model, messages=messages, temperature=temperature,
                    max_tokens=max_tokens, **kwargs
                )
            except Exception as exc:
                text = str(exc).lower()
                if "daily token quota" in text or "per day" in text or "tpd" in text:
                    # A daily cap does not clear within a run. Fail fast and
                    # loudly so the report records an environment limit rather
                    # than attributing the shortfall to the pipeline.
                    logger.error(
                        "Groq DAILY token quota exhausted — aborting LLM phases. %s",
                        str(exc)[:200],
                    )
                    raise
                if "rate limit" not in text:
                    raise
                last_exc = exc
                wait = 20.0 * (attempt + 1)
                logger.warning(
                    "Provider rate limit hit (attempt %d/4); backing off %.0fs.",
                    attempt + 1, wait,
                )
                await asyncio.sleep(wait)
                # Do NOT clear the window here. Clearing it makes the limiter
                # *more* permissive at exactly the moment the provider says we
                # are over budget, which turns one rejection into a burst of
                # them. Instead, charge a full budget so the next acquire()
                # waits for a clean window.
                bucket._events.append((time.monotonic(), bucket.budget))
        raise last_exc  # type: ignore[misc]

    gs.groq_service.chat_complete = paced  # type: ignore[assignment]
    _installed = True
    logger.info("Installed evaluation rate-limit pacing at %d TPM.", tokens_per_minute)
