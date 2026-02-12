import fitz  # PyMuPDF
from pathlib import Path
from typing import Optional
import json


class PDFExtractor:
    """Extract text, tables, and metadata from PDF documents using PyMuPDF."""

    def extract(self, file_path: str) -> dict:
        """
        Extract all content from a PDF file.
        Returns dict with: text, pages, page_count, metadata, sections, tables_found
        """
        doc = fitz.open(file_path)
        result = {
            "text": "",
            "pages": [],
            "page_count": len(doc),
            "metadata": doc.metadata,
            "sections": [],
            "tables_found": 0,
        }

        full_text_parts = []

        for page_num, page in enumerate(doc):
            page_text = page.get_text("text")
            full_text_parts.append(page_text)

            # Extract text blocks with positioning for section detection
            blocks = page.get_text("dict")["blocks"]
            page_data = {
                "page_number": page_num + 1,
                "text": page_text,
                "word_count": len(page_text.split()),
            }
            result["pages"].append(page_data)

            # Detect sections by font size (larger = heading)
            for block in blocks:
                if "lines" in block:
                    for line in block["lines"]:
                        for span in line["spans"]:
                            if span["size"] > 14:  # Likely a heading
                                result["sections"].append({
                                    "title": span["text"].strip(),
                                    "page": page_num + 1,
                                    "font_size": span["size"],
                                })

            # Detect tables
            tables = page.find_tables()
            if tables:
                result["tables_found"] += len(tables.tables)

        result["text"] = "\n\n".join(full_text_parts)
        doc.close()
        return result

    def extract_tables(self, file_path: str) -> list[dict]:
        """Extract tables as structured data."""
        doc = fitz.open(file_path)
        all_tables = []

        for page_num, page in enumerate(doc):
            tables = page.find_tables()
            for table in tables.tables:
                table_data = table.extract()
                if table_data and len(table_data) > 1:
                    headers = table_data[0]
                    rows = table_data[1:]
                    all_tables.append({
                        "page": page_num + 1,
                        "headers": headers,
                        "rows": rows,
                        "row_count": len(rows),
                    })

        doc.close()
        return all_tables


pdf_extractor = PDFExtractor()
