"""
SQLite storage for the invoice pipeline.

Schema design: two tables.

invoices       - one row per invoice. Includes the validation_status
                 and validation_issues columns directly, since validation
                 is a 1:1 fact about an invoice, not a one-to-many
                 relationship - no need for a separate table that would
                 just force an extra JOIN on every query.

line_items     - one row per line item, linked back to its parent
                 invoice via invoice_id (a foreign key). This IS a
                 genuine one-to-many relationship (one invoice has
                 several line items), so it gets its own table -
                 standard relational database normalization.

In production this would map to Azure SQL Database - same schema,
just a different connection string. SQLite is the free, zero-setup
local equivalent for this prototype.
"""

import logging
import sqlite3
from pathlib import Path

from src.models import Invoice
from src.validators.invoice_validator import ValidationResult

logger = logging.getLogger(__name__)

# This is the actual table structure. I'm using TEXT for dates and
# amounts rather than SQLite's limited native types - SQLite doesn't
# have a real DATE or DECIMAL type, so I store dates as ISO format
# strings (YYYY-MM-DD, which sorts correctly as plain text) and
# amounts as TEXT to avoid SQLite silently converting them to its
# native REAL (floating point) type, which would reintroduce the exact
# float precision problem I avoided by using Decimal in the first place.
SCHEMA = """
CREATE TABLE IF NOT EXISTS invoices (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_number TEXT NOT NULL UNIQUE,
    invoice_date TEXT NOT NULL,
    due_date TEXT,
    vendor_name TEXT NOT NULL,
    vendor_address TEXT,
    vendor_tax_id TEXT,
    vendor_iban TEXT,
    customer_name TEXT,
    customer_address TEXT,
    subtotal TEXT,
    vat_rate REAL,
    vat_amount TEXT,
    total_amount TEXT NOT NULL,
    confidence_score REAL NOT NULL,
    extraction_warnings TEXT,
    validation_status TEXT NOT NULL,
    validation_issues TEXT,
    source_file TEXT NOT NULL,
    created_at TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS line_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    invoice_id INTEGER NOT NULL,
    position INTEGER NOT NULL,
    description TEXT NOT NULL,
    quantity REAL NOT NULL,
    unit_price TEXT NOT NULL,
    line_total TEXT NOT NULL,
    FOREIGN KEY (invoice_id) REFERENCES invoices (id)
);
"""


def get_connection(db_path: Path) -> sqlite3.Connection:
    """
    Open a connection to the SQLite database, creating the tables if
    they don't exist yet.

    db_path.parent.mkdir ensures the output/ folder actually exists
    before SQLite tries to create the .db file inside it - SQLite
    won't create missing parent folders on its own.
    """
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    conn.execute("PRAGMA foreign_keys = ON")  # SQLite has FK constraints off by default
    conn.executescript(SCHEMA)
    return conn


def save_invoice(conn: sqlite3.Connection, invoice: Invoice, validation: ValidationResult) -> int:
    """
    Insert one invoice and all its line items into the database.

    Returns the new invoice's database id (its primary key), in case
    the caller wants it for logging or further reference.

    I use a single transaction for the invoice row and all its line
    items together - if anything fails partway through, the whole
    insert rolls back rather than leaving an invoice with only some of
    its line items saved.
    """

    cursor = conn.cursor()

    try:
        cursor.execute(
            """
            INSERT INTO invoices (
                invoice_number, invoice_date, due_date,
                vendor_name, vendor_address, vendor_tax_id, vendor_iban,
                customer_name, customer_address,
                subtotal, vat_rate, vat_amount, total_amount,
                confidence_score, extraction_warnings,
                validation_status, validation_issues,
                source_file
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                invoice.invoice_number,
                invoice.invoice_date.isoformat(),
                invoice.due_date.isoformat() if invoice.due_date else None,
                invoice.vendor_name,
                invoice.vendor_address,
                invoice.vendor_tax_id,
                invoice.vendor_iban,
                invoice.customer_name,
                invoice.customer_address,
                str(invoice.subtotal) if invoice.subtotal is not None else None,
                invoice.vat_rate,
                str(invoice.vat_amount) if invoice.vat_amount is not None else None,
                str(invoice.total_amount),
                invoice.confidence_score,
                "; ".join(invoice.extraction_warnings) if invoice.extraction_warnings else None,
                validation.status,
                "; ".join(validation.issues) if validation.issues else None,
                invoice.source_file,
            ),
        )
        invoice_id = cursor.lastrowid

        for item in invoice.line_items:
            cursor.execute(
                """
                INSERT INTO line_items (invoice_id, position, description, quantity, unit_price, line_total)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    invoice_id,
                    item.position,
                    item.description,
                    item.quantity,
                    str(item.unit_price),
                    str(item.line_total),
                ),
            )

        conn.commit()
        logger.info(f"Saved invoice {invoice.invoice_number} (id={invoice_id}) with {len(invoice.line_items)} line item(s)")
        return invoice_id

    except sqlite3.IntegrityError as e:
        conn.rollback()
        logger.error(f"Failed to save {invoice.invoice_number} - likely a duplicate invoice_number: {e}")
        raise
    except Exception as e:
        conn.rollback()
        logger.error(f"Failed to save {invoice.invoice_number}: {e}")
        raise