"""SL-v3 条件续写复用的保守规范化与非流式 checkpoint 恢复。"""

from __future__ import annotations

import json
import re
import unicodedata
from dataclasses import dataclass
from typing import Any, Callable

from implementations.postprocess import normalize_final_response


MAX_CHECKPOINT_CHARS = 512
MAX_SCAN_CHARS = 65_536

_STRICT_FRACTION_RE = re.compile(
    r"(?:"
    r"\\(?:d?frac|tfrac)\s*\{[+-]?\d+\}\s*\{[+-]?\d+\}"
    r"|(?<![\w/])[+-]?\d+\s*/\s*[+-]?\d+(?![\w/])"
    r")"
)
_STRICT_DECIMAL_RE = re.compile(
    r"(?<![\w/])[+-]?(?:\d+\.\d*|\.\d+)(?:[eE][+-]?\d+)?(?![\w/])"
)
_CHECKPOINT_RE = re.compile(
    r"(?im)^[ \t]*(?:候选答案检查点|answer\s+checkpoint)\s*[:：]"
    r"\s*(?P<answer>[^\r\n]{1,512})\s*$"
)
_FINAL_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]+)?(?:\*{0,2})"
    r"(?:最终答案|答案|final\s+answer|answer)(?:\*{0,2})"
    r"\s*(?:[:：=]|为|\bis\b)"
    r"\s*(?P<answer>[^\r\n]+)$"
)
_VERIFY_RE = re.compile(
    r"(?:复核|验证|验算|自检|再次检查|back[- ]?check|verify|verification)",
    re.IGNORECASE,
)
_UNCERTAINTY_RE = re.compile(
    r"(?:可能|也许|或许|不确定|maybe|perhaps|possibly|uncertain|not\s+sure)",
    re.IGNORECASE,
)
_INCOMPLETE_TAIL_RE = re.compile(
    r"(?:[,，:：=＝+＋*＊/／{｛\[［(（【「]|"
    r"因此|所以|从而|可得|therefore|hence|thus)\s*$",
    re.IGNORECASE,
)
_REASONING_REQUIRED_RE = re.compile(
    r"(?:证明|论证|解释|说明(?:理由|原因|为什么)?|推导|"
    r"\b(?:prove|proof|justify|explain|demonstrate|derive)\b|\bshow\s+that\b)",
    re.IGNORECASE,
)
_CHOICE_RE = re.compile(r"^[A-H]$", re.IGNORECASE)
_BOOLEAN_RE = re.compile(
    r"^(?:yes|no|true|false|dne|does\s+not\s+exist|no\s+solution|"
    r"是|否|真|假|成立|不成立|无解|不存在|"
    r"命题为真|命题为假)$",
    re.IGNORECASE,
)
_MATH_TEXT_RE = re.compile(
    r"^[\s\dA-Za-z\\{}\[\]()+\-*/=<>|&_^.,;:'%π∞≤≥∪∩∅×·]+$"
)
_ALLOWED_MATH_WORDS = frozenset(
    {
        "alpha",
        "angle",
        "approx",
        "bar",
        "begin",
        "beta",
        "binom",
        "bmatrix",
        "bmod",
        "boxed",
        "cap",
        "cases",
        "cdot",
        "cdots",
        "chi",
        "circ",
        "cup",
        "delta",
        "dfrac",
        "dne",
        "emptyset",
        "end",
        "epsilon",
        "equiv",
        "eta",
        "exists",
        "false",
        "frac",
        "gamma",
        "geq",
        "hat",
        "infty",
        "iota",
        "kappa",
        "lambda",
        "ldots",
        "left",
        "leq",
        "mathbb",
        "mathbf",
        "mathcal",
        "mathfrak",
        "mathrm",
        "matrix",
        "mp",
        "mu",
        "nabla",
        "neq",
        "nu",
        "omega",
        "operatorname",
        "overline",
        "parallel",
        "partial",
        "perp",
        "phi",
        "pi",
        "pm",
        "pmatrix",
        "pmod",
        "prime",
        "psi",
        "qquad",
        "quad",
        "rho",
        "right",
        "setminus",
        "sigma",
        "sqrt",
        "subseteq",
        "supseteq",
        "tau",
        "text",
        "tfrac",
        "theta",
        "tilde",
        "times",
        "true",
        "underline",
        "upsilon",
        "varepsilon",
        "varnothing",
        "varphi",
        "varpi",
        "varrho",
        "varsigma",
        "vartheta",
        "vec",
        "xi",
        "zeta",
    }
)


@dataclass(frozen=True)
class NormalizationDecision:
    final_response: str
    applied: bool
    reason: str


@dataclass(frozen=True)
class ClosureDecision:
    final_response: str
    applied: bool
    reason: str
    checkpoint_available: bool
    truncation_signal: bool
    oververification_signal: bool


def _strict_json(value: str) -> Any:
    return json.loads(
        value,
        parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
    )


def _is_structured_json(value: str) -> bool:
    try:
        parsed = _strict_json(value.strip())
    except (TypeError, ValueError, RecursionError):
        return False
    return isinstance(parsed, (dict, list))


def _has_mixed_exact_fraction_and_decimal(value: str) -> bool:
    return bool(_STRICT_FRACTION_RE.search(value) and _STRICT_DECIMAL_RE.search(value))


def guarded_normalize(
    final_response: object,
    problem: object = "",
    *,
    normalizer: Callable[..., str] = normalize_final_response,
) -> NormalizationDecision:
    """只接受结构上仍是单一终答的共享规范化结果。"""

    if not isinstance(final_response, str):
        return NormalizationDecision("", False, "invalid_input")
    original = final_response.strip()
    if not original:
        return NormalizationDecision("", False, "empty_input")
    try:
        candidate = normalizer(
            original,
            problem,
            prefer_exact_equivalent_annotation=True,
        )
    except Exception:
        return NormalizationDecision(original, False, "normalizer_error")
    if not isinstance(candidate, str) or not candidate.strip():
        return NormalizationDecision(original, False, "invalid_normalizer_output")
    normalized = candidate.strip()
    if normalized == original:
        return NormalizationDecision(original, False, "unchanged")

    # 共享层的 exact-equivalent 模式应已把该结构收窄为分数。这里仅防止
    # 依赖回归后重新返回“精确分数 + 小数解释”的非原子终答。
    if (
        not _is_structured_json(normalized)
        and _has_mixed_exact_fraction_and_decimal(normalized)
    ):
        return NormalizationDecision(
            original,
            False,
            "rejected_mixed_exact_fraction_decimal",
        )
    return NormalizationDecision(normalized, True, "accepted")


def _strip_outer_wrappers(value: str) -> str:
    result = value.strip()
    changed = True
    while changed and result:
        changed = False
        for opening, closing in (
            ("$$", "$$"),
            ("$", "$"),
            (r"\(", r"\)"),
            (r"\[", r"\]"),
            ("**", "**"),
            ("`", "`"),
        ):
            if (
                len(result) > len(opening) + len(closing)
                and result.startswith(opening)
                and result.endswith(closing)
            ):
                result = result[len(opening) : -len(closing)].strip()
                changed = True
                break
    result = result.rstrip("。；;").strip()
    if result.endswith(".") and _STRICT_DECIMAL_RE.fullmatch(result) is None:
        result = result[:-1].rstrip()
    return result


def _delimiters_balanced(value: str) -> bool:
    pairs = {
        "(": ")",
        "[": "]",
        "{": "}",
        "（": "）",
        "［": "］",
        "｛": "｝",
        "【": "】",
        "「": "」",
    }
    closing = set(pairs.values())
    stack: list[str] = []
    for char in value:
        if char in pairs:
            stack.append(pairs[char])
        elif char in closing:
            if not stack or stack.pop() != char:
                return False
    return not stack


def _latex_environments_balanced(value: str) -> bool:
    stack: list[str] = []
    for action, environment in re.findall(r"\\(begin|end)\{([^{}]+)\}", value):
        if action == "begin":
            stack.append(environment)
        elif not stack or stack.pop() != environment:
            return False
    return not stack


def _is_high_confidence_candidate(value: str) -> bool:
    candidate = _strip_outer_wrappers(value)
    if (
        not candidate
        or len(candidate) > MAX_CHECKPOINT_CHARS
        or "\n" in candidate
        or _UNCERTAINTY_RE.search(candidate)
        or _INCOMPLETE_TAIL_RE.search(candidate)
        or not _delimiters_balanced(candidate)
        or not _latex_environments_balanced(candidate)
        or _has_mixed_exact_fraction_and_decimal(candidate)
    ):
        return False
    if _is_structured_json(candidate):
        return True
    if _CHOICE_RE.fullmatch(candidate) or _BOOLEAN_RE.fullmatch(candidate):
        return True
    if not _MATH_TEXT_RE.fullmatch(candidate):
        return False
    words = {word.casefold() for word in re.findall(r"[A-Za-z]{2,}", candidate)}
    return words <= _ALLOWED_MATH_WORDS and bool(
        re.search(r"[\d=+\-*/_^{}\\<>≤≥∪∩]", candidate)
    )


def _canonical_candidate(value: str) -> str:
    normalized = unicodedata.normalize("NFC", _strip_outer_wrappers(value))
    return re.sub(r"\s+", "", normalized).casefold()


def _find_checkpoint(response: str) -> tuple[str, int, int] | None:
    source = response[:MAX_SCAN_CHARS]
    matches: list[tuple[str, int, int]] = []
    for match in _CHECKPOINT_RE.finditer(source):
        candidate = _strip_outer_wrappers(match.group("answer"))
        if _is_high_confidence_candidate(candidate):
            matches.append((candidate, match.start(), match.end()))
    if not matches:
        return None
    if len({_canonical_candidate(item[0]) for item in matches}) != 1:
        return None
    return matches[-1]


def _line_is_complete(value: str) -> bool:
    candidate = value.strip()
    return bool(
        candidate
        and not _UNCERTAINTY_RE.search(candidate)
        and not _INCOMPLETE_TAIL_RE.search(candidate)
        and _delimiters_balanced(candidate)
        and _latex_environments_balanced(candidate)
    )


def _has_complete_final_line(response: str) -> bool:
    return any(
        _line_is_complete(match.group("answer"))
        for match in _FINAL_LINE_RE.finditer(response[-MAX_SCAN_CHARS:])
    )


def _truncation_signal(response: str) -> bool:
    bounded = response[-MAX_SCAN_CHARS:]
    tail = bounded.rstrip()
    if not tail:
        return False
    if _INCOMPLETE_TAIL_RE.search(tail[-256:]):
        return True
    if not _delimiters_balanced(bounded) or not _latex_environments_balanced(bounded):
        return True
    unescaped_dollars = re.findall(r"(?<!\\)\$", bounded)
    return len(unescaped_dollars) % 2 == 1


def _oververification_signal(response: str, checkpoint_end: int) -> bool:
    tail = response[checkpoint_end:]
    return len(tail.strip()) >= 64 and _VERIFY_RE.search(tail) is not None


def recover_forced_closure(
    final_response: object,
    problem: object = "",
) -> ClosureDecision:
    """从已返回的非流式文本恢复早期 checkpoint；不处理在途字节。"""

    if not isinstance(final_response, str) or not final_response.strip():
        value = final_response.strip() if isinstance(final_response, str) else ""
        return ClosureDecision(value, False, "empty_input", False, False, False)
    original = final_response.strip()
    if _has_complete_final_line(original):
        return ClosureDecision(
            original,
            False,
            "complete_final_present",
            False,
            False,
            False,
        )
    checkpoint = _find_checkpoint(original)
    if checkpoint is None:
        return ClosureDecision(
            original,
            False,
            "no_high_confidence_checkpoint",
            False,
            _truncation_signal(original),
            False,
        )
    candidate, checkpoint_start, checkpoint_end = checkpoint
    truncated = _truncation_signal(original)
    oververified = _oververification_signal(original, checkpoint_end)
    if not truncated and not oververified:
        return ClosureDecision(
            original,
            False,
            "no_trigger_signal",
            True,
            False,
            False,
        )

    problem_text = problem if isinstance(problem, str) else ""
    if _REASONING_REQUIRED_RE.search(problem_text):
        derivation = original[:checkpoint_start].rstrip()
        recovered = (
            f"{derivation}\n\n最终答案：{candidate}"
            if derivation
            else f"最终答案：{candidate}"
        )
    else:
        recovered = candidate
    reason = "recovered_truncation" if truncated else "recovered_oververification"
    return ClosureDecision(
        recovered,
        recovered != original,
        reason,
        True,
        truncated,
        oververified,
    )


__all__ = [
    "ClosureDecision",
    "NormalizationDecision",
    "guarded_normalize",
    "recover_forced_closure",
]
