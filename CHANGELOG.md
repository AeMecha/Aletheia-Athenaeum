# Changelog

## 0.1.2

- Add a standalone Windows x64 executable bundling Python, Qt Essentials and semantic-search libraries; no separate Python installation is required.
- Retain compatible GGUF/API connections and the optional default Qwen download. Model weights and inference engines remain separately downloaded or selected.
- Verify the actual executable's native GUI, archive inventory, title edits, saved theme, document preparation, cited answers and real BGE ONNX inference before release.
- Publish executable and dependency license notices alongside the Python wheel/source, with complete SHA-256 checksums after both native and Python builds pass.

## 0.1.1

- Route ordinary library existence questions and collection/empty-library phrasing to complete archive counts and saved titles without a generation model.
- Preserve topic and date filters as document searches.
- Enable chat inventory requests before an AI connection is configured and cover them through real Qt widget tests.
- Document the verified legacy Linux workaround using uv-managed Python 3.13 and PySide6-Essentials 6.9.3, without changing global dependency constraints.

## 0.1.0

Initial independent Python edition derived from Aletheia 0.2.0.

- Native PySide6 / Qt Widgets interface with a background asyncio worker.
- Portable offline keyword search and optional BGE semantic hybrid search.
- Librarian cited answers, complete archive inventory, Archivist preparation, original source retention and separate saving.
- Markdown import/export, revision-checked title editing, saved themes.
- Configurable GGUF and Chat Completions models, optional default Qwen download, model discovery, context/output settings and validated response negotiation.
- Pinned native engines for Windows/Linux/macOS x64/ARM64 and custom engine paths.
- Independent packaging, license notices, documentation and multi-platform CI.
