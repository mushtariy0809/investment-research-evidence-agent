"""Verification agent tests — including the required scenario where the
extraction side produces a fabricated (unsupported) claim and verification
blocks it before it can reach a brief."""

from datetime import date

from app.agents.verification import VerificationAgent
from app.llm.mock_provider import MockProvider
from app.schemas.agent_io import EvidenceItem, Verdict

SOURCE = (
    "Total net revenue increased 14% to $612.4 million in fiscal 2023. "
    "Gross margin improved to 71.5% from 69.8% in the prior year."
)


def make_item(claim: str, excerpt: str) -> EvidenceItem:
    return EvidenceItem(
        claim=claim,
        excerpt=excerpt,
        section_name="Item 7. Management's Discussion and Analysis",
        filing_date=date(2024, 2, 15),
        accession_number="0000012345-24-000001",
        source_url="https://example.test/doc.htm",
        confidence=0.9,
    )


def test_fabricated_excerpt_is_blocked():
    """The core safety property: a quote that is not in the source fails the
    deterministic citation check — no LLM judgment can override it."""
    agent = VerificationAgent(MockProvider())
    item = make_item(
        claim="The filing states that revenue reached $999 billion.",
        excerpt="Revenue reached $999 billion in fiscal 2023.",  # fabricated
    )
    result = agent.verify(item, SOURCE)
    assert result.citation_valid is False
    assert result.verdict == Verdict.UNSUPPORTED
    assert not VerificationAgent.passes(result)


def test_missing_section_is_blocked():
    agent = VerificationAgent(MockProvider())
    item = make_item("Any claim.", "Any excerpt.")
    result = agent.verify(item, source_text=None)
    assert result.citation_valid is False
    assert not VerificationAgent.passes(result)


def test_grounded_claim_is_supported():
    agent = VerificationAgent(MockProvider())
    item = make_item(
        claim="The filing states that total net revenue increased 14% to "
              "$612.4 million in fiscal 2023.",
        excerpt="Total net revenue increased 14% to $612.4 million in fiscal 2023.",
    )
    result = agent.verify(item, SOURCE)
    assert result.citation_valid is True
    assert result.verdict == Verdict.SUPPORTED
    assert VerificationAgent.passes(result)


def test_claim_beyond_excerpt_is_not_fully_supported():
    agent = VerificationAgent(MockProvider())
    item = make_item(
        claim="The filing states that revenue increased because of strong demand "
              "in Asia, new products, acquisitions and favorable currency effects.",
        excerpt="Total net revenue increased 14% to $612.4 million in fiscal 2023.",
    )
    result = agent.verify(item, SOURCE)
    assert result.verdict in {Verdict.PARTIALLY_SUPPORTED, Verdict.UNSUPPORTED}


class GarbageProvider:
    """Simulates an LLM returning an unusable verdict."""

    name = "garbage"

    def run_task(self, task_name: str, payload: dict) -> dict:
        return {"verdict": "definitely-true!!", "explanation": "trust me"}


def test_unparseable_verdict_fails_closed():
    agent = VerificationAgent(GarbageProvider())
    item = make_item(
        claim="Gross margin improved to 71.5%.",
        excerpt="Gross margin improved to 71.5% from 69.8% in the prior year.",
    )
    result = agent.verify(item, SOURCE)
    # Citation is valid, but the unknown verdict must not pass.
    assert result.citation_valid is True
    assert result.verdict == Verdict.UNSUPPORTED
    assert not VerificationAgent.passes(result)
