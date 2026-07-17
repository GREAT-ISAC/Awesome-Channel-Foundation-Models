# Research Taxonomy

The catalog uses non-exclusive dimensions in its source records, while the public paper page places each paper once in a stage-first hierarchy.

## Research stage

- `survey` — surveys, perspectives, definitions, and research agendas.
- `backbone` — reusable architectures, neural operators, positional encodings, or representation backbones.
- `pretraining` — work that learns transferable representations or general-purpose wireless models.
- `adaptation` — fine-tuning, in-context learning, retrieval, transfer, or feature adaptation.
- `inference-deployment` — early exit, compression, serving, latency, energy, or deployment methods.

This dimension preserves the original Backbone, Pretraining, Adaptation, and Inference organization. It is no longer a mutually exclusive folder hierarchy.

## Pretraining objective

- `masked-reconstruction` — masked autoencoding, denoising, or reconstruction from incomplete observations.
- `direct-forecasting` — direct prediction of future channel states or other future wireless observations without a masked-token formulation.
- `autoregressive-generative` — next-token/sequence modeling, diffusion, or another explicitly generative objective.
- `contrastive-alignment` — contrastive learning or alignment across views, domains, or modalities.
- `predictive-latent` — JEPA-style or world-model prediction in a learned latent space.
- `task-supervised` — direct optimization of one or more labeled downstream-task losses during pretraining.

Specific objective labels replace the former ambiguous “Other Pretraining Approaches” section. Papers carry every concrete objective that is central to the method. A hybrid method is represented by multiple objective labels instead of a generic `hybrid` label, and `primary_objective` controls its single public placement.

## Training signal

The `training_signals` field records where the optimization targets come from, independently of the objective family:

- `self-supervised` — targets are derived from the input data itself, including masks, future observations, augmentations, or alternate views.
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

The `scope` field separates core channel foundation models from broader wireless/radio foundation models and related methods. See the [inclusion criteria](inclusion-criteria.md) for the decision boundary.

## Modality

Modalities identify model inputs or representations, for example CSI, CIR, IQ, spectrograms, pilot observations, delay–Doppler–angle tensors, environment data, point clouds, trajectories, or received symbols. New slugs should be reused consistently and should describe a data representation rather than a task.

## Downstream task

Tasks describe evaluated or explicitly targeted uses such as channel estimation, extrapolation, feedback, beam prediction, positioning, sensing, classification, detection, or resource optimization. Use the most specific existing slug that matches the paper; add a new slug only when needed.

## Resource display

The paper page shows qualifying code, pretrained-weight, benchmark, or simulation-tool links. Dataset relationships are presented on the dataset page instead of being repeated under papers. Missing-resource and verification states remain in YAML for maintenance and are not repeated in the public listing.
