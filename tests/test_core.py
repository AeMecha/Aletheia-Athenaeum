"""Deterministic behavior checks: no user data, model weights or external API."""
import asyncio
import importlib.util
import json
import os
import struct
import tempfile
import unittest
from pathlib import Path

import httpx

from aletheia_core.archive import Archive, metadata_of
from aletheia_core.assets import MANIFEST, extract_runtime, runtime_target
from aletheia_core.config import Config, DEFAULTS, validate_settings
from aletheia_core.embeddings import KeywordIndex, chunk_text
from aletheia_core.model import Model, validate_gguf
from aletheia_core.protocol import archivist_payload, is_inventory, validate_answer, validate_draft
from aletheia_core.service import Service


def profile(case):
    directory = tempfile.TemporaryDirectory(prefix="aletheia-python-")
    path = Path(directory.name).resolve()
    def cleanup():
        case.assertEqual(path.parent, Path(tempfile.gettempdir()).resolve())
        case.assertTrue(path.name.startswith("aletheia-python-"))
        directory.cleanup()
    case.addCleanup(cleanup)
    return path


def completed(content, model="test/model-resolved"):
    return dict(model=model, choices=[dict(finish_reason="stop", message=dict(content=json.dumps(content)))])


class ArchiveTests(unittest.TestCase):
    def setUp(self):
        self.home = profile(self)
        self.archive = Archive(self.home, KeywordIndex())
        self.addCleanup(self.archive.close)

    def test_lexical_search_originals_and_stemming(self):
        original = "# Magic glossary\n\nA warlock is a practitioner of magic.\n"
        record = self.archive.save(original)
        self.assertIn(original, record["content"])
        self.assertEqual(self.archive.search("Any entries on warlocks?")["results"][0]["id"], record["id"])
        self.assertEqual(self.archive.search("gardening")["results"], [])
        self.assertEqual(self.archive.search("magic")["search_scope"], "lexical_top_k")

    def test_title_edit_preserves_id_filename_body_and_rejects_stale_revision(self):
        original = "# Source\n\n## Content\nOriginal quoted text.\n\n## Metadata\nID: original-source\nCreated: 2001-01-01\n"
        source = "# Prepared\n\n## Content\n\n" + original + "\n\n## Metadata\nType: Reference\n"
        record = self.archive.save(source)
        filenames = list(self.archive.directory.glob("*.md"))
        renamed = self.archive.rename_title(record["id"], "New title", record["revision"])
        self.assertEqual(renamed["id"], record["id"])
        self.assertEqual(list(self.archive.directory.glob("*.md")), filenames)
        self.assertIn(original, renamed["content"])
        self.assertEqual(renamed["metadata"]["created"], record["metadata"]["created"])
        self.assertEqual(metadata_of(renamed["content"])["id"], record["id"])
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.archive.rename_title(record["id"], "Stale overwrite", record["revision"])

    def test_external_edit_cannot_be_overwritten(self):
        record = self.archive.save("# Original\n\nA blue bicycle.")
        path = next(self.archive.directory.glob("*.md"))
        path.write_text(record["content"] + "\nExternal addition.", encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "changed after"):
            self.archive.rename_title(record["id"], "Overwrite", record["revision"])
        self.assertIn("External addition", path.read_text(encoding="utf-8"))

    def test_duplicate_id_fails_closed_and_import_keeps_id(self):
        content = "# Imported\n\nOriginal note.\n\n## Metadata\nID: imported-record\n"
        record = self.archive.save(content, True)
        self.assertEqual(record["id"], "imported-record")
        self.assertTrue(self.archive.save(content, True)["duplicate"])
        duplicate = self.archive.directory / "duplicate.md"
        duplicate.write_text(content, encoding="utf-8")
        with self.assertRaisesRegex(ValueError, "Duplicate archive ID"):
            self.archive.scan()
        with self.assertRaisesRegex(ValueError, "Duplicate archive ID"):
            self.archive.search("note")
        duplicate.unlink()
        self.archive.scan()
        self.assertEqual(self.archive.inventory()["total"], 1)

    def test_inventory_counts_beyond_examples(self):
        for number in range(15):
            self.archive.save(f"# Note {number}\n\nBlue bicycle {number}.\n\n## Metadata\nType: Observation\nTopics: Bicycles\n")
        result = self.archive.inventory()
        self.assertEqual(result["total"], 15)
        self.assertEqual(len(result["documents"]), 12)
        self.assertEqual(result["types"][0]["count"], 15)
        self.assertEqual(result["topics"][0]["count"], 15)

    def test_unsafe_import_id_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "unsafe ID"):
            self.archive.save("# Bad\n\n## Metadata\nID: ../outside\n", True)

    def test_unicode_chunks_are_exact_spans(self):
        text = ("Unicode \U0001f33f source with punctuation. " * 100)
        chunks = chunk_text(text, len, 90)
        self.assertEqual(chunks[-1]["end"], len(text))
        for chunk in chunks:
            self.assertEqual(chunk["text"], text[chunk["start"]:chunk["end"]])
            self.assertLessEqual(len(chunk["text"]), 90)


class ProtocolTests(unittest.TestCase):
    def test_malformed_api_envelopes_fail_closed(self):
        for raw in (None, [], {"choices": None}, {"choices": [None]}, {"choices": [{"message": None}]}):
            with self.subTest(raw=raw), self.assertRaises(ValueError):
                validate_draft(raw, "Original source")

    def test_inventory_intent_does_not_swallow_topical_questions(self):
        self.assertTrue(is_inventory("What does my archive contain?"))
        self.assertTrue(is_inventory("Show all my documents"))
        self.assertFalse(is_inventory("What does my archive contain about bicycles?"))

    def test_draft_keeps_original_and_rejects_incomplete_metadata(self):
        original = "# Input\n\nUser: this is a legitimate quote.\n\n## Metadata\nID: quoted-id\n"
        data = dict(title="Input note", summary="A legitimate quoted note.", keywords=["note"], type="Observation")
        self.assertIn(original, validate_draft(completed(data), original))
        raw = completed(data)
        raw["choices"][0]["finish_reason"] = "length"
        with self.assertRaisesRegex(ValueError, "generation limit"):
            validate_draft(raw, original)
        with self.assertRaisesRegex(ValueError, "invalid document metadata"):
            validate_draft(completed({**data, "title": "Injected\nheading"}), original)

    def test_source_and_tool_validation_remains_strict(self):
        retrieval = dict(documents=[dict(id="real", title="Real note", is_excerpt=False)], search_scope="lexical_top_k")
        self.assertEqual(validate_answer(completed(dict(answer="A blue bicycle.", sources=["real"])), retrieval)["sources"][0]["id"], "real")
        for value in (dict(answer="A blue bicycle.", sources=["invented"]), dict(answer="assistant: another turn", sources=["real"])):
            with self.assertRaises(ValueError):
                validate_answer(completed(value), retrieval)
        raw = completed(dict(answer="A blue bicycle.", sources=["real"]))
        raw["choices"][0]["message"]["tool_calls"] = [dict(name="invented")]
        with self.assertRaisesRegex(ValueError, "tool operation"):
            validate_answer(raw, retrieval)


class ConfigAndRuntimeTests(unittest.TestCase):
    def test_legacy_preferences_and_private_key_handling(self):
        home = profile(self)
        (home / "settings.json").write_text(json.dumps(dict(provider="lmstudio", lmStudioUrl="https://example.test/custom/v1/", apiKey="synthetic-key", theme="dark")), encoding="utf-8")
        config = Config(home)
        self.assertEqual(config.value["provider"], "api")
        self.assertEqual(config.value["apiUrl"], "https://example.test/custom/v1")
        self.assertEqual(config.public()["apiKey"], "")
        self.assertTrue(config.public()["hasApiKey"])
        self.assertEqual(config.with_saved_key(dict(apiUrl=config.value["apiUrl"], apiKey=""))["apiKey"], "synthetic-key")
        self.assertEqual(config.with_saved_key(dict(apiUrl="https://other.test/v1", apiKey=""))["apiKey"], "")
        self.assertEqual(config.with_saved_key(dict(apiUrl=config.value["apiUrl"], apiKey="", clearApiKey=True))["apiKey"], "")
        for patch in (dict(apiUrl="file:///tmp"), dict(apiUrl="https://user:secret@example.test/v1"), dict(contextSize=10), dict(provider="api", apiModel="")):
            with self.assertRaises(ValueError):
                validate_settings({**DEFAULTS, **patch})

    def test_all_native_targets_have_pinned_digests(self):
        for system, machine, expected in [("Windows", "AMD64", "win32-x64"), ("Windows", "ARM64", "win32-arm64"), ("Linux", "aarch64", "linux-arm64"), ("Linux", "x86_64", "linux-x64"), ("Darwin", "arm64", "darwin-arm64"), ("Darwin", "x86_64", "darwin-x64")]:
            self.assertEqual(runtime_target(system, machine), expected)
            for asset in MANIFEST["runtimePlatforms"][expected].values():
                self.assertEqual(len(asset["sha256"]), 64)
                self.assertGreater(asset["size"], 0)
        with self.assertRaisesRegex(ValueError, "No pinned engine"):
            runtime_target("Linux", "riscv64")

    def test_gguf_header_and_unsafe_archive_paths(self):
        home = profile(self)
        filename = home / "another-model.gguf"
        filename.write_bytes(b"GGUF" + struct.pack("<I", 3) + b"\0" * 16)
        self.assertEqual(validate_gguf(str(filename)), filename)
        filename.write_bytes(b"not-a-model")
        with self.assertRaises(ValueError):
            validate_gguf(str(filename))
        import zipfile
        archive = home / "bad.zip"
        with zipfile.ZipFile(archive, "w") as bundle:
            bundle.writestr("../escape.txt", "unsafe")
        with self.assertRaisesRegex(ValueError, "Unsafe engine archive"):
            extract_runtime(archive, home / "extract")
        self.assertFalse((home / "escape.txt").exists())


class ServiceTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.home = profile(self)
        self.service = Service(self.home)
        self.service.config.save({**self.service.config.value, "autoStart": False})
        await self.service.initialize()
        self.addAsyncCleanup(self.service.close)

    async def test_overview_and_theme_work_without_an_ai(self):
        await self.service.save("# Blue bicycle\n\nA blue bicycle is in the green barn.")
        answer = await self.service.ask("What does my archive contain?")
        self.assertIn("contains 1 document.", answer["answer"])
        self.assertEqual(self.service.model.state["phase"], "stopped")
        self.service.theme("dark")
        self.assertEqual(Config(self.home).value["theme"], "dark")
        self.assertEqual(len(self.service.chat["messages"]), 2)

    async def test_api_formats_aliases_selected_id_and_credentials(self):
        requests = []
        async def handler(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(404, json=dict(error=dict(message="No catalog")))
            body = json.loads(request.content)
            requests.append(body)
            self.assertEqual(request.headers["authorization"], "Bearer synthetic-key")
            if body.get("response_format"):
                return httpx.Response(400, json=dict(error=dict(message="Unsupported response_format", param="response_format")))
            return httpx.Response(200, json=completed(dict(title="Blue bicycle", summary="A blue bicycle is recorded.", keywords=["bicycle"], type="Observation")))
        self.service.model.transport = httpx.MockTransport(handler)
        await self.service.settings({**self.service.config.value, "provider": "api", "apiUrl": "https://example.test/custom/v1", "apiModel": "org/other-instruct:latest", "apiKey": "synthetic-key", "tokenLimitField": "max_completion_tokens", "outputTokens": 4096})
        draft = await self.service.draft("A blue bicycle is in the barn.")
        self.assertIn("A blue bicycle is in the barn.", draft["markdown"])
        self.assertEqual([body.get("response_format", {}).get("type", "prompt") for body in requests], ["json_schema", "json_object", "prompt"])
        self.assertTrue(all(body["model"] == "org/other-instruct:latest" and body["max_completion_tokens"] == 4096 and "reasoning_effort" not in body and "tools" not in body for body in requests))
        self.assertEqual(self.service.archive.inventory()["total"], 0)
        self.assertEqual(self.service.snapshot()["settings"]["apiKey"], "")

    async def test_authentication_failure_is_not_retried(self):
        calls = []
        def handler(request):
            calls.append(request)
            return httpx.Response(401, json=dict(error=dict(message="Unauthorized")))
        self.service.model.transport = httpx.MockTransport(handler)
        with self.assertRaisesRegex(ValueError, "Unauthorized"):
            await self.service.settings({**self.service.config.value, "provider": "api", "apiModel": "another-model"})
        self.assertEqual(len(calls), 1)

    async def test_cancellation_does_not_commit_a_partial_answer(self):
        await self.service.save("# Bicycle\n\nA blue bicycle is in the barn.")
        entered = asyncio.Event()
        async def handler(request):
            if request.url.path.endswith("/models"):
                return httpx.Response(200, json=dict(data=[]))
            entered.set()
            await asyncio.Event().wait()
        self.service.model.transport = httpx.MockTransport(handler)
        await self.service.settings({**self.service.config.value, "provider": "api", "apiModel": "another-model"})
        pending = asyncio.create_task(self.service.ask("What color is the bicycle?"))
        await asyncio.wait_for(entered.wait(), 5)
        await self.service.cancel()
        with self.assertRaises(asyncio.CancelledError):
            await pending
        self.assertEqual(self.service.chat["messages"], [])
        self.assertIsNone(self.service.operation)


if __name__ == "__main__":
    unittest.main()
