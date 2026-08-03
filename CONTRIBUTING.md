# Contributing to Awesome Channel Foundation Models

Contributions may add a resource, correct metadata, or report a broken link. You can open a [GitHub issue](https://github.com/GREAT-ISAC/Awesome-Channel-Foundation-Models/issues/new) without editing YAML, or submit a direct pull request.

Please check the [inclusion criteria](docs/inclusion-criteria.md) and [taxonomy](docs/taxonomy.md), then provide primary sources such as the paper page, author repository, or official dataset/tool page. Do not guess URLs, licenses, or release status. Community implementations must be identified as community-maintained.

## Direct pull requests

If you prefer to edit the catalog directly:

- add or update one record in the matching `catalog/` directory;
- use a stable lowercase, hyphen-separated `id`;
- use an author-defined model, method, framework, or acronym for `short_name`; otherwise use the first author's initial and family name followed by `et al.`;
- quote dates such as `"2026-07-17"`;
- for datasets, fill the structured `specifications` fields from official sources and leave unknown values null or empty; when an evaluation exists, keep its name, protocol link, and metrics in the same dataset record's `evaluation` block rather than creating a benchmark record;
- update `last_verified` and regenerate the public pages;
- keep verifiable resource URLs in structured link or artifact fields whenever possible. Explicit Markdown links in resource descriptions and paper summaries, abstracts, and notes are also audited, but their provenance and availability appear as unspecified because prose fields do not declare that metadata.

Run:

```bash
python3 scripts/catalog.py validate
python3 scripts/catalog.py generate
python3 scripts/catalog.py generate --check
python3 -m unittest discover -s tests -v
```

Maintainers can review verification age separately with `python3 scripts/catalog.py check-freshness`; this audit writes a report but does not make deterministic validation depend on the current date.

The papers, datasets, and simulation-tools pages are generated from YAML. Do not hand-edit those pages; update the catalog and regenerate them. The root `README.md` is maintained directly. Include the sources used to verify changed URLs in the pull request.

By contributing catalog metadata or documentation, you agree to license that contribution under [CC BY 4.0](LICENSE-CONTENT). Contributions to validation or generation code are licensed under [MIT](LICENSE-CODE). External linked resources retain their own licenses.
