# Aletheia Athenaeum

A native **PySide6 / Qt Widgets personal knowledge library**. An athenaeum is a place for reading and learning. The application includes the Librarian, Archivist, document browser and model settings as native widgets. It uses no Electron, WebEngine, browser, FastAPI server, Node.js or other Aletheia installation.

Derived from [Aletheia 0.2.0](https://github.com/AeMecha/Aletheia/tree/v0.2.0), with its Git history and AGPL-3.0-only license retained. The independent browser sibling is Aletheia Agora.

## Run

Requires Python 3.12+ and a platform supported by PySide6. Only PySide6 Essentials (including Qt Widgets) is installed; WebEngine and the full add-ons bundle are unnecessary. From this repository:

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
aletheia-athenaeum
```

`python -m aletheia_athenaeum --home /path/to/a/separate/profile` selects another data directory. Use a separate virtual environment for each sibling application.

Keyword search works immediately, offline, without NumPy, ONNX, a tokenizer or model weights. Semantic hybrid search is optional: install `python -m pip install '.[semantic]'`, then choose **Semantic hybrid** in Settings. The pinned BGE search model downloads once and is verified by SHA-256. Switching search modes rebuilds only the derived Python index, preserving original Markdown.

Choose a compatible instruction/chat GGUF, download the default Qwen, or configure a Chat Completions API. Local engines download on first use, selected for Windows, Linux or macOS and x64 or ARM64, with pinned official digests. A custom native llama-server executable path is also supported. Engine/library availability, OS versions, CPU/GPU support, memory and the selected model's architecture still determine whether local inference works. API mode needs no local inference engine. This does not claim support for every OS or CPU.

## Features

- Librarian search and cited answers; exact archive overview without a generation model.
- Archivist metadata preparation with the complete original source retained for review and separate saving.
- Markdown import by files or folder, title filtering, original document view, revision-checked title edits and Markdown export.
- Local GGUFs, a verified/resumable default Qwen download, configurable API endpoints/model IDs, model discovery/manual IDs and LM Studio/Ollama presets.
- Saved light/dark themes, context size, response budget, acceleration and schema/JSON/prompt compatibility settings.
- A background asyncio/QThread service keeps native widgets responsive. Stop cancels generation; shutdown stops only the owned local model process.

Models must follow instructions and produce valid structured JSON. Tool calling is not required. All response modes retain completion, metadata and citation validation. APIs using a different native protocol require a Chat Completions-compatible endpoint or gateway. Remote APIs receive the current input and retrieved passages; local generation/search stay on the computer. Provider keys stay in the local settings file and are never sent back to the GUI form. Blank fields retain the key for the same endpoint; the clear checkbox removes it.

Default data lives in `%APPDATA%/AletheiaAthenaeum` on Windows, `$XDG_CONFIG_HOME/AletheiaAthenaeum` (normally `~/.config/AletheiaAthenaeum`) on Linux, and `~/.config/AletheiaAthenaeum` on macOS. `ALETHEIA_HOME` overrides it; `ALETHEIA_RESOURCES` selects an existing asset cache. Back up the profile and externally selected model files.

`knowledge/` Markdown is authoritative; `archive-python.sqlite3` is derived. Import copies files and preserves safe Metadata IDs. The original Electron application's data is not opened automatically. Do not use one profile simultaneously in different applications/processes.

## Development

```sh
python -m pip install -e .
python -m unittest discover -s tests -v
python -m build
```

The repository includes its own Python archive/model core. No sibling repository or server is required. Native UI tests can use `QT_QPA_PLATFORM=offscreen` and operate on isolated synthetic profiles. See `ARCHITECTURE.md`, `NOTICE` and `THIRD-PARTY-NOTICES.md`.
