"""Check the MathAgent repository contract without calling a model provider."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
REQUIRED_FILES = (
    "user_agent.py",
    "requirements.txt",
    "README.md",
    "BASELINE.json",
)
FORBIDDEN_NAMES = {"eval_112.json", "temporary_answer_bank.json"}


class OfflineClient:
    """Return a stable answer while exercising the public solve contract."""

    def chat(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        """Return a serializable response without a network request."""

        del messages, kwargs
        return "最终答案：2"


def check_files() -> None:
    """Verify files required for a clean development checkout."""

    missing = [name for name in REQUIRED_FILES if not (ROOT / name).is_file()]
    if missing:
        raise SystemExit(f"missing_required_files:{','.join(missing)}")
    forbidden = [
        str(path.relative_to(ROOT))
        for path in ROOT.rglob("*")
        if path.is_file() and path.name in FORBIDDEN_NAMES
    ]
    if forbidden:
        raise SystemExit(f"forbidden_answer_assets:{','.join(forbidden)}")


def check_entry() -> None:
    """Import the official entry and validate the minimum JSON result contract."""

    sys.path.insert(0, str(ROOT))
    from user_agent import ReasoningAgent

    result = ReasoningAgent(client=OfflineClient()).solve("计算 1+1", {})
    if not isinstance(result, dict):
        raise SystemExit("solve_result_not_dict")
    if not isinstance(result.get("final_response"), str) or not result["final_response"].strip():
        raise SystemExit("final_response_not_non_empty_string")
    json.dumps(result, ensure_ascii=False, allow_nan=False)


def main() -> int:
    """Run repository and entry checks; offline mode never calls a provider."""

    parser = argparse.ArgumentParser()
    parser.add_argument("--offline", action="store_true", help="Skip provider configuration checks")
    parser.parse_args()
    check_files()
    check_entry()
    print("workspace_contract=PASS")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
