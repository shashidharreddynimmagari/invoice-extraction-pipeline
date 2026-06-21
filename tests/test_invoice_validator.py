"""
Unit tests for src/validators/invoice_validator.py.

These tests build fake Invoice objects directly in Python (no PDF, no
Azure call needed) and check that validate_invoice() flags the right
issues. This is possible because the validator only depends on an
Invoice object's field values, not on how that Invoice was created -
so I can construct exactly the scenario I want to test, deterministically.
"""

import unittest
from datetime import date, timedelta
from decimal import Decimal

from src.models import Invoice, LineItem
from src.validators.invoice_validator import validate_invoice


def _make_invoice(**overrides) -> Invoice:
    """
    Helper that builds a minimal valid Invoice, with any field
    overridden by keyword argument.

    This avoids repeating all of Invoice's required fields in every
    single test - each test only specifies the field(s) it actually
    cares about changing, and everything else uses a sensible default.
    """
    defaults = dict(
        invoice_number="TEST-001",
        invoice_date=date(2024, 6, 1),
        due_date=date(2024, 6, 15),
        vendor_name="Test Vendor GmbH",
        line_items=[
            LineItem(position=1, description="Test item", quantity=1.0, unit_price=Decimal("100.00"), line_total=Decimal("100.00")),
        ],
        subtotal=Decimal("100.00"),
        vat_rate=0.19,
        vat_amount=Decimal("19.00"),
        total_amount=Decimal("119.00"),
        confidence_score=0.95,
        source_file="test.pdf",
    )
    defaults.update(overrides)
    return Invoice(**defaults)


class TestInvoiceValidator(unittest.TestCase):

    def test_clean_invoice_is_valid(self):
        """A well-formed invoice with no issues should pass as 'valid'."""
        invoice = _make_invoice()
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "valid")
        self.assertEqual(result.issues, [])

    def test_low_confidence_flags_for_review(self):
        """Confidence below the threshold should trigger needs_review."""
        invoice = _make_invoice(confidence_score=0.5)
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("Confidence" in issue for issue in result.issues))

    def test_due_date_before_invoice_date_is_flagged(self):
        """A due date earlier than the invoice date suggests swapped dates."""
        invoice = _make_invoice(
            invoice_date=date(2024, 6, 15),
            due_date=date(2024, 6, 1),
        )
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("before invoice_date" in issue for issue in result.issues))

    def test_future_invoice_date_is_flagged(self):
        """An invoice dated after today is implausible."""
        invoice = _make_invoice(invoice_date=date.today() + timedelta(days=30))
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("future" in issue for issue in result.issues))

    def test_invalid_vat_rate_is_flagged(self):
        """A VAT rate that doesn't match a known German rate is suspicious."""
        invoice = _make_invoice(vat_rate=0.35)
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("vat_rate" in issue for issue in result.issues))

    def test_standard_vat_rates_are_accepted(self):
        """0%, 7%, and 19% should all pass without a VAT-related issue."""
        for rate in (0.0, 0.07, 0.19):
            invoice = _make_invoice(vat_rate=rate)
            result = validate_invoice(invoice)
            vat_issues = [i for i in result.issues if "vat_rate" in i]
            self.assertEqual(vat_issues, [], f"Rate {rate} should not be flagged")

    def test_negative_total_is_flagged(self):
        """A negative total amount makes no business sense."""
        invoice = _make_invoice(total_amount=Decimal("-50.00"))
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("not a positive value" in issue for issue in result.issues))

    def test_no_line_items_is_flagged(self):
        """An invoice with zero line items is incomplete."""
        invoice = _make_invoice(line_items=[])
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")
        self.assertTrue(any("no line items" in issue for issue in result.issues))

    def test_extraction_warnings_trigger_review(self):
        """Pre-existing warnings from earlier pipeline stages should also
        push the invoice into needs_review, even if nothing else is wrong."""
        invoice = _make_invoice(extraction_warnings=["Some earlier warning"])
        result = validate_invoice(invoice)
        self.assertEqual(result.status, "needs_review")


if __name__ == "__main__":
    unittest.main()