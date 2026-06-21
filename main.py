"""
Entry point for the invoice extraction pipeline.

Run this file directly to process every PDF in sample_data/ through
the full pipeline (preprocess -> extract -> transform -> validate ->
store) and write the results into output/invoices.db.

Usage:
    python main.py
"""

import logging

from config.logging_config import setup_logging
from src.pipeline import run_pipeline


def main() -> None:
    # This has to run first, before any other module logs anything -
    # it's what connects every logger.info()/warning()/error() call
    # across the whole project to an actual file and console output.
    log_file = setup_logging()

    logger = logging.getLogger(__name__)
    logger.info("Starting invoice extraction pipeline run")

    print("Invoice Extraction Pipeline")
    print("=" * 40)

    summary = run_pipeline()

    print(f"\nLog file written to: {log_file}")

    logger.info("Pipeline run finished")


if __name__ == "__main__":
    main()