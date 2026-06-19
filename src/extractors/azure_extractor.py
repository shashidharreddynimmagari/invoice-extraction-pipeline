"""
Azure Document Intelligence extraction.

This is the core extraction step - it sends a PDF to Azure's prebuilt
invoice model and maps the response onto my own Invoice/LineItem schema
(defined in models.py). Everything downstream of this file only ever
sees clean Invoice objects - nothing else in the pipeline needs to know
Azure is involved at all. If I ever swapped to a different extraction
service, this would be the only file that needs to change.

Azure DI gives back a confidence score per field. I use that to decide
how much I trust each extracted value, and I average a handful of the
most important ones into a single confidence_score on the Invoice itself.
"""

import logging
from datetime import date
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Optional

from azure.ai.formrecognizer import DocumentAnalysisClient
from azure.core.credentials import AzureKeyCredential
from azure.core.exceptions import HttpResponseError

from config.settings import AZURE_DI_ENDPOINT, AZURE_DI_KEY, CONFIDENCE_THRESHOLD
from src.models import ExtractionResult, Invoice, LineItem

logger = logging.getLogger(__name__)

# I only build this client once per pipeline run, not once per document -
# creating it is a network/auth handshake, no need to repeat that per file.
_client: Optional[DocumentAnalysisClient] = None


def _get_client() -> DocumentAnalysisClient:
    """
    Lazily create and reuse the Azure client.

    "Lazily" means: don't create the client the moment this module is
    imported, only create it the first time it's actually needed. This
    way, if AZURE_DI_KEY is missing or wrong, the error only happens
    when I actually try to extract something - not just from importing
    this file.
    """
    global _client
    if _client is None:
        if not AZURE_DI_KEY or not AZURE_DI_ENDPOINT:
            raise ValueError(
                "AZURE_DI_KEY and AZURE_DI_ENDPOINT must be set in .env - "
                "check config/settings.py is loading them correctly"
            )
        _client = DocumentAnalysisClient(
            endpoint=AZURE_DI_ENDPOINT,
            credential=AzureKeyCredential(AZURE_DI_KEY),
        )
    return _client


def _safe_decimal(value) -> Optional[Decimal]:
    """
    Convert Azure's extracted currency value into a Decimal safely.

    Azure returns amount fields as a CurrencyValue object with an
    .amount attribute (a float). I convert through str() first rather
    than passing the float directly into Decimal() - doing
    Decimal(0.1) directly can carry over float's binary rounding
    error, but Decimal(str(0.1)) does not, since it parses the clean
    decimal text instead.
    """
    if value is None:
        return None
    try:
        amount = getattr(value, "amount", value)
        return Decimal(str(amount))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _safe_date(value) -> Optional[date]:
    """Azure already gives back proper Python date objects for date fields,
    but I still guard against None so calling code doesn't have to."""
    if value is None:
        return None
    if isinstance(value, date):
        return value
    return None


def _field_confidence(field) -> float:
    """
    Pull the confidence score off one Azure field object.

    Azure DI fields have a .confidence attribute (0.0-1.0). If a field
    wasn't found at all, Azure may return None for the field itself,
    so I treat that as 0 confidence rather than crashing on a missing
    attribute.
    """
    if field is None:
        return 0.0
    confidence = getattr(field, "confidence", None)
    return confidence if confidence is not None else 0.0


def extract_invoice(file_path: Path) -> ExtractionResult:
    """
    Send one PDF to Azure Document Intelligence and map the result onto
    my Invoice schema.

    Required fields (invoice_number, invoice_date, vendor_name,
    total_amount) missing from Azure's response cause this to return
    success=False - I'd rather flag the document for manual review than
    store an invoice with a guessed or empty value for something that
    important.
    """

    client = _get_client()

    try:
        with open(file_path, "rb") as f:
            poller = client.begin_analyze_document("prebuilt-invoice", document=f)
        result = poller.result()
    except HttpResponseError as e:
        logger.error(f"Azure DI request failed for {file_path.name}: {e}")
        return ExtractionResult(
            success=False,
            error_message=f"Azure Document Intelligence request failed: {e}",
            source_file=file_path.name,
        )

    if not result.documents:
        logger.warning(f"Azure DI found no invoice document in {file_path.name}")
        return ExtractionResult(
            success=False,
            error_message="Azure DI did not recognize this file as an invoice",
            source_file=file_path.name,
        )

    # The prebuilt-invoice model can technically detect multiple invoices
    # in one file, but my test data is always one invoice per PDF, so I
    # only use the first document found.
    doc = result.documents[0]
    fields = doc.fields

    warnings: list[str] = []
    confidence_scores: list[float] = []

    # --- Required fields ---
    invoice_number_field = fields.get("InvoiceId")
    invoice_date_field = fields.get("InvoiceDate")
    vendor_name_field = fields.get("VendorName")
    total_field = fields.get("InvoiceTotal")

    invoice_number = invoice_number_field.value if invoice_number_field else None
    invoice_date = _safe_date(invoice_date_field.value if invoice_date_field else None)
    vendor_name = vendor_name_field.value if vendor_name_field else None
    total_amount = _safe_decimal(total_field.value if total_field else None)

    missing_required = []
    if not invoice_number:
        missing_required.append("invoice_number")
    if not invoice_date:
        missing_required.append("invoice_date")
    if not vendor_name:
        missing_required.append("vendor_name")
    if total_amount is None:
        missing_required.append("total_amount")

    if missing_required:
        msg = f"Missing required field(s): {', '.join(missing_required)}"
        logger.warning(f"{file_path.name}: {msg}")
        return ExtractionResult(
            success=False,
            error_message=msg,
            source_file=file_path.name,
        )

    confidence_scores.append(_field_confidence(invoice_number_field))
    confidence_scores.append(_field_confidence(invoice_date_field))
    confidence_scores.append(_field_confidence(vendor_name_field))
    confidence_scores.append(_field_confidence(total_field))

    # --- Optional fields ---
    due_date_field = fields.get("DueDate")
    due_date = _safe_date(due_date_field.value if due_date_field else None)

    vendor_address_field = fields.get("VendorAddress")
    vendor_address = vendor_address_field.content if vendor_address_field else None
    if vendor_address_field and _field_confidence(vendor_address_field) < CONFIDENCE_THRESHOLD:
        warnings.append(
            f"vendor_address has low confidence ({_field_confidence(vendor_address_field):.2f}) - verify against source PDF"
        )

    vendor_tax_id_field = fields.get("VendorTaxId")
    vendor_tax_id = vendor_tax_id_field.value if vendor_tax_id_field else None

    customer_name_field = fields.get("CustomerName")
    customer_name = customer_name_field.value if customer_name_field else None

    customer_address_field = fields.get("CustomerAddress")
    customer_address = customer_address_field.content if customer_address_field else None

    subtotal_field = fields.get("SubTotal")
    subtotal = _safe_decimal(subtotal_field.value if subtotal_field else None)

    vat_field = fields.get("TotalTax")
    vat_amount = _safe_decimal(vat_field.value if vat_field else None)

    # Azure doesn't return a VAT rate directly, only the VAT amount - I
    # calculate the rate myself if I have both numbers, since the
    # validator and documentation want to see the rate too (e.g. "19%").
    vat_rate = None
    if subtotal and vat_amount and subtotal > 0:
        vat_rate = float(vat_amount / subtotal)

    # --- Line items ---
    line_items: list[LineItem] = []
    items_field = fields.get("Items")

    if items_field and items_field.value:
        for i, item in enumerate(items_field.value, start=1):
            item_fields = item.value

            description_field = item_fields.get("Description")
            quantity_field = item_fields.get("Quantity")
            unit_price_field = item_fields.get("UnitPrice")
            amount_field = item_fields.get("Amount")

            description = description_field.value if description_field else f"Item {i}"
            quantity = quantity_field.value if quantity_field else 1.0
            unit_price = _safe_decimal(unit_price_field.value if unit_price_field else None)
            line_total = _safe_decimal(amount_field.value if amount_field else None)

            # If unit_price is missing but I have a line total and a
            # quantity, I can back-calculate it rather than dropping the
            # line item entirely.
            if unit_price is None and line_total is not None and quantity:
                unit_price = line_total / Decimal(str(quantity))

            if unit_price is None or line_total is None:
                warnings.append(f"Line item {i} ('{description}') had incomplete pricing - skipped")
                continue

            line_items.append(
                LineItem(
                    position=i,
                    description=description,
                    quantity=float(quantity),
                    unit_price=unit_price,
                    line_total=line_total,
                )
            )

    if not line_items:
        warnings.append("No line items were extracted")

    # --- Confidence score ---
    # Average of the required-field confidences I collected above. I'm
    # deliberately only averaging the fields that matter most for
    # business decisions, not every single field Azure returns.
    avg_confidence = sum(confidence_scores) / len(confidence_scores) if confidence_scores else 0.0

    if avg_confidence < CONFIDENCE_THRESHOLD:
        warnings.append(
            f"Average confidence {avg_confidence:.2f} is below threshold {CONFIDENCE_THRESHOLD} - recommend manual review"
        )

    invoice = Invoice(
        invoice_number=invoice_number,
        invoice_date=invoice_date,
        due_date=due_date,
        vendor_name=vendor_name,
        vendor_address=vendor_address,
        vendor_tax_id=vendor_tax_id,
        vendor_iban=None,  # Azure's prebuilt model has no dedicated IBAN field
        customer_name=customer_name,
        customer_address=customer_address,
        line_items=line_items,
        subtotal=subtotal,
        vat_rate=vat_rate,
        vat_amount=vat_amount,
        total_amount=total_amount,
        confidence_score=round(avg_confidence, 4),
        extraction_warnings=warnings,
        source_file=file_path.name,
    )

    logger.info(f"Extracted {file_path.name}: confidence={avg_confidence:.2f}, {len(line_items)} line item(s)")

    return ExtractionResult(success=True, invoice=invoice, source_file=file_path.name)