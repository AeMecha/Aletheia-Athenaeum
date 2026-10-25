"""Add missing upstream notices without replacing any historical build bytes.

Run through this repository's GitHub workflow and scoped GITHUB_TOKEN. Only the
three controlled UPSTREAM-* assets and the corrective release-note block change.
"""
from __future__ import annotations
import hashlib
import json
import os
import re
import subprocess
import tempfile
from pathlib import Path

START = "<!-- aletheia-upstream-notice:start -->"
END = "<!-- aletheia-upstream-notice:end -->"


def update_body(existing, block):
    existing = re.sub(re.escape(START) + r".*?" + re.escape(END), "", existing or "", flags=re.S).strip()
    return block + ("\n\n" + existing if existing else "") + "\n"


def gh(*arguments):
    return subprocess.check_output(["gh", *arguments], text=True, encoding="utf-8")


def main():
    repository = os.environ["GITHUB_REPOSITORY"]
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", repository):
        raise ValueError("Invalid repository.")
    manifest = json.loads(Path("UPSTREAM-PROVENANCE.json").read_text(encoding="utf-8"))
    license_bytes = Path(manifest["license"]["path"]).read_bytes()
    if hashlib.sha256(license_bytes).hexdigest() != manifest["license"]["sha256"]:
        raise ValueError("The verbatim upstream license changed.")
    commit = subprocess.check_output(["git", "rev-parse", "HEAD"], text=True).strip()
    source = f"https://github.com/{repository}/blob/{commit}"
    releases = json.loads(gh("api", f"repos/{repository}/releases?per_page=100"))
    for release in releases:
        if release["draft"]:
            continue
        tag = release["tag_name"]
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._/-]*", tag):
            raise ValueError("Unsupported release tag.")
        asset_base = f"https://github.com/{repository}/releases/download/{tag}"
        block = f'''{START}
### Original project, attribution and license correction

This independently maintained derivative contains original/adapted material from **[Aletheia](https://github.com/AdeptTel1/Aletheia)** by **[Adeptus Telvannus (AdeptTel1)](https://github.com/AdeptTel1)**.

Copyright © 2026 Adeptus Telvannus. All rights reserved.

The original Archivist/Librarian prompts and Binder workflow are credited to that project. Covered material retains the author's **[original custom license]({asset_base}/UPSTREAM-ALETHEIA-LICENSE.txt)**; historical AGPL-only descriptions did not account for those terms and must not be read as relicensing that upstream material. See the **[upstream attribution notice]({asset_base}/UPSTREAM-ALETHEIA-NOTICE.md)**, [material changes]({source}/ATTRIBUTION.md) and [license scope]({source}/LICENSING.md).

These notices supplement this historical release. Existing installer, executable, wheel, source and original checksum assets are unchanged. The notices document existing terms; they do not grant additional permissions. **[Notice checksums]({asset_base}/UPSTREAM-NOTICE-SHA256SUMS.txt)** accompany the added files.
{END}'''
        with tempfile.TemporaryDirectory(prefix="aletheia-upstream-notices-") as temporary:
            directory = Path(temporary)
            license_file = directory / "UPSTREAM-ALETHEIA-LICENSE.txt"
            notice_file = directory / "UPSTREAM-ALETHEIA-NOTICE.md"
            checksum_file = directory / "UPSTREAM-NOTICE-SHA256SUMS.txt"
            license_file.write_bytes(license_bytes)
            notice = f'''# Original Aletheia attribution and license notice

Original project: https://github.com/AdeptTel1/Aletheia
Original author: Adeptus Telvannus (AdeptTel1), https://github.com/AdeptTel1
Copyright © 2026 Adeptus Telvannus. All rights reserved.

This release of {repository} contains original/adapted Aletheia prompts and Binder-related material. The original custom license is provided verbatim as UPSTREAM-ALETHEIA-LICENSE.txt. Historical blanket AGPL-only descriptions omitted these upstream terms; they do not relicense the author's covered work. Separately authored contributions and dependencies retain their own terms. No additional permission is granted by this notice.

Original license source: https://github.com/AdeptTel1/Aletheia/blob/{manifest['license']['commit']}/LICENSE.txt
Original release: https://github.com/AdeptTel1/Aletheia/releases/tag/NewRelease
Material changes: {source}/ATTRIBUTION.md
License scope: {source}/LICENSING.md
Source provenance and hashes: {source}/UPSTREAM-PROVENANCE.json
Retained AGPL text: {source}/LICENSES/AGPL-3.0-only.txt

The Scriptorium desktop repository was previously named AeMecha/Aletheia. Scriptorium, Agora and Athenaeum are independently maintained derivatives, not the upstream Aletheia release. Original artifact bytes and their checksums have not been replaced by this correction.
'''
            notice_file.write_text(notice, encoding="utf-8", newline="\n")
            hashes = {file.name: hashlib.sha256(file.read_bytes()).hexdigest() for file in (license_file, notice_file)}
            checksum_file.write_text("".join(f"{digest}  {name}\n" for name, digest in hashes.items()), encoding="utf-8", newline="\n")
            hashes[checksum_file.name] = hashlib.sha256(checksum_file.read_bytes()).hexdigest()
            gh("release", "upload", tag, str(license_file), str(notice_file), str(checksum_file), "--clobber")
            current = json.loads(gh("api", f"repos/{repository}/releases/{release['id']}"))
            for name, digest in hashes.items():
                matches = [item for item in current["assets"] if item["name"] == name]
                if len(matches) != 1 or matches[0]["state"] != "uploaded" or matches[0].get("digest") != "sha256:" + digest:
                    raise ValueError("Upstream notice upload verification failed: " + name)
            body = directory / "release-body.md"
            body.write_text(update_body(release.get("body"), block), encoding="utf-8", newline="\n")
            arguments = ["release", "edit", tag, "--notes-file", str(body)]
            if repository.endswith("/Aletheia-Scriptorium") and release["name"].startswith("Aletheia ") and not release["name"].startswith("Aletheia Scriptorium "):
                arguments += ["--title", release["name"].replace("Aletheia ", "Aletheia Scriptorium ", 1)]
            gh(*arguments)
            print("Added verified upstream attribution/license notices to " + tag)


if __name__ == "__main__":
    main()
