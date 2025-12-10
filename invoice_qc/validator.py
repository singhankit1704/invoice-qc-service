from typing import List, Dict, Any, Tuple
from collections import Counter
from datetime import datetime, date


REQUIRED_FIELDS = [
    "invoice_number",
    "invoice_date",
    "seller_name",
    "buyer_name",
    "currency",
    "gross_total",
]


def _parse_date(value: str) -> date | None:
    if not value:
        return None
    value = value.strip()
    formats = ["%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d.%m.%Y", "%Y/%m/%d"]
    for fmt in formats:
        try:
            return datetime.strptime(value, fmt).date()
        except ValueError:
            continue
    return None


def _approx_equal(a: float | None, b: float | None, rel_tol: float = 0.01, abs_tol: float = 0.01) -> bool:
    if a is None or b is None:
        return False
    diff = abs(a - b)
    return diff <= max(abs_tol, rel_tol * max(abs(a), abs(b)))


def validate_invoice(invoice: Dict[str, Any]) -> Dict[str, Any]:
    """Validate a single invoice and return the per-invoice result structure."""
    errors: List[str] = []

    for field in REQUIRED_FIELDS:
        if invoice.get(field) in (None, ""):
            errors.append(f"missing_field: {field}")

    inv_date_raw = invoice.get("invoice_date") or ""
    inv_date = _parse_date(inv_date_raw)
    if inv_date_raw and not inv_date:
        errors.append("invalid_format: invoice_date")
    elif inv_date:
        if not (date(2000, 1, 1) <= inv_date <= date(2100, 1, 1)):
            errors.append("out_of_range: invoice_date")

    due_date_raw = invoice.get("due_date") or ""
    due_date = _parse_date(due_date_raw)
    if due_date_raw and not due_date:
        errors.append("invalid_format: due_date")
    elif due_date:
        if not (date(2000, 1, 1) <= due_date <= date(2100, 1, 1)):
            errors.append("out_of_range: due_date")

    currency = invoice.get("currency")
    if currency:
        allowed = {"INR", "EUR", "USD", "GBP", "CHF", "JPY"}
        if currency.upper() not in allowed:
            errors.append("invalid_value: currency")
    else:
        errors.append("missing_field: currency")

    for fld in ["net_total", "tax_amount", "gross_total"]:
        val = invoice.get(fld)
        if isinstance(val, (int, float)) and val < 0:
            errors.append(f"anomaly:negative_{fld}")

    net_total = invoice.get("net_total")
    tax_amount = invoice.get("tax_amount")
    gross_total = invoice.get("gross_total")

    if all(isinstance(v, (int, float)) for v in [net_total, tax_amount, gross_total]):
        if not _approx_equal(net_total + tax_amount, gross_total):
            errors.append("business_rule_failed: totals_mismatch")

    line_items = invoice.get("line_items") or []
    line_sum = 0.0
    any_line_total = False
    for li in line_items:
        lt = li.get("line_total")
        if isinstance(lt, (int, float)):
            any_line_total = True
            line_sum += lt
    if any_line_total and isinstance(net_total, (int, float)):
        if not _approx_equal(line_sum, net_total):
            errors.append("business_rule_failed: line_items_sum_mismatch")

    if inv_date and due_date:
        if due_date < inv_date:
            errors.append("business_rule_failed: due_before_invoice_date")

    invoice_id = invoice.get("invoice_number") or invoice.get("_source_file") or "<unknown>"
    is_valid = len(errors) == 0

    return {
        "invoice_id": invoice_id,
        "is_valid": is_valid,
        "errors": errors,
    }


def validate_invoices(invoices: List[Dict[str, Any]]) -> Tuple[List[Dict[str, Any]], Dict[str, Any]]:
    """Validate a list of invoices, including duplicate detection and summary aggregation."""
    results: List[Dict[str, Any]] = []

    for inv in invoices:
        result = validate_invoice(inv)
        results.append(result)

    key_counts = Counter()
    for inv in invoices:
        key = (
            inv.get("invoice_number") or "",
            inv.get("seller_name") or "",
            inv.get("invoice_date") or "",
        )
        key_counts[key] += 1

    for (inv_num, seller_name, inv_date_raw), count in key_counts.items():
        if count > 1 and (inv_num or seller_name or inv_date_raw):
            for result in results:
                if inv_num and result["invoice_id"] == inv_num:
                    result["errors"].append("anomaly:duplicate_invoice")
                    result["is_valid"] = False

    total = len(results)
    invalid = sum(1 for r in results if not r["is_valid"])
    valid = total - invalid

    from collections import Counter as _Counter
    error_counts: _Counter[str] = _Counter()
    for r in results:
        error_counts.update(r["errors"])

    summary = {
        "total_invoices": total,
        "valid_invoices": valid,
        "invalid_invoices": invalid,
        "error_counts": dict(error_counts),
    }

    return results, summary
