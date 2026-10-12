"""Harness v0 的保守 SymPy 白名单验证器。"""

from __future__ import annotations

import ast
import math
import re
import time
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Mapping


MAX_FINAL_SCAN_CHARS = 65_536
MAX_ANSWER_CHARS = 512
MAX_PROBLEM_CHARS = 8_192
MAX_EXPRESSION_CHARS = 512
MAX_AST_NODES = 128
MAX_AST_DEPTH = 16
MAX_INTEGER_BITS = 256
MAX_POWER_ABS = 32
MAX_SYMBOLIC_DEGREE_BOUND = 32
MAX_EQUATIONS = 4

_FINAL_LINE_RE = re.compile(
    r"(?im)^[ \t]*(?:[-*][ \t]+)?(?:\*{0,2})"
    r"(?:最终答案|答案|final\s+answer|answer)(?:\*{0,2})"
    r"\s*(?:[:：=]|为|\bis\b)\s*(?P<answer>[^\r\n]+)$"
)
_DANGEROUS_RE = re.compile(
    r"(?:__|\b(?:import|lambda|open|eval|exec|compile|globals|locals)\b)",
    re.IGNORECASE,
)
_PROOF_RE = re.compile(
    r"(?:证明|论证|说明(?:理由|原因|为什么)?|"
    r"\b(?:prove|proof|justify|show\s+that)\b)",
    re.IGNORECASE,
)
_UNAVAILABLE_ANSWER_RE = re.compile(
    r"^(?:无法确定|不确定|无有效解答|unknown|undetermined|n/?a)$",
    re.IGNORECASE,
)
_BARE_MATH_RE = re.compile(
    r"^[\s\dA-Za-z_\\{}()[\].,+\-*/^=|<>或和、，；;]+$"
)
_BARE_MATH_WORD_RE = re.compile(r"[A-Za-z]+")
_BARE_MATH_WORDS = frozenset(
    {
        "abs",
        "acos",
        "asin",
        "atan",
        "boxed",
        "cos",
        "dfrac",
        "e",
        "exp",
        "frac",
        "infty",
        "ln",
        "log",
        "oo",
        "pi",
        "sin",
        "sqrt",
        "tan",
        "tfrac",
    }
)
_SAFE_EXPRESSION_RE = re.compile(r"^[\s\dA-Za-z_.,()+\-*/^]+$")
_VARIABLE_RE = re.compile(r"^[A-Za-z]$")

_CN_EQUATION_RE = re.compile(
    r"^\s*(?:(?:求解|解)\s*(?:关于\s*(?P<variable>[A-Za-z])\s*的\s*)?方程"
    r"|求\s*方程)\s*[:：]?\s*(?P<equation>.+?)"
    r"(?:\s*的(?:全部)?(?:解|根))?\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_EN_EQUATION_RE = re.compile(
    r"^\s*solve\s+(?P<equation>.+?)\s+for\s+(?P<variable>[A-Za-z])"
    r"\s*[?.]?\s*$",
    re.IGNORECASE,
)
_CN_DIRECT_RE = re.compile(
    r"^\s*(?:计算|求值)\s*(?:表达式\s*)?[:：]?\s*"
    r"(?P<expression>.+?)\s*(?:的值)?\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_CN_VALUE_RE = re.compile(
    r"^\s*求\s*(?:表达式\s*)?(?P<expression>.+?)\s*的值\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_EN_DIRECT_RE = re.compile(
    r"^\s*(?:calculate|evaluate|find\s+the\s+value\s+of)\s+"
    r"(?:the\s+expression\s+)?(?P<expression>.+?)\s*[?.]?\s*$",
    re.IGNORECASE,
)
_CN_DERIVATIVE_RE = re.compile(
    r"^\s*求(?:函数\s*)?(?:(?P<name>[A-Za-z])\s*\(\s*(?P<variable>[A-Za-z])\s*\)\s*=\s*)?"
    r"(?P<expression>.+?)\s*在\s*(?P<point_variable>[A-Za-z])\s*=\s*"
    r"(?P<point>.+?)\s*处的(?:导数|导数值)\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_EN_DERIVATIVE_RE = re.compile(
    r"^\s*(?:find|compute)\s+(?:the\s+)?derivative\s+of\s+"
    r"(?P<expression>.+?)\s+at\s+(?P<point_variable>[A-Za-z])\s*=\s*"
    r"(?P<point>.+?)\s*[?.]?\s*$",
    re.IGNORECASE,
)
_UNICODE_INTEGRAL_RE = re.compile(
    r"^\s*(?:计算|求|evaluate|compute)?\s*(?:定积分|the\s+definite\s+integral)?\s*"
    r"∫\s*[_]?(?P<lower>[^\s^]+)\s*\^?(?P<upper>[^\s]+)\s+"
    r"(?P<expression>.+?)\s*d\s*(?P<variable>[A-Za-z])\s*[。？?.]?\s*$",
    re.IGNORECASE,
)
_LATEX_INTEGRAL_RE = re.compile(
    r"^\s*(?:计算|求|evaluate|compute)?\s*(?:定积分|the\s+definite\s+integral)?\s*"
    r"\\int\s*_\s*\{(?P<lower>[^{}]+)\}\s*\^\s*\{(?P<upper>[^{}]+)\}"
    r"\s*(?P<expression>.+?)\s*(?:\\,|\\;|\s)*d\s*(?P<variable>[A-Za-z])"
    r"\s*[。？?.]?\s*$",
    re.IGNORECASE,
)
_LATEX_SIMPLE_INTEGRAL_RE = re.compile(
    r"^\s*(?:计算|求|evaluate|compute)?\s*(?:定积分|the\s+definite\s+integral)?\s*"
    r"\\int\s*_\s*(?P<lower>[^\s^{}]+)\s*\^\s*(?P<upper>[^\s{}]+)"
    r"\s+(?P<expression>.+?)\s*(?:\\,|\\;|\s)*d\s*(?P<variable>[A-Za-z])"
    r"\s*[。？?.]?\s*$",
    re.IGNORECASE,
)
_CN_INTERVAL_INTEGRAL_RE = re.compile(
    r"^\s*求\s*(?:函数\s*)?(?P<expression>.+?)\s*在\s*"
    r"(?P<lower>\S+?)\s*到\s*(?P<upper>\S+?)\s*上(?:的)?定积分"
    r"\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_LIMIT_RE = re.compile(
    r"^\s*(?:计算|求|evaluate|compute|find)?\s*(?:极限|the\s+limit)?\s*"
    r"(?:\\lim|lim)\s*_\s*\{?\s*(?P<variable>[A-Za-z])\s*"
    r"(?:\\to|→|->)\s*(?P<point>[^}\s]+)\s*\}?\s*"
    r"(?P<expression>.+?)\s*[。？?]?\s*$",
    re.IGNORECASE,
)
_CN_SYSTEM_RE = re.compile(
    r"^\s*(?:求解|解)\s*(?:线性)?方程组\s*[:：]?\s*(?P<equations>.+?)\s*[。？?]?\s*$",
    re.IGNORECASE | re.DOTALL,
)
_EN_SYSTEM_RE = re.compile(
    r"^\s*solve\s+(?:the\s+)?(?:linear\s+)?system\s*[:：]?\s*"
    r"(?P<equations>.+?)\s*[?.]?\s*$",
    re.IGNORECASE | re.DOTALL,
)


@dataclass(frozen=True)
class VerificationResult:
    status: str
    kind: str
    agreed: bool | None
    expected: str | None
    got: str | None
    detail: str
    elapsed_seconds: float


class _NotApplicable(ValueError):
    pass


class _BudgetExpired(RuntimeError):
    pass


class _Clock:
    def __init__(self, now: Callable[[], float], budget_seconds: float) -> None:
        self._now = now
        self.started = float(now())
        if not math.isfinite(self.started):
            raise ValueError("时钟必须返回有限数")
        self.last = self.started
        self.deadline = self.started + budget_seconds

    def check(self) -> None:
        self.last = float(self._now())
        if self.last >= self.deadline:
            raise _BudgetExpired("本地验证预算已用完")

    def elapsed(self) -> float:
        try:
            self.last = float(self._now())
        except BaseException as exc:
            if _must_reraise(exc):
                raise
            pass
        return max(0.0, self.last - self.started)


def _must_reraise(exc: BaseException) -> bool:
    return isinstance(exc, (KeyboardInterrupt, SystemExit, GeneratorExit)) or (
        "DeadlineExceeded" in type(exc).__name__
    )


def _strip_wrappers(value: str) -> str:
    result = value.strip().rstrip("。；;").strip()
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
    if result.startswith(r"\boxed{") and result.endswith("}"):
        inner = result[len(r"\boxed{") : -1]
        if _balanced(inner):
            result = inner.strip()
    return result


def _balanced(value: str) -> bool:
    pairs = {"(": ")", "[": "]", "{": "}"}
    closing = set(pairs.values())
    stack: list[str] = []
    for char in value:
        if char in pairs:
            stack.append(pairs[char])
        elif char in closing:
            if not stack or stack.pop() != char:
                return False
    return not stack


def _canonical(value: str) -> str:
    return re.sub(r"\s+", "", _strip_wrappers(value)).casefold()


def _looks_like_bare_math_answer(value: str) -> bool:
    """只接受无需自然语言解释即可成立的单行数学答案。"""

    if not _BARE_MATH_RE.fullmatch(value):
        return False
    if not (re.search(r"\d", value) or re.search(r"(?:\\pi|\\infty|\b(?:pi|oo|e)\b)", value)):
        return False
    for word in _BARE_MATH_WORD_RE.findall(value):
        lowered = word.casefold()
        if len(word) == 1 or lowered in _BARE_MATH_WORDS:
            continue
        return False
    return True


def extract_final_answer(final_response: str) -> str | None:
    """提取唯一、完整的显式终答行；有歧义时拒绝。"""

    try:
        if not isinstance(final_response, str) or not final_response.strip():
            return None
        bounded = final_response[-MAX_FINAL_SCAN_CHARS:]
        candidates = []
        explicit_matches = list(_FINAL_LINE_RE.finditer(bounded))
        for match in explicit_matches:
            candidate = _strip_wrappers(match.group("answer"))
            if (
                not candidate
                or len(candidate) > MAX_ANSWER_CHARS
                or not _balanced(candidate)
                or _UNAVAILABLE_ANSWER_RE.fullmatch(candidate)
            ):
                continue
            candidates.append(candidate)
        if not candidates and explicit_matches:
            return None
        if not candidates:
            bare = _strip_wrappers(final_response)
            if (
                bare
                and "\n" not in bare
                and len(bare) <= MAX_ANSWER_CHARS
                and _balanced(bare)
                and not _UNAVAILABLE_ANSWER_RE.fullmatch(bare)
                and _looks_like_bare_math_answer(bare)
            ):
                return bare
            return None
        if len({_canonical(item) for item in candidates}) != 1:
            return None
        return candidates[-1]
    except Exception:
        return None


def _replace_latex_commands(value: str) -> str:
    result = value
    for command, replacement in (
        (r"\left", ""),
        (r"\right", ""),
        (r"\cdot", "*"),
        (r"\times", "*"),
        (r"\div", "/"),
        (r"\pi", "pi"),
        (r"\infty", "oo"),
        (r"\operatorname{abs}", "abs"),
        (r"\arcsin", "asin"),
        (r"\arccos", "acos"),
        (r"\arctan", "atan"),
        (r"\sin", "sin"),
        (r"\cos", "cos"),
        (r"\tan", "tan"),
        (r"\exp", "exp"),
        (r"\ln", "log"),
        (r"\log", "log"),
    ):
        result = result.replace(command, replacement)
    return result


def _brace_group(value: str, start: int) -> tuple[str, int]:
    if start >= len(value) or value[start] != "{":
        raise _NotApplicable("LaTeX 分组不完整")
    depth = 0
    for index in range(start, len(value)):
        if value[index] == "{":
            depth += 1
        elif value[index] == "}":
            depth -= 1
            if depth == 0:
                return value[start + 1 : index], index + 1
    raise _NotApplicable("LaTeX 分组不平衡")


def _expand_latex_groups(value: str, clock: _Clock) -> str:
    result = value
    for _ in range(16):
        clock.check()
        match = re.search(r"\\(?:d?frac|tfrac|sqrt)\s*\{", result)
        if match is None:
            return result
        command = match.group(0).split("{")[0].strip()
        first, after_first = _brace_group(result, result.find("{", match.start()))
        if command.endswith("sqrt"):
            replacement = f"sqrt({_expand_latex_groups(first, clock)})"
            result = result[: match.start()] + replacement + result[after_first:]
            continue
        cursor = after_first
        while cursor < len(result) and result[cursor].isspace():
            cursor += 1
        second, after_second = _brace_group(result, cursor)
        replacement = (
            f"(({_expand_latex_groups(first, clock)})/"
            f"({_expand_latex_groups(second, clock)}))"
        )
        result = result[: match.start()] + replacement + result[after_second:]
    raise _NotApplicable("LaTeX 嵌套层数超限")


def _normalize_expression(value: str, clock: _Clock) -> str:
    text = _strip_wrappers(value)
    if (
        not text
        or len(text) > MAX_EXPRESSION_CHARS
        or "\n" in text
        or _DANGEROUS_RE.search(text)
    ):
        raise _NotApplicable("表达式为空、过长或含禁用标记")
    text = _expand_latex_groups(_replace_latex_commands(text), clock)
    text = (
        text.replace("×", "*")
        .replace("·", "*")
        .replace("÷", "/")
        .replace("−", "-")
        .replace("∞", "oo")
        .replace("π", "pi")
        .replace("^", "**")
    )
    text = re.sub(r"\s+", "", text)
    if not text or not _SAFE_EXPRESSION_RE.fullmatch(text):
        raise _NotApplicable("表达式含白名单外字符")
    # 只补最常见且无歧义的隐式乘法，不引入通用语法猜测。
    text = re.sub(r"(?<=\d)(?=[A-Za-z(])", "*", text)
    text = re.sub(r"(?<=\))(?=[A-Za-z\d(])", "*", text)
    return text


class _AstToSympy:
    def __init__(self, sp: Any, *, allowed_symbols: Iterable[str]) -> None:
        self.sp = sp
        self.allowed_symbols = frozenset(allowed_symbols)
        self.nodes = 0

    def convert(self, node: ast.AST, depth: int = 0) -> Any:
        self.nodes += 1
        if depth > MAX_AST_DEPTH or self.nodes > MAX_AST_NODES:
            raise _NotApplicable("表达式资源规模超限")
        if isinstance(node, ast.Constant):
            if type(node.value) is int:
                if abs(node.value).bit_length() > MAX_INTEGER_BITS:
                    raise _NotApplicable("整数位数超限")
                return self.sp.Integer(node.value)
            if type(node.value) is float and math.isfinite(node.value):
                return self.sp.Rational(str(node.value))
            raise _NotApplicable("常量类型不受支持")
        if isinstance(node, ast.Name):
            if node.id in self.allowed_symbols and _VARIABLE_RE.fullmatch(node.id):
                return self.sp.Symbol(node.id)
            constants = {"pi": self.sp.pi, "e": self.sp.E, "oo": self.sp.oo}
            if node.id in constants:
                return constants[node.id]
            raise _NotApplicable("表达式含未授权符号")
        if isinstance(node, ast.UnaryOp):
            value = self.convert(node.operand, depth + 1)
            if isinstance(node.op, ast.UAdd):
                return value
            if isinstance(node.op, ast.USub):
                return -value
            raise _NotApplicable("一元运算不受支持")
        if isinstance(node, ast.BinOp):
            left = self.convert(node.left, depth + 1)
            right = self.convert(node.right, depth + 1)
            if isinstance(node.op, ast.Add):
                return left + right
            if isinstance(node.op, ast.Sub):
                return left - right
            if isinstance(node.op, ast.Mult):
                return left * right
            if isinstance(node.op, ast.Div):
                return left / right
            if isinstance(node.op, ast.Pow):
                if not right.is_Integer or abs(int(right)) > MAX_POWER_ABS:
                    raise _NotApplicable("指数不在安全范围")
                return left**right
            raise _NotApplicable("二元运算不受支持")
        if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
            if node.keywords or len(node.args) != 1:
                raise _NotApplicable("函数参数不受支持")
            functions = {
                "sin": self.sp.sin,
                "cos": self.sp.cos,
                "tan": self.sp.tan,
                "asin": self.sp.asin,
                "acos": self.sp.acos,
                "atan": self.sp.atan,
                "exp": self.sp.exp,
                "log": self.sp.log,
                "sqrt": self.sp.sqrt,
                "abs": self.sp.Abs,
            }
            function = functions.get(node.func.id)
            if function is None:
                raise _NotApplicable("函数不在白名单")
            return function(self.convert(node.args[0], depth + 1))
        raise _NotApplicable("表达式语法不受支持")


def _integer_literal(node: ast.AST) -> int | None:
    if isinstance(node, ast.Constant) and type(node.value) is int:
        return node.value
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, (ast.UAdd, ast.USub)):
        value = _integer_literal(node.operand)
        if value is not None:
            return -value if isinstance(node.op, ast.USub) else value
    return None


def _degree_bound(node: ast.AST, allowed_symbols: frozenset[str], depth: int = 0) -> int:
    """保守估计符号算术次数，先拒绝嵌套幂展开。"""

    if depth > MAX_AST_DEPTH:
        raise _NotApplicable("表达式深度超限")
    if isinstance(node, ast.Constant):
        return 0
    if isinstance(node, ast.Name):
        return 1 if node.id in allowed_symbols else 0
    if isinstance(node, ast.UnaryOp):
        return _degree_bound(node.operand, allowed_symbols, depth + 1)
    if isinstance(node, ast.BinOp):
        left = _degree_bound(node.left, allowed_symbols, depth + 1)
        right = _degree_bound(node.right, allowed_symbols, depth + 1)
        if isinstance(node.op, (ast.Add, ast.Sub)):
            bound = max(left, right)
        elif isinstance(node.op, (ast.Mult, ast.Div)):
            bound = left + right
        elif isinstance(node.op, ast.Pow):
            exponent = _integer_literal(node.right)
            if exponent is None:
                raise _NotApplicable("指数必须是有界整数")
            bound = left * abs(exponent)
        else:
            return MAX_SYMBOLIC_DEGREE_BOUND + 1
        if bound > MAX_SYMBOLIC_DEGREE_BOUND:
            raise _NotApplicable("表达式估计次数超限")
        return bound
    if isinstance(node, ast.Call) and len(node.args) == 1:
        return _degree_bound(node.args[0], allowed_symbols, depth + 1)
    return MAX_SYMBOLIC_DEGREE_BOUND + 1


def _parse_expression(
    value: str,
    sp: Any,
    clock: _Clock,
    *,
    allowed_symbols: Iterable[str] = (),
) -> Any:
    clock.check()
    normalized = _normalize_expression(value, clock)
    try:
        parsed = ast.parse(normalized, mode="eval")
    except (SyntaxError, ValueError, MemoryError, RecursionError):
        raise _NotApplicable("表达式语法无法安全解析") from None
    symbol_names = frozenset(allowed_symbols)
    _degree_bound(parsed.body, symbol_names)
    result = _AstToSympy(sp, allowed_symbols=symbol_names).convert(parsed.body)
    clock.check()
    return result


def _split_equation(value: str) -> tuple[str, str]:
    text = _strip_wrappers(value)
    if text.count("=") != 1 or any(token in text for token in ("<=", ">=", "!=", "==")):
        raise _NotApplicable("方程必须含唯一等号")
    left, right = text.split("=", 1)
    if not left.strip() or not right.strip():
        raise _NotApplicable("方程两侧不能为空")
    return left, right


def _split_top_level(value: str) -> list[str]:
    text = value.strip()
    if len(text) >= 2 and (text[0], text[-1]) in {
        ("{", "}"),
        ("[", "]"),
        ("(", ")"),
    }:
        text = text[1:-1].strip()
    parts: list[str] = []
    start = 0
    stack: list[str] = []
    pairs = {"(": ")", "[": "]", "{": "}"}
    for index, char in enumerate(text):
        if char in pairs:
            stack.append(pairs[char])
        elif char in pairs.values():
            if not stack or stack.pop() != char:
                raise _NotApplicable("候选分隔符不平衡")
        elif char in ",，;；、或和" and not stack:
            parts.append(text[start:index].strip())
            start = index + 1
    if stack:
        raise _NotApplicable("候选分隔符不平衡")
    parts.append(text[start:].strip())
    if not parts or any(not part for part in parts):
        raise _NotApplicable("候选列表为空")
    return parts


def _answer_values(
    answer: str,
    sp: Any,
    clock: _Clock,
    *,
    variable: str | None = None,
) -> list[Any]:
    values = []
    for part in _split_top_level(answer):
        if "=" in part:
            left, right = _split_equation(part)
            label = left.strip()
            if variable is None or re.fullmatch(rf"{re.escape(variable)}(?:_?\d+)?", label) is None:
                raise _NotApplicable("终答变量与题面不一致")
            part = right
        values.append(_parse_expression(part, sp, clock))
    if len(values) > 8:
        raise _NotApplicable("候选答案数量超限")
    return values


def _format_expression(value: Any) -> str:
    return str(value)


def _symbolic_equal(left: Any, right: Any, sp: Any, mp: Any, clock: _Clock) -> bool | None:
    clock.check()
    difference = sp.cancel(left - right)
    clock.check()
    simplified = sp.simplify(difference)
    clock.check()
    if simplified == 0 or simplified.is_zero is True:
        return True
    if simplified.is_zero is False and not simplified.free_symbols:
        if simplified.is_Rational or simplified.is_Integer or simplified.is_algebraic is True:
            return False
    if left.free_symbols or right.free_symbols:
        return None
    try:
        with mp.workdps(60):
            left_value = mp.mpc(str(sp.N(left, 60)))
            right_value = mp.mpc(str(sp.N(right, 60)))
            if not all(
                mp.isfinite(item)
                for item in (
                    left_value.real,
                    left_value.imag,
                    right_value.real,
                    right_value.imag,
                )
            ):
                return None
            scale = max(mp.mpf(1), abs(left_value), abs(right_value))
            if abs(left_value - right_value) / scale < mp.mpf("1e-25"):
                return True
    except (ArithmeticError, TypeError, ValueError):
        return None
    finally:
        clock.check()
    # 数值不一致不是严格反证，低误报策略下不返回 False。
    return None


def _bounded_polynomial(expression: Any, symbol: Any, sp: Any) -> Any:
    try:
        polynomial = sp.Poly(expression, symbol)
    except (sp.PolynomialError, TypeError, ValueError):
        raise _NotApplicable("表达式不在低次多项式白名单") from None
    if polynomial.degree() < 0 or polynomial.degree() > 8:
        raise _NotApplicable("多项式次数超出白名单")
    return polynomial


def _bounded_rational(expression: Any, symbol: Any, sp: Any) -> Any:
    numerator, denominator = sp.fraction(sp.cancel(expression))
    _bounded_polynomial(numerator, symbol, sp)
    _bounded_polynomial(denominator, symbol, sp)
    return numerator / denominator


def _equation_plan(problem: str) -> tuple[str, str, str] | None:
    match = _CN_EQUATION_RE.fullmatch(problem) or _EN_EQUATION_RE.fullmatch(problem)
    if match is None:
        return None
    left, right = _split_equation(match.group("equation"))
    explicit = match.groupdict().get("variable")
    return left, right, explicit or ""


def _verify_equation_root(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    plan = _equation_plan(problem)
    if plan is None:
        raise _NotApplicable("题面不是受支持的显式单变量方程")
    left_text, right_text, explicit_variable = plan
    symbol_names = set(re.findall(r"\b[A-Za-z]\b", f"{left_text} {right_text}"))
    if explicit_variable:
        symbol_names.add(explicit_variable)
    if len(symbol_names) != 1:
        raise _NotApplicable("方程变量不唯一")
    variable = next(iter(symbol_names))
    left = _parse_expression(left_text, sp, clock, allowed_symbols={variable})
    right = _parse_expression(right_text, sp, clock, allowed_symbols={variable})
    symbol = sp.Symbol(variable)
    try:
        left_polynomial = sp.Poly(left, symbol)
        right_polynomial = sp.Poly(right, symbol)
    except (sp.PolynomialError, TypeError, ValueError):
        raise _NotApplicable("方程两侧必须是多项式") from None
    expression = left_polynomial.as_expr() - right_polynomial.as_expr()
    candidates = _answer_values(answer, sp, clock, variable=variable)
    if not candidates:
        raise _NotApplicable("终答没有候选根")
    for candidate in candidates:
        clock.check()
        residual = sp.simplify(expression.subs(symbol, candidate))
        if residual == 0 or residual.is_zero is True:
            continue
        if residual.is_zero is False:
            return "contradicted", None, "候选根代回原方程不成立"
        raise _NotApplicable("代回结果无法严格判定")
    try:
        polynomial = sp.Poly(expression, symbol)
    except (sp.PolynomialError, TypeError, ValueError):
        raise _NotApplicable("只能证明候选是根，无法证明解集完整") from None
    if polynomial.degree() < 1 or polynomial.degree() > 4:
        raise _NotApplicable("方程次数不在完整求解白名单")
    clock.check()
    roots = sp.solve(polynomial.as_expr(), symbol)
    clock.check()
    if not isinstance(roots, list) or len(roots) > 8:
        raise _NotApplicable("SymPy 未给出有限完整解集")
    unmatched = list(roots)
    for candidate in candidates:
        match_index = next(
            (
                index
                for index, root in enumerate(unmatched)
                if _symbolic_equal(candidate, root, sp, mp, clock) is True
            ),
            None,
        )
        if match_index is None:
            return "contradicted", str(roots), "候选根不属于完整解集"
        unmatched.pop(match_index)
    if unmatched:
        return "contradicted", str(roots), "终答遗漏原方程的根"
    return "verified", str(roots), "候选根代回成立且与完整解集一致"


def _integral_plan(problem: str) -> Mapping[str, str] | None:
    match = (
        _LATEX_INTEGRAL_RE.fullmatch(problem)
        or _LATEX_SIMPLE_INTEGRAL_RE.fullmatch(problem)
        or _UNICODE_INTEGRAL_RE.fullmatch(problem)
    )
    if match is not None:
        return match.groupdict()
    match = _CN_INTERVAL_INTEGRAL_RE.fullmatch(problem)
    if match is None:
        return None
    plan = match.groupdict()
    variables = set(re.findall(r"\b[A-Za-z]\b", plan["expression"]))
    if len(variables) != 1:
        return None
    plan["variable"] = next(iter(variables))
    return plan


def _verify_integral(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    plan = _integral_plan(problem)
    if plan is None:
        raise _NotApplicable("题面不是受支持的显式定积分")
    variable = plan["variable"]
    symbol = sp.Symbol(variable)
    expression = _parse_expression(plan["expression"], sp, clock, allowed_symbols={variable})
    _bounded_polynomial(expression, symbol, sp)
    lower = _parse_expression(plan["lower"], sp, clock)
    upper = _parse_expression(plan["upper"], sp, clock)
    got = _parse_expression(answer, sp, clock)
    clock.check()
    expected = sp.integrate(expression, (symbol, lower, upper))
    clock.check()
    if expected.has(sp.Integral):
        raise _NotApplicable("SymPy 未完成定积分")
    agreed = _symbolic_equal(expected, got, sp, mp, clock)
    if agreed is True:
        return "verified", _format_expression(expected), "独立定积分结果与终答一致"
    if agreed is False:
        return "contradicted", _format_expression(expected), "独立定积分结果与终答矛盾"
    raise _NotApplicable("定积分结果无法严格比较")


def _derivative_plan(problem: str) -> Mapping[str, str] | None:
    match = _CN_DERIVATIVE_RE.fullmatch(problem) or _EN_DERIVATIVE_RE.fullmatch(problem)
    return match.groupdict() if match is not None else None


def _verify_derivative(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    plan = _derivative_plan(problem)
    if plan is None:
        raise _NotApplicable("题面不是受支持的显式点导数")
    variable = plan.get("variable") or plan["point_variable"]
    if variable != plan["point_variable"]:
        raise _NotApplicable("求导变量不一致")
    symbol = sp.Symbol(variable)
    expression = _parse_expression(plan["expression"], sp, clock, allowed_symbols={variable})
    _bounded_polynomial(expression, symbol, sp)
    point = _parse_expression(plan["point"], sp, clock)
    got = _parse_expression(answer, sp, clock)
    clock.check()
    expected = sp.diff(expression, symbol).subs(symbol, point)
    clock.check()
    agreed = _symbolic_equal(expected, got, sp, mp, clock)
    if agreed is True:
        return "verified", _format_expression(expected), "独立求导并代入后与终答一致"
    if agreed is False:
        return "contradicted", _format_expression(expected), "独立点导数与终答矛盾"
    raise _NotApplicable("点导数结果无法严格比较")


def _limit_plan(problem: str) -> Mapping[str, str] | None:
    match = _LIMIT_RE.fullmatch(problem)
    return match.groupdict() if match is not None else None


def _verify_limit(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    plan = _limit_plan(problem)
    if plan is None:
        raise _NotApplicable("题面不是受支持的显式极限")
    variable = plan["variable"]
    symbol = sp.Symbol(variable)
    expression = _parse_expression(plan["expression"], sp, clock, allowed_symbols={variable})
    expression = _bounded_rational(expression, symbol, sp)
    point = _parse_expression(plan["point"], sp, clock)
    got = _parse_expression(answer, sp, clock)
    clock.check()
    expected = sp.limit(expression, symbol, point)
    clock.check()
    if expected.has(sp.Limit):
        raise _NotApplicable("SymPy 未完成极限")
    agreed = _symbolic_equal(expected, got, sp, mp, clock)
    if agreed is True:
        return "verified", _format_expression(expected), "独立极限结果与终答一致"
    if agreed is False:
        return "contradicted", _format_expression(expected), "独立极限结果与终答矛盾"
    raise _NotApplicable("极限结果无法严格比较")


def _system_plan(problem: str) -> list[tuple[str, str]] | None:
    match = _CN_SYSTEM_RE.fullmatch(problem) or _EN_SYSTEM_RE.fullmatch(problem)
    if match is None:
        return None
    equations_text = _strip_wrappers(match.group("equations")).replace("\\begin{cases}", "").replace("\\end{cases}", "")
    equations_text = equations_text.replace(r"\\", ";")
    parts = [part.strip() for part in re.split(r"[,，;；\n]", equations_text) if part.strip()]
    if not 1 <= len(parts) <= MAX_EQUATIONS:
        raise _NotApplicable("方程组规模不在白名单")
    return [_split_equation(part) for part in parts]


def _answer_assignments(answer: str, sp: Any, clock: _Clock) -> dict[str, Any]:
    assignments: dict[str, Any] = {}
    for part in _split_top_level(answer):
        left, right = _split_equation(part)
        variable = left.strip()
        if not _VARIABLE_RE.fullmatch(variable) or variable in assignments:
            raise _NotApplicable("终答变量赋值无效或重复")
        assignments[variable] = _parse_expression(right, sp, clock)
    return assignments


def _verify_linear_system(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    plan = _system_plan(problem)
    if plan is None:
        raise _NotApplicable("题面不是受支持的显式线性方程组")
    variable_names = set(re.findall(r"\b[A-Za-z]\b", " ".join(sum(plan, ()))))
    if not 1 <= len(variable_names) <= MAX_EQUATIONS:
        raise _NotApplicable("方程组变量数量不在白名单")
    symbols = [sp.Symbol(name) for name in sorted(variable_names)]
    expressions = [
        _parse_expression(left, sp, clock, allowed_symbols=variable_names)
        - _parse_expression(right, sp, clock, allowed_symbols=variable_names)
        for left, right in plan
    ]
    try:
        if any(sp.Poly(expression, *symbols).total_degree() > 1 for expression in expressions):
            raise _NotApplicable("方程组不是线性的")
    except sp.PolynomialError:
        raise _NotApplicable("方程组不是多项式线性系统") from None
    assignments = _answer_assignments(answer, sp, clock)
    if set(assignments) != variable_names:
        raise _NotApplicable("终答没有给出全部且仅给出题面变量")
    substitutions = {sp.Symbol(name): value for name, value in assignments.items()}
    for expression in expressions:
        clock.check()
        residual = sp.simplify(expression.subs(substitutions))
        if residual == 0 or residual.is_zero is True:
            continue
        if residual.is_zero is False:
            return "contradicted", None, "候选解代回线性方程组不成立"
        raise _NotApplicable("线性方程组残差无法严格判定")
    clock.check()
    solution_set = sp.linsolve(expressions, symbols)
    clock.check()
    if not isinstance(solution_set, sp.FiniteSet) or len(solution_set) != 1:
        raise _NotApplicable("线性方程组没有可确认的唯一解")
    expected_tuple = next(iter(solution_set))
    if any(value.free_symbols for value in expected_tuple):
        raise _NotApplicable("线性方程组解不是唯一常量向量")
    for symbol, expected_value in zip(symbols, expected_tuple):
        agreed = _symbolic_equal(assignments[str(symbol)], expected_value, sp, mp, clock)
        if agreed is False:
            return "contradicted", str(expected_tuple), "候选向量与唯一解矛盾"
        if agreed is not True:
            raise _NotApplicable("唯一解与候选向量无法严格比较")
    return "verified", str(expected_tuple), "候选向量代回成立且等于唯一解"


def _direct_plan(problem: str) -> str | None:
    match = _CN_DIRECT_RE.fullmatch(problem) or _CN_VALUE_RE.fullmatch(problem) or _EN_DIRECT_RE.fullmatch(problem)
    return match.group("expression") if match is not None else None


def _verify_numeric_closed_form(
    problem: str, answer: str, sp: Any, mp: Any, clock: _Clock
) -> tuple[str, str | None, str]:
    expression_text = _direct_plan(problem)
    if expression_text is None:
        raise _NotApplicable("题面不是受支持的显式闭式求值")
    expected = _parse_expression(expression_text, sp, clock)
    got = _parse_expression(answer, sp, clock)
    if expected.free_symbols or got.free_symbols:
        raise _NotApplicable("闭式求值含自由变量")
    clock.check()
    expected = sp.simplify(expected)
    clock.check()
    agreed = _symbolic_equal(expected, got, sp, mp, clock)
    if agreed is True:
        return "verified", _format_expression(expected), "独立闭式求值与终答一致"
    if agreed is False:
        return "contradicted", _format_expression(expected), "独立闭式求值与终答矛盾"
    raise _NotApplicable("闭式结果无法严格比较")


def _result(
    status: str,
    kind: str,
    expected: str | None,
    got: str | None,
    detail: str,
    clock: _Clock | None,
) -> VerificationResult:
    agreed = True if status == "verified" else False if status == "contradicted" else None
    elapsed = clock.elapsed() if clock is not None else 0.0
    return VerificationResult(
        status=status,
        kind=kind,
        agreed=agreed,
        expected=expected,
        got=got,
        detail=str(detail)[:200],
        elapsed_seconds=elapsed,
    )


def verify(
    problem: str,
    final_response: str,
    *,
    budget_seconds: float = 20.0,
    now: Callable[[], float] | None = None,
) -> VerificationResult:
    """在严格题面白名单内独立验证终答，歧义情形一律拒绝判定。"""

    clock: _Clock | None = None
    kind = ""
    got: str | None = None
    try:
        clock_fn = time.monotonic if now is None else now
        if not callable(clock_fn):
            return _result("error", "", None, None, "now 必须可调用", None)
        if isinstance(budget_seconds, bool):
            return _result("error", "", None, None, "验证预算必须是正有限数", None)
        budget = float(budget_seconds)
        if not math.isfinite(budget) or budget <= 0:
            return _result("error", "", None, None, "验证预算必须是正有限数", None)
        clock = _Clock(clock_fn, budget)
        clock.check()
        if (
            not isinstance(problem, str)
            or not problem.strip()
            or len(problem) > MAX_PROBLEM_CHARS
            or _DANGEROUS_RE.search(problem)
        ):
            return _result("not_applicable", "", None, None, "题面为空、过长或含禁用标记", clock)
        if _PROOF_RE.search(problem):
            return _result("not_applicable", "", None, None, "证明类题目不在 v0 白名单", clock)
        got = extract_final_answer(final_response)
        if got is None:
            return _result("not_applicable", "", None, None, "未提取到唯一完整终答", clock)
        if _DANGEROUS_RE.search(got):
            return _result("not_applicable", "", None, got, "终答含禁用标记", clock)

        try:
            import mpmath as mp
            import sympy as sp
        except ImportError:
            return _result("error", "", None, got, "SymPy 或 mpmath 依赖不可用", clock)

        builders = (
            ("linear_system", _system_plan, _verify_linear_system),
            ("equation_root", _equation_plan, _verify_equation_root),
            ("definite_integral", _integral_plan, _verify_integral),
            ("derivative_at_point", _derivative_plan, _verify_derivative),
            ("limit", _limit_plan, _verify_limit),
            ("numeric_closed_form", _direct_plan, _verify_numeric_closed_form),
        )
        for candidate_kind, detector, verifier in builders:
            clock.check()
            if detector(problem.strip()) is None:
                continue
            kind = candidate_kind
            status, expected, detail = verifier(problem.strip(), got, sp, mp, clock)
            return _result(status, kind, expected, got, detail, clock)
        return _result("not_applicable", "", None, got, "题面未命中 v0 白名单", clock)
    except _NotApplicable as exc:
        return _result("not_applicable", kind, None, got, str(exc), clock)
    except _BudgetExpired as exc:
        return _result("error", kind, None, got, str(exc), clock)
    except Exception as exc:
        if _must_reraise(exc):
            raise
        return _result("error", kind, None, got, f"验证内部错误：{type(exc).__name__}", clock)
    except BaseException as exc:
        if _must_reraise(exc):
            raise
        return _result("error", kind, None, got, f"验证内部错误：{type(exc).__name__}", clock)


__all__ = ["VerificationResult", "extract_final_answer", "verify"]
