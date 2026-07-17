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
- `autoregressive-generative` — next-token/sequence modeling, diffusion, or another explicitly generative objective.
- `contrastive-alignment` — contrastive learning or alignment across views, domains, or modalities.
- `predictive-latent` — JEPA-style or world-model prediction in a learned latent space.
- `supervised-multitask` — joint pretraining over multiple labeled tasks or task-conditioned objectives.
- `hybrid` — a method whose central design deliberately combines objective families.

Specific objective labels replace the former ambiguous “Other Pretraining Approaches” section. Papers may carry several objective tags when the method genuinely combines them.

## Scope

The `scope` field separates core channel foundation models from broader wireless/radio foundation models and related methods. See the [inclusion criteria](inclusion-criteria.md) for the decision boundary.

## Modality

Modalities identify model inputs or representations, for example CSI, CIR, IQ, spectrograms, pilot observations, delay–Doppler–angle tensors, environment data, point clouds, trajectories, or received symbols. New slugs should be reused consistently and should describe a data representation rather than a task.

## Downstream task

Tasks describe evaluated or explicitly targeted uses such as channel estimation, extrapolation, feedback, beam prediction, positioning, sensing, classification, detection, or resource optimization. Use the most specific existing slug that matches the paper; add a new slug only when needed.

## Resource display

The paper page shows qualifying code, pretrained-weight, benchmark, or simulation-tool links. Dataset relationships are presented on the dataset page instead of being repeated under papers. Missing-resource and verification states remain in YAML for maintenance and are not repeated in the public listing.
