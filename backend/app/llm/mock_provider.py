"""Deterministic mock LLM provider.

Purpose: the whole application, the test suite, and the evaluation must run
without a paid API key and produce reproducible results.

Honesty matters here — the mock is not a canned-strings fake. It computes its
output from the actual payload:
- extraction returns real sentences copied verbatim from the provided section
  text (scored by keyword overlap with the question), so its citations are
  genuinely valid;
- verification judges claim/excerpt token overlap and negation mismatches;
- the brief writer assembles markdown from the evidence it was given.

So even in mock mode the pipeline's guarantees (grounded excerpts, blocked
unsupported claims) are exercised for real, not simulated.
"""

from app.llm.base import TASK_BRIEF, TASK_EXTRACT, TASK_VERIFY, LLMError
from app.services.relevance import keyword_score, tokenize
from app.services.textutil import split_sentences

_NEGATIONS = frozenset({"not", "no", "never", "none", "without", "decrease", "decreased",
                        "decline", "declined", "loss", "losses"})


class MockProvider:
    name = "mock"

    def run_task(self, task_name: str, payload: dict) -> dict:
        if task_name == TASK_EXTRACT:
            return self._extract(payload)
        if task_name == TASK_VERIFY:
            return self._verify(payload)
        if task_name == TASK_BRIEF:
            return self._brief(payload)
        raise LLMError(f"Unknown LLM task: {task_name}")

    # -- extraction -------------------------------------------------------

    def _extract(self, payload: dict) -> dict:
        question = payload["question"]
        max_items = payload.get("max_items", 6)
        candidates: list[tuple[float, dict]] = []

        for section in payload["sections"]:
            for sentence in split_sentences(section["text"])[:400]:
                score = keyword_score(question, sentence)
                if score <= 0:
                    continue
                candidates.append(
                    (
                        score,
                        {
                            "claim": f"The filing states that {sentence[:300].rstrip('.')}.",
                            "excerpt": sentence[:600],
                            "section_name": section["name"],
                            "filing_label": section.get("filing_label", "current"),
                            "confidence": round(min(0.95, 0.35 + 0.6 * score), 2),
                        },
                    )
                )

        # Deterministic ordering: score desc, then excerpt text as tiebreaker.
        candidates.sort(key=lambda pair: (-pair[0], pair[1]["excerpt"]))
        evidence = [item for _, item in candidates[:max_items]]
        note = None
        if not evidence:
            note = (
                "The selected filing sections do not appear to address this "
                "question; no evidence was extracted."
            )
        return {"evidence": evidence, "missing_info_note": note}

    # -- verification -----------------------------------------------------

    def _verify(self, payload: dict) -> dict:
        claim_tokens = set(tokenize(payload["claim"])) - {"filing", "states"}
        excerpt_tokens = set(tokenize(payload["excerpt"]))
        if not claim_tokens:
            return {"verdict": "unsupported",
                    "explanation": "The claim contains no checkable content."}

        overlap = len(claim_tokens & excerpt_tokens) / len(claim_tokens)

        # Polarity check runs even at modest overlap: "margin increased" vs a
        # source saying "margin declined" shares terms but flips direction.
        claim_neg = bool(set(tokenize(payload["claim"])) & _NEGATIONS)
        excerpt_neg = bool(excerpt_tokens & _NEGATIONS)
        if overlap >= 0.3 and claim_neg != excerpt_neg:
            return {"verdict": "contradicted",
                    "explanation": "The claim and the cited excerpt disagree in polarity "
                                   "(one negates what the other asserts)."}
        if overlap >= 0.75:
            return {"verdict": "supported",
                    "explanation": f"{overlap:.0%} of the claim's substantive terms appear "
                                   "in the cited excerpt, which states the same fact."}
        if overlap >= 0.4:
            return {"verdict": "partially_supported",
                    "explanation": f"Only {overlap:.0%} of the claim's substantive terms are "
                                   "grounded in the cited excerpt."}
        return {"verdict": "unsupported",
                "explanation": f"The cited excerpt shares only {overlap:.0%} of the claim's "
                               "substantive terms and does not establish it."}

    # -- brief writing ----------------------------------------------------

    def _brief(self, payload: dict) -> dict:
        lines = [
            f"## Research Brief: {payload['company_name']} "
            f"({payload['form_type']}, filed {payload['filing_date']})",
            "",
            "## Summary",
            f"This brief addresses: \"{payload['question']}\". "
            f"It is based on {len(payload['evidence'])} verified evidence item(s) "
            "drawn directly from the filing. All statements below cite their source.",
            "",
            "## Findings",
        ]
        partial_refs = []
        for item in payload["evidence"]:
            ref = item["ref"]
            lines.append(f"- {item['claim']} [{ref}]")
            lines.append(f"  > \"{item['excerpt']}\" — {item['section_name']}")
            if item["verdict"] == "partially_supported":
                partial_refs.append(ref)

        lines += ["", "## Limitations & Uncertainty"]
        if partial_refs:
            lines.append(
                f"- Evidence {', '.join(partial_refs)} was rated *partially supported*; "
                "treat those statements with additional caution."
            )
        lines.append(
            "- This brief reflects only the cited filing sections; other parts of the "
            "filing and outside sources were not consulted."
        )
        if payload.get("reviewer_comment"):
            lines.append(f"- Revised per reviewer comment: {payload['reviewer_comment']}")
        lines += [
            "",
            "*This document is generated for research and education. "
            "It is not investment advice.*",
        ]
        return {"markdown": "\n".join(lines)}
