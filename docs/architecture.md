# Architecture

Two diagrams, both in this folder as editable draw.io files:

- **`architecture_local.drawio`** - the current local prototype. `main.py` triggers `pipeline.py`, which orchestrates 5 stages in sequence (preprocessing, Azure DI extraction, transformation, validation, SQLite storage), all sharing the `models.py` schema, with every stage logging to a local file.

- **`architecture_azure.drawio`** - the production equivalent. Blob Storage + Event Grid trigger a Fabric Data Pipeline, which orchestrates the same 5 steps as individual Azure Functions, writing to Azure SQL Database instead of SQLite, with logging centralized in Application Insights.

Open either file at [app.diagrams.net](https://app.diagrams.net) via File → Open from → Device.

## Quick reference: local → production mapping

| Stage | Local | Production |
|---|---|---|
| Trigger | `python main.py` (manual) | Blob Storage + Event Grid (automatic) |
| Orchestration | `pipeline.py` | Fabric Data Pipeline |
| Preprocessing | `pdf_preprocessor.py` | Azure Function (same code) |
| Extraction | `azure_extractor.py` (Azure DI, free F0 tier) | Azure Function (same code, paid tier) |
| Transformation | `invoice_transformer.py` | Azure Function (same code) |
| Validation | `invoice_validator.py` | Azure Function (same code) |
| Storage | SQLite (`invoices.db`) | Azure SQL Database |
| Logging | Local `.log` files | Application Insights |
| Shared schema | `models.py` imported directly | `models.py` packaged as a shared library across Functions |
