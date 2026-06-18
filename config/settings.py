"""
Application configuration.
Loads all settings from the .env file.
No API keys or secrets are hardcoded here.
"""

import os
from pathlib import Path
from dotenv import load_dotenv

# Load .env file from the project root
load_dotenv()

# Azure Document Intelligence
AZURE_DI_KEY: str = os.getenv("AZURE_DI_KEY", "")
AZURE_DI_ENDPOINT: str = os.getenv("AZURE_DI_ENDPOINT", "")

# Paths
BASE_DIR: Path = Path(__file__).resolve().parent.parent
SAMPLE_DATA_DIR: Path = BASE_DIR / "sample_data"
OUTPUT_DIR: Path = BASE_DIR / "output"
LOGS_DIR: Path = BASE_DIR / "logs"
DB_PATH: Path = BASE_DIR / "output" / "invoices.db"

# Pipeline settings
CONFIDENCE_THRESHOLD: float = 0.8  # Below this, flag for manual review
SUPPORTED_EXTENSIONS: list = [".pdf"]