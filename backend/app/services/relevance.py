"""Pick which filing sections are relevant to a research task.

Two signals, combined:
1. Task-type priors — a risk-factors question should look at Item 1A first.
2. Keyword overlap between the question and each section's text.

This is deliberately simple (no embeddings) for the MVP: it is transparent,
deterministic, testable, and measured by the evaluation script ("retrieval
relevance"). Swapping in embedding-based retrieval later only touches this file.
"""

import re
from collections import Counter

from app.schemas.agent_io import TaskType

# Item keys to prefer per task, for 10-K and 10-Q forms.
TASK_SECTION_PRIORS: dict[TaskType, dict[str, list[str]]] = {
    TaskType.BUSINESS_OVERVIEW: {"10-K": ["1", "7"], "10-Q": ["I-2", "I-1"]},
    TaskType.RISK_FACTORS: {"10-K": ["1A", "7A"], "10-Q": ["II-1A", "I-3"]},
    TaskType.REVENUE_SEGMENTS: {"10-K": ["7", "8", "1"], "10-Q": ["I-2", "I-1"]},
    TaskType.MANAGEMENT_DISCUSSION: {"10-K": ["7", "7A"], "10-Q": ["I-2"]},
    TaskType.MATERIAL_CHANGES: {"10-K": ["1A", "7"], "10-Q": ["II-1A", "I-2"]},
    TaskType.CUSTOM: {"10-K": [], "10-Q": []},
}

_STOPWORDS = frozenset(
    "the a an and or of to in for on with is are was were be been what which how why "
    "does do did about from as at by it its their our we they that this these those "
    "company filing describe main key".split()
)

_WORD_RE = re.compile(r"[a-z][a-z0-9'-]+")


def tokenize(text: str) -> list[str]:
    return [w for w in _WORD_RE.findall(text.lower()) if w not in _STOPWORDS]


def keyword_score(question: str, section_text: str) -> float:
    """Fraction of question keywords that appear in the section (0..1)."""
    q_tokens = set(tokenize(question))
    if not q_tokens:
        return 0.0
    section_counts = Counter(tokenize(section_text[:100_000]))
    hits = sum(1 for t in q_tokens if section_counts[t] > 0)
    return hits / len(q_tokens)


def rank_sections(
    question: str,
    task_type: TaskType,
    form_type: str,
    sections: list,  # objects with .item_key, .name, .text
    top_n: int = 3,
) -> list:
    priors = TASK_SECTION_PRIORS.get(task_type, {}).get(form_type, [])
    scored = []
    for section in sections:
        score = keyword_score(question, section.text)
        if section.item_key in priors:
            # Prior sections get a strong boost, ordered by prior position.
            score += 1.0 - 0.1 * priors.index(section.item_key)
        scored.append((score, section))
    scored.sort(key=lambda pair: pair[0], reverse=True)
    return [section for score, section in scored[:top_n] if score > 0]
