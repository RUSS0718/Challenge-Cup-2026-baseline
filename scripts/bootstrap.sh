#!/usr/bin/env bash
set -euo pipefail

command -v uv >/dev/null 2>&1 || { echo "uv is required: https://docs.astral.sh/uv/" >&2; exit 1; }
uv sync --all-groups
uv run pre-commit install --install-hooks
if [[ "${1:-}" == "--offline" ]]; then
  uv run python scripts/check_workspace.py --offline
else
  uv run python scripts/check_workspace.py
fi
printf '%s\n' "MathAgent development environment is ready."
