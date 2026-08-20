"""Brief Writer Agent.

Receives ONLY verified evidence (enforced with a runtime check, not just
convention) and produces a markdown research brief with inline [E#] citations.
Output is compliance-checked: investment-advice language fails the run, and
the research-only disclaimer is guaranteed to be present.
"""

import re

from app.agents.verification import PASSING_VERDICTS
from app.llm.base import TASK_BRIEF, LLMError, LLMProvider
from app.schemas.agent_io import BriefInput

AGENT_NAME = "brief_writer"

DISCLAIMER = (
    "*This document is generated for research and education. "
    "It is not investment advice.*"
)

# Advice-like language the brief must never contain.
_BANNED = re.compile(
    r"\b(you should (buy|sell|hold)|we recommend (buying|selling|holding)|"
    r"price target|strong (buy|sell)|(buy|sell) rating)\b",
    re.IGNORECASE,
)


class BriefWriterAgent:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def run(self, brief_input: BriefInput) -> str:
        # Defense in depth: the orchestrator already filters, but this agent
        # refuses unverified evidence even if a future caller forgets to.
        for verdict in brief_input.verdicts:
            if verdict not in PASSING_VERDICTS:
                raise LLMError(
                    f"Brief writer received evidence with verdict '{verdict}'. "
                    "Only verified evidence may reach the brief writer."
                )

        payload = {
            "question": brief_input.question,
            "task_type": brief_input.task_type.value,
            "company_name": brief_input.company_name,
            "form_type": brief_input.form_type,
            "filing_date": str(brief_input.filing_date),
            "reviewer_comment": brief_input.reviewer_comment,
            "evidence": [
                {
                    "ref": f"E{i + 1}",
                    "claim": item.claim,
                    "excerpt": item.excerpt,
                    "section_name": item.section_name,
                    "verdict": verdict.value,
                }
                for i, (item, verdict) in enumerate(
                    zip(brief_input.evidence, brief_input.verdicts, strict=True)
                )
            ],
        }
        raw = self._provider.run_task(TASK_BRIEF, payload)
        markdown = str(raw.get("markdown", "")).strip()
        if not markdown:
            raise LLMError("Brief writer returned an empty brief.")

        if _BANNED.search(markdown):
            raise LLMError(
                "Generated brief contained investment-advice language and was rejected."
            )
        if "not investment advice" not in markdown.lower():
            markdown += f"\n\n{DISCLAIMER}"
        return markdown

    @staticmethod
    def insufficient_evidence_brief(question: str, note: str | None) -> str:
        """Honest fallback when no claim survived verification — no LLM involved."""
        default_note = ("The selected filing sections did not contain verifiable "
                        "evidence for this question.")
        return (
            "## Research Brief\n\n"
            f"**Question:** {question}\n\n"
            "## Findings\n\n"
            "No claims could be verified against the filing for this question, "
            "so no findings are reported.\n\n"
            "## Limitations & Uncertainty\n\n"
            f"- {note or default_note}\n"
            "- Consider rephrasing the question or selecting a different filing.\n\n"
            f"{DISCLAIMER}"
        )
