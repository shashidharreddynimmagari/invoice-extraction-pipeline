"""
Data models for the invoice extraction pipeline.

These Pydantic models define the exact shape of data I expect to get
out of the extraction step. If Azure Document Intelligence (or whatever
extractor I use) returns something that doesn't match this shape - wrong
type, missing required field, etc. - Pydantic raises a validation error
right away instead of letting bad data flow further into the pipeline.

I'm keeping this as the single source of truth for "what is an invoice"
in this project. Every other module (transformer, validator, storage)
imports from here.
"""

from datetime import date
from decimal import Decimal
from typing import Optional

from pydantic import BaseModel, Field  # `BaseModel` - the Pydantic class every model inherits from, 
  # `Field` - lets me add extra rules/metadata to a field (min length, description, greater-than-zero, etc.)


class LineItem(BaseModel):
    """One line item / position on an invoice."""

    position: int = Field(..., description="Line number on the invoice, e.g. 1, 2, 3")
    description: str = Field(..., min_length=1, description="What was bought, e.g. 'Cloud Hosting Paket M'")
    quantity: float = Field(..., gt=0, description="How many units")
    unit_price: Decimal = Field(..., description="Price per unit, before VAT")
    line_total: Decimal = Field(..., description="quantity * unit_price")


class Invoice(BaseModel):
    """
    Structured representation of a single invoice.

    This is the target schema for the whole pipeline. Raw extraction
    output gets mapped into this model, then this model is what gets
    transformed, validated, and finally stored.
    """

    # --- Identification ---
    invoice_number: str = Field(..., min_length=1, description="Unique invoice ID, e.g. RE-2024-0091")
    invoice_date: date = Field(..., description="Date the invoice was issued")
    due_date: Optional[date] = Field(default=None, description="Payment due date, if present")

    # --- Vendor (who is billing) ---
    vendor_name: str = Field(..., min_length=1)
    vendor_address: Optional[str] = None
    vendor_tax_id: Optional[str] = Field(default=None, description="Steuer-Nr. / VAT ID")
    vendor_iban: Optional[str] = None

    # --- Customer (who is being billed) ---
    customer_name: Optional[str] = None
    customer_address: Optional[str] = None

    # --- Line items ---
    line_items: list[LineItem] = Field(default_factory=list)

    # --- Totals ---
    subtotal: Optional[Decimal] = Field(default=None, description="Net amount before VAT")
    vat_rate: Optional[float] = Field(default=None, description="VAT rate as decimal, e.g. 0.19 for 19%")
    vat_amount: Optional[Decimal] = None
    total_amount: Decimal = Field(..., description="Final amount including VAT")

    # --- Pipeline metadata (not part of the original document) ---
    # These two fields are how I track extraction quality. Azure DI gives
    # back a confidence score per field - I take the average across the
    # fields I care about and store it here. Anything below the threshold
    # in config/settings.py gets flagged for manual review instead of
    # being trusted blindly.
    confidence_score: float = Field(
        default=1.0,
        ge=0.0,
        le=1.0,
        description="Average extraction confidence across key fields (0-1)",
    )
    extraction_warnings: list[str] = Field(
        default_factory=list,
        description="Human-readable notes about anything that looked off during extraction",
    )
    source_file: str = Field(..., description="Original PDF filename this invoice came from")


class ExtractionResult(BaseModel):
    """
    Wraps the outcome of trying to process one document.

    I added this because not every PDF will extract cleanly - some
    might be unreadable, some might be missing required fields. Instead
    of letting the pipeline crash on a bad file, each document produces
    one of these results, and the pipeline just moves on to the next file.
    """

    success: bool
    invoice: Optional[Invoice] = None
    error_message: Optional[str] = None
    source_file: str