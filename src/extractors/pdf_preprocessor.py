"""
PDF preprocessing and validation.

Before I send anything to Azure Document Intelligence, I want to check
the file itself is actually usable - readable, not corrupted, has at
least one page. This is a local, fast check using PyMuPDF, so I don't
waste an Azure API call on a broken file.

This module does NOT extract invoice fields (no invoice number, no
amounts) - that's the job of azure_extractor.py. This file only checks
"can this document even be processed at all."
"""

import logging
from dataclasses import dataclass
from pathlib import Path

import fitz  # PyMuPDF's import name is "fitz", not "pymupdf"

logger = logging.getLogger(__name__)


@dataclass
class PreprocessResult:
    """
    Outcome of checking one PDF file.

    is_valid tells the pipeline whether it's safe to send this file on
    to Azure DI. If False, reason explains why, and the pipeline should
    skip this file rather than crash.
    """

    is_valid: bool
    file_path: Path
    page_count: int = 0
    has_text_layer: bool = False
    extracted_text: str = ""
    reason: str = ""


def validate_and_read_pdf(file_path: Path) -> PreprocessResult:
    """
    Open a PDF, check it's usable, and pull out the text layer if present.

    I wrapped the whole thing in a try/except because PyMuPDF raises
    different exceptions depending on what's wrong with the file
    (corrupted, encrypted, not actually a PDF, etc.) - I don't need to
    catch each one separately, I just need to know "did opening this
    file fail, and why."
    """

    if not file_path.exists():
        logger.warning(f"File does not exist: {file_path}")
        return PreprocessResult(
            is_valid=False,
            file_path=file_path,
            reason="File does not exist on disk",
        )

    if file_path.suffix.lower() != ".pdf":
        logger.warning(f"File is not a PDF: {file_path}")
        return PreprocessResult(
            is_valid=False,
            file_path=file_path,
            reason=f"Expected a .pdf file, got '{file_path.suffix}'",
        )

    try:
        doc = fitz.open(file_path)
    except Exception as e:
        logger.error(f"Failed to open PDF {file_path.name}: {e}")
        return PreprocessResult(
            is_valid=False,
            file_path=file_path,
            reason=f"Could not open file - it may be corrupted: {e}",
        )

    # fitz.open() can succeed even on a broken/empty file in some cases,
    # so I check the page count explicitly rather than trusting open()
    # alone to catch everything.
    page_count = doc.page_count
    if page_count == 0:
        doc.close()
        logger.warning(f"PDF has zero pages: {file_path.name}")
        return PreprocessResult(
            is_valid=False,
            file_path=file_path,
            reason="PDF has no pages",
        )

    if doc.is_encrypted:
        doc.close()
        logger.warning(f"PDF is password protected: {file_path.name}")
        return PreprocessResult(
            is_valid=False,
            file_path=file_path,
            page_count=page_count,
            reason="PDF is password protected",
        )

    # Pull text out of every page and join it together. For our invoices
    # (generated as real text, not scanned images) this will return the
    # full invoice content as plain text.
    full_text = ""
    for page in doc:
        full_text += page.get_text()

    doc.close()

    has_text = len(full_text.strip()) > 0

    if not has_text:
        # Not a hard failure - a scanned invoice with no text layer is
        # still valid, Azure DI can read it directly from the image.
        # I just flag it so the pipeline knows what kind of document
        # this is.
        logger.info(f"No text layer found in {file_path.name} - likely a scanned document")

    logger.info(f"Validated {file_path.name}: {page_count} page(s), text layer: {has_text}")

    return PreprocessResult(
        is_valid=True,
        file_path=file_path,
        page_count=page_count,
        has_text_layer=has_text,
        extracted_text=full_text,
        reason="OK",
    )


def validate_batch(folder_path: Path) -> list[PreprocessResult]:
    """
    Run validate_and_read_pdf() on every PDF in a folder.

    This is what main.py will actually call - it loops through
    sample_data/, checks each file, and returns a list of results so
    the pipeline can see at a glance which files are good to process
    and which ones to skip.
    """

    pdf_files = sorted(folder_path.glob("*.pdf"))

    if not pdf_files:
        logger.warning(f"No PDF files found in {folder_path}")
        return []

    results = [validate_and_read_pdf(pdf_path) for pdf_path in pdf_files]

    valid_count = sum(1 for r in results if r.is_valid)
    logger.info(f"Validated {len(results)} files: {valid_count} valid, {len(results) - valid_count} invalid")

    return results