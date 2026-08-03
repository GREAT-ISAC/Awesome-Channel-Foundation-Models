#!/usr/bin/env python3
"""Validate, render, and inspect the Awesome CFM structured catalog."""

from __future__ import annotations

import argparse
import concurrent.futures
import http.client
import ipaddress
import json
import os
import queue
import re
import socket
import sys
import threading
import time
import urllib.error
import urllib.request
from collections import Counter, defaultdict
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Mapping, Optional, Sequence, Tuple
from urllib.parse import urljoin, urlparse

import yaml
from jsonschema import Draft202012Validator, FormatChecker
from yaml.resolver import BaseResolver


ROOT = Path(__file__).resolve().parents[1]
CATALOG_DIR = ROOT / "catalog"
SCHEMA_PATH = ROOT / "schemas" / "catalog.schema.json"

OUTPUTS = {
    "paper": ROOT / "papers" / "README.md",
    "dataset": ROOT / "datasets" / "README.md",
    "simulation-tool": ROOT / "simulation-tools" / "README.md",
}

KIND_DIRS = {
    "papers": "paper",
    "datasets": "dataset",
    "models": "model",
    "simulation-tools": "simulation-tool",
}

MAX_VERIFICATION_AGE_DAYS = 180
PROSE_LINK_FIELDS = ("description", "summary", "abstract", "abstract_zh", "note")
REDIRECT_STATUS_CODES = {301, 302, 303, 307, 308}
PERMANENT_DNS_ERRORS = {
    value
    for value in (getattr(socket, "EAI_NONAME", None), getattr(socket, "EAI_NODATA", None))
    if value is not None
}
MARKDOWN_ANGLE_LINK_RE = re.compile(
    r"\[[^\]\n]*\]\(\s*<(https?://[^>\s]+)>(?:\s+['\"][^)]*['\"])?\s*\)"
)
MARKDOWN_PLAIN_LINK_RE = re.compile(
    r"\[[^\]\n]*\]\(\s*(https?://(?:[^()\s]|\([^()\s]*\))+)(?:\s+['\"][^)]*['\"])?\s*\)"
)
MARKDOWN_AUTOLINK_RE = re.compile(r"<(https?://[^>\s]+)>")

DISPLAY = {
    "cfm-ecosystem": "CFM Ecosystem",
    "related-method": "Related Method",
    "survey": "Surveys & Perspectives",
    "backbone": "Backbones & Architectures",
    "pretraining": "Pretraining Methods",
    "application": "Applications",
    "adaptation": "Adaptation & Transfer",
    "inference-deployment": "Inference & Deployment",
    "masked-reconstruction": "Masked/Reconstruction Learning",
    "reconstruction-contrastive": "Reconstruction + Contrastive Learning",
    "predictive-generative": "Predictive/Generative Modeling",
    "contrastive-alignment": "Contrastive/Alignment Learning",
    "predictive-latent": "Predictive Latent Learning",
    "direct-optimization": "Direct Physical/Utility Optimization",
    "task-supervised": "Task-Supervised Learning",
    "self-supervised": "Self-Supervised",
    "supervised": "Supervised",
    "weakly-supervised": "Weakly-Supervised",
    "single-task": "Single-Task",
    "multitask": "Multitask",
    "task-conditioned": "Task-Conditioned",
    "not-specified": "Not Specified",
    "delay-doppler-angle": "Delay–Doppler–Angle",
    "los-nlos-identification": "LOS/NLOS Identification",
    "near-far-field-classification": "Near-/Far-Field Classification",
    "max-min-sinr-optimization": "Max–Min SINR Optimization",
    "qos-aware-resource-allocation": "QoS-Aware Resource Allocation",
    "short-term-forecasting": "Short-Term Forecasting",
    "long-term-forecasting": "Long-Term Forecasting",
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
    "imu": "IMU",
    "lidar": "LiDAR",
    "los": "LOS",
    "mae": "MAE",
    "mimo": "MIMO",
    "mmwave": "mmWave",
    "nlos": "NLOS",
    "nmse": "NMSE",
    "qos": "QoS",
    "rf": "RF",
    "rgb": "RGB",
    "rsrp": "RSRP",
    "sinr": "SINR",
    "snr": "SNR",
    "toa": "ToA",
    "uav": "UAV",
    "wifi": "WiFi",
    "xl": "XL",
}

ARTIFACT_LABELS = {
    "code": "Code",
    "datasets": "Data",
    "models": "Weights",
    "simulation_tools": "Simulator",
}


class CatalogError(Exception):
    """Raised for deterministic catalog validation failures."""


class UnsafeURL(ValueError):
    """Raised when an automated request would target an unsafe URL."""


class RedirectPolicyError(ValueError):
    """Raised when a redirect chain is malformed, cyclic, or too long."""


class UniqueKeyLoader(yaml.SafeLoader):
    """Safe YAML loader that rejects duplicate mapping keys."""


def _construct_unique_mapping(
    loader: UniqueKeyLoader, node: yaml.MappingNode, deep: bool = False
) -> Dict[Any, Any]:
    loader.flatten_mapping(node)
    mapping: Dict[Any, Any] = {}
    for key_node, value_node in node.value:
        key = loader.construct_object(key_node, deep=deep)
        if key in mapping:
            raise yaml.constructor.ConstructorError(
                "while constructing a mapping",
                node.start_mark,
                f"found duplicate key {key!r}",
                key_node.start_mark,
            )
        mapping[key] = loader.construct_object(value_node, deep=deep)
    return mapping


UniqueKeyLoader.add_constructor(
    BaseResolver.DEFAULT_MAPPING_TAG, _construct_unique_mapping
)


def load_records() -> List[Dict[str, Any]]:
    records: List[Dict[str, Any]] = []
    catalog_yaml_paths = sorted(
        candidate
        for candidate in CATALOG_DIR.rglob("*")
        if candidate.is_file() and candidate.suffix.lower() in {".yaml", ".yml"}
    )
    for yaml_path in catalog_yaml_paths:
        relative = yaml_path.relative_to(CATALOG_DIR)
        if len(relative.parts) != 2:
            if relative.parts and relative.parts[0] in KIND_DIRS:
                raise CatalogError(
                    f"{yaml_path.relative_to(ROOT)}: nested catalog records are not supported"
                )
            raise CatalogError(
                f"{yaml_path.relative_to(ROOT)}: unsupported catalog record location"
            )
        if relative.parts[0] not in KIND_DIRS:
            raise CatalogError(
                f"{yaml_path.relative_to(ROOT)}: unsupported catalog kind directory "
                f"{relative.parts[0]!r}"
            )

    for directory, expected_kind in KIND_DIRS.items():
        path = CATALOG_DIR / directory
        if not path.exists():
            continue
        yaml_paths = sorted(
            candidate
            for candidate in path.rglob("*")
            if candidate.is_file() and candidate.suffix.lower() in {".yaml", ".yml"}
        )
        for yaml_path in yaml_paths:
            try:
                record = yaml.load(
                    yaml_path.read_text(encoding="utf-8"), Loader=UniqueKeyLoader
                )
            except yaml.YAMLError as exc:
                raise CatalogError(f"{yaml_path.relative_to(ROOT)}: invalid YAML: {exc}") from exc
            if not isinstance(record, dict):
                raise CatalogError(f"{yaml_path.relative_to(ROOT)}: expected a YAML mapping")
            if record.get("id") != yaml_path.stem:
                raise CatalogError(
                    f"{yaml_path.relative_to(ROOT)}: filename stem must match record id "
                    f"{record.get('id')!r}"
                )
            record["_path"] = yaml_path
            record["_expected_kind"] = expected_kind
            records.append(record)
    return records


def public_record(record: Mapping[str, Any]) -> Dict[str, Any]:
    return {key: value for key, value in record.items() if not key.startswith("_")}


def repository_file_reason(
    value: str,
    *,
    root: Optional[Path] = None,
    required_subdir: Optional[str] = None,
) -> Optional[str]:
    """Return why a local catalog path is not a regular file inside the repository."""

    raw_path = Path(value)
    if raw_path.is_absolute():
        return "expected a repository-relative path"
    root_path = (root or ROOT).resolve()
    try:
        candidate = (root_path / raw_path).resolve(strict=True)
    except (FileNotFoundError, OSError, RuntimeError):
        return "file does not exist or cannot be resolved"
    try:
        candidate.relative_to(root_path)
    except ValueError:
        return "path resolves outside the repository"
    if required_subdir:
        allowed_root = (root_path / required_subdir).resolve()
        try:
            candidate.relative_to(allowed_root)
        except ValueError:
            return f"path must remain inside {required_subdir}/"
    if not candidate.is_file():
        return "path is not a regular file"
    return None


def extract_markdown_urls(text: str) -> List[str]:
    """Extract explicit Markdown links and autolinks without guessing bare URLs."""

    return sorted(
        {
            *MARKDOWN_ANGLE_LINK_RE.findall(text),
            *MARKDOWN_PLAIN_LINK_RE.findall(text),
            *MARKDOWN_AUTOLINK_RE.findall(text),
        }
    )


def unsafe_http_url_reason(url: str) -> Optional[str]:
    """Return why a catalog URL is unsafe for the automated checker, if applicable."""

    if any(
        character.isspace() or ord(character) < 32 or ord(character) == 127
        for character in url
    ):
        return "URL whitespace and control characters must be percent-encoded"
    if "\\" in url:
        return "backslashes are not allowed in HTTP(S) URLs"
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        # Accessing port also validates malformed and out-of-range values.
        explicit_port = parsed.port
    except ValueError as exc:
        return f"invalid URL authority: {exc}"
    if parsed.scheme not in {"http", "https"} or not hostname:
        return "expected an absolute HTTP(S) URL"
    if parsed.username is not None or parsed.password is not None:
        return "URL userinfo is not allowed"
    if explicit_port is not None and explicit_port < 1:
        return "URL port must be between 1 and 65535"
    hostname = hostname.lower().rstrip(".")
    if hostname == "localhost" or hostname.endswith(".localhost"):
        return "localhost URLs are not allowed"
    if "%" in hostname:
        return "zone-qualified IP addresses are not allowed"
    try:
        address = ipaddress.ip_address(hostname)
    except ValueError:
        try:
            ascii_hostname = hostname.encode("idna")
        except UnicodeError:
            return "hostname is not valid IDNA"
        labels = ascii_hostname.split(b".")
        if len(ascii_hostname) > 253 or any(
            not label or len(label) > 63 for label in labels
        ):
            return "hostname contains an empty or overlong DNS label"
        return None
    if not address.is_global or address.is_multicast:
        return "non-public IP addresses are not allowed"
    return None


def resolved_http_url_reason(
    url: str,
    *,
    resolver: Optional[Any] = None,
    timeout: float = 15.0,
) -> Optional[str]:
    """Resolve a URL host and reject any answer that is not globally routable."""

    if timeout <= 0:
        raise ValueError("DNS resolution timeout must be positive")
    reason = unsafe_http_url_reason(url)
    if reason:
        return reason
    parsed = urlparse(url)
    port = parsed.port or (443 if parsed.scheme == "https" else 80)
    lookup = resolver or socket.getaddrinfo
    # The connection layer resolves the hostname again. Checking immediately
    # before each request and rejecting mixed public/private answers mitigates
    # SSRF, but does not claim to provide transport-level DNS pinning.
    resolution_result: queue.Queue[Tuple[bool, Any]] = queue.Queue(maxsize=1)

    def resolve() -> None:
        try:
            answers = lookup(parsed.hostname, port, type=socket.SOCK_STREAM)
            resolution_result.put((True, answers))
        except Exception as exc:
            resolution_result.put((False, exc))

    # CPython cannot cancel a getaddrinfo() call that is already running. A
    # daemon resolver thread gives each audit request a real deadline without
    # allowing a stalled resolver to keep the CLI process alive indefinitely.
    threading.Thread(target=resolve, daemon=True).start()
    try:
        succeeded, value = resolution_result.get(timeout=timeout)
    except queue.Empty as exc:
        raise TimeoutError(
            f"DNS resolution exceeded {timeout:g}s for {parsed.hostname}"
        ) from exc
    if not succeeded:
        raise value
    answers = value
    addresses = []
    for family, _socktype, _proto, _canonname, sockaddr in answers:
        if family not in {socket.AF_INET, socket.AF_INET6} or not sockaddr:
            continue
        raw_address = str(sockaddr[0]).split("%", 1)[0]
        try:
            addresses.append(ipaddress.ip_address(raw_address))
        except ValueError:
            continue
    if not addresses:
        raise socket.gaierror(f"DNS lookup returned no IP addresses for {parsed.hostname}")
    unsafe = sorted(
        str(address)
        for address in addresses
        if not address.is_global or address.is_multicast
    )
    if unsafe:
        return "hostname resolves to non-public address(es): " + ", ".join(unsafe)
    return None


def validate_records(records: Sequence[Mapping[str, Any]]) -> None:
    """Validate catalog structure first, then run cross-record semantic checks."""

    schema = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    validator = Draft202012Validator(schema, format_checker=FormatChecker())
    errors: List[str] = []
    by_id: Dict[str, Mapping[str, Any]] = {}

    # Phase one never assumes a record has a valid shape. This keeps malformed
    # submissions in the normal CatalogError report instead of leaking KeyError,
    # TypeError, or AttributeError from the semantic checks below.
    for record in records:
        relpath = record["_path"].relative_to(ROOT)
        if record.get("kind") != record.get("_expected_kind"):
            errors.append(
                f"{relpath}: kind {record.get('kind')!r} does not match its catalog directory"
            )
        schema_errors = sorted(validator.iter_errors(public_record(record)), key=str)
        for error in schema_errors:
            location = ".".join(str(part) for part in error.absolute_path)
            suffix = f" at {location}" if location else ""
            errors.append(f"{relpath}{suffix}: {error.message}")
        if schema_errors:
            continue
        record_id = record.get("id")
        if record_id in by_id:
            errors.append(
                f"{relpath}: duplicate id {record_id!r}; already used by "
                f"{by_id[record_id]['_path'].relative_to(ROOT)}"
            )
        else:
            by_id[record_id] = record

    if errors:
        raise CatalogError("Catalog validation failed:\n- " + "\n- ".join(errors))

    # Phase two is safe to access required fields because every record has
    # already passed the JSON Schema.
    errors = []
    url_owners: Dict[str, str] = {}
    paper_ids = {record["id"] for record in records if record["kind"] == "paper"}
    kind_ids = defaultdict(set)
    for record in records:
        kind_ids[record["kind"]].add(record["id"])

    artifact_kind = {
        "datasets": "dataset",
        "models": "model",
        "simulation_tools": "simulation-tool",
    }
    referenced_model_ids = set()
    forward_resource_refs = set()

    for record in records:
        relpath = record["_path"].relative_to(ROOT)
        if record["kind"] == "paper":
            stages = record["stages"]
            objectives = record["objectives"]
            primary_objective = record["primary_objective"]
            training_signals = record["training_signals"]
            task_regime = record["task_regime"]
            if "pretraining" in stages:
                if not objectives:
                    errors.append(f"{relpath}: pretraining papers require at least one objective")
                if not training_signals:
                    errors.append(f"{relpath}: pretraining papers require at least one training signal")
                if primary_objective not in objectives:
                    errors.append(
                        f"{relpath}: primary_objective must be one of the paper's objectives"
                    )
                if task_regime == "not-applicable":
                    errors.append(f"{relpath}: pretraining papers cannot use task_regime 'not-applicable'")
            else:
                if objectives:
                    errors.append(f"{relpath}: non-pretraining papers require objectives: []")
                if primary_objective is not None:
                    errors.append(f"{relpath}: non-pretraining papers require primary_objective: null")
                if training_signals:
                    errors.append(f"{relpath}: non-pretraining papers require training_signals: []")
                if task_regime != "not-applicable":
                    errors.append(f"{relpath}: non-pretraining papers require task_regime 'not-applicable'")
            for slot_name, slot in record["artifacts"].items():
                status = slot["status"]
                items = slot["items"]
                if status in {"available", "restricted", "broken"} and not items:
                    errors.append(f"{relpath}: artifacts.{slot_name} status {status!r} requires items")
                if status in {"not-found", "not-released"} and items:
                    errors.append(f"{relpath}: artifacts.{slot_name} status {status!r} requires no items")
                resolved_availability = []
                for item in items:
                    ref = item.get("ref")
                    if ref:
                        expected = artifact_kind.get(slot_name)
                        if not expected or ref not in kind_ids[expected]:
                            errors.append(
                                f"{relpath}: artifacts.{slot_name} references unknown {expected} id {ref!r}"
                            )
                            continue
                        target_record = by_id[ref]
                        canonical_link = primary_resource_link(target_record)
                        resolved_availability.append(canonical_link["availability"])
                        forward_resource_refs.add((record["id"], ref, slot_name))
                        if record["id"] not in target_record["related_papers"]:
                            errors.append(
                                f"{relpath}: artifacts.{slot_name} references {ref!r}, but the resource does not include {record['id']!r} in related_papers"
                            )
                        if expected == "model":
                            referenced_model_ids.add(ref)
                    else:
                        resolved_availability.append(item["availability"])
                        if slot_name in {"datasets", "simulation_tools"}:
                            errors.append(
                                f"{relpath}: artifacts.{slot_name} must use a canonical resource ref instead of a direct URL"
                            )
                if resolved_availability:
                    expected_status = (
                        "available"
                        if "available" in resolved_availability
                        else "restricted"
                        if "restricted" in resolved_availability
                        else "broken"
                    )
                    if status != expected_status:
                        errors.append(
                            f"{relpath}: artifacts.{slot_name} status {status!r} does not match canonical item availability {expected_status!r}"
                        )
        else:
            for paper_id in record["related_papers"]:
                if paper_id not in paper_ids:
                    errors.append(f"{relpath}: related_papers references unknown paper {paper_id!r}")

        direct_urls = [link["url"] for link in record.get("links", [])]
        paper_url = record.get("paper_url")
        if isinstance(paper_url, str) and paper_url.startswith(("http://", "https://")):
            direct_urls.append(paper_url)
        evaluation = record.get("evaluation")
        if isinstance(evaluation, Mapping):
            protocol = evaluation.get("protocol", {})
            if isinstance(protocol, Mapping) and protocol.get("url"):
                direct_urls.append(protocol["url"])
        for slot_name, slot in record.get("artifacts", {}).items():
            direct_urls.extend(
                item["url"] for item in slot.get("items", []) if item.get("url")
            )
        for url in direct_urls:
            reason = unsafe_http_url_reason(url)
            if reason:
                errors.append(f"{relpath}: URL {url!r} is invalid: {reason}")
            owner = url_owners.get(url)
            if owner:
                errors.append(
                    f"{relpath}: URL {url!r} is already maintained by {owner}; use a resource ref or one canonical role"
                )
            else:
                url_owners[url] = str(relpath)
        for field in PROSE_LINK_FIELDS:
            value = record.get(field)
            if not isinstance(value, str):
                continue
            for url in extract_markdown_urls(value):
                reason = unsafe_http_url_reason(url)
                if reason:
                    errors.append(
                        f"{relpath}: {field} URL {url!r} is invalid: {reason}"
                    )

    # Check the reverse direction after every paper reference has been collected,
    # so validation is independent of input record ordering.
    for record in (item for item in records if item["kind"] != "paper"):
        relpath = record["_path"].relative_to(ROOT)
        expected_slot = {
            "dataset": "datasets",
            "model": "models",
            "simulation-tool": "simulation_tools",
        }[record["kind"]]
        for paper_id in record["related_papers"]:
            if paper_id in paper_ids and (
                paper_id,
                record["id"],
                expected_slot,
            ) not in forward_resource_refs:
                errors.append(
                    f"{relpath}: related_papers includes {paper_id!r}, but that paper does not reference this resource from artifacts.{expected_slot}"
                )

    for record in records:
        relpath = record["_path"].relative_to(ROOT)
        paper_url = record.get("paper_url")
        if isinstance(paper_url, str) and not paper_url.startswith(
            ("http://", "https://")
        ):
            if Path(paper_url).parts and Path(paper_url).parts[0] == "docs":
                reason = repository_file_reason(paper_url, required_subdir="docs")
                if reason:
                    errors.append(
                        f"{relpath}: paper_url {paper_url!r} is invalid: {reason}"
                    )
            else:
                errors.append(f"{relpath}: unsupported paper_url {paper_url!r}")
        local_url = record.get("local_url")
        if local_url:
            reason = repository_file_reason(local_url)
            if reason:
                errors.append(
                    f"{relpath}: local_url {local_url!r} is invalid: {reason}"
                )
    for model in (record for record in records if record.get("kind") == "model"):
        if model.get("id") not in referenced_model_ids:
            errors.append(
                f"{model['_path'].relative_to(ROOT)}: model is not referenced by any paper artifact"
            )

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


def primary_resource_link(record: Mapping[str, Any]) -> Mapping[str, Any]:
    for link in record["links"]:
        if link["availability"] in {"available", "restricted"}:
            return link
    return record["links"][0]


def primary_resource_url(record: Mapping[str, Any]) -> str:
    return primary_resource_link(record)["url"]


def resolve_artifact_item(
    item: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> Mapping[str, Any]:
    """Resolve canonical metadata for a paper artifact reference."""

    if "ref" not in item:
        return item
    resolved = dict(primary_resource_link(by_id[item["ref"]]))
    resolved["label"] = item["label"]
    return resolved


def available_artifacts(
    paper: Mapping[str, Any], by_id: Mapping[str, Mapping[str, Any]]
) -> List[str]:
    ref_targets = {
        "datasets": "../datasets/README.md#{}",
        "simulation_tools": "../simulation-tools/README.md#{}",
    }
    by_target: Dict[str, Dict[str, Any]] = {}
    for slot_name, slot in paper["artifacts"].items():
        # Dataset relationships remain in YAML and on the dataset page. Repeating
        # them under individual papers makes the paper index harder to scan.
        if slot_name == "datasets":
            continue
        for item in slot["items"]:
            resolved_item = resolve_artifact_item(item, by_id)
            if resolved_item["availability"] not in {"available", "restricted"}:
                continue
            target = item.get("url")
            if not target and slot_name == "models":
                target = resolved_item["url"]
            if not target:
                target = ref_targets[slot_name].format(item["ref"])
            group = by_target.setdefault(
                target, {"item": resolved_item, "types": []}
            )
            artifact_type = ARTIFACT_LABELS[slot_name]
            if artifact_type not in group["types"]:
                group["types"].append(artifact_type)

    by_types: Dict[Tuple[str, ...], List[str]] = {}
    for target, group in by_target.items():
        types = tuple(group["types"])
        # A single implementation repository often hosts code, checkpoints, and
        # evaluation scripts. One Code link conveys that without repeating roles.
        if "Code" in types:
            types = ("Code",)
        by_types.setdefault(types, []).append(qualified_link(group["item"], target))
    return [
        f"**{' / '.join(types)}:** {', '.join(item_links)}"
        for types, item_links in by_types.items()
    ]


def generated_header(title: str, intro: str) -> str:
    return (
        f"# {title}\n\n"
        "<!-- Generated from catalog/*/*.yaml; do not edit this file directly. -->\n\n"
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
    is_survey = "survey" in paper["stages"]
    if not is_survey and paper["modalities"]:
        lines.append(
            f"  - **Modalities:** {', '.join(label(item) for item in paper['modalities'])}"
        )
    if not is_survey and paper["tasks"]:
        lines.append(f"  - **Tasks:** {', '.join(label(item) for item in paper['tasks'])}")
    if paper["stages"][0] != "pretraining" and "pretraining" in paper["stages"]:
        objectives = []
        multiple_objectives = len(paper["objectives"]) > 1
        ordered_objectives = sorted(
            paper["objectives"],
            key=lambda objective: objective != paper["primary_objective"],
        )
        for objective in ordered_objectives:
            objective_label = label(objective)
            if multiple_objectives and objective == paper["primary_objective"]:
                objective_label += " (primary)"
            objectives.append(objective_label)
        profile = [f"**Pretraining:** {', '.join(objectives)}"]
        profile.append(
            f"**Signals:** {', '.join(label(item) for item in paper['training_signals'])}"
        )
        profile.append(f"**Task regime:** {label(paper['task_regime'])}")
        lines.append("  - " + " · ".join(profile))
    if is_survey:
        for field, field_label in (
            ("summary", "Summary"),
            ("abstract", "Abstract"),
            ("abstract_zh", "摘要"),
            ("note", "Note"),
        ):
            if paper.get(field):
                lines.append(f"  - **{field_label}:** {paper[field]}")
    resources = available_artifacts(paper, by_id)
    if resources:
        lines.append("  - " + " · ".join(resources))
    return "\n".join(lines)


def pretraining_section_key(paper: Mapping[str, Any]) -> str:
    """Return the presentation group for a primary-stage pretraining paper."""

    objectives = set(paper.get("objectives", []))
    if {"masked-reconstruction", "contrastive-alignment"} <= objectives:
        return "reconstruction-contrastive"
    return paper.get("primary_objective") or "objective-not-specified"


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
            "Each paper appears once in a stage-first hierarchy. Papers whose primary stage is pretraining are grouped by objective; papers cataloged under another primary stage show a compact pretraining profile inline.",
        ),
        "## Contents\n\n"
        "- [Surveys & Perspectives](#surveys)\n"
        "- [Backbones & Architectures](#backbones)\n"
        "- [Pretraining Methods](#pretraining)\n"
        "  - [Masked/Reconstruction](#objective-masked-reconstruction)\n"
        "  - [Contrastive/Alignment](#objective-contrastive-alignment)\n"
        "  - [Reconstruction + Contrastive](#objective-reconstruction-contrastive)\n"
        "  - [Predictive/Generative](#objective-predictive-generative)\n"
        "  - [Predictive Latent](#objective-predictive-latent)\n"
        "  - [Task-Supervised](#objective-task-supervised)\n"
        "- [Applications, Adaptation & Transfer](#adaptation)\n"
        "- [Inference & Deployment](#inference-deployment)",
        render_stage(label("survey"), "surveys", by_stage["survey"], by_id),
        render_stage(label("backbone"), "backbones", by_stage["backbone"], by_id),
    ]

    objective_order = [
        "masked-reconstruction",
        "contrastive-alignment",
        "reconstruction-contrastive",
        "predictive-generative",
        "predictive-latent",
        "direct-optimization",
        "task-supervised",
        "objective-not-specified",
    ]
    by_objective: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for paper in by_stage["pretraining"]:
        by_objective[pretraining_section_key(paper)].append(paper)
    pretraining = [
        '<a id="pretraining"></a>\n## Pretraining Methods',
        "Classification follows the primary optimization objective used during pretraining, not the number of downstream tasks.",
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
        render_stage(
            "Applications, Adaptation & Transfer",
            "adaptation",
            [*by_stage["application"], *by_stage["adaptation"]],
            by_id,
        )
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
        specifications = record["specifications"]
        release_details = []
        if specifications["version"]:
            release_details.append(f"Version: {specifications['version']}")
        if specifications["scale"]:
            release_details.append(f"Scale: {specifications['scale']}")
        if specifications["download_size"]:
            release_details.append(f"Download: {specifications['download_size']}")
        if release_details:
            lines.append(f"- **Release:** {' · '.join(release_details)}")
        coverage = []
        for field, field_label in (
            ("frequency_bands", "Bands"),
            ("scenarios", "Scenarios"),
            ("antenna_configurations", "Antennas"),
        ):
            if specifications[field]:
                coverage.append(f"{field_label}: {', '.join(specifications[field])}")
        if coverage:
            lines.append(f"- **Coverage:** {' · '.join(coverage)}")
        evaluation = record.get("evaluation")
        if evaluation:
            lines.append(f"- **Evaluation:** {evaluation['name']}")
            lines.append(
                f"- **Protocol:** {qualified_link(evaluation['protocol'])}"
            )
            lines.append(f"- **Metrics:** {', '.join(evaluation['metrics'])}")
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
    all_records: Sequence[Mapping[str, Any]],
) -> str:
    papers = {record["id"]: record for record in all_records if record.get("kind") == "paper"}
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
        )
        for record in sorted(
            datasets,
            key=lambda item: (not item.get("featured", False), item["name"].lower()),
        )
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


def render_outputs(records: Sequence[Mapping[str, Any]]) -> Dict[Path, str]:
    by_kind: Dict[str, List[Mapping[str, Any]]] = defaultdict(list)
    for record in records:
        by_kind[record["kind"]].append(record)
    return {
        OUTPUTS["paper"]: render_papers(by_kind["paper"], records),
        OUTPUTS["dataset"]: render_datasets(by_kind["dataset"], records),
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


def collect_url_owners(
    records: Sequence[Mapping[str, Any]],
) -> Dict[str, List[Dict[str, Any]]]:
    """Collect each unique URL together with every catalog field that owns it."""

    owners: Dict[str, List[Dict[str, Any]]] = defaultdict(list)

    def add_owner(
        record: Mapping[str, Any],
        url: Any,
        field: str,
        link: Optional[Mapping[str, Any]] = None,
    ) -> None:
        if not isinstance(url, str) or not url.startswith(("http://", "https://")):
            return
        source_path = record.get("_path")
        path = None
        if isinstance(source_path, Path):
            try:
                path = str(source_path.relative_to(ROOT))
            except ValueError:
                path = str(source_path)
        owner = {
            "path": path,
            "record_id": record.get("id"),
            "kind": record.get("kind"),
            "field": field,
            "provenance": (link or {}).get("provenance", "unspecified"),
            "availability": (link or {}).get("availability", "unspecified"),
        }
        if owner not in owners[url]:
            owners[url].append(owner)

    for record in records:
        paper_url = record.get("paper_url")
        add_owner(record, paper_url, "paper_url")
        for index, link in enumerate(record.get("links", [])):
            add_owner(record, link.get("url"), f"links[{index}].url", link)
        evaluation = record.get("evaluation")
        if evaluation:
            protocol = evaluation["protocol"]
            add_owner(record, protocol.get("url"), "evaluation.protocol.url", protocol)
        for slot_name, slot in record.get("artifacts", {}).items():
            for index, item in enumerate(slot.get("items", [])):
                add_owner(
                    record,
                    item.get("url"),
                    f"artifacts.{slot_name}.items[{index}].url",
                    item,
                )
        for field in PROSE_LINK_FIELDS:
            value = record.get(field)
            if isinstance(value, str):
                for url in extract_markdown_urls(value):
                    add_owner(record, url, field)

    for url in owners:
        owners[url].sort(
            key=lambda item: (
                item["path"] or "",
                item["record_id"] or "",
                item["field"],
            )
        )
    return dict(owners)


def collect_urls(records: Sequence[Mapping[str, Any]]) -> List[str]:
    """Return sorted unique catalog URLs; retained as a stable public helper."""

    return sorted(collect_url_owners(records))


def check_freshness(
    records: Sequence[Mapping[str, Any]],
    max_age_days: int = MAX_VERIFICATION_AGE_DAYS,
    today: Optional[date] = None,
    report_path: Optional[Path] = None,
    max_stale_rate: Optional[float] = None,
) -> Dict[str, Any]:
    """Report verification freshness without making deterministic validation age-dependent."""

    if max_age_days < 0:
        raise CatalogError("max verification age cannot be negative")
    if max_stale_rate is not None and not 0 <= max_stale_rate <= 1:
        raise CatalogError("max stale rate must be between 0 and 1")

    audit_day = today or datetime.now(timezone.utc).date()
    results = []
    for record in records:
        verified_day = date.fromisoformat(record["last_verified"])
        age = (audit_day - verified_day).days
        status = "future" if age < 0 else "stale" if age > max_age_days else "current"
        results.append(
            {
                "id": record["id"],
                "kind": record["kind"],
                "path": str(record["_path"].relative_to(ROOT)),
                "last_verified": record["last_verified"],
                "age_days": age,
                "status": status,
            }
        )

    counts = Counter(item["status"] for item in results)
    stale_rate = counts["stale"] / len(results) if results else 0.0
    report = {
        "as_of": audit_day.isoformat(),
        "policy": {
            "max_age_days": max_age_days,
            "max_stale_rate": max_stale_rate,
        },
        "summary": {
            "total": len(results),
            "current": counts["current"],
            "stale": counts["stale"],
            "future": counts["future"],
            "stale_rate": round(stale_rate, 4),
        },
        "results": sorted(results, key=lambda item: (item["status"], item["path"])),
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote freshness audit report to {report_path}")

    print(
        f"Audited {len(results)} records: {counts['current']} current, "
        f"{counts['stale']} stale, {counts['future']} future-dated"
    )
    for item in report["results"]:
        if item["status"] != "current":
            print(
                f"{item['status']:7} {item['last_verified']} "
                f"{item['path']} ({item['age_days']} days)"
            )

    if max_stale_rate is not None:
        failures = []
        if counts["future"]:
            failures.append(f"{counts['future']} future-dated record(s)")
        if stale_rate > max_stale_rate:
            failures.append(
                f"stale rate {stale_rate:.1%} exceeds {max_stale_rate:.1%}"
            )
        if failures:
            raise CatalogError("Freshness audit failed: " + "; ".join(failures))
    return report


class NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Expose redirects to the checker so every target can be validated first."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def open_checked_request(
    request: urllib.request.Request,
    timeout: float,
    *,
    resolver: Optional[Any] = None,
    open_request: Optional[Any] = None,
    max_redirects: int = 5,
):
    """Open an HTTP request after validating DNS and each redirect destination."""

    if max_redirects < 0:
        raise RedirectPolicyError("maximum redirects cannot be negative")
    if open_request is None:
        open_request = urllib.request.build_opener(NoRedirectHandler()).open
    current_url = request.full_url
    method = request.get_method()
    headers = dict(request.header_items())
    visited = set()
    redirects = 0
    while True:
        reason = resolved_http_url_reason(
            current_url, resolver=resolver, timeout=timeout
        )
        if reason:
            raise UnsafeURL(reason)
        if current_url in visited:
            raise RedirectPolicyError("redirect loop detected")
        visited.add(current_url)
        current_request = urllib.request.Request(
            current_url, headers=headers, method=method
        )
        try:
            return open_request(current_request, timeout=timeout)
        except urllib.error.HTTPError as exc:
            if exc.code not in REDIRECT_STATUS_CODES:
                raise
            location = exc.headers.get("Location") if exc.headers else None
            if not location:
                raise RedirectPolicyError(
                    f"redirect response {exc.code} has no Location header"
                )
            if redirects >= max_redirects:
                raise RedirectPolicyError(
                    f"redirect limit of {max_redirects} exceeded"
                )
            try:
                current_url = urljoin(current_url, location)
            except (TypeError, ValueError) as join_error:
                raise RedirectPolicyError(
                    f"redirect response {exc.code} has an invalid Location header"
                ) from join_error
            redirects += 1


def check_url(
    url: str,
    timeout: float,
    retries: int = 2,
    retry_delay: float = 0.5,
    *,
    resolver: Optional[Any] = None,
    open_request: Optional[Any] = None,
    max_redirects: int = 5,
) -> Tuple[str, str, str]:
    headers = {"User-Agent": "Awesome-CFM-link-checker/1.0 (+https://github.com/GREAT-ISAC/Awesome-Channel-Foundation-Models)"}
    last_detail = "no response"
    for attempt in range(retries + 1):
        for method in ("HEAD", "GET"):
            request = urllib.request.Request(url, headers=headers, method=method)
            if method == "GET":
                request.add_header("Range", "bytes=0-1023")
            try:
                with open_checked_request(
                    request,
                    timeout,
                    resolver=resolver,
                    open_request=open_request,
                    max_redirects=max_redirects,
                ) as response:
                    status = response.getcode()
                if 200 <= status < 400:
                    return url, "ok", str(status)
                last_detail = str(status)
            except UnsafeURL as exc:
                return url, "broken", f"unsafe URL: {exc}"
            except RedirectPolicyError as exc:
                last_detail = f"redirect error: {exc}"
                if method == "HEAD":
                    continue
                return url, "broken", last_detail
            except http.client.InvalidURL as exc:
                return url, "broken", f"invalid URL: {exc}"
            except urllib.error.HTTPError as exc:
                last_detail = str(exc.code)
                # Always try GET after a HEAD failure. Some otherwise healthy
                # project hosts reject or misroute HEAD requests.
                if method == "HEAD":
                    continue
                if exc.code in {401, 403, 429} or 500 <= exc.code < 600:
                    break
                return url, "broken", str(exc.code)
            except socket.gaierror as exc:
                last_detail = str(exc)
                if method == "HEAD":
                    continue
                if exc.errno in PERMANENT_DNS_ERRORS and attempt >= retries:
                    return url, "broken", f"DNS name not found: {last_detail}"
                break
            except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
                last_detail = str(exc.reason if hasattr(exc, "reason") else exc)
                if method == "HEAD":
                    continue
                break
        if attempt < retries and retry_delay:
            time.sleep(retry_delay * (2**attempt))
    return url, "indeterminate", last_detail


def check_links(
    records: Sequence[Mapping[str, Any]],
    workers: int,
    timeout: float,
    retries: int = 2,
    retry_delay: float = 0.5,
    report_path: Optional[Path] = None,
    max_indeterminate_rate: float = 0.5,
) -> Dict[str, Any]:
    if workers < 1:
        raise CatalogError("workers must be at least 1")
    if timeout <= 0:
        raise CatalogError("timeout must be positive")
    if retries < 0:
        raise CatalogError("retries cannot be negative")
    if retry_delay < 0:
        raise CatalogError("retry delay cannot be negative")
    if not 0 <= max_indeterminate_rate <= 1:
        raise CatalogError("max indeterminate rate must be between 0 and 1")
    url_owners = collect_url_owners(records)
    urls = sorted(url_owners)
    results = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {
            executor.submit(check_url, url, timeout, retries, retry_delay): url
            for url in urls
        }
        for future in concurrent.futures.as_completed(futures):
            url = futures[future]
            try:
                results.append(future.result())
            except Exception as exc:  # Keep the audit report complete on checker bugs.
                results.append((url, "checker-error", f"checker error: {exc}"))
    counts = Counter(status for _, status, _ in results)
    for url, status, detail in sorted(results):
        print(f"{status:13} {detail:20} {url}")
    print(
        f"Checked {len(urls)} URLs: {counts['ok']} ok, "
        f"{counts['indeterminate']} indeterminate, {counts['broken']} broken, "
        f"{counts['checker-error']} checker errors"
    )
    indeterminate_rate = counts["indeterminate"] / len(urls) if urls else 0.0
    report = {
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "summary": {
            "total": len(urls),
            "ok": counts["ok"],
            "indeterminate": counts["indeterminate"],
            "broken": counts["broken"],
            "checker_error": counts["checker-error"],
            "indeterminate_rate": round(indeterminate_rate, 4),
        },
        "results": [
            {
                "url": url,
                "status": status,
                "detail": detail,
                "owners": url_owners[url],
            }
            for url, status, detail in sorted(results)
        ],
    }
    if report_path:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report, indent=2) + "\n", encoding="utf-8")
        print(f"Wrote link audit report to {report_path}")
    failures = []
    if counts["checker-error"]:
        failures.append(f"{counts['checker-error']} internal checker error(s)")
    if counts["broken"]:
        failures.append(f"{counts['broken']} broken URL(s)")
    if indeterminate_rate > max_indeterminate_rate:
        failures.append(
            f"indeterminate rate {indeterminate_rate:.1%} exceeds {max_indeterminate_rate:.1%}"
        )
    if failures:
        raise CatalogError("Link audit failed: " + "; ".join(failures))
    return report


def parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser("validate", help="validate all YAML records and references")
    generate_parser = subparsers.add_parser("generate", help="render README and resource pages")
    generate_parser.add_argument("--check", action="store_true", help="fail if generated files differ")
    freshness_parser = subparsers.add_parser(
        "check-freshness",
        help="report stale verification dates without changing catalog data",
    )
    freshness_parser.add_argument("--max-age-days", type=int, default=MAX_VERIFICATION_AGE_DAYS)
    freshness_parser.add_argument("--report", type=Path, default=Path("freshness-report.json"))
    freshness_parser.add_argument(
        "--max-stale-rate",
        type=float,
        default=None,
        help="optionally fail when this stale-record fraction is exceeded",
    )
    links_parser = subparsers.add_parser("check-links", help="check catalog HTTP(S) links without modifying data")
    links_parser.add_argument("--workers", type=int, default=min(8, (os.cpu_count() or 2) * 2))
    links_parser.add_argument("--timeout", type=float, default=15.0)
    links_parser.add_argument("--retries", type=int, default=2)
    links_parser.add_argument("--retry-delay", type=float, default=0.5)
    links_parser.add_argument("--report", type=Path, default=Path("link-report.json"))
    links_parser.add_argument("--max-indeterminate-rate", type=float, default=0.5)
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
        elif args.command == "check-freshness":
            check_freshness(
                records,
                max_age_days=args.max_age_days,
                report_path=args.report,
                max_stale_rate=args.max_stale_rate,
            )
        elif args.command == "check-links":
            check_links(
                records,
                workers=args.workers,
                timeout=args.timeout,
                retries=args.retries,
                retry_delay=args.retry_delay,
                report_path=args.report,
                max_indeterminate_rate=args.max_indeterminate_rate,
            )
    except CatalogError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
