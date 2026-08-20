"""Verification Agent.

Independently checks each proposed claim against its cited source, in two
layers:

1. Deterministic citation check (code, not a model): the cited section must
   exist and the excerpt must appear in it verbatim (whitespace/quote-style
   insensitive). A fabricated quote fails here with certainty — no LLM
   judgment involved, so this layer cannot be sweet-talked by injected text.
2. Semantic check (LLM): does the excerpt actually support the claim?
   Verdicts: supported / partially_supported / unsupported / contradicted.

Only claims that pass BOTH layers may reach the brief writer. This agent never
modifies evidence — it only judges it, which keeps generation and verification
separated.
"""

from app.llm.base import TASK_VERIFY, LLMProvider
from app.schemas.agent_io import EvidenceItem, Verdict, VerificationResult
from app.services.textutil import excerpt_appears_in

AGENT_NAME = "verification"

# Verdicts that allow a claim into the brief.
PASSING_VERDICTS = {Verdict.SUPPORTED, Verdict.PARTIALLY_SUPPORTED}


class VerificationAgent:
    def __init__(self, provider: LLMProvider):
        self._provider = provider

    def verify(self, item: EvidenceItem, source_text: str | None) -> VerificationResult:
        # Layer 1: deterministic citation validation.
        if source_text is None:
            return VerificationResult(
                verdict=Verdict.UNSUPPORTED,
                citation_valid=False,
                explanation=(
                    f"The cited section '{item.section_name}' does not exist in the "
                    "filing, so the claim has no valid source."
                ),
            )
        if not excerpt_appears_in(item.excerpt, source_text):
            return VerificationResult(
                verdict=Verdict.UNSUPPORTED,
                citation_valid=False,
                explanation=(
                    "The cited excerpt does not appear verbatim in the cited section — "
                    "it was paraphrased or fabricated, so the citation is invalid."
                ),
            )

        # Layer 2: semantic support judgment.
        raw = self._provider.run_task(
            TASK_VERIFY,
            {
                "claim": item.claim,
                "excerpt": item.excerpt,
                "section_name": item.section_name,
                "section_text": source_text[:50_000],
            },
        )
        try:
            verdict = Verdict(raw.get("verdict", ""))
        except ValueError:
            # An unparseable verdict must fail closed, never pass through.
            verdict = Verdict.UNSUPPORTED
        explanation = str(raw.get("explanation", ""))[:2000] or "No explanation provided."
        return VerificationResult(
            verdict=verdict, citation_valid=True, explanation=explanation
        )

    @staticmethod
    def passes(result: VerificationResult) -> bool:
        return result.citation_valid and result.verdict in PASSING_VERDICTS
