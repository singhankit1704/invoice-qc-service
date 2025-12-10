from invoice_qc import validator


def test_valid_invoice_passes():
    invoice = {
        "invoice_number": "INV-001",
        "invoice_date": "2024-01-10",
        "due_date": "2024-01-20",
        "seller_name": "Seller Ltd",
        "buyer_name": "Buyer Ltd",
        "currency": "INR",
        "net_total": 100.0,
        "tax_amount": 18.0,
        "gross_total": 118.0,
        "line_items": [
            {"description": "Item A", "quantity": 1, "unit_price": 100.0, "line_total": 100.0}
        ],
    }
    results, summary = validator.validate_invoices([invoice])
    assert summary["total_invoices"] == 1
    assert summary["valid_invoices"] == 1
    assert summary["invalid_invoices"] == 0
    assert results[0]["is_valid"]
    assert results[0]["errors"] == []


def test_missing_required_and_mismatch_totals():
    invoice = {
        "invoice_number": "",
        "invoice_date": "10/01/2024",
        "due_date": "09/01/2024",
        "seller_name": "",
        "buyer_name": "Buyer Ltd",
        "currency": "XYZ",
        "net_total": 100.0,
        "tax_amount": 18.0,
        "gross_total": 150.0,
        "line_items": [
            {"description": "Item A", "quantity": 1, "unit_price": 100.0, "line_total": 50.0}
        ],
    }
    results, summary = validator.validate_invoices([invoice])
    r = results[0]
    assert not r["is_valid"]
    assert any(e.startswith("missing_field") for e in r["errors"])
    assert "invalid_value: currency" in r["errors"]
    assert "business_rule_failed: totals_mismatch" in r["errors"]
    assert "business_rule_failed: line_items_sum_mismatch" in r["errors"]
    assert "business_rule_failed: due_before_invoice_date" in r["errors"]
