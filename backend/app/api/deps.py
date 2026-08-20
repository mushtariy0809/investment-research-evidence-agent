"""Shared singletons for the API layer.

Lazy, module-level singletons keep construction in one place and let tests
swap implementations by resetting them.
"""

from app.agents.orchestrator import Orchestrator
from app.agents.retrieval import FilingRetrievalAgent
from app.llm.base import get_provider
from app.services.sec_client import get_sec_client

_orchestrator: Orchestrator | None = None
_retrieval: FilingRetrievalAgent | None = None


def get_orchestrator() -> Orchestrator:
    global _orchestrator
    if _orchestrator is None:
        _orchestrator = Orchestrator(get_provider(), get_sec_client())
    return _orchestrator


def get_retrieval_agent() -> FilingRetrievalAgent:
    global _retrieval
    if _retrieval is None:
        _retrieval = FilingRetrievalAgent(get_sec_client())
    return _retrieval


def reset_singletons() -> None:
    """Used by tests to re-create agents after swapping providers/clients."""
    global _orchestrator, _retrieval
    _orchestrator = None
    _retrieval = None
