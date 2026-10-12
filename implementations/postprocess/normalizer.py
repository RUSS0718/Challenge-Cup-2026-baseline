"""将模型解答保守地收束为可判分终答。

本模块只做可逆的文本抽取与有限结构整理，不推导答案、不做符号化简，
也不执行模型生成的任何内容。不能唯一确认终答时，原样返回非空输入。
"""

from __future__ import annotations

import json
import math
import re
import unicodedata
from decimal import Decimal, InvalidOperation
from fractions import Fraction
from typing import Any


_MAX_JSON_CHARS = 16_384
_MAX_JSON_DEPTH = 16
_MAX_JSON_NODES = 2_048
_MAX_CANDIDATE_CHARS = 4_096

_STRONG_MARKER = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]+)?(?:\*{0,2})(?:"
    r"最终答案(?:\*{0,2})\s*(?:[:：=]|为)"
    r"|final\s+answer(?:\*{0,2})\s*(?:[:：=]|\bis\b)"
    r")\s*",
)
_GENERIC_MARKER = re.compile(
    r"(?im)^[ \t]*(?:[-*]\s*)?(?:\*{0,2})"
    r"(?:"
    r"答案(?:\*{0,2})\s*(?:[:：=]|为|是)"
    r"|answer(?:\*{0,2})\s*(?:[:：=]|\bis\b)"
    r")\s*"
)
_PART_LABEL = re.compile(r"(?<![\w\\])(?:\(|（)\s*([1-9]\d?)\s*(?:\)|）)")
_PART_ANSWER_PREFIX = re.compile(
    r"^(?:"
    r"(?:最终答案|答案)\s*(?:[:：=]|为|是)"
    r"|(?:final\s+answer|answer)\s*(?:[:：=]|\bis\b)"
    r")\s*",
    re.IGNORECASE,
)
_UNCERTAINTY = re.compile(
    r"(?:答案可能|也许|或许|可能是|或者为|perhaps|maybe|possibly|not\s+sure|uncertain)",
    re.IGNORECASE,
)
_PLACEHOLDER = re.compile(r"^(?:\.{3,}|…+|答案|answer|待定|unknown)$", re.IGNORECASE)
_TRUNCATED_TAIL = re.compile(r"(?:[,，:：=+*/{\[]|因此|所以|从而|可得)\s*$")
_STRICT_DECIMAL = re.compile(
    r"^[+-]?(?:\d+(?:\.\d*)?|\.\d+)(?:[eE][+-]?\d+)?$"
)
_STRICT_SLASH_FRACTION = re.compile(r"^([+-]?\d+)\s*/\s*([+-]?\d+)$")
_STRICT_LATEX_FRACTION = re.compile(
    r"^\\(?:d?frac|tfrac)\s*\{([+-]?\d+)\}\s*\{([+-]?\d+)\}$"
)
_CHOICE = re.compile(r"^[A-H](?:\s*[、,，]\s*[A-H])*$", re.IGNORECASE)
_BOOLEAN_ANSWER = re.compile(
    r"^(?:yes|no|true|false|是|否|真|假|成立|不成立)$",
    re.IGNORECASE,
)
_CJK = re.compile(r"[\u3400-\u9fff]")
_LATIN = re.compile(r"[A-Za-z]")
_ZH_BOOLEAN_QUESTION = re.compile(r"(?:是否|能否|是不是|正确还是错误|判断.{0,12}(?:真假|真伪|成立))")
_EN_BOOLEAN_QUESTION = re.compile(
    r"(?:\bwhether\b|\btrue\s+or\s+false\b|\b(?:is|are|does|do|can)\b[^?。]{0,160}\?)",
    re.IGNORECASE,
)
_JSON_REQUEST = re.compile(r"(?:\bJSON\b|合法\s*JSON|JSON\s*(?:数组|对象|array|object))", re.IGNORECASE)
_REASONING_REQUIRED = re.compile(
    r"(?:证明|论证|解释|说明(?:理由|原因|为什么)?|推导|给出.{0,12}证明"
    r"|给出.{0,8}(?:条件|理由|过程)"
    r"|\b(?:prove|proof|justify|explain|demonstrate|derive)\b|\bshow\s+that\b"
    r"|\bstate\s+(?:all\s+)?conditions?\b)",
    re.IGNORECASE,
)
_NONNUMERIC_PART_LABEL = re.compile(
    r"(?:\(|（)\s*([A-Za-z]{1,4}|[ivxIVX]{1,5}|[甲乙丙丁])\s*(?:\)|）)"
)
_RECOVERABLE_TRUNCATION_SIGNAL = re.compile(
    r"(?:传输|输出|响应|生成).{0,80}(?:截断|中断)|"
    r"(?:truncated|interrupted).{0,40}(?:transmission|output|response|generation)",
    re.IGNORECASE,
)
_RECOVERABLE_TRUNCATION_TEXT = re.compile(
    r"^[\s，。；;：:,._\-\u3400-\u9fffA-Za-z]{1,256}$"
)
_EQUIVALENT_DECIMAL_ANNOTATION = re.compile(
    r"^(?P<exact>.+?)\s*[（(]\s*"
    r"(?:即|即为|也即|也就是|等价于|=)\s*"
    r"(?P<decimal>[^()（）]+?)\s*[）)]$"
)


def _balanced_boxed_values(text: str) -> list[tuple[int, int, str]]:
    """返回所有配平 ``\\boxed`` 的起止位置和内容。"""

    values: list[tuple[int, int, str]] = []
    marker = "\\boxed{"
    starts = [match.start() for match in re.finditer(re.escape(marker), text)]
    for start in starts:
        content_start = start + len(marker)
        depth = 1
        for index in range(content_start, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    values.append((start, index + 1, text[content_start:index].strip()))
                    break
    return values


def _extract_balanced_boxed(text: str) -> str:
    """只在所有配平 ``\\boxed`` 保守等价时返回其内容。"""

    candidates = [
        candidate
        for _start, _end, candidate in _balanced_boxed_values(text)
        if _is_safe_candidate(candidate)
    ]
    return _choose_unique(candidates)


def _strip_outer_wrappers(value: str) -> str:
    """只移除完整成对的展示包装和句末标点。"""

    result = value.strip()
    changed = True
    while changed and result:
        changed = False
        if result.endswith(("。", ".")):
            result = result[:-1].rstrip()
            changed = True
            continue
        pairs = (("$$", "$$"), ("$", "$"), (r"\(", r"\)"), (r"\[", r"\]"))
        for opening, closing in pairs:
            if (
                len(result) > len(opening) + len(closing)
                and result.startswith(opening)
                and result.endswith(closing)
                and (
                    result.count(opening) == 2
                    if opening == closing
                    else result.count(opening) == 1 and result.count(closing) == 1
                )
            ):
                result = result[len(opening) : -len(closing)].strip()
                changed = True
                break
        if changed:
            continue
        for wrapper in ("**", "__", "`"):
            if (
                len(result) > 2 * len(wrapper)
                and result.startswith(wrapper)
                and result.endswith(wrapper)
                and result.count(wrapper) == 2
            ):
                result = result[len(wrapper) : -len(wrapper)].strip()
                changed = True
                break

        exact_boxes = [
            content
            for start, end, content in _balanced_boxed_values(result)
            if start == 0 and end == len(result)
        ]
        if exact_boxes:
            result = exact_boxes[-1].strip()
            changed = True

    result = re.sub(r"^\\displaystyle\s*", "", result).strip()
    return result


def _braces_balanced(value: str) -> bool:
    depth = 0
    for char in value:
        if char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth < 0:
                return False
    return depth == 0


def _latex_environments_balanced(value: str) -> bool:
    stack: list[str] = []
    for match in re.finditer(r"\\(begin|end)\{([^{}]+)\}", value):
        kind, environment = match.groups()
        if kind == "begin":
            stack.append(environment)
        elif not stack or stack.pop() != environment:
            return False
    return not stack


def _is_safe_candidate(value: str) -> bool:
    candidate = value.strip()
    if not candidate or len(candidate) > _MAX_CANDIDATE_CHARS:
        return False
    if _UNCERTAINTY.search(candidate) or _PLACEHOLDER.fullmatch(candidate):
        return False
    if _TRUNCATED_TAIL.search(candidate):
        return False
    return _braces_balanced(candidate) and _latex_environments_balanced(candidate)


def _safe_number(value: str) -> Fraction | None:
    stripped = _strip_outer_wrappers(value)
    slash_match = _STRICT_SLASH_FRACTION.fullmatch(stripped)
    if slash_match:
        denominator = int(slash_match.group(2))
        return Fraction(int(slash_match.group(1)), denominator) if denominator else None
    latex_match = _STRICT_LATEX_FRACTION.fullmatch(stripped)
    if latex_match:
        denominator = int(latex_match.group(2))
        return Fraction(int(latex_match.group(1)), denominator) if denominator else None
    if not _STRICT_DECIMAL.fullmatch(stripped) or len(stripped) > 256:
        return None
    try:
        decimal = Decimal(stripped)
    except InvalidOperation:
        return None
    if not decimal.is_finite() or abs(decimal.as_tuple().exponent) > 1_000:
        return None
    return Fraction(decimal)


def _is_fraction(value: str) -> bool:
    stripped = _strip_outer_wrappers(value)
    return bool(
        _STRICT_SLASH_FRACTION.fullmatch(stripped)
        or _STRICT_LATEX_FRACTION.fullmatch(stripped)
    )


def _canonical_for_agreement(value: str) -> tuple[str, Any]:
    number = _safe_number(value)
    if number is not None:
        return "number", (number.numerator, number.denominator)
    normalized = unicodedata.normalize("NFC", _strip_outer_wrappers(value))
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return "text", normalized


def _choose_unique(candidates: list[str]) -> str:
    """只在全部有效声明保守等价时选取；等价数字优先保留分数写法。"""

    cleaned = [_strip_outer_wrappers(item) for item in candidates]
    cleaned = [item for item in cleaned if _is_safe_candidate(item)]
    if not cleaned:
        return ""
    keys = {_canonical_for_agreement(item) for item in cleaned}
    if len(keys) != 1:
        return ""
    fractions = [item for item in cleaned if _is_fraction(item)]
    return fractions[-1] if fractions else cleaned[-1]


def _exact_fraction_from_equivalent_decimal_annotation(value: str) -> str:
    """从“精确分数（即等价小数）”中保守保留原分数文本。"""

    match = _EQUIVALENT_DECIMAL_ANNOTATION.fullmatch(value.strip())
    if match is None:
        return ""
    exact = _strip_outer_wrappers(match.group("exact"))
    decimal = _strip_outer_wrappers(match.group("decimal"))
    if not _is_fraction(exact) or _STRICT_DECIMAL.fullmatch(decimal) is None:
        return ""
    exact_number = _safe_number(exact)
    decimal_number = _safe_number(decimal)
    if exact_number is None or exact_number != decimal_number:
        return ""
    return exact


def _validate_json_shape(value: Any) -> bool:
    nodes = 0
    pending: list[tuple[Any, int]] = [(value, 0)]
    while pending:
        item, depth = pending.pop()
        nodes += 1
        if nodes > _MAX_JSON_NODES or depth > _MAX_JSON_DEPTH:
            return False
        if isinstance(item, list):
            pending.extend((child, depth + 1) for child in item)
        elif isinstance(item, dict):
            if not all(isinstance(key, str) and len(key) <= 128 for key in item):
                return False
            pending.extend((child, depth + 1) for child in item.values())
        elif isinstance(item, float) and not math.isfinite(item):
            return False
        elif item is not None and not isinstance(item, (str, int, float, bool)):
            return False
    return True


def _json_prefix(value: str) -> tuple[str, Any] | None:
    stripped = value.lstrip()
    if not stripped.startswith(("[", "{")) or len(stripped) > _MAX_JSON_CHARS:
        return None

    def build_object(pairs: list[tuple[str, Any]]) -> dict[str, Any]:
        result: dict[str, Any] = {}
        for key, item in pairs:
            if key in result:
                raise ValueError("duplicate JSON key")
            result[key] = item
        return result

    try:
        parsed, end = json.JSONDecoder(
            object_pairs_hook=build_object,
            parse_constant=lambda token: (_ for _ in ()).throw(ValueError(token)),
        ).raw_decode(stripped)
    except (json.JSONDecodeError, OverflowError, RecursionError, ValueError):
        return None
    remainder = stripped[end:].strip().strip("。.")
    if remainder or not _validate_json_shape(parsed):
        return None
    compact = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    return compact, parsed


def _problem_parts(problem: str) -> tuple[int, ...]:
    labels = [int(match.group(1)) for match in _PART_LABEL.finditer(problem)]
    unique: list[int] = []
    for label in labels:
        if label not in unique:
            unique.append(label)
    if len(unique) < 2:
        return ()
    expected = list(range(1, max(unique) + 1))
    return tuple(unique) if unique == expected else ()


def _has_unsupported_multipart(problem: str) -> bool:
    """识别尚不重组的字母、罗马数字或中文序号多问。"""

    labels = [match.group(1).casefold() for match in _NONNUMERIC_PART_LABEL.finditer(problem)]
    return len(dict.fromkeys(labels)) >= 2


def _json_covers_parts(parsed: Any, parts: tuple[int, ...]) -> bool:
    if not parts:
        return True
    if isinstance(parsed, list):
        return len(parsed) == len(parts)
    if not isinstance(parsed, dict) or len(parsed) != len(parts):
        return False
    normalized_keys = {
        re.sub(r"[^0-9]", "", key) for key in parsed if re.sub(r"[^0-9]", "", key)
    }
    return normalized_keys == {str(part) for part in parts}


def _clean_part_value(value: str) -> str:
    candidate = value.strip().lstrip("：:=").strip()
    candidate = _PART_ANSWER_PREFIX.sub("", candidate, count=1).strip()
    candidate = candidate.rstrip("；;").strip()
    nonempty_lines = [line.strip() for line in candidate.splitlines() if line.strip()]
    if len(nonempty_lines) != 1:
        return ""
    candidate = nonempty_lines[0]
    return _strip_outer_wrappers(candidate)


def _labeled_part_values(text: str, parts: tuple[int, ...]) -> dict[int, str] | None:
    matches = list(_PART_LABEL.finditer(text))
    if not matches:
        return None
    collected: dict[int, list[str]] = {part: [] for part in parts}
    for index, match in enumerate(matches):
        part = int(match.group(1))
        if part not in collected:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        candidate = _clean_part_value(text[match.end() : end])
        if _is_safe_candidate(candidate):
            collected[part].append(candidate)
    result: dict[int, str] = {}
    for part in parts:
        selected = _choose_unique(collected[part])
        if not selected:
            return None
        result[part] = selected
    return result


def _labeled_marked_part_values(text: str, parts: tuple[int, ...]) -> dict[int, str] | None:
    """只接受每个编号后紧跟答案标记的分散式多问终答。"""

    matches = list(_PART_LABEL.finditer(text))
    collected: dict[int, list[str]] = {part: [] for part in parts}
    for index, match in enumerate(matches):
        part = int(match.group(1))
        if part not in collected:
            continue
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        segment = text[match.end() : end].lstrip()
        marker = _PART_ANSWER_PREFIX.match(segment)
        if marker is None:
            continue
        tail = segment[marker.end() :].lstrip()
        candidate = _line_candidate(tail, 0)
        if _is_safe_candidate(candidate):
            collected[part].append(candidate)

    result: dict[int, str] = {}
    for part in parts:
        selected = _choose_unique(collected[part])
        if not selected:
            return None
        result[part] = selected
    return result


def _render_parts(values: dict[int, str], problem: str) -> str:
    cjk = len(_CJK.findall(problem))
    latin = len(_LATIN.findall(problem))
    if cjk >= latin:
        return "；".join(f"（{part}）{values[part]}" for part in values)
    return "; ".join(f"({part}) {values[part]}" for part in values)


def _marker_segments(text: str, pattern: re.Pattern[str]) -> list[str]:
    matches = list(pattern.finditer(text))
    return [
        text[match.end() : (matches[index + 1].start() if index + 1 < len(matches) else len(text))]
        for index, match in enumerate(matches)
    ]


def _extract_multipart(text: str, problem: str, parts: tuple[int, ...]) -> str:
    segments = _marker_segments(text, _STRONG_MARKER)
    if segments:
        area = segments[-1].strip()
        parsed_json = _json_prefix(area)
        if parsed_json is not None and _json_covers_parts(parsed_json[1], parts):
            return parsed_json[0]
        values = _labeled_part_values(area, parts)
        return _render_parts(values, problem) if values is not None else ""

    marked_values = _labeled_marked_part_values(text, parts)
    if marked_values is not None:
        return _render_parts(marked_values, problem)

    if (
        len(text) <= 1_024
        and "\n" not in text
        and len(_PART_LABEL.findall(text)) == len(parts)
        and ("；" in text or ";" in text)
    ):
        compact_values = _labeled_part_values(text, parts)
        if compact_values is not None:
            return _render_parts(compact_values, problem)
    return ""


def _is_recoverable_truncation_suffix(lines: list[str]) -> bool:
    suffix = "\n".join(lines).strip()
    return bool(
        _RECOVERABLE_TRUNCATION_TEXT.fullmatch(suffix)
        and _RECOVERABLE_TRUNCATION_SIGNAL.search(suffix)
    )


def _line_candidate(text: str, start: int) -> str:
    tail = text[start:].lstrip()
    parsed_json = _json_prefix(tail)
    if parsed_json is not None:
        return parsed_json[0]
    lines = [line.strip() for line in tail.splitlines() if line.strip()]
    if not lines:
        return ""
    if len(lines) > 1 and not _is_recoverable_truncation_suffix(lines[1:]):
        return ""
    line = lines[0]
    for wrapper in ("**", "__", "`"):
        if line.endswith(wrapper) and not line.startswith(wrapper):
            line = line[: -len(wrapper)].rstrip()
    cleaned = _strip_outer_wrappers(line)
    boxed = [
        content
        for _box_start, _box_end, content in _balanced_boxed_values(cleaned)
        if _is_safe_candidate(content)
    ]
    if boxed:
        return _choose_unique(boxed)
    return cleaned


def _marker_candidates(
    text: str,
    pattern: re.Pattern[str],
    *,
    latest_only: bool = False,
) -> list[str]:
    candidates: list[str] = []
    segments = _marker_segments(text, pattern)
    if latest_only and segments:
        segments = segments[-1:]
    for segment in segments:
        candidate = _line_candidate(segment, 0)
        if not candidate:
            return []
        candidates.append(candidate)
    return candidates


def _localize_boolean(answer: str, problem: str) -> str:
    token = answer.strip()
    cjk = len(_CJK.findall(problem))
    latin = len(_LATIN.findall(problem))
    if cjk >= 4 and _ZH_BOOLEAN_QUESTION.search(problem):
        return {
            "yes": "是",
            "no": "否",
            "true": "真",
            "false": "假",
        }.get(token.casefold(), answer)
    if latin >= 10 and latin > 2 * cjk and _EN_BOOLEAN_QUESTION.search(problem):
        return {
            "是": "Yes",
            "否": "No",
            "真": "True",
            "假": "False",
            "成立": "True",
            "不成立": "False",
        }.get(token, answer)
    return answer


def _finalize_selected(answer: str, problem: str, original: str) -> str:
    """应用只依赖题面的有限输出约束。"""

    if _JSON_REQUEST.search(problem) and answer.lstrip().startswith(("[", "{")):
        parsed = _json_prefix(answer)
        return parsed[0] if parsed is not None else original
    return _localize_boolean(answer, problem)


def _is_compact_bare_answer(text: str) -> bool:
    if not _is_safe_candidate(text) or "\n" in text or len(text) > 512:
        return False
    stripped = _strip_outer_wrappers(text)
    if (
        _safe_number(stripped) is not None
        or _CHOICE.fullmatch(stripped)
        or _BOOLEAN_ANSWER.fullmatch(stripped)
    ):
        return True
    if stripped.startswith(("[", "{")) and _json_prefix(stripped) is not None:
        return True
    return bool(re.search(r"[=<>≤≥∈∉∪∩^_\\]", stripped))


def normalize_final_response(
    final_response: object,
    problem: object = "",
    *,
    prefer_exact_equivalent_annotation: bool = False,
) -> str:
    """返回最简且唯一的终答；无法安全收束时保留原始非空文本。

    处理优先级为完整多子问结构、显式最终答案、保守一致的配平
    ``\\boxed``、行首普通答案标记和已经是裸答案的文本。最后一份行首
    强终答可修订先前草稿；普通声明或 boxed 冲突、歧义和不可修复截断均
    原样回退。``prefer_exact_equivalent_annotation`` 默认关闭；开启时只把
    “精确分数（即严格等价十进制）”收窄为原分数文本。
    """

    if not isinstance(final_response, str):
        return ""
    original = final_response.strip()
    if not original:
        return ""
    problem_text = problem if isinstance(problem, str) else ""
    if _REASONING_REQUIRED.search(problem_text) or _has_unsupported_multipart(problem_text):
        return original
    parts = _problem_parts(problem_text)
    if parts:
        multipart = _extract_multipart(original, problem_text, parts)
        if multipart:
            return multipart
        return original

    strong = _marker_candidates(original, _STRONG_MARKER, latest_only=True)
    if any(_UNCERTAINTY.search(candidate) for candidate in strong):
        return original
    selected = _choose_unique(strong)
    if selected:
        if prefer_exact_equivalent_annotation:
            selected = (
                _exact_fraction_from_equivalent_decimal_annotation(selected)
                or selected
            )
        return _finalize_selected(selected, problem_text, original)
    if _STRONG_MARKER.search(original):
        return original

    boxed = _extract_balanced_boxed(original)
    if boxed:
        return _finalize_selected(_strip_outer_wrappers(boxed), problem_text, original)

    generic = _marker_candidates(original, _GENERIC_MARKER)
    if any(_UNCERTAINTY.search(candidate) for candidate in generic):
        return original
    selected = _choose_unique(generic)
    if selected:
        return _finalize_selected(selected, problem_text, original)
    if _GENERIC_MARKER.search(original):
        return original

    parsed_json = _json_prefix(original)
    if parsed_json is not None:
        return parsed_json[0]
    if _is_compact_bare_answer(original):
        return _finalize_selected(_strip_outer_wrappers(original), problem_text, original)
    return original


__all__ = ["normalize_final_response"]
