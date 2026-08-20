from pathlib import Path

from app.services.filing_parser import html_to_text, split_sections

FIXTURE_HTML = (Path(__file__).parent / "fixture_filing.html").read_text()


def test_html_to_text_strips_tags_and_scripts():
    text = html_to_text(FIXTURE_HTML)
    assert "<p>" not in text
    assert "scripts must be stripped" not in text
    assert "ExampleCo Inc. designs and sells" in text


def test_html_to_text_decodes_entities():
    text = html_to_text(FIXTURE_HTML)
    assert "Company’s data analytics platform" in text  # &#8217; decoded


def test_split_sections_finds_items_and_drops_toc():
    text = html_to_text(FIXTURE_HTML)
    sections = split_sections(text, "10-K")
    keys = {s.item_key for s in sections}
    assert keys == {"1", "1A", "7"}
    # TOC produced short duplicate "Item 1" entries; the real (long) one wins.
    item1 = next(s for s in sections if s.item_key == "1")
    assert "two reportable segments" in item1.text


def test_split_sections_names_known_items():
    sections = split_sections(html_to_text(FIXTURE_HTML), "10-K")
    names = {s.item_key: s.name for s in sections}
    assert names["1A"] == "Item 1A. Risk Factors"


def test_split_sections_falls_back_to_chunks_when_no_items():
    text = "word " * 10_000  # no Item headings at all
    sections = split_sections(text, "10-K")
    assert len(sections) >= 2
    assert all(s.item_key.startswith("FULL-") for s in sections)
    assert "".join(s.text for s in sections) == text


def test_split_sections_10q_tracks_parts():
    text = (
        "PART I\n"
        "Item 1. Financial Statements\n" + ("balance sheet data. " * 40) +
        "\nPART II\n"
        "Item 1A. Risk Factors\n" + ("updated risk disclosure. " * 40)
    )
    sections = split_sections(text, "10-Q")
    keys = {s.item_key for s in sections}
    assert "I-1" in keys and "II-1A" in keys
