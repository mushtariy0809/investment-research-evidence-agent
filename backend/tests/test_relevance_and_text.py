from dataclasses import dataclass

from app.schemas.agent_io import TaskType
from app.services.relevance import keyword_score, rank_sections
from app.services.textutil import excerpt_appears_in, split_sentences


@dataclass
class Section:
    item_key: str
    name: str
    text: str
    char_count: int = 0


SECTIONS = [
    Section("1", "Item 1. Business", "We sell cloud software to retailers."),
    Section("1A", "Item 1A. Risk Factors",
            "Competition is intense. Cyber attacks could harm our platform."),
    Section("7", "Item 7. MD&A", "Revenue increased 14% driven by subscriptions."),
]


def test_rank_sections_prefers_task_prior():
    top = rank_sections("What are the risks?", TaskType.RISK_FACTORS, "10-K", SECTIONS)
    assert top[0].item_key == "1A"


def test_rank_sections_uses_keywords_for_custom_task():
    top = rank_sections("How much did revenue increase?", TaskType.CUSTOM, "10-K",
                        SECTIONS, top_n=1)
    assert top[0].item_key == "7"


def test_keyword_score_range():
    assert keyword_score("revenue increased", "Revenue increased 14%") == 1.0
    assert keyword_score("dividends", "Revenue increased 14%") == 0.0


def test_excerpt_matching_tolerates_quotes_and_whitespace():
    source = "The Company’s revenue — driven by “subscriptions” — grew."
    excerpt = 'The Company\'s revenue - driven by "subscriptions" - grew.'
    assert excerpt_appears_in(excerpt, source)


def test_excerpt_matching_rejects_fabrication():
    assert not excerpt_appears_in("Revenue fell 50%", "Revenue increased 14%")


def test_split_sentences_filters_short_fragments():
    sentences = split_sentences("Too short. This sentence is long enough to be "
                                "meaningfully quoted as filing evidence.")
    assert len(sentences) == 1
