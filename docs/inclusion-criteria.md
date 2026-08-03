# Catalog Inclusion Criteria

This policy defines what belongs in Awesome Channel Foundation Models and how resource claims are represented.

## Scope

### CFM Ecosystem

This catalog uses one CFM-ecosystem scope without publicly ranking papers as “core” or “broader.” A paper qualifies when it learns a reusable representation or prior of wireless channels, propagation, or channel-bearing observations; transfers such a representation across channel-grounded tasks or environments; or directly studies the adaptation, evaluation, or deployment of a CFM. Eligible observations include explicit CSI/CIR, pilots, radio maps, channel statistics, received signals, and environmental context used to infer or generate channels.

IQ, spectrum, traffic, topology, or environmental data are not sufficient by themselves. The model must learn or reuse propagation-aware structure rather than treating a channel value as one ordinary feature in a generic signal, network-forecasting, or control model.

### Related Method

Backbone, adaptation, inference, retrieval, evaluation, or deployment work designed around wireless foundation models but not introducing a new pretrained CFM.

The distinction between the CFM ecosystem and related methods is descriptive, not a ranking.

## Eligible records

- CFM-ecosystem and directly related-method papers with a stable paper or publisher page.
- Datasets used directly by a cataloged paper, or general-purpose measured/simulated channel data suitable for CFM training or evaluation.
- Pretrained models with an accessible checkpoint or model card. Source code without weights belongs under a paper's code artifact, not in the model catalog.
- Existing evaluation projects that identify tasks, datasets, metrics, and a public protocol link. Their metadata is stored in the corresponding dataset record's `evaluation` block; the catalog does not maintain standalone benchmark records.
- Channel, ray-tracing, link-level, or system simulation tools that can support CFM data workflows. Open-source tools are preferred; important commercial or restricted tools may be included with access and license conditions.

The catalog indexes existing dataset-integrated evaluations. It does not claim that this repository supplies a unified benchmark runner.

A publication whose primary contribution is a benchmark dataset or evaluation protocol is represented by the dataset record. Its paper or protocol link belongs in that record's structured `evaluation` metadata and is not duplicated as a paper-page entry.

Dataset records separate release and coverage facts from prose. Each record includes version, scale, download size, frequency bands, scenarios, and antenna configurations. Use `null` or an empty list when an official source does not state a value; do not infer missing specifications.

## Normally excluded

- A task-specific model with no reusable pretraining, generalization, or direct foundation-model contribution.
- A general mobile-network, electromagnetic-signal, or spectrum model whose objectives and evaluations do not learn, infer, generate, or reuse channel/propagation structure.
- A receiver or resource-control model that merely consumes CSI as a condition, unless it is explicitly cataloged as an application of a foundation model and demonstrates cross-configuration or cross-environment generalization.
- A search-result URL, URL shortener, unverified mirror, or generated/guessed link when a primary source is unavailable.
- A model entry that provides code but no checkpoint or model artifact.
- Duplicate records for the same resource.
- Marketing claims without technical documentation or a stable official page.

## Provenance

- `official` — maintained by the paper authors, their institution, the dataset/tool owner, or the official publisher/project.
- `community` — a third-party reproduction, conversion, mirror, wrapper, or benchmark integration.

Community resources must never be described as official. When both exist, list the official source first.

Each direct resource URL has one canonical role in the catalog. Papers should reference an existing dataset, model, or simulation-tool record by `ref` instead of repeating that resource's URL. An evaluation protocol belongs in the corresponding dataset record's `evaluation` block rather than in a standalone benchmark record. A repository that only contains ordinary training or evaluation code remains a paper code artifact rather than becoming a second model or dataset record.

## Availability

- `available` — the linked resource is publicly reachable and usable under its stated terms.
- `restricted` — access requires payment, approval, credentials, or another material restriction.
- `not-released` — the resource is explicitly described but the authors state that it has not been released.
- `not-found` — maintainers found no qualifying release during the latest audit.
- `broken` — a previously valid link is persistently unavailable after manual confirmation.

HTTP `401`, `403`, `429`, timeouts, DNS errors, and transient server failures are uncertain observations, not automatic evidence that a link is broken.

The automated audit retries transient failures, falls back from `HEAD` to a ranged `GET`, and writes a machine-readable report. Each result identifies every owning YAML record and field together with declared provenance and availability. Explicit Markdown links in resource descriptions and paper summaries, abstracts, and notes are also checked; because those prose links do not declare resource metadata, the report marks their provenance and availability as `unspecified`. Before every request and redirect, the checker rejects userinfo and resolves the destination to ensure that every returned address is publicly routable. This request-time guard mitigates server-side request forgery but does not claim transport-level DNS pinning. A high proportion of indeterminate results fails the scheduled audit so that a network-wide outage or blocked runner cannot be mistaken for a healthy catalog. It never rewrites catalog status automatically.

## Verification requirements

Every record must include `last_verified`. Reviewers should:

1. open the paper or official project page;
2. confirm ownership and provenance;
3. confirm what is actually released—code, data, weights, evaluation, or a tool;
4. record access and license information without inference;
5. retain an explicit unavailable status when no reliable release is found.

Deterministic validation checks that every verification date is present and well formed. The separate weekly freshness audit reports future-dated records and entries older than 180 days without changing catalog data or making an unchanged commit fail ordinary validation.

Search engines and aggregation sites may be used for discovery, but catalog links should resolve to primary sources whenever possible.

## Corrections and removals

Metadata corrections and newly released artifacts are welcome at any time. A record may be removed if it falls outside scope, duplicates another record, or cannot be supported by a stable primary source. Broken links should first be checked for a relocated official source.
