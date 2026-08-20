"""Client for official SEC EDGAR data.

Endpoints used (all official, no scraping of search pages):
- https://www.sec.gov/files/company_tickers.json      ticker -> CIK mapping
- https://data.sec.gov/submissions/CIK{cik}.json      filing history per company
- https://www.sec.gov/Archives/edgar/data/...         the filing documents

Fair-access compliance (https://www.sec.gov/os/accessing-edgar-data):
- Declared User-Agent with app name and contact email (from settings).
- Client-side throttle far below the 10 requests/second limit.
- Filings are cached in the database so each document is fetched once.
"""

import threading
import time
from dataclasses import dataclass
from datetime import date

import httpx

from app.config import get_settings
from app.logging_config import get_logger

logger = get_logger(__name__)

TICKER_MAP_URL = "https://www.sec.gov/files/company_tickers.json"
SUBMISSIONS_URL = "https://data.sec.gov/submissions/CIK{cik}.json"
ARCHIVES_URL = "https://www.sec.gov/Archives/edgar/data/{cik_int}/{accession_nodash}/{doc}"

SUPPORTED_FORMS = {"10-K", "10-Q"}


class SecError(Exception):
    """Raised for SEC network/availability problems (mapped to HTTP 502)."""


@dataclass(frozen=True)
class CompanyMatch:
    cik: str  # zero-padded to 10 digits
    ticker: str
    name: str


@dataclass(frozen=True)
class FilingRef:
    accession_number: str
    form_type: str
    filing_date: date
    period_of_report: date | None
    primary_doc: str
    primary_doc_url: str


class SecClient:
    def __init__(self, timeout: float = 30.0, min_interval: float = 0.15):
        settings = get_settings()
        self._client = httpx.Client(
            timeout=timeout,
            headers={
                "User-Agent": settings.sec_user_agent,
                "Accept-Encoding": "gzip, deflate",
            },
            follow_redirects=True,
        )
        self._min_interval = min_interval
        self._last_request = 0.0
        self._lock = threading.Lock()
        self._ticker_map: dict[str, CompanyMatch] | None = None
        self._ticker_map_fetched = 0.0

    def _get(self, url: str) -> httpx.Response:
        """GET with throttling and clear error translation."""
        with self._lock:
            wait = self._min_interval - (time.monotonic() - self._last_request)
            if wait > 0:
                time.sleep(wait)
            self._last_request = time.monotonic()
        try:
            resp = self._client.get(url)
        except httpx.HTTPError as exc:
            raise SecError(f"Network error reaching SEC: {exc}") from exc
        if resp.status_code == 429 or resp.status_code == 403:
            raise SecError("SEC rate limit reached; wait a moment and retry.")
        if resp.status_code == 404:
            raise SecError(f"SEC resource not found: {url}")
        if resp.status_code != 200:
            raise SecError(f"SEC returned HTTP {resp.status_code} for {url}")
        return resp

    def _load_ticker_map(self) -> dict[str, CompanyMatch]:
        # Cache in memory for an hour; the file only changes daily.
        if self._ticker_map is not None and time.monotonic() - self._ticker_map_fetched < 3600:
            return self._ticker_map
        logger.info("Fetching SEC ticker map")
        data = self._get(TICKER_MAP_URL).json()
        mapping: dict[str, CompanyMatch] = {}
        for entry in data.values():
            ticker = str(entry["ticker"]).upper()
            mapping[ticker] = CompanyMatch(
                cik=str(entry["cik_str"]).zfill(10),
                ticker=ticker,
                name=str(entry["title"]),
            )
        self._ticker_map = mapping
        self._ticker_map_fetched = time.monotonic()
        return mapping

    def search_companies(self, query: str, limit: int = 10) -> list[CompanyMatch]:
        """Match by exact ticker first, then ticker prefix, then name substring."""
        q = query.strip().upper()
        if not q:
            return []
        mapping = self._load_ticker_map()
        results: list[CompanyMatch] = []
        if q in mapping:
            results.append(mapping[q])
        for match in mapping.values():
            if len(results) >= limit:
                break
            if match in results:
                continue
            if match.ticker.startswith(q) or q in match.name.upper():
                results.append(match)
        return results[:limit]

    def list_filings(self, cik: str, forms: set[str] | None = None,
                     limit: int = 20) -> list[FilingRef]:
        forms = forms or SUPPORTED_FORMS
        data = self._get(SUBMISSIONS_URL.format(cik=cik.zfill(10))).json()
        recent = data.get("filings", {}).get("recent", {})
        refs: list[FilingRef] = []
        # The submissions API returns parallel arrays (column-oriented).
        for i in range(len(recent.get("accessionNumber", []))):
            form = recent["form"][i]
            if form not in forms:
                continue
            accession = recent["accessionNumber"][i]
            primary_doc = recent["primaryDocument"][i]
            period = recent.get("reportDate", [None] * (i + 1))[i] or None
            refs.append(
                FilingRef(
                    accession_number=accession,
                    form_type=form,
                    filing_date=date.fromisoformat(recent["filingDate"][i]),
                    period_of_report=date.fromisoformat(period) if period else None,
                    primary_doc=primary_doc,
                    primary_doc_url=ARCHIVES_URL.format(
                        cik_int=int(cik),
                        accession_nodash=accession.replace("-", ""),
                        doc=primary_doc,
                    ),
                )
            )
            if len(refs) >= limit:
                break
        return refs

    def fetch_document(self, url: str) -> str:
        """Download a filing document (HTML) and return its raw text."""
        logger.info("Fetching filing document", extra={"extra_fields": {"url": url}})
        return self._get(url).text


# Module-level singleton so the in-memory ticker cache is shared across requests.
_client: SecClient | None = None


def get_sec_client() -> SecClient:
    global _client
    if _client is None:
        _client = SecClient()
    return _client
