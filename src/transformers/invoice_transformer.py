"""
Transformation step for the invoice pipeline.

Azure Document Intelligence already gives me clean Python types (real
date objects, real Decimal numbers) instead of raw OCR text, so I don't
need to do date-format parsing or currency-string parsing here like I
would with a regex/OCR-only approach. Instead this module focuses on
two things:

1. Cleaning - trimming whitespace and normalizing text fields
2. Cross-checking (enrichment) - does the math in the invoice actually
   add up? (subtotal + VAT = total, and quantity * unit_price =
   line_total for each line item, and line items sum to the subtotal).
   This adds a genuinely new signal - extraction trustworthiness -
   that wasn't on the original document, which is what enrichment
   means here. It's also a good way to catch extraction mistakes.

Input and output are both Invoice objects - this function doesn't
change the schema, it returns a cleaned/enriched version of the same
shape.
"""

import logging
from decimal import Decimal

from src.models import Invoice

logger = logging.getLogger(__name__)

# Small mismatches between Azure's total and my own recalculated total
# are normal - VAT rounding differs depending on whether it's applied
# per line item or on the subtotal as a whole. Anything under this
# tolerance gets ignored. Anything over it gets flagged as a warning,
# since it could mean a line item was misread.
ROUNDING_TOLERANCE = Decimal("0.05")  # 5 cents


def transform_invoice(invoice: Invoice) -> Invoice:
    """
    Clean and enrich a single Invoice, returning a new Invoice object.

    I'm not mutating the input in place - I build a fresh dict of
    changes and construct a new Invoice from it, so the original
    extracted object stays untouched in case I ever want to compare
    "before vs after transformation" for debugging.
    """

    new_warnings = list(invoice.extraction_warnings)  # copy, don't mutate original

    # --- 1. Clean text fields ---
    cleaned_vendor_name = _clean_text(invoice.vendor_name)
    cleaned_customer_name = _clean_text(invoice.customer_name)
    cleaned_vendor_address = _clean_text(invoice.vendor_address)
    cleaned_customer_address = _clean_text(invoice.customer_address)

    # --- 2. Cross-check line item math ---
    for item in invoice.line_items:
        expected_total = (Decimal(str(item.quantity)) * item.unit_price).quantize(Decimal("0.01"))
        actual_total = item.line_total.quantize(Decimal("0.01"))
        diff = abs(expected_total - actual_total)
        if diff > ROUNDING_TOLERANCE:
            new_warnings.append(
                f"Line item {item.position} ('{item.description}'): "
                f"quantity x unit_price = {expected_total}, but extracted line_total = {actual_total}"
            )

    # --- 3. Cross-check subtotal + VAT = total ---
    if invoice.subtotal is not None and invoice.vat_amount is not None:
        expected_total = (invoice.subtotal + invoice.vat_amount).quantize(Decimal("0.01"))
        actual_total = invoice.total_amount.quantize(Decimal("0.01"))
        diff = abs(expected_total - actual_total)
        if diff > ROUNDING_TOLERANCE:
            new_warnings.append(
                f"subtotal + VAT = {expected_total}, but extracted total_amount = {actual_total} "
                f"(difference: {diff})"
            )

    # --- 4. Cross-check line items sum to subtotal ---
    if invoice.subtotal is not None and invoice.line_items:
        items_sum = sum((item.line_total for item in invoice.line_items), Decimal("0"))
        diff = abs(items_sum.quantize(Decimal("0.01")) - invoice.subtotal.quantize(Decimal("0.01")))
        if diff > ROUNDING_TOLERANCE:
            new_warnings.append(
                f"Sum of line items ({items_sum}) does not match extracted subtotal ({invoice.subtotal})"
            )

    # --- 5. Enrichment ---
    # My main enrichment here is the cross-checking above (steps 2-4) -
    # comparing extracted numbers against each other to surface possible
    # extraction errors. I deliberately don't store derived fields like
    # "invoice_month" or "invoice_quarter" on the Invoice itself, since
    # those can be calculated trivially from invoice_date at query time
    # (e.g. in a SQL query or in pandas) - storing them as well would
    # just be redundant, duplicated data.

    logger.info(
        f"Transformed {invoice.source_file}: "
        f"{len(new_warnings) - len(invoice.extraction_warnings)} new warning(s) added during cross-checks"
    )

    # Build a new Invoice with cleaned fields and the updated warnings
    # list. model_copy(update=...) creates a new object based on the
    # existing one, only overriding the fields I pass in - everything
    # else (line_items, totals, etc.) carries over unchanged.
    return invoice.model_copy(
        update={
            "vendor_name": cleaned_vendor_name,
            "customer_name": cleaned_customer_name,
            "vendor_address": cleaned_vendor_address,
            "customer_address": cleaned_customer_address,
            "extraction_warnings": new_warnings,
        }
    )


def _clean_text(value):
    """
    Trim whitespace and collapse repeated spaces in a text field.

    Returns None unchanged if the input is None, so I don't have to
    guard against that at every call site above.
    """
    if value is None:
        return None
    # split() with no arguments splits on any whitespace (spaces,
    # tabs, newlines) and automatically discards empty strings from
    # multiple consecutive spaces - join() then puts it back together
    # with single spaces. This is a common Python idiom for collapsing
    # whitespace.
    return " ".join(value.split())