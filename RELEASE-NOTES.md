# Aletheia Athenaeum 0.1.0

An independent Python personal knowledge library with a native PySide6 Qt Widgets interface. No Electron or Node.js runtime is required.

Install Python 3.12+, create a virtual environment, then install the wheel with pip. Run aletheia-athenaeum. The source distribution includes installation instructions and tests. Keyword search works offline immediately; generation needs a compatible GGUF or Chat Completions API. Qwen remains an optional default download. Semantic hybrid search is optional via the semantic extra.

This initial edition includes archive inventory, cited search answers, document preparation, title editing and saved themes. Local inference, Qt and optional semantic library support depend on platform, hardware and selected model. Engine packages are pinned for Windows/Linux/macOS x64/ARM64; API mode requires no local engine.

The release contains a Python wheel and source distribution; these are not standalone operating-system installers. See README.md for setup and data locations. AGPL-3.0-only; upstream history and attribution retained.
