# Architecture

## Independent distribution

This repository includes its own Python app and archive/model core. It needs neither original Aletheia nor its sibling. There is no Electron, Node.js, SillyTavern, Transformers.js or Sharp runtime dependency. Use separate environments and profiles. The sibling includes its own core copy; port core changes with their tests.

## Interface boundary

Native Qt Widgets live in window.py. A QThread in backend.py owns the asyncio Service and emits snapshots/results through Qt signals. Widgets are touched only on the GUI thread. Downloads and inference remain cancellable. Closing cancels jobs, closes the database and stops only an owned engine. No HTTP server, browser or WebEngine starts.

## Archive and retrieval

config.py validates preferences and saves JSON atomically. A profile lock prevents concurrent processes. archive.py treats knowledge/ Markdown as authoritative; SQLite FTS5 is derived. Imports preserve valid IDs, duplicate IDs fail closed, and SHA-256 revisions protect title edits from overwriting external changes. Periodic scans discover changed files.

Keyword mode uses Python/SQLite with no native ML imports. Optional embeddings.py loads text-only BGE ONNX, applies masked mean pooling and normalizes 384-dimensional vectors. Hybrid search merges lexical and vector passage results. Index signatures distinguish search modes and rebuild derived rows while preserving originals. Source spans use exact Unicode offsets. The Python database is separate from the original JavaScript index.

Inventory questions use complete counts/titles without inference. Other questions retrieve selected passages and pass only bounded evidence to the model. A selected search does not prove archive-wide absence.

## Model ownership and validation

model.py owns a loopback llama-server child or connects to an external Chat Completions API. External servers are never stopped. Local files must be GGUF v2/v3 with an architecture and chat template supported by the engine. assets.py verifies pinned sizes/digests, resumes weight downloads, selects Windows/Linux/macOS x64/ARM64 engines and contains extracted paths. A custom executable supports separately built native engines. Available packages do not guarantee every CPU, GPU or OS version.

Default Qwen is optional. Generic models use schema/JSON/prompt negotiation. protocol.py validates complete responses, metadata, citations and simulated dialogue/tool activity in every mode. Archivist generates metadata, retaining full source verbatim in a review draft; saving is separate. Remote APIs receive input and retrieved passages.

## Verification

The Windows release additionally builds a native one-file PyInstaller executable. It bundles Qt Essentials and the text-only semantic libraries, with no Electron or browser engine. Package data is resolved relative to module paths inside the bundle; user profiles remain outside the temporary extraction directory. The standalone verification command uses real widgets, a disposable profile, synthetic API replies and separately verified BGE weights. Publication waits for both Python and Windows builds, then checks upload sizes and hashes before making the release public. Build scripts and complete license notices accompany the release.

Run python -m unittest discover -s tests -v and python -m build. Tests use disposable profiles and synthetic model responses. Native acceptance tests drive real widgets, signals and the worker offscreen. CI covers Windows, Linux, macOS and Linux ARM64. Local inference and optional semantic dependencies need platform-specific validation.
