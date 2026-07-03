"""Three-stage analysis pipeline:
1. extract  — Claude reads the quote (image/PDF/text) into structured JSON
2. research — Claude with web_search checks the contractor and local prices
3. compose  — Claude merges extraction + deterministic rules + research into the report
"""
import base64
import json
from typing import Optional
import logging

import anthropic

from . import rules
from .config import settings

log = logging.getLogger("contrax.analyzer")


class AnalysisError(Exception):
    pass


EXTRACTION_SCHEMA = {
    "type": "object",
    "properties": {
        "contractor_name": {"type": ["string", "null"]},
        "license_number": {"type": ["string", "null"]},
        "total_amount": {"type": ["number", "null"]},
        "deposit_percent": {"type": ["number", "null"]},
        "line_items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "description": {"type": "string"},
                    "amount": {"type": ["number", "null"]},
                },
                "required": ["description", "amount"],
                "additionalProperties": False,
            },
        },
        "scope_vague": {"type": "boolean"},
        "has_timeline": {"type": "boolean"},
        "has_permit_line": {"type": "boolean"},
        "pressure_language": {"type": "boolean"},
        "summary": {"type": "string"},
    },
    "required": [
        "contractor_name", "license_number", "total_amount", "deposit_percent",
        "line_items", "scope_vague", "has_timeline", "has_permit_line",
        "pressure_language", "summary",
    ],
    "additionalProperties": False,
}

REPORT_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["fair", "negotiate", "caution"]},
        "headline": {"type": "string"},
        "quote_total": {"type": ["number", "null"]},
        "local_range_low": {"type": ["number", "null"]},
        "local_range_high": {"type": ["number", "null"]},
        "price_basis": {"type": "string"},
        "price_confidence": {"type": "string", "enum": ["low", "medium", "high"]},
        "red_flags": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "title": {"type": "string"},
                    "detail": {"type": "string"},
                    "severity": {"type": "string", "enum": ["warning", "danger"]},
                },
                "required": ["title", "detail", "severity"],
                "additionalProperties": False,
            },
        },
        "research_findings": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "finding": {"type": "string"},
                    "source": {"type": "string"},
                },
                "required": ["finding", "source"],
                "additionalProperties": False,
            },
        },
        "counter_offer_message": {"type": "string"},
        "questions_to_ask": {"type": "array", "items": {"type": "string"}},
    },
    "required": [
        "verdict", "headline", "quote_total", "local_range_low", "local_range_high",
        "price_basis", "price_confidence", "red_flags", "research_findings",
        "counter_offer_message", "questions_to_ask",
    ],
    "additionalProperties": False,
}


def _client() -> anthropic.Anthropic:
    if not settings.anthropic_api_key:
        raise AnalysisError("ANTHROPIC_API_KEY is not configured")
    return anthropic.Anthropic(api_key=settings.anthropic_api_key)


def _text_of(response) -> str:
    if response.stop_reason == "refusal":
        raise AnalysisError("The model declined to analyze this document.")
    return "".join(b.text for b in response.content if b.type == "text")


def _quote_content_block(file_bytes: Optional[bytes], file_mime: Optional[str]):
    if not file_bytes:
        return None
    data = base64.standard_b64encode(file_bytes).decode()
    if file_mime == "application/pdf":
        return {"type": "document", "source": {"type": "base64", "media_type": "application/pdf", "data": data}}
    if file_mime in ("image/jpeg", "image/png", "image/gif", "image/webp"):
        return {"type": "image", "source": {"type": "base64", "media_type": file_mime, "data": data}}
    raise AnalysisError(f"Unsupported file type: {file_mime}. Send a photo, PDF, or plain text.")


def extract(client, file_bytes, file_mime, quote_text, trade) -> dict:
    content = []
    block = _quote_content_block(file_bytes, file_mime)
    if block:
        content.append(block)
    instruction = (
        f"This is a contractor quote for a {trade} job. Extract its contents faithfully. "
        "Set scope_vague true if any work is described with open-ended language "
        '("as needed", "misc", "TBD"). Set pressure_language true for urgency tactics. '
        "Use null for anything not present in the document — do not guess."
    )
    if quote_text:
        instruction += f"\n\nQuote text:\n{quote_text}"
    content.append({"type": "text", "text": instruction})

    resp = client.messages.create(
        model=settings.extraction_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": EXTRACTION_SCHEMA}},
        messages=[{"role": "user", "content": content}],
    )
    return json.loads(_text_of(resp))


def research(client, extraction: dict, zip_code: str, trade: str) -> str:
    contractor = extraction.get("contractor_name") or "the contractor"
    prompt = (
        f"You are researching a {trade} quote for a homeowner in zip code {zip_code}, USA.\n"
        f"Contractor: {contractor}. License number on quote: {extraction.get('license_number') or 'none listed'}. "
        f"Quote total: {extraction.get('total_amount')}.\n\n"
        "Research and report, citing sources:\n"
        f"1. Typical price range for this job near {zip_code} (cost guides, published data).\n"
        f"2. Whether {contractor} appears in state license records, and license status if findable.\n"
        f"3. Complaints or reviews (BBB, Google) for {contractor} near {zip_code}.\n"
        "Only state what the sources support; say explicitly when something could not be verified."
    )
    messages = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20260209", "name": "web_search", "max_uses": 6}]

    resp = client.messages.create(
        model=settings.research_model, max_tokens=16000,
        thinking={"type": "adaptive"}, tools=tools, messages=messages,
    )
    for _ in range(4):
        if resp.stop_reason != "pause_turn":
            break
        messages = [{"role": "user", "content": prompt}, {"role": "assistant", "content": resp.content}]
        resp = client.messages.create(
            model=settings.research_model, max_tokens=16000,
            thinking={"type": "adaptive"}, tools=tools, messages=messages,
        )
    return _text_of(resp)


def compose(client, extraction, rule_flags, research_text, zip_code, trade) -> dict:
    prompt = (
        "Compose a Contrax quote-analysis report for a homeowner. Plain, warm, non-technical "
        "English — the reader may be elderly and anxious.\n\n"
        f"Job: {trade} in zip {zip_code}.\n"
        f"Extracted quote data:\n{json.dumps(extraction)}\n\n"
        f"Red flags found by deterministic document rules (include ALL of these in red_flags, "
        f"rewritten warmly but factually; you may add others only if clearly supported):\n"
        f"{json.dumps(rule_flags)}\n\n"
        f"Web research findings:\n{research_text}\n\n"
        "Rules:\n"
        "- Price range: only from the research; if the data is thin, use wide bounds and "
        "price_confidence 'low', and say so in price_basis. Never invent a range.\n"
        "- Verdict: 'fair' if price in range and no danger flags; 'caution' if danger flags or "
        "far above range; else 'negotiate'.\n"
        "- counter_offer_message: a short, polite, ready-to-send text message from the homeowner "
        "to the contractor. Reference the local range only if confidence is medium/high; always "
        "address deposit and itemization if flagged.\n"
        "- questions_to_ask: 3-5 short questions.\n"
        "- research_findings: each with its source; include unverifiable items honestly."
    )
    resp = client.messages.create(
        model=settings.extraction_model,
        max_tokens=8000,
        thinking={"type": "adaptive"},
        output_config={"format": {"type": "json_schema", "schema": REPORT_SCHEMA}},
        messages=[{"role": "user", "content": prompt}],
    )
    return json.loads(_text_of(resp))


def analyze(file_bytes, file_mime, quote_text, zip_code, trade) -> dict:
    if settings.mock_analysis:
        return _mock_report()
    client = _client()
    extraction = extract(client, file_bytes, file_mime, quote_text, trade)
    log.info("extraction done: contractor=%s total=%s", extraction.get("contractor_name"), extraction.get("total_amount"))
    rule_flags = rules.evaluate(extraction)
    research_text = research(client, extraction, zip_code, trade)
    log.info("research done (%d chars)", len(research_text))
    report = compose(client, extraction, rule_flags, research_text, zip_code, trade)
    report["extraction"] = extraction
    return report


def _mock_report() -> dict:
    return {
        "verdict": "negotiate",
        "headline": "3 red flags — negotiate before signing",
        "quote_total": 2000,
        "local_range_low": 650,
        "local_range_high": 1100,
        "price_basis": "MOCK MODE — illustrative data, not real research.",
        "price_confidence": "medium",
        "red_flags": [
            {"title": "Deposit over 50%", "detail": "Standard is 10-30%.", "severity": "danger"},
            {"title": "No license number on the quote", "detail": "Verify with the state board.", "severity": "danger"},
            {"title": "Vague scope of work", "detail": '"Materials as needed" is open-ended.', "severity": "warning"},
        ],
        "research_findings": [
            {"finding": "License status could not be verified (mock).", "source": "mock"},
        ],
        "counter_offer_message": (
            "Hi — thanks for the quote. Comparable repairs in this area run $650-$1,100, so $2,000 "
            "is above range. I can move forward this week at $1,150 with a 20% deposit and the "
            "scope itemized. Does that work?"
        ),
        "questions_to_ask": [
            "What is your license number?",
            "Can you itemize labor and materials?",
            "Is a permit required for this job, and who pulls it?",
        ],
    }
