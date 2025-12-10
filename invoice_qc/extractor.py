import os
from typing import List, Dict, Any, Optional
import re

import pdfplumber


def extract_text_from_pdf(path: str) -> str:
    """Extract plain text from a PDF using pdfplumber."""
    text_parts: List[str] = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            page_text = page.extract_text() or ""
            text_parts.append(page_text)
    return "\n".join(text_parts)


def _search_first(patterns: List[str], text: str, flags: int = re.IGNORECASE) -> Optional[str]:
    """Try several regex patterns and return the first meaningful match."""
    for pattern in patterns:
        m = re.search(pattern, text, flags)
        if m:
            if m.lastindex:
                return m.group(1).strip()
            return m.group(0).strip()
    return None


def _parse_float(value: Optional[str]) -> Optional[float]:
    if not value:
        return None
    try:
        cleaned = value.strip()
        # Remove currency symbols and spaces
        cleaned = re.sub(r"[₹$€£]", "", cleaned)
        cleaned = cleaned.replace(" ", "")

        # Handle European style: 1.285,20 -> 1285.20
        if "," in cleaned and "." in cleaned:
            cleaned = cleaned.replace(".", "").replace(",", ".")
        elif "," in cleaned:
            # 64,00 -> 64.00
            cleaned = cleaned.replace(",", ".")
        # else: "1234.50" already fine

        return float(cleaned)
    except Exception:
        return None



def infer_currency_from_text(text: str) -> Optional[str]:
    """Infer currency either from explicit code or from symbol."""
    m = re.search(r"\b(INR|EUR|USD|GBP|CHF|JPY)\b", text)
    if m:
        return m.group(1)

    if "₹" in text:
        return "INR"
    if "€" in text:
        return "EUR"
    if "$" in text:
        return "USD"
    if "£" in text:
        return "GBP"

    return None


def extract_basic_fields(text: str) -> Dict[str, Any]:
    """Extract main invoice fields using regex heuristics.

    Tuned for the provided German B2B order/invoice PDFs.
    """

    # -------- invoice_number --------
    # Examples:
    # "ABC Corporation Bestellung AUFNR34343 im Auftrag von ..."
    # "Bestellung AUFNR34343 vom 22.05.2024"
    invoice_number = _search_first(
        [
            r"Bestellung\s+AUFNR(\S+)",  # AUFNR34343, AUFNR234953, etc.
            r"Invoice\s*(No\.?|Number|#)\s*[:\-]?\s*(\S+)",  # fallback for other layouts
        ],
        text,
    )

    # -------- invoice_date --------
    # From: "Bestellung AUFNR34343 vom 22.05.2024"
    invoice_date = _search_first(
        [
            r"Bestellung\s+AUFNR\S+\s+vom\s+([0-9]{1,2}\.[0-9]{1,2}\.[0-9]{4})",
            r"Invoice Date\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"Dated\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
        text,
    )

    # -------- due_date --------
    # Not explicitly present in samples; keep old patterns as fallback
    due_date = _search_first(
        [
            r"Due Date\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
            r"Payment Due\s*[:\-]?\s*([0-9]{1,2}[./-][0-9]{1,2}[./-][0-9]{2,4})",
        ],
        text,
    )

    # -------- seller_name --------
    # First line pattern: "ABC Corporation Bestellung AUFNR34343 ..."
    # We grab everything before "Bestellung".
    seller_name = _search_first(
        [
            r"^(.*?)\s+Bestellung\s+AUFNR",  # ABC Corporation, JKL Corporation, ERT Corporation
            r"Seller\s*[:\-]?\s*(.+)",
            r"Supplier\s*[:\-]?\s*(.+)",
            r"From\s*[:\-]?\s*(.+)",
        ],
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # -------- buyer_name --------
    # Lines like:
    # "Beispielname Unternehmen · Albertus-Magnus-Str. 8, Matternfeld, SL 44624 Kundenanschrift"
    # "Softwareunternehmen · Philipp-Ott-Str. 64, Süd Lenjaberg, SN 48103 Kundenanschrift"
    buyer_name = _search_first(
        [
            r"^(.*?)\s+·[^\n]*Kundenanschrift",  # text before '· ... Kundenanschrift'
            r"Buyer\s*[:\-]?\s*(.+)",
            r"Customer\s*[:\-]?\s*(.+)",
            r"Bill To\s*[:\-]?\s*(.+)",
            r"Ship To\s*[:\-]?\s*(.+)",
        ],
        text,
        flags=re.IGNORECASE | re.MULTILINE,
    )

    # -------- tax IDs (optional) --------
    seller_tax_id = _search_first(
        [
            r"(GSTIN|VAT No\.?|Tax ID)\s*[:\-]?\s*([A-Z0-9]+)",
        ],
        text,
    )
    buyer_tax_id = None  # not present in these samples

    # -------- currency & totals --------
    currency = infer_currency_from_text(text)

    # Net total: "Gesamtwert EUR 64,00"
    net_total = _parse_float(
        _search_first(
            [
                r"Gesamtwert\s+EUR\s+([0-9\.,]+)",  # first Gesamtwert = net total
                r"(Net Total|Sub Total|Subtotal)\s*[:\-]?\s*([0-9,]+(?:\.[0-9]+)?)",
            ],
            text,
        )
    )

    # Tax amount: "MwSt. 19,00% EUR 12,16"
    tax_amount = _parse_float(
        _search_first(
            [
                r"MwSt\.\s*[0-9,]+%\s+EUR\s+([0-9\.,]+)",
                r"(Tax|VAT|GST)[^\r\n]*?[:\-]?\s*([0-9,]+(?:\.[0-9]+)?)",
            ],
            text,
        )
    )

    # Gross total: "Gesamtwert inkl. MwSt. EUR 76,16"
    gross_total = _parse_float(
        _search_first(
            [
                r"Gesamtwert inkl\. MwSt\.\s+EUR\s+([0-9\.,]+)",
                r"(Grand Total|Total Amount Payable|Invoice Total|Total)\s*[:\-]?\s*([0-9,]+(?:\.[0-9]+)?)",
            ],
            text,
        )
    )

    return {
        "invoice_number": invoice_number,
        "invoice_date": invoice_date,
        "due_date": due_date,
        "seller_name": seller_name,
        "seller_tax_id": seller_tax_id,
        "buyer_name": buyer_name,
        "buyer_tax_id": buyer_tax_id,
        "currency": currency,
        "net_total": net_total,
        "tax_amount": tax_amount,
        "gross_total": gross_total,
    }


def extract_line_items(text: str) -> List[Dict[str, Any]]:
    """Very simple heuristic line-item parser.

    Looks for a header line with something like 'Description' and 'Qty'/'Quantity'
    and then parses subsequent lines until a blank or 'Total' row.
    """
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    header_index = None
    for i, ln in enumerate(lines):
        if re.search(r"description", ln, re.IGNORECASE) and (
            re.search(r"qty|quantity", ln, re.IGNORECASE)
            or re.search(r"rate|price", ln, re.IGNORECASE)
        ):
            header_index = i
            break

    if header_index is None:
        return []

    items: List[Dict[str, Any]] = []
    for ln in lines[header_index + 1 :]:
        if re.search(r"total", ln, re.IGNORECASE):
            break

        parts = ln.split()
        if not parts:
            continue

        maybe_total = _parse_float(parts[-1])
        if maybe_total is None:
            continue

        qty = None
        unit_price = None
        desc_tokens = []
        for p in parts[:-1]:
            if qty is None:
                q = _parse_float(p)
                if q is not None:
                    qty = q
                    continue
            if qty is not None and unit_price is None:
                u = _parse_float(p)
                if u is not None:
                    unit_price = u
                    continue
            desc_tokens.append(p)

        description = " ".join(desc_tokens) if desc_tokens else "Item"
        items.append(
            {
                "description": description,
                "quantity": qty,
                "unit_price": unit_price,
                "line_total": maybe_total,
            }
        )

    return items


def extract_invoices_from_pdfs(pdf_dir: str) -> List[Dict[str, Any]]:
    """Walk a folder, read all PDFs, and return a list of invoice dicts."""
    invoices: List[Dict[str, Any]] = []
    for fname in os.listdir(pdf_dir):
        if not fname.lower().endswith(".pdf"):
            continue
        path = os.path.join(pdf_dir, fname)
        try:
            text = extract_text_from_pdf(path)
        except Exception:
            invoices.append(
                {
                    "invoice_number": None,
                    "invoice_date": None,
                    "due_date": None,
                    "seller_name": None,
                    "seller_tax_id": None,
                    "buyer_name": None,
                    "buyer_tax_id": None,
                    "currency": None,
                    "net_total": None,
                    "tax_amount": None,
                    "gross_total": None,
                    "line_items": [],
                    "_source_file": fname,
                    "_extraction_error": True,
                }
            )
            continue

        base_fields = extract_basic_fields(text)
        line_items = extract_line_items(text)

        invoice: Dict[str, Any] = {**base_fields}
        invoice["line_items"] = line_items
        invoice["_source_file"] = fname
        invoice["_extraction_error"] = False
        invoices.append(invoice)

    return invoices
