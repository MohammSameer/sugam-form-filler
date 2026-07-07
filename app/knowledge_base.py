"""Shared, self-populating knowledge base for Sugam.

Every lookup (government scheme *or* named-form field list) is backed by two tiers:

  1. SEED_* — a small, curated, authoritative catalog compiled into the code.
     These are hand-verified and always win over anything auto-discovered.
  2. A JSON store on disk (``artifacts/kb/*.json``) that the agent's grounded
     research tools write to whenever something is NOT in the seed. The first
     person to ask about an unknown scheme pays for one live lookup; everyone
     after gets an instant cache hit — including the separate MCP stdio
     subprocess, which reads the very same store.

This turns the old hardcoded dicts from a *gate* ("I don't have that") into a
*cache* that grows over time and never permanently dead-ends.

Design constraint: this module is imported by ``mcp_server.py`` at module load,
inside its stdio JSON-RPC transport, where a heavy C-extension import can
deadlock the server. So it stays deliberately stdlib-only (json / os / re /
datetime) — all network + LLM work lives in ``agent.py`` and only ever calls
``remember_*`` here to persist a validated result.
"""

from __future__ import annotations

import io
import os
import re
import json
import datetime
from typing import Optional

# --------------------------------------------------------------------------- #
# Tier 1 — curated seed catalog (authoritative, always preferred)
# --------------------------------------------------------------------------- #
SEED_FORMS: dict[str, list[tuple[str, str]]] = {
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

SEED_SCHEMES: dict[str, dict[str, str]] = {
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

# Common alternate names / synonyms, resolved to a canonical seed key.
SCHEME_ALIASES = {
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

SCHEME_FIELDS = ("full_name", "benefit", "eligibility", "documents")

# --------------------------------------------------------------------------- #
# Tier 2 — self-populating JSON store (written by the grounded research tools)
# --------------------------------------------------------------------------- #
_PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
_KB_DIR = os.path.join(_PROJECT_ROOT, "artifacts", "kb")
_SCHEMES_STORE = os.path.join(_KB_DIR, "schemes.json")
_FORMS_STORE = os.path.join(_KB_DIR, "forms.json")


def _normalise(key: str) -> str:
    """Canonical form so 'pm kisan', 'PM-KISAN', 'pm_kisan' all collapse together."""
    return re.sub(r"[\s_\-]+", " ", (key or "").strip().upper())


def _resolve_scheme_key(name: str) -> str:
    key = _normalise(name)
    return SCHEME_ALIASES.get(key, key)


# Seed lookups keyed by their normalised name (built once at import).
_SEED_SCHEME_LOOKUP = {_normalise(k): v for k, v in SEED_SCHEMES.items()}
_SEED_FORM_LOOKUP = {_normalise(k): v for k, v in SEED_FORMS.items()}


def _load_store(path: str) -> dict:
    """Read a JSON store, tolerating a missing or half-written file (returns {})."""
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return {}


def _save_store(path: str, data: dict) -> None:
    """Atomically overwrite a JSON store (temp file + os.replace).

    Atomic on Windows too, so the MCP subprocess never reads a half-written file
    while the agent process is persisting a freshly-researched entry.
    """
    os.makedirs(os.path.dirname(path), exist_ok=True)
    tmp = f"{path}.{os.getpid()}.tmp"
    with io.open(tmp, "w", encoding="utf-8") as fh:
        json.dump(data, fh, ensure_ascii=False, indent=2)
    os.replace(tmp, path)


# --------------------------------------------------------------------------- #
# Public API — schemes
# --------------------------------------------------------------------------- #
def lookup_scheme(name: str) -> Optional[dict]:
    """Return a scheme entry (seed first, then the learned store) or None.

    A returned dict always has the four SCHEME_FIELDS. Curated seed hits carry
    ``origin='curated'``; learned hits carry ``origin='grounded'`` plus whatever
    ``sources`` / ``retrieved_at`` were recorded when they were researched.
    """
    key = _resolve_scheme_key(name)

    seed = _SEED_SCHEME_LOOKUP.get(key)
    if seed:
        return {**seed, "origin": "curated"}

    entry = _load_store(_SCHEMES_STORE).get(key)
    if entry and all(entry.get(f) for f in ("full_name", "benefit")):
        return {"origin": "grounded", **entry}
    return None


def remember_scheme(name: str, entry: dict) -> None:
    """Persist a researched scheme into the learned store (idempotent overwrite).

    Curated seed entries are never overwritten — they stay authoritative — so a
    name that already resolves to a seed is a no-op here.
    """
    key = _resolve_scheme_key(name)
    if key in _SEED_SCHEME_LOOKUP:
        return
    clean = {f: str(entry.get(f, "") or "").strip() for f in SCHEME_FIELDS}
    if not clean["full_name"] or not clean["benefit"]:
        raise ValueError("refusing to store a scheme without a name and benefit")
    sources = [str(s).strip() for s in (entry.get("sources") or []) if str(s).strip()]
    clean["sources"] = sources[:5]
    clean["retrieved_at"] = datetime.datetime.now().isoformat(timespec="seconds")

    store = _load_store(_SCHEMES_STORE)
    store[key] = clean
    _save_store(_SCHEMES_STORE, store)


def known_scheme_names() -> list[str]:
    """All scheme names we can answer instantly (curated seeds + learned)."""
    learned = [e.get("full_name") or k for k, e in _load_store(_SCHEMES_STORE).items()]
    return sorted({*SEED_SCHEMES.keys(), *learned})


# --------------------------------------------------------------------------- #
# Public API — named forms (field lists)
# --------------------------------------------------------------------------- #
def lookup_form(name: str) -> Optional[list[tuple[str, str]]]:
    """Return a form's [(label, description), ...] (seed first, then learned)."""
    key = _normalise(name)

    seed = _SEED_FORM_LOOKUP.get(key)
    if seed:
        return list(seed)

    entry = _load_store(_FORMS_STORE).get(key)
    if entry and isinstance(entry.get("fields"), list) and entry["fields"]:
        return [
            (str(f.get("label", "")).strip(), str(f.get("description", "")).strip())
            for f in entry["fields"]
            if str(f.get("label", "")).strip()
        ] or None
    return None


def remember_form(name: str, fields: list) -> None:
    """Persist a researched form field list into the learned store.

    ``fields`` is a list of {"label", "description"} dicts (or (label, desc)
    tuples). Seed forms are authoritative and never overwritten.
    """
    key = _normalise(name)
    if key in _SEED_FORM_LOOKUP:
        return

    norm: list[dict] = []
    for f in fields or []:
        if isinstance(f, (list, tuple)):
            label, desc = (f + ("", ""))[:2]
        else:
            label, desc = f.get("label", ""), f.get("description", "")
        label = str(label or "").strip()
        if label:
            norm.append({"label": label, "description": str(desc or "").strip()})
    if not norm:
        raise ValueError("refusing to store a form with no usable fields")

    store = _load_store(_FORMS_STORE)
    store[key] = {
        "fields": norm,
        "retrieved_at": datetime.datetime.now().isoformat(timespec="seconds"),
    }
    _save_store(_FORMS_STORE, store)


def known_form_names() -> list[str]:
    """All form names we have a stored field template for (seeds + learned)."""
    learned = list(_load_store(_FORMS_STORE).keys())
    return sorted({*SEED_FORMS.keys(), *learned})
