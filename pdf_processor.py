import pdfplumber
import re
import json
from typing import Dict, List, Any
from collections import Counter
from difflib import SequenceMatcher
import io

class PDFProcessor:
    def __init__(
        self,
        max_pages: int = 50,
        font_size_threshold: float = 1.2,
        min_heading_score: int = 60,
        toc_skip_pages: int = 2,
        header_footer_ratio: float = 0.1,
        verbose: bool = False,
        debug: bool = False
    ):
        self.max_pages = max_pages
        self.font_size_threshold = font_size_threshold
        self.min_heading_score = min_heading_score
        self.toc_skip_pages = toc_skip_pages
        self.header_footer_ratio = header_footer_ratio
        self.verbose = verbose
        self.debug = debug
        self.rejected_blocks = []

    def _similar(self, a: str, b: str) -> bool:
        return SequenceMatcher(None, a, b).ratio() > 0.85

    def _calculate_vertical_spacing(self, current_y: float, sorted_chars: List[Dict[str, Any]]) -> float:
        above_chars = [c for c in sorted_chars if c.get('y0', 0) > current_y]
        if not above_chars:
            return 0
        closest_above = min(above_chars, key=lambda c: c.get('y0', 0) - current_y)
        return closest_above.get('y0', current_y) - current_y

    def _group_chars_into_blocks(self, chars: List[Dict[str, Any]]) -> List[List[Dict[str, Any]]]:
        chars.sort(key=lambda c: (-c['y0'], c['x0']))
        blocks = []
        block = []
        last_y = None
        for char in chars:
            if last_y is not None and abs(char['y0'] - last_y) > 5:
                blocks.append(block)
                block = []
            block.append(char)
            last_y = char['y0']
        if block:
            blocks.append(block)
        return blocks

    def _block_text(self, block: List[Dict[str, Any]]) -> str:
        return ''.join([c['text'] for c in block])

    def _is_all_caps(self, text: str) -> bool:
        return text.isupper() and any(c.isalpha() for c in text)

    def _is_title_case(self, text: str) -> bool:
        words = text.split()
        return all(w[0].isupper() for w in words if w)

    def _is_font_bold(self, block: List[Dict[str, Any]]) -> bool:
        fonts = [c.get("fontname", "") for c in block]
        bold_fonts = [f for f in fonts if "Bold" in f or "bold" in f]
        return len(bold_fonts) / len(fonts) > 0.6 if fonts else False

    def _calculate_heading_score(self, text: str, font_size: float, is_bold: bool, spacing: float) -> float:
        score = 0
        if self._is_all_caps(text): score += 20
        if self._is_title_case(text): score += 10
        if is_bold: score += 10
        score += font_size * self.font_size_threshold
        score += spacing * 0.5
        return score

    def _assign_heading_levels(self, headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        font_sizes = sorted({h['font_size'] for h in headings}, reverse=True)
        size_to_level = {size: f"H{i+1}" for i, size in enumerate(font_sizes)}
        for h in headings:
            h['level'] = size_to_level.get(h['font_size'], "H5")
        return headings

    def _deduplicate_headings(self, headings: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        seen = []
        unique = []
        for h in headings:
            is_duplicate = False
            for s in seen:
                if h['page'] == s['page'] and self._similar(h['text'].lower(), s['text'].lower()):
                    is_duplicate = True
                    break
            if not is_duplicate:
                seen.append(h)
                unique.append(h)
        return sorted(unique, key=lambda h: h['page'])

    def _extract_headings(self, pdf, title) -> List[Dict[str, Any]]:
        headings = []
        toc_detected = False
        toc_start_page = -1

        for i, page in enumerate(pdf.pages[1:self.max_pages]):
            chars = page.chars
            if not chars:
                continue

            blocks = self._group_chars_into_blocks(chars)
            page_height = page.height
            top_margin = page_height * self.header_footer_ratio
            bottom_margin = page_height * (1 - self.header_footer_ratio)

            for block in blocks:
                if not block:
                    continue

                block_y0 = block[0]['y0']
                block_y1 = block[0]['top']
                text = self._block_text(block).strip()
                reasons = []

                if block_y0 > bottom_margin or block_y1 < top_margin:
                    reasons.append("header/footer region")

                if len(text) < 3 or not any(c.isalpha() for c in text):
                    reasons.append("too short or no letters")

                if self._similar(text, title) or text.strip().lower() == title.strip().lower():
                    if self.debug:
                        self.rejected_blocks.append({"page": i, "text": text, "reasons": ["matches title"]})
                    continue

                if "table of contents" in text.lower():
                    toc_detected = True
                    toc_start_page = i
                    headings.append({
                        'text': "Table of Contents",
                        'page': i,
                        'font_size': max(c['size'] for c in block),
                        'score': 100
                    })
                    continue

                if toc_detected and toc_start_page >= 0 and i <= toc_start_page + self.toc_skip_pages - 1:
                    reasons.append("ToC page skipped")

                if re.match(r'^.*\.{2,}\s*\d+\s*$', text):
                    reasons.append("dotted ToC entry")

                if re.match(r'^\d+\.\d+\s+\d{1,2} [A-Z]{3,9} \d{4}\s+.+$', text):
                    reasons.append("version table entry")

                if re.match(r'^[•\-]\s*\w+', text):
                    reasons.append("bullet point")

                if re.match(r'^\(?\d+\)?[\.\)]?\s+\w+', text):
                    reasons.append("numbered paragraph")

                if reasons:
                    if self.debug:
                        self.rejected_blocks.append({"page": i, "text": text, "reasons": reasons})
                    continue

                font_size = max(c['size'] for c in block)
                is_bold = self._is_font_bold(block)
                spacing = self._calculate_vertical_spacing(block[0]['y0'], chars)
                score = self._calculate_heading_score(text, font_size, is_bold, spacing)

                if (
                    (score >= self.min_heading_score and (is_bold or self._is_all_caps(text)))
                    or (len(text.split()) <= 10 and font_size >= 10)
                    or re.match(r'^\d+\.\s', text) or re.match(r'^\d+\.\d+\s', text)
                ):
                    headings.append({
                        'text': text,
                        'page': i,
                        'font_size': round(font_size, 1),
                        'score': score
                    })
                else:
                    if self.debug:
                        self.rejected_blocks.append({"page": i, "text": text, "reasons": ["low score"]})

        headings = self._deduplicate_headings(headings)
        headings = self._assign_heading_levels(headings)
        for h in headings:
            h.pop('score', None)
            h.pop('font_size', None)
        return headings

    def _extract_title(self, pdf) -> str:
        if pdf.pages:
            first_page = pdf.pages[0]
            chars = first_page.chars
            if chars:
                max_size = max(char.get('size', 0) for char in chars)
                title_chars = [c for c in chars if c.get('size', 0) >= max_size * 0.9]
                page_width = first_page.width
                title_chars = [c for c in title_chars if 0.2 * page_width < c['x0'] < 0.8 * page_width]
                if title_chars:
                    title_chars.sort(key=lambda c: (-c.get('y0', 0), c.get('x0', 0)))
                    text = ''.join([c.get('text', '') for c in title_chars])
                    title = re.sub(r'\s+', ' ', text).split('\n')[0][:100].strip()
                    if title:
                        return title
        if pdf.metadata and pdf.metadata.get('Title'):
            title = pdf.metadata['Title']
            if title and title.strip():
                return title.strip()
        return "Untitled Document"

    def process_pdf(self, uploaded_file) -> Dict[str, Any]:
        try:
            uploaded_file.seek(0)
            with pdfplumber.open(io.BytesIO(uploaded_file.read())) as pdf:
                if len(pdf.pages) > self.max_pages:
                    raise ValueError(f"PDF exceeds {self.max_pages} pages.")
                title = self._extract_title(pdf)
                outline = self._extract_headings(pdf, title)
                result = {
                    "title": title,
                    "outline": outline
                }
                if self.debug:
                    result["rejected"] = self.rejected_blocks
                return result
        except Exception as e:
            raise Exception(f"Failed to process PDF: {str(e)}")

    def process_file_to_json(self, filepath: str) -> str:
        try:
            with open(filepath, "rb") as f:
                result = self.process_pdf(f)
                return json.dumps(result, indent=4, ensure_ascii=False)
        except Exception as e:
            return json.dumps({"error": str(e)})

