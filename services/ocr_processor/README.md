# OCR Processor Service (Planned)

This service will extract text and transaction tables from the downloaded Congressional disclosure PDFs stored in `/data`.

---

## Planned Responsibilities

1. **PDF Ingestion**:
   - Reads PDFs from `/data/house_rep/{YEAR}/...` and `/data/senate/{YEAR}/...`.
   - Distinguishes between text-based electronic PDFs and scanned paper PDFs.
2. **Text & Table Extraction**:
   - Extract structured tables (Ticker, Asset Description, Transaction Type, Amount, Date).
   - Optical Character Recognition (OCR) fallback for scanned image documents using Tesseract / PaddleOCR / Docling.
3. **Structured Output**:
   - Output structured JSON / markdown files into `/data/processed_text/` for downstream indexing.
