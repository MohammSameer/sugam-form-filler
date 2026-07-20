"""In-process bus for security-checkpoint events, so the UI can render them live.

The checkpoint in `agent.py` already writes every event to `artifacts/audit.log`,
but a file is invisible to a browser, and the ADK event stream never carries
these events: masking happens *before* the model call, and blocking happens
*instead of* it. This module mirrors the same records into a bounded in-memory
ring that `app/server.py` exposes over HTTP.

Two design points worth knowing:

1.  The checkpoint runs before EVERY model call — including the model's internal
    tool-calling loop and each sub-agent turn — so a single user message can emit
    a dozen `input_cleared` events. Storing them all would evict the events a
    user actually cares about. Clean passes are therefore counted, not stored;
    only *notable* events get a slot in the ring.

2.  It is a ring, not a log. The UI only renders recent activity, and an
    unbounded list in a long-running server is a leak. `artifacts/audit.log`
    remains the complete system of record.

SCOPE — READ BEFORE DEPLOYING MULTI-USER
    This ring is process-global, not per-session, because the checkpoint callback
    has no session id to key on. On a local single-user run (the intended setup)
    that is exactly right. If you ever serve multiple users from one process,
    every user's trust panel would poll the same feed and see the others' events.
    The payloads are already stripped of raw input by `_safe_details`, so no PII
    or prompt text leaks — but the *fact* that someone was masked or blocked
    would. To go multi-user, thread the session id through the callback and key
    the ring by it.
"""

from __future__ import annotations

import datetime
import itertools
import threading
from collections import deque
from typing import Any, Dict, List

_MAX_EVENTS = 250

_events: deque[Dict[str, Any]] = deque(maxlen=_MAX_EVENTS)
_seq = itertools.count(1)
_clean_passes = 0
_lock = threading.Lock()  # ADK serves requests on a threadpool; the ring is shared.


def publish(action: str, severity: str, details: Dict[str, Any]) -> None:
    """Record a checkpoint event. Never raises — auditing must not break a turn."""
    global _clean_passes
    try:
        # A clean pass with nothing masked is the common case and carries no
        # information beyond "the checkpoint ran". Count it and move on.
        if action == "input_cleared" and not details.get("masked"):
            with _lock:
                _clean_passes += 1
            return

        record = {
            "id": next(_seq),
            "event": action,
            "severity": severity,
            "ts": datetime.datetime.now(datetime.timezone.utc).isoformat(),
            "details": _safe_details(action, details),
        }
        with _lock:
            _events.append(record)
            _clean_passes += 1 if action == "input_cleared" else 0
    except Exception:  # pragma: no cover - defensive; auditing is best-effort
        pass


def snapshot(cursor: int = 0) -> Dict[str, Any]:
    """Events with id > cursor (oldest first), plus the running clean-pass count."""
    with _lock:
        events = [e for e in _events if e["id"] > cursor]
        return {
            "events": events,
            "cursor": _events[-1]["id"] if _events else cursor,
            "checksPassed": _clean_passes,
        }


def reset() -> None:
    """Clear the ring. Used by tests and by the UI's 'start over' action."""
    global _clean_passes
    with _lock:
        _events.clear()
        _clean_passes = 0


def _safe_details(action: str, details: Dict[str, Any]) -> Dict[str, Any]:
    """Strip anything unsafe to hand to a browser.

    `prompt_injection_detected` and `consent_refused` record the raw offending
    input for the audit file — that text is exactly what must NOT be echoed back
    into the DOM, so the UI gets the event type and nothing else. `scrubbed_input`
    is dropped too: it is PII-masked, but it is still the user's own prose and the
    trust panel has no reason to repeat it back at them.
    """
    if action in ("prompt_injection_detected", "consent_refused"):
        return {}
    safe = {k: v for k, v in details.items() if k not in ("input", "scrubbed_input")}
    return safe
