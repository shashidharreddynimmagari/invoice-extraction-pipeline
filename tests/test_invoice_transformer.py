"""
Unit tests for src/transformers/invoice_transformer.py.

Same approach as the validator tests: build fake Invoice objects
directly, run them through transform_invoice(), and check the result.
"""

import unittest
from datetime import date
from decimal import Decimal

from src.models import Invoice, LineItem
from src.transformers.invoice_transformer import transform_invoice


def _make_invoice(**overrides) -> Invoice:
    """Same helper pattern as in test_invoice_validator.py - builds a
    minimal valid Invoice with any field overridden by keyword argument."""
    defaults = dict(
        invoice_number="TEST-001",
        invoice_date=date(2024, 6, 1),
        vendor_name="  Test   Vendor GmbH  ",  # deliberately messy whitespace
        line_items=[
            LineItem(position=1, description="Item A", quantity=2.0, unit_price=Decimal("50.00"), line_total=Decimal("100.00")),
            LineItem(position=2, description="Item B", quantity=1.0, unit_price=Decimal("19.00"), line_total=Decimal("19.00")),
        ],
        subtotal=Decimal("119.00"),
        vat_rate=0.19,
        vat_amount=Decimal("22.61"),
        total_amount=Decimal("141.61"),
        confidence_score=0.95,
        source_file="test.pdf",
    )
    defaults.update(overrides)
    return Invoice(**defaults)


class TestInvoiceTransformer(unittest.TestCase):

    def test_whitespace_is_cleaned(self):
        """Extra/repeated whitespace in text fields should be collapsed."""
        invoice = _make_invoice()
        result = transform_invoice(invoice)
        self.assertEqual(result.vendor_name, "Test Vendor GmbH")

    def test_none_text_fields_stay_none(self):
        """Cleaning a missing optional field should not raise an error
        or turn it into an empty string - it should stay None."""
        invoice = _make_invoice(customer_name=None)
        result = transform_invoice(invoice)
        self.assertIsNone(result.customer_name)

    def test_correct_math_produces_no_warnings(self):
        """When line items, subtotal, VAT, and total all agree, no
        cross-check warning should be added."""
        invoice = _make_invoice()
        result = transform_invoice(invoice)
        self.assertEqual(result.extraction_warnings, [])

    def test_mismatched_line_item_total_is_flagged(self):
        """If quantity x unit_price doesn't match line_total, that's a
        sign of a possible extraction error and should be flagged."""
        invoice = _make_invoice(
            line_items=[
                LineItem(position=1, description="Bad item", quantity=2.0, unit_price=Decimal("50.00"), line_total=Decimal("999.00")),
            ],
            subtotal=Decimal("999.00"),
            vat_amount=Decimal("189.81"),
            total_amount=Decimal("1188.81"),
        )
        result = transform_invoice(invoice)
        self.assertTrue(any("quantity x unit_price" in w for w in result.extraction_warnings))

    def test_mismatched_subtotal_plus_vat_is_flagged(self):
        """If subtotal + VAT doesn't equal the extracted total, that
        should be flagged - this is the check that would catch a
        misread total_amount field."""
        invoice = _make_invoice(total_amount=Decimal("500.00"))  # doesn't match subtotal+VAT
        result = transform_invoice(invoice)
        self.assertTrue(any("subtotal + VAT" in w for w in result.extraction_warnings))

    def test_small_rounding_difference_is_ignored(self):
        """A 1-2 cent difference is normal rounding noise and should
        NOT trigger a warning - only differences above the tolerance
        should be flagged."""
        invoice = _make_invoice(total_amount=Decimal("141.62"))  # 1 cent off from 141.61
        result = transform_invoice(invoice)
        self.assertEqual(result.extraction_warnings, [])

    def test_original_invoice_is_not_mutated(self):
        """transform_invoice should return a new object, not modify the
        one it was given - the original vendor_name should still have
        its messy whitespace untouched."""
        invoice = _make_invoice()
        transform_invoice(invoice)
        self.assertEqual(invoice.vendor_name, "  Test   Vendor GmbH  ")


if __name__ == "__main__":
    unittest.main()