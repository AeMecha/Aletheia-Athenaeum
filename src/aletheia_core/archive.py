# Binder workflow provenance: https://github.com/AdeptTel1/Aletheia by Adeptus Telvannus.
# Covered upstream material retains the custom terms in LICENSES/LicenseRef-AdeptTel1-Aletheia.txt; see ATTRIBUTION.md.
"""Markdown is authoritative; SQLite/FTS and vectors are disposable derived data.

One reentrant lock protects both scans and mutations. New vectors are prepared
before a transaction replaces old rows; duplicate IDs make retrieval fail visibly.
"""
from __future__ import annotations
import hashlib
import json
import re
import secrets
import sqlite3
import struct
import threading
import unicodedata
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path

from .config import atomic_write
from .embeddings import INDEX_VERSION, chunk_text

BLOCK = re.compile(r"(^## Metadata[^\S\r\n]*\r?\n)(.*?)(?=^##\s|\Z)", re.M | re.S)
STOP_WORDS = set("a an the any all are am is was were be been being do does did have has had can could would should will i me my we our you your he she it its they their them this that these those there here what when where why how who which about on in at to of for with from and or but not please tell show find search archive archives document documents entry entries note notes recorded record know information say says more current question recent conversation resolving references user librarian".split())


def digest(content: str) -> str:
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


def metadata_of(content: str) -> dict:
    fields = {}
    for block in BLOCK.finditer(content):
        fields.update({key.strip().lower(): value.strip() for key, value in re.findall(r"^([\w -]+):[^\S\r\n]*(.*)$", block[2], re.M)})
    return fields


def title_of(content: str) -> str:
    match = re.search(r"^#[ \t]+(.+)$", content, re.M)
    return match[1].strip()[:400] if match else "Untitled"


def rewrite_metadata(content: str, update) -> str:
    block = list(BLOCK.finditer(content))[-1]
    return content[:block.start()] + update(block[1], block[2]) + content[block.end():]


def search_terms(query: str) -> list[str]:
    return list(dict.fromkeys(term for term in re.findall(r"[^\W_]+", query.lower()) if len(term) > 1 and term not in STOP_WORDS))[:40]


class Archive:
    def __init__(self, home: Path, embedder, status=lambda value: None):
        self.home, self.embedder, self.status = home.resolve(), embedder, status
        self.directory = self.home / "knowledge"
        self.directory.mkdir(parents=True, exist_ok=True)
        self.lock, self.error = threading.RLock(), None
        # A distinct filename prevents accidental reuse of an Electron index with
        # different Unicode offsets/tokenizer numerics when importing a profile.
        self.db = sqlite3.connect(self.home / "archive-python.sqlite3", check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        self.db.executescript("""
            PRAGMA journal_mode=WAL; PRAGMA foreign_keys=ON; PRAGMA busy_timeout=3000;
            CREATE TABLE IF NOT EXISTS settings(key TEXT PRIMARY KEY,value TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS documents(id TEXT PRIMARY KEY,filename TEXT UNIQUE NOT NULL,title TEXT NOT NULL,content TEXT NOT NULL,metadata TEXT NOT NULL,hash TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS chunks(rowid INTEGER PRIMARY KEY,document_id TEXT NOT NULL REFERENCES documents(id) ON DELETE CASCADE,title TEXT NOT NULL,text TEXT NOT NULL,start INTEGER NOT NULL,end INTEGER NOT NULL,embedding BLOB NOT NULL);
            CREATE VIRTUAL TABLE IF NOT EXISTS passages USING fts5(title,text,content='chunks',content_rowid='rowid',tokenize='porter unicode61');
            CREATE TRIGGER IF NOT EXISTS chunks_ai AFTER INSERT ON chunks BEGIN INSERT INTO passages(rowid,title,text) VALUES(new.rowid,new.title,new.text); END;
            CREATE TRIGGER IF NOT EXISTS chunks_ad AFTER DELETE ON chunks BEGIN INSERT INTO passages(passages,rowid,title,text) VALUES('delete',old.rowid,old.title,old.text); END;
        """)
        existing = self.db.execute("SELECT value FROM settings WHERE key='embedding'").fetchone()
        version = getattr(embedder, "index_version", INDEX_VERSION)
        if existing and existing[0] != version:
            # Changing search mode rebuilds derived rows only. Original Markdown
            # and stable IDs remain authoritative and are never deleted.
            self.db.execute("DELETE FROM documents")
            self.db.execute("UPDATE settings SET value=? WHERE key='embedding'", (version,))
        self.db.execute("INSERT OR IGNORE INTO settings VALUES('embedding',?)", (version,))
        self.db.commit()

    def require_ready(self):
        if self.error:
            raise ValueError(str(self.error))

    def scan(self) -> dict:
        with self.lock:
            try:
                records, ids = [], set()
                for filename in sorted(self.directory.rglob("*")):
                    if not filename.is_file() or filename.is_symlink() or filename.suffix.lower() != ".md":
                        continue
                    if not filename.resolve().is_relative_to(self.directory.resolve()):
                        raise ValueError("An archive path escapes the library.")
                    if filename.stat().st_size > 2 * 1024 * 1024:
                        raise ValueError(f"Archive file exceeds 2 MiB: {filename.name}")
                    content = filename.read_bytes().decode("utf-8")
                    metadata = metadata_of(content)
                    identifier = metadata.get("id") or filename.stem
                    if identifier in ids:
                        raise ValueError(f"Duplicate archive ID: {identifier}. Give the documents distinct IDs before searching.")
                    ids.add(identifier)
                    records.append(dict(id=identifier, filename=str(filename), title=title_of(content), content=content, metadata=metadata, hash=digest(content)))
                changed = 0
                for record in records:
                    previous = self.db.execute("SELECT hash FROM documents WHERE id=?", (record["id"],)).fetchone()
                    if previous and previous[0] == record["hash"]:
                        with self.db:
                            self.db.execute("UPDATE documents SET filename=? WHERE id=?", (record["filename"], record["id"]))
                        continue
                    self.status(dict(phase="indexing", message=f"Indexing {record['title']}", done=changed, total=len(records)))
                    chunks = chunk_text(record["content"], self.embedder.token_count)
                    vectors = [self.embedder.embed(chunk["text"]) for chunk in chunks]
                    with self.db:
                        self.db.execute("DELETE FROM documents WHERE id=? OR filename=?", (record["id"], record["filename"]))
                        self.db.execute("INSERT INTO documents VALUES(?,?,?,?,?,?)", (record["id"], record["filename"], record["title"], record["content"], json.dumps(record["metadata"]), record["hash"]))
                        for chunk, vector in zip(chunks, vectors):
                            blob = struct.pack(f"<{len(vector)}f", *vector)
                            self.db.execute("INSERT INTO chunks(document_id,title,text,start,end,embedding) VALUES(?,?,?,?,?,?)", (record["id"], record["title"], chunk["text"], chunk["start"], chunk["end"], blob))
                    changed += 1
                with self.db:
                    for record in self.db.execute("SELECT id FROM documents").fetchall():
                        if record[0] not in ids:
                            self.db.execute("DELETE FROM documents WHERE id=?", (record[0],))
                self.error = None
                return dict(count=len(records), changed=changed)
            except Exception as error:
                self.error = error
                raise

    def list(self) -> list[dict]:
        with self.lock:
            self.require_ready()
            return [dict(id=row["id"], title=row["title"], metadata=json.loads(row["metadata"])) for row in self.db.execute("SELECT id,title,metadata FROM documents ORDER BY rowid DESC")]

    def get(self, identifier: str) -> dict:
        with self.lock:
            self.require_ready()
            row = self.db.execute("SELECT id,title,content,metadata,hash AS revision FROM documents WHERE id=?", (identifier,)).fetchone()
            if not row:
                raise ValueError("This document is no longer in the archive.")
            return {**dict(row), "metadata": json.loads(row["metadata"])}

    def inventory(self, limit=12) -> dict:
        with self.lock:
            self.require_ready()
            rows = self.list()
            types, topics = Counter(), Counter()
            for row in rows:
                types[row["metadata"].get("type", "").strip() or "Uncategorized"] += 1
                topics.update({label.strip().lower()[:100] for label in re.split(r"[,;\n]", row["metadata"].get("topics", "")) if label.strip() and label.strip().lower() not in ("none", "unknown", "n/a")})
            return dict(total=len(rows), types=[dict(type=name, count=count) for name, count in types.most_common(15)], topics=[dict(topic=name, count=count) for name, count in topics.most_common(10)], documents=[dict(id=row["id"], title=row["title"]) for row in rows[:limit]])

    def search(self, query: str, limit=5, max_chars=20000) -> dict:
        with self.lock:
            self.require_ready()
            if not isinstance(query, str) or len(query) > 8000 or not 1 <= limit <= 10 or not 1 <= max_chars <= 40000:
                raise ValueError("Invalid search question or limits.")
            candidates = {}
            def add(row, rank):
                entry = candidates.setdefault(row["document_id"], dict(score=0, spans=[]))
                entry["score"] += 1 / (60 + rank)
                entry["spans"].append((row["start"], row["end"]))
            terms = search_terms(query)
            if terms:
                expression = " OR ".join('"' + term.replace('"', '""') + '"' for term in terms)
                matches = self.db.execute("SELECT c.document_id,c.start,c.end,bm25(passages,3,1) AS rank FROM passages JOIN chunks c ON c.rowid=passages.rowid WHERE passages MATCH ? ORDER BY rank LIMIT 80", (expression,)).fetchall()
                for rank, row in enumerate(matches):
                    add(row, rank)
            chunks = self.db.execute("SELECT document_id,start,end,embedding FROM chunks").fetchall()
            if query.strip() and chunks and getattr(self.embedder, "semantic", True):
                vector = self.embedder.embed(query[:2000], True)
                scored = [(sum(a * b for a, (b,) in zip(vector, struct.iter_unpack("<f", row["embedding"]))), row) for row in chunks]
                for rank, (_, row) in enumerate(sorted((item for item in scored if item[0] >= .65), key=lambda item: item[0], reverse=True)[:80]):
                    add(row, rank)
            results, remaining, truncated = [], max_chars, False
            for identifier, candidate in sorted(candidates.items(), key=lambda item: item[1]["score"], reverse=True)[:limit]:
                if remaining <= 0:
                    truncated = True
                    break
                record = self.get(identifier)
                original = content = record["content"]
                if len(content) > remaining:
                    merged = []
                    for start, end in sorted(candidate["spans"]):
                        if merged and start <= merged[-1][1]:
                            merged[-1][1] = max(merged[-1][1], end)
                        else:
                            merged.append([start, end])
                    content = "\n\n[...]\n\n".join(original[start:end] for start, end in merged)[:remaining]
                    truncated = True
                remaining -= len(content)
                results.append({**record, "content": content, "is_excerpt": content != original})
            return dict(success=True, query=query, results=results, truncated=truncated, search_scope="hybrid_top_k" if getattr(self.embedder, "semantic", True) else "lexical_top_k")

    def save(self, content: str, preserve_id=False) -> dict:
        if not isinstance(content, str) or not content.strip() or len(content.encode("utf-8")) > 2 * 1024 * 1024:
            raise ValueError("Save nonempty Markdown of at most 2 MiB.")
        with self.lock:
            self.require_ready()
            fields = metadata_of(content)
            identifier = fields.get("id") if preserve_id else None
            if identifier:
                if not re.fullmatch(r"[\w-]{1,240}", identifier, re.UNICODE):
                    raise ValueError("The imported document has an unsafe ID.")
                previous = self.db.execute("SELECT hash FROM documents WHERE id=?", (identifier,)).fetchone()
                if previous:
                    if previous[0] == digest(content):
                        return {**self.get(identifier), "duplicate": True}
                    raise ValueError(f"A different document already uses the ID {identifier}.")
            else:
                now = datetime.now(timezone.utc)
                slug = re.sub(r"[^a-z0-9]+", "-", unicodedata.normalize("NFKD", title_of(content)).encode("ascii", "ignore").decode().lower()).strip("-")[:120] or "untitled"
                base = now.strftime("%Y%m%d_%H%M%S") + "_" + slug
                identifier, suffix = base, 0
                while (self.directory / (identifier + ".md")).exists() or self.db.execute("SELECT 1 FROM documents WHERE id=?", (identifier,)).fetchone():
                    suffix += 1
                    identifier = f"{base}_{suffix}"
                stamp = now.isoformat(timespec="milliseconds").replace("+00:00", "Z")
                text = f"ID: {identifier}\nCreated: {stamp}\nModified: {stamp}\n"
                if BLOCK.search(content):
                    content = rewrite_metadata(content, lambda heading, block: heading + "\n" + text + re.sub(r"^(?:ID|Created|Modified):.*\r?\n?", "", block, flags=re.I | re.M).strip() + "\n")
                else:
                    content += "\n\n## Metadata\n\n" + text
            destination = self.directory / (identifier + ".md")
            if destination.exists():
                raise ValueError("A document with this filename already exists.")
            atomic_write(destination, content)
            self.scan()
            return {**self.get(identifier), "duplicate": False}

    def rename_title(self, identifier: str, title: str, revision: str) -> dict:
        if not isinstance(title, str) or not 1 <= len(title.strip()) <= 400 or re.search(r"[\x00-\x1f\x7f]", title):
            raise ValueError("Enter a title of 1-400 characters on one line.")
        with self.lock:
            record = self.get(identifier)
            path = Path(self.db.execute("SELECT filename FROM documents WHERE id=?", (identifier,)).fetchone()[0])
            if path.is_symlink() or not path.resolve().is_relative_to(self.directory.resolve()):
                raise ValueError("The document must be inside the archive folder.")
            original = path.read_bytes().decode("utf-8")
            if record["revision"] != revision or digest(original) != revision:
                raise ValueError("This document changed after it was opened. Reopen it before editing the title.")
            eol = "\r\n" if "\r\n" in original else "\n"
            content = re.sub(r"^#[ \t]+[^\r\n]*(\r?)$", lambda match: "# " + title.strip() + match[1], original, count=1, flags=re.M) if re.search(r"^#[ \t]+", original, re.M) else "# " + title.strip() + eol + eol + original
            modified = datetime.now(timezone.utc).isoformat(timespec="milliseconds")
            if BLOCK.search(content):
                content = rewrite_metadata(content, lambda heading, block: heading + ("" if metadata_of("## Metadata\n" + block).get("id") else "ID: " + identifier + eol) + "Modified: " + modified + eol + re.sub(r"^Modified:[^\r\n]*(?:\r?\n|$)", "", block, flags=re.I | re.M))
            else:
                content += eol + eol + "## Metadata" + eol + eol + f"ID: {identifier}{eol}Modified: {modified}{eol}"
            atomic_write(path, content)
            self.scan()
            return self.get(identifier)

    def close(self):
        with self.lock:
            self.db.close()
