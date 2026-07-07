import os
import re
import sys
import json
import logging
from typing import Any, Dict, Optional

from google.genai import types
from google.adk.agents import LlmAgent
from google.adk.models.google_llm import Gemini
from google.adk.tools import MCPToolset
from google.adk.tools.mcp_tool.mcp_session_manager import StdioConnectionParams
from google.adk.models.llm_response import LlmResponse
from mcp import StdioServerParameters

from app.config import config

# --------------------------------------------------------------------------- #
# Shared model with automatic retry/backoff.
# Gemini free tier occasionally returns 429/503 ("high demand") — transient,
# server-side spikes. Retrying with exponential backoff rides them out so a demo
# take isn't ruined by a momentary overload instead of a real failure.
# --------------------------------------------------------------------------- #
SUGAM_MODEL = Gemini(
    model=config.model,
    retry_options=types.HttpRetryOptions(
        attempts=5,
        initialDelay=1.0,
        maxDelay=20.0,
        expBase=2.0,
        httpStatusCodes=[429, 500, 503, 504],
    ),
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


def _blocked_response(reason: str) -> LlmResponse:
    message = f"Security Policy Violation: {reason} We cannot proceed with this request."
    return LlmResponse(
        content=types.Content(role="model", parts=[types.Part(text=message)])
    )


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

    lowered = latest_user_text.lower()

    if config.injection_detection_enabled and any(k in lowered for k in INJECTION_KEYWORDS):
        audit_log("prompt_injection_detected", "CRITICAL", {"input": latest_user_text})
        return _blocked_response("An injection attempt was detected.")

    if any(k in lowered for k in REFUSAL_KEYWORDS):
        audit_log("consent_refused", "WARNING", {"input": latest_user_text})
        return _blocked_response("You have refused to provide consent for data processing.")

    audit_log("input_cleared", "INFO", {"scrubbed_input": _scrub(latest_user_text)})
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

    await tool_context.save_artifact(
        filename, types.Part.from_bytes(data=data, mime_type="application/pdf")
    )
    audit_log("pdf_delivered", "INFO", {"artifact": filename, "bytes": len(data)})
    return (
        f"The filled PDF '{filename}' is ready. It has been attached to this "
        f"conversation — open the Artifacts panel in the UI to download it."
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
  accessible to everyone.
- If the form is only NAMED (e.g. "KYC", "PM-KISAN") with no upload, use your
  'parse_form_fields' / 'lookup_govt_scheme' tools to find what it requires.
After you have explained the fields, transfer control back to the 'orchestrator' agent so it
can collect the user's details."""
    + LANGUAGE_RULE
    + SECURITY_NOTE,
    tools=[sugam_mcp_toolset()],
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
- To gather the user's details one field at a time, call
  transfer_to_agent(agent_name="data_collector").
- When all details are collected, use the 'generate_filled_pdf' tool to produce the final document.
  Then IMMEDIATELY call 'deliver_pdf_for_download', passing the exact file path that
  generate_filled_pdf returned, so the user gets a download link (not just a file path).
  Finally, tell the user their PDF is ready and to open the Artifacts panel to download it.
Be warm, clear, and never ask for everything at once."""
    + LANGUAGE_RULE
    + SECURITY_NOTE,
    sub_agents=[form_reader, data_collector],
    tools=[
        sugam_mcp_toolset(),
        deliver_pdf_for_download,
    ],
    before_model_callback=security_checkpoint,
)

# The ADK dev server (`adk web app`) and agent loader look for `root_agent`.
root_agent = orchestrator
