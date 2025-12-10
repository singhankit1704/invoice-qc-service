import argparse
import json
from typing import Any

from . import extractor, validator


def cmd_extract(args: argparse.Namespace) -> int:
    invoices = extractor.extract_invoices_from_pdfs(args.pdf_dir)
    with open(args.output, "w", encoding="utf-8") as f:
        json.dump(invoices, f, indent=2, ensure_ascii=False)
    print(f"Extracted {len(invoices)} invoices to {args.output}")
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    with open(args.input, "r", encoding="utf-8") as f:
        invoices = json.load(f)
    results, summary = validator.validate_invoices(invoices)

    report = {"summary": summary, "results": results}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    _print_summary(summary)

    return 0 if summary["invalid_invoices"] == 0 else 1


def cmd_full_run(args: argparse.Namespace) -> int:
    invoices = extractor.extract_invoices_from_pdfs(args.pdf_dir)
    results, summary = validator.validate_invoices(invoices)

    report = {"summary": summary, "results": results}
    with open(args.report, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    _print_summary(summary)

    return 0 if summary["invalid_invoices"] == 0 else 1


def _print_summary(summary: dict[str, Any]) -> None:
    print("\nValidation Summary")
    print("-------------------")
    print(f"Total invoices : {summary['total_invoices']}")
    print(f"Valid invoices : {summary['valid_invoices']}")
    print(f"Invalid invoices : {summary['invalid_invoices']}")
    if summary["error_counts"]:
        print("\nTop error types:")
        for err, count in sorted(summary["error_counts"].items(), key=lambda x: -x[1])[:10]:
            print(f"  {err}: {count}")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Invoice Extraction & QC CLI")
    subparsers = parser.add_subparsers(dest="command", required=True)

    p_extract = subparsers.add_parser("extract", help="Extract invoices from PDFs to JSON")
    p_extract.add_argument("--pdf-dir", required=True, help="Directory containing invoice PDFs")
    p_extract.add_argument("--output", required=True, help="Path to output JSON file")
    p_extract.set_defaults(func=cmd_extract)

    p_validate = subparsers.add_parser("validate", help="Validate invoices from JSON")
    p_validate.add_argument("--input", required=True, help="Input JSON file with invoices list")
    p_validate.add_argument("--report", required=True, help="Output JSON report path")
    p_validate.set_defaults(func=cmd_validate)

    p_full = subparsers.add_parser("full-run", help="Extract from PDFs and then validate")
    p_full.add_argument("--pdf-dir", required=True, help="Directory containing invoice PDFs")
    p_full.add_argument("--report", required=True, help="Output JSON report path")
    p_full.set_defaults(func=cmd_full_run)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
