#!/usr/bin/env python3
"""Validate, render, and inspect the Awesome CFM structured catalog."""

from __future__ import annotations

import argparse
import concurrent.futures
import json
import os
import sys
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any, Dict, Iterable, List, Mapping, Optional, Sequence, Tuple

import yaml
from jsonschema import Draft202012Validator, FormatChecker


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "catalog"
SCHEMA_PATH = ROOT / "schemas" / "catalog.schema.json"
README_TEMPLATE = ROOT / "templates" / "README.md"

OUTPUTS = {
    "readme": ROOT / "README.md",
    "paper": ROOT / "papers" / "README.md",
    "dataset": ROOT / "datasets" / "README.md",
    "model": ROOT / "models" / "README.md",
    "benchmark": ROOT / "benchmarks" / "README.md",
    "simulation-tool": ROOT / "simulation-tools" / "README.md",
}

KIND_DIRS = {
    "papers": "paper",
    "datasets": "dataset",
    "models": "model",
    "benchmarks": "benchmark",
    "simulation-tools": "simulation-tool",
}

DISPLAY = {
    "core-cfm": "Core CFM",
    "broader-wireless-radio-fm": "Broader Wireless/Radio FM",
    "related-method": "Related Method",
    "survey": "Surveys & Perspectives",
    "backbone": "Backbones & Architectures",
    "pretraining": "Pretraining Methods",
    "adaptation": "Adaptation & Transfer",
    "inference-deployment": "Inference & Deployment",
    "masked-reconstruction": "Masked/Reconstruction Learning",
    "autoregressive-generative": "Autoregressive/Generative Modeling",
    "contrastive-alignment": "Contrastive/Alignment Learning",
    "predictive-latent": "Predictive Latent Learning",
    "supervised-multitask": "Supervised/Multitask Pretraining",
    "hybrid": "Hybrid Objectives",
    "delay-doppler-angle": "Delay–Doppler–Angle",
    "los-nlos-identification": "LOS/NLOS Identification",
    "near-far-field-classification": "Near-/Far-Field Classification",
    "max-min-sinr-optimization": "Max–Min SINR Optimization",
    "snr-doppler-classification": "Joint SNR and Doppler Classification",
}

ACRONYMS = {
    "3d": "3D",
    "5g": "5G",
    "6g": "6G",
    "aoa": "AoA",
    "cir": "CIR",
    "csi": "CSI",
    "dda": "DDA",
    "fm": "FM",
    "gnss": "GNSS",
    "iq": "IQ",
    "los": "LOS",
    "mae": "MAE",
    "mimo": "MIMO",
    "mmwave": "mmWave",
    "nlos": "NLOS",
    "nmse": "NMSE",
    "rf": "RF",
    "sinr": "SINR",
    "snr": "SNR",
    "toa": "ToA",
    "wifi": "WiFi",
    "xl": "XL",
}

ARTIFACT_LABELS = {
    "code": "Code",
    "datasets": "Data",
    "models": "Weights",
    "benchmarks": "Benchmark",
    "simulation_tools": "Simulator",
}


class CatalogError(Exception):
    """Raised for deterministic catalog validation failures."""


def load_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    for directory, expected_kind in KIND_DIRS.items():
        path = CATALOG_DIR / directory
        if not path.exists():
            continue
        for yaml_path in sorted(path.glob("*.yaml")):
            try:
                record = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
            except yaml.YAMLError as exc:
                raise CatalogError(f"{yaml_path.relative_to(ROOT)}: invalid YAML: {exc}") from exc
            if not isinstance(record, dict):
                raise CatalogError(f"{yaml_path.relative_to(ROOT)}: expected a YAML mapping")
            record["_path"] = yaml_path
            record["_expected_kind"] = expected_kind
            records.append(record)
    return records


def public_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def validate_records(records: Sequence[Mapping[str, Any]]) -> None:
    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: List[str] = []
    by_id: Dict[str, Mapping[str, Any]] = {}

    for record in records:
        relpath = record["_path"].relative_to(ROOT)
        if record.get("kind") != record.get("_expected_kind"):
            errors.append(
                f"{relpath}: kind {record.get('kind')!r} does not match its catalog directory"
            )
        for error in sorted(validator.iter_errors(public_record(record)), key=str):
            location = ".".join(str(part) for part in error.absolute_path)
            suffix = f" at {location}" if location else ""
            errors.append(f"{relpath}{suffix}: {error.message}")
        record_id = record.get("id")
        if isinstance(record_id, str):
            if record_id in by_id:
                errors.append(
                    f"{relpath}: duplicate id {record_id!r}; already used by "
                    f"{by_id[record_id]['_path'].relative_to(ROOT)}"
                )
            else:
                by_id[record_id] = record

    paper_ids = {record["id"] for record in records if record.get("kind") == "paper"}
    kind_ids = defaultdict(set)
    for record in records:
        if "id" in record and "kind" in record:
            kind_ids[record["kind"]].add(record["id"])

    artifact_kind = {
        "datasets": "dataset",
        "models": "model",
        "benchmarks": "benchmark",
        "simulation_tools": "simulation-tool",
    }

    for record in records:
        relpath = record["_path"].relative_to(ROOT)
        if record.get("kind") == "paper":
            for slot_name, slot in record.get("artifacts", {}).items():
                status = slot.get("status")
                items = slot.get("items", [])
                if status in {"available", "restricted", "broken"} and not items:
                    errors.append(f"{relpath}: artifacts.{slot_name} status {status!r} requires items")
                if status in {"not-found", "not-released"} and items:
                    errors.append(f"{relpath}: artifacts.{slot_name} status {status!r} requires no items")
                for item in items:
                    if item.get("availability") != status and not (
                        status == "available" and item.get("availability") == "restricted"
                    ):
                        errors.append(
                            f"{relpath}: artifacts.{slot_name} item availability must match slot status"
                        )
                    ref = item.get("ref")
                    if ref:
                        expected = artifact_kind.get(slot_name)
                        if not expected or ref not in kind_ids[expected]:
                            errors.append(
                                f"{relpath}: artifacts.{slot_name} references unknown {expected} id {ref!r}"
                            )
        else:
            for paper_id in record.get("related_papers", []):
                if paper_id not in paper_ids:
                    errors.append(f"{relpath}: related_papers references unknown paper {paper_id!r}")
            if record.get("kind") == "benchmark":
                for dataset_id in record.get("datasets", []):
                    if dataset_id not in kind_ids["dataset"]:
                        errors.append(f"{relpath}: datasets references unknown dataset {dataset_id!r}")

    for record in records:
        paper_url = record.get("paper_url")
        if isinstance(paper_url, str) and not (
            paper_url.startswith("https://") or paper_url.startswith("http://") or paper_url.startswith("docs/")
        ):
            errors.append(f"{record['_path'].relative_to(ROOT)}: unsupported paper_url {paper_url!r}")
        local_url = record.get("local_url")
        if local_url and not (ROOT / local_url).is_file():
            errors.append(f"{record['_path'].relative_to(ROOT)}: local_url does not exist: {local_url}")

    if errors:
        raise CatalogError("Catalog validation failed:\n- " + "\n- ".join(errors))


def label(value: str) -> str:
    if value in DISPLAY:
        return DISPLAY[value]
    return " ".join(ACRONYMS.get(token, token.capitalize()) for token in value.split("-"))


def markdown_link(text: str, target: str) -> str:
    return f"[{text}]({target.replace(' ', '%20')})"


def paper_link(paper: Mapping[str, Any], prefix: str = "../") -> str:
    url = paper["paper_url"]
    if url.startswith("docs/"):
        url = prefix + url
    return markdown_link(paper["short_name"], url)


def full_paper_link(paper: Mapping[str, Any], prefix: str = "../") -> str:
    url = paper["paper_url"]
    if url.startswith("docs/"):
        url = prefix + url
    return markdown_link(paper["title"], url)


def artifact_cell(paper: Mapping[str, Any], slot_name: str) -> str:
    slot = paper["artifacts"][slot_name]
    status = slot["status"]
    if status == "not-found":
        return "Not found"
    if status == "not-released":
        return "Not released"
    links = []
    for item in slot["items"]:
        suffix_parts = [item["provenance"]]
        if item["availability"] != "available":
            suffix_parts.append(item["availability"])
        suffix = ", ".join(suffix_parts)
        target = item.get("url") or f"../{slot_name.replace('_', '-')}/README.md#{item['ref']}"
        links.append(markdown_link(f"{item['label']} ({suffix})", target))
    return "<br>".join(links) if links else label(status)


def make_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    rendered = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    rendered.extend("| " + " | ".join(str(cell).replace("\n", " ") for cell in row) + " |" for row in rows)
    return "\n".join(rendered)


def generated_header(title: str, intro: str) -> str:
    return (
        f"# {title}\n\n"
        "<!-- Generated from catalog/*.yaml; do not edit this file directly. -->\n\n"
        f"{intro}\n\n"
        "[← Back to the main catalog](../README.md)\n"
    )


def grouped_paper_view(papers: Sequence[Mapping[str, Any]], field: str, heading: str) -> str:
    grouped: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for paper in papers:
        for value in paper[field]:
            grouped[value].append(paper)
    chunks = [f"## {heading}"]
    for value in sorted(grouped, key=lambda item: label(item).lower()):
        entries = sorted(grouped[value], key=lambda paper: (-paper["year"], paper["short_name"].lower()))
        chunks.append(f"### {label(value)}")
        chunks.extend(f"- {paper_link(paper)} ({paper['year']})" for paper in entries)
    return "\n\n".join(chunks)


def render_papers(papers: Sequence[Mapping[str, Any]]) -> str:
    papers = sorted(papers, key=lambda paper: (-paper["year"], paper["short_name"].lower()))
    rows = []
    for paper in papers:
        rows.append(
            [
                f"<a id=\"{paper['id']}\"></a>{paper_link(paper)}",
                str(paper["year"]),
                label(paper["scope"]),
                ", ".join(label(item) for item in paper["stages"]),
                ", ".join(label(item) for item in paper["modalities"]) or "—",
                ", ".join(label(item) for item in paper["objectives"]) or "—",
                ", ".join(label(item) for item in paper["tasks"]) or "—",
                artifact_cell(paper, "code"),
                artifact_cell(paper, "datasets"),
                artifact_cell(paper, "models"),
                artifact_cell(paper, "benchmarks"),
                artifact_cell(paper, "simulation_tools"),
            ]
        )
    details = ["## Paper records"]
    for paper in papers:
        detail_lines = [
                f"### {paper['short_name']} ({paper['year']})",
                f"- **Paper:** {full_paper_link(paper)}",
                f"- **Authors:** {', '.join(paper['authors'])}",
                f"- **Venue:** {paper['venue']}",
                f"- **Scope:** {label(paper['scope'])}",
                f"- **Research stages:** {', '.join(label(item) for item in paper['stages'])}",
                f"- **Pretraining objectives:** {', '.join(label(item) for item in paper['objectives']) or 'Not applicable'}",
                f"- **Modalities:** {', '.join(label(item) for item in paper['modalities']) or 'Not specified'}",
                f"- **Downstream tasks:** {', '.join(label(item) for item in paper['tasks']) or 'Not specified'}",
                "- **Resources:** "
                + "; ".join(
                    f"{ARTIFACT_LABELS[name]} — {artifact_cell(paper, name)}"
                    for name in ARTIFACT_LABELS
                ),
                f"- **Last verified:** {paper['last_verified']}",
            ]
        if paper.get("summary"):
            detail_lines.append(f"- **Note:** {paper['summary']}")
        details.append("\n".join(detail_lines))
    sections = [
        generated_header(
            "CFM Papers",
            "A structured, non-exclusive view of CFM and adjacent wireless foundation-model research.",
        ),
        "## Master catalog\n\n"
        + make_table(
            ["Paper", "Year", "Scope", "Stage", "Modality", "Objective", "Tasks", "Code", "Data", "Weights", "Benchmark", "Simulator"],
            rows,
        ),
        "\n\n".join(details),
        grouped_paper_view(papers, "stages", "Browse by research stage"),
        grouped_paper_view(papers, "objectives", "Browse by pretraining objective"),
        grouped_paper_view(papers, "modalities", "Browse by modality"),
        grouped_paper_view(papers, "tasks", "Browse by downstream task"),
    ]

    reproducibility = defaultdict(list)
    for paper in papers:
        available = [
            ARTIFACT_LABELS[name]
            for name, slot in paper["artifacts"].items()
            if slot["status"] in {"available", "restricted"}
        ]
        key = ", ".join(available) if available else "Paper only"
        reproducibility[key].append(paper)
    repro_chunks = ["## Browse by reproducibility status"]
    for status in sorted(reproducibility):
        repro_chunks.append(f"### {status}")
        repro_chunks.extend(f"- {paper_link(paper)} ({paper['year']})" for paper in reproducibility[status])
    sections.append("\n\n".join(repro_chunks))
    return "\n\n".join(sections).rstrip() + "\n"


def first_available_link(record: Mapping[str, Any]) -> str:
    for item in record["links"]:
        if item["availability"] in {"available", "restricted"}:
            return markdown_link(record["name"], item["url"])
    return record["name"]


def resource_links(record: Mapping[str, Any]) -> str:
    links = []
    for item in record["links"]:
        details = f"{item['provenance']}, {item['availability']}"
        links.append(markdown_link(f"{item['label']} ({details})", item["url"]))
    return "<br>".join(links)


def render_resources(
    kind: str,
    records: Sequence[Mapping[str, Any]],
    all_records: Sequence[Mapping[str, Any]],
) -> str:
    config = {
        "dataset": (
            "Datasets",
            "Measured and simulated datasets relevant to channel foundation-model training and evaluation.",
            ["Dataset", "Description", "Origin", "Access", "Modalities", "Tasks", "Links", "License", "Related papers", "Verified"],
        ),
        "model": (
            "Pretrained Models",
            "Public checkpoints and model cards associated with cataloged foundation models.",
            ["Model", "Description", "Framework", "Access", "Modalities", "Tasks", "Links", "License", "Related papers", "Verified"],
        ),
        "benchmark": (
            "Benchmark Projects",
            "Existing external evaluation projects; this repository does not provide a new benchmark runner in v1.",
            ["Benchmark", "Description", "Tasks", "Datasets", "Metrics", "Links", "License", "Related papers", "Verified"],
        ),
        "simulation-tool": (
            "Simulation Tools",
            "Open-first channel, ray-tracing, and system simulation infrastructure useful for CFM data workflows.",
            ["Tool", "Description", "Type", "Access", "Capabilities", "Links", "License", "Related papers", "Verified"],
        ),
    }
    title, intro, headers = config[kind]
    by_id = {record["id"]: record for record in all_records}
    papers = {record["id"]: record for record in all_records if record.get("kind") == "paper"}
    rows = []
    for record in sorted(records, key=lambda item: item["name"].lower()):
        name = f"<a id=\"{record['id']}\"></a>{first_available_link(record)}"
        related = ", ".join(paper_link(papers[item]) for item in record["related_papers"]) or "—"
        links = resource_links(record)
        if kind == "dataset":
            row = [name, record["description"], record["data_origin"].capitalize(), label(record["access"]), ", ".join(label(x) for x in record["modalities"]), ", ".join(label(x) for x in record["tasks"]), links, record["license"], related, record["last_verified"]]
        elif kind == "model":
            row = [name, record["description"], record["framework"], label(record["access"]), ", ".join(label(x) for x in record["modalities"]), ", ".join(label(x) for x in record["tasks"]), links, record["license"], related, record["last_verified"]]
        elif kind == "benchmark":
            dataset_names = ", ".join(by_id.get(item, {}).get("name", item) for item in record["datasets"]) or "—"
            row = [name, record["description"], ", ".join(label(x) for x in record["tasks"]), dataset_names, ", ".join(record["metrics"]) or "—", links, record["license"], related, record["last_verified"]]
        else:
            row = [name, record["description"], label(record["tool_type"]), label(record["access"]), ", ".join(label(x) for x in record["capabilities"]), links, record["license"], related, record["last_verified"]]
        rows.append(row)
    if not rows:
        rows = [["No verified records yet"] + ["—"] * (len(headers) - 1)]
    return generated_header(title, intro) + "\n\n" + make_table(headers, rows) + "\n"


def render_readme(records: Sequence[Mapping[str, Any]]) -> str:
    by_kind = Counter(record["kind"] for record in records)
    papers = sorted(
        (record for record in records if record["kind"] == "paper"),
        key=lambda paper: (-paper["year"], paper["short_name"].lower()),
    )
    template = README_TEMPLATE.read_text(encoding="utf-8")
    stats = " · ".join(
        [
            f"**{by_kind['paper']} papers**",
            f"**{by_kind['dataset']} datasets**",
            f"**{by_kind['model']} pretrained models**",
            f"**{by_kind['benchmark']} benchmark projects**",
            f"**{by_kind['simulation-tool']} simulation tools**",
        ]
    )
    stage_counts = Counter(stage for paper in papers for stage in paper["stages"])
    taxonomy = "\n".join(
        f"- [{label(stage)}](papers/README.md#browse-by-research-stage) — "
        f"{stage_counts[stage]} {'entry' if stage_counts[stage] == 1 else 'entries'}"
        for stage in ["survey", "backbone", "pretraining", "adaptation", "inference-deployment"]
        if stage_counts[stage]
    )
    recent_rows = [
        [paper_link(paper, prefix=""), str(paper["year"]), label(paper["scope"]), ", ".join(label(stage) for stage in paper["stages"])]
        for paper in papers[:12]
    ]
    recent = make_table(["Paper", "Year", "Scope", "Research stage"], recent_rows)
    artifact_counts = Counter()
    for paper in papers:
        for slot_name, slot in paper["artifacts"].items():
            if slot["status"] in {"available", "restricted"}:
                artifact_counts[slot_name] += 1
    reproducibility = make_table(
        ["Artifact", "Papers with a verified resource", "Coverage"],
        [
            [
                ARTIFACT_LABELS[name],
                str(artifact_counts[name]),
                f"{(100 * artifact_counts[name] / len(papers)):.1f}%" if papers else "0.0%",
            ]
            for name in ARTIFACT_LABELS
        ],
    )
    last_verified = max((record["last_verified"] for record in records), default="Not available")
    return (
        template.replace("{{STATS}}", stats)
        .replace("{{TAXONOMY}}", taxonomy)
        .replace("{{RECENT_PAPERS}}", recent)
        .replace("{{REPRODUCIBILITY}}", reproducibility)
        .replace("{{LAST_VERIFIED}}", last_verified)
    )


def render_outputs(records: Sequence[Mapping[str, Any]]) -> Dict[Path, str]:
    by_kind: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_kind[record["kind"]].append(record)
    return {
        OUTPUTS["readme"]: render_readme(records),
        OUTPUTS["paper"]: render_papers(by_kind["paper"]),
        OUTPUTS["dataset"]: render_resources("dataset", by_kind["dataset"], records),
        OUTPUTS["model"]: render_resources("model", by_kind["model"], records),
        OUTPUTS["benchmark"]: render_resources("benchmark", by_kind["benchmark"], records),
        OUTPUTS["simulation-tool"]: render_resources("simulation-tool", by_kind["simulation-tool"], records),
    }


def generate(records: Sequence[Mapping[str, Any]], check: bool) -> None:
    outputs = render_outputs(records)
    stale = []
    for path, content in outputs.items():
        if check:
            if not path.exists() or path.read_text(encoding="utf-8") != content:
                stale.append(str(path.relative_to(ROOT)))
            continue
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    if stale:
        raise CatalogError("Generated files are stale: " + ", ".join(stale))


def collect_urls(records: Sequence[Mapping[str, Any]]) -> List[str]:
    urls = set()
    for record in records:
        paper_url = record.get("paper_url")
        if isinstance(paper_url, str) and paper_url.startswith(("http://", "https://")):
            urls.add(paper_url)
        for link in record.get("links", []):
            urls.add(link["url"])
        for slot in record.get("artifacts", {}).values():
            for item in slot.get("items", []):
                if item.get("url"):
                    urls.add(item["url"])
    return sorted(urls)


def check_url(url: str, timeout: float) -> Tuple[str, str, str]:
    headers = {"User-Agent": "Awesome-CFM-link-checker/1.0 (+https://github.com/GREAT-ISAC/Awesome-Channel-Foundation-Models)"}
    for method in ("HEAD", "GET"):
        request = urllib.request.Request(url, headers=headers, method=method)
        if method == "GET":
            request.add_header("Range", "bytes=0-1023")
        try:
            with urllib.request.urlopen(request, timeout=timeout) as response:
                status = response.getcode()
            if 200 <= status < 400:
                return url, "ok", str(status)
        except urllib.error.HTTPError as exc:
            if exc.code in {403, 405, 429} and method == "HEAD":
                continue
            if exc.code in {403, 429}:
                return url, "indeterminate", str(exc.code)
            if method == "HEAD" and exc.code in {400, 405, 501}:
                continue
            return url, "broken", str(exc.code)
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            if method == "HEAD":
                continue
            return url, "indeterminate", str(exc.reason if hasattr(exc, "reason") else exc)
    return url, "indeterminate", "no response"


def check_links(records: Sequence[Mapping[str, Any]], workers: int, timeout: float) -> None:
    urls = collect_urls(records)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = [executor.submit(check_url, url, timeout) for url in urls]
        for future in concurrent.futures.as_completed(futures):
            results.append(future.result())
    counts = Counter(status for _, status, _ in results)
    for url, status, detail in sorted(results):
        print(f"{status:13} {detail:20} {url}")
    print(f"Checked {len(urls)} URLs: {counts['ok']} ok, {counts['indeterminate']} indeterminate, {counts['broken']} broken")
    if counts["broken"]:
        raise CatalogError(f"{counts['broken']} broken URL(s) found")


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate all YAML records and references")
    generate_parser = subparsers.add_parser("generate", help="render README and resource pages")
    generate_parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    links_parser = subparsers.add_parser("check-links", help="check catalog HTTP(S) links without modifying data")
    links_parser.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 2) * 2))
    links_parser.add_argument("--timeout", type=float, default=15.0)
    return parser.parse_args(argv)


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = parse_args(argv or sys.argv[1:])
    try:
        records = load_records()
        validate_records(records)
        if args.command == "validate":
            print(f"Validated {len(records)} catalog records.")
        elif args.command == "generate":
            generate(records, check=args.check)
            print("Generated catalog files are current." if args.check else "Generated catalog files.")
        elif args.command == "check-links":
            check_links(records, workers=args.workers, timeout=args.timeout)
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
