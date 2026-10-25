# Origins and material changes

**Aletheia Athenaeum** is an independently maintained derivative of **[Aletheia](https://github.com/AdeptTel1/Aletheia)**, created by **[Adeptus Telvannus / AdeptTel1](https://github.com/AdeptTel1)**. The original project introduced the Archivist → Binder → Librarian workflow and the original prompts/ingestion scripts used in this project. This repository is not the upstream Aletheia release.

Copyright © 2026 Adeptus Telvannus. All rights reserved.

The original author's [custom license](LICENSES/LicenseRef-AdeptTel1-Aletheia.txt) is included verbatim. It was obtained from [LICENSE.txt at commit 618e5881e802](https://github.com/AdeptTel1/Aletheia/blob/618e5881e802f34fac923d460728c645f27431c0/LICENSE.txt) and matches the license supplied in the original [NewRelease source bundles](https://github.com/AdeptTel1/Aletheia/releases/tag/NewRelease). See [LICENSING.md](LICENSING.md) for scope and [UPSTREAM-PROVENANCE.json](UPSTREAM-PROVENANCE.json) for hashes and source paths.

## Retained and adapted material

- `src/aletheia_core/data/prompts/librarian.md`: original Librarian prompt body, with a provenance/license header added. Line endings may be normalized; the original instruction text is retained.
- `src/aletheia_core/data/prompts/archivist.md`: adaptation of the original Archivist role and preservation workflow. The standalone implementation requests bounded JSON metadata and retains the full input in code, rather than having the model reproduce a complete Markdown document.
- `src/aletheia_core/archive.py`: archive persistence implementation informed by the Binder workflow, including durable Markdown, title-derived IDs and creation/modification metadata. The original Binder code and workflow are credited to the upstream author; this implementation has substantial storage, indexing and validation changes.

## Changes in this derivative

AeMecha's derivative adds independent Python archive/model core, native PySide6 Qt Widgets interface, background worker, portable keyword/optional hybrid search and standalone Windows packaging. Retrieval and generated output are validated by the application; archive inventory is computed from the actual index. These changes are not represented as work by the upstream author.

The Python variants were ported from the independently developed desktop implementation, now named [Aletheia Scriptorium](https://github.com/AeMecha/Aletheia-Scriptorium). That fork lineage does not replace credit to the original AdeptTel1/Aletheia project. SillyTavern is a separate optional integration/framework, not the author of the original Aletheia prompts or Binder.
