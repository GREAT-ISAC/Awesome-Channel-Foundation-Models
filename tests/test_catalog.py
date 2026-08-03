"""Deterministic tests for the structured Awesome CFM catalog."""

from __future__ import annotations

import copy
import importlib.util
import json
import re
import socket
import tempfile
import time
import unittest
import http.client
import urllib.error
from datetime import date, timedelta
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


def public_resolver(_hostname, port, **_kwargs):
    """Return a stable public address without using DNS in unit tests."""

    return [
        (
            socket.AF_INET,
            socket.SOCK_STREAM,
            socket.IPPROTO_TCP,
            "",
            ("93.184.216.34", port),
        )
    ]


class CatalogTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.records = catalog.load_records()
        catalog.validate_records(cls.records)

    def test_schema_is_valid_draft_2020_12(self):
        import json

        schema = json.loads(catalog.SCHEMA_PATH.read_text(encoding="utf-8"))
        Draft202012Validator.check_schema(schema)

    def test_resource_schemas_reject_unknown_fields(self):
        for kind in ("dataset", "model", "simulation-tool"):
            records = copy.deepcopy(self.records)
            record = next(item for item in records if item["kind"] == kind)
            record["typo_field"] = "must not be silently accepted"
            with self.subTest(kind=kind), self.assertRaises(catalog.CatalogError):
                catalog.validate_records(records)

    def test_malformed_records_report_catalog_errors_instead_of_crashing(self):
        malformed = []

        records = copy.deepcopy(self.records)
        next(item for item in records if item["kind"] == "paper").pop("id")
        malformed.append(("missing id", records))

        records = copy.deepcopy(self.records)
        next(item for item in records if item["kind"] == "paper")["artifacts"] = "invalid"
        malformed.append(("artifacts shape", records))

        records = copy.deepcopy(self.records)
        next(item for item in records if item["kind"] == "paper")["stages"] = None
        malformed.append(("stages shape", records))

        records = copy.deepcopy(self.records)
        next(item for item in records if item["kind"] == "dataset")["links"][0].pop("url")
        malformed.append(("missing link URL", records))

        for label, records in malformed:
            with self.subTest(case=label), self.assertRaises(catalog.CatalogError):
                catalog.validate_records(records)

    def test_v1_inventory_baseline_can_grow_without_test_edits(self):
        by_kind = {
            kind: [record for record in self.records if record["kind"] == kind]
            for kind in ("paper", "dataset", "model", "simulation-tool")
        }
        self.assertGreaterEqual(len(by_kind["paper"]), 48)
        for kind in ("dataset", "model", "simulation-tool"):
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
                self.assertIn("primary_objective", paper)
                self.assertIn("training_signals", paper)
                self.assertIn("task_regime", paper)
                self.assertIn("modalities", paper)
                self.assertIn("tasks", paper)
                self.assertEqual(
                    set(paper["artifacts"]),
                    {"code", "datasets", "models", "simulation_tools"},
                )
                self.assertRegex(paper["last_verified"], r"^\d{4}-\d{2}-\d{2}$")

    def test_scope_does_not_split_core_and_broader_foundation_models(self):
        scopes = {record["scope"] for record in self.records}
        self.assertEqual(scopes, {"cfm-ecosystem", "related-method"})
        self.assertNotIn("core-cfm", scopes)
        self.assertNotIn("broader-wireless-radio-fm", scopes)

    def test_loader_rejects_duplicate_yaml_keys(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            papers = root / "catalog" / "papers"
            papers.mkdir(parents=True)
            (papers / "duplicate.yaml").write_text(
                "kind: paper\nid: duplicate\nid: duplicate\n", encoding="utf-8"
            )
            with mock.patch.multiple(
                catalog, ROOT=root, CATALOG_DIR=root / "catalog"
            ), self.assertRaisesRegex(catalog.CatalogError, "duplicate key 'id'"):
                catalog.load_records()

    def test_loader_supports_yml_and_requires_filename_to_match_id(self):
        source = catalog.public_record(
            next(record for record in self.records if record["kind"] == "paper")
        )
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            papers = root / "catalog" / "papers"
            papers.mkdir(parents=True)
            yml_path = papers / f"{source['id']}.yml"
            yml_path.write_text(yaml.safe_dump(source, sort_keys=False), encoding="utf-8")
            with mock.patch.multiple(catalog, ROOT=root, CATALOG_DIR=root / "catalog"):
                self.assertEqual(catalog.load_records()[0]["id"], source["id"])
            yml_path.rename(papers / "wrong-name.yml")
            with mock.patch.multiple(
                catalog, ROOT=root, CATALOG_DIR=root / "catalog"
            ), self.assertRaisesRegex(catalog.CatalogError, "filename stem must match"):
                catalog.load_records()

    def test_loader_rejects_nested_catalog_records(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            nested = root / "catalog" / "papers" / "nested"
            nested.mkdir(parents=True)
            (nested / "paper.yaml").write_text(
                "kind: paper\nid: paper\n", encoding="utf-8"
            )
            with mock.patch.multiple(
                catalog, ROOT=root, CATALOG_DIR=root / "catalog"
            ), self.assertRaisesRegex(catalog.CatalogError, "nested catalog records"):
                catalog.load_records()

    def test_loader_rejects_removed_or_unknown_catalog_kinds(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            legacy = root / "catalog" / "benchmarks"
            legacy.mkdir(parents=True)
            (legacy / "legacy.yaml").write_text(
                "kind: benchmark\nid: legacy\n", encoding="utf-8"
            )
            with mock.patch.multiple(
                catalog, ROOT=root, CATALOG_DIR=root / "catalog"
            ), self.assertRaisesRegex(catalog.CatalogError, "unsupported catalog kind"):
                catalog.load_records()

    def test_validator_rejects_duplicate_paper_urls(self):
        records = copy.deepcopy(self.records)
        papers = [
            record
            for record in records
            if record["kind"] == "paper"
            and record["paper_url"].startswith(("http://", "https://"))
        ]
        papers[1]["paper_url"] = papers[0]["paper_url"]
        with self.assertRaisesRegex(catalog.CatalogError, "already maintained"):
            catalog.validate_records(records)

    def test_validator_rejects_non_http_artifact_urls(self):
        records = copy.deepcopy(self.records)
        paper = next(record for record in records if record["id"] == "early-exit")
        paper["artifacts"]["code"] = {
            "status": "available",
            "items": [
                {
                    "label": "Local file",
                    "url": "file:///etc/passwd",
                    "provenance": "official",
                    "availability": "available",
                }
            ],
        }
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_records(records)

    def test_validator_rejects_missing_or_escaping_local_paths(self):
        records = copy.deepcopy(self.records)
        local_paper = next(record for record in records if record["id"] == "6g-native-ai-cfm")
        local_paper["paper_url"] = "docs/does-not-exist.pdf"
        local_paper.pop("local_url", None)
        with self.assertRaisesRegex(catalog.CatalogError, "paper_url.*does not exist"):
            catalog.validate_records(records)

        records = copy.deepcopy(self.records)
        local_paper = next(record for record in records if record["id"] == "6g-native-ai-cfm")
        local_paper["paper_url"] = "docs/../README.md"
        local_paper.pop("local_url", None)
        with self.assertRaisesRegex(catalog.CatalogError, "paper_url.*inside docs"):
            catalog.validate_records(records)

        records = copy.deepcopy(self.records)
        local_paper = next(record for record in records if record["id"] == "6g-native-ai-cfm")
        local_paper["local_url"] = "/etc/hosts"
        with self.assertRaisesRegex(catalog.CatalogError, "local_url.*repository-relative"):
            catalog.validate_records(records)

        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            root = base / "repository"
            docs = root / "docs"
            docs.mkdir(parents=True)
            outside = base / "outside.pdf"
            outside.write_text("outside", encoding="utf-8")
            (docs / "escape.pdf").symlink_to(outside)
            self.assertIn(
                "outside the repository",
                catalog.repository_file_reason(
                    "docs/escape.pdf", root=root, required_subdir="docs"
                ),
            )

    def test_url_safety_rejects_userinfo_and_non_public_addresses(self):
        for url in (
            "https://user@example.com/path",
            "https://user:password@example.com/path",
            "https://@example.com/path",
            "http://127.0.0.1/path",
            "http://224.0.0.1/path",
            "http://[::1]/path",
            "http://[ff02::1]/path",
            "https://example.com:99999/path",
            "https://example.com:0/path",
            "https://exa mple.com/path",
            "https://example.com/a b",
            "https://example.com\\@127.0.0.1/path",
            f"https://{'a' * 64}.example/path",
            "https://.example.com/path",
            "https://example..com/path",
        ):
            with self.subTest(url=url):
                self.assertIsNotNone(catalog.unsafe_http_url_reason(url))

        self.assertIsNone(
            catalog.resolved_http_url_reason(
                "https://example.test/path", resolver=public_resolver
            )
        )
        private_answer = [
            (
                socket.AF_INET,
                socket.SOCK_STREAM,
                socket.IPPROTO_TCP,
                "",
                ("127.0.0.1", 443),
            )
        ]
        mixed_answers = public_resolver("example.test", 443) + private_answer
        for answers in (private_answer, mixed_answers):
            with self.subTest(answers=answers):
                reason = catalog.resolved_http_url_reason(
                    "https://example.test/path",
                    resolver=mock.Mock(return_value=answers),
                )
                self.assertIn("non-public", reason)

    def test_validator_rejects_orphan_model_records(self):
        records = copy.deepcopy(self.records)
        paper = next(record for record in records if record["id"] == "hetercsi")
        paper["artifacts"]["models"] = {"status": "not-found", "items": []}
        with self.assertRaisesRegex(catalog.CatalogError, "model is not referenced"):
            catalog.validate_records(records)

    def test_verification_freshness_is_separate_from_deterministic_validation(self):
        records = copy.deepcopy(self.records)
        audit_day = date(2026, 8, 3)
        records[0]["last_verified"] = (audit_day - timedelta(days=181)).isoformat()
        records[1]["last_verified"] = (audit_day - timedelta(days=180)).isoformat()
        records[2]["last_verified"] = (audit_day + timedelta(days=1)).isoformat()

        catalog.validate_records(records)
        report = catalog.check_freshness(records, today=audit_day)
        by_id = {item["id"]: item for item in report["results"]}
        self.assertEqual(by_id[records[0]["id"]]["status"], "stale")
        self.assertEqual(by_id[records[1]["id"]]["status"], "current")
        self.assertEqual(by_id[records[2]["id"]]["status"], "future")

        with tempfile.TemporaryDirectory() as directory:
            report_path = Path(directory) / "freshness-report.json"
            with self.assertRaisesRegex(catalog.CatalogError, "Freshness audit failed"):
                catalog.check_freshness(
                    records,
                    today=audit_day,
                    report_path=report_path,
                    max_stale_rate=0,
                )
            self.assertTrue(report_path.is_file())

    def test_non_pretraining_papers_cannot_carry_stale_training_taxonomy(self):
        records = copy.deepcopy(self.records)
        paper = next(record for record in records if record["id"] == "early-exit")
        paper["objectives"] = ["masked-reconstruction"]
        paper["training_signals"] = ["self-supervised"]
        with self.assertRaisesRegex(
            catalog.CatalogError,
            r"non-pretraining papers require objectives: \[\][\s\S]*"
            r"non-pretraining papers require training_signals: \[\]",
        ):
            catalog.validate_records(records)

    def test_paper_resource_references_are_bidirectionally_declared(self):
        by_id = {record["id"]: record for record in self.records}
        for paper in (record for record in self.records if record["kind"] == "paper"):
            for slot in paper["artifacts"].values():
                for item in slot["items"]:
                    if "ref" not in item:
                        continue
                    with self.subTest(paper=paper["id"], resource=item["ref"]):
                        self.assertIn(paper["id"], by_id[item["ref"]]["related_papers"])

    def test_validator_enforces_both_directions_of_resource_relations(self):
        catalog.validate_records(list(reversed(copy.deepcopy(self.records))))

        records = copy.deepcopy(self.records)
        model = next(record for record in records if record["id"] == "hetercsi-model")
        model["related_papers"] = []
        with self.assertRaisesRegex(catalog.CatalogError, "does not include 'hetercsi'"):
            catalog.validate_records(records)

        records = copy.deepcopy(self.records)
        dataset = next(record for record in records if record["id"] == "mocsid")
        dataset["related_papers"] = ["lwm"]
        with self.assertRaisesRegex(
            catalog.CatalogError, "does not reference this resource"
        ):
            catalog.validate_records(records)

    def test_artifact_references_use_only_canonical_relationship_fields(self):
        by_id = {record["id"]: record for record in self.records}
        for paper in (record for record in self.records if record["kind"] == "paper"):
            for slot in paper["artifacts"].values():
                for item in slot["items"]:
                    if "ref" in item:
                        with self.subTest(paper=paper["id"], resource=item["ref"]):
                            self.assertEqual(set(item), {"label", "ref"})

        deepmimo_item = next(
            item
            for item in by_id["wifo-mud"]["artifacts"]["simulation_tools"]["items"]
            if item["ref"] == "deepmimo-toolchain"
        )
        resolved = catalog.resolve_artifact_item(deepmimo_item, by_id)
        self.assertEqual(resolved["provenance"], "official")
        self.assertEqual(resolved["availability"], "available")
        self.assertEqual(resolved["license"], "Apache-2.0")

        records = copy.deepcopy(self.records)
        paper = next(record for record in records if record["id"] == "lwm")
        paper["artifacts"]["models"]["items"][0]["license"] = "duplicated"
        with self.assertRaises(catalog.CatalogError):
            catalog.validate_records(records)

    def test_direct_resource_urls_have_one_canonical_owner(self):
        owners = {}
        for record in self.records:
            direct_urls = [link["url"] for link in record.get("links", [])]
            if record.get("paper_url", "").startswith(("http://", "https://")):
                direct_urls.append(record["paper_url"])
            if record.get("evaluation"):
                direct_urls.append(record["evaluation"]["protocol"]["url"])
            for slot in record.get("artifacts", {}).values():
                direct_urls.extend(
                    item["url"] for item in slot["items"] if item.get("url")
                )
            for url in direct_urls:
                with self.subTest(url=url):
                    self.assertNotIn(url, owners, f"also maintained by {owners.get(url)}")
                    owners[url] = record["id"]

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
            "### Contrastive/Alignment Learning",
            "### Reconstruction + Contrastive Learning",
            "### Predictive/Generative Modeling",
            "### Predictive Latent Learning",
            "### Task-Supervised Learning",
            "## Applications, Adaptation & Transfer",
            "## Inference & Deployment",
        ):
            self.assertIn(heading, rendered)

        ordered_headings = (
            "### Masked/Reconstruction Learning",
            "### Contrastive/Alignment Learning",
            "### Reconstruction + Contrastive Learning",
            "### Predictive/Generative Modeling",
            "### Predictive Latent Learning",
            "### Task-Supervised Learning",
        )
        positions = [rendered.index(heading) for heading in ordered_headings]
        self.assertEqual(positions, sorted(positions))

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
            "This Chinese-language invited position paper on CFM and 6G Native AI is "
            "published in ZTE Technology Journal. The [CNKI publication record]"
            "(https://link.cnki.net/urlid/34.1228.TN.20260225.0923.002) is available online."
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

    def test_secondary_pretraining_papers_show_compact_profiles(self):
        by_id = {record["id"]: record for record in self.records}
        papers = [record for record in self.records if record["kind"] == "paper"]
        for paper in papers:
            expected = paper["stages"][0] != "pretraining" and "pretraining" in paper["stages"]
            entry = catalog.render_paper_entry(paper, by_id)
            with self.subTest(paper=paper["id"]):
                self.assertEqual("**Pretraining:**" in entry, expected)

        airfm = catalog.render_paper_entry(by_id["airfm-dda"], by_id)
        self.assertIn(
            "**Pretraining:** Masked/Reconstruction Learning · "
            "**Signals:** Self-Supervised · **Task regime:** Not Specified",
            airfm,
        )
        hierarchical = catalog.render_paper_entry(by_id["hierarchical-wfm"], by_id)
        self.assertIn(
            "**Pretraining:** Masked/Reconstruction Learning (primary), "
            "Task-Supervised Learning, Direct Physical/Utility Optimization · "
            "**Signals:** Self-Supervised, Supervised · **Task regime:** Task-Conditioned",
            hierarchical,
        )
        self.assertNotIn(
            "**Pretraining:**",
            catalog.render_paper_entry(by_id["wifo-cf"], by_id),
        )

    def test_pretraining_objectives_follow_training_mechanism_not_task_count(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertEqual(by_id["6g-wavesfm"]["objectives"], ["masked-reconstruction"])
        self.assertEqual(by_id["6g-wavesfm"]["training_signals"], ["self-supervised"])
        self.assertEqual(
            by_id["wifo-2"]["objectives"],
            ["masked-reconstruction", "predictive-generative"],
        )
        self.assertEqual(by_id["wirelessgpt"]["objectives"], ["masked-reconstruction"])
        self.assertEqual(
            by_id["wireless-multitask-prediction"]["objectives"],
            ["predictive-generative"],
        )
        self.assertEqual(by_id["wifo-2"]["task_regime"], "task-conditioned")
        self.assertEqual(by_id["wirelessgpt"]["task_regime"], "not-specified")
        self.assertEqual(
            by_id["wireless-multitask-prediction"]["task_regime"], "multitask"
        )
        for paper_id in ("wifo-2", "wirelessgpt", "wireless-multitask-prediction"):
            self.assertNotIn("task-supervised", by_id[paper_id]["objectives"])

        rendered = catalog.render_papers(
            [record for record in self.records if record["kind"] == "paper"],
            self.records,
        )
        self.assertIn(
            "Classification follows the primary optimization objective used during "
            "pretraining, not the number of downstream tasks.",
            rendered,
        )
        supervised_section = rendered.split(
            '<a id="objective-task-supervised"></a>', 1
        )[1].split('<a id="adaptation"></a>', 1)[0]
        for paper_id in ("wifo-2", "wirelessgpt", "wireless-multitask-prediction"):
            self.assertNotIn(f'<a id="{paper_id}"></a>', supervised_section)

    def test_multi_objective_papers_use_concrete_labels_and_explicit_primary(self):
        by_id = {record["id"]: record for record in self.records}
        for paper_id in (
            "am-fm",
            "contrawimae",
            "lwlm",
            "m3f-uav",
            "multimodal-ai-6g",
            "spa-mae",
            "lwm-spectro",
        ):
            with self.subTest(paper=paper_id):
                paper = by_id[paper_id]
                self.assertGreater(len(paper["objectives"]), 1)
                self.assertIn(paper["primary_objective"], paper["objectives"])
                self.assertNotIn("hybrid", paper["objectives"])

    def test_reconstruction_contrastive_papers_share_a_public_section(self):
        paper_ids = {
            "am-fm",
            "contrawimae",
            "lwlm",
            "multimodal-ai-6g",
            "spa-mae",
        }
        rendered = catalog.render_papers(
            [record for record in self.records if record["kind"] == "paper"],
            self.records,
        )
        section = rendered.split(
            '<a id="objective-reconstruction-contrastive"></a>', 1
        )[1].split('<a id="objective-predictive-generative"></a>', 1)[0]
        for paper_id in paper_ids:
            with self.subTest(paper=paper_id):
                self.assertIn(f'<a id="{paper_id}"></a>', section)

        self.assertIn('<a id="lwm-spectro"></a>', section)

    def test_audited_stage_objective_and_modality_boundaries(self):
        by_id = {record["id"]: record for record in self.records}

        for paper_id in ("spikewfm", "wimamba"):
            with self.subTest(paper=paper_id):
                paper = by_id[paper_id]
                self.assertEqual(paper["stages"], ["backbone", "pretraining"])
                self.assertEqual(paper["objectives"], ["masked-reconstruction"])
                self.assertEqual(paper["training_signals"], ["self-supervised"])

        self.assertEqual(by_id["bert4beam"]["objectives"], ["task-supervised"])
        self.assertEqual(by_id["bert4beam"]["training_signals"], ["supervised"])
        self.assertEqual(by_id["bert4beam"]["task_regime"], "task-conditioned")
        self.assertEqual(
            by_id["bert4beam"]["stages"],
            ["application", "backbone", "pretraining", "adaptation"],
        )
        self.assertEqual(by_id["bert4beam"]["modalities"], ["csi", "system-metadata"])
        self.assertEqual(
            by_id["lwm-spectro"]["objectives"],
            ["masked-reconstruction", "contrastive-alignment"],
        )
        self.assertEqual(by_id["full-domain-coupler"]["scope"], "related-method")
        self.assertEqual(by_id["full-domain-coupler"]["modalities"], ["csi"])
        self.assertEqual(by_id["latentwave"]["modalities"], ["csi", "spectrogram"])
        self.assertEqual(by_id["radio-fm-indoor-localization"]["modalities"], ["cir"])

    def test_audited_multitask_papers_preserve_all_reported_tasks(self):
        by_id = {record["id"]: record for record in self.records}

        self.assertEqual(
            set(by_id["wirelessgpt"]["tasks"]),
            {
                "channel-estimation",
                "time-channel-extrapolation",
                "human-activity-recognition",
                "environment-reconstruction",
            },
        )
        self.assertEqual(len(by_id["wifo-2"]["tasks"]), 12)
        self.assertIn("doppler-estimation", by_id["wifo-2"]["tasks"])
        self.assertIn("channel-reconstruction", by_id["hetercsi"]["tasks"])

    def test_july_2026_foundation_models_are_cataloged_with_paper_based_taxonomy(self):
        by_id = {record["id"]: record for record in self.records}

        receiver = by_id["fm-receiver"]
        self.assertEqual(receiver["stages"], ["application", "pretraining"])
        self.assertEqual(receiver["objectives"], ["task-supervised"])
        self.assertEqual(receiver["training_signals"], ["supervised"])
        self.assertEqual(receiver["task_regime"], "multitask")
        self.assertEqual(receiver["modalities"], ["resource-grid", "csi"])
        self.assertEqual(
            receiver["tasks"],
            ["channel-estimation", "signal-detection", "channel-decoding"],
        )
        self.assertEqual(
            receiver["artifacts"]["simulation_tools"]["status"], "not-found"
        )
        self.assertEqual(receiver["artifacts"]["simulation_tools"]["items"], [])
        self.assertNotIn("fm-receiver", by_id["sionna"]["related_papers"])

        rendered = catalog.render_papers(
            [record for record in self.records if record["kind"] == "paper"],
            self.records,
        )
        application_section = rendered.split('<a id="adaptation"></a>', 1)[1].split(
            '<a id="inference-deployment"></a>', 1
        )[0]
        self.assertIn('<a id="fm-receiver"></a>', application_section)

        wifo_cf = by_id["wifo-cf"]
        self.assertEqual(wifo_cf["stages"], ["pretraining", "application"])
        self.assertEqual(wifo_cf["primary_objective"], "masked-reconstruction")
        masked_section = rendered.split(
            '<a id="objective-masked-reconstruction"></a>', 1
        )[1].split('<a id="objective-contrastive-alignment"></a>', 1)[0]
        self.assertIn('<a id="wifo-cf"></a>', masked_section)
        self.assertNotIn('<a id="wifo-cf"></a>', application_section)

        m3f = by_id["m3f-uav"]
        self.assertEqual(
            m3f["objectives"], ["masked-reconstruction", "task-supervised"]
        )
        self.assertEqual(m3f["modalities"], ["rgb", "depth", "lidar", "csi"])
        self.assertEqual(m3f["artifacts"]["datasets"]["items"][0]["ref"], "lambda-6g")

    def test_august_2026_literature_refresh_is_cataloged_and_auditable(self):
        by_id = {record["id"]: record for record in self.records}
        added_papers = {
            "cross-domain-wifi-sensing-fm",
            "cross-band-csi-reconstruction",
            "channelgpt",
            "farm",
            "filter-and-attend",
            "fm-rme",
            "foundation-model-communication-systems",
            "foundation-models-wireless-communications",
            "graph-fm-resource-allocation",
            "hierarchical-wfm",
            "how-big-wfm",
            "jepa-cfm",
            "large-ai-models-wireless-phy",
            "massive-mimo-precoding-fm",
            "multimodal-wireless-foundational-model",
            "phys-wfm",
            "predictive-foundation-channel-estimation",
            "scorefm",
            "sifo",
            "sigmap",
            "stronger-over-bigger",
            "tiny-wifo",
            "towards-csi-native",
            "towards-wireless-physical-layer-fm",
            "waloma",
            "wavesfm-multimodal",
            "wico-mg",
            "wico-pg",
            "wifo-e",
            "wifo-m2",
            "wifo-misac",
            "wifo-mud",
            "willm",
            "wireless-ai-evolution",
            "wmfm",
        }
        self.assertTrue(added_papers.issubset(by_id))
        for paper_id in added_papers:
            with self.subTest(paper=paper_id):
                self.assertEqual(by_id[paper_id]["kind"], "paper")
                self.assertGreaterEqual(by_id[paper_id]["last_verified"], "2026-08-03")

        cross_band = by_id["cross-band-csi-reconstruction"]
        self.assertEqual(cross_band["objectives"], ["masked-reconstruction"])
        self.assertEqual(cross_band["training_signals"], ["self-supervised"])
        self.assertEqual(
            cross_band["artifacts"]["datasets"]["items"][0]["ref"],
            "cross-band-rt-datasets",
        )

        jepa = by_id["jepa-cfm"]
        self.assertEqual(
            jepa["objectives"], ["masked-reconstruction", "predictive-latent"]
        )
        self.assertEqual(jepa["primary_objective"], "predictive-latent")
        self.assertNotIn("contrastive-alignment", jepa["objectives"])

        hierarchical = by_id["hierarchical-wfm"]
        self.assertEqual(
            hierarchical["objectives"],
            ["masked-reconstruction", "task-supervised", "direct-optimization"],
        )
        self.assertEqual(hierarchical["training_signals"], ["self-supervised", "supervised"])
        self.assertEqual(hierarchical["task_regime"], "task-conditioned")
        self.assertNotIn("contrastive-alignment", hierarchical["objectives"])

        multimodal = by_id["multimodal-wireless-foundational-model"]
        self.assertEqual(multimodal["objectives"], ["masked-reconstruction"])
        self.assertEqual(multimodal["modalities"], ["csi", "environment", "user-location"])
        self.assertEqual(multimodal["artifacts"]["datasets"]["status"], "not-released")
        self.assertEqual(multimodal["artifacts"]["models"]["status"], "not-released")

        for paper_id in (
            "cross-band-csi-reconstruction",
            "jepa-cfm",
            "hierarchical-wfm",
            "multimodal-wireless-foundational-model",
        ):
            self.assertEqual(
                by_id[paper_id]["artifacts"]["simulation_tools"]["status"],
                "not-found",
            )

        rt_data = by_id["cross-band-rt-datasets"]
        self.assertEqual(rt_data["kind"], "dataset")
        self.assertEqual(rt_data["related_papers"], ["cross-band-csi-reconstruction"])
        self.assertEqual(
            rt_data["specifications"]["frequency_bands"],
            ["2.4 GHz", "3.5 GHz", "15 GHz", "28 GHz", "40 GHz"],
        )
        self.assertEqual(rt_data["specifications"]["version"], "v1.0.0")
        self.assertEqual(len(rt_data["specifications"]["antenna_configurations"]), 3)
        self.assertEqual(rt_data["modalities"], ["multipath-components"])
        self.assertEqual(
            rt_data["license"],
            "Repository metadata MIT; dataset files license not stated; attribution required",
        )
        self.assertEqual(by_id["wavesfm-model"]["kind"], "model")
        self.assertEqual(by_id["wavesfm-model"]["related_papers"], ["wavesfm-multimodal"])
        self.assertEqual(
            by_id["wavesfm-multimodal"]["artifacts"]["datasets"]["items"][0]["ref"],
            "wavesfm-evaluation-suite",
        )
        self.assertEqual(
            by_id["wavesfm-evaluation-suite"]["related_papers"],
            ["wavesfm-multimodal"],
        )
        self.assertEqual(
            by_id["wavesfm-multimodal"]["modalities"],
            ["iq", "spectrogram", "wifi-csi", "5g-csi"],
        )
        self.assertIn("cir", by_id["wavesfm-model"]["modalities"])
        self.assertNotIn("cir", by_id["wavesfm-multimodal"]["modalities"])
        self.assertEqual(by_id["willm"]["artifacts"]["code"]["status"], "available")
        self.assertEqual(
            by_id["graph-fm-resource-allocation"]["objectives"],
            ["masked-reconstruction", "contrastive-alignment"],
        )
        self.assertEqual(
            by_id["farm"]["objectives"],
            ["masked-reconstruction", "predictive-generative"],
        )
        self.assertEqual(
            by_id["farm"]["artifacts"]["datasets"]["items"][0]["ref"],
            "farm-training-test",
        )
        self.assertEqual(by_id["cfm-bench"]["related_papers"], [])
        self.assertEqual(
            by_id["cfm-bench"]["evaluation"]["protocol"]["url"],
            "https://arxiv.org/abs/2607.14975",
        )
        self.assertEqual(
            by_id["cfm-bench"]["specifications"]["scale"],
            "157,900 single-frame examples (132,525 train / 17,523 validation / 7,852 test) across six domains",
        )
        self.assertEqual(len(by_id["cfm-bench"]["specifications"]["scenarios"]), 6)
        self.assertEqual(
            len(by_id["cfm-bench"]["specifications"]["antenna_configurations"]),
            6,
        )
        self.assertEqual(by_id["fm-rme"]["venue"], "IEEE International Conference on Communications")
        self.assertEqual(by_id["tiny-wifo"]["year"], 2026)
        self.assertEqual(by_id["tiny-wifo"]["venue"], "IEEE Wireless Communications Letters")
        self.assertEqual(
            by_id["tiny-wifo"]["paper_url"],
            "https://doi.org/10.1109/LWC.2026.3664439",
        )

        rendered = catalog.render_papers(
            [record for record in self.records if record["kind"] == "paper"],
            self.records,
        )
        masked_section = rendered.split(
            '<a id="objective-masked-reconstruction"></a>', 1
        )[1].split('<a id="objective-contrastive-alignment"></a>', 1)[0]
        for paper_id in (
            "cross-band-csi-reconstruction",
            "multimodal-wireless-foundational-model",
        ):
            self.assertIn(f'<a id="{paper_id}"></a>', masked_section)
        backbone_section = rendered.split('<a id="backbones"></a>', 1)[1].split(
            '<a id="pretraining"></a>', 1
        )[0]
        self.assertIn('<a id="hierarchical-wfm"></a>', backbone_section)
        latent_section = rendered.split(
            '<a id="objective-predictive-latent"></a>', 1
        )[1].split('<a id="objective-task-supervised"></a>', 1)[0]
        self.assertIn('<a id="jepa-cfm"></a>', latent_section)
        hybrid_section = rendered.split(
            '<a id="objective-reconstruction-contrastive"></a>', 1
        )[1].split('<a id="objective-predictive-generative"></a>', 1)[0]
        self.assertIn('<a id="wifo-misac"></a>', hybrid_section)

        for paper_id in ("massive-mimo-precoding-fm", "wifo-e"):
            self.assertEqual(by_id[paper_id]["objectives"], ["direct-optimization"])
            self.assertEqual(by_id[paper_id]["training_signals"], ["self-supervised"])

        channelgpt = by_id["channelgpt"]
        self.assertEqual(channelgpt["stages"], ["application", "adaptation"])
        self.assertEqual(channelgpt["objectives"], [])
        self.assertEqual(
            channelgpt["modalities"], ["csi", "rgb", "point-cloud", "user-location"]
        )
        application_section = rendered.split('<a id="adaptation"></a>', 1)[1].split(
            '<a id="inference-deployment"></a>', 1
        )[0]
        self.assertIn('<a id="channelgpt"></a>', application_section)

        self.assertNotIn("cfm-bench-paper", by_id)
        self.assertNotIn("Benchmarks & Evaluation", rendered)

        for excluded_id in (
            "emind",
            "emind-cjr-mix",
            "emind-pretrained-model",
            "mobigpt",
            "rfprompt",
            "spectrumfm",
        ):
            self.assertNotIn(excluded_id, by_id)

        deepverse = by_id["deepverse6g"]
        self.assertEqual(deepverse["kind"], "dataset")
        self.assertEqual(deepverse["related_papers"], ["wmfm"])
        self.assertEqual(
            by_id["wmfm"]["artifacts"]["datasets"]["items"][0]["ref"],
            "deepverse6g",
        )

        muse = by_id["muse-fm"]
        self.assertEqual(
            muse["objectives"], ["direct-optimization", "task-supervised"]
        )
        self.assertEqual(
            muse["modalities"],
            [
                "csi",
                "pilot-observations",
                "received-symbols",
                "environment",
                "system-metadata",
            ],
        )

    def test_wifi_csi_is_distinguished_from_generic_csi(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertEqual(by_id["am-fm"]["modalities"], ["wifi-csi"])
        self.assertEqual(
            by_id["6g-wavesfm"]["modalities"],
            ["wifi-csi", "5g-csi", "iq", "spectrogram", "resource-grid"],
        )
        self.assertEqual(by_id["lwm-spectro"]["modalities"], ["spectrogram"])
        self.assertEqual(
            by_id["building-6g-radio-fm"]["modalities"],
            ["spectrogram", "wifi-csi"],
        )

    def test_p14_content_review_conclusions_are_preserved(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertEqual(by_id["coupler-checkpoints"]["modalities"], ["csi"])
        self.assertNotIn("cir", by_id["coupler-checkpoints"]["modalities"])
        self.assertEqual(
            by_id["sionna"]["related_papers"],
            ["pilotwimae", "foundation-model-communication-systems"],
        )
        self.assertIn("Sionna", by_id["laetwin-xl-toolchain"]["description"])

        self.assertEqual(by_id["fm-rme"]["objectives"], ["masked-reconstruction"])
        wifo_mud_datasets = {
            item["ref"] for item in by_id["wifo-mud"]["artifacts"]["datasets"]["items"]
        }
        self.assertEqual(
            wifo_mud_datasets,
            {"argos-channel-survey", "dichasus", "synthsom"},
        )
        argos = by_id["argos-channel-survey"]
        self.assertEqual(argos["data_origin"], "measured")
        self.assertEqual(argos["access"], "registration")
        self.assertEqual(argos["related_papers"], ["wifo-mud"])
        self.assertIn("multi-user-demodulation", argos["tasks"])
        self.assertEqual(
            argos["specifications"]["download_size"],
            "102 individually downloadable files; approximately 0.58–29.72 GB per file",
        )

    def test_datasets_have_structured_release_and_coverage_metadata(self):
        for dataset in (record for record in self.records if record["kind"] == "dataset"):
            with self.subTest(dataset=dataset["id"]):
                self.assertEqual(
                    set(dataset["specifications"]),
                    {
                        "version",
                        "scale",
                        "download_size",
                        "frequency_bands",
                        "scenarios",
                        "antenna_configurations",
                    },
                )

    def test_deepmimo_is_only_cataloged_as_a_simulation_tool(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertNotIn("deepmimo", by_id)
        self.assertEqual(by_id["deepmimo-toolchain"]["kind"], "simulation-tool")
        self.assertNotIn("csigen", by_id)
        self.assertNotIn("pilotwimae-channels", by_id)
        self.assertNotIn("ns-3", by_id)
        outputs = catalog.render_outputs(self.records)
        dataset_page = outputs[catalog.OUTPUTS["dataset"]]
        tool_page = outputs[catalog.OUTPUTS["simulation-tool"]]
        self.assertNotIn('<a id="deepmimo"></a>', dataset_page)
        self.assertIn('<a id="deepmimo-toolchain"></a>', tool_page)
        self.assertNotIn('<a id="csigen"></a>', tool_page)
        self.assertNotIn('<a id="ns-3"></a>', tool_page)

    def test_verified_large_scale_datasets_are_cataloged(self):
        by_id = {record["id"]: record for record in self.records}
        expected = {
            "wifo-channel-dataset",
            "lambda-6g",
            "m3sc",
            "synthsom",
            "deepsense-6g",
            "multimodal-wireless",
            "mocsid",
        }
        self.assertTrue(expected.issubset(by_id))
        for dataset_id in expected:
            with self.subTest(dataset=dataset_id):
                self.assertEqual(by_id[dataset_id]["kind"], "dataset")
                self.assertGreaterEqual(by_id[dataset_id]["last_verified"], "2026-07-17")

        wifo = by_id["wifo"]
        self.assertEqual(wifo["artifacts"]["datasets"]["items"][0]["ref"], "wifo-channel-dataset")
        self.assertEqual(wifo["artifacts"]["simulation_tools"]["items"][0]["ref"], "quadriga")
        self.assertEqual(by_id["wifo-cf"]["artifacts"]["datasets"]["status"], "not-found")

    def test_laetwin_dataset_and_toolchain_remain_distinct(self):
        by_id = {record["id"]: record for record in self.records}
        self.assertEqual(by_id["laetwin-xl-dataset"]["kind"], "dataset")
        self.assertEqual(by_id["laetwin-xl-toolchain"]["kind"], "simulation-tool")

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

    def test_models_and_dataset_evaluations_have_no_standalone_public_sections(self):
        outputs = catalog.render_outputs(self.records)
        paper_page = outputs[catalog.OUTPUTS["paper"]]
        dataset_page = outputs[catalog.OUTPUTS["dataset"]]
        by_id = {record["id"]: record for record in self.records}
        for paper in (record for record in self.records if record["kind"] == "paper"):
            self.assertNotIn("benchmarks", paper["artifacts"])
            for item in paper["artifacts"]["models"]["items"]:
                if "ref" in item:
                    self.assertIn(catalog.primary_resource_url(by_id[item["ref"]]), paper_page)
        self.assertNotIn("**Benchmark:**", paper_page)
        self.assertNotIn("https://wavesfm.waveslab.ai/benchmarks/", paper_page)
        self.assertFalse(any(record["kind"] == "benchmark" for record in self.records))
        self.assertFalse(any((ROOT / "catalog" / "benchmarks").glob("*.yaml")))
        for dataset_id in ("cfm-bench", "lwm-challenge", "wavesfm-evaluation-suite"):
            evaluation = by_id[dataset_id]["evaluation"]
            self.assertIn(evaluation["name"], dataset_page)
            self.assertIn(evaluation["protocol"]["url"], dataset_page)
            for metric in evaluation["metrics"]:
                self.assertIn(metric, dataset_page)
        self.assertEqual(
            by_id["lwm"]["artifacts"]["datasets"]["items"],
            [{"label": "LWM Challenge", "ref": "lwm-challenge"}],
        )
        self.assertIn("https://wavesfm.waveslab.ai/docs/datasets/", dataset_page)
        for model in (record for record in self.records if record["kind"] == "model"):
            self.assertNotIn(f'<a id="{model["id"]}"></a>', paper_page)
        self.assertNotIn("## Pretrained Models", paper_page)
        self.assertNotIn("## Benchmark Projects", dataset_page)
        homepage = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("Pretrained Models", homepage)
        self.assertNotIn("Benchmark Projects", homepage)
        self.assertNotIn("models/README.md", homepage)
        self.assertNotIn("benchmarks/README.md", homepage)
        self.assertFalse((ROOT / "models" / "README.md").exists())
        self.assertFalse((ROOT / "benchmarks" / "README.md").exists())

    def test_public_pages_omit_maintenance_clutter(self):
        outputs = catalog.render_outputs(self.records)
        homepage = (ROOT / "README.md").read_text(encoding="utf-8")
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

    def test_homepage_is_the_single_manually_maintained_source(self):
        self.assertNotIn(ROOT / "README.md", catalog.OUTPUTS.values())
        self.assertFalse((ROOT / "templates" / "README.md").exists())
        homepage = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertNotIn("do not edit this file directly", homepage)
        self.assertIn(
            "img.shields.io/github/last-commit/"
            "GREAT-ISAC/Awesome-Channel-Foundation-Models/main",
            homepage,
        )

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
        content_license = (ROOT / "LICENSE-CONTENT").read_text(encoding="utf-8")
        self.assertIn("CC-BY-4.0", content_license)
        self.assertIn("PDF files under docs/ are expressly excluded", content_license)
        self.assertIn("MIT License", (ROOT / "LICENSE-CODE").read_text(encoding="utf-8"))

    def test_link_checker_accepts_success(self):
        open_request = mock.Mock(return_value=FakeResponse(200))
        self.assertEqual(
            catalog.check_url(
                "https://example.test",
                1,
                resolver=public_resolver,
                open_request=open_request,
            )[1],
            "ok",
        )

    def test_link_checker_treats_access_and_rate_limits_as_indeterminate(self):
        for status in (401, 403, 429):
            error = urllib.error.HTTPError("https://example.test", status, "blocked", {}, None)
            with self.subTest(status=status):
                self.assertEqual(
                    catalog.check_url(
                        "https://example.test",
                        1,
                        retries=0,
                        resolver=public_resolver,
                        open_request=mock.Mock(side_effect=error),
                    )[1],
                    "indeterminate",
                )

    def test_link_checker_reports_confirmed_http_failure(self):
        error = urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)
        self.assertEqual(
            catalog.check_url(
                "https://example.test",
                1,
                retries=0,
                resolver=public_resolver,
                open_request=mock.Mock(side_effect=error),
            )[1],
            "broken",
        )

    def test_link_checker_retries_head_with_get(self):
        head_error = urllib.error.HTTPError("https://example.test", 405, "method", {}, None)
        open_request = mock.Mock(side_effect=[head_error, FakeResponse(200)])
        self.assertEqual(
            catalog.check_url(
                "https://example.test",
                1,
                resolver=public_resolver,
                open_request=open_request,
            )[1],
            "ok",
        )
        self.assertEqual(open_request.call_count, 2)

    def test_link_checker_retries_head_404_with_get(self):
        head_error = urllib.error.HTTPError("https://example.test", 404, "missing", {}, None)
        open_request = mock.Mock(side_effect=[head_error, FakeResponse(200)])
        self.assertEqual(
            catalog.check_url(
                "https://example.test",
                1,
                retries=0,
                resolver=public_resolver,
                open_request=open_request,
            )[1],
            "ok",
        )
        self.assertEqual(open_request.call_count, 2)

    def test_link_checker_treats_server_errors_as_indeterminate(self):
        error = urllib.error.HTTPError("https://example.test", 503, "temporary", {}, None)
        self.assertEqual(
            catalog.check_url(
                "https://example.test",
                1,
                retries=2,
                retry_delay=0,
                resolver=public_resolver,
                open_request=mock.Mock(side_effect=error),
            )[1],
            "indeterminate",
        )

    def test_link_checker_applies_timeout_to_dns_resolution(self):
        def slow_resolver(_hostname, _port, **_kwargs):
            time.sleep(0.25)
            return public_resolver(_hostname, _port)

        started = time.monotonic()
        result = catalog.check_url(
            "https://example.test",
            0.01,
            retries=0,
            resolver=slow_resolver,
            open_request=mock.Mock(),
        )
        elapsed = time.monotonic() - started
        self.assertEqual(result[1], "indeterminate")
        self.assertIn("DNS resolution exceeded", result[2])
        self.assertLess(elapsed, 0.2)

    def test_link_checker_validates_dns_and_redirects_before_opening(self):
        private_resolver = mock.Mock(
            return_value=[
                (
                    socket.AF_INET,
                    socket.SOCK_STREAM,
                    socket.IPPROTO_TCP,
                    "",
                    ("127.0.0.1", 443),
                )
            ]
        )
        open_request = mock.Mock(return_value=FakeResponse(200))
        result = catalog.check_url(
            "https://example.test",
            1,
            retries=0,
            resolver=private_resolver,
            open_request=open_request,
        )
        self.assertEqual(result[1], "broken")
        open_request.assert_not_called()

        redirect = urllib.error.HTTPError(
            "https://example.test",
            302,
            "redirect",
            {"Location": "/next?part=1#section"},
            None,
        )
        open_request = mock.Mock(side_effect=[redirect, FakeResponse(200)])
        result = catalog.check_url(
            "https://example.test/start",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=open_request,
        )
        self.assertEqual(result[1], "ok")
        self.assertEqual(open_request.call_count, 2)
        self.assertEqual(
            open_request.call_args_list[1].args[0].full_url,
            "https://example.test/next?part=1#section",
        )

        unsafe_redirect = urllib.error.HTTPError(
            "https://example.test",
            302,
            "redirect",
            {"Location": "http://127.0.0.1/private"},
            None,
        )
        open_request = mock.Mock(side_effect=unsafe_redirect)
        result = catalog.check_url(
            "https://example.test/start",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=open_request,
        )
        self.assertEqual(result[1], "broken")
        self.assertEqual(open_request.call_count, 1)

        malformed_head_redirect = urllib.error.HTTPError(
            "https://example.test/start", 302, "redirect", {}, None
        )
        open_request = mock.Mock(
            side_effect=[malformed_head_redirect, FakeResponse(200)]
        )
        result = catalog.check_url(
            "https://example.test/start",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=open_request,
        )
        self.assertEqual(result[1], "ok")
        self.assertEqual(open_request.call_count, 2)

        invalid_location_redirect = urllib.error.HTTPError(
            "https://example.test/start",
            302,
            "redirect",
            {"Location": "https://[bad/path"},
            None,
        )
        open_request = mock.Mock(
            side_effect=[invalid_location_redirect, FakeResponse(200)]
        )
        result = catalog.check_url(
            "https://example.test/start",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=open_request,
        )
        self.assertEqual(result[1], "ok")
        self.assertEqual(open_request.call_count, 2)

        for location, max_redirects in ((None, 5), ("/start", 5), ("/next", 0)):
            headers = {} if location is None else {"Location": location}
            redirect = urllib.error.HTTPError(
                "https://example.test/start", 302, "redirect", headers, None
            )
            with self.subTest(location=location, max_redirects=max_redirects):
                result = catalog.check_url(
                    "https://example.test/start",
                    1,
                    retries=0,
                    resolver=public_resolver,
                    open_request=mock.Mock(side_effect=redirect),
                    max_redirects=max_redirects,
                )
                self.assertEqual(result[1], "broken")

        invalid_location_redirect = urllib.error.HTTPError(
            "https://example.test/start",
            302,
            "redirect",
            {"Location": "https://[bad/path"},
            None,
        )
        result = catalog.check_url(
            "https://example.test/start",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=mock.Mock(side_effect=invalid_location_redirect),
        )
        self.assertEqual(result[1], "broken")

        dns_failure = catalog.check_url(
            "https://example.test",
            1,
            retries=0,
            resolver=mock.Mock(side_effect=socket.gaierror("temporary DNS failure")),
            open_request=mock.Mock(),
        )
        self.assertEqual(dns_failure[1], "indeterminate")

        permanent_dns_failure = catalog.check_url(
            "https://does-not-exist.example",
            1,
            retries=0,
            resolver=mock.Mock(
                side_effect=socket.gaierror(socket.EAI_NONAME, "name not known")
            ),
            open_request=mock.Mock(),
        )
        self.assertEqual(permanent_dns_failure[1], "broken")

        invalid_url = catalog.check_url(
            "https://example.test",
            1,
            retries=0,
            resolver=public_resolver,
            open_request=mock.Mock(side_effect=http.client.InvalidURL("invalid")),
        )
        self.assertEqual(invalid_url[1], "broken")

    def test_link_audit_preserves_owners_and_embedded_markdown_links(self):
        shared_url = "https://example.test/resource?version=1#files"
        records = [
            {
                "id": "resource-one",
                "kind": "dataset",
                "_path": ROOT / "catalog" / "datasets" / "resource-one.yaml",
                "links": [
                    {
                        "url": shared_url,
                        "provenance": "official",
                        "availability": "available",
                    }
                ],
            },
            {
                "id": "paper-two",
                "kind": "paper",
                "_path": ROOT / "catalog" / "papers" / "paper-two.yaml",
                "note": f"See [the same release](<{shared_url}>).",
            },
        ]
        self.assertEqual(catalog.collect_urls(records), [shared_url])
        owners = catalog.collect_url_owners(records)[shared_url]
        self.assertEqual([owner["field"] for owner in owners], ["links[0].url", "note"])
        self.assertEqual(owners[0]["provenance"], "official")
        self.assertEqual(owners[0]["availability"], "available")
        self.assertEqual(owners[1]["provenance"], "unspecified")
        self.assertEqual(owners[1]["availability"], "unspecified")

        with mock.patch.object(
            catalog,
            "check_url",
            return_value=(shared_url, "ok", "200"),
        ) as checker:
            report = catalog.check_links(
                records,
                workers=1,
                timeout=1,
                retries=0,
                retry_delay=0,
                max_indeterminate_rate=1.0,
            )
        self.assertEqual(checker.call_count, 1)
        self.assertEqual(report["results"][0]["owners"], owners)

        cnki_url = "https://link.cnki.net/urlid/34.1228.TN.20260225.0923.002"
        cnki_owner = catalog.collect_url_owners(self.records)[cnki_url][0]
        self.assertEqual(cnki_owner["record_id"], "6g-native-ai-cfm")
        self.assertEqual(cnki_owner["field"], "note")

    def test_markdown_url_extraction_preserves_parenthesized_destinations(self):
        url = "https://example.test/a_(b)?version=1#section"
        for markdown in (f"[plain]({url})", f"[angle](<{url}>)"):
            with self.subTest(markdown=markdown):
                self.assertEqual(catalog.extract_markdown_urls(markdown), [url])

    def test_link_audit_writes_report_and_alerts_on_high_uncertainty(self):
        records = [
            {
                "links": [
                    {
                        "url": "https://example.test/resource",
                    }
                ]
            }
        ]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            catalog,
            "check_url",
            return_value=("https://example.test/resource", "indeterminate", "timeout"),
        ):
            report_path = Path(directory) / "link-report.json"
            with self.assertRaises(catalog.CatalogError):
                catalog.check_links(
                    records,
                    workers=1,
                    timeout=1,
                    retries=0,
                    retry_delay=0,
                    report_path=report_path,
                    max_indeterminate_rate=0.5,
                )
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["indeterminate"], 1)
            self.assertEqual(report["summary"]["indeterminate_rate"], 1.0)

    def test_link_audit_reports_unexpected_checker_errors(self):
        records = [{"links": [{"url": "https://example.test/resource"}]}]
        with tempfile.TemporaryDirectory() as directory, mock.patch.object(
            catalog, "check_url", side_effect=RuntimeError("unexpected")
        ):
            report_path = Path(directory) / "link-report.json"
            with self.assertRaisesRegex(
                catalog.CatalogError, "internal checker error"
            ):
                catalog.check_links(
                    records,
                    workers=1,
                    timeout=1,
                    retries=0,
                    retry_delay=0,
                    report_path=report_path,
                    max_indeterminate_rate=1.0,
                )
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["summary"]["checker_error"], 1)
            self.assertEqual(report["summary"]["indeterminate"], 0)
            self.assertEqual(report["results"][0]["status"], "checker-error")
            self.assertIn("checker error", report["results"][0]["detail"])


if __name__ == "__main__":
    unittest.main()
