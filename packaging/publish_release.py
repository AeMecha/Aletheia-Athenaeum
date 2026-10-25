"""Publish a complete native/Python release only after upload digests agree."""
import hashlib
import json
import os
import re
import subprocess
import time
import tomllib
from pathlib import Path


def gh(*args):
    return subprocess.check_output(["gh", *args], text=True)


def asset_plan(directory, version):
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Expected a stable semantic version.")
    names = [f"aletheia_athenaeum-{version}-py3-none-any.whl", f"aletheia_athenaeum-{version}.tar.gz",
             f"Aletheia-Athenaeum-{version}-windows-x64.exe", f"Aletheia-Athenaeum-{version}-windows-x64-licenses.zip"]
    hashes = {}
    for name in names:
        path = directory / name
        if not path.is_file() or not path.stat().st_size:
            raise ValueError("Missing or empty release asset: " + name)
        with path.open("rb") as stream:
            hashes[name] = hashlib.file_digest(stream, "sha256").hexdigest()
    checksum = directory / "SHA256SUMS.txt"
    checksum.write_text("".join(f"{value}  {name}\n" for name, value in hashes.items()), encoding="utf-8", newline="\n")
    hashes[checksum.name] = hashlib.sha256(checksum.read_bytes()).hexdigest()
    return hashes


def verify_assets(release, directory, hashes):
    for name, digest in hashes.items():
        matches = [item for item in release["assets"] if item["name"] == name]
        if len(matches) != 1 or matches[0]["state"] != "uploaded" or matches[0]["size"] != (directory / name).stat().st_size or matches[0].get("digest") != "sha256:" + digest:
            raise ValueError("Release asset verification failed: " + name)


def main():
    version = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]
    tag = "v" + version
    if os.environ["GITHUB_REF_NAME"] != tag:
        raise ValueError("Tag and package version differ.")
    directory = Path("release-assets")
    hashes = asset_plan(directory, version)
    repository = os.environ["GITHUB_REPOSITORY"]
    releases = json.loads(gh("api", f"repos/{repository}/releases?per_page=100"))
    release = next((item for item in releases if item["tag_name"] == tag), None)
    if release is None:
        gh("release", "create", tag, "--verify-tag", "--draft", "--title", "Aletheia Athenaeum " + version, "--notes-file", "RELEASE-NOTES.md")
        # A new draft can take a moment to appear in the release listing.
        for attempt in range(6):
            releases = json.loads(gh("api", f"repos/{repository}/releases?per_page=100"))
            release = next((item for item in releases if item["tag_name"] == tag), None)
            if release:
                break
            time.sleep(1.5)
        if release is None:
            raise ValueError("GitHub did not return the expected draft release.")
    if release["draft"]:
        gh("release", "upload", tag, *(str(directory / name) for name in hashes), "--clobber")
        release = json.loads(gh("api", f"repos/{repository}/releases/{release['id']}"))
    verify_assets(release, directory, hashes)
    for name in hashes:
        print("Verified " + name)
    if release["draft"]:
        gh("release", "edit", tag, "--draft=false", "--latest")
    print("Published " + release["html_url"])


if __name__ == "__main__":
    main()
