# Third-party components

Aletheia Athenaeum is AGPL-3.0-only; see LICENSE and NOTICE. Distributions must preserve applicable notices and provide corresponding source as required by the AGPL.

Python is under the [PSF license](https://docs.python.org/3/license.html). Runtime packages retain their licenses:

- [PySide6 / Qt for Python](https://doc.qt.io/qtforpython-6/licenses.html): LGPL-3.0/GPL-3.0 or commercial terms, depending on components. This app uses dynamically loaded, unmodified Qt Widgets libraries from official wheels. Preserve Qt notices and recipients' ability to replace LGPL libraries when redistributing.
- [HTTPX](https://github.com/encode/httpx): BSD-3-Clause; [filelock](https://github.com/tox-dev/filelock): Unlicense. Transitive dependency notices remain in installed distributions.
- Optional semantic search: [NumPy](https://github.com/numpy/numpy) BSD-3-Clause, [ONNX Runtime](https://github.com/microsoft/onnxruntime) MIT, [Tokenizers](https://github.com/huggingface/tokenizers) Apache-2.0. None are required for keyword search.
- Optional native engine: [llama.cpp](https://github.com/ggml-org/llama.cpp) MIT; bundled notices remain in the extracted cache.
- Optional search weights: [BAAI/bge-small-en-v1.5](https://huggingface.co/BAAI/bge-small-en-v1.5) MIT, using the [Xenova ONNX conversion](https://huggingface.co/Xenova/bge-small-en-v1.5).
- The separately downloaded default [Qwen model](https://huggingface.co/JamieBradfield/qwen3.8-9b-hermes-fc-tooluse) is identified by its publisher as Apache-2.0. Its quantized artifact is pinned in src/aletheia_core/data/assets.json.

Other models and API providers retain their licenses and terms. Weights, inference engines and semantic libraries are not bundled in the Python wheel. Installed package metadata and upstream projects supply complete dependency license texts.
