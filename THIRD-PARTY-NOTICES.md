# Third-party components

Aletheia Athenaeum includes original/adapted material from [Aletheia](https://github.com/AdeptTel1/Aletheia) by **Adeptus Telvannus (AdeptTel1)**. That covered material retains the [original custom license](LICENSES/LicenseRef-AdeptTel1-Aletheia.txt); it is not relicensed under the AGPL. See LICENSE, LICENSING.md, NOTICE and ATTRIBUTION.md for scope, provenance and material changes. The AGPL text retained for separately authored contributions is in LICENSES/AGPL-3.0-only.txt. Other components retain the following notices.

Python is under the [PSF license](https://docs.python.org/3/license.html). Runtime packages retain their licenses:

- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html): LGPL-3.0/GPL-3.0 or commercial terms, depending on components. This app uses dynamically loaded, unmodified Qt Widgets libraries from official wheels. Preserve Qt notices and recipients' ability to replace LGPL libraries when redistributing.
- [HTTPX](https://github.com/encode/httpx): BSD-3-Clause; [filelock](https://github.com/tox-dev/filelock): Unlicense. Transitive dependency notices remain in installed distributions.
- Semantic search: [NumPy](https://github.com/numpy/numpy) BSD-3-Clause, [ONNX Runtime](https://github.com/microsoft/onnxruntime) MIT, [Tokenizers](https://github.com/huggingface/tokenizers) Apache-2.0. These are optional for Python installations and included in the standalone Windows executable.
- Optional native engine: [llama.cpp](https://github.com/ggml-org/llama.cpp) MIT; bundled notices remain in the extracted cache.
- Optional search weights: [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) MIT, using the [Xenova ONNX conversion](https://huggingface.co/Xenova/bge-small-en-v1.5).
- The separately downloaded default [Qwen model](https://huggingface.co/JamieBradfield/qwen3.8-9b-hermes-fc-tooluse) is identified by its publisher as Apache-2.0. Its quantized artifact is pinned in src/aletheia_core/data/assets.json.

Other models and API providers retain their licenses and terms. Weights, inference engines and semantic libraries are not bundled in the Python wheel. Installed package metadata and upstream projects supply complete dependency license texts.

The standalone executable is built with [PyInstaller](https://pyinstaller.org/) and includes its bootloader, Python, Qt Essentials and the application dependencies. Original license/notice files are retained inside the executable and in the accompanying Windows licenses ZIP. The source archive includes the application and Windows build scripts. Use the Python/source distribution to run with independently installed or replaced Qt libraries, including the documented legacy Linux configuration.
