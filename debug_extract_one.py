from invoice_qc.extractor import extract_text_from_pdf
import os

pdf_dir = "pdfs"

files = [f for f in os.listdir(pdf_dir) if f.lower().endswith(".pdf")]

if not files:
    print("No PDF files found in pdfs/ folder.")
else:
    for fname in files:
        pdf_path = os.path.join(pdf_dir, fname)
        print(f"\n\n======= Extracting from: {fname} =======\n")
        text = extract_text_from_pdf(pdf_path)
        print(text)
        print("\n======= End of Extraction =======\n")
