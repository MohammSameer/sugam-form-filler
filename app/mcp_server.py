import os
import re
import json
import datetime

# Import the (heavy) PDF/font stack at MODULE LOAD — before stdio_server() takes
# over stdout. Importing fpdf -> fontTools -> Pillow lazily inside the tool
# handler deadlocks the stdio JSON-RPC transport on Windows (the C-extension
# import races the asyncio stdout reader), which surfaced as a 30s tool timeout.
from fpdf import FPDF

from mcp.server import Server, NotificationOptions
from mcp.server.stdio import stdio_server
from mcp.server.models import InitializationOptions
from mcp.types import Tool, TextContent

server = Server("sugam-mcp-server")

# --------------------------------------------------------------------------- #
# Paths — write generated PDFs into <project_root>/artifacts/
# --------------------------------------------------------------------------- #
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_ARTIFACTS_DIR = os.path.join(_PROJECT_ROOT, "artifacts")

# Fonts that support Indic / Unicode scripts, tried in order. Falls back to a
# built-in Latin font if none are present.
_UNICODE_FONT_CANDIDATES = [
    r"C:\Windows\Fonts\Nirmala.ttc",   # Windows 11: Nirmala UI *collection* — covers Devanagari, Tamil, Telugu, etc.
    r"C:\Windows\Fonts\Nirmala.ttf",   # older Windows layout (single-file variant)
    r"C:\Windows\Fonts\mangal.ttf",    # Devanagari
    r"C:\Windows\Fonts\ARIALUNI.TTF",  # Arial Unicode MS
    "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
]

# --------------------------------------------------------------------------- #
# Real reference data (offline knowledge base) for named forms & schemes.
# --------------------------------------------------------------------------- #
FORM_CATALOG = {
    "KYC": [
        ("Full Name", "Your name exactly as printed on your official ID."),
        ("Father's / Spouse's Name", "Name of your father or spouse."),
        ("Date of Birth", "Your birth date in DD/MM/YYYY format."),
        ("Gender", "Male, Female, or Other."),
        ("PAN Number", "Your 10-character Permanent Account Number."),
        ("Aadhaar Number", "Your 12-digit Aadhaar number."),
        ("Address", "Your full residential address with PIN code."),
        ("Mobile Number", "An active 10-digit mobile number."),
        ("Email ID", "A valid email address (optional)."),
    ],
    "PAN": [
        ("Full Name", "Applicant's full name as it should appear on the PAN card."),
        ("Father's Name", "Father's full name (mandatory even for married women)."),
        ("Date of Birth", "Date of birth in DD/MM/YYYY."),
        ("Aadhaar Number", "12-digit Aadhaar for e-KYC."),
        ("Address", "Residential or office address."),
        ("Source of Income", "Salary, business, or other income source."),
    ],
    "AADHAAR": [
        ("Full Name", "Resident's name in English and local language."),
        ("Date of Birth", "Verified or declared date of birth."),
        ("Gender", "Male, Female, or Transgender."),
        ("Address", "Current residential address with proof."),
        ("Mobile Number", "For OTP-based verification."),
        ("Biometrics", "Fingerprints and iris scan captured at the centre."),
    ],
}

SCHEME_CATALOG = {
    "PM-KISAN": {
        "full_name": "Pradhan Mantri Kisan Samman Nidhi",
        "benefit": "Rs. 6,000 per year paid in three equal instalments to eligible farmer families.",
        "eligibility": "Small and marginal farmer families owning cultivable land.",
        "documents": "Aadhaar, land records, and bank account details.",
    },
    "AYUSHMAN BHARAT": {
        "full_name": "Ayushman Bharat - Pradhan Mantri Jan Arogya Yojana (PMJAY)",
        "benefit": "Health cover of up to Rs. 5 lakh per family per year for secondary and tertiary care.",
        "eligibility": "Families identified as deprived under the SECC 2011 database.",
        "documents": "Aadhaar and ration card / SECC verification.",
    },
    "PMAY": {
        "full_name": "Pradhan Mantri Awas Yojana",
        "benefit": "Financial assistance / interest subsidy to build or buy a house.",
        "eligibility": "EWS, LIG and MIG households without a pucca house.",
        "documents": "Aadhaar, income certificate, and bank details.",
    },
    "UJJWALA": {
        "full_name": "Pradhan Mantri Ujjwala Yojana",
        "benefit": "Free LPG connection with financial support to below-poverty-line households.",
        "eligibility": "Adult women from BPL households without an existing LPG connection.",
        "documents": "Aadhaar, BPL ration card, and bank account details.",
    },
    "SUKANYA SAMRIDDHI": {
        "full_name": "Sukanya Samriddhi Yojana",
        "benefit": "High-interest small savings account for a girl child with tax benefits.",
        "eligibility": "Girl child below 10 years of age; account opened by parent/guardian.",
        "documents": "Girl's birth certificate, guardian's ID and address proof.",
    },
}


def _normalise(key: str) -> str:
    return re.sub(r"[\s_\-]+", " ", key.strip().upper())


# Normalised lookup tables so "pm kisan", "PM-KISAN", "pm_kisan" all match.
_FORM_LOOKUP = {_normalise(k): v for k, v in FORM_CATALOG.items()}
_SCHEME_LOOKUP = {_normalise(k): v for k, v in SCHEME_CATALOG.items()}

# Common alternate names / synonyms for schemes.
_SCHEME_ALIASES = {
    "PMJAY": "AYUSHMAN BHARAT",
    "AYUSHMAN": "AYUSHMAN BHARAT",
    "AYUSHMAN BHARAT PMJAY": "AYUSHMAN BHARAT",
    "PM KISAN SAMMAN NIDHI": "PM-KISAN",
    "KISAN": "PM-KISAN",
    "PM AWAS YOJANA": "PMAY",
    "AWAS": "PMAY",
    "SUKANYA": "SUKANYA SAMRIDDHI",
    "SUKANYA SAMRIDDHI YOJANA": "SUKANYA SAMRIDDHI",
    "UJJWALA YOJANA": "UJJWALA",
    "LPG": "UJJWALA",
}


# --------------------------------------------------------------------------- #
# Tool declarations
# --------------------------------------------------------------------------- #
@server.list_tools()
async def handle_list_tools() -> list[Tool]:
    return [
        Tool(
            name="parse_form_fields",
            description="Returns the real list of required fields (with plain-language descriptions) for a known official form.",
            inputSchema={
                "type": "object",
                "properties": {
                    "form_id": {"type": "string", "description": "Form name, e.g. 'KYC', 'PAN', 'AADHAAR'"}
                },
                "required": ["form_id"],
            },
        ),
        Tool(
            name="lookup_govt_scheme",
            description="Looks up real eligibility criteria, benefits and required documents for a government scheme.",
            inputSchema={
                "type": "object",
                "properties": {
                    "scheme_name": {"type": "string", "description": "Scheme name, e.g. 'PM-KISAN', 'Ayushman Bharat'"}
                },
                "required": ["scheme_name"],
            },
        ),
        Tool(
            name="generate_filled_pdf",
            description="Generates a real filled PDF from collected user data and saves it to the artifacts folder. Returns the file path.",
            inputSchema={
                "type": "object",
                "properties": {
                    "form_id": {"type": "string", "description": "The form name, e.g. 'KYC'"},
                    "user_data": {"type": "string", "description": "JSON object (as a string) of field name -> value"},
                },
                "required": ["form_id", "user_data"],
            },
        ),
    ]


# --------------------------------------------------------------------------- #
# Tool implementations
# --------------------------------------------------------------------------- #
def _build_pdf(form_id: str, data: dict) -> str:
    """Render a real, well-formatted PDF and return its absolute path."""
    os.makedirs(_ARTIFACTS_DIR, exist_ok=True)

    pdf = FPDF()
    pdf.add_page()

    # Register a Unicode font when available so native-language values render.
    font = "helvetica"
    unicode_ok = False
    for path in _UNICODE_FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                pdf.add_font("uni", "", path)
                pdf.add_font("uni", "B", path)
                font = "uni"
                unicode_ok = True
                break
            except Exception:
                continue

    def text(value: str) -> str:
        # If we only have a Latin font, drop characters it cannot encode.
        if unicode_ok:
            return value
        return value.encode("latin-1", "replace").decode("latin-1")

    pdf.set_font(font, "B", 16)
    pdf.cell(0, 12, text(f"{form_id.upper()} - Filled Application"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_font(font, "", 10)
    stamp = datetime.datetime.now().strftime("%d %b %Y, %H:%M")
    pdf.set_text_color(110, 110, 110)
    pdf.cell(0, 8, text(f"Generated by Sugam Form Filler on {stamp}"), new_x="LMARGIN", new_y="NEXT")
    pdf.set_text_color(0, 0, 0)
    pdf.ln(4)

    for key, value in data.items():
        label = str(key).replace("_", " ").title()
        pdf.set_font(font, "B", 11)
        pdf.multi_cell(0, 8, text(f"{label}:"), new_x="LMARGIN", new_y="NEXT")
        pdf.set_font(font, "", 11)
        pdf.multi_cell(0, 8, text(str(value)), new_x="LMARGIN", new_y="NEXT")
        pdf.ln(1)

    safe_id = re.sub(r"[^A-Za-z0-9]+", "_", form_id).strip("_") or "form"
    filename = f"filled_{safe_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.pdf"
    out_path = os.path.join(_ARTIFACTS_DIR, filename)
    pdf.output(out_path)
    return out_path


@server.call_tool()
async def handle_call_tool(name: str, arguments: dict | None) -> list[TextContent]:
    arguments = arguments or {}

    if name == "parse_form_fields":
        form_id = arguments.get("form_id", "")
        fields = _FORM_LOOKUP.get(_normalise(form_id))
        if not fields:
            known = ", ".join(sorted(FORM_CATALOG))
            return [TextContent(
                type="text",
                text=(f"I don't have a stored template for '{form_id}'. "
                      f"Known forms: {known}. If you have the form, please upload it and I will read it directly."),
            )]
        lines = "\n".join(f"{i}. {label} - {desc}" for i, (label, desc) in enumerate(fields, 1))
        return [TextContent(type="text", text=f"Required fields for {form_id.upper()}:\n{lines}")]

    if name == "lookup_govt_scheme":
        scheme_name = arguments.get("scheme_name", "")
        key = _normalise(scheme_name)
        key = _SCHEME_ALIASES.get(key, key)
        scheme = _SCHEME_LOOKUP.get(key)
        if not scheme:
            known = ", ".join(sorted(SCHEME_CATALOG))
            return [TextContent(
                type="text",
                text=f"I don't have details for '{scheme_name}'. Known schemes: {known}.",
            )]
        return [TextContent(
            type="text",
            text=(f"{scheme['full_name']}\n"
                  f"- Benefit: {scheme['benefit']}\n"
                  f"- Eligibility: {scheme['eligibility']}\n"
                  f"- Documents needed: {scheme['documents']}"),
        )]

    if name == "generate_filled_pdf":
        form_id = arguments.get("form_id", "form")
        raw = arguments.get("user_data", "{}")
        try:
            data = json.loads(raw) if isinstance(raw, str) else dict(raw)
            if not isinstance(data, dict):
                raise ValueError("user_data must be a JSON object of field -> value")
        except (json.JSONDecodeError, ValueError) as exc:
            return [TextContent(type="text", text=f"ERROR: could not parse user_data ({exc}). Expected a JSON object.")]
        if not data:
            return [TextContent(type="text", text="ERROR: no user data was provided, so there is nothing to fill.")]
        try:
            path = _build_pdf(form_id, data)
        except Exception as exc:  # pragma: no cover - surfaced to the agent
            return [TextContent(type="text", text=f"ERROR generating PDF: {exc}")]
        return [TextContent(
            type="text",
            text=f"SUCCESS: filled {form_id.upper()} PDF generated with {len(data)} field(s) and saved at:\n{path}",
        )]

    raise ValueError(f"Unknown tool: {name}")


async def main():
    async with stdio_server() as (read_stream, write_stream):
        await server.run(
            read_stream,
            write_stream,
            InitializationOptions(
                server_name="sugam-mcp",
                server_version="1.0.0",
                capabilities=server.get_capabilities(
                    notification_options=NotificationOptions(),
                    experimental_capabilities={},
                ),
            ),
        )


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
