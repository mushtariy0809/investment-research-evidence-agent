"""Shared test setup.

Key decisions:
- LLM_PROVIDER is forced to "mock" and DATABASE_URL to a per-session temp file
  BEFORE the app is imported, because engine/settings are created at import.
- Unit/API tests never touch the network: a FakeSecClient serves a small
  synthetic filing (clearly labeled as a test fixture, not real SEC data).
"""

import os
import tempfile
from datetime import date
from pathlib import Path

import pytest

_TMP_DIR = tempfile.mkdtemp(prefix="irea-tests-")
os.environ["DATABASE_URL"] = f"sqlite:///{_TMP_DIR}/test.db"
os.environ["LLM_PROVIDER"] = "mock"
os.environ["ANTHROPIC_API_KEY"] = ""

from app.db import database  # noqa: E402
from app.db.database import Base  # noqa: E402
from app.services.sec_client import CompanyMatch, FilingRef  # noqa: E402

FIXTURE_HTML = (Path(__file__).parent / "fixture_filing.html").read_text()

FIXTURE_COMPANY = CompanyMatch(cik="0000012345", ticker="EXCO", name="ExampleCo Inc.")
FIXTURE_FILING = FilingRef(
    accession_number="0000012345-24-000001",
    form_type="10-K",
    filing_date=date(2024, 2, 15),
    period_of_report=date(2023, 12, 31),
    primary_doc="exco-10k.htm",
    primary_doc_url="https://www.sec.gov/Archives/edgar/data/12345/000001234524000001/exco-10k.htm",
)


class FakeSecClient:
    """Stands in for SecClient — no network, deterministic content."""

    def __init__(self, html: str = FIXTURE_HTML):
        self.html = html
        self.fetch_count = 0

    def search_companies(self, query: str, limit: int = 10):
        q = query.strip().upper()
        matches = [FIXTURE_COMPANY]
        return [m for m in matches if q in m.ticker or q in m.name.upper()]

    def list_filings(self, cik: str, forms=None, limit: int = 20):
        return [FIXTURE_FILING] if cik == FIXTURE_COMPANY.cik else []

    def fetch_document(self, url: str) -> str:
        self.fetch_count += 1
        return self.html


@pytest.fixture(autouse=True)
def clean_db():
    """Fresh schema for every test — no cross-test state."""
    Base.metadata.drop_all(bind=database.engine)
    Base.metadata.create_all(bind=database.engine)
    yield


@pytest.fixture
def db():
    session = database.SessionLocal()
    yield session
    session.close()


@pytest.fixture
def fake_sec():
    return FakeSecClient()


@pytest.fixture
def client(fake_sec, monkeypatch):
    """API test client with the fake SEC backend injected."""
    from fastapi.testclient import TestClient

    from app.api import deps
    from app.main import app

    monkeypatch.setattr(deps, "get_sec_client", lambda: fake_sec)
    deps.reset_singletons()
    with TestClient(app) as test_client:
        yield test_client
    deps.reset_singletons()
