"""
Pipeline orchestrator for the invoice extraction project.

This file doesn't contain any new business logic of its own - every
individual step (preprocessing, extraction, transformation, validation,
storage) already exists as its own tested module. This file's only job
is to call them in the right order, for every file in a folder, and
make sure one bad document never stops the rest of the batch from
being processed.

Flow per document:
    PDF -> PyMuPDF validation -> Azure DI extraction -> transform
        -> validate -> save to SQLite

If any step fails for a given file, that file is recorded as failed
and the pipeline moves on to the next one - it does not crash the
whole batch run.
"""

import logging
from dataclasses import dataclass, field
from pathlib import Path

from config.settings import DB_PATH, SAMPLE_DATA_DIR
from src.extractors.azure_extractor import extract_invoice
from src.extractors.pdf_preprocessor import validate_and_read_pdf
from src.storage.database import get_connection, save_invoice
from src.transformers.invoice_transformer import transform_invoice
from src.validators.invoice_validator import validate_invoice

logger = logging.getLogger(__name__)


@dataclass
class PipelineSummary:
    """
    End-of-run report for a batch of documents.

    I'm tracking filenames in each category (not just counts) so
    main.py can print exactly which files need attention, not just
    how many.
    """

    total_files: int = 0
    succeeded: list = field(default_factory=list)        # filenames saved successfully, status "valid"
    needs_review: list = field(default_factory=list)     # filenames saved successfully, status "needs_review"
    failed: list = field(default_factory=list)            # (filename, reason) tuples - never made it to storage


def run_pipeline(input_dir: Path = None, db_path: Path = None) -> PipelineSummary:
    """
    Process every PDF in input_dir through the full pipeline and store
    the results in the database at db_path.

    Both arguments default to the paths configured in config/settings.py
    if not explicitly provided - this makes the function easy to call
    with no arguments for the normal case, while still letting tests
    point it at a different folder/database if needed.
    """

    input_dir = input_dir or SAMPLE_DATA_DIR
    db_path = db_path or DB_PATH

    pdf_files = sorted(input_dir.glob("*.pdf"))
    summary = PipelineSummary(total_files=len(pdf_files))

    if not pdf_files:
        logger.warning(f"No PDF files found in {input_dir}")
        return summary

    conn = get_connection(db_path)

    for i, pdf_path in enumerate(pdf_files, start=1):
        logger.info(f"[{i}/{len(pdf_files)}] Processing {pdf_path.name}")
        print(f"[{i}/{len(pdf_files)}] {pdf_path.name} ... ", end="", flush=True)

        try:
            _process_one_file(pdf_path, conn, summary)
        except Exception as e:
            # This is the safety net for anything I didn't anticipate -
            # every step inside _process_one_file already has its own
            # specific error handling, but if something truly
            # unexpected happens, I still don't want it to kill the
            # whole batch.
            logger.error(f"Unexpected error processing {pdf_path.name}: {e}")
            summary.failed.append((pdf_path.name, f"Unexpected error: {e}"))
            print("FAILED (unexpected error)")

    conn.close()

    _log_summary(summary)
    return summary


def _process_one_file(pdf_path: Path, conn, summary: PipelineSummary) -> None:
    """
    Run the full preprocess -> extract -> transform -> validate -> store
    sequence for a single file, updating summary in place.

    Each stage can fail for its own specific reason, and I check for
    that immediately after each call rather than letting a bad result
    silently flow into the next stage.
    """

    # --- Stage 1: Preprocessing ---
    preprocess_result = validate_and_read_pdf(pdf_path)
    if not preprocess_result.is_valid:
        summary.failed.append((pdf_path.name, f"Preprocessing failed: {preprocess_result.reason}"))
        print(f"FAILED (preprocessing: {preprocess_result.reason})")
        return

    # --- Stage 2: Extraction ---
    extraction_result = extract_invoice(pdf_path)
    if not extraction_result.success:
        summary.failed.append((pdf_path.name, f"Extraction failed: {extraction_result.error_message}"))
        print(f"FAILED (extraction: {extraction_result.error_message})")
        return

    # --- Stage 3: Transformation ---
    transformed_invoice = transform_invoice(extraction_result.invoice)

    # --- Stage 4: Validation ---
    validation_result = validate_invoice(transformed_invoice)

    # --- Stage 5: Storage ---
    # Even invoices flagged "needs_review" still get saved - the point
    # of validation is to flag them for a human to look at later, not
    # to throw the data away. Only genuine failures (stages 1-2) result
    # in nothing being stored.
    save_invoice(conn, transformed_invoice, validation_result)

    if validation_result.status == "valid":
        summary.succeeded.append(pdf_path.name)
        print("OK")
    else:
        summary.needs_review.append(pdf_path.name)
        print(f"OK (needs review: {len(validation_result.issues)} issue(s))")


def _log_summary(summary: PipelineSummary) -> None:
    """Print and log a final report of the batch run."""

    print("\n--- Pipeline Summary ---")
    print(f"Total files:    {summary.total_files}")
    print(f"Valid:          {len(summary.succeeded)}")
    print(f"Needs review:   {len(summary.needs_review)}")
    print(f"Failed:         {len(summary.failed)}")

    if summary.needs_review:
        print("\nFiles flagged for review:")
        for filename in summary.needs_review:
            print(f"  - {filename}")

    if summary.failed:
        print("\nFailed files:")
        for filename, reason in summary.failed:
            print(f"  - {filename}: {reason}")

    logger.info(
        f"Pipeline run complete: {len(summary.succeeded)} valid, "
        f"{len(summary.needs_review)} need review, {len(summary.failed)} failed "
        f"(out of {summary.total_files} total)"
    )