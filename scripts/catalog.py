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
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple

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


def full_paper_link(paper: Mapping[str, Any], prefix: str = "../") -> str:
    url = paper["paper_url"]
    if url.startswith("docs/"):
        url = prefix + url
    return markdown_link(paper["title"], url)


def qualified_link(item: Mapping[str, Any], target: Optional[str] = None) -> str:
    qualifiers = []
    if item["provenance"] == "community":
        qualifiers.append("community")
    if item["availability"] != "available":
        qualifiers.append(item["availability"])
    text = item["label"]
    if qualifiers:
        text += f" ({', '.join(qualifiers)})"
    return markdown_link(text, target or item["url"])


def primary_resource_url(record: Mapping[str, Any]) -> str:
    for link in record["links"]:
        if link["availability"] in {"available", "restricted"}:
            return link["url"]
    return record["links"][0]["url"]


def available_artifacts(
    paper: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> List[str]:
    ref_targets = {
        "datasets": "../datasets/README.md#{}",
        "simulation_tools": "../simulation-tools/README.md#{}",
    }
    by_target: Dict[str, Dict[str, Any]] = {}
    for slot_name, slot in paper["artifacts"].items():
        if slot["status"] not in {"available", "restricted"}:
            continue
        for item in slot["items"]:
            target = item.get("url")
            if not target and slot_name in {"models", "benchmarks"}:
                target = primary_resource_url(by_id[item["ref"]])
            if not target:
                target = ref_targets[slot_name].format(item["ref"])
            group = by_target.setdefault(target, {"item": item, "types": []})
            artifact_type = ARTIFACT_LABELS[slot_name]
            if artifact_type not in group["types"]:
                group["types"].append(artifact_type)

    by_types: Dict[Tuple[str, ...], List[str]] = {}
    for target, group in by_target.items():
        types = tuple(group["types"])
        by_types.setdefault(types, []).append(qualified_link(group["item"], target))
    return [
        f"**{' / '.join(types)}:** {', '.join(item_links)}"
        for types, item_links in by_types.items()
    ]


def generated_header(title: str, intro: str) -> str:
    return (
        f"# {title}\n\n"
        "<!-- Generated from catalog/*.yaml; do not edit this file directly. -->\n\n"
        f"{intro}\n\n"
        "[← Back to the main catalog](../README.md)\n"
    )


def render_paper_entry(
    paper: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> str:
    lines = [
        f'<a id="{paper["id"]}"></a>',
        f"- **{paper['short_name']}** — {full_paper_link(paper)} "
        f"({paper['year']} · {paper['venue']})",
        f"  - **Authors:** {', '.join(paper['authors'])}",
    ]
    profile = []
    if paper["modalities"]:
        profile.append(f"**Modalities:** {', '.join(label(item) for item in paper['modalities'])}")
    if paper["tasks"]:
        profile.append(f"**Tasks:** {', '.join(label(item) for item in paper['tasks'])}")
    if profile:
        lines.append("  - " + " · ".join(profile))
    resources = available_artifacts(paper, by_id)
    if resources:
        lines.append("  - " + " · ".join(resources))
    return "\n".join(lines)


def primary_objective(paper: Mapping[str, Any]) -> str:
    objectives = paper["objectives"]
    if "hybrid" in objectives:
        return "hybrid"
    if "supervised-multitask" in objectives:
        return "supervised-multitask"
    return objectives[0] if objectives else "objective-not-specified"


def render_stage(
    title: str,
    anchor: str,
    papers: Sequence[Mapping[str, Any]],
    by_id: Mapping[str, Mapping[str, Any]],
) -> str:
    chunks = [f'<a id="{anchor}"></a>\n## {title}']
    chunks.extend(
        render_paper_entry(paper, by_id)
        for paper in sorted(
            papers,
            key=lambda item: (-item["year"], item["short_name"].lower()),
        )
    )
    return "\n\n".join(chunks)


def render_papers(
    papers: Sequence[Mapping[str, Any]],
    all_records: Sequence[Mapping[str, Any]],
) -> str:
    by_id = {record["id"]: record for record in all_records}
    by_stage: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for paper in papers:
        by_stage[paper["stages"][0]].append(paper)

    sections = [
        generated_header(
            "CFM Papers",
            "Each paper appears once in a stage-first hierarchy. Pretraining papers are further grouped by their primary learning objective; additional taxonomy remains in the YAML record.",
        ),
        "## Contents\n\n"
        "- [Surveys & Perspectives](#surveys)\n"
        "- [Backbones & Architectures](#backbones)\n"
        "- [Pretraining Methods](#pretraining)\n"
        "  - [Masked/Reconstruction](#objective-masked-reconstruction)\n"
        "  - [Autoregressive/Generative](#objective-autoregressive-generative)\n"
        "  - [Contrastive/Alignment](#objective-contrastive-alignment)\n"
        "  - [Predictive Latent](#objective-predictive-latent)\n"
        "  - [Supervised/Multitask](#objective-supervised-multitask)\n"
        "  - [Hybrid](#objective-hybrid)\n"
        "- [Adaptation & Transfer](#adaptation)\n"
        "- [Inference & Deployment](#inference-deployment)",
        render_stage(label("survey"), "surveys", by_stage["survey"], by_id),
        render_stage(label("backbone"), "backbones", by_stage["backbone"], by_id),
    ]

    objective_order = [
        "masked-reconstruction",
        "autoregressive-generative",
        "contrastive-alignment",
        "predictive-latent",
        "supervised-multitask",
        "hybrid",
        "objective-not-specified",
    ]
    by_objective: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for paper in by_stage["pretraining"]:
        by_objective[primary_objective(paper)].append(paper)
    pretraining = [
        '<a id="pretraining"></a>\n## Pretraining Methods',
        "Papers with multiple objectives are placed under Hybrid when explicitly tagged as hybrid, or under Supervised/Multitask when multitask learning is their primary organization.",
    ]
    for objective in objective_order:
        entries = by_objective[objective]
        if not entries:
            continue
        heading = "Objective Not Specified" if objective == "objective-not-specified" else label(objective)
        pretraining.append(f'<a id="objective-{objective}"></a>\n### {heading}')
        pretraining.extend(
            render_paper_entry(paper, by_id)
            for paper in sorted(
                entries,
                key=lambda item: (-item["year"], item["short_name"].lower()),
            )
        )
    sections.append("\n\n".join(pretraining))
    sections.append(
        render_stage(label("adaptation"), "adaptation", by_stage["adaptation"], by_id)
    )
    sections.append(
        render_stage(
            label("inference-deployment"),
            "inference-deployment",
            by_stage["inference-deployment"],
            by_id,
        )
    )
    return "\n\n".join(sections).rstrip() + "\n"


def resource_links(record: Mapping[str, Any]) -> str:
    return " · ".join(qualified_link(item) for item in record["links"])


def related_paper_links(
    record: Mapping[str, Any],
    papers: Mapping[str, Mapping[str, Any]],
    target_pattern: str,
) -> str:
    return ", ".join(
        markdown_link(papers[item]["short_name"], target_pattern.format(item))
        for item in record["related_papers"]
    )


def render_resource_record(
    kind: str,
    record: Mapping[str, Any],
    papers: Mapping[str, Mapping[str, Any]],
    heading_level: int = 2,
    paper_target: str = "../papers/README.md#{}",
    evaluations: Sequence[Mapping[str, Any]] = (),
) -> str:
    heading = "#" * heading_level
    lines = [
        f'<a id="{record["id"]}"></a>',
        f"{heading} {record['name']}",
        record["description"],
    ]
    if kind == "dataset":
        profile = [
            record["data_origin"].capitalize(),
            label(record["access"]),
            ", ".join(label(item) for item in record["modalities"]),
        ]
        lines.append(f"- **Profile:** {' · '.join(item for item in profile if item)}")
        lines.append(f"- **Tasks:** {', '.join(label(item) for item in record['tasks'])}")
        if evaluations:
            resource_urls = {item["url"] for item in record["links"]}
            evaluation_labels = []
            for item in evaluations:
                url = primary_resource_url(item)
                evaluation_labels.append(
                    item["name"] if url in resource_urls else markdown_link(item["name"], url)
                )
            lines.append(
                "- **Evaluation:** "
                + " · ".join(evaluation_labels)
            )
    else:
        lines.append(
            f"- **Profile:** {label(record['tool_type'])} · {label(record['access'])}"
        )
        lines.append(
            f"- **Capabilities:** {', '.join(label(item) for item in record['capabilities'])}"
        )
    lines.append(f"- **Links:** {resource_links(record)}")
    related = related_paper_links(record, papers, paper_target)
    if related:
        lines.append(f"- **Related papers:** {related}")
    return "\n".join(lines)


def render_datasets(
    datasets: Sequence[Mapping[str, Any]],
    benchmarks: Sequence[Mapping[str, Any]],
    all_records: Sequence[Mapping[str, Any]],
) -> str:
    papers = {record["id"]: record for record in all_records if record.get("kind") == "paper"}
    evaluations: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for benchmark in benchmarks:
        for dataset_id in benchmark["datasets"]:
            evaluations[dataset_id].append(benchmark)
    sections = [
        generated_header(
            "Datasets",
            "Measured and simulated datasets relevant to CFM research. Existing evaluation projects are attached directly to the datasets they use.",
        ),
    ]
    sections.extend(
        render_resource_record(
            "dataset",
            record,
            papers,
            evaluations=evaluations[record["id"]],
        )
        for record in sorted(datasets, key=lambda item: item["name"].lower())
    )
    return "\n\n".join(sections).rstrip() + "\n"


def render_simulation_tools(
    records: Sequence[Mapping[str, Any]],
    all_records: Sequence[Mapping[str, Any]],
) -> str:
    papers = {record["id"]: record for record in all_records if record.get("kind") == "paper"}
    sections = [
        generated_header(
            "Simulation Tools",
            "Open-first channel, ray-tracing, and system simulation infrastructure useful for CFM data workflows.",
        )
    ]
    sections.extend(
        render_resource_record("simulation-tool", record, papers)
        for record in sorted(records, key=lambda item: item["name"].lower())
    )
    if not records:
        sections.append("## No entries yet")
    return "\n\n".join(sections).rstrip() + "\n"


def render_readme(_records: Sequence[Mapping[str, Any]]) -> str:
    return README_TEMPLATE.read_text(encoding="utf-8")


def render_outputs(records: Sequence[Mapping[str, Any]]) -> Dict[Path, str]:
    by_kind: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_kind[record["kind"]].append(record)
    return {
        OUTPUTS["readme"]: render_readme(records),
        OUTPUTS["paper"]: render_papers(by_kind["paper"], records),
        OUTPUTS["dataset"]: render_datasets(
            by_kind["dataset"], by_kind["benchmark"], records
        ),
        OUTPUTS["simulation-tool"]: render_simulation_tools(
            by_kind["simulation-tool"], records
        ),
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
