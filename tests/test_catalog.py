"""Deterministic tests for the structured Awesome CFM catalog."""

from __future__ import annotations

import importlib.util
import re
import unittest
import urllib.error
from collections import Counter
from pathlib import Path
from typing import Iterable, Set
from unittest import mock
from urllib.parse import unquote

import yaml
from jsonschema import Draft202012Validator


ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("catalog_cli", ROOT / "scripts" / "catalog.py")
assert SPEC and SPEC.loader
catalog = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(catalog)


def github_heading_ids(markdown: str) -> Set[str]:
    """Return the GitHub-style anchors needed by this repository's headings."""
    anchors = set(re.findall(r'<a\s+id="([^"]+)"', markdown))
    for heading in re.findall(r"^#{1,6}\s+(.+?)\s*$", markdown, flags=re.MULTILINE):
        heading = re.sub(r"<[^>]+>", "", heading).strip().lower()
        heading = re.sub(r"[^\w\- ]", "", heading, flags=re.UNICODE)
        anchors.add(heading.replace(" ", "-"))
    return anchors


def markdown_files() -> Iterable[Path]:
    yield ROOT / "README.md"
    yield ROOT / "CONTRIBUTING.md"
    yield from sorted((ROOT / "docs").glob("*.md"))
    yield from sorted(path for path in catalog.OUTPUTS.values() if path.suffix == ".md")


class FakeResponse:
    def __init__(self, status: int):
        self.status = status

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def getcode(self) -> int:
        return self.status


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = catalog.load_records()
        catalog.validate_records(cls.records)

    def test_schema_is_valid_draft_2020_12(self):
        import json

        schema = json.loads(catalog.SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

    def test_v1_inventory_counts(self):
        counts = Counter(record["kind"] for record in self.records)
        self.assertEqual(
            counts,
            {
                "paper": 48,
                "dataset": 5,
                "model": 6,
                "benchmark": 4,
                "simulation-tool": 8,
            },
        )

    def test_all_papers_have_complete_taxonomy_and_audit_state(self):
        papers = [record for record in self.records if record["kind"] == "paper"]
        for paper in papers:
            with self.subTest(paper=paper["id"]):
                self.assertTrue(paper["title"])
                self.assertTrue(paper["authors"])
                self.assertTrue(paper["paper_url"])
                self.assertTrue(paper["scope"])
                self.assertTrue(paper["stages"])
                self.assertIn("objectives", paper)
                self.assertIn("modalities", paper)
                self.assertIn("tasks", paper)
                self.assertEqual(
                    set(paper["artifacts"]),
                    {"code", "datasets", "models", "benchmarks", "simulation_tools"},
                )
                self.assertRegex(paper["last_verified"], r"^\d{4}-\d{2}-\d{2}$")

    def test_paper_resource_references_are_bidirectionally_declared(self):
        by_id = {record["id"]: record for record in self.records}
        for paper in (record for record in self.records if record["kind"] == "paper"):
            for slot in paper["artifacts"].values():
                for item in slot["items"]:
                    if "ref" not in item:
                        continue
                    with self.subTest(paper=paper["id"], resource=item["ref"]):
                        self.assertIn(paper["id"], by_id[item["ref"]]["related_papers"])

    def test_generated_pages_are_current(self):
        catalog.generate(self.records, check=True)

    def test_internal_markdown_links_and_anchors_resolve(self):
        seen = set()
        for source in markdown_files():
            if source in seen:
                continue
            seen.add(source)
            text = source.read_text(encoding="utf-8")
            for raw_target in re.findall(r"(?<!!)\[[^]]*\]\(([^)]+)\)", text):
                target = raw_target.strip().strip("<>")
                if target.startswith(("http://", "https://", "mailto:")):
                    continue
                path_text, separator, fragment = target.partition("#")
                if not path_text:
                    destination = source
                else:
                    destination = (source.parent / unquote(path_text)).resolve()
                    try:
                        destination.relative_to(ROOT)
                    except ValueError:
                        self.fail(f"{source.relative_to(ROOT)} links outside the repository: {target}")
                self.assertTrue(
                    destination.is_file(),
                    f"{source.relative_to(ROOT)} has a missing relative link: {target}",
                )
                if separator and fragment and destination.suffix.lower() == ".md":
                    anchors = github_heading_ids(destination.read_text(encoding="utf-8"))
                    self.assertIn(
                        unquote(fragment),
                        anchors,
                        f"{source.relative_to(ROOT)} has a missing anchor: {target}",
                    )

    def test_local_maintainer_pdf_remains_available(self):
        self.assertTrue((ROOT / "docs" / "6G Native AI and Channel Foundation Models.pdf").is_file())

    def test_citation_and_license_boundaries(self):
        citation = yaml.safe_load((ROOT / "CITATION.cff").read_text(encoding="utf-8"))
        self.assertEqual(citation["cff-version"], "1.2.0")
        self.assertEqual(citation["license"], "CC-BY-4.0")
        self.assertIn("CC-BY-4.0", (ROOT / "LICENSE-CONTENT").read_text(encoding="utf-8"))
        self.assertIn("MIT License", (ROOT / "LICENSE-CODE").read_text(encoding="utf-8"))

    @mock.patch.object(catalog.urllib.request, "urlopen", return_value=FakeResponse(200))
    def test_link_checker_accepts_success(self, _urlopen):
        self.assertEqual(catalog.check_url("https://example.test", 1)[1], "ok")

    def test_link_checker_treats_403_and_429_as_indeterminate(self):
        for status in (403, 429):
            error = urllib.error.HTTPError("https://example.test", status, "blocked", {}, None)
            with self.subTest(status=status), mock.patch.object(
                catalog.urllib.request, "urlopen", side_effect=[error, error]
            ):
                self.assertEqual(catalog.check_url("https://example.test", 1)[1], "indeterminate")

    @mock.patch.object(
        catalog.urllib.request,
        "urlopen",
        side_effect=urllib.error.HTTPError("https://example.test", 404, "missing", {}, None),
    )
    def test_link_checker_reports_confirmed_http_failure(self, _urlopen):
        self.assertEqual(catalog.check_url("https://example.test", 1)[1], "broken")

    def test_link_checker_retries_head_with_get(self):
        head_error = urllib.error.HTTPError("https://example.test", 405, "method", {}, None)
        with mock.patch.object(
            catalog.urllib.request, "urlopen", side_effect=[head_error, FakeResponse(200)]
        ) as urlopen:
            self.assertEqual(catalog.check_url("https://example.test", 1)[1], "ok")
            self.assertEqual(urlopen.call_count, 2)


if __name__ == "__main__":
    unittest.main()
