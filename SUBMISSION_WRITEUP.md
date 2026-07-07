# Sugam Form Filler - Submission Writeup

## Problem Statement
Official paperwork in India (KYC, government schemes, bank forms) is intimidating — especially for
elderly citizens, first-time applicants, or people who are not comfortable in English. A single
wrong field can mean a rejected application. There is a real need for an accessible, conversational
interface that can look at a form, explain it in the user's **own language**, and guide them
through filling it out safely.

## Solution Architecture
Sugam is a **Google ADK multi-agent** system running on **Gemini 2.5 Flash** (vision-capable),
with an **MCP server** exposing domain tools.

```mermaid
graph TD
    User["User input (text · uploaded form · any language)"] --> Sec[Security Checkpoint - before_model_callback]
    Sec -- "clean" --> Orch[Orchestrator Agent]
    Sec -- "PII" --> Mask[Mask Aadhaar/PAN/Bank before LLM]
    Sec -- "injection / refusal" --> Block[Block + audit log]

    Orch -- "transfer_to_agent" --> FR[form_reader - vision]
    Orch -- "transfer_to_agent" --> DC[data_collector - conversational]

    FR -.-> MCP[MCP Server]
    Orch -.-> MCP
    MCP --> T1[parse_form_fields]
    MCP --> T2[lookup_govt_scheme]
    MCP --> T3[generate_filled_pdf]
```

## Concepts Used
- **ADK LlmAgent + sub-agents**: A root `orchestrator` coordinates two specialists — `form_reader`
  (reads uploaded documents with vision) and `data_collector` (gathers answers conversationally).
- **`transfer_to_agent` delegation**: The orchestrator hands control to a sub-agent via ADK's
  built-in transfer. Because a transferred sub-agent inherits the full session history, `form_reader`
  can see the uploaded image — something a text-only tool call cannot do.
- **`before_model_callback` security checkpoint**: Attached to all three agents, so PII masking and
  injection/consent checks run before *every* model call.
- **MCP Server** (`app/mcp_server.py`): Hosts real domain tools over stdio transport.
- **Multilingual instructions**: A shared language rule makes every agent reply in the user's
  language.

## Requirement Compliance (Concept Mapping)
Every mandatory concept is fulfilled with the current, stable ADK APIs. Where the original
scaffold targeted an experimental Workflow-graph API that did not run, the equivalent capability
is delivered with the supported mechanism:

| Mandatory concept | How Sugam fulfils it |
|---|---|
| **ADK Multi-Agent (2+ LlmAgents)** | `orchestrator` + `form_reader` + `data_collector` in `app/agent.py`. |
| **Orchestrator → sub-agent delegation** | ADK-native `sub_agents` + `transfer_to_agent` (forwards full context incl. uploaded images — an `AgentTool` text call cannot). |
| **Shared state / routing between agents** | Sub-agents share the ADK session/`InvocationContext`; the orchestrator + security callback implement the "gate then route" flow the graph was meant to express. |
| **MCP Server, 3+ tools, in 2+ agents** | `app/mcp_server.py` (stdio) with `parse_form_fields`, `lookup_govt_scheme`, `generate_filled_pdf`; `MCPToolset` wired into `orchestrator` and `form_reader`. |
| **Security checkpoint (PII + injection + audit)** | `security_checkpoint()` as a `before_model_callback` on all three agents — runs before *every* model call, stronger than a single graph node. |
| **Human-in-the-loop** | `data_collector` asks one field at a time via the chat turn loop. |
| **Agents CLI scaffold** | `agents-cli-manifest.yaml` + `GEMINI.md` present; `make playground` / `adk web app` runs. |

## Security Design
Handling sensitive user data requires strict guardrails, all implemented in `security_checkpoint`
in `app/agent.py`:
1. **PII Masking** — regexes detect and mask Aadhaar, PAN, and bank-account numbers, rewriting the
   request *in place* so the raw values never reach the LLM.
2. **Prompt-Injection Blocking** — keyword detection short-circuits with a "Security Policy
   Violation" response (returning an `LlmResponse` skips the model call entirely).
3. **Consent Enforcement** — a domain rule that blocks the flow if the user explicitly refuses
   consent.
4. **Audit Logging** — every decision is logged as JSON to `artifacts/audit.log` and streamed to
   the terminal, so redactions and blocks are visible live during a demo.

## MCP Server Design
`app/mcp_server.py` exposes three working tools:
- `parse_form_fields` — returns the real required-field list (with plain-language descriptions) for
  known forms (KYC, PAN, Aadhaar) from a curated knowledge base.
- `lookup_govt_scheme` — returns real benefit / eligibility / document details for common schemes
  (PM-KISAN, Ayushman Bharat, PMAY, Ujjwala, Sukanya Samriddhi), with fuzzy name matching.
- `generate_filled_pdf` — generates an actual PDF (via `fpdf2`) from the collected data and saves it
  to `artifacts/`, with Unicode-font support so native-language values render.

## Vision + Multilingual Flow
- **Vision**: When the user uploads a form, the orchestrator transfers to `form_reader`, whose
  Gemini model reads the actual document and explains each field.
- **Native language**: The user can converse in Hindi, Tamil, Bengali, and other Indian languages;
  explanations, questions, and messages all come back in that language.

## Human-in-the-Loop Flow
`data_collector` asks for one field at a time and waits for the user's reply in the chat UI, rather
than requesting twenty fields at once — a genuine step-by-step HITL experience. When collection is
complete it transfers back to the orchestrator to generate the PDF.

## Demo Walkthrough
1. **Upload + native language** — user uploads a KYC form and asks in Hindi; `form_reader` reads it
   with vision and explains the fields in Hindi.
2. **Conversational collection** — `data_collector` gathers details one field at a time.
3. **PII masking** — an Aadhaar number in the input is redacted before the LLM sees it.
4. **Injection/consent block** — a bypass/refusal attempt is stopped with a Security Policy Violation.
5. **Real PDF** — `generate_filled_pdf` writes a downloadable PDF to `artifacts/`.

## What is Real vs. Representative
- **Real**: vision reading, multilingual conversation, multi-agent delegation, PII masking,
  injection/consent blocking, audit logging, the three MCP tools, and PDF generation.
- **Representative**: the form/scheme catalogs are a curated **offline** knowledge base (not a live
  government API); the generated PDF is a clean labelled data sheet of collected fields (not a
  pixel-perfect overlay of the original form layout).

## Impact / Value Statement
Sugam turns an intimidating bureaucratic wall into a short conversation in the user's own language,
with personal data protected throughout. It blends vision, an accessible multilingual chat
interface, and strict PII safety to help users of any technical skill independently navigate
everyday paperwork.
