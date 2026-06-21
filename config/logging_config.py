"""
Logging configuration for the invoice extraction pipeline.

This module doesn't define any loggers itself - every module in src/
already does that individually with `logger = logging.getLogger(__name__)`.
What's missing until this file runs is telling Python's logging system
WHERE those log messages should actually go and in what format.

I set up two destinations:
- A log file in logs/, one per run, named with a timestamp - this is
  the full detailed record (timestamp, level, module, message) for
  reviewing a run after the fact.
- The console, but only for WARNING and above - the console already
  has clean progress output from print() statements in pipeline.py,
  so I don't want routine INFO messages cluttering that. Only
  warnings/errors are important enough to also show up live.
"""

import logging
from datetime import datetime
from pathlib import Path

from config.settings import LOGS_DIR


def setup_logging() -> Path:
    """
    Configure logging for the whole application. Call this once, at
    the very start of main.py, before anything else runs.

    Returns the path to the log file that was created, so main.py can
    tell the user where to find it.
    """

    LOGS_DIR.mkdir(parents=True, exist_ok=True)

    # One file per run - timestamp in the filename means I never
    # overwrite a previous run's log, and I can compare logs across
    # multiple runs later if needed.
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    log_file = LOGS_DIR / f"pipeline_{timestamp}.log"

    # The format string controls what each line in the log file looks
    # like. asctime = timestamp, name = the module name (from
    # getLogger(__name__) in each file), levelname = INFO/WARNING/etc,
    # message = the actual text passed to logger.info(...) etc.
    file_formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = logging.FileHandler(log_file, encoding="utf-8")
    file_handler.setLevel(logging.INFO)
    file_handler.setFormatter(file_formatter)

    # Console handler is intentionally quieter - only WARNING and
    # above - since print() statements in pipeline.py already give
    # live progress feedback at the INFO level of detail.
    console_formatter = logging.Formatter(fmt="%(levelname)s: %(message)s")
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.WARNING)
    console_handler.setFormatter(console_formatter)

    # The root logger is the top-level logger every module's own
    # logger (logging.getLogger(__name__)) feeds into automatically.
    # Configuring handlers here applies them to log messages from
    # every module in the project, not just one file.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.INFO)
    root_logger.addHandler(file_handler)
    root_logger.addHandler(console_handler)

    # Azure's SDK logs a lot of low-level HTTP detail at INFO level by
    # default (request headers, retry attempts, etc.) - useful for
    # debugging Azure connectivity issues, but way too noisy for normal
    # runs. I raise its threshold so only warnings/errors from the SDK
    # itself come through, without losing my own pipeline's INFO logs.
    logging.getLogger("azure").setLevel(logging.WARNING)

    return log_file