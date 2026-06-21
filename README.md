# Invoice Extraction Pipeline

AI-powered pipeline that extracts structured data from PDF invoices using Azure Document Intelligence, cleans and cross-validates the numbers, and stores everything in a relational database.

Built for the Hitachi Solutions take-home case study.

## What it does

```
PDF invoices → PyMuPDF validation → Azure Document Intelligence → cleaning + cross-checks → plausibility validation → SQLite
```

Every invoice gets extracted, checked for internal consistency (does quantity × price = line total, does subtotal + VAT = total), checked for business plausibility (valid VAT rate, sane dates), and saved with a status of `valid` or `needs_review`. One bad file never stops the rest of the batch.

See `docs/use_case_documentation.md` for the full problem/persona/metrics writeup, and `docs/architecture.md` for the local and Azure production diagrams.

## Setup

```
python -m venv venv
venv\Scripts\activate
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
AZURE_DI_KEY=your_key_here
AZURE_DI_ENDPOINT=your_endpoint_here
```

(Azure Document Intelligence free tier - 500 pages/month, no payment required.)

## Run it

```
python main.py
```

Processes every PDF in `sample_data/`, prints a live summary, writes results to `output/invoices.db`, and logs the full run to `logs/`.

8 sample invoices are already included, generated with `sample_data/generate_invoices.py`.

## Run the tests

```
python -m unittest tests.test_invoice_validator tests.test_invoice_transformer -v
```

## Project structure

```
src/
  models.py              Pydantic schema (Invoice, LineItem)
  pipeline.py             orchestrator
  extractors/              file validation + Azure DI extraction
  transformers/            cleaning + cross-checks
  validators/              plausibility checks
  storage/                 SQLite
config/                  settings + logging setup
tests/                   unit tests
docs/                    architecture diagrams, use case doc
sample_data/             test invoices + generator script
```

## Why Azure Document Intelligence

Used the actual prebuilt `prebuilt-invoice` model rather than a custom OCR/regex approach, since it gives per-field confidence scores out of the box and handles layout variation without me writing parsing rules per template. The extraction code is identical between this prototype and a production deployment - only the tier changes (free F0 here, paid tier for volume in production).