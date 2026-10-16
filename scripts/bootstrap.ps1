param(
  [switch]$Offline
)
$ErrorActionPreference = "Stop"

if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
  throw "uv is required. Install it from https://docs.astral.sh/uv/"
}

uv sync --all-groups
uv run pre-commit install --install-hooks
if ($Offline) {
  uv run python scripts/check.py --offline
} else {
  uv run python scripts/check.py
}
Write-Host "MathAgent development environment is ready."
