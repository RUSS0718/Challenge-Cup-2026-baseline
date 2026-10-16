# ADR-0003：PythonMathTool 与 Verifier 采用实验性可替换接口

**状态：accepted**  
**日期：2026-10-15**  
**范围：V0.1 Agent Workbench**

## 背景

数学任务需要计算工具和结果检查，但 V0.1 尚未确定最终 Verifier 理论，也没有生产级代码沙箱。Spike 已证明受限 Python 子进程可以完成 SymPy/mpmath 计算、超时处理和明显危险代码拦截。

## 决策

- 通过 Tool Registry 提供 `PythonMathTool`；
- V0.1 使用独立子进程、AST 检查、白名单模块、超时和输出捕获；
- 明确标记为实验性限制，不称为完整沙箱；
- Verifier 使用 `VerificationHook` 接口；
- V0.1 只做结构、工具结果和明显冲突检查；
- 后续可以替换为符号验证、数值反例、独立 Solver 或其他研究方案。

## 理由

该方案可以支持 V0.1 的真实演示，又不会在证据不足时冻结复杂数学验证路线或假装拥有生产级执行隔离。

## 后果

- 不可信任的任意代码不能进入该工具；
- 复杂 Verifier 不阻塞 V0.1；
- Python 工具和 Verifier 的结果必须带有实验状态和限制说明；
- 如果后续场景要求更强隔离，需要新增容器或远程沙箱设计。


