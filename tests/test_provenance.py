"""Original author terms must survive source and prompt redistribution intact."""
import hashlib
import importlib.util
import json
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location("project_notice_helpers", ROOT / "scripts/supplement_release_notices.py")
notices = importlib.util.module_from_spec(spec)
spec.loader.exec_module(notices)


class ProvenanceTests(unittest.TestCase):
    def test_original_license_credit_and_prompt_body_are_preserved(self):
        manifest = json.loads((ROOT / "UPSTREAM-PROVENANCE.json").read_text(encoding="utf-8"))
        raw = (ROOT / manifest["license"]["path"]).read_bytes()
        self.assertEqual(hashlib.sha256(raw).hexdigest(), manifest["license"]["sha256"])
        self.assertIn("Copyright \u00a9 2026 Adeptus Telvannus. All rights reserved.", raw.decode())
        prompts = ROOT / "src/aletheia_core/data/prompts"
        self.assertEqual((prompts / "LICENSE.txt").read_bytes(), raw)
        body = (prompts / "librarian.md").read_text(encoding="utf-8").split("-->\n\n", 1)[1]
        self.assertEqual(hashlib.sha256(body.encode()).hexdigest(), manifest["original_prompts_normalized_lf_sha256"]["librarian.md"])
        self.assertIn("AdeptTel1/Aletheia", (ROOT / "README.md").read_text(encoding="utf-8"))
        self.assertIn("GNU AFFERO GENERAL PUBLIC LICENSE", (ROOT / "LICENSES/AGPL-3.0-only.txt").read_text())

    def test_release_notice_update_keeps_original_notes_and_is_idempotent(self):
        block = notices.START + "\nCorrect upstream credit and exact license reference\n" + notices.END
        updated = notices.update_body("Original release notes and download instructions.", block)
        self.assertIn("Original release notes and download instructions.", updated)
        self.assertEqual(notices.update_body(updated, block), updated)
        self.assertEqual(updated.count(notices.START), 1)
