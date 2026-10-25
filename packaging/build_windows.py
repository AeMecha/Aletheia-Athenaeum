"""Build one portable Windows x64 executable from a clean native environment.

Run after installing .[semantic] and the pinned PyInstaller. Models and user data
are never collected. Dependency license files accompany and enter the bundle.
"""
from __future__ import annotations
import importlib.metadata
import platform
import shutil
import sys
import tomllib
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main():
    if sys.platform != "win32" or platform.machine().lower() not in ("amd64", "x86_64"):
        raise SystemExit("Build this executable on native Windows x64.")
    version = tomllib.loads((ROOT / "pyproject.toml").read_text(encoding="utf-8"))["project"]["version"]
    name = f"Aletheia-Athenaeum-{version}-windows-x64"
    work = ROOT / "build" / "windows"
    licenses = work / "licenses"
    own = licenses / "Aletheia"
    own.mkdir(parents=True, exist_ok=True)
    for filename in ("LICENSE", "NOTICE", "LICENSING.md", "ATTRIBUTION.md", "UPSTREAM-PROVENANCE.json", "THIRD-PARTY-NOTICES.md"):
        shutil.copyfile(ROOT / filename, own / filename)
    shutil.copytree(ROOT / "LICENSES", own / "LICENSES", dirs_exist_ok=True)
    # Retain original license texts from all build-environment distributions.
    # A clean venv avoids collecting unrelated applications or their metadata.
    for distribution in importlib.metadata.distributions():
        package = distribution.metadata["Name"].replace("/", "_").replace("\\", "_")
        for relative in distribution.files or []:
            if ".." in relative.parts or relative.is_absolute():
                continue
            if relative.name.lower().startswith(("license", "licence", "copying", "notice")):
                source = Path(distribution.locate_file(relative))
                if source.is_file():
                    target = licenses / package / relative
                    target.parent.mkdir(parents=True, exist_ok=True)
                    shutil.copyfile(source, target)
    for filename in ("LICENSE.txt", "LICENSE"):
        source = Path(sys.base_prefix) / filename
        if source.is_file():
            target = licenses / "Python" / filename
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(source, target)
    import PyInstaller.__main__
    args = [
        "--noconfirm", "--clean", "--onefile", "--windowed", "--noupx",
        "--name", name, "--distpath", str(ROOT / "dist"),
        "--workpath", str(work / "work"), "--specpath", str(work / "spec"),
        "--paths", str(ROOT / "src"),
        "--add-data", f"{ROOT / 'src/aletheia_core/data'}:aletheia_core/data",
        "--add-data", f"{licenses}:licenses",
        "--collect-all", "onnxruntime", "--collect-all", "tokenizers",
        "--hidden-import", "numpy",
    ]
    for package in ("onnxruntime", "tokenizers", "numpy", "PySide6_Essentials", "shiboken6", "httpx", "filelock"):
        args += ["--copy-metadata", package]
    # Avoid accidental collection of unrelated environments or browser engines.
    for package in ("PyQt5", "PyQt6", "PySide2", "PySide6.QtWebEngineCore", "PySide6.QtWebEngineWidgets", "fastapi", "uvicorn", "torch", "tensorflow", "matplotlib", "pandas", "scipy", "IPython"):
        args += ["--exclude-module", package]
    PyInstaller.__main__.run(args + [str(ROOT / "packaging" / "entry.py")])
    with zipfile.ZipFile(ROOT / "dist" / (name + "-licenses.zip"), "w", zipfile.ZIP_DEFLATED) as archive:
        for filename in sorted(licenses.rglob("*")):
            if filename.is_file():
                archive.write(filename, filename.relative_to(licenses))
    print("Built " + name + ".exe and accompanying license archive.")


if __name__ == "__main__":
    main()
