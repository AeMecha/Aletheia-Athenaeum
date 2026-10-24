"""Own one local llama-server or connect to a configurable Chat Completions API.

External servers are never stopped. Requests carry only portable parameters;
the pinned default Qwen alone gets its established no-thinking options.
"""
from __future__ import annotations
import asyncio
import collections
import json
import os
import secrets
import socket
import struct
import subprocess
import threading
from pathlib import Path

import httpx
from .assets import MANIFEST, prepare_runtime
from .config import api_connection

LOCAL_ID = "aletheia-local"


def validate_gguf(filename: str) -> Path:
    path = Path(filename)
    if not path.is_absolute() or path.suffix.lower() != ".gguf" or not path.is_file():
        raise ValueError("Choose a local instruction/chat GGUF file.")
    with path.open("rb") as stream:
        header = stream.read(24)
    if len(header) != 24 or header[:4] != b"GGUF" or struct.unpack_from("<I", header, 4)[0] not in (2, 3):
        raise ValueError("This file is not a supported GGUF version 2 or 3 container.")
    return path.resolve()


class ApiError(ValueError):
    def __init__(self, message, status, parameter=""):
        super().__init__(message)
        self.status, self.parameter = status, parameter


async def api_request(base, key, route, body=None, timeout=180, transport=None):
    headers = {"Content-Type": "application/json"}
    if key:
        headers["Authorization"] = "Bearer " + key
    async with httpx.AsyncClient(timeout=timeout, follow_redirects=False, transport=transport) as client:
        response = await client.request("POST" if body is not None else "GET", base + route, headers=headers, **({"json": body} if body is not None else {}))
    try:
        value = response.json()
    except ValueError:
        value = {}
    if response.is_redirect:
        raise ApiError("The API tried to redirect. Enter its final base URL; credentials are not forwarded.", response.status_code)
    if response.is_error:
        error = value.get("error", {}) if isinstance(value, dict) else {}
        detail = error.get("message") if isinstance(error, dict) else error
        raise ApiError(str(detail or f"API returned HTTP {response.status_code}. Check the address, key and selected model.")[:1200], response.status_code, error.get("param", "") if isinstance(error, dict) else "")
    if not isinstance(value, dict) or not value:
        raise ValueError("The API did not return a JSON object. Use a Chat Completions base address, usually ending in /v1.")
    return value


class Model:
    def __init__(self, config, resources: Path, progress=lambda value: None, transport=None):
        self.config, self.resources, self.progress, self.transport = config, resources, progress, transport
        self.state = dict(phase="stopped", message="Choose your AI model to get started.")
        self.child, self.starting, self.format = None, None, None
        self.log = collections.deque(maxlen=60)
        self.base, self.key, self.model_id = "", "", ""

    def status(self, phase, message, **fields):
        self.state = dict(phase=phase, message=message, **fields)

    async def request(self, route, body=None, timeout=180):
        return await api_request(self.base, self.key, route, body, timeout, self.transport)

    async def models(self, connection):
        base, key = api_connection(self.config.with_saved_key(connection))
        result = await api_request(base, key, "/models", timeout=15, transport=self.transport)
        if not isinstance(result.get("data"), list):
            raise ValueError("This server does not expose model discovery. Enter the model ID manually.")
        return sorted({item["id"] for item in result["data"] if isinstance(item, dict) and isinstance(item.get("id"), str) and 1 <= len(item["id"].strip()) <= 512 and not any(ord(c) < 32 for c in item["id"])})[:1000]

    async def start(self):
        if self.state["phase"] == "ready":
            if self.child is None or self.child.poll() is None:
                return
            self.status("error", "The owned model engine stopped. Reconnect or choose another model.")
        if self.starting:
            await self.starting
            return
        self.starting = asyncio.create_task(self.open())
        try:
            await self.starting
        finally:
            self.starting = None

    async def open(self):
        settings = self.config.value
        self.format = None
        try:
            if settings["provider"] == "api":
                self.base, self.key = settings["apiUrl"], settings["apiKey"]
                self.model_id = settings["apiModel"]
                self.status("loading", "Connecting to your API...")
                discovered = True
                try:
                    await self.request("/models", timeout=15)
                except ApiError as error:
                    if error.status not in (404, 405, 501):
                        raise
                    discovered = False
                self.status("ready", ("API connected" if discovered else "API configured; model checked on first request") + " - " + self.model_id, provider="api", backend="external", model=self.model_id)
                return
            if not settings["modelPath"]:
                self.status("setup", "Choose a local GGUF, download the default Qwen, or connect to an API.")
                return
            filename = validate_gguf(settings["modelPath"])
            failures = []
            for backend in (["cpu"] if settings["gpu"] == "cpu" else ["vulkan", "cpu"]):
                try:
                    await self.open_local(filename, backend)
                    return
                except asyncio.CancelledError:
                    await self.kill_child()
                    raise
                except Exception as error:
                    failures.append(f"{backend}: {error}")
                    await self.kill_child()
            raise ValueError("This model could not load. Use a compatible GGUF with an embedded chat template; try CPU mode or less context. " + " | ".join(failures))
        except asyncio.CancelledError:
            self.status("stopped", "Model loading stopped.")
            raise
        except Exception as error:
            self.status("error", str(error))
            raise

    async def open_local(self, filename: Path, backend: str):
        settings = self.config.value
        label = "CPU" if backend == "cpu" else "automatic GPU"
        self.status("loading", f"Preparing {filename.name} - {label}...", model=filename.name)
        executable = Path(settings["runtimePath"]) if settings["runtimePath"] else await prepare_runtime(self.resources, backend, self.progress)
        if not executable.is_file():
            raise ValueError("The selected llama-server executable does not exist.")
        with socket.socket() as listener:
            listener.bind(("127.0.0.1", 0))
            port = listener.getsockname()[1]
        self.base, self.key, self.model_id = f"http://127.0.0.1:{port}/v1", secrets.token_urlsafe(32), LOCAL_ID
        args = [str(executable), "--model", str(filename), "--alias", LOCAL_ID, "--host", "127.0.0.1", "--port", str(port), "--api-key", self.key, "--ctx-size", str(settings["contextSize"]), "--parallel", "1", "--n-gpu-layers", "0" if backend == "cpu" else "99", "--jinja", "--no-webui"]
        if filename.name == MANIFEST["model"]["filename"]:
            args += ["--reasoning-budget", "0"]
        env = dict(os.environ)
        if os.name != "nt":
            env["LD_LIBRARY_PATH"] = str(executable.parent) + (":" + env["LD_LIBRARY_PATH"] if env.get("LD_LIBRARY_PATH") else "")
        self.log.clear()
        self.child = subprocess.Popen(args, cwd=executable.parent, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding="utf-8", errors="replace", creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        child = self.child
        def capture():
            # The logging thread owns and closes its pipe even after cancellation.
            with child.stdout:
                for line in child.stdout:
                    self.log.append(line[-1000:])
        threading.Thread(target=capture, daemon=True, name="aletheia-owned-engine-log").start()
        self.status("loading", f"Loading {filename.name} - {label}...", model=filename.name)
        async with asyncio.timeout(240):
            while True:
                if child.poll() is not None:
                    raise ValueError("Engine exited. " + "".join(self.log)[-2500:])
                try:
                    health = await api_request(self.base.removesuffix("/v1"), self.key, "/health", timeout=1.5)
                    if health.get("status") == "ok":
                        result = await self.request("/models")
                        if not any(item.get("id") == LOCAL_ID for item in result.get("data", [])):
                            raise ValueError("The engine did not expose the selected model.")
                        self.status("ready", f"{filename.name} is ready - {label}", provider="embedded", backend=backend, model=filename.name)
                        return
                except (httpx.HTTPError, ApiError):
                    pass
                await asyncio.sleep(.35)

    async def count_tokens(self, text):
        if self.config.value["provider"] == "api":
            return len(text.encode("utf-8"))
        result = await api_request(self.base.removesuffix("/v1"), self.key, "/tokenize", dict(content=text, add_special=False), timeout=15)
        if not isinstance(result.get("tokens"), list):
            raise ValueError("Could not measure model context.")
        return len(result["tokens"])

    async def complete(self, payload):
        await self.start()
        if self.state["phase"] != "ready":
            raise ValueError("Finish AI setup in Settings before generating an answer.")
        settings = self.config.value
        local = settings["provider"] == "embedded"
        modes = ["json_schema", "json_object", "prompt"]
        selected = settings["responseMode"]
        modes = modes[modes.index(self.format):] if selected == "auto" and self.format else modes if selected == "auto" else [selected]
        for mode in modes:
            messages = [dict(item) for item in payload["messages"]]
            schema = payload.get("response_format", {}).get("json_schema", {}).get("schema")
            if mode != "json_schema" and schema:
                messages[0]["content"] += "\n\nReturn only one JSON object, without Markdown, matching this schema: " + json.dumps(schema)
            available = settings["contextSize"] - await self.count_tokens(json.dumps(messages, ensure_ascii=False)) - 256
            if available < 256:
                raise ValueError("This request exceeds the selected context. Shorten it, or increase context only if the model supports it.")
            field = "max_tokens" if local else settings["tokenLimitField"]
            body = dict(model=self.model_id, messages=messages, stream=False, **{field: min(settings["outputTokens"], available)})
            if mode == "json_schema" and payload.get("response_format"):
                body["response_format"] = payload["response_format"]
            elif mode == "json_object":
                body["response_format"] = dict(type="json_object")
            if local:
                body.update(temperature=0, top_p=1, tools=[], tool_choice="none")
                if Path(settings["modelPath"]).name == MANIFEST["model"]["filename"]:
                    body["reasoning_effort"] = "none"
            try:
                raw = await self.request("/chat/completions", body)
                if local and raw.get("model") != LOCAL_ID:
                    raise ValueError("The local engine answered with a different model. Nothing was accepted.")
                if selected == "auto":
                    self.format = mode
                return raw
            except ApiError as error:
                import re
                format_error = error.status in (400, 422) and re.search(r"response_format|json_schema|json_object|structured[ _-]outputs?", str(error) + str(error.parameter), re.I)
                grammar_error = local and error.status == 400 and re.search(r"initializ.*sampler|grammar", str(error), re.I)
                if selected != "auto" or mode == modes[-1] or not (format_error or grammar_error):
                    raise

    async def kill_child(self):
        child, self.child = self.child, None
        if child and child.poll() is None:
            child.terminate()
            try:
                await asyncio.to_thread(child.wait, timeout=5)
            except subprocess.TimeoutExpired:
                child.kill()
                await asyncio.to_thread(child.wait, timeout=5)

    async def stop(self):
        if self.starting and self.starting is not asyncio.current_task():
            self.starting.cancel()
            await asyncio.gather(self.starting, return_exceptions=True)
        await self.kill_child()
        self.status("stopped", "The AI connection is stopped.")
