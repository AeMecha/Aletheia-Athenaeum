"""One async application owner for browser requests and the native Qt worker.

SQLite/embedding work goes to a thread; cancellation and HTTP remain responsive.
Both interfaces call these operations instead of implementing their own archive
or accepting unvalidated model output.
"""
from __future__ import annotations
import asyncio
import copy
import json
import os
import secrets
from pathlib import Path

from filelock import FileLock, Timeout
from .archive import Archive
from .assets import DATA, MANIFEST, download, prepare_embeddings
from .config import Config, atomic_json
from .embeddings import Embeddings, KeywordIndex
from .model import Model, validate_gguf
from .protocol import NO_MATCH, build_query, fit_draft, inventory_answer, is_inventory, librarian_payload, validate_answer, validate_draft


class Service:
    def __init__(self, home: Path, resources: Path | None = None, embedder=None, transport=None):
        self.home = home.resolve()
        self.home.mkdir(parents=True, exist_ok=True)
        self.profile_lock = FileLock(self.home / "profile.lock")
        try:
            self.profile_lock.acquire(timeout=0)
        except Timeout as error:
            raise ValueError("This data folder is already open in another Aletheia process.") from error
        self.config = Config(self.home)
        self.resources = resources or (Path(os.environ["ALETHEIA_RESOURCES"]).expanduser().resolve() if os.environ.get("ALETHEIA_RESOURCES") else self.home / "resources")
        self.embedder, self.archive = embedder, None
        self.progress, self.operation = None, None
        self.documents = []
        self.library = dict(phase="loading", message="Opening your library...")
        self.model = Model(self.config, self.resources, self.set_progress, transport)
        self.history_path = self.home / "conversation.json"
        self.chat = json.loads(self.history_path.read_text(encoding="utf-8")) if self.history_path.exists() else dict(id=secrets.token_hex(16), messages=[])
        self.prompts = {name: (DATA / "prompts" / (name + ".md")).read_text(encoding="utf-8") for name in ("librarian", "archivist")}
        self.scan_task, self.start_task = None, None
        self.closed = False
        self.refresh_lock = asyncio.Lock()

    def set_progress(self, value):
        self.progress = value

    async def initialize(self):
        try:
            if self.embedder is None:
                if self.config.value["searchMode"] == "keyword":
                    self.embedder = KeywordIndex()
                else:
                    try:
                        import importlib.util
                        if any(importlib.util.find_spec(name) is None for name in ("numpy", "onnxruntime", "tokenizers")):
                            raise ImportError()
                    except ImportError as error:
                        raise ValueError("Install this app's [semantic] extra to use semantic search, or choose keyword search in Settings.") from error
                    directory = await prepare_embeddings(self.resources, self.set_progress)
                    self.embedder = await asyncio.to_thread(Embeddings, directory)
            if self.archive is None:
                self.archive = Archive(self.home, self.embedder, self.set_library)
            await self.refresh()
            self.progress = None
            if self.scan_task is None:
                self.scan_task = asyncio.create_task(self.scan_loop())
            if self.config.value["autoStart"]:
                self.start_task = asyncio.create_task(self.auto_start())
        except Exception as error:
            self.library = dict(phase="error", message=str(error))
            self.progress = None

    async def auto_start(self):
        try:
            await self.model.start()
        except Exception:
            pass  # Model publishes the actionable error through its state.

    def set_library(self, value):
        self.library = value

    async def scan_loop(self):
        while True:
            await asyncio.sleep(15)
            if self.operation is None:
                try:
                    await self.refresh()
                except Exception:
                    pass

    def snapshot(self):
        # Do not take the SQLite scan lock on the event loop. Snapshots remain
        # responsive during inference/indexing, and Qt receives independent data.
        return copy.deepcopy(dict(settings=self.config.public(), model=dict(self.model.state), library=dict(self.library), busy=self.operation is not None,
                    progress=self.progress, chat=self.chat, documents=self.documents if not (self.archive and self.archive.error) else [], home=str(self.home)))

    def require_archive(self):
        if not self.archive or self.library["phase"] == "error":
            raise ValueError(self.library.get("message", "Your library is still opening."))

    async def refresh(self):
        if not self.archive:
            raise ValueError("Your search model is still being prepared. Wait for library setup to finish.")
        async with self.refresh_lock:
            return await self._refresh_locked()

    async def _refresh_locked(self):
        try:
            result = await asyncio.to_thread(self.archive.scan)
            self.documents = await asyncio.to_thread(self.archive.list)
            count = result["count"]
            mode = "hybrid search" if getattr(self.embedder, "semantic", True) else "keyword search"
            self.library = dict(phase="ready", message=f"{count} document{'s' if count != 1 else ''} in your library - {mode}", count=count)
            return self.snapshot()
        except Exception as error:
            self.library = dict(phase="error", message=str(error))
            raise

    async def exclusive(self, callback):
        if self.operation:
            raise ValueError("Finish or stop the current operation first.")
        current = self.operation = asyncio.current_task()
        try:
            return await callback()
        finally:
            if self.operation is current:
                self.operation, self.progress = None, None

    async def cancel(self):
        if self.operation and self.operation is not asyncio.current_task():
            self.operation.cancel()
        if self.model.state["phase"] == "loading":
            await self.model.stop()
        return True

    def persist_chat(self):
        atomic_json(self.history_path, self.chat)
        atomic_json(self.home / "conversations" / (self.chat["id"] + ".json"), self.chat)

    def remember(self, question, answer):
        self.chat["messages"].extend([dict(role="user", content=question.strip()), dict(role="assistant", content=answer["answer"], sources=answer["sources"])])
        self.chat["messages"] = self.chat["messages"][-100:]
        self.persist_chat()

    async def ask(self, question):
        self.require_archive()
        async def action():
            query = build_query(question, self.chat["messages"])
            await self.refresh()
            if is_inventory(question.strip()):
                accepted = inventory_answer(await asyncio.to_thread(self.archive.inventory))
            else:
                await self.model.start()
                if self.model.state["phase"] != "ready":
                    raise ValueError("Choose a local model or configure an API in Settings first.")
                self.progress = dict(phase="searching", message="Searching your library...")
                result = await asyncio.to_thread(self.archive.search, query)
                if not result["results"]:
                    accepted = dict(answer=NO_MATCH, sources=[], search_scope=result["search_scope"])
                else:
                    fitted = await self.fit_sources(result)
                    self.progress = dict(phase="answering", message="Reading the retrieved sources...")
                    raw = await self.model.complete(librarian_payload(self.prompts["librarian"], question.strip(), query, fitted))
                    accepted = validate_answer(raw, fitted)
            self.remember(question, accepted)
            return accepted
        return await self.exclusive(action)

    async def fit_sources(self, result):
        documents = [dict(item) for item in result["results"]]
        budget = min(4500, self.config.value["contextSize"] // 4)
        async def measure(items):
            return await self.model.count_tokens(json.dumps(items, ensure_ascii=False))
        if await measure(documents) <= budget:
            return {**result, "documents": documents}
        while documents and await measure([{**item, "content": item["content"][:80], "is_excerpt": True} for item in documents]) > budget:
            documents.pop()
        if not documents:
            raise ValueError("Matching sources cannot fit this context. Increase the context if the model supports it.")
        low, high = 0, max(len(item["content"]) for item in documents)
        clipped = lambda size: [{**item, "content": item["content"][:size], "is_excerpt": True} for item in documents]
        while low < high:
            middle = (low + high + 1) // 2
            if await measure(clipped(middle)) <= budget:
                low = middle
            else:
                high = middle - 1
        return {**result, "documents": clipped(low), "truncated": True}

    async def draft(self, content):
        if not isinstance(content, str) or not content.strip() or len(content) > 20000:
            raise ValueError("Provide between 1 and 20,000 characters to prepare.")
        async def action():
            await self.model.start()
            for attempt in range(2):
                self.progress = dict(phase="drafting", message="Preparing document metadata..." if not attempt else "Retrying document metadata...")
                instructions = self.prompts["archivist"] + ("\nThe previous attempt was invalid. Return all four fields and a short neutral summary." if attempt else "")
                payload, excerpted = await fit_draft(instructions, content, self.config.value["contextSize"], self.model.count_tokens, 600 if attempt else 1200)
                raw = await self.model.complete(payload)
                try:
                    return dict(markdown=validate_draft(raw, content), source_excerpted=excerpted)
                except ValueError:
                    if attempt:
                        raise
        return await self.exclusive(action)

    async def save(self, content):
        self.require_archive()
        async def action():
            result = await asyncio.to_thread(self.archive.save, content)
            await self.refresh()
            return result
        return await self.exclusive(action)

    async def rename_title(self, identifier, title, revision):
        self.require_archive()
        async def action():
            record = await asyncio.to_thread(self.archive.rename_title, identifier, title, revision)
            for message in self.chat["messages"]:
                for source in message.get("sources", []):
                    if source["id"] == identifier:
                        source["title"] = record["title"]
            self.persist_chat()
            await self.refresh()
            return record
        return await self.exclusive(action)

    async def import_contents(self, files):
        self.require_archive()
        if not isinstance(files, list) or len(files) > 2000:
            raise ValueError("Import at most 2,000 Markdown documents at a time.")
        async def action():
            imported = duplicates = 0
            errors = []
            for item in files:
                name = Path(item.get("name", "document.md")).name
                try:
                    if Path(name).suffix.lower() != ".md":
                        raise ValueError("Only Markdown files can be imported.")
                    record = await asyncio.to_thread(self.archive.save, item["content"], True)
                    duplicates += int(record["duplicate"])
                    imported += int(not record["duplicate"])
                except Exception as error:
                    errors.append(f"{name}: {error}")
            await self.refresh()
            return dict(imported=imported, duplicates=duplicates, errors=errors)
        return await self.exclusive(action)

    async def select_model(self, filename):
        async def action():
            path = await asyncio.to_thread(validate_gguf, filename)
            await self.model.stop()
            self.config.save({**self.config.value, "provider": "embedded", "modelPath": str(path)})
            await self.model.start()
            return self.snapshot()
        return await self.exclusive(action)

    async def download_model(self):
        async def action():
            asset = MANIFEST["model"]
            filename = await download(asset, self.home / "models" / asset["filename"], self.set_progress)
            (filename.parent / "MODEL-NOTICES.txt").write_text("Default Qwen model: Apache-2.0 as identified by its publisher. https://huggingface.co/JamieBradfield/qwen3.8-9b-hermes-fc-tooluse\n", encoding="utf-8")
            await self.model.stop()
            self.config.save({**self.config.value, "provider": "embedded", "modelPath": str(filename)})
            await self.model.start()
            return self.snapshot()
        return await self.exclusive(action)

    async def settings(self, value):
        async def action():
            from .config import validate_settings
            checked = validate_settings({**self.config.with_saved_key(value), "theme": self.config.value["theme"]})
            search_changed = checked["searchMode"] != self.config.value["searchMode"] or self.archive is None
            await self.model.stop()
            self.config.save(checked)
            if search_changed:
                async with self.refresh_lock:
                    if self.archive:
                        await asyncio.to_thread(self.archive.close)
                    self.archive, self.embedder, self.documents = None, None, []
                await self.initialize()
                if self.library["phase"] == "error":
                    raise ValueError(self.library["message"])
            await self.model.start()
            return self.snapshot()
        return await self.exclusive(action)

    def theme(self, theme):
        self.config.save({**self.config.value, "theme": theme})
        return dict(theme=theme)

    def new_chat(self):
        if self.operation:
            raise ValueError("Stop the current operation before starting a new conversation.")
        if self.chat["messages"]:
            self.persist_chat()
        self.chat = dict(id=secrets.token_hex(16), messages=[])
        self.persist_chat()
        return self.snapshot()

    async def execute(self, name, args):
        """Explicit operation map; no reflection or arbitrary filesystem RPC."""
        async def document(identifier):
            self.require_archive()
            return await asyncio.to_thread(self.archive.get, identifier)
        async def connect():
            return await self.exclusive(self.model.start)
        operations = dict(snapshot=self.snapshot, ask=self.ask, draft=self.draft, save=self.save,
                          renameTitle=self.rename_title, theme=self.theme, newChat=self.new_chat,
                          cancel=self.cancel, settings=self.settings, connect=connect,
                          models=self.model.models, downloadModel=self.download_model,
                          document=document, refresh=self.refresh, chooseModel=self.select_model,
                          importContents=self.import_contents, openFolder=lambda: str(self.home / "knowledge"))
        if name not in operations or not isinstance(args, list) or len(args) > 4:
            raise ValueError("Unknown application operation.")
        result = operations[name](*args)
        if hasattr(result, "__await__"):
            result = await result
        return result

    async def close(self):
        self.closed = True
        tasks = [task for task in (self.operation, self.scan_task, self.start_task) if task and task is not asyncio.current_task()]
        for task in tasks:
            task.cancel()
        await asyncio.gather(*tasks, return_exceptions=True)
        await self.model.stop()
        if self.archive:
            await asyncio.to_thread(self.archive.close)
        self.profile_lock.release()
