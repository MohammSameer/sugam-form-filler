import os
import re
import sys
import json
import asyncio
import hashlib
import datetime
import logging
from typing import Any, Dict, Optional

from google import genai
from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.tools import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.models.llm_response import LlmResponse
from mcp import StdioServerParameters

import app.pdf_filler as pdf_filler  # direct submodule import avoids the app/__init__ cycle
import app.knowledge_base as kb  # shared, self-populating scheme/form catalog
import app.security_events as security_events  # in-memory bus the web UI reads
from app.config import config
from app.fallback_model import build_fallback_model

# --------------------------------------------------------------------------- #
# Paths — mirror mcp_server.py so uploads and outputs share one artifacts tree.
# --------------------------------------------------------------------------- #
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARTIFACTS_DIR = os.path.join(_PROJECT_ROOT, "artifacts")
_UPLOADS_DIR = os.path.join(_ARTIFACTS_DIR, "uploads")

# Mime types we treat as an uploaded form we can later fill. All image types here
# are decoded by PyMuPDF (fitz) in image_to_pdf_bytes, which infers the format
# from the bytes — so any raster format fitz can open (webp, tiff, bmp, gif, …)
# can be wrapped into a fillable single-page PDF, not just PNG/JPEG.
_UPLOAD_MIME_EXT = {
    "application/pdf": "pdf",
    "image/png": "png",
    "image/jpeg": "jpg",
    "image/jpg": "jpg",
    "image/webp": "webp",
    "image/tiff": "tiff",
    "image/bmp": "bmp",
    "image/gif": "gif",
}

# --------------------------------------------------------------------------- #
# Shared model with automatic retry/backoff AND cross-model failover.
#
# Two layers of resilience, because free-tier quota fails in two different ways:
#   1. Per-minute spikes (transient 429/503): HttpRetryOptions rides them out with
#      exponential backoff on the SAME model — the right fix, since waiting works.
#   2. Per-DAY exhaustion (429) or an unavailable/unknown model (404): retrying the
#      same model is futile. So the model is a FallbackGemini that fails over to the
#      next model in config.model_chain (default: flash -> flash-lite). This also lets
#      the chain name a newer model first ("use it if my key has it, else fall back"):
#      a 404 is probed once, cached, and skipped thereafter. One completed form is many
#      requests; without this, a spent daily quota strands the user mid-form.
#
# Attempts are 3 (not 5) here: failover is now the safety net for true exhaustion,
# so there is no need to hammer a dead quota for 20s before switching.
# --------------------------------------------------------------------------- #
_MODEL_RETRY = types.HttpRetryOptions(
    attempts=3,
    initialDelay=1.0,
    maxDelay=20.0,
    expBase=2.0,
    httpStatusCodes=[429, 500, 503, 504],
)


def _on_model_switch(from_model: str, to_model: str, reason: str) -> None:
    """Record a quota failover so it shows in the audit log and the UI trust feed."""
    audit_log(
        "model_failover",
        "WARNING",
        {"from": from_model, "to": to_model, "reason": reason},
    )


SUGAM_MODEL = build_fallback_model(
    config.model_chain, _MODEL_RETRY, on_switch=_on_model_switch
)

# --------------------------------------------------------------------------- #
# Audit logging
# --------------------------------------------------------------------------- #
logger = logging.getLogger("sugam_audit")
logger.setLevel(logging.INFO)
if not logger.handlers:  # guard against duplicate handlers on hot-reload
    os.makedirs("artifacts", exist_ok=True)
    _fmt = logging.Formatter("%(message)s")
    _file = logging.FileHandler(os.path.join("artifacts", "audit.log"))
    _file.setFormatter(_fmt)
    logger.addHandler(_file)
    _stream = logging.StreamHandler()  # also surface events in the terminal for live demos
    _stream.setFormatter(_fmt)
    logger.addHandler(_stream)


def audit_log(action: str, severity: str, details: Dict[str, Any]) -> None:
    logger.info(json.dumps({"event": action, "severity": severity, "details": details}))
    # Mirror onto the in-memory bus so the web UI can render the checkpoint live.
    # The file remains the system of record; this is purely a display feed.
    security_events.publish(action, severity, details)


# --------------------------------------------------------------------------- #
# MCP toolset — spawns app/mcp_server.py as a stdio subprocess.
# Run the file by path (NOT `-m app.mcp_server`) so importing the `app` package
# — which imports this module — is not re-triggered, avoiding a fork loop.
# --------------------------------------------------------------------------- #
_MCP_SERVER = os.path.join(os.path.dirname(__file__), "mcp_server.py")


def sugam_mcp_toolset() -> MCPToolset:
    return MCPToolset(
        connection_params=StdioConnectionParams(
            server_params=StdioServerParameters(
                # Use THIS interpreter (the venv's python) rather than a bare
                # "python", which on Windows can resolve to the Microsoft Store
                # app-execution-alias stub and never start the server.
                command=sys.executable,
                args=[_MCP_SERVER],
            ),
            timeout=30.0,
        )
    )


# --------------------------------------------------------------------------- #
# Security checkpoint — runs before every model call on the orchestrator.
# 1. Scrubs PII (Aadhaar / PAN / bank) in-place before it reaches Gemini.
# 2. Blocks prompt-injection and consent-refusal by short-circuiting with a
#    canned response (returning an LlmResponse skips the model call).
# --------------------------------------------------------------------------- #
AADHAAR_RE = re.compile(r"\b\d{4}\s\d{4}\s\d{4}\b")
PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]{1}\b")
BANK_RE = re.compile(r"\b\d{9,18}\b")

INJECTION_KEYWORDS = ["ignore previous", "system prompt", "bypass", "override", "you are now"]
REFUSAL_KEYWORDS = ["do not consent", "refuse to share", "won't provide data"]


def _scrub(text: str) -> str:
    if config.pii_redaction_enabled:
        text = AADHAAR_RE.sub("[AADHAAR_REDACTED]", text)
        text = PAN_RE.sub("[PAN_REDACTED]", text)
        text = BANK_RE.sub("[BANK_REDACTED]", text)
    return text


def _masked_types(text: str) -> list[str]:
    """Which PII categories the scrub would mask. Drives the UI's trust panel.

    Detection mirrors _scrub's regexes so the panel can never claim a masking
    that did not actually happen.
    """
    if not config.pii_redaction_enabled:
        return []
    found = []
    for label, pattern in (("AADHAAR", AADHAAR_RE), ("PAN", PAN_RE), ("BANK", BANK_RE)):
        if pattern.search(text):
            found.append(label)
    return found


def _blocked_response(reason: str) -> LlmResponse:
    message = f"Security Policy Violation: {reason} We cannot proceed with this request."
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=message)])
    )


def _persist_uploaded_form(callback_context, llm_request) -> None:
    """Save the most recent uploaded PDF/image so a tool can fill it later.

    The uploaded file only ever reaches Gemini as an inline message Part — it is
    never otherwise written to disk. We capture the newest qualifying Part here
    (the one place the raw bytes are reliably in hand) and record its path in
    session state so `fill_uploaded_pdf` can read it back. Idempotent: a byte
    signature guards against re-writing the same upload on every turn.
    """
    latest = None  # (mime, data) of the last qualifying part across history
    for content in llm_request.contents or []:
        for part in content.parts or []:
            blob = getattr(part, "inline_data", None)
            if blob and getattr(blob, "data", None):
                mime = (getattr(blob, "mime_type", "") or "").lower()
                if mime in _UPLOAD_MIME_EXT:
                    latest = (mime, blob.data)

    if latest is None:
        return

    mime, data = latest
    sig = hashlib.sha256(data).hexdigest()
    if callback_context.state.get("uploaded_form_sig") == sig:
        return  # already saved this exact upload

    os.makedirs(_UPLOADS_DIR, exist_ok=True)
    ext = _UPLOAD_MIME_EXT[mime]
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    path = os.path.join(_UPLOADS_DIR, f"upload_{stamp}_{sig[:8]}.{ext}")
    with open(path, "wb") as fh:
        fh.write(data)

    callback_context.state["uploaded_form_path"] = path
    callback_context.state["uploaded_form_mime"] = mime
    callback_context.state["uploaded_form_sig"] = sig
    audit_log("form_uploaded", "INFO", {"path": path, "mime": mime, "bytes": len(data)})


def security_checkpoint(callback_context, llm_request) -> Optional[LlmResponse]:
    """ADK before_model_callback: scrub PII, block injection / consent refusal."""
    latest_user_text = ""

    for content in llm_request.contents or []:
        for part in content.parts or []:
            if getattr(part, "text", None):
                original = part.text
                part.text = _scrub(part.text)  # scrub in place before Gemini sees it
                if content.role == "user":
                    latest_user_text = original

    # Persist any uploaded form so it can be filled later (best-effort — must
    # never block a model call if disk/state write fails).
    try:
        _persist_uploaded_form(callback_context, llm_request)
    except Exception as exc:  # pragma: no cover - defensive
        audit_log("form_upload_capture_failed", "WARNING", {"error": str(exc)})

    lowered = latest_user_text.lower()

    if config.injection_detection_enabled and any(k in lowered for k in INJECTION_KEYWORDS):
        audit_log("prompt_injection_detected", "CRITICAL", {"input": latest_user_text})
        return _blocked_response("An injection attempt was detected.")

    if any(k in lowered for k in REFUSAL_KEYWORDS):
        audit_log("consent_refused", "WARNING", {"input": latest_user_text})
        return _blocked_response("You have refused to provide consent for data processing.")

    audit_log(
        "input_cleared",
        "INFO",
        {
            "scrubbed_input": _scrub(latest_user_text),
            "masked": _masked_types(latest_user_text),
        },
    )
    return None  # proceed to the model


# --------------------------------------------------------------------------- #
# Shared language rule — Sugam serves users across many Indian languages.
# Appended to every agent so the WHOLE conversation stays in the user's tongue.
# --------------------------------------------------------------------------- #
LANGUAGE_RULE = (
    "\n\nLANGUAGE: Reply in the SAME language the user actually writes in. If the user "
    "writes in English, reply in English. If the user writes in another language (e.g. Hindi, "
    "Tamil, Bengali, Marathi, Telugu, Kannada, Gujarati, Punjabi, Urdu), reply in that "
    "language. If the user explicitly asks you to speak in a particular language, switch to it "
    "and keep using it until they say otherwise. NEVER guess the user's language from the "
    "topic, form type, or your own name — use ONLY the language of the user's own messages; "
    "when in doubt, use English. Use simple, everyday words. Official field labels may stay in "
    "English, but every explanation, question, and message you write must be in the user's language."
)

# Makes the invisible PII masking visible in the conversation, so the security
# feature is demonstrable and the user is reassured their data was protected.
SECURITY_NOTE = (
    "\n\nSECURITY: You may see redaction tokens such as [AADHAAR_REDACTED], [PAN_REDACTED] "
    "or [BANK_REDACTED] in the user's messages. This means Sugam's security layer masked the "
    "user's sensitive number BEFORE it reached you — this is correct and intended. When you "
    "see one, briefly reassure the user that their sensitive number was received and protected, "
    "store it in the form as that redaction token, and NEVER ask them to retype the number in "
    "plain text."
)


# --------------------------------------------------------------------------- #
# Download delivery — an ADK-native tool (so it has tool_context, which MCP
# subprocess tools do not). It reads the PDF that generate_filled_pdf wrote and
# saves it as an ADK *artifact*, which the web UI surfaces with a download link.
# --------------------------------------------------------------------------- #
async def _attach_pdf_and_preview(tool_context, filename: str, pdf_bytes: bytes) -> None:
    """Save the PDF as a download artifact AND a page-1 PNG preview beside it.

    The preview (named '<stem>_preview.png') is what the web UI renders inline as
    an <img> — reliable in every browser, unlike a PDF blob in an <iframe>. The
    preview is best-effort: a render failure must never block the actual download.
    """
    await tool_context.save_artifact(
        filename, types.Part.from_bytes(data=pdf_bytes, mime_type="application/pdf")
    )
    try:
        preview = await asyncio.to_thread(pdf_filler.render_preview_png, pdf_bytes)
        preview_name = os.path.splitext(filename)[0] + "_preview.png"
        await tool_context.save_artifact(
            preview_name, types.Part.from_bytes(data=preview, mime_type="image/png")
        )
    except Exception as exc:  # pragma: no cover - preview is non-essential
        audit_log("preview_render_failed", "WARNING", {"artifact": filename, "error": str(exc)})


async def deliver_pdf_for_download(pdf_path: str, tool_context) -> str:
    """Attach a generated PDF to the conversation as a downloadable artifact.

    Call this immediately AFTER 'generate_filled_pdf' succeeds, passing the file
    path it returned, so the user gets a download link in the UI instead of just
    a path on disk.

    Args:
        pdf_path: The path returned by generate_filled_pdf. If it is missing or
            not found, the most recently generated PDF is used as a fallback.
    """
    import glob

    path = pdf_path
    if not path or not os.path.exists(path):
        candidates = sorted(
            glob.glob(os.path.join("artifacts", "filled_*.pdf")), key=os.path.getmtime
        )
        if not candidates:
            return "No generated PDF was found to attach. Please generate the PDF first."
        path = candidates[-1]

    with open(path, "rb") as fh:
        data = fh.read()
    filename = os.path.basename(path)

    await _attach_pdf_and_preview(tool_context, filename, data)
    audit_log("pdf_delivered", "INFO", {"artifact": filename, "bytes": len(data)})
    return (
        f"The filled PDF '{filename}' is ready. A download card with a preview now "
        f"appears right below your message — tell the user to tap Download there. "
        f"Do NOT mention any 'Artifacts panel'; there is no separate panel."
    )


# --------------------------------------------------------------------------- #
# Fill the user's OWN uploaded PDF (the core feature).
# An ADK-native tool (so it has tool_context/state) that reads the upload saved
# by the security checkpoint and fills it in place — either by setting AcroForm
# field values, or by overlaying values at Gemini-mapped coordinates on a flat /
# scanned form. Falls back cleanly to the data-sheet tool when no form was
# uploaded.
# --------------------------------------------------------------------------- #
_genai_client: Optional[genai.Client] = None


def _get_genai_client() -> genai.Client:
    """Lazily build a Gemini client (uses GOOGLE_API_KEY, non-Vertex per config).

    Configured with the same retry/backoff as SUGAM_MODEL — the Gemini free tier
    returns transient 429/503 ("high demand") that must be ridden out, otherwise
    a momentary spike fails the fill instead of a real error.
    """
    global _genai_client
    if _genai_client is None:
        _genai_client = genai.Client(
            api_key=os.environ.get("GOOGLE_API_KEY"),
            http_options=types.HttpOptions(
                retry_options=types.HttpRetryOptions(
                    attempts=5,
                    initialDelay=1.0,
                    maxDelay=20.0,
                    expBase=2.0,
                    httpStatusCodes=[429, 500, 503, 504],
                )
            ),
        )
    return _genai_client


def _parse_json_object(text: str) -> dict:
    """Parse a JSON object from a model response, tolerating ```json fences."""
    text = (text or "").strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?\s*|\s*```$", "", text, flags=re.IGNORECASE)
    start, end = text.find("{"), text.rfind("}")
    if start != -1 and end != -1:
        text = text[start : end + 1]
    return json.loads(text)


def _map_fields_to_values(field_names: list[str], data: dict) -> dict:
    """Ask Gemini to map collected {label: value} onto real AcroForm field names."""
    prompt = (
        "You map a user's collected form answers onto the exact field names of a "
        "PDF AcroForm. Return ONLY a JSON object of {pdf_field_name: value}.\n"
        "Rules: use ONLY field names from the provided list; include a field ONLY "
        "when you are confident which answer belongs to it; if unsure, omit it "
        "(never guess). Copy the answer value verbatim.\n\n"
        f"PDF field names:\n{json.dumps(field_names, ensure_ascii=False)}\n\n"
        f"Collected answers:\n{json.dumps(data, ensure_ascii=False)}"
    )
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    mapping = _parse_json_object(resp.text)
    # Keep only real field names, stringified.
    allowed = set(field_names)
    return {k: str(v) for k, v in mapping.items() if k in allowed and v not in (None, "")}


def _map_values_to_anchors(anchors: list[dict], data: dict) -> list[dict]:
    """Semantically match answers to real form lines (text-based forms).

    The geometry is already known from `extract_line_anchors`; Gemini only picks
    which line each answer belongs to (a text task it is reliable at), so the
    value lands on the actual blank instead of a guessed pixel coordinate.
    """
    lines = "\n".join(f'{a["index"]}: {a["label"]}' for a in anchors)
    prompt = (
        "You are placing a user's answers onto an official form. Below is a "
        "numbered list of the form's line labels, then the user's answers.\n"
        'Return ONLY JSON: {"placements": [{"index": int, "value": str}]} mapping '
        "each answer to the SINGLE best-matching line index (the blank that answer "
        "should be written on). Use each index at most once. Omit any answer with "
        "no confident match. Never guess.\n\n"
        f"Form lines:\n{lines}\n\n"
        f"Answers:\n{json.dumps(data, ensure_ascii=False)}"
    )
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = _parse_json_object(resp.text)
    by_index = {a["index"]: a for a in anchors}
    placements: list[dict] = []
    seen_values: set[str] = set()
    seen_indices: set[int] = set()
    for item in parsed.get("placements", []):
        try:
            idx = int(item["index"])
            a = by_index[idx]
        except (KeyError, ValueError, TypeError):
            continue
        value = str(item.get("value", "")).strip()
        # Guard against the model writing the same answer onto two anchors, or two
        # answers onto one anchor — each value and each blank is used at most once.
        if not value or value in seen_values or idx in seen_indices:
            continue
        seen_values.add(value)
        seen_indices.add(idx)
        placement = {"page": a["page"], "x": a["x"], "y": a["y"], "value": value}
        if a.get("size"):  # OCR anchors carry a form-scaled size; text anchors don't
            placement["size"] = a["size"]
        placements.append(placement)
    return placements


def _map_values_to_boxes(box_rows: list[dict], data: dict) -> list[dict]:
    """Match answers to comb/box grids and expand them one character per cell."""
    lines = "\n".join(
        f'{r["index"]}: {r["label"] or "(unlabelled)"} [{len(r["cells"])} boxes]'
        for r in box_rows
    )
    prompt = (
        "You are filling an official form whose fields are rows of boxes (one "
        "character per box). Below is a numbered list of box-fields (with their "
        "label and box count), then the user's answers.\n"
        'Return ONLY JSON: {"placements": [{"index": int, "value": str}]} mapping '
        "each answer to the SINGLE best-matching box-field index. The value must "
        "fit within the box count. Use each index at most once. Omit answers with "
        "no confident match. Never guess.\n\n"
        f"Box fields:\n{lines}\n\n"
        f"Answers:\n{json.dumps(data, ensure_ascii=False)}"
    )
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=prompt,
        config=types.GenerateContentConfig(response_mime_type="application/json"),
    )
    parsed = _parse_json_object(resp.text)
    by_index = {r["index"]: r for r in box_rows}
    placements: list[dict] = []
    seen_values: set[str] = set()
    seen_indices: set[int] = set()
    for item in parsed.get("placements", []):
        try:
            idx = int(item["index"])
            row = by_index[idx]
        except (KeyError, ValueError, TypeError):
            continue
        value = str(item.get("value", "")).strip()
        if not value or value in seen_values or idx in seen_indices:
            continue
        seen_values.add(value)
        seen_indices.add(idx)
        placements.extend(pdf_filler.boxes_to_char_placements(row, value))
    return placements


def _extract_box(item: dict) -> Optional[list[float]]:
    """Pull a 4-number bounding box out of a placement item, tolerant of key drift.

    The schema pins the key to 'box_2d', but the model has been seen to emit
    'box_2'/'box'/'bbox'. As a last resort we accept the first value in the item
    that is a list of four numbers, so a stray key never silently drops a field.
    """
    for key in ("box_2d", "box_2", "box", "bbox"):
        v = item.get(key)
        if isinstance(v, (list, tuple)) and len(v) == 4:
            try:
                return [float(x) for x in v]
            except (TypeError, ValueError):
                pass
    for v in item.values():
        if isinstance(v, (list, tuple)) and len(v) == 4 and all(
            isinstance(x, (int, float)) for x in v
        ):
            return [float(x) for x in v]
    return None


def _ocr_covers_form(anchors: list[dict], data: dict, threshold: float = 0.6) -> bool:
    """Locally judge whether OCR read the form well enough to trust — no API call.

    For each collected field, look for an OCR label that resembles its name. If
    enough fields have a plausible label match, OCR captured the form's structure
    and its deterministic placement is worth using; if few do, the scan is noisy
    (a photo with dotted leaders / box grids) and we should go straight to the
    vision path instead of wasting a matching call on a poor OCR read.
    """
    import difflib

    labels = [str(a.get("label", "")).lower() for a in anchors if a.get("label")]
    if not labels or not data:
        return False
    hits = 0
    for key in data:
        k = str(key).lower()
        best = max(
            (difflib.SequenceMatcher(None, k, lb).ratio() for lb in labels),
            default=0.0,
        )
        # 0.65 separates a crisp digital scan (labels read cleanly, high ratios)
        # from a noisy phone photo (dotted leaders / box grids corrupt many labels).
        if best >= 0.65:
            hits += 1
    return hits >= threshold * len(data)


def _map_values_to_coords(page_pngs: list[bytes], sizes: list, data: dict) -> list[dict]:
    """Ask Gemini vision only WHERE each answer goes; fill the text ourselves.

    Two deliberate choices make this reliable:

    1. Boxes, not points. Asking for a bare x/y of "where to write" is a vision
       model's least reliable mode — it lands text on the printed label and
       overlaps neighbours (the overlap bug). A 2-D bounding box is a trained
       detection capability the model does well, and the box lets us LEFT-ALIGN at
       the blank's start (never over the label) and SCALE the font to the box
       height (so a value can never spill onto the row above or below).

    2. Index in, index out — never the value. The model returns {index, box_2d};
       we look the answer TEXT up from `data` ourselves. When we instead asked the
       model to echo the value, it wrote the field LABEL ("Sub Division") into the
       blank instead of the answer ("Medchal"). Returning only a position removes
       every chance of the model writing the wrong text.

    Coordinates are Gemini's standard 0-1000 normalised [ymin, xmin, ymax, xmax],
    resolution-independent, so they map onto the PDF's point dimensions regardless
    of render size.
    """
    items = [(str(k), str(v)) for k, v in data.items() if str(v).strip()]
    if not items:
        return []

    numbered = "\n".join(f"{i}: {label} = {answer}" for i, (label, answer) in enumerate(items))
    parts: list = []
    for i, png in enumerate(page_pngs):
        parts.append(types.Part.from_text(text=f"--- Page {i} ---"))
        parts.append(types.Part.from_bytes(data=png, mime_type="image/png"))
    parts.append(
        types.Part.from_text(
            text=(
                "These images are the pages of a blank official form (0-based). Below "
                "is a numbered list of answers, each 'index: LABEL = ANSWER'. For each "
                "one, find on the form the EMPTY writing area for that LABEL — the blank "
                "line or box immediately AFTER the printed label, NOT the label text "
                "itself — and return its bounding box.\n"
                'Return ONLY JSON: {"placements": [{"index": int, "page": int, '
                '"box_2d": [ymin, xmin, ymax, xmax]}]} where box_2d is normalised to '
                "0-1000 (ymin/ymax vertical, xmin/xmax horizontal, origin TOP-LEFT), "
                "covering the blank space to write in, tight in height (one text line). "
                "Use each index at most once. Omit any index whose blank you cannot "
                "confidently find. Never guess a box.\n\n"
                f"Answers:\n{numbered}"
            )
        )
    )
    # A response schema forces exact keys and valid JSON: without it the model
    # drifts (observed: "box_2" instead of "box_2d") and, with many fields,
    # truncates the array into unparseable JSON. The generous token budget guards
    # against truncation for a form with many blanks.
    box_schema = types.Schema(
        type="OBJECT",
        properties={
            "index": types.Schema(type="INTEGER"),
            "page": types.Schema(type="INTEGER"),
            "box_2d": types.Schema(type="ARRAY", items=types.Schema(type="NUMBER")),
        },
        required=["index", "page", "box_2d"],
    )
    schema = types.Schema(
        type="OBJECT",
        properties={"placements": types.Schema(type="ARRAY", items=box_schema)},
        required=["placements"],
    )
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=parts,
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=8192,
        ),
    )
    parsed = _parse_json_object(resp.text)

    placements: list[dict] = []
    seen_indices: set[int] = set()
    for item in parsed.get("placements", []):
        try:
            idx = int(item["index"])
            page = int(item["page"])
            box = _extract_box(item)
            if idx in seen_indices or not (0 <= idx < len(items)) or box is None:
                continue
            if not (0 <= page < len(sizes)):
                continue
            ymin, xmin, ymax, xmax = box
            # Reject nonsense boxes (inverted / out of range) rather than writing
            # at a bad spot.
            if not (0 <= xmin < xmax <= 1000 and 0 <= ymin < ymax <= 1000):
                continue

            value = items[idx][1]  # the ANSWER, from our own data — never the model's echo
            w, h = sizes[page]
            box_h_pt = (ymax - ymin) / 1000.0 * h
            # Fit the text to the blank's height so it never spills onto adjacent
            # rows; clamp to a sane, readable range.
            size = max(7.0, min(box_h_pt * 0.72, 13.0))
            # Start a little past the blank's left edge so the value clears the
            # label's tail instead of butting against it. Scaled to the font so it
            # is proportional, but capped so a short blank isn't overshot.
            x_pt = xmin / 1000.0 * w + min(max(2.0, size * 0.35), 6.0)
            # FPDF baseline sits at y; place it just above the blank's bottom edge.
            y_pt = ymax / 1000.0 * h - max(1.5, box_h_pt * 0.18)

            seen_indices.add(idx)
            placements.append({"page": page, "x": x_pt, "y": y_pt, "value": value, "size": size})
        except (KeyError, ValueError, TypeError):
            continue
    return placements


async def fill_uploaded_pdf(user_data: str, tool_context) -> str:
    """Fill the user's OWN uploaded form with their collected answers.

    Call this (instead of generate_filled_pdf) whenever the user uploaded a
    document. It fills interactive fields if the PDF has them, otherwise overlays
    the values onto the original scan/image, then attaches the result for download.

    Args:
        user_data: JSON object (as a string) of collected {field label: value}.
    """
    path = tool_context.state.get("uploaded_form_path")
    mime = tool_context.state.get("uploaded_form_mime", "application/pdf")
    if not path or not os.path.exists(path):
        return (
            "No uploaded form is available to fill. If the user only NAMED a form "
            "(did not upload it), use 'generate_filled_pdf' instead."
        )

    try:
        data = json.loads(user_data) if isinstance(user_data, str) else dict(user_data)
        if not isinstance(data, dict) or not data:
            raise ValueError("expected a non-empty JSON object of field -> value")
    except (json.JSONDecodeError, ValueError) as exc:
        return f"ERROR: could not parse user_data ({exc}). Expected a JSON object of field -> value."

    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        # Normalise images to a single-page PDF so both paths produce a real PDF.
        pdf_bytes = pdf_filler.image_to_pdf_bytes(raw) if mime.startswith("image/") else raw

        if pdf_filler.has_acroform_fields(pdf_bytes):
            field_names = pdf_filler.list_acroform_fields(pdf_bytes)
            mapping = await asyncio.to_thread(_map_fields_to_values, field_names, data)
            if not mapping:
                return (
                    "The uploaded PDF has form fields, but none could be confidently "
                    "matched to the collected answers. Please double-check the answers "
                    "or use 'generate_filled_pdf' as a fallback."
                )
            out_bytes = pdf_filler.fill_acroform(pdf_bytes, mapping)
            method = f"filled {len(mapping)} interactive field(s)"
        else:
            # Deterministic geometry when the form is text-based: comb/box grids
            # (one char per cell) if that dominates, else underline blanks. For a
            # scanned/image form with no extractable text, OCR the labels (accurate
            # and local); fall back to the vision model only if OCR finds nothing.
            anchors = pdf_filler.extract_line_anchors(pdf_bytes)
            box_rows = pdf_filler.extract_box_rows(pdf_bytes)
            if box_rows and len(box_rows) >= len(anchors):
                placements = await asyncio.to_thread(_map_values_to_boxes, box_rows, data)
                mode = "box-grid"
            elif anchors:
                placements = await asyncio.to_thread(_map_values_to_anchors, anchors, data)
                mode = "text-anchored"
            else:
                # No text layer (photo/scan). Two strategies, chosen per form:
                #   * OCR-anchored — Tesseract reads each label's exact box, giving
                #     deterministic placement and needing only a fast text match. Best
                #     on CLEAN scans / digital images.
                #   * Vision-mapped — Gemini returns a bounding box per value. Best on
                #     NOISY camera photos, where OCR misreads dotted leaders and box
                #     grids (measured: vision 13/14 vs OCR 8/14 on a real photo).
                # We decide LOCALLY (no API call) whether OCR read this form well
                # enough; a noisy photo skips straight to vision with nothing wasted.
                ocr_anchors = await asyncio.to_thread(pdf_filler.ocr_line_anchors, pdf_bytes)
                placements = []
                if ocr_anchors and _ocr_covers_form(ocr_anchors, data):
                    ocr_pl = await asyncio.to_thread(_map_values_to_anchors, ocr_anchors, data)
                    if len(ocr_pl) >= max(3, int(0.6 * len(data))):
                        placements, mode = ocr_pl, "ocr-anchored"
                if not placements:
                    page_pngs = pdf_filler.render_pages_to_pngs(pdf_bytes)
                    sizes = pdf_filler.page_sizes(pdf_bytes)
                    placements = await asyncio.to_thread(_map_values_to_coords, page_pngs, sizes, data)
                    mode = "vision-mapped"
            if not placements:
                return (
                    "Could not confidently locate where to write the answers on the "
                    "uploaded form. Please try a clearer scan or use 'generate_filled_pdf'."
                )
            out_bytes = pdf_filler.overlay_values(pdf_bytes, placements)
            method = f"overlaid {len(placements)} value(s) onto the original form ({mode})"
    except Exception as exc:  # pragma: no cover - surfaced to the agent
        return f"ERROR filling the uploaded PDF: {exc}"

    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)
    stamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
    filename = f"filled_upload_{stamp}.pdf"
    out_path = os.path.join(_ARTIFACTS_DIR, filename)
    with open(out_path, "wb") as fh:
        fh.write(out_bytes)

    # Attach for download + an inline preview image (same mechanism everywhere).
    await _attach_pdf_and_preview(tool_context, filename, out_bytes)
    audit_log("uploaded_pdf_filled", "INFO", {"artifact": filename, "method": method})
    return (
        f"SUCCESS: your uploaded form was filled ({method}) and attached as "
        f"'{filename}'. A download card with a preview now appears right below your "
        f"message — tell the user to tap Download there. Do NOT mention any "
        f"'Artifacts panel'; there is no separate panel."
    )


# --------------------------------------------------------------------------- #
# Grounded research fallback — the permanent fix for schemes/forms NOT in the
# curated catalog. Instead of dead-ending, we look the item up LIVE from official
# web sources (Gemini + Google Search grounding), cite the sources, and persist
# the verified result to the shared knowledge base so it becomes an instant,
# offline cache hit for everyone afterwards (including the MCP subprocess).
#
# Grounding is used — not the model's bare memory — because ungrounded answers
# invent benefit amounts and eligibility cutoffs, which is a real liability for
# government benefits. Every researched answer is tied to a citable source.
# --------------------------------------------------------------------------- #
def _grounded_research(query: str) -> tuple[str, list[str]]:
    """Grounded natural-language research call; returns (prose_notes, source_labels).

    Deliberately does NOT force JSON: demanding strict JSON makes Gemini answer
    from parametric memory and skip the search entirely (observed: zero grounding
    chunks), which would silently drop the citations that make the answer
    trustworthy. So we let it search and write prose here, and structure it into
    JSON in a separate, non-grounded step (`_structure_json`).
    """
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=query,
        config=types.GenerateContentConfig(
            tools=[types.Tool(google_search=types.GoogleSearch())],
            temperature=0.0,
        ),
    )
    # Prefer the human-readable source name (e.g. "nsdcindia.org") over the opaque
    # Vertex grounding redirect URI, so citations shown to the user are meaningful.
    sources: list[str] = []
    for cand in resp.candidates or []:
        meta = getattr(cand, "grounding_metadata", None)
        for chunk in getattr(meta, "grounding_chunks", None) or []:
            web = getattr(chunk, "web", None)
            label = getattr(web, "domain", None) or getattr(web, "title", None) or getattr(web, "uri", None)
            if label and label not in sources:
                sources.append(label)
    return (resp.text or ""), sources


def _structure_json(instruction: str, notes: str) -> dict:
    """Reshape grounded research notes into a strict JSON object (no search)."""
    resp = _get_genai_client().models.generate_content(
        model=config.model,
        contents=f"{instruction}\n\nRESEARCH NOTES:\n{notes}",
        config=types.GenerateContentConfig(
            response_mime_type="application/json",
            temperature=0.0,
        ),
    )
    return _parse_json_object(resp.text)


def _format_scheme(entry: dict) -> str:
    lines = [
        entry["full_name"],
        f"- Benefit: {entry['benefit']}",
        f"- Eligibility: {entry['eligibility']}",
        f"- Documents needed: {entry['documents']}",
    ]
    if entry.get("sources"):
        lines.append("- Sources: " + ", ".join(entry["sources"][:5]))
    return "\n".join(lines)


async def research_govt_scheme(scheme_name: str) -> str:
    """Answer a question about ANY Indian government scheme, even unlisted ones.

    Tiered and self-improving: returns the curated/learned entry instantly when
    the scheme is already known; otherwise researches it live from official web
    sources, remembers the verified result so it is instant next time, and always
    cites its sources. Use this for any "tell me about scheme X" request — it is
    the correct tool even when the local catalog does not have the scheme.

    Args:
        scheme_name: The scheme the user asked about (any spelling / language).
    """
    name = (scheme_name or "").strip()
    if not name:
        return "Please tell me which government scheme you'd like to know about."

    cached = kb.lookup_scheme(name)
    if cached:
        return _format_scheme(cached)

    research_query = (
        "Using Google Search, research the official Indian government scheme "
        f"'{name}'. Report its full official name, the exact benefit(s) it provides, "
        "who is eligible, and the documents required to apply. Prefer official "
        "(.gov.in / ministry) sources. If it is NOT a real Indian government scheme, "
        "say clearly that it does not appear to exist."
    )
    structure_instruction = (
        "From the research notes, return ONLY a JSON object with keys "
        '{"found": true|false, "full_name": str, "benefit": str, "eligibility": str, '
        '"documents": str}. Set found=false if the notes say the scheme is not real or '
        "give no real information. Keep benefit / eligibility / documents concise and "
        "factual; do not invent amounts the notes do not state."
    )
    try:
        notes, sources = await asyncio.to_thread(_grounded_research, research_query)
        parsed = await asyncio.to_thread(_structure_json, structure_instruction, notes)
    except Exception as exc:  # network / parse / API error — degrade gracefully
        audit_log("scheme_research_failed", "WARNING", {"scheme": name, "error": str(exc)})
        return (
            f"I couldn't reliably look up '{name}' right now. Please check the official "
            f"government portal, or upload the scheme's form and I'll read it directly."
        )

    if not parsed.get("found") or not parsed.get("full_name") or not parsed.get("benefit"):
        return (
            f"I couldn't find reliable official details for '{name}'. It may not be a "
            f"government scheme, or the name may be spelled differently. If you have its "
            f"form, upload it and I'll read and explain it directly."
        )

    entry = {f: str(parsed.get(f, "") or "").strip() for f in kb.SCHEME_FIELDS}
    entry["sources"] = sources
    try:
        kb.remember_scheme(name, entry)
        audit_log("scheme_researched", "INFO", {"scheme": name, "sources": sources[:3]})
    except Exception as exc:  # persistence is best-effort; still answer the user
        audit_log("scheme_persist_failed", "WARNING", {"scheme": name, "error": str(exc)})

    return (
        _format_scheme(entry)
        + "\n(Fetched live from official sources — please confirm critical details on the official portal.)"
    )


async def research_form_fields(form_id: str) -> str:
    """Find the required fields of a NAMED official form not in the local catalog.

    Prefer having the user UPLOAD the form (form_reader reads the real document,
    which is always ground truth). Use this only when the user names a form but
    cannot upload it: it researches the form's typical required fields from
    official sources and remembers them for next time.

    Args:
        form_id: The form's name, e.g. "Ration Card", "Voter ID", "Passport".
    """
    name = (form_id or "").strip()
    if not name:
        return "Please tell me which form you'd like the required fields for."

    cached = kb.lookup_form(name)
    if cached:
        lines = "\n".join(f"{i}. {label} - {desc}" for i, (label, desc) in enumerate(cached, 1))
        return f"Required fields for {name.upper()}:\n{lines}"

    research_query = (
        "Using Google Search, research the official Indian form "
        f"'{name}'. List the fields an applicant must fill on it, with a short "
        "plain-language hint for each. Prefer official sources. If it is NOT a real "
        "official form, say clearly that it does not appear to exist."
    )
    structure_instruction = (
        "From the research notes, return ONLY a JSON object with keys "
        '{"found": true|false, "fields": [{"label": str, "description": str}]}. Set '
        "found=false if the notes say the form is not real. Include only fields the "
        "notes actually mention (4-15 of them); do not invent fields."
    )
    try:
        notes, sources = await asyncio.to_thread(_grounded_research, research_query)
        parsed = await asyncio.to_thread(_structure_json, structure_instruction, notes)
    except Exception as exc:
        audit_log("form_research_failed", "WARNING", {"form": name, "error": str(exc)})
        return (
            f"I couldn't reliably look up the '{name}' form right now. If you have it, "
            f"please upload it and I'll read the fields directly."
        )

    fields = parsed.get("fields") if parsed.get("found") else None
    if not isinstance(fields, list) or not fields:
        return (
            f"I couldn't find a reliable field list for the '{name}' form. If you have it, "
            f"please upload it and I'll read and explain every field directly."
        )

    try:
        kb.remember_form(name, fields)
        audit_log("form_researched", "INFO", {"form": name, "fields": len(fields)})
    except Exception as exc:
        audit_log("form_persist_failed", "WARNING", {"form": name, "error": str(exc)})

    pairs = kb.lookup_form(name) or [
        (str(f.get("label", "")).strip(), str(f.get("description", "")).strip()) for f in fields
    ]
    lines = "\n".join(f"{i}. {label} - {desc}" for i, (label, desc) in enumerate(pairs, 1))
    tail = ("\n- Sources: " + ", ".join(sources[:5])) if sources else ""
    return (
        f"Required fields for {name.upper()} (researched from official sources):\n{lines}{tail}"
        "\n(For an exact fill, uploading the real form is still best.)"
    )


# --------------------------------------------------------------------------- #
# Agents
# --------------------------------------------------------------------------- #
form_reader = LlmAgent(
    name="form_reader",
    model=SUGAM_MODEL,
    description="Reads official forms — including uploaded images/PDFs — and explains their required fields in plain language.",
    instruction="""You are the Form Reader agent for Sugam.
When you receive control, analyze the official form the user is asking about:
- If the user UPLOADED a document or image, READ IT DIRECTLY with your vision: identify every
  field on the form and explain each one in simple, plain language. You make paperwork
  accessible to everyone. This is always the best path — the real document is ground truth.
- If the form is only NAMED (e.g. "KYC", "PM-KISAN") with no upload, use 'parse_form_fields'.
  If it replies NOT_FOUND, call 'research_form_fields' with the same name to look the fields
  up from official sources (it remembers them for next time). Prefer asking the user to upload
  the actual form whenever possible.
- For questions about a government SCHEME (benefit / eligibility / documents), call
  'research_govt_scheme' — it uses the curated catalog first and researches unlisted schemes
  live from official sources, always citing them.
After you have explained the fields, transfer control back to the 'orchestrator' agent so it
can collect the user's details."""
    + LANGUAGE_RULE
    + SECURITY_NOTE,
    tools=[sugam_mcp_toolset(), research_govt_scheme, research_form_fields],
    before_model_callback=security_checkpoint,
)

data_collector = LlmAgent(
    name="data_collector",
    model=SUGAM_MODEL,
    description="Politely collects the details a form needs from the user, one at a time.",
    instruction="""You are the Data Collector agent for Sugam.
You converse with the user politely in their preferred language to gather the missing
details required for the form. Do not ask for everything at once; be conversational and
ask for one field at a time. When you have collected all the required details (or the user
wants to finish), call transfer_to_agent(agent_name="orchestrator") so the final document
can be generated."""
    + LANGUAGE_RULE
    + SECURITY_NOTE,
    before_model_callback=security_checkpoint,
)

orchestrator = LlmAgent(
    name="orchestrator",
    model=SUGAM_MODEL,
    description="Coordinates form reading and data collection to help the user complete a form.",
    instruction="""You are the Orchestrator for Sugam Form Filler.
Help the user understand and complete their official form.

IMPORTANT — how to reach your sub-agents:
'form_reader' and 'data_collector' are sub-agents, NOT callable tools. There are NO functions
named 'form_reader' or 'data_collector'. The ONLY way to hand work to a sub-agent is to call
the built-in function `transfer_to_agent` with the agent's name. Never call a sub-agent directly.

Your workflow:
- When the user UPLOADS a document/image, or asks about a specific named form, call
  transfer_to_agent(agent_name="form_reader"). form_reader can see the uploaded document
  directly and will read and explain its fields — always route documents to it rather than
  describing them yourself.
- For a question about a government SCHEME (its benefit, eligibility, or documents), call
  'research_govt_scheme' with the scheme name. It returns curated details instantly for known
  schemes and researches ANY unlisted scheme live from official sources (with citations),
  remembering it for next time — so never dead-end with "I don't have that scheme".
- If 'parse_form_fields' or 'lookup_govt_scheme' ever returns a NOT_FOUND message, do NOT stop:
  follow its instruction and call 'research_form_fields' / 'research_govt_scheme' respectively.
- To gather the user's details one field at a time, call
  transfer_to_agent(agent_name="data_collector").
- When all details are collected, produce the final document. CHOOSE THE RIGHT TOOL:
  * If the user UPLOADED a form/document/image, call 'fill_uploaded_pdf' with the collected
    answers as a JSON string. This fills the user's OWN form (their exact document) — either
    its interactive fields or by writing values onto the original scan. It also attaches the
    result for download, so you do NOT need to call 'deliver_pdf_for_download' afterwards.
  * ONLY if the form was merely NAMED (e.g. "KYC") and never uploaded, use 'generate_filled_pdf'
    to produce a clean data sheet, then IMMEDIATELY call 'deliver_pdf_for_download' with the
    exact path it returned so the user gets a download link.

CRITICAL — NEVER CLAIM A FILL YOU DID NOT PERFORM:
Producing the document means CALLING the tool, not describing it. You must NOT tell the user the
form is "filled", "ready", "done", or "available to download" unless, IN THIS SAME TURN, you have
actually called 'fill_uploaded_pdf' (or 'generate_filled_pdf' + 'deliver_pdf_for_download') and it
returned a message beginning with SUCCESS. If you have collected the details but have not yet called
the tool, your ONLY correct next action is to call it now — pass every collected answer as a JSON
string in `user_data`. Reconstruct that JSON from the conversation (the user's answers are in the
history). A message announcing success without a preceding successful tool call is a bug: the user
gets no download and is stranded. When in doubt, call the tool.
  After a SUCCESSFUL tool call, tell the user their filled form is ready and that a download card
  with a preview now appears right below your message, where they can tap Download. NEVER tell the
  user to "open the Artifacts panel" — there is no such panel; the download appears inline in the
  chat. Keep this closing message SHORT (2-3 sentences); do not pad it with long instructions.
Be warm, clear, and never ask for everything at once."""
    + LANGUAGE_RULE
    + SECURITY_NOTE,
    sub_agents=[form_reader, data_collector],
    tools=[
        sugam_mcp_toolset(),
        research_govt_scheme,
        research_form_fields,
        fill_uploaded_pdf,
        deliver_pdf_for_download,
    ],
    before_model_callback=security_checkpoint,
)

# The ADK dev server (`adk web app`) and agent loader look for `root_agent`.
root_agent = orchestrator
