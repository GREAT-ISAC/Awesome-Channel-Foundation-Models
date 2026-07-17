"""Deterministic tests for the structured Awesome CFM catalog."""

from __future__ import annotations

import importlib.util
import re
import unittest
import urllib.error
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

    def test_v1_inventory_baseline_can_grow_without_test_edits(self):
        by_kind = {
            kind: [record for record in self.records if record["kind"] == kind]
            for kind in ("paper", "dataset", "model", "benchmark", "simulation-tool")
        }
        self.assertGreaterEqual(len(by_kind["paper"]), 48)
        for kind in ("dataset", "model", "benchmark", "simulation-tool"):
            self.assertTrue(by_kind[kind], f"The {kind} catalog must not be empty")

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

    def test_paper_page_has_one_hierarchical_entry_per_paper(self):
        papers = [record for record in self.records if record["kind"] == "paper"]
        rendered = catalog.render_papers(papers, self.records)
        for paper in papers:
            with self.subTest(paper=paper["id"]):
                self.assertEqual(rendered.count(f'<a id="{paper["id"]}"></a>'), 1)
        for heading in (
            "## Surveys & Perspectives",
            "## Backbones & Architectures",
            "## Pretraining Methods",
            "### Masked/Reconstruction Learning",
            "### Autoregressive/Generative Modeling",
            "### Contrastive/Alignment Learning",
            "### Predictive Latent Learning",
            "### Supervised/Multitask Pretraining",
            "### Hybrid Objectives",
            "## Adaptation & Transfer",
            "## Inference & Deployment",
        ):
            self.assertIn(heading, rendered)

    def test_survey_descriptions_are_preserved_without_profile_labels(self):
        by_id = {record["id"]: record for record in self.records}
        expected_summary = (
            "This paper introduces the concept of channel foundation models (CFMs) "
            "for the first time, providing a comprehensive survey on motivations, "
            "methodologies, and future opportunities."
        )
        expected_abstract = (
            "The integration of Artificial Intelligence (AI) and communication has "
            "emerged as a key target and hallmarks for sixth-generation wireless "
            "communication systems. Based on the discussion of the understanding of "
            "Native AI and the summary of the evolution of AI research paradigms in "
            "wireless communications, this paper points out that traditional "
            "task-specific AI models have various limitations, making them hardly "
            "serve as an important component of future 6G Native AI. Accordingly, we "
            "propose Channel Foundation Models (CFMs) and systematically introduce "
            "their pretraining methods, as well as their potential adaptation to "
            "various channel-related tasks. As an exploration and sharing on issues "
            "such as \"what is Native AI\" and \"what kind of AI capabilities future "
            "6G systems need\", we argue that 6G Native AI must possess strong task "
            "adaptability and scenario generalization ability, and CFMs are expected "
            "to become one of the technical options for future 6G Native AI."
        )
        expected_abstract_zh = (
            "人工智能（Artificial intelligence, AI）与通信的深度结合已成为6G的关键目标和标志之一。"
            "内生智能（Native AI）被认为是6G重要特征。本文在给出对内生智能理解探讨的基础上总结"
            "无线AI研究范式演进，指出基于监督学习的传统AI模型存在诸多局限，使其很难作为未来6G"
            "内生智能的重要组成部分。基于此，我们提出了信道基础模型（Channel Foundation Models, "
            "CFMs）并系统地介绍了其预训练方法，以及对各类信道相关任务的可能适配。作为对“什么是"
            "内生智能，什么样的AI能力是未来6G系统需要的”等问题的探讨和分享，我们认为6G内生智能"
            "需要具备强大任务适应性和场景泛化能力，CFMs有可能成为未来6G内生智能的技术选项之一。"
        )
        expected_note = (
            "This invited position paper on CFM and 6G Native AI will be published by "
            "ZTE Communications soon (in Chinese). An early access version can be found "
            "in [CNKI](https://link.cnki.net/urlid/34.1228.TN.20260225.0923.002)."
        )

        towards = by_id["towards-cfm"]
        native_ai = by_id["6g-native-ai-cfm"]
        self.assertEqual(towards["summary"], expected_summary)
        self.assertEqual(native_ai["abstract"], expected_abstract)
        self.assertEqual(native_ai["abstract_zh"], expected_abstract_zh)
        self.assertEqual(native_ai["note"], expected_note)
        for paper in (towards, native_ai):
            entry = catalog.render_paper_entry(paper, by_id)
            self.assertNotIn("**Modalities:**", entry)
            self.assertNotIn("**Tasks:**", entry)
        self.assertIn(f"**Summary:** {expected_summary}", catalog.render_paper_entry(towards, by_id))
        native_entry = catalog.render_paper_entry(native_ai, by_id)
        self.assertIn(f"**Abstract:** {expected_abstract}", native_entry)
        self.assertIn(f"**摘要:** {expected_abstract_zh}", native_entry)
        self.assertIn(f"**Note:** {expected_note}", native_entry)

    def test_paper_profiles_and_artifacts_are_compact(self):
        by_id = {record["id"]: record for record in self.records}
        temporal_entry = catalog.render_paper_entry(by_id["lwm-temporal"], by_id)
        self.assertIn(
            "  - **Modalities:** CSI\n  - **Tasks:** Time Channel Extrapolation",
            temporal_entry,
        )
        self.assertNotIn(" · **Tasks:**", temporal_entry)

        coupler_entry = catalog.render_paper_entry(by_id["full-domain-coupler"], by_id)
        self.assertIn("**Code:** [Official implementation]", coupler_entry)
        self.assertNotIn("Code / Weights / Benchmark", coupler_entry)
        rendered = catalog.render_papers(
            [record for record in self.records if record["kind"] == "paper"],
            self.records,
        )
        self.assertNotIn("**Data:**", rendered)

    def test_deepmimo_is_cataloged_as_dataset_and_simulation_tool(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertEqual(by_id["deepmimo"]["kind"], "dataset")
        self.assertEqual(by_id["deepmimo-toolchain"]["kind"], "simulation-tool")
        self.assertNotIn("ns-3", by_id)
        tool_page = catalog.render_outputs(self.records)[catalog.OUTPUTS["simulation-tool"]]
        self.assertIn('<a id="deepmimo-toolchain"></a>', tool_page)
        self.assertNotIn('<a id="ns-3"></a>', tool_page)

    def test_featured_cfm_bench_is_first_dataset(self):
        outputs = catalog.render_outputs(self.records)
        dataset_page = outputs[catalog.OUTPUTS["dataset"]]
        first_entry = dataset_page.index('<a id="cfm-bench"></a>')
        other_entries = [
            dataset_page.index(f'<a id="{record["id"]}"></a>')
            for record in self.records
            if record["kind"] == "dataset" and record["id"] != "cfm-bench"
        ]
        self.assertTrue(all(first_entry < position for position in other_entries))
        self.assertIn("https://www.chaspark.com/#/s/CFM-Bench", dataset_page)

    def test_great_x_is_cataloged_from_official_sources(self):
        by_id = {record["id"]: record for record in self.records}
        great_x = by_id["great-x"]
        self.assertEqual(great_x["kind"], "simulation-tool")
        self.assertEqual(great_x["license"], "Apache-2.0")
        urls = {link["url"] for link in great_x["links"]}
        self.assertIn("https://github.com/hkw-xg/Great-MCD", urls)
        self.assertIn("https://arxiv.org/abs/2507.08716", urls)

    def test_models_and_benchmarks_are_embedded_without_public_sections(self):
        outputs = catalog.render_outputs(self.records)
        paper_page = outputs[catalog.OUTPUTS["paper"]]
        dataset_page = outputs[catalog.OUTPUTS["dataset"]]
        by_id = {record["id"]: record for record in self.records}
        for paper in (record for record in self.records if record["kind"] == "paper"):
            for slot_name in ("models", "benchmarks"):
                for item in paper["artifacts"][slot_name]["items"]:
                    if "ref" in item:
                        self.assertIn(catalog.primary_resource_url(by_id[item["ref"]]), paper_page)
        for benchmark in (record for record in self.records if record["kind"] == "benchmark"):
            if benchmark["datasets"]:
                self.assertIn(catalog.primary_resource_url(benchmark), dataset_page)
            self.assertNotIn(f'<a id="{benchmark["id"]}"></a>', dataset_page)
        for model in (record for record in self.records if record["kind"] == "model"):
            self.assertNotIn(f'<a id="{model["id"]}"></a>', paper_page)
        self.assertNotIn("## Pretrained Models", paper_page)
        self.assertNotIn("## Benchmark Projects", dataset_page)
        homepage = outputs[catalog.OUTPUTS["readme"]]
        self.assertNotIn("Pretrained Models", homepage)
        self.assertNotIn("Benchmark Projects", homepage)
        self.assertNotIn("models/README.md", homepage)
        self.assertNotIn("benchmarks/README.md", homepage)
        self.assertFalse((ROOT / "models" / "README.md").exists())
        self.assertFalse((ROOT / "benchmarks" / "README.md").exists())

    def test_public_pages_omit_maintenance_clutter(self):
        outputs = catalog.render_outputs(self.records)
        homepage = outputs[catalog.OUTPUTS["readme"]]
        papers = outputs[catalog.OUTPUTS["paper"]]
        for phrase in (
            "Catalog at a glance",
            "Latest cataloged papers",
            "Reproducibility snapshot",
            "Last catalog verification",
            "## Scope",
            "## Organization",
        ):
            self.assertNotIn(phrase, homepage)
        for phrase in ("Not found", "Not released", "**Scope:**", "Last verified", "Browse by"):
            self.assertNotIn(phrase, papers)
        for kind in ("dataset", "simulation-tool"):
            resource_page = outputs[catalog.OUTPUTS[kind]]
            self.assertNotIn("**License:**", resource_page)
            self.assertNotIn("Verified", resource_page)

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
                    destination.exists(),
                    f"{source.relative_to(ROOT)} has a missing relative link: {target}",
                )
                if separator and fragment and destination.is_file() and destination.suffix.lower() == ".md":
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
