"""A Gemini model that transparently fails over to the next model on quota exhaustion.

WHY THIS EXISTS
    The free Gemini tier has a hard requests-per-day ceiling, and one completed
    form is many requests (each agent hop, each tool, each turn). When the primary
    model's daily quota is spent, every remaining turn 429s and the user is
    stranded mid-form — the worst possible moment.

    ADK builds ONE model object that all three agents (orchestrator, form_reader,
    data_collector) share. So wrapping the *model* — rather than each agent — gives
    the whole system automatic failover for free: when the primary is exhausted,
    the next model in the chain takes over and the conversation continues. The ADK
    agent loop never knows a switch happened.

    A sensible default chain trades reliability down gracefully rather than failing:
        gemini-2.5-flash  ->  gemini-2.5-flash-lite
    Flash is the reliable default; if its daily quota is gone, lite (more generous
    RPD) keeps the user moving, accepting weaker tool-calling over a dead end.

THE ONE LIMITATION, STATED PLAINLY
    Only a failure BEFORE any output is streamed can be retried on another model.
    Once tokens (or a tool call) have been emitted to the client, re-running on a
    different model would double-emit them, so we re-raise instead. In practice
    quota/429 errors fire at the very START of the call — exactly the case this
    recovers — so this limitation almost never bites.
"""

from __future__ import annotations

from typing import AsyncGenerator, Callable, List, Optional

from pydantic import PrivateAttr

from google.adk.models.base_llm import BaseLlm
from google.adk.models.google_llm import Gemini
from google.adk.models.llm_request import LlmRequest
from google.adk.models.llm_response import LlmResponse
from google.genai import errors, types


def _code(exc: BaseException) -> Optional[int]:
    return getattr(exc, "code", None) if isinstance(exc, errors.APIError) else None


def should_failover(exc: BaseException) -> bool:
    """True when `exc` is worth trying the next model for.

    Two kinds of failure justify a switch:
      * 429 — the model's quota/rate limit is spent. A different model may have
        quota left. TEMPORARY: the model recovers (next minute, next day).
      * 404 / NOT_FOUND — the model name is wrong or not enabled on this key.
        A different model may exist. PERMANENT for this process (see is_permanent):
        the name will never resolve, so we probe it once and skip it thereafter.

    Structured error code is checked first; a string match is the fallback because
    ADK/the SDK sometimes wraps the original error so the numeric code is hidden.
    """
    if _code(exc) in (429, 404):
        return True
    text = str(exc).upper()
    return any(
        k in text
        for k in (
            "429", "RESOURCE_EXHAUSTED", "QUOTA", "RATE LIMIT",  # exhaustion
            "404", "NOT_FOUND", "NOT FOUND", "WAS NOT FOUND",   # unavailable
            "IS NOT SUPPORTED", "DOES NOT EXIST",
        )
    )


def is_permanent(exc: BaseException) -> bool:
    """A model-unavailable failure (404) — permanent, unlike a quota 429.

    Used to cache a dead model so a made-up or unavailable name is not re-probed
    on every turn. Quota is deliberately NOT permanent: it comes back.
    """
    if _code(exc) == 404:
        return True
    if _code(exc) == 429:
        return False
    text = str(exc).upper()
    if "429" in text or "RESOURCE_EXHAUSTED" in text or "QUOTA" in text:
        return False
    return any(
        k in text
        for k in ("404", "NOT_FOUND", "NOT FOUND", "WAS NOT FOUND", "IS NOT SUPPORTED", "DOES NOT EXIST")
    )


class FallbackGemini(BaseLlm):
    """Delegates to an ordered list of Gemini models, failing over on exhaustion.

    `model` (the field BaseLlm requires) is set to the primary's name so anything
    that reads it — config echoes, logs — reports the model actually preferred.
    """

    # The chain, primary first. Pydantic accepts these because Gemini is itself a
    # pydantic model.
    chain: List[Gemini] = []
    # Called as on_switch(from_model, to_model, reason) each time we fail over, so
    # the caller can audit the switch. Kept out of the model's data (exclude) since
    # a callable is not serialisable.
    on_switch: Optional[Callable[[str, str, str], None]] = None

    # Model names that returned a permanent 404 (wrong/unavailable name). Skipped
    # on every subsequent turn so a made-up primary is not re-probed each time.
    _dead: set = PrivateAttr(default_factory=set)

    model_config = {"arbitrary_types_allowed": True}

    async def generate_content_async(
        self, llm_request: LlmRequest, stream: bool = False
    ) -> AsyncGenerator[LlmResponse, None]:
        # The live chain skips models already known to be permanently unavailable.
        live = [m for m in self.chain if m.model not in self._dead] or self.chain
        last_exc: Optional[BaseException] = None

        for i, m in enumerate(live):
            produced = False
            try:
                async for resp in m.generate_content_async(llm_request, stream=stream):
                    produced = True
                    yield resp
                return  # this model carried the whole turn — done
            except Exception as exc:  # noqa: BLE001 - deciding whether to fail over
                is_last = i == len(live) - 1
                # Cannot switch once output has started (would double-emit), and a
                # non-failover error (a real bug) must not be masked by trying
                # another model. In those cases, and when the chain is spent, surface it.
                if produced or not should_failover(exc):
                    raise
                # A permanently unavailable model (404) is cached so it is never
                # tried again this process; a quota 429 is not (it recovers).
                if is_permanent(exc):
                    self._dead.add(m.model)
                if is_last:
                    raise
                last_exc = exc
                if self.on_switch is not None:
                    try:
                        self.on_switch(m.model, live[i + 1].model, str(exc)[:200])
                    except Exception:  # auditing must never break the turn
                        pass
                # loop continues to the next model in the chain

        if last_exc is not None:  # pragma: no cover - chain was non-empty above
            raise last_exc


def build_fallback_model(
    model_names: List[str],
    retry_options: types.HttpRetryOptions,
    on_switch: Optional[Callable[[str, str, str], None]] = None,
) -> BaseLlm:
    """Build a model for `model_names` (primary first).

    A single-entry chain returns a plain Gemini — no wrapper overhead when there
    is nothing to fail over to.
    """
    geminis = [Gemini(model=name, retry_options=retry_options) for name in model_names]
    if len(geminis) == 1:
        return geminis[0]
    return FallbackGemini(model=model_names[0], chain=geminis, on_switch=on_switch)
