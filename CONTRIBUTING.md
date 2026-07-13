# Contributing to Awesome Channel Foundation Models

Thank you for helping maintain a reliable community catalog. Contributions may add a paper or resource, correct metadata, update availability, or report a broken link.

## Before proposing an entry

Read the [inclusion criteria](docs/inclusion-criteria.md) and [taxonomy](docs/taxonomy.md). A record must have a clear relationship to channel foundation models, broader wireless/radio foundation models, or a directly relevant method. Inclusion documents relevance and availability; it is not an endorsement or a paper-quality ranking.

Prefer primary sources:

- the paper page, DOI page, or author project page;
- an author or institution repository;
- an official dataset, model, benchmark, or product page.

Community implementations are welcome when useful, but they must use `provenance: community`. Never present a third-party reproduction as the official implementation.

## Catalog workflow

Each item is maintained in one YAML file under the matching `catalog/` directory:

```text
catalog/
├── papers/
├── datasets/
├── models/
├── benchmarks/
└── simulation-tools/
```

Use a stable lowercase, hyphen-separated ID for both the filename and `id`. Quote ISO dates such as `"2026-07-13"` so YAML does not convert them to date objects. Reuse an existing resource record through `ref` instead of duplicating its URL in multiple paper records.

For an artifact that could not be located, use `not-found`. Use `not-released` only when the authors explicitly state that it is unavailable. Do not guess URLs, licenses, metrics, or release status.

## Local checks

Install the lightweight validation dependencies and run:

```bash
python3 -m pip install -r requirements.txt
python3 scripts/catalog.py validate
python3 scripts/catalog.py generate
python3 scripts/catalog.py generate --check
python3 -m unittest discover -s tests -v
```

The README and the five resource pages are generated. Edit YAML or `templates/README.md`, then regenerate; do not hand-edit generated files.

External link checks are intentionally separate because network responses are not deterministic:

```bash
python3 scripts/catalog.py check-links
```

HTTP `403` and `429` responses and temporary network failures are reported as indeterminate. They are not grounds for automatically changing an entry to `broken`.

## Pull requests

Keep a pull request focused and complete the repository PR checklist. Include the source used to verify every new or changed URL and set `last_verified` to the actual check date. Generated files must be committed with the corresponding YAML change.

By contributing catalog metadata or documentation, you agree to license that contribution under [CC BY 4.0](LICENSE-CONTENT). Contributions to validation or generation code are licensed under [MIT](LICENSE-CODE). External linked resources retain their own licenses.
