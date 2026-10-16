# Subjective Agent Workbench V0.1 Implementation Spec

**Status:** ready-for-agent  
**Source:** approved V0.1 PRD, accepted technical design, accepted ADRs, and completed Risk Spike  
**Execution profile:** `showcase_mvp`  
**Official profile:** unchanged

**Issue:** https://github.com/RUSS0718/MathAgent/issues/1

## Problem Statement

The repository currently has a stable official mathematical answer path and a small local Demo, but it does not yet provide a product-side Run model for the subjective evaluation story. The project needs a real, inspectable execution path that can organize a mathematical task, let an Agent use tools when needed, survive a failed step, and export evidence without changing the official scoring path.

The first release must establish the seams that later features can use. It must not claim a mathematical accuracy improvement from the existence of an Agent framework, a tool, or a verifier.

## Solution

Build a `showcase_mvp` product path with LangGraph as the Run control layer and DeepAgents as the role-level Agent layer. A Run Manager owns Run identity, stage transitions, budgets, events, checkpoints, and final results. A Tool Registry exposes approved tools to the Agent loop. The first tools are an Intern model adapter, a minimal multimodal adapter, and an experimental `PythonMathTool`. A lightweight, replaceable `VerificationHook` checks result structure and obvious tool-result conflicts. The system exports a JSON Evidence Pack containing the observable execution record.

The official profile remains independent. It keeps the current entry point, request budget, output contract, dependency boundary, and baseline files.

## User Stories

1. As a judge, I want to submit a text mathematics problem, so that I can see one complete live Showcase Run.
2. As a judge, I want to see the Run ID and current stage, so that I can follow the execution without guessing from a spinner.
3. As a judge, I want to see when the Agent chooses a tool, so that the system story is grounded in an observable action.
4. As a judge, I want to see a Python calculation result, so that I can distinguish model reasoning from executable checking.
5. As a judge, I want to see a tool failure and recovery, so that the checkpoint and resume design is visible.
6. As a judge, I want the Demo to label live, replay, experimental, and unavailable states, so that a recorded result is not presented as a live model call.
7. As an Agent engineer, I want one Run state model, so that Agent roles and tools can be replaced without rewriting the product API.
8. As an Agent engineer, I want a LangGraph-controlled execution loop, so that tool calls, interruption, resume, and budgets have one owner.
9. As an Agent engineer, I want DeepAgents behind an Agent Adapter, so that DeepAgents internals do not become the product persistence contract.
10. As an Agent engineer, I want an Intern model adapter, so that current text and multimodal capabilities can be used without changing Run orchestration.
11. As an Agent engineer, I want a Tool Registry, so that every tool has a name, capability declaration, permission decision, timeout, and result status.
12. As an Agent engineer, I want an Agent to request Python only when a task needs computation, so that the workflow is dynamic rather than a fixed tool chain.
13. As an Agent engineer, I want the Python tool to return structured success, timeout, rejection, and execution-error states, so that the Agent can choose whether to continue or request review.
14. As an Agent engineer, I want a Vision Adapter to represent text plus image input, so that multimodal tasks use the same Run contract.
15. As an Agent engineer, I want image assets to have content hashes and references, so that traces can point to an input without storing the full image in every event.
16. As an Agent engineer, I want a checkpoint after observable execution steps, so that a failed Run can resume from persisted product state.
17. As an Agent engineer, I want failed tool calls to be recorded as events, so that recovery does not overwrite the original failure.
18. As an Agent engineer, I want explicit runtime budgets, so that a dynamic Agent loop cannot run forever.
19. As an Agent engineer, I want budget exhaustion to produce a terminal or review state, so that the Run always has an explainable outcome.
20. As an Agent engineer, I want a lightweight verification hook, so that the product can detect structural and obvious consistency errors before adopting a research-grade verifier.
21. As an Agent engineer, I want verification results to be `pass`, `conflict`, or `unknown`, so that a missing proof is not presented as a successful proof.
22. As an Agent engineer, I want the final answer to refer to evidence identifiers, so that a reviewer can connect the result to tools and stages.
23. As an Agent engineer, I want a JSON Evidence Pack, so that a Run can be reviewed and replayed outside the live process.
24. As an Agent engineer, I want product dependencies to be loaded only by the Showcase path, so that official imports remain stable.
25. As an Agent engineer, I want an offline fake model and fake tools in tests, so that orchestration contracts can be tested without credentials or network access.
26. As an Agent engineer, I want the product to fail clearly when credentials are missing, so that a Demo does not wait indefinitely.
27. As an Agent engineer, I want a health check that does not call a model, so that the service can be diagnosed before credentials are configured.
28. As a maintainer, I want the baseline snapshot to remain unchanged, so that subjective features do not silently alter the official submission.
29. As a maintainer, I want the product API to validate Run inputs, so that malformed requests do not reach an Agent or tool.
30. As a maintainer, I want event and export redaction, so that credentials, full prompts, hidden answers, and personal data do not enter the Demo trace.
31. As a maintainer, I want the first vertical slice to use a deterministic fake Agent, so that the API and UI can be integrated before all live model features are complete.
32. As a maintainer, I want the first live slice to use the current Intern adapter, so that the product path is connected to the actual model after the contract is proven.
33. As a reviewer, I want each feature to state whether it is implemented, experimental, replay, or planned, so that the report does not overstate evidence.
34. As a reviewer, I want the product result and official result to be labeled separately, so that subjective Demo evidence is not confused with objective evaluation evidence.

## Implementation Decisions

### Runtime boundary

- The product path is enabled only by the `showcase_mvp` profile.
- The official path keeps the existing entry point, call budget, output contract, and dependency closure.
- Product modules must not be imported by the root official entry.

### Orchestration

- LangGraph owns Run state transitions, execution-loop control, interrupt, resume, checkpoint integration, and budget decisions.
- DeepAgents is used behind an `AgentAdapter` for Planner, Solver, and optional Researcher roles.
- LangGraph nodes depend on product-level adapter results rather than DeepAgents internal message or persistence types.
- The Agent loop can return a final answer, request a registered tool, request human review, or return a structured failure.
- Every observable loop step emits an event and updates the recoverable state.

### Run state and statuses

- A Run has a unique ID, profile, input reference, asset references, current status, plan, messages or summaries, tool results, verification result, evidence references, budget state, and error state.
- The supported status path is `RECEIVED`, `PLANNING`, `RUNNING`, `VERIFYING`, `SYNTHESIZING`, `COMPLETED`, `NEEDS_REVIEW`, `RESUMED`, and `FAILED`.
- `RUNNING` may contain multiple loop steps, but each step is bounded by time, step, tool, retry, and Python execution budgets.
- A resume creates new events and continues from a checkpoint. It does not rewrite the original Run history.

### Adapter contracts

- `ModelAdapter` accepts normalized messages, optional function tool schemas, and safe metadata; it returns text, tool requests, usage metadata, and structured errors.
- `AgentAdapter` accepts product Run state and returns a product Agent result; it must not write directly to the database.
- `ToolAdapter` declares a name and capabilities and returns status, duration, result summary, and error category.
- Adapter failures are normalized before they enter events or Evidence Packs.

### Tool Registry

- All Agent-requested tools pass through the registry.
- The registry checks profile permission, capability, input size, timeout, retry policy, and budget before invocation.
- Tool event records contain the tool name, status, duration, parameter summary, result summary, and error category.
- The registry does not store credentials or full sensitive request bodies.

### Intern model and multimodal input

- The Intern adapter supports the existing text request shape.
- The Vision Adapter represents text plus image content and associates each image with an asset reference and content hash.
- V0.1 supports the minimum verified Base64 PNG request path, then adds real-task input limits and timeout handling.
- The product must label multimodal support as implemented only after a real task path is connected; endpoint-level verification alone is not sufficient.

### PythonMathTool

- The tool runs in a separate Python process.
- V0.1 uses an AST check, a small import and call allowlist, SymPy/mpmath support, a process timeout, and captured stdout/stderr.
- The tool returns explicit success, timeout, rejected-input, and execution-error states.
- The implementation is experimental and is not described as a production sandbox.
- Container or remote isolation remains outside this spec.

### Verification

- V0.1 implements `VerificationHook` rather than a fixed mathematical proof system.
- The first hook checks output shape, tool status, obvious tool-result mismatch, and simple variable, unit, or numeric conflicts.
- The result is `pass`, `conflict`, or `unknown`.
- A verification result is evidence about a check; it is not a claim that the mathematical answer is proven.

### Persistence and Evidence Pack

- SQLite is the first product persistence target.
- Product records include Runs, events, checkpoints, tool calls, artifacts, and review requests.
- The memory checkpointer used by the Spike is not the product completion criterion.
- Evidence Packs include Run ID, profile, version, stage timeline, Agent and tool summaries, verification status, final answer, and failure or recovery decisions.
- Full prompts, credentials, hidden answers, full images, and personal data are excluded from ordinary events and exports.

### First integration seam

The highest seam is the Run application service: it accepts a validated Run request, drives the orchestrator through adapters, and returns a Run snapshot or event stream. Tests should exercise this seam with fake adapters first, then real Intern and Python adapters in integration tests. The UI consumes the same Run snapshot and event contracts.

### API behavior

- Create a Run from a validated text input and optional asset references.
- Read a Run snapshot by ID.
- Read or stream Run events.
- Resume a Run that is waiting for review or recoverable failure.
- Export a JSON Evidence Pack.
- Return a credential-free health response.
- Return bounded, actionable errors for invalid input, missing configuration, tool timeout, and adapter failure.

### Dependency and installation boundary

- Product-only dependencies are installed in the Showcase or local development environment.
- The official dependency file and baseline closure remain unchanged.
- A clean environment check must verify that the product entry can be installed and that the official entry does not import product dependencies.

## Testing Decisions

### Test quality

Tests should observe external behavior at the highest available seam. They should use fake model and tool adapters for deterministic orchestration checks, and use real adapters only in explicitly marked integration tests. Tests must not depend on hidden model reasoning or exact provider wording.

### Unit and contract coverage

- Run input validation and status transitions;
- adapter result and error normalization;
- Tool Registry permission, timeout, budget, and redaction behavior;
- PythonMathTool success, timeout, rejected imports, and execution errors;
- Evidence Pack serialization and sensitive-field exclusion;
- checkpoint save and resume behavior;
- official import boundary and baseline protection;
- health, Run creation, Run snapshot, resume, and export API contracts.

### Integration coverage

- DeepAgents through the Intern Adapter with one fake or real registered tool;
- LangGraph execution loop with a failed tool, interrupt, resume, and final result;
- SQLite persistence across a service restart;
- Vision Adapter with a small test image and explicit failure behavior;
- live Showcase Run with PythonMathTool and Lightweight VerificationHook.

### Regression coverage

The existing official entry contract, Demo health and solve contract, workspace check, and baseline snapshot remain regression gates. Product tests must run without changing official behavior.

### Acceptance cases

1. A valid text request creates a Run and returns a non-empty final result.
2. A malformed request is rejected before model or tool invocation.
3. An Agent requests Python and receives a structured calculation result.
4. A failed tool call enters review or failure with an event and checkpoint.
5. Resuming the Run records the new attempt and completes without replacing the original failure.
6. A text plus image request reaches the Vision Adapter or returns a clear unsupported state.
7. Evidence export is JSON serializable and excludes sensitive fields.
8. The official entry still passes its existing contract and baseline checks.

## Out of Scope

- Changing the official scoring path;
- claiming official accuracy improvement;
- a complete mathematical proof verifier;
- production-grade arbitrary-code sandboxing;
- long-term memory or a vector database;
- Debate, Reflection, RSI, or automatic strategy mutation;
- distributed execution or multi-machine scheduling;
- a plugin marketplace;
- a complete React/Vite Workbench before the Run API seam is stable;
- support for every multimodal input format;
- multi-Solver comparison as a V0.1 requirement.

## Further Notes

- The Risk Spike proved minimum connectivity, not product completion. Product adapters, persistence, event mapping, evidence export, and real-task demos remain implementation work.
- The first implementation slice should use a deterministic fake Agent and fake tools through the Run application service. The live Intern path follows the same contract.
- The first UI integration should begin once the Run snapshot and event contracts exist and one backend vertical slice works. It should use the same contracts as live execution.
- Feature labels must remain visible in Demo and reports: `implemented`, `experimental`, `replay`, `unavailable`, or `planned`.
- Any later change to the official profile requires a new boundary review and a new baseline check.
