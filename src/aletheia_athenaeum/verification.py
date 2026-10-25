"""Offline release acceptance using real widgets and a disposable owned profile.

The executable runs this before publication. Synthetic responses exercise the
bundled API path without contacting an external provider or opening user data.
"""
from __future__ import annotations
import json
import math
import sys
import tempfile
import time
import traceback
from pathlib import Path

import httpx
from aletheia_core import __version__
from aletheia_core.config import Config, atomic_json
from aletheia_core.embeddings import Embeddings
from aletheia_core.service import Service
from .window import LibraryWindow


def verify(app, report: Path, embeddings: Path | None = None):
    result = dict(passed=False, version=__version__, frozen=bool(getattr(sys, "frozen", False)), checks=[])
    app.setQuitOnLastWindowClosed(False)

    def wait(condition, window, timeout=30):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            app.processEvents()
            if condition():
                return
            time.sleep(.01)  # Let the Python backend thread run as well as Qt.
        raise ValueError("Packaged workflow timed out: " + window.notice_label.text())

    def response(request):
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json=dict(data=[dict(id="verification/instruct")]))
        body = json.loads(request.content)
        source = json.loads(body["messages"][-1]["content"])
        if "retrieval" in source:
            value = dict(answer="The bicycle is blue.", sources=[source["retrieval"]["documents"][0]["id"]])
        else:
            value = dict(title="Blue bicycle", summary="A blue bicycle is stored in a green barn.", keywords=["bicycle"], type="Observation")
        return httpx.Response(200, json=dict(choices=[dict(finish_reason="stop", message=dict(content=json.dumps(value)))]))

    try:
        with tempfile.TemporaryDirectory(prefix="aletheia-packaged-acceptance-") as directory:
            home = Path(directory)
            def factory(home):
                service = Service(home, transport=httpx.MockTransport(response))
                service.config.save({**service.config.value, "autoStart": False})
                return service
            window = LibraryWindow(home, service_factory=factory)
            window.show()
            def idle():
                wait(lambda: window.snapshot and not window.job_count and not window.snapshot["busy"], window)
            def ask(text, length):
                window.show_page(0)
                window.question.setPlainText(text)
                if not window.ask_button.isEnabled():
                    raise ValueError("Packaged chat is disabled.")
                window.ask_button.click()
                wait(lambda: len(window.snapshot["chat"]["messages"]) == length, window)
                idle()
                return window.snapshot["chat"]["messages"][-1]
            try:
                wait(lambda: window.snapshot and window.snapshot["library"]["phase"] == "ready", window)
                assert "archive is empty" in ask("Do I have anything in the library?", 2)["content"]
                result["checks"].append("Qt startup and empty inventory without AI")
                original = "A blue bicycle is stored in the green barn."
                window.show_page(1)
                window.source_input.setPlainText(original)
                window.save_original_button.click()
                wait(lambda: len(window.snapshot["documents"]) == 1, window)
                idle()
                identifier = window.snapshot["documents"][0]["id"]
                answer = ask("Can you check if I have anything in the collection?", 4)
                assert "contains 1 document" in answer["content"] and answer["sources"][0]["id"] == identifier
                result["checks"].append("SQLite FTS5, Markdown save and populated inventory")
                window.open_document(identifier)
                wait(lambda: bool(window.active_document), window)
                idle()
                window.title_input.setText("Packaged bicycle")
                window.rename_button.click()
                wait(lambda: window.active_document["title"] == "Packaged bicycle", window)
                idle()
                assert original in window.active_document["content"]
                window.document_dialog.close()
                window.toggle_theme()
                wait(lambda: window.snapshot["settings"]["theme"] == "dark", window)
                assert Config(home).value["theme"] == "dark"
                result["checks"].append("Stable document title edits and saved theme")
                settings = {**window.snapshot["settings"], "provider": "api", "apiUrl": "https://example.test/v1", "apiModel": "verification/instruct", "autoStart": False}
                window.request("settings", [settings])
                wait(lambda: window.snapshot["model"]["phase"] == "ready", window)
                idle()
                window.show_page(1)
                window.prepare_button.click()
                wait(lambda: bool(window.draft_input.toPlainText()), window)
                idle()
                assert original in window.draft_input.toPlainText()
                answer = ask("What color is the bicycle?", 6)
                assert "blue" in answer["content"] and answer["sources"][0]["id"] == identifier
                result["checks"].append("API transport, complete draft and validated source answer")
                if embeddings:
                    encoder = Embeddings(embeddings)
                    vector = encoder.embed(original)
                    assert len(vector) == 384 and all(math.isfinite(x) for x in vector)
                    assert abs(sum(x*x for x in vector) - 1) < .0001
                    result["checks"].append("Bundled NumPy, Tokenizers and real BGE ONNX inference")
                if getattr(sys, "frozen", False):
                    assert (Path(sys._MEIPASS) / "licenses" / "Aletheia" / "LICENSE").is_file()
                    result["checks"].append("Bundled license notices")
            finally:
                window.document_dialog.close()
                window.close()
                wait(lambda: not window.backend.isRunning(), window)
                result["checks"].append("Owned backend shutdown and profile cleanup")
                window.deleteLater()
                app.processEvents()
        result["passed"] = True
    except Exception:
        result["error"] = traceback.format_exc()
    atomic_json(report.resolve(), result)
    return 0 if result["passed"] else 1
