# Aletheia Athenaeum

A native **PySide6 / Qt Widgets personal knowledge library**. An athenaeum is a place for reading and learning. The application includes the Librarian, Archivist, document browser and model settings as native widgets. It uses no Electron, WebEngine, browser, FastAPI server, Node.js or other Aletheia installation.

Derived from [Aletheia 0.2.0](https://github.com/AeMecha/Aletheia/tree/v0.2.0), with its Git history and AGPL-3.0-only license retained. The independent browser sibling is Aletheia Agora.

## Run on Windows

Download **[Aletheia-Athenaeum-0.1.2-windows-x64.exe](https://github.com/AeMecha/Aletheia-Athenaeum/releases/download/v0.1.2/Aletheia-Athenaeum-0.1.2-windows-x64.exe)** and double-click it. This standalone executable includes Python, PySide6 Qt Widgets and the keyword/semantic-search libraries. No Python installation, virtual environment, Electron or Node.js is required.

The executable is unsigned. Its accompanying licenses ZIP, source archive and SHA-256 checksums are on the [release page](https://github.com/AeMecha/Aletheia-Athenaeum/releases/tag/v0.1.2). Keep license notices with redistributed copies.

Your settings and archive still live in `%APPDATA%/AletheiaAthenaeum`, independently of the executable's location. Existing profiles are reused. Keyword search works immediately; semantic mode downloads verified BGE weights once. Local generation downloads its native engine on first use and needs a selected GGUF or the optional Qwen download. API connections work without a local generation engine.

## Run from Python

Download the [0.1.2 wheel and source archive](https://github.com/AeMecha/Aletheia-Athenaeum/releases/tag/v0.1.2), or install from this checkout as follows.

Requires Python 3.12+ and a platform supported by PySide6. Only PySide6 Essentials (including Qt Widgets) is installed; WebEngine and the full add-ons bundle are unnecessary. From this repository:

```sh
python -m venv .venv
# Linux: source .venv/bin/activate
# Windows PowerShell: .venv\Scripts\Activate.ps1
python -m pip install .
aletheia-athenaeum
```

`python -m aletheia_athenaeum --home /path/to/a/separate/profile` selects another data directory. Use a separate virtual environment for each sibling application.

Keyword search works immediately, offline, without NumPy, ONNX, a tokenizer or model weights. For a Python installation, semantic hybrid search is optional: install `python -m pip install '.[semantic]'`, then choose **Semantic hybrid** in Settings. The Windows executable already includes those libraries. The pinned BGE search model downloads once and is verified by SHA-256. Switching search modes rebuilds only the derived Python index, preserving original Markdown.

Choose a compatible instruction/chat GGUF, download the default Qwen, or configure a Chat Completions API. Local engines download on first use, selected for Windows, Linux or macOS and x64 or ARM64, with pinned official digests. A custom native llama-server executable path is also supported. Engine/library availability, OS versions, CPU/GPU support, memory and the selected model's architecture still determine whether local inference works. API mode needs no local inference engine. This does not claim support for every OS or CPU.

## Legacy CPU Compatibility (Linux)

Aletheia Athenaeum 0.1.0 was successfully installed and launched with the configuration below. The commands install the current 0.1.2 wheel using the same environment settings.

| Component | Tested configuration |
| --- | --- |
| Operating system | Ubuntu 26.04.1 LTS (Resolute) |
| Processor | Intel Pentium Dual-Core E6700 @ 3.20 GHz |
| Architecture | x86_64 |
| System Python | 3.14.4 |
| Working application Python | 3.13, managed through `uv` |
| Working Qt dependency | PySide6-Essentials 6.9.3 |

This processor lacks SSE4.1, SSE4.2, POPCNT, AVX and AVX2. Recent prebuilt PySide6/Qt libraries can contain instructions that older processors cannot execute, causing `SIGILL`, usually displayed as `Illegal instruction (core dumped)`. On this system, installing the application under Python 3.14 selected PySide6-Essentials 6.12.0 and crashed. Importing `PySide6.QtCore` independently also crashed, pointing to Qt's native libraries before application startup; the precise failing instruction was not identified.

Python 3.13 was needed because [PySide6-Essentials 6.9.3 requires Python below 3.14](https://pypi.org/project/PySide6-Essentials/6.9.3/). The configured Ubuntu repositories did not provide Python 3.12 or 3.13 on this installation. The workaround uses a separate interpreter and an explicit Qt version for this environment; the standard installation instructions above still apply to modern hardware.

These steps document one successful configuration, not a guarantee for every older x86-64 processor. Local inference engines and optional semantic search libraries have their own CPU requirements; successfully launching Qt does not establish their compatibility.

### 1. Bootstrap uv

Run the following commands in Bash from the **Aletheia-Athenaeum repository root**, the directory containing `pyproject.toml`. For a fresh checkout:

```bash
git clone https://github.com/AeMecha/Aletheia-Athenaeum.git
cd Aletheia-Athenaeum
```

If you do not already have a `.venv`, create a bootstrap environment with the system Python:

```bash
python3 -m venv .venv
```

If Ubuntu reports that `venv` or `ensurepip` is unavailable, install `python3-venv` with `sudo apt install python3-venv`, then retry. With either the existing Python 3.14 environment or the new bootstrap environment:

```bash
source .venv/bin/activate
python -m pip install uv
deactivate
```

This installs `uv` inside `.venv`; the next step invokes that executable directly. See the [uv installation documentation](https://docs.astral.sh/uv/getting-started/installation/#pypi).

### 2. Create the Python 3.13 environment

```bash
.venv/bin/uv venv --python 3.13 --seed .venv313
source .venv313/bin/activate
python --version
```

Confirm that the output is `Python 3.13.x`. `uv` locates a suitable interpreter or downloads its own managed Python installation if necessary, then creates `.venv313`; `--seed` supplies pip. This leaves Ubuntu's system Python and `/usr/bin/python3` intact. No system interpreter replacement or apt repository change is needed. See [uv's Python version management](https://docs.astral.sh/uv/concepts/python-versions/#requesting-a-version).

### 3. Install and verify the compatible Qt version

With `.venv313` active:

```bash
python -m pip install 'PySide6-Essentials==6.9.3'
python -c "from PySide6.QtCore import QCoreApplication; print('QtCore OK')"
```

Expected output from the import check:

```text
QtCore OK
```

### 4. Install and launch Athenaeum

Use the wheel at `dist/aletheia_athenaeum-0.1.2-py3-none-any.whl`, relative to the repository root. If it is not already there, download it from the [0.1.2 release](https://github.com/AeMecha/Aletheia-Athenaeum/releases/tag/v0.1.2):

```bash
mkdir -p dist
curl -fL --output dist/aletheia_athenaeum-0.1.2-py3-none-any.whl \
  https://github.com/AeMecha/Aletheia-Athenaeum/releases/download/v0.1.2/aletheia_athenaeum-0.1.2-py3-none-any.whl
```

Keep `.venv313` active and install without requesting a dependency upgrade:

```bash
python -m pip install ./dist/aletheia_athenaeum-0.1.2-py3-none-any.whl
python -m pip check
aletheia-athenaeum
```

`pip check` should report `No broken requirements found.` The installed PySide6-Essentials 6.9.3 satisfies this application's dependency range.

### 5. Subsequent launches

From the same repository root:

```bash
source .venv313/bin/activate
aletheia-athenaeum
```

**Keep PySide6-Essentials pinned to 6.9.3 in this legacy environment.** Upgrading it may reintroduce the illegal-instruction crash. When updating the application, include `'PySide6-Essentials==6.9.3'` in the pip install command so the resolver retains this version or reports a dependency conflict. Recheck the Qt import before launching after dependency changes.

### Troubleshooting: Illegal instruction (core dumped)

First activate `.venv313` and confirm which Python and Qt packages are in use:

```bash
source .venv313/bin/activate
python --version
python -m pip show PySide6-Essentials shiboken6
python -c "from PySide6.QtCore import QCoreApplication; print('QtCore OK')"
```

- If Python is still 3.14 or PySide6-Essentials is newer than 6.9.3, follow the environment and Qt installation steps above. Downgrading Qt to 6.9.3 inside Python 3.14 cannot resolve its Python version requirement.
- If the isolated QtCore import also crashes, the failure occurs without Athenaeum's application code. Check the machine's CPU flags with `lscpu | grep -E 'Architecture|Model name|Flags'`; another native build may be needed if the tested workaround also fails on that processor.
- If QtCore prints `QtCore OK` but Athenaeum crashes, the QtCore check alone does not identify the remaining cause. Capture the terminal output and, where available, the core dump backtrace, including which native library failed. A crash during local model loading or optional semantic search needs separate investigation.

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

### Build the Windows executable

Build on Windows x64 in a clean Python environment (release CI uses Python 3.13):

```powershell
python -m pip install ".[semantic]" PyInstaller==6.22.3
python packaging/build_windows.py
```

This creates the executable and a dependency-license ZIP in `dist/`. [PyInstaller](https://pyinstaller.org/en/stable/operating-mode.html) bundles the interpreter and native libraries; model weights and user profiles are excluded. The release workflow runs `packaging/verify_windows.py` against the actual executable with a disposable profile and verified search weights before publishing. Python wheels remain available for other platforms and the legacy Linux installation described above.
