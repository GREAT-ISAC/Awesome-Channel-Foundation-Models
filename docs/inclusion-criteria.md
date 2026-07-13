# Catalog Inclusion Criteria

This policy defines what belongs in Awesome Channel Foundation Models and how resource claims are represented.

## Scope tiers

### Core CFM

Work centered on reusable pretrained channel representations or general-purpose channel models that transfer across channel-related scenarios or downstream tasks. CSI, CIR, channel tensors, pilot observations, and physically equivalent channel-domain inputs are included.

### Broader Wireless/Radio FM

Foundation-model work for radio signals, spectrum, sensing, localization, resource management, or multimodal wireless systems that contributes reusable methods or infrastructure to CFM research.

### Related Method

Backbone, adaptation, inference, retrieval, evaluation, or deployment work designed around wireless foundation models but not introducing a new pretrained CFM.

The tiers are descriptive, not a ranking.

## Eligible records

- Papers that fit one of the three scope tiers and have a stable paper or publisher page.
- Datasets used directly by a cataloged paper, or general-purpose measured/simulated channel data suitable for CFM training or evaluation.
- Pretrained models with an accessible checkpoint or model card. Source code without weights belongs under a paper's code artifact, not in the model catalog.
- Existing benchmark or evaluation projects that identify tasks, datasets, metrics, and a public project link.
- Channel, ray-tracing, link-level, or system simulation tools that can support CFM data workflows. Open-source tools are preferred; important commercial or restricted tools may be included with access and license conditions.

Benchmark v1 indexes existing evaluation projects. It does not claim that this repository supplies a unified benchmark runner.

## Normally excluded

- A task-specific model with no reusable pretraining, generalization, or direct foundation-model contribution.
- A search-result URL, URL shortener, unverified mirror, or generated/guessed link when a primary source is unavailable.
- A model entry that provides code but no checkpoint or model artifact.
- Duplicate records for the same resource.
- Marketing claims without technical documentation or a stable official page.

## Provenance

- `official` — maintained by the paper authors, their institution, the dataset/tool owner, or the official publisher/project.
- `community` — a third-party reproduction, conversion, mirror, wrapper, or benchmark integration.

Community resources must never be described as official. When both exist, list the official source first.

## Availability

- `available` — the linked resource is publicly reachable and usable under its stated terms.
- `restricted` — access requires payment, approval, credentials, or another material restriction.
- `not-released` — the resource is explicitly described but the authors state that it has not been released.
- `not-found` — maintainers found no qualifying release during the latest audit.
- `broken` — a previously valid link is persistently unavailable after manual confirmation.

HTTP `403`, `429`, timeouts, DNS errors, and transient server failures are uncertain observations, not automatic evidence that a link is broken.

## Verification requirements

Every record must include `last_verified`. Reviewers should:

1. open the paper or official project page;
2. confirm ownership and provenance;
3. confirm what is actually released—code, data, weights, evaluation, or a tool;
4. record access and license information without inference;
5. retain an explicit unavailable status when no reliable release is found.

Search engines and aggregation sites may be used for discovery, but catalog links should resolve to primary sources whenever possible.

## Corrections and removals

Metadata corrections and newly released artifacts are welcome at any time. A record may be removed if it falls outside scope, duplicates another record, or cannot be supported by a stable primary source. Broken links should first be checked for a relocated official source.
