"""Publication must reject a missing executable, incomplete upload or tampering."""
import hashlib
import importlib.util
import tempfile
import unittest
from pathlib import Path

spec = importlib.util.spec_from_file_location("athenaeum_publisher", Path(__file__).resolve().parents[1] / "packaging/publish_release.py")
publisher = importlib.util.module_from_spec(spec)
spec.loader.exec_module(publisher)


class ReleaseTests(unittest.TestCase):
    def test_complete_assets_and_remote_digests_are_required(self):
        with tempfile.TemporaryDirectory(prefix="aletheia-release-test-") as temporary:
            home = Path(temporary).resolve()
            self.assertEqual(home.parent, Path(tempfile.gettempdir()).resolve())
            with self.assertRaises(ValueError):
                publisher.asset_plan(home, "0.1.2")
            names = ["aletheia_athenaeum-0.1.2-py3-none-any.whl", "aletheia_athenaeum-0.1.2.tar.gz",
                     "Aletheia-Athenaeum-0.1.2-windows-x64.exe", "Aletheia-Athenaeum-0.1.2-windows-x64-licenses.zip"]
            for name in names:
                (home / name).write_bytes(name.encode())
            hashes = publisher.asset_plan(home, "0.1.2")
            self.assertEqual(len(hashes), 5)
            self.assertEqual(hashes[names[2]], hashlib.sha256(names[2].encode()).hexdigest())
            self.assertIn(names[2], (home / "SHA256SUMS.txt").read_text())
            assets = [dict(name=name, state="uploaded", size=(home / name).stat().st_size, digest="sha256:" + value) for name, value in hashes.items()]
            publisher.verify_assets(dict(assets=assets), home, hashes)
            for changed in (dict(size=1), dict(state="starter"), dict(digest="sha256:" + "0" * 64)):
                with self.subTest(changed=changed), self.assertRaises(ValueError):
                    publisher.verify_assets(dict(assets=[{**assets[0], **changed}, *assets[1:]]), home, hashes)
            with self.assertRaises(ValueError):
                publisher.verify_assets(dict(assets=[*assets, assets[0]]), home, hashes)
