#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

python_command="${PYTHON:-python}"
if ! "$python_command" -c "import duckdb, pyarrow, pydantic" >/dev/null 2>&1; then
  if [[ -x ".venv/bin/python" ]] \
    && .venv/bin/python -c "import duckdb, pyarrow, pydantic" >/dev/null 2>&1; then
    python_command=".venv/bin/python"
  else
    echo "Dependencies are missing. Activate the project virtual environment and run: pip install -r requirements.txt" >&2
    exit 1
  fi
fi

exec "$python_command" etl.py
