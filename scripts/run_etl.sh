#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."
exec uv run --with-requirements requirements.txt python etl.py
