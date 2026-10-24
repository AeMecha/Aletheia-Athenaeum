"""Text-only BGE inference: WordPiece, masked mean pooling, L2 normalization.

No vision library or Node/Electron dependency is imported. The derived Python
index has its own version and is rebuilt from authoritative Markdown.
"""
from __future__ import annotations
import threading
from pathlib import Path

INDEX_VERSION = "python-bge-small-v1.5-q8-masked-mean384-chunk240-overlap40-v1"


class KeywordIndex:
    """Portable FTS-only mode: no weights, NumPy, tokenizer, or ONNX import."""
    semantic = False
    index_version = "python-fts5-byte960-overlap160-v1"

    def token_count(self, text):
        return max(1, (len(text.encode("utf-8")) + 3) // 4)

    def embed(self, text, query=False):
        return []


class Embeddings:
    semantic = True
    index_version = INDEX_VERSION

    def __init__(self, directory: Path):
        # Import native ML libraries only after the user opts into semantic mode.
        import numpy as np
        import onnxruntime as ort
        from tokenizers import Tokenizer
        self.np = np
        self.counter = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer = Tokenizer.from_file(str(directory / "tokenizer.json"))
        self.tokenizer.enable_truncation(max_length=512)
        options = ort.SessionOptions()
        options.intra_op_num_threads = 2
        options.inter_op_num_threads = 1
        self.session = ort.InferenceSession(str(directory / "onnx/model_quantized.onnx"), sess_options=options, providers=["CPUExecutionProvider"])
        self.lock = threading.RLock()

    def token_count(self, text: str) -> int:
        return len(self.counter.encode(text).ids)

    def embed(self, text: str, query=False) -> list[float]:
        with self.lock:
            np = self.np
            encoded = self.tokenizer.encode(("Represent this sentence for searching relevant passages: " if query else "") + text)
            fields = {"input_ids": encoded.ids, "attention_mask": encoded.attention_mask, "token_type_ids": encoded.type_ids}
            feeds = {item.name: np.asarray([fields[item.name]], dtype=np.int64) for item in self.session.get_inputs()}
            hidden = self.session.run(None, feeds)[0][0]
            mask = np.asarray(encoded.attention_mask, dtype=np.float32)
            vector = (hidden * mask[:, None]).sum(axis=0) / max(float(mask.sum()), 1)
            norm = float(np.linalg.norm(vector))
            if vector.shape != (384,) or not np.isfinite(vector).all() or norm == 0:
                raise ValueError("The search model did not return a valid 384-dimensional vector.")
            return (vector / norm).astype(np.float32).tolist()


def chunk_text(text: str, count, size=240) -> list[dict]:
    chunks, start = [], 0
    while start < len(text):
        low, high = 1, min(len(text) - start, 4000)
        while low < high:
            middle = (low + high + 1) // 2
            if count(text[start:start + middle]) <= size:
                low = middle
            else:
                high = middle - 1
        end = start + low
        if count(text[start:end]) > size:
            raise ValueError("A document cannot fit the retrieval passage limit.")
        chunks.append(dict(start=start, end=end, text=text[start:end]))
        if end == len(text):
            break
        minimum, overlap = start + max(1, (end - start) // 2), end
        while overlap > minimum and count(text[overlap - 1:end]) <= 40:
            overlap -= 1
        start = max(minimum, overlap)
    return chunks
