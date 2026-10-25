"""Native QWidget interface: archive conversation, editing, browsing and settings.

All source/model text uses plain text widgets. Source buttons carry stable IDs;
title edits carry the document revision read when the dialog was opened.
"""
from __future__ import annotations
import json
import secrets
from pathlib import Path

from PySide6.QtCore import Qt, QTimer, QUrl
from PySide6.QtGui import QColor, QDesktopServices, QFont, QPalette
from PySide6.QtWidgets import (QApplication, QCheckBox, QComboBox, QDialog, QFileDialog,
    QFormLayout, QFrame, QHBoxLayout, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QPlainTextEdit, QPushButton, QScrollArea, QSizePolicy, QSplitter,
    QStackedWidget, QVBoxLayout, QWidget)

from aletheia_core.config import atomic_write, data_home
from .backend import Backend


def label(text, name="", wrap=False):
    widget = QLabel(text)
    widget.setTextFormat(Qt.TextFormat.PlainText)
    widget.setWordWrap(wrap)
    if name:
        widget.setObjectName(name)
    return widget


def button(text, callback, primary=False):
    widget = QPushButton(text)
    widget.setCursor(Qt.CursorShape.PointingHandCursor)
    if primary:
        widget.setObjectName("primary")
    widget.clicked.connect(callback)
    return widget


class LibraryWindow(QMainWindow):
    def __init__(self, home=None, service_factory=None):
        super().__init__()
        self.setWindowTitle("Aletheia Athenaeum")
        self.resize(1280, 880)
        self.setMinimumSize(960, 680)
        self.home = Path(home) if home else data_home("AletheiaAthenaeum")
        self.snapshot, self.callbacks = None, {}
        self.chat_stamp = self.documents_stamp = self.settings_stamp = ""
        self.current_theme, self.closing, self.allow_close = None, False, False
        self.active_document = None
        self.job_count = 0
        self.build()
        kwargs = dict(service_factory=service_factory) if service_factory else {}
        self.backend = Backend(self.home, parent=self, **kwargs)
        self.backend.state.connect(self.render)
        self.backend.result.connect(self.completed)
        self.backend.error.connect(self.failed)
        self.backend.finished.connect(self.backend_finished)
        self.backend.start()
        self.apply_theme("light")

    def build(self):
        root = QWidget()
        self.setCentralWidget(root)
        layout = QHBoxLayout(root)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        sidebar = QFrame()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(230)
        side = QVBoxLayout(sidebar)
        side.setContentsMargins(22, 30, 22, 22)
        side.addWidget(label("Aletheia\nAthenaeum", "brand"))
        side.addWidget(label("PERSONAL KNOWLEDGE LIBRARY", "eyebrow"))
        side.addSpacing(45)
        self.navigation = {}
        for index, (name, title) in enumerate((("librarian", "Librarian"), ("archivist", "Archivist"), ("library", "Your library"), ("settings", "Settings"))):
            widget = button(title, lambda checked=False, i=index: self.show_page(i))
            widget.setObjectName("navigation")
            self.navigation[name] = widget
            side.addWidget(widget)
        side.addStretch()
        self.theme_button = button("Dark mode", self.toggle_theme)
        side.addWidget(self.theme_button)
        self.side_status = label("Opening your library...", "subtle", True)
        side.addWidget(self.side_status)
        side.addWidget(label("ATHENAEUM  0.1.1", "eyebrow"))
        layout.addWidget(sidebar)
        main = QWidget()
        body = QVBoxLayout(main)
        body.setContentsMargins(30, 24, 30, 24)
        header = QHBoxLayout()
        self.page_label = label("Librarian", "page-label")
        header.addWidget(self.page_label)
        header.addStretch()
        self.engine_label = button("Set up your AI", lambda: self.show_page(3))
        self.engine_label.setMaximumWidth(540)
        header.addWidget(self.engine_label)
        body.addLayout(header)
        self.notice_label = label("", "notice", True)
        self.notice_label.setVisible(False)
        body.addWidget(self.notice_label)
        progress_row = QHBoxLayout()
        self.progress_label = label("Opening your library...", "subtle", True)
        progress_row.addWidget(self.progress_label, 1)
        self.cancel_button = button("Stop", lambda: self.request("cancel"))
        progress_row.addWidget(self.cancel_button)
        body.addLayout(progress_row)
        self.pages = QStackedWidget()
        self.pages.addWidget(self.librarian_page())
        self.pages.addWidget(self.archivist_page())
        self.pages.addWidget(self.library_page())
        self.pages.addWidget(self.settings_page())
        body.addWidget(self.pages, 1)
        layout.addWidget(main, 1)
        self.build_document_dialog()

    def heading(self, box, title, description):
        box.addWidget(label(title, "hero"))
        box.addWidget(label(description, "subtle", True))
        box.addSpacing(16)

    def librarian_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.heading(box, "Search the archive", "Ask about your saved documents. Accepted answers include links to retrieved sources.")
        actions = QHBoxLayout()
        self.overview_button = button("Archive overview", lambda: self.request("ask", ["What does my archive contain?"]))
        actions.addWidget(self.overview_button)
        self.new_chat_button = button("New conversation", lambda: self.request("newChat"))
        actions.addWidget(self.new_chat_button)
        actions.addStretch()
        box.addLayout(actions)
        self.chat_scroll = QScrollArea()
        self.chat_scroll.setWidgetResizable(True)
        self.chat_widget = QWidget()
        self.chat_layout = QVBoxLayout(self.chat_widget)
        self.chat_layout.setAlignment(Qt.AlignmentFlag.AlignTop)
        self.chat_scroll.setWidget(self.chat_widget)
        box.addWidget(self.chat_scroll, 1)
        self.question = QPlainTextEdit()
        self.question.setPlaceholderText("What would you like to find in your library?")
        self.question.setMaximumHeight(95)
        self.question.textChanged.connect(self.update_controls)
        box.addWidget(self.question)
        self.ask_button = button("Ask Librarian", self.ask, True)
        box.addWidget(self.ask_button, alignment=Qt.AlignmentFlag.AlignRight)
        box.addWidget(label("Selected retrieval may not find every relevant document.", "subtle"))
        return page

    def archivist_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.heading(box, "Prepare a document", "Create metadata from your text. Review the complete draft before saving it.")
        splitter = QSplitter(Qt.Orientation.Horizontal)
        left, right = QWidget(), QWidget()
        first, second = QVBoxLayout(left), QVBoxLayout(right)
        first.addWidget(label("What would you like to preserve?"))
        self.source_input = QPlainTextEdit()
        self.source_input.setPlaceholderText("Paste or write something you want to remember...")
        self.source_input.textChanged.connect(self.update_controls)
        first.addWidget(self.source_input, 1)
        self.prepare_button = button("Prepare document", self.prepare, True)
        self.save_original_button = button("Save as written", lambda: self.request("save", [self.source_input.toPlainText()], lambda value: self.notice("Saved to your library.")))
        first.addWidget(self.prepare_button)
        first.addWidget(self.save_original_button)
        second.addWidget(label("Review your document - editable Markdown"))
        self.draft_input = QPlainTextEdit()
        self.draft_input.setPlaceholderText("Your prepared document will appear here. You can edit it before saving.")
        self.draft_input.textChanged.connect(self.update_controls)
        second.addWidget(self.draft_input, 1)
        self.save_draft_button = button("Save to library", lambda: self.request("save", [self.draft_input.toPlainText()], lambda value: self.notice("Saved to your library.")), True)
        second.addWidget(self.save_draft_button)
        self.draft_status = label("", "subtle", True)
        second.addWidget(self.draft_status)
        splitter.addWidget(left)
        splitter.addWidget(right)
        box.addWidget(splitter, 1)
        return page

    def library_page(self):
        page = QWidget()
        box = QVBoxLayout(page)
        self.heading(box, "Archived documents", "Browse original Markdown and edit titles while keeping IDs and filenames stable.")
        row = QHBoxLayout()
        self.import_files_button = button("Import documents", self.import_files, True)
        self.import_folder_button = button("Import folder", self.import_folder)
        row.addWidget(self.import_files_button)
        row.addWidget(self.import_folder_button)
        row.addStretch()
        self.refresh_button = button("Refresh", lambda: self.request("refresh"))
        row.addWidget(self.refresh_button)
        row.addWidget(button("Open archive folder", self.open_folder))
        box.addLayout(row)
        self.filter_input = QLineEdit()
        self.filter_input.setPlaceholderText("Filter documents by title...")
        self.filter_input.textChanged.connect(lambda: self.render_documents(force=True))
        box.addWidget(self.filter_input)
        self.document_list = QListWidget()
        self.document_list.itemDoubleClicked.connect(lambda item: self.open_document(item.data(Qt.ItemDataRole.UserRole)))
        box.addWidget(self.document_list, 1)
        box.addWidget(button("Open selected document", self.open_selected))
        return page

    def combo(self, values):
        widget = QComboBox()
        for title, value in values:
            widget.addItem(title, value)
        return widget

    def settings_page(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        page = QWidget()
        scroll.setWidget(page)
        box = QVBoxLayout(page)
        self.heading(box, "Application settings", "Run a compatible GGUF here, or connect to a local or hosted Chat Completions API.")
        form = QFormLayout()
        form.setVerticalSpacing(15)
        self.provider = self.combo([("Local GGUF model", "embedded"), ("API connection", "api")])
        self.provider.currentIndexChanged.connect(self.provider_fields)
        form.addRow("AI connection", self.provider)
        self.local_fields = QWidget()
        local = QVBoxLayout(self.local_fields)
        local.setContentsMargins(0, 0, 0, 0)
        self.model_path = label("No model selected", "subtle", True)
        self.choose_model_button = button("Choose GGUF file", self.choose_model)
        self.download_button = button("Download default Qwen - 5.5 GB", lambda: self.request("downloadModel"))
        local.addWidget(self.model_path)
        local.addWidget(self.choose_model_button)
        local.addWidget(self.download_button)
        local.addWidget(label("Use an instruction/chat GGUF supported by llama.cpp, with an embedded chat template and enough available memory.", "subtle", True))
        form.addRow("Local model", self.local_fields)
        self.api_fields = QWidget()
        api = QFormLayout(self.api_fields)
        api.setContentsMargins(0, 0, 0, 0)
        self.preset = self.combo([("Custom / hosted API", "custom"), ("LM Studio", "lmstudio"), ("Ollama", "ollama")])
        self.preset.activated.connect(self.preset_changed)
        api.addRow("Preset", self.preset)
        self.api_url = QLineEdit()
        self.api_url.setPlaceholderText("http://127.0.0.1:1234/v1")
        api.addRow("API base address", self.api_url)
        self.api_key = QLineEdit()
        self.api_key.setEchoMode(QLineEdit.EchoMode.Password)
        api.addRow("API key", self.api_key)
        self.clear_key = QCheckBox("Clear the saved API key")
        api.addRow("", self.clear_key)
        self.api_model = QComboBox()
        self.api_model.setEditable(True)
        self.api_model.setInsertPolicy(QComboBox.InsertPolicy.NoInsert)
        api.addRow("Model ID", self.api_model)
        self.fetch_models_button = button("Fetch available models", self.fetch_models)
        api.addRow("", self.fetch_models_button)
        api.addRow(label("Use a Chat Completions base URL, including its API path (usually /v1). Enter a model ID manually if discovery is unavailable. Remote APIs receive the current input and retrieved excerpts.", "subtle", True))
        form.addRow("API", self.api_fields)
        self.acceleration = self.combo([("Automatic GPU acceleration", "auto"), ("CPU only", "cpu")])
        form.addRow("Acceleration", self.acceleration)
        self.search_mode = self.combo([("Keyword search - portable", "keyword"), ("Semantic hybrid - optional dependencies", "semantic")])
        form.addRow("Archive search", self.search_mode)
        self.context = self.combo([(f"{value:,} tokens", value) for value in (4096, 8192, 16384, 32768, 65536, 131072, 262144)])
        form.addRow("Model context size", self.context)
        self.output_tokens = self.combo([(f"{value:,} tokens", value) for value in (1536, 4096, 8192, 16384, 32768)])
        form.addRow("Response token budget", self.output_tokens)
        self.response_mode = self.combo([("Automatic - schema, JSON, prompt", "auto"), ("JSON schema", "json_schema"), ("JSON mode", "json_object"), ("Prompt only", "prompt")])
        form.addRow("Structured responses", self.response_mode)
        self.token_field = self.combo([("max_tokens", "max_tokens"), ("max_completion_tokens", "max_completion_tokens")])
        form.addRow("API output limit parameter", self.token_field)
        self.runtime_path = QLineEdit()
        self.runtime_path.setPlaceholderText("Optional native llama-server path; blank downloads the platform's engine")
        form.addRow("Custom engine executable", self.runtime_path)
        self.auto_start = QCheckBox("Load/connect when Athenaeum opens")
        form.addRow("", self.auto_start)
        box.addLayout(form)
        box.addWidget(label("Keyword search needs no native ML libraries. Semantic mode requires the [semantic] extra and downloads BGE once. Choose context/budget values supported by your model. Every response format keeps the same output/citation checks.", "subtle", True))
        actions = QHBoxLayout()
        self.save_settings_button = button("Save and connect", self.save_settings, True)
        self.reconnect_button = button("Reconnect saved connection", lambda: self.request("connect"))
        actions.addWidget(self.save_settings_button)
        actions.addWidget(self.reconnect_button)
        box.addLayout(actions)
        self.storage_path = label(str(self.home), "subtle", True)
        box.addWidget(self.storage_path)
        box.addWidget(button("Open archive folder", self.open_folder))
        box.addStretch()
        return scroll

    def build_document_dialog(self):
        self.document_dialog = QDialog(self)
        self.document_dialog.setWindowTitle("Archive document")
        self.document_dialog.resize(850, 690)
        box = QVBoxLayout(self.document_dialog)
        self.document_title = label("", "hero", True)
        box.addWidget(self.document_title)
        self.document_id = label("", "subtle", True)
        box.addWidget(self.document_id)
        row = QHBoxLayout()
        self.title_input = QLineEdit()
        self.title_input.setMaxLength(400)
        row.addWidget(self.title_input, 1)
        self.rename_button = button("Save title", self.rename_document)
        row.addWidget(self.rename_button)
        box.addLayout(row)
        self.document_content = QPlainTextEdit()
        self.document_content.setReadOnly(True)
        box.addWidget(self.document_content, 1)
        footer = QHBoxLayout()
        footer.addWidget(button("Export Markdown", self.export_document))
        footer.addStretch()
        footer.addWidget(button("Close", self.document_dialog.close))
        box.addLayout(footer)

    def show_page(self, index):
        self.pages.setCurrentIndex(index)
        self.page_label.setText(["Librarian", "Archivist", "Your library", "Settings"][index])

    def request(self, name, args=None, callback=None):
        if self.closing:
            return
        identifier = secrets.token_hex(8)
        self.callbacks[identifier] = callback
        if name != "theme":
            self.job_count += 1
        self.callbacks[identifier + ":name"] = name
        self.update_controls()
        self.backend.submit(identifier, name, args or [])

    def completed(self, identifier, value):
        callback = self.callbacks.pop(identifier, None)
        name = self.callbacks.pop(identifier + ":name", None)
        if name and name != "theme":
            self.job_count = max(0, self.job_count - 1)
        if callback:
            callback(value)
        self.update_controls()

    def failed(self, identifier, message):
        self.callbacks.pop(identifier, None)
        name = self.callbacks.pop(identifier + ":name", None)
        if name and name != "theme":
            self.job_count = max(0, self.job_count - 1)
        self.notice(message)
        self.update_controls()

    def notice(self, message):
        self.notice_label.setText(message)
        self.notice_label.setVisible(bool(message))

    def ask(self):
        text = self.question.toPlainText()
        self.request("ask", [text], lambda value: self.question.clear())

    def prepare(self):
        def accepted(value):
            self.draft_input.setPlainText(value["markdown"])
            self.draft_status.setText("Review before saving - metadata uses excerpts" if value["source_excerpted"] else "Review before saving")
        self.request("draft", [self.source_input.toPlainText()], accepted)

    def open_document(self, identifier):
        self.request("document", [identifier], self.display_document)

    def open_selected(self):
        if self.document_list.currentItem():
            self.open_document(self.document_list.currentItem().data(Qt.ItemDataRole.UserRole))

    def display_document(self, record):
        self.active_document = record
        self.document_title.setText(record["title"])
        self.document_id.setText(record["id"])
        self.title_input.setText(record["title"])
        self.document_content.setPlainText(record["content"])
        self.document_dialog.show()
        self.document_dialog.raise_()

    def rename_document(self):
        if self.active_document:
            self.request("renameTitle", [self.active_document["id"], self.title_input.text(), self.active_document["revision"]], self.display_document)

    def export_document(self):
        if self.active_document:
            filename, _ = QFileDialog.getSaveFileName(self, "Export document", self.active_document["id"] + ".md", "Markdown (*.md)")
            if filename:
                try:
                    atomic_write(Path(filename), self.active_document["content"])
                    self.notice("Exported Markdown document.")
                except OSError as error:
                    self.notice(str(error))

    def import_files(self):
        files, _ = QFileDialog.getOpenFileNames(self, "Import Markdown documents", "", "Markdown (*.md)")
        if files:
            self.request("importPaths", [files], self.imported)

    def import_folder(self):
        folder = QFileDialog.getExistingDirectory(self, "Import a Markdown folder")
        if folder:
            self.request("importPaths", [[folder]], self.imported)

    def imported(self, value):
        self.notice(f"Imported {value['imported']} documents; {value['duplicates']} already present." + ("\n" + "\n".join(value["errors"]) if value["errors"] else ""))

    def choose_model(self):
        filename, _ = QFileDialog.getOpenFileName(self, "Choose an instruction/chat GGUF model", "", "GGUF model (*.gguf)")
        if filename:
            self.request("chooseModel", [filename])

    def open_folder(self):
        self.request("openFolder", callback=lambda path: QDesktopServices.openUrl(QUrl.fromLocalFile(path)))

    def provider_fields(self):
        if hasattr(self, "local_fields"):
            local = self.provider.currentData() == "embedded"
            self.local_fields.setVisible(local)
            self.api_fields.setVisible(not local)

    def preset_changed(self):
        address = {"lmstudio": "http://127.0.0.1:1234/v1", "ollama": "http://localhost:11434/v1"}.get(self.preset.currentData())
        if address:
            self.api_url.setText(address)
        self.api_key.clear()
        self.api_model.clear()
        self.clear_key.setChecked(True)

    def fetch_models(self):
        value = dict(apiUrl=self.api_url.text(), apiKey=self.api_key.text(), clearApiKey=self.clear_key.isChecked())
        def accepted(models):
            selected = self.api_model.currentText()
            self.api_model.clear()
            self.api_model.addItems(models)
            self.api_model.setCurrentText(selected or (models[0] if len(models) == 1 else ""))
            self.notice(f"{len(models)} models available. Choose or enter the model ID.")
        self.request("models", [value], accepted)

    def save_settings(self):
        if not self.snapshot:
            return
        value = {**self.snapshot["settings"], "provider": self.provider.currentData(), "apiUrl": self.api_url.text().strip(), "apiKey": self.api_key.text(), "clearApiKey": self.clear_key.isChecked(), "apiModel": self.api_model.currentText().strip(), "gpu": self.acceleration.currentData(), "searchMode": self.search_mode.currentData(), "contextSize": self.context.currentData(), "outputTokens": self.output_tokens.currentData(), "responseMode": self.response_mode.currentData(), "tokenLimitField": self.token_field.currentData(), "runtimePath": self.runtime_path.text().strip(), "autoStart": self.auto_start.isChecked()}
        self.request("settings", [value])

    def toggle_theme(self):
        if self.snapshot:
            theme = "dark" if self.snapshot["settings"]["theme"] == "light" else "light"
            self.apply_theme(theme)
            self.request("theme", [theme])

    def render(self, state):
        self.snapshot = state
        self.apply_theme(state["settings"]["theme"])
        model = state["model"]
        self.engine_label.setText((model.get("model") or "Your AI") + (" - ready" if model["phase"] == "ready" else "") if model["phase"] == "ready" else {"setup": "Set up your AI", "loading": "Loading your AI...", "error": "Connection needs attention"}.get(model["phase"], "AI not loaded"))
        self.engine_label.setToolTip(model["message"])
        self.side_status.setText(state["library"]["message"])
        progress = state.get("progress")
        self.progress_label.setText(progress.get("message", "") if progress else model["message"] if model["phase"] in ("loading", "error") else state["library"]["message"] if state["library"]["phase"] != "ready" else "")
        self.render_chat()
        self.render_documents()
        self.render_settings()
        self.update_controls()

    def render_chat(self):
        stamp = json.dumps(self.snapshot["chat"], sort_keys=True)
        if stamp == self.chat_stamp:
            return
        self.chat_stamp = stamp
        while self.chat_layout.count():
            item = self.chat_layout.takeAt(0)
            if item.widget():
                item.widget().deleteLater()
        messages = self.snapshot["chat"]["messages"]
        if not messages:
            self.chat_layout.addWidget(label("Ask a question, or open Archive overview to see what is saved.", "subtle", True))
        for message in messages:
            row = QFrame()
            row.setObjectName("message")
            box = QVBoxLayout(row)
            box.addWidget(label("YOU" if message["role"] == "user" else "LIBRARIAN", "eyebrow"))
            text = label(message["content"], "answer", True)
            text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
            box.addWidget(text)
            for source in message.get("sources", []):
                box.addWidget(button(source["title"], lambda checked=False, identifier=source["id"]: self.open_document(identifier)), alignment=Qt.AlignmentFlag.AlignLeft)
            self.chat_layout.addWidget(row)
        QTimer.singleShot(0, lambda: self.chat_scroll.verticalScrollBar().setValue(self.chat_scroll.verticalScrollBar().maximum()))

    def render_documents(self, force=False):
        if not self.snapshot:
            return
        query = self.filter_input.text().strip().lower()
        stamp = json.dumps(self.snapshot["documents"], sort_keys=True) + query
        if not force and stamp == self.documents_stamp:
            return
        self.documents_stamp = stamp
        self.document_list.clear()
        for document in self.snapshot["documents"]:
            if query not in document["title"].lower():
                continue
            item = QListWidgetItem(document["title"] + "\n" + document["metadata"].get("type", "Document"))
            item.setData(Qt.ItemDataRole.UserRole, document["id"])
            self.document_list.addItem(item)

    def set_combo(self, widget, value):
        index = widget.findData(value)
        if index < 0:
            widget.addItem(str(value), value)
            index = widget.count() - 1
        widget.setCurrentIndex(index)

    def render_settings(self):
        settings = self.snapshot["settings"]
        stamp = json.dumps({key: value for key, value in settings.items() if key != "theme"}, sort_keys=True)
        if stamp == self.settings_stamp:
            return
        self.settings_stamp = stamp
        for widget, name in ((self.provider, "provider"), (self.acceleration, "gpu"), (self.search_mode, "searchMode"), (self.context, "contextSize"), (self.output_tokens, "outputTokens"), (self.response_mode, "responseMode"), (self.token_field, "tokenLimitField")):
            self.set_combo(widget, settings[name])
        self.api_url.setText(settings["apiUrl"])
        self.api_key.clear()
        self.api_key.setPlaceholderText("Saved key - leave blank to keep" if settings["hasApiKey"] else "API key, if required")
        self.clear_key.setChecked(False)
        self.api_model.setCurrentText(settings["apiModel"])
        self.model_path.setText(settings["modelPath"] or "No local model selected")
        self.runtime_path.setText(settings["runtimePath"])
        self.auto_start.setChecked(settings["autoStart"])
        self.storage_path.setText(self.snapshot["home"])
        self.provider_fields()

    def update_controls(self):
        if not hasattr(self, "save_settings_button"):
            return
        state = self.snapshot
        busy = bool(self.job_count or (state and state["busy"]))
        ready = bool(state and state["model"]["phase"] == "ready")
        library = bool(state and state["library"]["phase"] == "ready")
        for widget in (self.save_settings_button, self.reconnect_button, self.fetch_models_button, self.choose_model_button, self.download_button, self.import_files_button, self.import_folder_button, self.refresh_button, self.new_chat_button, self.rename_button):
            widget.setEnabled(bool(state) and not busy)
        # Inventory questions need only the library. The service owns deciding
        # whether a question needs a generation model and starting it if so.
        self.ask_button.setEnabled(not busy and library and bool(self.question.toPlainText().strip()))
        self.prepare_button.setEnabled(not busy and ready and bool(self.source_input.toPlainText().strip()))
        self.save_original_button.setEnabled(not busy and library and bool(self.source_input.toPlainText().strip()))
        self.save_draft_button.setEnabled(not busy and library and bool(self.draft_input.toPlainText().strip()))
        self.overview_button.setEnabled(not busy and library)
        self.cancel_button.setEnabled(bool(state and (state["busy"] or state["model"]["phase"] == "loading")))
        self.theme_button.setEnabled(bool(state))

    def apply_theme(self, theme):
        if self.current_theme == theme:
            return
        self.current_theme = theme
        dark = theme == "dark"
        paper, card, sidebar, ink, muted, line, green, selected = ("#171e1b", "#202a24", "#111914", "#e0e8dc", "#a0b39b", "#3b4a3e", "#3e6648", "#293d2d") if dark else ("#f7f5f0", "#fffcf7", "#ecefe6", "#25382e", "#778078", "#d9dfd1", "#284e3a", "#eaf0e3")
        palette = QPalette()
        for role, color in ((QPalette.ColorRole.Window, paper), (QPalette.ColorRole.WindowText, ink), (QPalette.ColorRole.Base, card), (QPalette.ColorRole.Text, ink), (QPalette.ColorRole.Button, card), (QPalette.ColorRole.ButtonText, ink), (QPalette.ColorRole.Highlight, green), (QPalette.ColorRole.HighlightedText, "#ffffff")):
            palette.setColor(role, QColor(color))
        QApplication.instance().setPalette(palette)
        self.setStyleSheet(f"""
            QWidget {{ color: {ink}; font-family: 'Segoe UI', 'DejaVu Sans'; font-size: 12px; }}
            QMainWindow, QDialog {{ background: {paper}; }}
            QFrame#sidebar {{ background: {sidebar}; border-right: 1px solid {line}; }}
            QLabel#brand {{ font-family: Georgia, serif; font-size: 27px; }}
            QLabel#hero {{ font-family: Georgia, serif; font-size: 29px; margin: 16px 0 8px; }}
            QLabel#eyebrow {{ color: {muted}; font-size: 9px; padding: 5px 0; }}
            QLabel#subtle {{ color: {muted}; font-size: 11px; padding: 5px 0; }}
            QLabel#notice {{ background: {selected}; border: 1px solid {line}; border-radius: 5px; padding: 12px; }}
            QLabel#answer {{ font-size: 13px; padding: 8px 0; }}
            QPushButton {{ background: {card}; border: 1px solid {line}; border-radius: 5px; padding: 10px 14px; }}
            QPushButton:hover {{ background: {selected}; }}
            QPushButton:disabled {{ color: {muted}; }}
            QPushButton#primary {{ background: {green}; color: #f5f7ec; }}
            QPushButton#navigation {{ text-align: left; padding: 15px; background: transparent; border: 0; }}
            QLineEdit, QComboBox, QPlainTextEdit, QListWidget {{ background: {card}; border: 1px solid {line}; border-radius: 5px; padding: 9px; }}
            QComboBox QAbstractItemView {{ background: {card}; selection-background-color: {green}; }}
            QScrollArea {{ border: 0; background: transparent; }}
            QScrollArea > QWidget > QWidget {{ background: {paper}; }}
            QFrame#message {{ background: {paper}; border-bottom: 1px solid {line}; padding: 14px 4px; }}
            QListWidget::item {{ padding: 14px; border-bottom: 1px solid {line}; }}
            QListWidget::item:selected {{ background: {selected}; color: {ink}; }}
            QCheckBox {{ spacing: 10px; }}
        """)
        self.theme_button.setText("Light mode" if dark else "Dark mode")

    def closeEvent(self, event):
        if self.allow_close or not self.backend.isRunning():
            event.accept()
            return
        event.ignore()
        if not self.closing:
            self.closing = True
            self.notice("Closing the library and owned model engine...")
            self.centralWidget().setEnabled(False)
            self.backend.stop()

    def backend_finished(self):
        if self.closing:
            self.allow_close = True
            self.close()
