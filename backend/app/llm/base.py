"""Provider interface for all LLM access.

Agents never talk to a vendor SDK directly; they call
provider.run_task(task_name, payload) and get back a plain dict, which they
validate with Pydantic. Two implementations exist:

- AnthropicProvider: renders the payload into a prompt and calls the API.
- MockProvider: computes a deterministic result from the payload itself,
  grounded in the actual filing text — so the entire pipeline, the tests, and
  the evaluation run with no API key and produce reproducible results.

Task names are constants so a typo fails loudly.
"""

from typing import Protocol

TASK_EXTRACT = "extract_evidence"
TASK_VERIFY = "verify_claim"
TASK_BRIEF = "write_brief"


class LLMError(Exception):
    """The provider could not produce a usable structured response."""


class LLMProvider(Protocol):
    name: str

    def run_task(self, task_name: str, payload: dict) -> dict:
        """Execute one agent task and return its JSON result as a dict."""
        ...


def get_provider() -> "LLMProvider":
    from app.config import get_settings

    settings = get_settings()
    if settings.llm_provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicProvider

        return AnthropicProvider()
    from app.llm.mock_provider import MockProvider

    return MockProvider()
