# Aletheia Athenaeum 0.1.1

This patch fixes ordinary library inventory questions in the independent native PySide6 Qt Widgets application and adds verified legacy Linux installation guidance.

- "Do I have anything in the library?" and "Can you check if I have anything in the collection?" now use complete archive counts and real saved titles with source links.
- Empty-library checks and conversational phrasing work without a generation model, including when typed into chat. Actual Qt widget tests cover this workflow.
- Questions about specific topics or dates remain document searches.
- README instructions document the successful 0.1.0 installation on an older Pentium E6700 using uv-managed Python 3.13 and PySide6-Essentials 6.9.3. The instructions now point to the 0.1.1 wheel; native dependency constraints are unchanged.

Requires Python 3.12+ and a platform supported by PySide6 Essentials. Create a separate virtual environment, install `aletheia_athenaeum-0.1.1-py3-none-any.whl` with pip, and run `aletheia-athenaeum`. Existing users can install the wheel in their application environment; for the documented legacy environment, retain the explicit Qt pin:

```bash
source .venv313/bin/activate
python -m pip install --upgrade ./aletheia_athenaeum-0.1.1-py3-none-any.whl 'PySide6-Essentials==6.9.3'
python -m pip check
aletheia-athenaeum
```

Adjust the wheel path to its download location. Settings, models and Markdown remain in the existing profile. The legacy workaround is one tested configuration, not a guarantee for every older CPU. Local inference engines and optional semantic libraries have separate hardware requirements.

The release includes a Python wheel, source distribution and SHA-256 checksums. Python is required; Electron, WebEngine and Node.js are not. See README.md for standard setup, the full legacy Linux procedure and data locations. AGPL-3.0-only; upstream history and attribution retained.
