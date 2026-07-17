# Contributing to Awesome Channel Foundation Models

Contributions may add a resource, correct metadata, or report a broken link. The easiest path is the [resource proposal Issue Form](https://github.com/GREAT-ISAC/Awesome-Channel-Foundation-Models/issues/new?template=resource-proposal.yml); proposing an item does not require editing YAML.

Please check the [inclusion criteria](docs/inclusion-criteria.md) and [taxonomy](docs/taxonomy.md), then provide primary sources such as the paper page, author repository, or official dataset/tool page. Do not guess URLs, licenses, or release status. Community implementations must be identified as community-maintained.

## Direct pull requests

If you prefer to edit the catalog directly:

- add or update one record in the matching `catalog/` directory;
- use a stable lowercase, hyphen-separated `id`;
- quote dates such as `"2026-07-17"`;
- for datasets, fill the structured `specifications` fields from official sources and leave unknown values null or empty;
- update `last_verified` and regenerate the public pages.

Run:

```bash
python3 scripts/catalog.py validate
python3 scripts/catalog.py generate
python3 scripts/catalog.py generate --check
python3 -m unittest discover -s tests -v
```

The papers, datasets, and simulation-tools pages are generated from YAML. Do not hand-edit those pages; update the catalog and regenerate them. The root `README.md` is maintained directly. Include the sources used to verify changed URLs in the pull request.

By contributing catalog metadata or documentation, you agree to license that contribution under [CC BY 4.0](LICENSE-CONTENT). Contributions to validation or generation code are licensed under [MIT](LICENSE-CODE). External linked resources retain their own licenses.
