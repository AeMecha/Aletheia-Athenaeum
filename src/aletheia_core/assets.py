"""Fetch pinned assets into a private cache; never execute an unchecked download."""
from __future__ import annotations

import asyncio
import hashlib
import json
import os
import platform
import shutil
import tarfile
import zipfile
from pathlib import Path

import httpx

DATA = Path(__file__).parent / "data"
MANIFEST = json.loads((DATA / "assets.json").read_text(encoding="utf-8"))


def sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as stream:
        for block in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


async def download(asset: dict, target: Path, progress=lambda value: None) -> Path:
    target.parent.mkdir(parents=True, exist_ok=True)
    if target.exists() and await asyncio.to_thread(sha256, target) == asset["sha256"]:
        return target
    partial = target.with_name(target.name + ".part")
    size = partial.stat().st_size if partial.exists() else 0
    if asset.get("size") and size > asset["size"]:
        partial.unlink()
        size = 0
    if size != asset.get("size"):
        async with httpx.AsyncClient(follow_redirects=True, timeout=httpx.Timeout(60, read=120)) as client:
            async with client.stream("GET", asset["url"], headers={"Range": f"bytes={size}-"} if size else {}) as response:
                response.raise_for_status()
                if response.status_code != 206:
                    size = 0
                elif not response.headers.get("content-range", "").startswith(f"bytes {size}-"):
                    raise ValueError("The download server returned an unexpected range.")
                total = asset.get("size") or size + int(response.headers.get("content-length", 0))
                with partial.open("ab" if size else "wb") as stream:
                    async for chunk in response.aiter_bytes(1024 * 1024):
                        stream.write(chunk)
                        size += len(chunk)
                        progress(dict(phase="downloading", received=size, total=total, message=f"Downloading {target.name}"))
    progress(dict(phase="verifying", message=f"Verifying {target.name}"))
    if (asset.get("size") and size != asset["size"]) or await asyncio.to_thread(sha256, partial) != asset["sha256"]:
        partial.unlink(missing_ok=True)
        raise ValueError("The downloaded file failed its size/SHA-256 check. Retry setup.")
    os.replace(partial, target)
    return target


async def prepare_embeddings(resources: Path, progress=lambda value: None) -> Path:
    directory = resources / "embedding"
    for asset in MANIFEST["embedding"]["files"]:
        await download(asset, directory / asset["filename"], progress)
    # Preserve the model publisher's license beside the cached weights.
    if not (directory / "LICENSE").exists():
        (directory / "LICENSE").write_text("BAAI/bge-small-en-v1.5: MIT. https://huggingface.co/BAAI/bge-small-en-v1.5\n", encoding="utf-8")
    return directory


def extract_runtime(archive: Path, directory: Path) -> None:
    """Contain paths and materialize library links only inside the new cache."""
    directory.mkdir(parents=True, exist_ok=True)
    root = directory.resolve()
    def destination(name):
        path = (root / name).resolve()
        if not path.is_relative_to(root):
            raise ValueError("Unsafe engine archive path.")
        return path
    if archive.suffix == ".zip":
        with zipfile.ZipFile(archive) as bundle:
            for item in bundle.infolist():
                path = destination(item.filename)
                if item.is_dir():
                    path.mkdir(parents=True, exist_ok=True)
                else:
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.open(item) as source, path.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
    else:
        with tarfile.open(archive, "r:gz") as bundle:
            links = []
            for item in bundle:
                path = destination(item.name)
                if item.isdir():
                    path.mkdir(parents=True, exist_ok=True)
                elif item.isfile():
                    path.parent.mkdir(parents=True, exist_ok=True)
                    with bundle.extractfile(item) as source, path.open("wb") as sink:
                        shutil.copyfileobj(source, sink)
                    path.chmod(item.mode & 0o777)
                elif item.issym() or item.islnk():
                    link = destination(str(path.parent.relative_to(root) / item.linkname) if item.issym() else item.linkname)
                    links.append((path, link))
                else:
                    raise ValueError("Unsupported engine archive entry.")
            for _ in range(len(links) + 1):
                for path, link in links[:]:
                    if link.is_file():
                        path.parent.mkdir(parents=True, exist_ok=True)
                        shutil.copyfile(link, path)
                        path.chmod(0o755)
                        links.remove((path, link))
            if links:
                raise ValueError("Unresolved engine archive links.")


def runtime_target(system=None, machine=None):
    system, machine = system or platform.system(), (machine or platform.machine()).lower()
    operating_system = {"Windows": "win32", "Linux": "linux", "Darwin": "darwin"}.get(system)
    architecture = {"amd64": "x64", "x86_64": "x64", "arm64": "arm64", "aarch64": "arm64"}.get(machine)
    if not operating_system or not architecture:
        raise ValueError("No pinned engine is available for this platform. Configure a native llama-server path or use an API.")
    return operating_system + "-" + architecture


async def prepare_runtime(resources: Path, backend: str, progress=lambda value: None) -> Path:
    target = runtime_target()
    executable = "llama-server.exe" if target.startswith("win32-") else "llama-server"
    asset = MANIFEST["runtimePlatforms"][target][backend]
    directory = resources / "runtime" / target / backend
    marker = directory / ".verified.json"
    if marker.exists() and json.loads(marker.read_text())["sha256"] == asset["sha256"]:
        found = list(directory.rglob(executable))
        if found:
            return found[0]
    archive = resources / "downloads" / Path(asset["url"]).name
    await download(asset, archive, progress)
    await asyncio.to_thread(extract_runtime, archive, directory)
    found = list(directory.rglob(executable))
    if len(found) != 1:
        raise ValueError("The verified engine archive does not contain one model server.")
    marker.write_text(json.dumps({"sha256": asset["sha256"]}), encoding="utf-8")
    return found[0]
