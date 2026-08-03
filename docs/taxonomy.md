# Research Taxonomy

The catalog uses non-exclusive dimensions in its source records, while the public paper page places each paper once in a stage-first hierarchy.

## Research stage

- `survey` — surveys, perspectives, definitions, and research agendas.
- `backbone` — reusable architectures, neural operators, positional encodings, or representation backbones.
- `pretraining` — work that learns transferable representations or general-purpose wireless models.
- `application` — systems that apply a foundation model to a concrete wireless pipeline without making adaptation itself the primary contribution.
- `adaptation` — fine-tuning, in-context learning, retrieval, transfer, or feature adaptation.
- `inference-deployment` — early exit, compression, serving, latency, energy, or deployment methods.

This dimension preserves the original Backbone, Pretraining, Adaptation, and Inference organization while accommodating application-oriented systems. On the public page, applications and adaptation methods share one section to avoid a sparse extra category. A paper may carry multiple stages: the first value in `stages` is its primary public placement, while the remaining values preserve cross-cutting contributions without duplicating the entry. When pretraining is a secondary stage, the public entry shows a compact profile of its concrete objectives, training signals, and task regime.

## Pretraining objective

- `masked-reconstruction` — masked autoencoding, denoising, or reconstruction from incomplete observations.
- `predictive-generative` — future-value prediction, next-token/sequence modeling, diffusion, or another predictive or generative objective.
- `contrastive-alignment` — contrastive learning or alignment across views, domains, or modalities.
- `predictive-latent` — JEPA-style or world-model prediction in a learned latent space.
- `direct-optimization` — label-free optimization of a differentiable communication objective, such as sum rate, energy, or another physics/system utility.
- `task-supervised` — direct optimization of one or more labeled downstream-task losses during pretraining.

Specific objective labels replace the former ambiguous “Other Pretraining Approaches” section. Papers carry every concrete objective that is central to the method. A hybrid method is represented by multiple objective labels instead of a generic `hybrid` label, and `primary_objective` controls its single public placement.

Only objectives optimized during pretraining belong in this dimension. A loss introduced solely for downstream fine-tuning or adaptation remains an adaptation detail and does not add a pretraining-objective label.

For readability, papers that jointly optimize reconstruction and contrastive objectives are automatically grouped under **Reconstruction + Contrastive Learning** on the public paper page. This is a presentation group rather than an additional YAML objective; the source record retains both concrete objective labels.

## Training signal

The `training_signals` field records where the optimization targets come from, independently of the objective family:

- `self-supervised` — targets or losses are derived without human/task annotations, including masks, future observations, alternate views, or differentiable physical/system utilities.
- `supervised` — targets use task annotations or explicitly labeled outputs.
- `weakly-supervised` — targets use incomplete, noisy, indirect, or automatically derived labels.

Papers may use more than one signal. Non-pretraining papers use an empty list.

## Task regime

The `task_regime` field describes how tasks are organized during pretraining rather than how many downstream evaluations appear in the paper:

- `single-task` — pretraining directly optimizes one task.
- `multitask` — several tasks are optimized jointly.
- `task-conditioned` — a prompt, task token, or equivalent condition selects the requested task.
- `not-specified` — the available paper description does not support a more precise classification.
- `not-applicable` — the record is not a pretraining paper.

## Scope

The catalog intentionally does not separate “core CFM” from “broader wireless/radio FM.” The `scope` field only distinguishes the CFM ecosystem from directly related backbone, adaptation, or deployment methods. Benchmark papers and evaluation protocols are maintained as structured `evaluation` metadata on the corresponding dataset record rather than as standalone benchmark records or duplicate paper-page entries. See the [inclusion criteria](inclusion-criteria.md) for the decision boundary.

## Modality

Modalities identify model inputs or representations, for example CSI, WiFi CSI, 5G CSI, CIR, channel statistics, IQ, spectrograms, pilot observations, delay–Doppler–angle tensors, environment data, point clouds, trajectories, or received symbols. Use protocol-specific labels such as `wifi-csi` or `5g-csi` when the source is explicit, and retain the broader `csi` label for simulated, protocol-agnostic, or unspecified CSI. New slugs should be reused consistently and should describe a data representation rather than a task.

## Downstream task

Tasks describe evaluated or explicitly targeted uses such as channel estimation, extrapolation, feedback, beam prediction, positioning, sensing, classification, detection, or resource optimization. Use the most specific existing slug that matches the paper; add a new slug only when needed.

## Resource display

The paper page shows qualifying code, paper-linked pretrained checkpoints, and simulation-tool links. Dataset relationships and structured evaluation protocols are presented only on the dataset page instead of being repeated under papers. Missing-resource and verification states remain in YAML for maintenance and are not repeated in the public listing.
