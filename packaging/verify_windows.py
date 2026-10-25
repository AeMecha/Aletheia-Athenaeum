"""Execute the actual frozen GUI in an isolated, offline acceptance profile."""
import argparse
import json
import os
import subprocess
import tempfile
from pathlib import Path


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--exe", type=Path, required=True)
    parser.add_argument("--embeddings", type=Path, required=True)
    args = parser.parse_args()
    with tempfile.TemporaryDirectory(prefix="aletheia-frozen-report-") as temporary:
        report = Path(temporary) / "verification.json"
        environment = {**os.environ, "QT_QPA_PLATFORM": "offscreen"}
        # Prevent a developer's source tree or Python installation masking a
        # missing file/import in the executable; the executable owns Python.
        for key in ("PYTHONHOME", "PYTHONPATH"):
            environment.pop(key, None)
        if os.name == "nt":
            system = Path(os.environ.get("SystemRoot", "C:/Windows"))
            environment["PATH"] = os.pathsep.join((str(system / "System32"), str(system)))
        command = [str(args.exe.resolve()), "--verify-installation", str(report), "--verification-embeddings", str(args.embeddings.resolve())]
        completed = subprocess.run(command, env=environment, cwd=temporary, timeout=180,
                                   creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0)
        value = json.loads(report.read_text(encoding="utf-8")) if report.exists() else {}
        print(json.dumps(value, indent=2))
        if completed.returncode != 0 or not value.get("passed") or not value.get("frozen"):
            raise SystemExit("Frozen application verification failed.")
        if not any("BGE ONNX" in item for item in value["checks"]):
            raise SystemExit("The executable did not verify its semantic dependencies.")


if __name__ == "__main__":
    main()
