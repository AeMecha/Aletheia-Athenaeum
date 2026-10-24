# Initial Python edition validation

Local checks on Windows x64 with Python 3.14.5:

- 19 archive/protocol/service/native acceptance tests passed using actual Qt Widgets, signals and a QThread worker. Offscreen tests cover save, inventory, title edit, themes, API discovery, preparation, cited answers and clean shutdown.
- Wheel and source distribution build successfully. The application wheel contains Python source, prompts, manifest and native Qt interface code; it contains no Electron, Node.js or model weights.
- Real cached BGE ONNX inference produced finite, normalized 384-dimensional vectors.
- Real local Qwen Q4_K_S GGUF passed metadata preparation, complete source retention, hybrid retrieval and cited answers through schema mode.
- A separate Llama-family GGUF passed the same workflow through prompt JSON fallback. Other model families require their own validation; not every model can follow this protocol.

Multi-platform CI installs each app independently on Windows, Ubuntu x64, macOS ARM64 and Ubuntu ARM64, runs its tests and builds source/wheel artifacts. This does not validate every native inference engine or CPU. Optional semantic search depends on available ONNX/tokenizer wheels; local inference depends on native engine and model compatibility.
