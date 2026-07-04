"""Deterministic red-flag rules. These run in code, not in the model, so the
same document always produces the same flags — the defensible core of the report."""


def evaluate(extraction: dict) -> list[dict]:
    flags = []

    deposit = extraction.get("deposit_percent")
    if isinstance(deposit, (int, float)):
        if deposit >= 50:
            flags.append(_flag(
                "Deposit over 50%",
                f"This quote asks for {deposit:.0f}% up front. Standard is 10-30%; "
                "many states cap deposits by law. Never pay more than a third before work starts.",
                "danger",
            ))
        elif deposit > 30:
            flags.append(_flag(
                "High deposit",
                f"A {deposit:.0f}% deposit is above the 10-30% standard. Negotiate it down "
                "or tie payments to completed milestones.",
                "warning",
            ))

    if not extraction.get("license_number"):
        flags.append(_flag(
            "No license number on the quote",
            "A legitimate contractor lists their license number. Ask for it and verify it "
            "with your state's contractor licensing board before signing.",
            "danger",
        ))

    if extraction.get("scope_vague"):
        flags.append(_flag(
            "Vague scope of work",
            'Language like "as needed" or "miscellaneous" lets the final bill grow. '
            "Ask for every task and material as a line item with its own price.",
            "warning",
        ))

    if not extraction.get("has_timeline"):
        flags.append(_flag(
            "No timeline",
            "The quote doesn't say when work starts or finishes. Get start and completion "
            "dates in writing.",
            "warning",
        ))

    items = extraction.get("line_items") or []
    total = extraction.get("total_amount")
    if isinstance(total, (int, float)) and total >= 1000 and len(items) <= 1:
        flags.append(_flag(
            "Single lump sum, no breakdown",
            "A four-figure job quoted as one number hides where the money goes. "
            "Request an itemized breakdown of labor and materials.",
            "warning",
        ))

    if extraction.get("pressure_language"):
        flags.append(_flag(
            "Pressure tactics",
            'Phrases like "price good today only" are a classic sign of an inflated quote. '
            "A fair price survives a week of thinking it over.",
            "warning",
        ))

    return flags


def _flag(title, detail, severity):
    return {"title": title, "detail": detail, "severity": severity, "source": "document"}
