"""
Validation step for the invoice pipeline.

This is a different layer of checking than what's already happened
earlier in the pipeline:
- pdf_preprocessor.py checks if the FILE is readable
- models.py (Pydantic) checks if the DATA TYPES are correct
- invoice_transformer.py checks if the MATH is internally consistent

This file checks if the data is PLAUSIBLE from a business standpoint -
a value can be the right type and the math can add up perfectly, but
still not make business sense (e.g. an invoice dated in 2099, or a
35% VAT rate that doesn't exist in Germany).

I return a separate ValidationResult rather than adding a status field
onto Invoice itself - same pattern as ExtractionResult in models.py.
The Invoice represents the document and what was extracted from it;
ValidationResult represents my pipeline's judgment about that data.
"""

import logging
from dataclasses import dataclass, field
from datetime import date, timedelta

from config.settings import CONFIDENCE_THRESHOLD
from src.models import Invoice

logger = logging.getLogger(__name__)

# German VAT rates as of writing - the standard rate is 19%, the
# reduced rate (food, books, public transport, etc.) is 7%, and 0% is
# valid for some exports/exempt cases. Anything else on a German
# invoice is suspicious and worth flagging.
VALID_GERMAN_VAT_RATES = {0.0, 0.07, 0.19}
VAT_RATE_TOLERANCE = 0.005  # allow tiny floating point drift around the exact rate

# An invoice from before the year 2000 or more than a year in the
# future is almost certainly an extraction error (e.g. OCR misread
# the year), not a real business document.
MIN_PLAUSIBLE_YEAR = 2000


@dataclass
class ValidationResult:
    """
    Outcome of running plausibility checks on one invoice.

    status is "valid" if nothing suspicious was found, or
    "needs_review" if any check failed or confidence was too low.
    issues lists exactly what triggered that status, in plain English,
    so a human reviewer knows what to look at without re-deriving it.
    """

    status: str  # "valid" or "needs_review"
    issues: list = field(default_factory=list)


def validate_invoice(invoice: Invoice) -> ValidationResult:
    """
    Run plausibility checks on a transformed Invoice and decide whether
    it's safe to trust or whether a human should look at it.
    """

    issues: list = []

    # --- Confidence check ---
    # If Azure itself wasn't confident, or the transformer already
    # found math that doesn't add up, that's reason enough on its own
    # to flag this for review - I don't need to duplicate that warning
    # text here, just fold it into the decision.
    if invoice.confidence_score < CONFIDENCE_THRESHOLD:
        issues.append(f"Confidence score {invoice.confidence_score} is below threshold {CONFIDENCE_THRESHOLD}")

    if invoice.extraction_warnings:
        issues.append(f"{len(invoice.extraction_warnings)} extraction/transformation warning(s) present")

    # --- Date plausibility ---
    issues.extend(_check_dates(invoice))

    # --- VAT rate plausibility ---
    issues.extend(_check_vat_rate(invoice))

    # --- Amount plausibility ---
    issues.extend(_check_amounts(invoice))

    status = "needs_review" if issues else "valid"

    logger.info(f"Validated {invoice.source_file}: status={status}, {len(issues)} issue(s)")

    return ValidationResult(status=status, issues=issues)


def _check_dates(invoice: Invoice) -> list:
    """Required fields and value ranges for the two date fields."""
    issues = []

    if invoice.invoice_date.year < MIN_PLAUSIBLE_YEAR:
        issues.append(f"invoice_date year {invoice.invoice_date.year} looks implausible")

    if invoice.invoice_date > date.today() + timedelta(days=1):
        # +1 day tolerance for timezone edge cases, not strict same-day
        issues.append(f"invoice_date {invoice.invoice_date} is in the future")

    if invoice.due_date is not None and invoice.due_date < invoice.invoice_date:
        issues.append(
            f"due_date {invoice.due_date} is before invoice_date {invoice.invoice_date} - dates may be swapped"
        )

    return issues


def _check_vat_rate(invoice: Invoice) -> list:
    """Plausibility check for German VAT rates specifically."""
    issues = []

    if invoice.vat_rate is None:
        return issues  # nothing to check, vat_rate is optional

    is_known_rate = any(
        abs(invoice.vat_rate - valid_rate) <= VAT_RATE_TOLERANCE
        for valid_rate in VALID_GERMAN_VAT_RATES
    )
    if not is_known_rate:
        issues.append(
            f"vat_rate {invoice.vat_rate:.3f} does not match a standard German rate (0%, 7%, 19%)"
        )

    return issues


def _check_amounts(invoice: Invoice) -> list:
    """Required fields and value ranges for monetary amounts."""
    issues = []

    if invoice.total_amount <= 0:
        issues.append(f"total_amount {invoice.total_amount} is not a positive value")

    if not invoice.line_items:
        issues.append("Invoice has no line items")

    return issues