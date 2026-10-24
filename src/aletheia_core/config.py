"""Validate settings, migrate Electron profiles, and replace JSON atomically."""
from __future__ import annotations

import json
import os
import secrets
from pathlib import Path
from urllib.parse import urlsplit

DEFAULT_MODEL = "qwen3.8-9b-hermes-fc-tooluse"
DEFAULTS = dict(provider="embedded", modelPath="", contextSize=16384, outputTokens=1536,
                gpu="auto", apiUrl="http://127.0.0.1:1234/v1", apiModel=DEFAULT_MODEL,
                apiKey="", responseMode="auto", tokenLimitField="max_tokens",
                autoStart=True, theme="light", runtimePath="", searchMode="keyword")


def data_home(app_name: str) -> Path:
    if os.environ.get("ALETHEIA_HOME"):
        return Path(os.environ["ALETHEIA_HOME"]).expanduser().resolve()
    base = Path(os.environ.get("APPDATA", Path.home() / "AppData/Roaming")) if os.name == "nt" else Path(os.environ.get("XDG_CONFIG_HOME", Path.home() / ".config"))
    return base / app_name


def atomic_write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name + "." + secrets.token_hex(8) + ".tmp")
    try:
        fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8", newline="") as stream:
            stream.write(content)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def atomic_json(path: Path, value) -> None:
    atomic_write(path, json.dumps(value, ensure_ascii=False, indent=2) + "\n")


def api_connection(value: dict) -> tuple[str, str]:
    address, key = value.get("apiUrl", ""), value.get("apiKey", "")
    if not isinstance(address, str) or not isinstance(key, str):
        raise ValueError("Enter an API base address and a valid key.")
    try:
        url = urlsplit(address)
        valid = url.scheme in ("http", "https") and url.hostname and url.port != 0 and not (url.username or url.password or url.query or url.fragment)
    except ValueError:
        valid = False
    if not valid or any(ord(c) < 32 for c in address) or len(key) > 4096 or "\r" in key or "\n" in key:
        raise ValueError("Use an HTTP(S) API base address without embedded credentials, query, or fragment.")
    return address.rstrip("/"), key


def validate_settings(value: dict) -> dict:
    if not isinstance(value, dict):
        raise ValueError("Invalid settings.")
    legacy = value.get("provider") == "lmstudio"
    value = {**DEFAULTS, **value}
    if legacy:
        value.update(provider="api", apiUrl=value.get("lmStudioUrl", value["apiUrl"]))
    if value["provider"] not in ("embedded", "api") or value["gpu"] not in ("auto", "cpu") or value["theme"] not in ("light", "dark"):
        raise ValueError("Choose a supported connection, acceleration mode and theme.")
    if value["searchMode"] not in ("keyword", "semantic"):
        raise ValueError("Choose keyword search or optional semantic hybrid search.")
    for field, low, high in (("contextSize", 4096, 262144), ("outputTokens", 256, 32768)):
        if type(value[field]) is not int or not low <= value[field] <= high:
            raise ValueError(f"{field} must be between {low:,} and {high:,} tokens.")
    for field in ("modelPath", "runtimePath"):
        if not isinstance(value[field], str) or (value[field] and not Path(value[field]).is_absolute()):
            raise ValueError("Model and optional engine paths must be absolute paths on this computer.")
    if value["modelPath"] and Path(value["modelPath"]).suffix.lower() != ".gguf":
        raise ValueError("Choose an instruction/chat GGUF model.")
    value["apiUrl"], value["apiKey"] = api_connection(value)
    model = value["apiModel"]
    if not isinstance(model, str) or len(model) > 512 or any(ord(c) < 32 for c in model) or (value["provider"] == "api" and not model.strip()):
        raise ValueError("Enter the API model ID, or fetch available models.")
    value["apiModel"] = model.strip()
    if value["responseMode"] not in ("auto", "json_schema", "json_object", "prompt") or value["tokenLimitField"] not in ("max_tokens", "max_completion_tokens") or type(value["autoStart"]) is not bool:
        raise ValueError("Invalid model compatibility settings.")
    return {name: value[name] for name in DEFAULTS}


class Config:
    def __init__(self, home: Path):
        self.path = home / "settings.json"
        home.mkdir(parents=True, exist_ok=True)
        self.value = validate_settings(json.loads(self.path.read_text(encoding="utf-8")) if self.path.exists() else {})

    def save(self, value: dict) -> dict:
        checked = validate_settings(value)
        atomic_json(self.path, checked)
        self.value = checked
        return checked

    def public(self) -> dict:
        # The browser and Qt form never receive a stored provider credential.
        return {**self.value, "apiKey": "", "hasApiKey": bool(self.value["apiKey"])}

    def with_saved_key(self, value: dict) -> dict:
        value = dict(value)
        if not value.get("apiKey") and not value.pop("clearApiKey", False):
            if value.get("apiUrl", "").rstrip("/") == self.value["apiUrl"]:
                value["apiKey"] = self.value["apiKey"]
        return value
