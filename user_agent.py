"""SL-v3 条件续写入口：协作预算闸与主线程抢占兜底。"""

from __future__ import annotations

import signal
import threading
import time
from contextlib import contextmanager
import re
from typing import Any, Dict, Iterator, Mapping

from implementations.candidates.sl_v3_cont.user_agent import (
    AgentConfig,
    ReasoningAgent as _SLV3ContReasoningAgent,
    SOLVE_DEADLINE_SECONDS,
    solve_budget_seconds,
)


class _SolveDeadlineExceeded(BaseException):
    """单题主动截止，给平台六小时总预算保留调度余量。"""


# H-A：主路由之前的一次短预算答案先行兜底；关闭时保留基座行为。
RBP_HA_ANSWER_FIRST = False
H_A_MAX_TOKENS = 2048
H_A_TEMPERATURE = 0.2
H_A_THINKING_MODE = True
H_A_PROMPT = (
    "请只输出一个唯一最终答案，必须使用 \\boxed{...} 包裹；不要写推导、解释或多个候选。"
    "\n\n题目：\n"
)


@contextmanager
def _realtime_deadline(seconds: float) -> Iterator[str]:
    """主线程启用抢占计时器；工作线程显式降级为协作模式。"""

    if threading.current_thread() is not threading.main_thread() or not all(
        hasattr(signal, attribute)
        for attribute in ("SIGALRM", "ITIMER_REAL", "getitimer", "setitimer")
    ):
        yield "cooperative_only"
        return

    try:
        previous_delay, previous_interval = signal.getitimer(signal.ITIMER_REAL)
        previous_handler = signal.getsignal(signal.SIGALRM)
    except (OSError, ValueError):
        yield "cooperative_only"
        return

    if 0.0 < previous_delay <= seconds:
        yield "preemptive"
        return

    def expire(_signum: int, _frame: object) -> None:
        raise _SolveDeadlineExceeded("solve deadline exceeded")

    started_at = time.monotonic()
    handler_installed = False
    try:
        signal.signal(signal.SIGALRM, expire)
        handler_installed = True
        signal.setitimer(signal.ITIMER_REAL, seconds)
    except (OSError, ValueError):
        if handler_installed:
            signal.signal(signal.SIGALRM, previous_handler)
        yield "cooperative_only"
        return

    try:
        yield "preemptive"
    finally:
        elapsed = max(0.0, time.monotonic() - started_at)
        try:
            signal.setitimer(signal.ITIMER_REAL, 0.0)
            signal.signal(signal.SIGALRM, previous_handler)
            if previous_delay > 0.0:
                remaining = max(1e-6, previous_delay - elapsed)
                signal.setitimer(signal.ITIMER_REAL, remaining, previous_interval)
        except (OSError, ValueError):
            pass


class ReasoningAgent(_SLV3ContReasoningAgent):
    """给动态续写 harness 增加批次分摊和截止模式遥测。"""

    def _ha_enabled(self) -> bool:
        return bool(getattr(self, "_ha_answer_first_enabled", RBP_HA_ANSWER_FIRST))

    @staticmethod
    def _ha_boxed_fragment(value: Any) -> str:
        """提取一个完整 ``\\boxed{...}``；无完整 boxed 时返回空串。"""

        text = value if isinstance(value, str) else ""
        match = re.search(r"\\boxed\s*\{", text)
        if match is None:
            return ""
        opening = text.find("{", match.start(), match.end())
        if opening < 0:
            return ""
        depth = 0
        for index in range(opening, len(text)):
            char = text[index]
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[match.start() : index + 1].strip()
                if depth < 0:
                    return ""
        return ""

    def _ha_mark_main_response(self, response: Any) -> None:
        if getattr(self, "_ha_phase", "idle") != "main":
            return
        if self._ha_boxed_fragment(self._extract_text(response)):
            self._ha_main_boxed_seen = True

    def _record_primary_response(self, response: Any) -> None:
        super()._record_primary_response(response)
        self._ha_mark_main_response(response)

    def _call_uncaptured(
        self,
        messages: list[dict[str, Any]],
        kwargs: Mapping[str, Any],
        *,
        on_response: Any = None,
    ) -> tuple[Any, str | None]:
        response, finish_reason = super()._call_uncaptured(
            messages,
            kwargs,
            on_response=on_response,
        )
        self._ha_mark_main_response(response)
        return response, finish_reason

    def _ha_answer_first(self, problem: str) -> str:
        """执行一次 fail-open 的短预算答案先行调用。"""

        if not self._ha_enabled():
            return ""
        client = getattr(self, "_source_client", None)
        if client is None:
            return ""
        messages = [
            {
                "role": "user",
                "content": f"{H_A_PROMPT}{problem}",
            }
        ]
        try:
            response = client.chat(
                messages,
                temperature=H_A_TEMPERATURE,
                max_tokens=H_A_MAX_TOKENS,
                thinking_mode=H_A_THINKING_MODE,
            )
        except Exception:
            return ""
        return self._ha_boxed_fragment(self._extract_text(response))

    def _ha_apply_fallback(self, result: Dict) -> Dict:
        if (
            not self._ha_enabled()
            or self._ha_main_boxed_seen
            or not self._ha_answer_first_candidate
        ):
            return result
        fallback = self._result_from_answer(
            self._ha_answer_first_candidate,
            "h_a_answer_first_fallback",
        )
        fallback.setdefault("trace", []).append(
            {
                "step": "h_a_answer_first",
                "content": {
                    "status": "used",
                    "max_tokens": H_A_MAX_TOKENS,
                    "temperature": H_A_TEMPERATURE,
                    "thinking_mode": H_A_THINKING_MODE,
                    "main_boxed_seen": False,
                },
            }
        )
        return fallback

    def solve(self, problem: str, metadata: Dict) -> Dict:
        budget_seconds = solve_budget_seconds(metadata)
        self._start_solve(budget_seconds)
        self._ha_main_boxed_seen = False
        self._ha_answer_first_candidate = ""
        try:
            with _realtime_deadline(budget_seconds) as deadline_mode:
                self._set_deadline_mode(deadline_mode)
                self._ha_phase = "answer_first"
                self._ha_answer_first_candidate = self._ha_answer_first(problem)
                self._ha_phase = "main"
                first = self._solve_prepared(problem, metadata)
                # 必须在这里再走一次加路判定：正式评测只调用本类的 solve()，
                # 内层 sl_v3_cont.ReasoningAgent.solve() 根本不会被执行。
                # 漏了这一行，难度自适应三路采样在线上就是死代码——
                # 2026-08-15 独立验收（W3）实测正式入口只发 1 调、round_trace 为空，
                # 而内层类同输入发 2 调，就是这个缺陷。
                return self._ha_apply_fallback(
                    self._maybe_run_extra_paths(problem, metadata, first)
                )
        except _SolveDeadlineExceeded:
            return self._ha_apply_fallback(
                self._best_effort_result(
                    status="deadline_exceeded",
                    error_type="_SolveDeadlineExceeded",
                )
            )


__all__ = ["AgentConfig", "ReasoningAgent"]
