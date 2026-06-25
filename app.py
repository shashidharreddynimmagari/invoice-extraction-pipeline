"""
Streamlit demo for the invoice extraction pipeline.
Upload a PDF invoice, run it through the full pipeline, and see the results.
"""

import sys
import os
import tempfile
from pathlib import Path
from decimal import Decimal

import streamlit as st

# Add project root to path so imports work
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import AZURE_DI_ENDPOINT, AZURE_DI_KEY
from src.extractors.pdf_preprocessor import validate_and_read_pdf
from src.extractors.azure_extractor import extract_invoice
from src.transformers.invoice_transformer import transform_invoice
from src.validators.invoice_validator import validate_invoice

# ─── Page config ────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Invoice Extraction",
    page_icon="🧾",
    layout="wide",
)

# ─── Styling ─────────────────────────────────────────────────────────────────
st.markdown("""
<style>
    /* Clean sans-serif base */
    html, body, [class*="css"] {
        font-family: 'Inter', 'Segoe UI', sans-serif;
    }

    /* Page background */
    .stApp {
        background-color: #F7F8FA;
    }

    /* Header strip */
    .header-strip {
        background: linear-gradient(135deg, #1B2A4A 0%, #2E4A7A 100%);
        border-radius: 12px;
        padding: 28px 36px;
        margin-bottom: 28px;
        color: white;
    }
    .header-strip h1 {
        color: white;
        font-size: 1.7rem;
        font-weight: 700;
        margin: 0 0 4px 0;
    }
    .header-strip p {
        color: #A8C0E8;
        margin: 0;
        font-size: 0.95rem;
    }

    /* Section cards */
    .card {
        background: white;
        border-radius: 10px;
        padding: 24px 28px;
        margin-bottom: 20px;
        border: 1px solid #E8ECF2;
        box-shadow: 0 1px 4px rgba(0,0,0,0.04);
    }
    .card h3 {
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.08em;
        color: #7A8BA8;
        margin: 0 0 16px 0;
    }

    /* Status badges */
    .badge-valid {
        display: inline-block;
        background: #E6F4EA;
        color: #1E7A34;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 4px 14px;
        border-radius: 20px;
        border: 1px solid #B7DFC3;
    }
    .badge-review {
        display: inline-block;
        background: #FFF3E0;
        color: #C25E00;
        font-weight: 700;
        font-size: 0.85rem;
        padding: 4px 14px;
        border-radius: 20px;
        border: 1px solid #FFCC80;
    }

    /* Field rows */
    .field-row {
        display: flex;
        justify-content: space-between;
        align-items: baseline;
        padding: 8px 0;
        border-bottom: 1px solid #F0F2F5;
    }
    .field-row:last-child { border-bottom: none; }
    .field-label {
        color: #7A8BA8;
        font-size: 0.85rem;
        font-weight: 500;
        min-width: 160px;
    }
    .field-value {
        color: #1B2A4A;
        font-size: 0.9rem;
        font-weight: 500;
        text-align: right;
    }

    /* Line items table */
    .li-table {
        width: 100%;
        border-collapse: collapse;
        font-size: 0.88rem;
    }
    .li-table th {
        background: #F0F4FA;
        color: #4A6080;
        font-weight: 600;
        padding: 8px 12px;
        text-align: left;
        border-bottom: 2px solid #D8E3F0;
    }
    .li-table td {
        padding: 8px 12px;
        border-bottom: 1px solid #F0F2F5;
        color: #1B2A4A;
    }
    .li-table tr:last-child td { border-bottom: none; }
    .li-table td.num { text-align: right; font-family: monospace; }

    /* Totals row */
    .totals-row {
        display: flex;
        justify-content: flex-end;
        gap: 40px;
        padding: 12px 0 4px 0;
        font-size: 0.9rem;
    }
    .total-item { display: flex; flex-direction: column; align-items: flex-end; }
    .total-label { color: #7A8BA8; font-size: 0.78rem; font-weight: 500; }
    .total-value { color: #1B2A4A; font-weight: 600; font-size: 1rem; }
    .total-value.grand { color: #1E7A34; font-size: 1.2rem; font-weight: 700; }

    /* Confidence bar */
    .conf-bar-outer {
        background: #E8ECF2;
        border-radius: 6px;
        height: 8px;
        margin-top: 6px;
        overflow: hidden;
    }
    .conf-bar-inner {
        height: 8px;
        border-radius: 6px;
        background: linear-gradient(90deg, #2E7D32, #66BB6A);
    }

    /* Warning items */
    .warning-item {
        background: #FFF8E1;
        border-left: 3px solid #FFA000;
        border-radius: 0 6px 6px 0;
        padding: 8px 14px;
        margin-bottom: 8px;
        font-size: 0.875rem;
        color: #5C3A00;
    }
    .issue-item {
        background: #FFF3E0;
        border-left: 3px solid #F57C00;
        border-radius: 0 6px 6px 0;
        padding: 8px 14px;
        margin-bottom: 8px;
        font-size: 0.875rem;
        color: #4A2500;
    }

    /* Pipeline steps */
    .step-done {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 0;
        color: #1E7A34;
        font-size: 0.88rem;
        font-weight: 500;
    }
    .step-fail {
        display: flex;
        align-items: center;
        gap: 10px;
        padding: 6px 0;
        color: #C62828;
        font-size: 0.88rem;
        font-weight: 500;
    }

    /* Hide Streamlit default elements */
    #MainMenu, footer, header { visibility: hidden; }
    .block-container { padding-top: 1.5rem; }
</style>
""", unsafe_allow_html=True)


# ─── Header ──────────────────────────────────────────────────────────────────
st.markdown("""
<div class="header-strip">
    <h1>🧾 Invoice Extraction Pipeline</h1>
    <p>Upload a PDF invoice to extract, validate, and review structured data using Azure Document Intelligence.</p>
</div>
""", unsafe_allow_html=True)


# ─── Check Azure credentials ─────────────────────────────────────────────────
if not AZURE_DI_KEY or not AZURE_DI_ENDPOINT:
    st.error("Azure Document Intelligence credentials not found. Make sure your .env file is configured correctly.")
    st.stop()


# ─── Upload section ───────────────────────────────────────────────────────────
col_upload, col_info = st.columns([2, 1])

with col_upload:
    st.markdown('<div class="card"><h3>Upload Invoice</h3>', unsafe_allow_html=True)
    uploaded_file = st.file_uploader(
        "Drop a PDF invoice here",
        type=["pdf"],
        label_visibility="collapsed",
    )
    st.markdown('</div>', unsafe_allow_html=True)

with col_info:
    st.markdown("""
    <div class="card">
        <h3>What this does</h3>
        <div class="field-row"><span class="field-label">Step 1</span><span class="field-value">File validation</span></div>
        <div class="field-row"><span class="field-label">Step 2</span><span class="field-value">Azure DI extraction</span></div>
        <div class="field-row"><span class="field-label">Step 3</span><span class="field-value">Math cross-check</span></div>
        <div class="field-row"><span class="field-label">Step 4</span><span class="field-value">Plausibility check</span></div>
    </div>
    """, unsafe_allow_html=True)


# ─── Run pipeline ─────────────────────────────────────────────────────────────
if uploaded_file is not None:
    run_col, _ = st.columns([1, 3])
    with run_col:
        run = st.button("Extract Invoice", type="primary", use_container_width=True)

    if run:
        # Save upload to a temp file
        with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as tmp:
            tmp.write(uploaded_file.read())
            tmp_path = Path(tmp.name)

        # ── Pipeline execution with live progress ──
        st.markdown('<div class="card"><h3>Pipeline Steps</h3>', unsafe_allow_html=True)

        steps_placeholder = st.empty()
        steps_log = []

        def render_steps(steps):
            html = ""
            for icon, label in steps:
                css = "step-done" if icon == "✅" else "step-fail"
                html += f'<div class="{css}">{icon} {label}</div>'
            steps_placeholder.markdown(html, unsafe_allow_html=True)

        # Step 1 — Preprocessing
        with st.spinner("Checking file..."):
            preprocess = validate_and_read_pdf(tmp_path)

        if not preprocess.is_valid:
            steps_log.append(("❌", f"File validation failed — {preprocess.reason}"))
            render_steps(steps_log)
            st.error(f"Could not process this file: {preprocess.reason}")
            os.unlink(tmp_path)
            st.stop()

        steps_log.append(("✅", f"File valid — {preprocess.page_count} page(s), text layer: {'yes' if preprocess.has_text_layer else 'no'}"))
        render_steps(steps_log)

        # Step 2 — Azure extraction
        with st.spinner("Sending to Azure Document Intelligence..."):
            extraction = extract_invoice(tmp_path)

        if not extraction.success:
            steps_log.append(("❌", f"Extraction failed — {extraction.error_message}"))
            render_steps(steps_log)
            st.error(f"Azure extraction failed: {extraction.error_message}")
            os.unlink(tmp_path)
            st.stop()

        invoice = extraction.invoice
        steps_log.append(("✅", f"Extracted — confidence {invoice.confidence_score:.0%}, {len(invoice.line_items)} line item(s)"))
        render_steps(steps_log)

        # Step 3 — Transform
        with st.spinner("Cleaning and cross-checking..."):
            invoice = transform_invoice(invoice)

        steps_log.append(("✅", f"Transformed — {len(invoice.extraction_warnings)} warning(s)"))
        render_steps(steps_log)

        # Step 4 — Validate
        with st.spinner("Running plausibility checks..."):
            validation = validate_invoice(invoice)

        status_label = "valid" if validation.status == "valid" else "needs review"
        steps_log.append(("✅", f"Validated — status: {status_label}"))
        render_steps(steps_log)

        st.markdown('</div>', unsafe_allow_html=True)
        os.unlink(tmp_path)

        # ── Results ──────────────────────────────────────────────────────────

        # Status + confidence banner
        badge = f'<span class="badge-valid">✓ Valid</span>' if validation.status == "valid" \
            else f'<span class="badge-review">⚠ Needs Review</span>'

        conf_pct = int(invoice.confidence_score * 100)
        conf_color = "#2E7D32" if conf_pct >= 80 else "#F57C00" if conf_pct >= 60 else "#C62828"

        st.markdown(f"""
        <div class="card">
            <h3>Result Summary</h3>
            <div style="display:flex; align-items:center; gap:24px; flex-wrap:wrap;">
                <div>
                    <div style="font-size:0.78rem; color:#7A8BA8; font-weight:500; margin-bottom:4px;">STATUS</div>
                    {badge}
                </div>
                <div style="flex:1; min-width:200px;">
                    <div style="font-size:0.78rem; color:#7A8BA8; font-weight:500; margin-bottom:4px;">
                        EXTRACTION CONFIDENCE — {conf_pct}%
                    </div>
                    <div class="conf-bar-outer">
                        <div class="conf-bar-inner" style="width:{conf_pct}%; background: linear-gradient(90deg, {conf_color}, {conf_color}99);"></div>
                    </div>
                </div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Two-column layout for invoice details
        left, right = st.columns(2)

        with left:
            # Invoice identification
            st.markdown(f"""
            <div class="card">
                <h3>Invoice Details</h3>
                <div class="field-row">
                    <span class="field-label">Invoice Number</span>
                    <span class="field-value">{invoice.invoice_number or '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Invoice Date</span>
                    <span class="field-value">{invoice.invoice_date.strftime('%d %b %Y') if invoice.invoice_date else '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Due Date</span>
                    <span class="field-value">{invoice.due_date.strftime('%d %b %Y') if invoice.due_date else '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Source File</span>
                    <span class="field-value">{invoice.source_file}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Customer
            st.markdown(f"""
            <div class="card">
                <h3>Customer</h3>
                <div class="field-row">
                    <span class="field-label">Name</span>
                    <span class="field-value">{invoice.customer_name or '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Address</span>
                    <span class="field-value">{invoice.customer_address or '—'}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        with right:
            # Vendor
            st.markdown(f"""
            <div class="card">
                <h3>Vendor</h3>
                <div class="field-row">
                    <span class="field-label">Name</span>
                    <span class="field-value">{invoice.vendor_name or '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Address</span>
                    <span class="field-value">{invoice.vendor_address or '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">Tax ID</span>
                    <span class="field-value">{invoice.vendor_tax_id or '—'}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">IBAN</span>
                    <span class="field-value">{invoice.vendor_iban or '—'}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Totals
            subtotal_str = f"€ {invoice.subtotal:,.2f}" if invoice.subtotal else "—"
            vat_str = f"€ {invoice.vat_amount:,.2f}" if invoice.vat_amount else "—"
            vat_rate_str = f"({int(invoice.vat_rate * 100)}%)" if invoice.vat_rate else ""
            total_str = f"€ {invoice.total_amount:,.2f}" if invoice.total_amount else "—"

            st.markdown(f"""
            <div class="card">
                <h3>Totals</h3>
                <div class="field-row">
                    <span class="field-label">Subtotal (net)</span>
                    <span class="field-value">{subtotal_str}</span>
                </div>
                <div class="field-row">
                    <span class="field-label">VAT {vat_rate_str}</span>
                    <span class="field-value">{vat_str}</span>
                </div>
                <div class="field-row">
                    <span class="field-label" style="color:#1B2A4A; font-weight:700;">Total (gross)</span>
                    <span class="field-value" style="color:#1E7A34; font-size:1.1rem; font-weight:700;">{total_str}</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # Line items
        if invoice.line_items:
            rows_html = ""
            for item in invoice.line_items:
                rows_html += f"""
                <tr>
                    <td>{item.position}</td>
                    <td>{item.description}</td>
                    <td class="num">{item.quantity:g}</td>
                    <td class="num">€ {item.unit_price:,.2f}</td>
                    <td class="num">€ {item.line_total:,.2f}</td>
                </tr>"""

            st.markdown(f"""
            <div class="card">
                <h3>Line Items</h3>
                <table class="li-table">
                    <thead>
                        <tr>
                            <th style="width:40px">#</th>
                            <th>Description</th>
                            <th style="text-align:right">Qty</th>
                            <th style="text-align:right">Unit Price</th>
                            <th style="text-align:right">Total</th>
                        </tr>
                    </thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </div>
            """, unsafe_allow_html=True)

        # Warnings and issues
        if invoice.extraction_warnings or validation.issues:
            warn_html = ""
            for w in invoice.extraction_warnings:
                warn_html += f'<div class="warning-item">⚠ {w}</div>'
            for issue in validation.issues:
                warn_html += f'<div class="issue-item">⚡ {issue}</div>'

            st.markdown(f"""
            <div class="card">
                <h3>Warnings & Issues</h3>
                {warn_html}
            </div>
            """, unsafe_allow_html=True)
        else:
            st.markdown("""
            <div class="card">
                <h3>Warnings & Issues</h3>
                <div style="color:#1E7A34; font-size:0.9rem; font-weight:500;">✓ No warnings or issues found</div>
            </div>
            """, unsafe_allow_html=True)