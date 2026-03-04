"""Test the table extractor — works on any PDF in the uploads directory."""
import sys
import glob
sys.path.insert(0, "/Users/tvishakhanna/Developer/Trace-Lit/backend")

import pymupdf4llm
from domain.extraction.table_extractor import extract_tables, tables_to_markdown_sections

# Find all uploaded PDFs
pdfs = sorted(glob.glob("/Users/tvishakhanna/Developer/Trace-Lit/backend/data/uploads/**/*.pdf", recursive=True))
if not pdfs:
    pdfs = sorted(glob.glob("/Users/tvishakhanna/Developer/Trace-Lit/data/uploads/**/*.pdf", recursive=True))

if not pdfs:
    print("No PDFs found in uploads/")
    sys.exit(1)

for pdf_path in pdfs:
    print(f"\n{'='*70}")
    print(f"PDF: {pdf_path}")
    print(f"{'='*70}")

    # Get markdown pages (same as pdf_processor does)
    page_chunks = pymupdf4llm.to_markdown(pdf_path, page_chunks=True, write_images=False)
    md_pages = [c.get("text", "") if isinstance(c, dict) else str(c) for c in page_chunks]

    tables = extract_tables(pdf_path, markdown_pages=md_pages)
    print(f"\nTables found: {len(tables)}")

    for t in tables:
        print(f"\n--- Page {t.page_number}, #{t.table_index} [{t.source}] ---")
        if t.caption:
            print(f"Caption: {t.caption}")
        lines = t.markdown.split("\n")
        for l in lines[:15]:
            print(f"  {l}")
        if len(lines) > 15:
            print(f"  ... ({len(lines) - 15} more rows)")

    # Full pipeline test
    print(f"\n--- Pipeline integration ---")
    from domain.extraction.pdf_processor import extract_pdf
    result = extract_pdf(pdf_path)
    table_sections = [s for s in result["sections"] if s.get("is_table")]
    print(f"Total sections: {len(result['sections'])}, Table sections: {len(table_sections)}")
    for s in table_sections:
        print(f"  [{s['title']}] ({len(s['content'])} chars)")
    print()
