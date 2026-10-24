"""Real Qt widgets/signals/worker checks with isolated files and a local fake API."""
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
if os.name == "nt":
    os.environ.setdefault("QT_QPA_FONTDIR", str(Path(os.environ.get("WINDIR", "C:/Windows")) / "Fonts"))
from PySide6.QtCore import Qt
from PySide6.QtTest import QTest, QSignalSpy
from PySide6.QtWidgets import QApplication, QScrollArea
from aletheia_core.config import Config
from aletheia_core.service import Service
from aletheia_athenaeum.window import LibraryWindow


class ModelFixture(BaseHTTPRequestHandler):
    requests = []
    def log_message(self, *args):
        pass

    def send_json(self, value):
        body = json.dumps(value).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        self.send_json(dict(data=[dict(id="test/native-instruct")]))

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        self.requests.append(body)
        source = json.loads(body["messages"][-1]["content"])
        if "retrieval" in source:
            value = dict(answer="The native fixture records a blue bicycle in a green barn.", sources=[source["retrieval"]["documents"][0]["id"]])
        else:
            value = dict(title="Native API draft", summary="A synthetic bicycle fixture is recorded.", keywords=["bicycle"], type="Observation")
        self.send_json(dict(model="test/native-instruct-resolved", choices=[dict(finish_reason="stop", message=dict(content=json.dumps(value)))]))


class NativeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def spin(self, condition, timeout=10):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            self.app.processEvents()
            if condition():
                return
            # Yield Python's GIL as well as pumping Qt: the service and fixture
            # server run in Python threads, which Qt's qWait can starve on Windows.
            time.sleep(.01)
        self.fail("Native UI did not reach the expected state: " + self.window.notice_label.text())

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="aletheia-native-")
        self.home = Path(self.temp.name).resolve()
        def factory(home):
            service = Service(home)
            service.config.save({**service.config.value, "autoStart": False})
            return service
        self.window = LibraryWindow(self.home, service_factory=factory)
        self.window.show()
        self.spin(lambda: bool(self.window.snapshot and self.window.snapshot["library"]["phase"] == "ready"))

    def tearDown(self):
        self.window.close()
        self.spin(lambda: not self.window.backend.isRunning())
        self.window.deleteLater()
        self.app.processEvents()
        self.assertEqual(self.home.parent, Path(tempfile.gettempdir()).resolve())
        self.assertTrue(self.home.name.startswith("aletheia-native-"))
        self.temp.cleanup()

    def click(self, widget):
        self.assertTrue(widget.isEnabled(), widget.text() + " must be enabled")
        parent = widget.parentWidget()
        while parent:
            if isinstance(parent, QScrollArea):
                parent.ensureWidgetVisible(widget)
            parent = parent.parentWidget()
        self.app.processEvents()
        signal = QSignalSpy(widget.clicked)
        QTest.mouseClick(widget, Qt.MouseButton.LeftButton)
        self.app.processEvents()
        self.assertEqual(signal.count(), 1, f"{widget.text()} did not receive its click; visible={widget.isVisible()}, rect={widget.geometry()}")

    def idle(self):
        self.spin(lambda: not self.window.job_count and not self.window.snapshot["busy"])

    def screenshot(self, name):
        directory = Path(__file__).resolve().parents[1] / "test-output" / "native"
        directory.mkdir(parents=True, exist_ok=True)
        self.app.processEvents()
        self.assertTrue(self.window.grab().save(str(directory / (name + ".png"))))

    def test_existence_questions_from_chat_without_an_ai(self):
        # Exercise typing/submitting through actual widgets, not the overview
        # shortcut. No model or API is configured in this disposable profile.
        self.window.show_page(0)
        self.window.question.setPlainText("Do I have anything in the library?")
        self.click(self.window.ask_button)
        self.spin(lambda: len(self.window.snapshot["chat"]["messages"]) == 2)
        self.idle()
        self.assertIn("archive is empty", self.window.snapshot["chat"]["messages"][-1]["content"])

        content = "# Physical limitations\n\nA reflection on imagination and memory.\n\n## Metadata\nID: existence-note\n"
        (self.home / "knowledge" / "external.md").write_text(content, encoding="utf-8")
        self.window.question.setPlainText("Can you check if I have anything in the collection?")
        self.click(self.window.ask_button)
        self.spin(lambda: len(self.window.snapshot["chat"]["messages"]) == 4)
        self.idle()
        answer = self.window.snapshot["chat"]["messages"][-1]
        self.assertIn("contains 1 document", answer["content"])
        self.assertEqual(answer["sources"][0]["id"], "existence-note")
        self.assertEqual(self.window.snapshot["model"]["phase"], "stopped")

    def test_native_archive_and_api_workflow_without_webengine_or_server(self):
        self.assertNotIn("PySide6.QtWebEngineWidgets", sys.modules)
        self.assertNotIn("fastapi", sys.modules)
        self.assertNotIn("uvicorn", sys.modules)
        self.assertNotIn("numpy", sys.modules)
        self.screenshot("first-run")
        self.window.show_page(1)
        original = "# Native verification\n\nThis synthetic fixture records a blue bicycle in a green barn."
        self.window.source_input.setPlainText(original)
        self.click(self.window.save_original_button)
        self.spin(lambda: len(self.window.snapshot["documents"]) == 1)
        self.idle()
        identifier = self.window.snapshot["documents"][0]["id"]
        self.click(self.window.theme_button)
        self.spin(lambda: self.window.snapshot["settings"]["theme"] == "dark")
        self.assertEqual(Config(self.home).value["theme"], "dark")
        self.window.show_page(0)
        self.click(self.window.overview_button)
        self.spin(lambda: len(self.window.snapshot["chat"]["messages"]) == 2)
        self.idle()
        self.assertEqual(self.window.snapshot["chat"]["messages"][-1]["sources"][0]["id"], identifier)
        self.screenshot("overview-dark")
        self.window.show_page(2)
        self.window.open_document(identifier)
        self.spin(lambda: self.window.document_dialog.isVisible())
        self.idle()
        self.window.title_input.setText("Renamed native fixture")
        self.click(self.window.rename_button)
        self.spin(lambda: self.window.document_title.text() == "Renamed native fixture")
        self.idle()
        self.assertEqual(self.window.active_document["id"], identifier)
        self.assertIn("green barn", self.window.document_content.toPlainText())
        self.window.document_dialog.close()

        fixture = ThreadingHTTPServer(("127.0.0.1", 0), ModelFixture)
        ModelFixture.requests = []
        thread = threading.Thread(target=fixture.serve_forever, daemon=True)
        thread.start()
        try:
            self.window.show_page(3)
            self.window.provider.setCurrentIndex(self.window.provider.findData("api"))
            self.window.api_url.setText(f"http://127.0.0.1:{fixture.server_port}/v1")
            self.window.api_model.setCurrentText("")
            self.click(self.window.fetch_models_button)
            self.spin(lambda: self.window.api_model.currentText() == "test/native-instruct")
            self.idle()
            self.window.output_tokens.setCurrentIndex(self.window.output_tokens.findData(4096))
            self.click(self.window.save_settings_button)
            self.spin(lambda: self.window.snapshot["model"]["phase"] == "ready")
            self.idle()
            self.assertEqual(Config(self.home).value["apiModel"], "test/native-instruct")
            self.assertEqual(Config(self.home).value["outputTokens"], 4096)
            self.screenshot("settings-dark")
            self.window.show_page(1)
            self.click(self.window.prepare_button)
            self.spin(lambda: bool(self.window.draft_input.toPlainText()))
            self.idle()
            self.assertIn(original, self.window.draft_input.toPlainText())
            self.screenshot("archivist-dark")
            self.window.show_page(0)
            self.window.question.setPlainText("What color is the bicycle?")
            self.click(self.window.ask_button)
            self.spin(lambda: len(self.window.snapshot["chat"]["messages"]) == 4)
            self.idle()
            answer = self.window.snapshot["chat"]["messages"][-1]
            self.assertIn("blue bicycle", answer["content"])
            self.assertEqual(answer["sources"][0]["id"], identifier)
            self.assertEqual(len(ModelFixture.requests), 2)
            self.assertTrue(all(item["model"] == "test/native-instruct" and item["max_tokens"] == 4096 for item in ModelFixture.requests))
            self.click(self.window.theme_button)
            self.spin(lambda: self.window.snapshot["settings"]["theme"] == "light")
            self.screenshot("librarian-light")
        finally:
            fixture.shutdown()
            fixture.server_close()
            thread.join(timeout=5)


if __name__ == "__main__":
    unittest.main()
