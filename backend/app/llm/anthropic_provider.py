"""Real LLM provider backed by the Anthropic API.

The API key comes only from configuration (ANTHROPIC_API_KEY env var) — it is
never hard-coded. Responses must be strict JSON; we retry once with an explicit
correction message before failing, and the failure is a typed LLMError that the
orchestrator records instead of crashing the request silently.
"""

import json

import anthropic

from app.config import get_settings
from app.llm import prompts
from app.llm.base import TASK_BRIEF, TASK_EXTRACT, TASK_VERIFY, LLMError
from app.logging_config import get_logger

logger = get_logger(__name__)

_PROMPT_BUILDERS = {
    TASK_EXTRACT: prompts.build_extract_prompt,
    TASK_VERIFY: prompts.build_verify_prompt,
    TASK_BRIEF: prompts.build_brief_prompt,
}


def _parse_json_object(text: str) -> dict:
    """Parse a JSON object, tolerating accidental markdown fences."""
    cleaned = text.strip()
    if cleaned.startswith("```"):
        cleaned = cleaned.strip("`")
        if cleaned.startswith("json"):
            cleaned = cleaned[4:]
    start, end = cleaned.find("{"), cleaned.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("no JSON object in response")
    result = json.loads(cleaned[start:end + 1])
    if not isinstance(result, dict):
        raise ValueError("response is not a JSON object")
    return result


class AnthropicProvider:
    name = "anthropic"

    def __init__(self) -> None:
        settings = get_settings()
        if not settings.anthropic_api_key:
            raise LLMError(
                "LLM_PROVIDER=anthropic but ANTHROPIC_API_KEY is not set. "
                "Set the key in .env or use LLM_PROVIDER=mock."
            )
        self._client = anthropic.Anthropic(api_key=settings.anthropic_api_key)
        self._model = settings.anthropic_model

    def run_task(self, task_name: str, payload: dict) -> dict:
        builder = _PROMPT_BUILDERS.get(task_name)
        if builder is None:
            raise LLMError(f"Unknown LLM task: {task_name}")
        system, user = builder(payload)

        messages = [{"role": "user", "content": user}]
        last_error: Exception | None = None
        for attempt in range(2):
            try:
                response = self._client.messages.create(
                    model=self._model,
                    max_tokens=3000,
                    system=system,
                    messages=messages,
                )
                text = "".join(
                    block.text for block in response.content if block.type == "text"
                )
                return _parse_json_object(text)
            except anthropic.APIError as exc:
                raise LLMError(f"Anthropic API error: {exc}") from exc
            except (ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning(
                    "LLM returned invalid JSON, retrying",
                    extra={"extra_fields": {"task": task_name, "attempt": attempt}},
                )
                messages = messages + [
                    {"role": "assistant", "content": text},
                    {"role": "user",
                     "content": "That was not valid JSON. Respond with only the JSON object."},
                ]
        raise LLMError(f"LLM did not return valid JSON for {task_name}: {last_error}")
