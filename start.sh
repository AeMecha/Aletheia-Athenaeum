#!/bin/sh
# Keep this app's dependencies in its own environment.
set -eu
cd "$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)"
if [ ! -x .venv/bin/python ]; then
    "${PYTHON:-python3}" -m venv .venv
fi
.venv/bin/python -m pip install .
exec .venv/bin/python -m aletheia_athenaeum "$@"
