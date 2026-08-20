"""Turn a raw SEC filing (HTML) into named plain-text sections.

Two steps:
1. HTML -> text with a small stdlib HTMLParser subclass (no extra dependency;
   the need is only "strip tags, keep block boundaries as newlines").
2. Split the text at "Item X" headings. SEC filings are inconsistent, so this
   is best-effort by design: table-of-contents entries produce tiny segments
   which we drop, and if detection fails entirely we fall back to fixed-size
   chunks so the pipeline still works on any document.
"""

import re
from dataclasses import dataclass
from html.parser import HTMLParser

# Tags that visually end a line/block in a rendered filing.
_BLOCK_TAGS = {
    "p", "div", "br", "tr", "table", "li", "h1", "h2", "h3", "h4", "h5", "h6",
    "section", "article",
}
_SKIP_TAGS = {"script", "style", "head", "title"}


class _TextExtractor(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")
        elif tag == "td":
            self.parts.append(" ")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0:
            self.parts.append(data)


def html_to_text(html: str) -> str:
    extractor = _TextExtractor()
    extractor.feed(html)
    text = "".join(extractor.parts)
    text = text.replace("\xa0", " ")  # non-breaking spaces are everywhere in filings
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


ITEM_TITLES_10K = {
    "1": "Business",
    "1A": "Risk Factors",
    "1B": "Unresolved Staff Comments",
    "1C": "Cybersecurity",
    "2": "Properties",
    "3": "Legal Proceedings",
    "4": "Mine Safety Disclosures",
    "5": "Market for Registrant's Common Equity",
    "6": "Selected Financial Data / Reserved",
    "7": "Management's Discussion and Analysis",
    "7A": "Quantitative and Qualitative Disclosures About Market Risk",
    "8": "Financial Statements and Supplementary Data",
    "9": "Changes in and Disagreements with Accountants",
    "9A": "Controls and Procedures",
    "9B": "Other Information",
    "9C": "Disclosure Regarding Foreign Jurisdictions",
    "10": "Directors, Executive Officers and Corporate Governance",
    "11": "Executive Compensation",
    "12": "Security Ownership",
    "13": "Certain Relationships and Related Transactions",
    "14": "Principal Accountant Fees and Services",
    "15": "Exhibits and Financial Statement Schedules",
}

ITEM_TITLES_10Q = {
    "I-1": "Financial Statements",
    "I-2": "Management's Discussion and Analysis",
    "I-3": "Quantitative and Qualitative Disclosures About Market Risk",
    "I-4": "Controls and Procedures",
    "II-1": "Legal Proceedings",
    "II-1A": "Risk Factors",
    "II-2": "Unregistered Sales of Equity Securities",
    "II-3": "Defaults Upon Senior Securities",
    "II-4": "Mine Safety Disclosures",
    "II-5": "Other Information",
    "II-6": "Exhibits",
}

# "Item 1A." / "ITEM 7:" / "Item 2 —" at the start of a line.
_ITEM_RE = re.compile(r"^\s*item\s+(\d{1,2}[A-C]?)\s*[.:—–-]?\s", re.IGNORECASE | re.MULTILINE)
_PART_RE = re.compile(r"^\s*part\s+(I{1,3}|IV)\b", re.IGNORECASE | re.MULTILINE)

# Segments shorter than this are almost certainly table-of-contents entries.
_MIN_SECTION_CHARS = 400
_FALLBACK_CHUNK_CHARS = 20_000


@dataclass
class ParsedSection:
    item_key: str
    name: str
    text: str


def _current_part(text: str, pos: int) -> str:
    """The most recent 'PART I/II' marker before pos (10-Q items repeat per part)."""
    part = ""
    for m in _PART_RE.finditer(text, 0, pos):
        part = m.group(1).upper()
    return part


def split_sections(text: str, form_type: str) -> list[ParsedSection]:
    matches = list(_ITEM_RE.finditer(text))
    segments: dict[str, str] = {}

    for i, m in enumerate(matches):
        start = m.start()
        end = matches[i + 1].start() if i + 1 < len(matches) else len(text)
        body = text[start:end].strip()
        if len(body) < _MIN_SECTION_CHARS:
            continue  # table-of-contents entry or empty item
        key = m.group(1).upper()
        if form_type == "10-Q":
            part = _current_part(text, start)
            key = f"{'II' if part == 'II' else 'I'}-{key}"
        # If the same item appears twice (e.g. TOC survived the length filter),
        # keep the longer body — the real section.
        if key not in segments or len(body) > len(segments[key]):
            segments[key] = body

    titles = ITEM_TITLES_10Q if form_type == "10-Q" else ITEM_TITLES_10K
    sections = [
        ParsedSection(
            item_key=key,
            name=f"Item {key}. {titles.get(key, 'Untitled')}",
            text=body,
        )
        for key, body in segments.items()
    ]

    if len(sections) < 2:
        # Heading detection failed (scanned PDF, unusual markup, ...).
        # Fall back to fixed-size chunks so research still works.
        sections = [
            ParsedSection(
                item_key=f"FULL-{n + 1}",
                name=f"Full document (part {n + 1})",
                text=text[i:i + _FALLBACK_CHUNK_CHARS],
            )
            for n, i in enumerate(range(0, len(text), _FALLBACK_CHUNK_CHARS))
        ]

    return sections
