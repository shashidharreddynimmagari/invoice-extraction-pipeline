"""
Script to generate sample invoice PDFs for testing the extraction pipeline.
I'm creating these myself so I have full control over the test data -
different vendors, date formats, and line items to make sure the pipeline
handles real-world variance, not just one fixed layout.
"""

from reportlab.lib.pagesizes import A4
from reportlab.lib import colors
from reportlab.lib.units import mm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_RIGHT, TA_CENTER
from pathlib import Path
import random

# All generated PDFs go into the same folder as this script (sample_data/)
OUTPUT_DIR = Path(__file__).parent

# Four different vendors - gives us variety in vendor name, address, tax ID
# In real life, invoices come from hundreds of different suppliers
VENDORS = [
    {
        "name": "TechSupply GmbH",
        "address": "Berliner Str. 42, 10115 Berlin",
        "tax_id": "DE123456789",
        "iban": "DE89 3704 0044 0532 0130 00",
    },
    {
        "name": "Office Solutions AG",
        "address": "Münchner Ring 8, 80331 München",
        "tax_id": "DE987654321",
        "iban": "DE21 2001 0020 0387 5438 00",
    },
    {
        "name": "CloudServices Europa GmbH",
        "address": "Kaiserstr. 15, 60311 Frankfurt",
        "tax_id": "DE456789123",
        "iban": "DE02 3007 0010 0123 4567 89",
    },
    {
        "name": "DataCenter Nord GmbH",
        "address": "Speicherstadt 1, 20457 Hamburg",
        "tax_id": "DE321654987",
        "iban": "DE75 2005 0550 1234 5678 90",
    },
]

# Three different customers - the companies receiving the invoices
CUSTOMERS = [
    {
        "name": "Mustermann & Partner GmbH",
        "address": "Hauptstraße 100, 70173 Stuttgart",
    },
    {
        "name": "Beispiel AG",
        "address": "Industrieweg 55, 50667 Köln",
    },
    {
        "name": "Alpha Consulting GmbH",
        "address": "Ringstraße 3, 90402 Nürnberg",
    },
]

# Pool of realistic line items - each invoice picks a random subset
# This way every invoice looks different, just like in real life
LINE_ITEMS_POOL = [
    ("Softwarelizenz Enterprise", 1200.00),
    ("IT-Support Stunden (10h)", 850.00),
    ("Cloud Hosting Paket M", 299.00),
    ("Laptop Dell XPS 15", 1899.00),
    ("Monitor 27 Zoll 4K", 450.00),
    ("Tastatur und Maus Set", 89.00),
    ("Netzwerk Switch 24-Port", 320.00),
    ("Beratungsleistung (5h)", 625.00),
    ("Datensicherung Backup", 149.00),
    ("VPN Lizenz Jahresabo", 199.00),
    ("Server Rack Einheit", 780.00),
    ("Schulung Python Grundlagen", 540.00),
]

# Three date formats - this is intentional to test if my pipeline handles variance
# Real invoices use different formats depending on the vendor's system/country
# Format 0: 05.01.2024 (German standard)
# Format 1: 2024-01-05 (ISO format)
# Format 2: 05/01/2024 (slash format)
DATE_FORMATS = [
    lambda d, m, y: f"{d:02d}.{m:02d}.{y}",   # German: 05.01.2024
    lambda d, m, y: f"{y}-{m:02d}-{d:02d}",    # ISO:    2024-01-05
    lambda d, m, y: f"{d:02d}/{m:02d}/{y}",     # Slash:  05/01/2024
]


def generate_invoice(
    invoice_number: str,
    vendor: dict,
    customer: dict,
    line_items: list,
    date_tuple: tuple,
    date_fmt_idx: int,
    output_path: Path,
    vat_rate: float = 0.19,  # Standard German VAT rate
) -> None:
    """
    Generate one invoice PDF and save it to disk.
    
    I'm using ReportLab's Platypus layout engine here - it works with
    'story' elements (paragraphs, tables, spacers) that get assembled
    into a page automatically. Much easier than positioning everything manually.
    """

    # SimpleDocTemplate handles page margins and builds the PDF from our story list
    doc = SimpleDocTemplate(
        str(output_path),
        pagesize=A4,
        rightMargin=20 * mm,
        leftMargin=20 * mm,
        topMargin=20 * mm,
        bottomMargin=20 * mm,
    )

    # Base styles from ReportLab, then I define custom ones on top
    styles = getSampleStyleSheet()
    style_normal = styles["Normal"]
    
    # Custom styles for different parts of the invoice
    style_h1 = ParagraphStyle(
        "h1",
        fontSize=20,
        spaceAfter=6,
        fontName="Helvetica-Bold"
    )
    style_small = ParagraphStyle(
        "small",
        fontSize=9,
        spaceAfter=2
    )
    style_bold = ParagraphStyle(
        "bold",
        fontSize=9,
        fontName="Helvetica-Bold"
    )

    # Unpack the date and format it according to the chosen format
    d, m, y = date_tuple
    date_str = DATE_FORMATS[date_fmt_idx](d, m, y)

    # Due date is 14 days after invoice date - standard payment term in Germany
    due_day = min(d + 14, 28)
    due_str = DATE_FORMATS[date_fmt_idx](due_day, m, y)

    # story is a list of elements - ReportLab assembles them top to bottom
    story = []

    # --- VENDOR HEADER ---
    story.append(Paragraph(vendor["name"], style_h1))
    story.append(Paragraph(vendor["address"], style_small))
    story.append(Paragraph(f"Steuer-Nr.: {vendor['tax_id']}", style_small))
    story.append(Paragraph(f"IBAN: {vendor['iban']}", style_small))
    story.append(Spacer(1, 10 * mm))  # Visual gap

    # --- CUSTOMER BLOCK ---
    story.append(Paragraph("Rechnungsempfänger:", style_bold))
    story.append(Paragraph(customer["name"], style_small))
    story.append(Paragraph(customer["address"], style_small))
    story.append(Spacer(1, 8 * mm))

    # --- INVOICE METADATA (number, date, due date) ---
    meta_data = [
        ["Rechnungsnummer:", invoice_number],
        ["Rechnungsdatum:", date_str],
        ["Fälligkeitsdatum:", due_str],
    ]
    meta_table = Table(meta_data, colWidths=[60 * mm, 80 * mm])
    meta_table.setStyle(TableStyle([
        ("FONTNAME", (0, 0), (0, -1), "Helvetica-Bold"),  # Left column bold
        ("FONTSIZE", (0, 0), (-1, -1), 9),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 3),
    ]))
    story.append(meta_table)
    story.append(Spacer(1, 8 * mm))

    # --- LINE ITEMS TABLE ---
    # First row is the header
    table_data = [["Pos.", "Beschreibung", "Menge", "Einzelpreis", "Gesamt"]]
    subtotal = 0.0

    for i, (desc, unit_price) in enumerate(line_items, 1):
        # Random quantity between 1 and 3 - adds more realism
        qty = random.randint(1, 3)
        total = qty * unit_price
        subtotal += total

        # German number format: period as thousands separator, comma as decimal
        # e.g. 1.234,56 EUR instead of 1,234.56 EUR
        # The replace chain handles this: 1234.56 -> 1.234,56
        def fmt(n: float) -> str:
            return f"{n:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")

        table_data.append([str(i), desc, str(qty), fmt(unit_price), fmt(total)])

    # Calculate VAT and total - added as summary rows at the bottom
    vat = subtotal * vat_rate
    grand_total = subtotal + vat

    def fmt(n: float) -> str:
        return f"{n:,.2f} EUR".replace(",", "X").replace(".", ",").replace("X", ".")

    table_data.append(["", "", "", "Nettobetrag:", fmt(subtotal)])
    table_data.append(["", "", "", f"MwSt. ({int(vat_rate*100)}%):", fmt(vat)])
    table_data.append(["", "", "", "Gesamtbetrag:", fmt(grand_total)])

    # Column widths add up to 185mm (A4 width minus margins)
    items_table = Table(
        table_data,
        colWidths=[15*mm, 80*mm, 20*mm, 35*mm, 35*mm]
    )
    items_table.setStyle(TableStyle([
        # Dark header row
        ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#2C3E50")),
        ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
        ("FONTNAME", (0, 0), (-1, 0), "Helvetica-Bold"),
        ("FONTSIZE", (0, 0), (-1, -1), 8),
        # Alternating row colors for readability
        ("ROWBACKGROUNDS", (0, 1), (-1, -4), [colors.white, colors.HexColor("#F2F2F2")]),
        # Bold totals section at bottom
        ("FONTNAME", (3, -3), (-1, -1), "Helvetica-Bold"),
        # Separator line above totals
        ("LINEABOVE", (3, -3), (-1, -3), 1, colors.black),
        # Double line above grand total
        ("LINEABOVE", (3, -1), (-1, -1), 2, colors.black),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 4),
        ("TOPPADDING", (0, 0), (-1, -1), 4),
        ("ALIGN", (2, 0), (-1, -1), "RIGHT"),
    ]))
    story.append(items_table)
    story.append(Spacer(1, 10 * mm))

    # --- PAYMENT NOTE ---
    story.append(Paragraph(
        f"Bitte überweisen Sie den Betrag bis zum {due_str} auf das oben genannte Konto.",
        style_small
    ))
    story.append(Spacer(1, 4 * mm))
    story.append(Paragraph("Vielen Dank für Ihren Auftrag!", style_small))

    # This call actually builds and writes the PDF file
    doc.build(story)
    print(f"  Generated: {output_path.name}")


def main() -> None:
    """
    Define all 8 invoices and generate them.
    
    I'm hardcoding the invoice definitions here so the output is
    reproducible - running this script twice gives the same PDFs.
    The only randomness is in quantity per line item, which is fine
    since the extraction pipeline doesn't depend on knowing exact quantities.
    """

    # Each tuple: (invoice_number, vendor, customer, line_items, date, date_format_index)
    # date_format_index 0=German, 1=ISO, 2=Slash - deliberately mixed to test variance handling
    invoices = [
        ("RE-2024-0091", VENDORS[0], CUSTOMERS[0], LINE_ITEMS_POOL[0:3],  (5,  1, 2024), 0),
        ("RE-2024-0092", VENDORS[1], CUSTOMERS[1], LINE_ITEMS_POOL[2:4],  (12, 2, 2024), 1),
        ("RE-2024-0093", VENDORS[2], CUSTOMERS[2], LINE_ITEMS_POOL[1:5],  (20, 3, 2024), 2),
        ("RE-2024-0094", VENDORS[3], CUSTOMERS[0], LINE_ITEMS_POOL[4:6],  (8,  4, 2024), 0),
        ("RE-2024-0095", VENDORS[0], CUSTOMERS[1], LINE_ITEMS_POOL[3:6],  (15, 5, 2024), 1),
        ("RE-2024-0096", VENDORS[1], CUSTOMERS[2], LINE_ITEMS_POOL[6:11], (3,  6, 2024), 2),
        ("RE-2024-0097", VENDORS[2], CUSTOMERS[0], LINE_ITEMS_POOL[5:7],  (22, 7, 2024), 0),
        ("RE-2024-0098", VENDORS[3], CUSTOMERS[1], LINE_ITEMS_POOL[8:12], (30, 8, 2024), 1),
    ]

    print("Generating sample invoices...\n")
    for inv_num, vendor, customer, items, date, fmt_idx in invoices:
        output_path = OUTPUT_DIR / f"{inv_num}.pdf"
        generate_invoice(inv_num, vendor, customer, items, date, fmt_idx, output_path)

    print(f"\nDone. {len(invoices)} invoices saved to {OUTPUT_DIR}")


if __name__ == "__main__":
    main()