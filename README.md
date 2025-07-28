# 📄 PDF Heading and Subheading Extractor

This project extracts structured **headings and subheadings** from PDF documents using a combination of font analysis, layout heuristics, and regex pattern matching. It's lightweight, explainable, and suitable for offline document intelligence tasks such as indexing, summarization, or persona-driven analysis.

---

## 🧠 Features

- Extracts headings and subheadings based on:
  - Font size and weight
  - Text spacing and alignment
  - Regex patterns (e.g., `1.`, `1.1.`, `I.`, etc.)
- Outputs a clean JSON structure
- No need for cloud/ML models – runs entirely offline
- Designed for documents like:
  - RFPs
  - Research papers
  - Business proposals

---

## 📦 Dependencies

Install the required Python packages:

```bash
pip install pdfplumber pymupdf


