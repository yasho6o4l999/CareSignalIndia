#!/usr/bin/env sh
set -eu

PROJECT_ROOT="$(CDPATH= cd -- "$(dirname -- "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

mkdir -p logs
exec .venv/bin/python etl.py >> "logs/etl.log" 2>&1

