# Aletheia Athenaeum 0.1.2

This release adds a standalone native Windows x64 executable. Download Aletheia-Athenaeum-0.1.2-windows-x64.exe and double-click it; Python, Qt Essentials and the semantic-search libraries are included. No Python installation, virtual environment, Electron, WebEngine or Node.js is required. The executable is unsigned.

- Retains the library inventory fix, original Markdown, title editing, saved themes, document preparation and validated source answers.
- Compatible local GGUF and Chat Completions API models remain supported; Qwen is an optional default download. Model weights and native generation engines are obtained separately during setup. Keyword search is available immediately; semantic mode downloads the verified BGE weights once.
- The Windows executable is tested as an actual frozen GUI before publication, including archive operations, draft preparation, cited answers and real BGE ONNX inference.
- Existing data remains in the same AletheiaAthenaeum profile. License notices accompany the executable and are embedded inside it.

The Python wheel and source archive remain available for Linux/macOS, Python installations and rebuilding. For the documented older Linux environment, retain Python 3.13 and the explicit Qt pin:

```bash
source .venv313/bin/activate
python -m pip install --upgrade ./aletheia_athenaeum-0.1.2-py3-none-any.whl 'PySide6-Essentials==6.9.3'
python -m pip check
aletheia-athenaeum
```

Adjust the wheel path to its download location. The legacy workaround remains one tested configuration; the standalone Windows binary does not change Linux CPU support or global Python dependency constraints.

Release files: standalone Windows x64 EXE, dependency licenses ZIP, Python wheel, source archive and SHA256SUMS.txt. The source includes build and verification scripts. Original Aletheia covered material retains Adeptus Telvannus’s custom license; see LICENSING.md and ATTRIBUTION.md. The full contribution/dependency license texts are retained.

Original project: [Aletheia](https://github.com/AdeptTel1/Aletheia) by [Adeptus Telvannus / AdeptTel1](https://github.com/AdeptTel1). Original custom terms and material changes are documented in LICENSES/, LICENSING.md and ATTRIBUTION.md.
