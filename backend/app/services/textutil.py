"""Small text utilities shared by extraction, verification, and the mock LLM."""

import re

_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9“\"(])")


def split_sentences(text: str) -> list[str]:
    """Naive sentence splitter — good enough for scoring/quoting filing prose."""
    parts = _SENTENCE_SPLIT_RE.split(text)
    return [p.strip() for p in parts if len(p.strip()) >= 30]


def normalize_for_match(text: str) -> str:
    """Normalize text so an excerpt can be matched against its source even if
    whitespace, quote style, or our delimiter-neutralized brackets differ."""
    text = text.lower()
    text = (
        text.replace("‘", "'").replace("’", "'")
        .replace("“", '"').replace("”", '"')
        .replace("–", "-").replace("—", "-")
        .replace("‹", "<").replace("›", ">")  # undo injection-guard neutralization
    )
    return re.sub(r"\s+", " ", text).strip()


def excerpt_appears_in(excerpt: str, source: str) -> bool:
    """The deterministic citation check: is the excerpt verbatim in the source?"""
    return normalize_for_match(excerpt) in normalize_for_match(source)
