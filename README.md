# Invoice QC Service – Ankit Singh

A small but realistic **Invoice Extraction & Quality Control Service** 

It can:

- Read invoice PDFs from a folder and extract structured JSON
- Validate extracted (or provided) invoices against a set of rules
- Expose the validation via:
  - A Python CLI
  - A FastAPI HTTP API
- (Bonus) Provide:
  - A minimal web-based QC console (HTML + JS)
  - Dockerfile for containerisation
  - Basic unit tests

---

## 1. Schema & Validation Design

### 1.1 Invoice fields

Invoice-level schema (keys are JSON field names):

- `invoice_number` (str) – Business identifier shown on the invoice.
- `external_reference` (str, optional) – Any secondary reference, PO number, etc.
- `invoice_date` (str, ISO-ish) – Date on which the invoice is issued.
- `due_date` (str, ISO-ish, optional) – Payment due date.
- `seller_name` (str) – Name of the seller/supplier.
- `seller_tax_id` (str, optional) – Tax/VAT/GST ID of the seller.
- `buyer_name` (str) – Name of the buyer/customer.
- `buyer_tax_id` (str, optional) – Tax/VAT/GST ID of the buyer.
- `currency` (str) – 3-letter currency code (e.g. `INR`, `EUR`, `USD`) or inferred from symbol.
- `net_total` (float, optional) – Total before tax (subtotal).
- `tax_amount` (float, optional) – Total tax/VAT/GST amount.
- `gross_total` (float, optional) – Total including tax (amount payable).
- `line_items` (list of objects) – Optional line items.

Line item schema:

- `description` (str) – Human readable item/service description.
- `quantity` (float, optional) – Quantity.
- `unit_price` (float, optional) – Unit price.
- `line_total` (float, optional) – Total value for this line.

Line items are parsed best-effort: the rest of the system works even if the list is empty.

### 1.2 Validation rules

Implemented in `invoice_qc/validator.py`.

#### A. Completeness / format rules

1. **Required key fields must be present and non-empty**
   - Fields: `invoice_number`, `invoice_date`, `seller_name`, `buyer_name`, `currency`, `gross_total`.
   - Rationale: these are the minimal fields you need to index, understand, and pay an invoice.

2. **Dates must be parseable and in a reasonable range**
   - Supported formats: `YYYY-MM-DD`, `DD-MM-YYYY`, `DD/MM/YYYY`, `DD.MM.YYYY`, `YYYY/MM/DD`.
   - Range: `2000-01-01` to `2100-01-01`.
   - Fields: `invoice_date`, `due_date`.
   - Rationale: prevents OCR artefacts like `32/13/2099` being silently accepted.

3. **Currency must be in a known set or inferred from symbol**
   - Allowed codes: `INR`, `EUR`, `USD`, `GBP`, `CHF`, `JPY`.
   - If text contains `₹`, `€`, `$`, `£` it is mapped to the relevant code.
   - Rationale: ensures we store clean ISO-like currency codes.

4. **Totals should not be negative**
   - Fields: `net_total`, `tax_amount`, `gross_total`.
   - Rationale: normal B2B invoices should not have negative totals; negative numbers are flagged as anomalies.

#### B. Business rules

5. **Net + tax ≈ gross**
   - If all of `net_total`, `tax_amount`, and `gross_total` exist, check that:
     `net_total + tax_amount ≈ gross_total` (1% tolerance).
   - Rationale: basic accounting consistency.

6. **Sum of line item totals ≈ net total**
   - If line items have usable `line_total` values and `net_total` exists, check sum(line_total) ≈ net_total.
   - Rationale: ensures line-level and invoice-level numbers tie out.

7. **Due date must be on or after invoice date**
   - If both dates exist, require `due_date >= invoice_date`.
   - Rationale: payment due before the invoice date usually indicates extraction error.

#### C. Anomaly / duplicate rules

8. **No duplicate invoice for (invoice_number, seller_name, invoice_date) within one batch**
   - If more than one invoice shares this triple, they all get `anomaly:duplicate_invoice`.
   - Rationale: prevents double-processing or double-payment.

9. **Negative totals flagged**
   - Any negative `net_total`, `tax_amount`, or `gross_total` is flagged as `anomaly:negative_<field>`.
   - Rationale: signals potential credit notes or extraction issues that need manual review.

---

## 2. Architecture

### 2.1 Folder structure

```text
invoice-qc-service-ankit/
├── invoice_qc/
│   ├── __init__.py
│   ├── extractor.py      # PDF → text → JSON extraction
│   ├── validator.py      # Core validation rules / aggregation
│   ├── cli.py            # CLI entrypoint (python -m invoice_qc.cli …)
│   └── api.py            # FastAPI app (uvicorn invoice_qc.api:app …)
├── pdfs/                 # Place sample PDFs here (ignored by git)
├── tests/
│   └── test_validator_basic.py  # Simple unit tests for the validator
├── ai-notes/
│   └── README.md         # Notes about AI usage
├── Dockerfile
├── requirements.txt
├── .gitignore
├── .dockerignore
└── README.md
```

### 2.2 Data flow

```
flowchart LR
  A[PDF files] --> B[Extraction\n(invoice_qc.extractor)]
  B --> C[Invoice JSON list]
  C --> D[Validation core\n(invoice_qc.validator)]
  D --> E[Validation results + summary]

  C --> F[CLI / API]
  E --> F[CLI / API / Web Console]
```

- **Extraction**: `pdfplumber` reads all pages and joins the text. Regex and keyword-based heuristics map text to invoice fields and line items.
- **Validation**: pure-Python rules check completeness, formats, business logic, and duplicates.
- **Interfaces**: CLI orchestrates local runs; FastAPI exposes `/health`, `/validate-json`, `/extract-and-validate-pdfs`, and `/console` for a simple UI.

---

## 3. Setup & Installation

### 3.1 Python & virtual environment

- Python: **3.10+** recommended.

```bash
git clone <your-private-repo-url> invoice-qc-service-ankit
cd invoice-qc-service-ankit

python -m venv .venv
# Windows
.venv\Scripts\activate
# Linux/macOS
source .venv/bin/activate

pip install -r requirements.txt
```

Place the provided sample PDFs into the `pdfs/` folder.

---

## 4. CLI Usage

All CLI logic lives in `invoice_qc/cli.py` and is executed as a module.

### 4.1 Extract only

```bash
python -m invoice_qc.cli extract       --pdf-dir ./pdfs       --output ./extracted_invoices.json
```

- Reads all `.pdf` files under `./pdfs`
- Writes a JSON list to `extracted_invoices.json`

### 4.2 Validate only

```bash
python -m invoice_qc.cli validate       --input ./extracted_invoices.json       --report ./validation_report.json
```

- Reads the invoices from `extracted_invoices.json`
- Runs validation rules
- Writes:
  ```json
  {
    "summary": { ... },
    "results": [ ... ]
  }
  ```
- Prints a human-friendly summary to stdout.
- Exits with code `0` if all invoices are valid, otherwise `1`.

### 4.3 Full run (extract + validate)

```bash
python -m invoice_qc.cli full-run       --pdf-dir ./pdfs       --report ./validation_report.json
```

- Runs extraction and then validation in one command.
- Outputs the same JSON report structure as `validate`.

---

## 5. HTTP API

The HTTP service is implemented using **FastAPI** in `invoice_qc/api.py`.

### 5.1 Run the API

```bash
uvicorn invoice_qc.api:app --reload
```

Default: `http://127.0.0.1:8000`.

### 5.2 Endpoints

#### `GET /health`

Health check:

```json
{ "status": "ok" }
```

#### `POST /validate-json`

Validates a list of invoice JSON objects according to the same rules used by the CLI.

Example request body:

```json
[
  {
    "invoice_number": "INV-001",
    "invoice_date": "2024-01-10",
    "due_date": "2024-01-25",
    "seller_name": "ACME GmbH",
    "buyer_name": "Example AG",
    "currency": "EUR",
    "net_total": 50.0,
    "tax_amount": 9.5,
    "gross_total": 59.5,
    "line_items": [
      {
        "description": "Product A",
        "quantity": 10,
        "unit_price": 5.0,
        "line_total": 50.0
      }
    ]
  }
]
```

Example `curl`:

```bash
curl -X POST "http://127.0.0.1:8000/validate-json"       -H "Content-Type: application/json"       -d @extracted_invoices.json
```

#### `POST /extract-and-validate-pdfs` (bonus)

Accepts multiple PDF uploads, runs extraction and validation, and returns both:

```bash
curl -X POST "http://127.0.0.1:8000/extract-and-validate-pdfs"       -F "files=@pdfs/sample1.pdf"       -F "files=@pdfs/sample2.pdf"
```

Response shape:

```json
{
  "extracted_invoices": [ ... ],
  "summary": { ... },
  "results": [ ... ]
}
```

#### `GET /console` (bonus web UI)

- Serves a very small HTML+JS “Invoice QC Console” page.
- From the browser you can:
  - Upload PDFs and see extracted + validated results.
  - Paste arbitrary JSON invoices and validate them.

Access it at: `http://127.0.0.1:8000/console`

---

## 6. Minimal Web UI (QC Console)

The UI is served directly from FastAPI at `/console`:

- A simple HTML form to:
  - Upload one or more PDFs → calls `/extract-and-validate-pdfs`.
  - Paste raw JSON → calls `/validate-json`.
- Displays:
  - Summary (total/valid/invalid)
  - A table of invoices with:
    - `invoice_id`
    - Valid/invalid badge
    - List of errors (if any)
- Allows filtering:
  - “Show only invalid invoices” (basic front-end filtering in JavaScript).

This keeps the UI minimal but demonstrates how an internal tool could sit on
top of the validation API.

---

## 7. Docker Support

A basic `Dockerfile` is provided:

```bash
docker build -t invoice-qc-service .

docker run -p 8000:8000 invoice-qc-service
```

This will start `uvicorn invoice_qc.api:app` on port 8000 inside the container.

`.dockerignore` excludes local env, git history, test artefacts, and sample PDFs
to keep the image small.

---

## 8. Tests

Basic unit tests live under `tests/` and use `pytest`.

Run tests with:

```bash
pytest
```

Currently included tests:

- `test_validator_basic.py`
  - Checks that a minimal valid invoice passes.
  - Checks that missing required fields and inconsistent totals are flagged.

---

## 9. GitHub Repo Setup

For the private GitHub repository (e.g. `invoice-qc-service-ankit-singh`):

```bash
# from inside the project folder
git init
git add .
git commit -m "Initial commit: invoice QC service"

# create a private repo on GitHub, then add it as a remote
git remote add origin git@github.com:<your-username>/invoice-qc-service-ankit-singh.git

# or using HTTPS
# git remote add origin https://github.com/<your-username>/invoice-qc-service-ankit-singh.git

git push -u origin main
```

Suggested branching & commit style:

- Branches:
  - `main` – stable, demo-ready.
  - `feature/extraction-improvements` – tune regex, support more layouts.
  - `feature/ui-enhancements` – add filters, pagination, etc.
- Commits:
  - Small, meaningful messages like:
    - `feat: add duplicate invoice detection`
    - `fix: relax totals tolerance for rounding`
    - `chore: add Dockerfile and .dockerignore`

---

## 10. AI Usage Notes

Tools used:

- **ChatGPT / Copilot-style assistant** – for:
  - Brainstorming schema and validation rules.
  - Remembering some FastAPI syntax.
  - Drafting basic regex ideas for invoice fields.
  - Suggesting Dockerfile structure and pytest setup.

How I adjusted AI suggestions:

- Reduced dependencies to essentials:
  - Avoided heavy CLIs (e.g. click/typer) to keep `argparse` only.
  - Used simple `datetime.strptime` instead of additional date libraries.
- Simplified the UI:
  - Instead of a full React/Vue setup, used a single HTML+JS page served from FastAPI (`/console`).
- Kept extraction logic explainable:
  - Chose explicit regex patterns and helper functions so behaviour is clear in a code review or interview.

Additional notes or screenshots can be added under `ai-notes/`.

---

## 11. Assumptions & Limitations

- Extraction is tuned for relatively standard B2B invoices with textual content.
  - It will not handle scanned images without an OCR step.
  - Highly irregular layouts may partially fail to extract.
- Line items are parsed using simple heuristics (header + numeric columns).
  - Complex multi-line descriptions or discounts per line are not handled.
- Date formats are limited to a small common set.
- Supported currencies are a small, configurable set.
- No persistence layer is used; everything is in-memory for a batch.

These trade-offs aim to balance realism with clarity and time constraints for
the assignment.

---

## 12. Video

Add your screen-recording link here (Google Drive, "Anyone with the link"):

> **Video:** _TBD – replace with your public link_

