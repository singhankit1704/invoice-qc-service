from typing import List, Dict, Any

from fastapi import FastAPI, UploadFile, File
from fastapi.responses import HTMLResponse
import tempfile
import os
import shutil

from . import extractor, validator


app = FastAPI(title="Invoice QC Service", version="1.0.0")


@app.get("/health")
async def health() -> Dict[str, str]:
    return {"status": "ok"}


@app.post("/validate-json")
async def validate_json(invoices: List[Dict[str, Any]]):
    """Validate a list of invoice objects (already in JSON form)."""
    results, summary = validator.validate_invoices(invoices)
    return {"summary": summary, "results": results}


@app.post("/extract-and-validate-pdfs")
async def extract_and_validate_pdfs(files: List[UploadFile] = File(...)):
    """Upload PDFs, extract invoices, then validate them."""
    with tempfile.TemporaryDirectory() as tmpdir:
        for f in files:
            dest_path = os.path.join(tmpdir, f.filename)
            with open(dest_path, "wb") as out:
                shutil.copyfileobj(f.file, out)

        invoices = extractor.extract_invoices_from_pdfs(tmpdir)

    results, summary = validator.validate_invoices(invoices)
    return {
        "extracted_invoices": invoices,
        "summary": summary,
        "results": results,
    }


@app.get("/console", response_class=HTMLResponse)
async def console() -> str:
    """Minimal HTML+JS QC console for manual testing."""
    return """
    <!DOCTYPE html>
    <html lang="en">
    <head>
      <meta charset="UTF-8" />
      <title>Invoice QC Console</title>
      <style>
        body { font-family: Arial, sans-serif; margin: 20px; }
        h1 { margin-bottom: 0.2rem; }
        .tabs { margin-top: 1rem; }
        button { cursor: pointer; }
        .tab-buttons button { margin-right: 8px; padding: 6px 12px; }
        .tab { display: none; margin-top: 1rem; }
        .tab.active { display: block; }
        textarea { width: 100%; min-height: 150px; }
        .badge { padding: 2px 6px; border-radius: 4px; font-size: 0.8rem; }
        .badge-valid { background: #d4edda; color: #155724; }
        .badge-invalid { background: #f8d7da; color: #721c24; }
        table { border-collapse: collapse; width: 100%; margin-top: 1rem; }
        th, td { border: 1px solid #ccc; padding: 6px 8px; font-size: 0.9rem; }
        th { background: #f2f2f2; }
        .controls { margin-top: 1rem; }
        .controls label { margin-right: 10px; }
        .summary { margin-top: 1rem; font-weight: bold; }
      </style>
    </head>
    <body>
      <h1>Invoice QC Console</h1>
      <p>Use this internal console to upload invoices or paste JSON, then run validation.</p>

      <div class="tabs">
        <div class="tab-buttons">
          <button type="button" onclick="showTab('pdfTab')">Upload PDFs</button>
          <button type="button" onclick="showTab('jsonTab')">Paste JSON</button>
        </div>

        <div id="pdfTab" class="tab active">
          <h2>Upload PDFs</h2>
          <form id="pdfForm">
            <input type="file" id="pdfFiles" name="files" multiple accept="application/pdf" />
            <button type="submit">Extract & Validate</button>
          </form>
        </div>

        <div id="jsonTab" class="tab">
          <h2>Paste JSON</h2>
          <p>Paste a JSON array of invoice objects below and click "Validate JSON".</p>
          <form id="jsonForm">
            <textarea id="jsonInput" placeholder="[ { \"invoice_number\": \"INV-001\", ... } ]"></textarea>
            <button type="submit">Validate JSON</button>
          </form>
        </div>
      </div>

      <div class="controls">
        <label>
          <input type="checkbox" id="filterInvalid" onchange="renderResults()"/>
          Show only invalid invoices
        </label>
      </div>

      <div id="summary" class="summary"></div>
      <div id="results"></div>

      <script>
        let lastResults = null;

        function showTab(id) {
          document.querySelectorAll('.tab').forEach(t => t.classList.remove('active'));
          document.getElementById(id).classList.add('active');
        }

        function setSummary(summary) {
          if (!summary) {
            document.getElementById('summary').textContent = '';
            return;
          }
          const { total_invoices, valid_invoices, invalid_invoices } = summary;
          document.getElementById('summary').textContent =
            `Total: ${total_invoices}, Valid: ${valid_invoices}, Invalid: ${invalid_invoices}`;
        }

        function renderResults() {
          const container = document.getElementById('results');
          container.innerHTML = '';
          if (!lastResults || !lastResults.results) return;

          const filterInvalid = document.getElementById('filterInvalid').checked;
          const rows = filterInvalid
            ? lastResults.results.filter(r => !r.is_valid)
            : lastResults.results;

          if (rows.length === 0) {
            container.textContent = 'No invoices to display.';
            return;
          }

          const table = document.createElement('table');
          const thead = document.createElement('thead');
          thead.innerHTML = '<tr><th>Invoice ID</th><th>Status</th><th>Errors</th></tr>';
          table.appendChild(thead);

          const tbody = document.createElement('tbody');
          rows.forEach(r => {
            const tr = document.createElement('tr');

            const tdId = document.createElement('td');
            tdId.textContent = r.invoice_id;

            const tdStatus = document.createElement('td');
            const span = document.createElement('span');
            span.classList.add('badge');
            if (r.is_valid) {
              span.classList.add('badge-valid');
              span.textContent = 'Valid';
            } else {
              span.classList.add('badge-invalid');
              span.textContent = 'Invalid';
            }
            tdStatus.appendChild(span);

            const tdErrors = document.createElement('td');
            tdErrors.textContent = r.errors && r.errors.length
              ? r.errors.join(', ')
              : '-';

            tr.appendChild(tdId);
            tr.appendChild(tdStatus);
            tr.appendChild(tdErrors);
            tbody.appendChild(tr);
          });

          table.appendChild(tbody);
          container.appendChild(table);
        }

        async function handlePdfSubmit(evt) {
          evt.preventDefault();
          const filesInput = document.getElementById('pdfFiles');
          if (!filesInput.files.length) {
            alert('Please select at least one PDF.');
            return;
          }

          const formData = new FormData();
          for (const file of filesInput.files) {
            formData.append('files', file);
          }

          const resp = await fetch('/extract-and-validate-pdfs', {
            method: 'POST',
            body: formData
          });

          if (!resp.ok) {
            alert('Error from server: ' + resp.status);
            return;
          }
          const data = await resp.json();
          lastResults = { results: data.results, summary: data.summary };
          setSummary(data.summary);
          renderResults();
        }

        async function handleJsonSubmit(evt) {
          evt.preventDefault();
          const text = document.getElementById('jsonInput').value.trim();
          if (!text) {
            alert('Please paste a JSON array of invoices.');
            return;
          }

          let payload;
          try {
            payload = JSON.parse(text);
          } catch (e) {
            alert('Invalid JSON: ' + e.message);
            return;
          }

          const resp = await fetch('/validate-json', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
          });

          if (!resp.ok) {
            alert('Error from server: ' + resp.status);
            return;
          }
          const data = await resp.json();
          lastResults = data;
          setSummary(data.summary);
          renderResults();
        }

        document.getElementById('pdfForm').addEventListener('submit', handlePdfSubmit);
        document.getElementById('jsonForm').addEventListener('submit', handleJsonSubmit);
      </script>
    </body>
    </html>
    """
