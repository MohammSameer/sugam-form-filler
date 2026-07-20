import os
from dataclasses import dataclass, field
from dotenv import load_dotenv

load_dotenv()
os.environ.setdefault("GOOGLE_GENAI_USE_VERTEXAI", "False")  # Gemini API key only


def _model_chain() -> list[str]:
    """The ordered model chain: the primary, then automatic fallbacks.

    GEMINI_MODEL is the primary and still works exactly as before. On top of it,
    GEMINI_MODEL_FALLBACKS (comma-separated) lists models to fail over to when the
    primary's free-tier quota is exhausted mid-conversation — so a spent daily
    quota degrades gracefully instead of stranding the user. The default drops
    from flash to flash-lite (which has a more generous requests-per-day ceiling).

    Order is preserved and duplicates removed, so the primary never appears twice
    even if it is also named in the fallback list.
    """
    primary = os.getenv("GEMINI_MODEL", "gemini-2.5-flash").strip()
    raw_fallbacks = os.getenv("GEMINI_MODEL_FALLBACKS", "gemini-2.5-flash-lite")
    names = [primary] + [n.strip() for n in raw_fallbacks.split(",")]
    chain: list[str] = []
    for n in names:
        if n and n not in chain:
            chain.append(n)
    return chain


@dataclass
class AgentConfig:
    # The primary model. Default gemini-2.5-flash (the 1.5 family is retired and returns 404).
    # gemini-2.5-flash-lite has tighter reasoning but a more generous free-tier RPD.
    model: str = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
    # Primary first, then quota fallbacks. See _model_chain(). model == model_chain[0].
    model_chain: list[str] = field(default_factory=_model_chain)
    mcp_server_port: int = 8090
    max_iterations: int = 3
    pii_redaction_enabled: bool = True
    injection_detection_enabled: bool = True

config = AgentConfig()
