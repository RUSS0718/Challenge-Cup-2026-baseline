#!/usr/bin/env bash
set -euo pipefail

if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="${HOME}/.local/bin:${PATH}"
fi

uv sync --all-groups
uv run pre-commit install --install-hooks
uv run python scripts/check_workspace.py --offline
printf '\nMathAgent Codespace is ready. Run: uv run pytest -q\n'
