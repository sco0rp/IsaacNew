# Isaac – Repository Instructions for Copilot

Isaac is not a generic chatbot project.
Isaac is a personal, local, trust-based, privacy-first, development-oriented AI core.

## Core principles

- Prefer local-first and privacy-preserving designs.
- Never assume raw user input should be sent externally without decomposition, abstraction, or minimization.
- Favor causal clarity over quick hacks.
- Favor meaningful coupling between modules over isolated feature growth.
- Treat trust, meaning, memory, values, and state as first-class architectural concerns.
- Isaac should evolve toward a coherent personal system, not a pile of disconnected utilities.

## What Isaac is not

- Not a generic SaaS chatbot
- Not a girlfriend bot
- Not a shallow assistant with fake emotional simulation
- Not a cloud-first prompt relay
- Not a feature pile without architectural consistency

## Current Status & Active Discipline

**Phase Status:** Phase 4 (CONNECT) complete. System is stable and architecture-aware.

**Active Focus:** Consolidate core behavior. Stabilize Isaac's kernel, memory, and execution paths. No feature expansion. No new architectural layers.

### Do NOT start or expand

- Human Layer, instincts, relationship systems, personality features
- Trust modeling or learning loops
- Inquiry/clarification architecture
- Vector-memory redesign (if exists)
- Dashboard or UI work (except blocking fixes)
- Cloud/deployment work
- MCP subagent expansion
- Broad speculative redesign

If any of these areas exist in the code, leave them untouched unless they directly block runtime stability.

## Build, Test, and Validation Commands

Before and after changes, **always** run these commands to verify stability:

```bash
# 1. Syntax validation
python3 -m py_compile isaac_core.py executor.py low_complexity.py memory.py relay.py logic.py watchdog.py task_checkpoint.py

# 2. Sanity check (greeting path and core flow)
cd /root/isaacnew && .venv/bin/python sanity_check.py

# 3. Regression tests (unit + integration) — ALWAYS use unittest, not pytest
cd /root/isaacnew && ISAAC_DISABLE_VECTOR_MEMORY=1 .venv/bin/python -m unittest \
  tests_phase_a_stabilization tests_state_io tests_provider_configuration

# 4. Interactive validation (optional)
cd /root/isaacnew && .venv/bin/python isaac_core.py
# Dashboard: http://localhost:8766 | WebSocket: ws://localhost:8765
```

**Critical:** Use `ISAAC_DISABLE_VECTOR_MEMORY=1` to avoid onnx/Chroma dependencies in CI and test environments.

**Runnable criterion:** No import/syntax errors; greeting path runs; at least one non-tool chat path succeeds.

## Critical Architectural Rules (DO NOT BREAK)

These rules must hold true after every change. If you violate any of these, you've broken core Isaac behavior:

1. **Classification must control routing.** The output of `classify_interaction_result()` determines which path executes. Later routing logic must use the same classification, not recalculate.

2. **Retrieval must happen before strategy selection.** Call `memory.build_retrieval_context()` *before* deciding what strategy/tools to allow.

3. **Executor must execute, not reinterpret decisions.** The executor receives a Strategy contract and a Task. It runs them as specified, does not re-classify or change tool permissions on its own.

4. **Memory must be typed and structured.** Memory should return structured objects, not raw prompt strings. Facts must have a `type` field for reliable filtering.

5. **Lightweight social inputs must short-circuit locally.** Greetings, thanks, acknowledgments must complete without calling LLM or tools.

6. **Normal chat must not opportunistically trigger tools.** Only explicit "Search:" or "Browser:" prefixes or declared Strategy should activate tools. Random chat about weather/news/etc. must not call search.

7. **Strategy must be explicit and inspectable.** Strategy is a concrete object (`allow_tools`, `allow_followup`, `allow_provider_switch`). No scattered boolean flags.

8. **No parallel retrieval paths.** There is one authority: `memory.build_retrieval_context()`. Do not create alternate context-building functions.

## Module Ownership & Concerns

| Module | Owns | Does NOT Own |
|--------|------|--------------|
| `isaac_core.py` | Orchestration, Classification → Retrieval → Strategy → Task, Context composition, Routing | Task queue loops, Executor logic, Quality evaluation, Re-classification |
| `executor.py` | Deterministic task execution, Task lifecycle, Strategy enforcement | Classification, Routing, Tool permission decisions, Architecture choices |
| `low_complexity.py` | Lightweight fast-path classification, Greeting/thanks/ack detection | LLM calls, Tool decisions, Complex reasoning |
| `memory.py` | Structured retrieval via `build_retrieval_context()`, Fact storage, Dialog history | Primary prompt composition, Routing decisions, Strategy selection |
| `relay.py` | Multi-provider LLM with fallback | Architecture decisions, Tool invocation |
| `tool_runtime.py` | Tool execution, Strategy compliance, Registry lookup | Tool selection logic, Permission decisions |
| `tool_policy.py` | Policy validation, Constitution gates | Tool runtime execution |
| `constitution.py` | Action validation, Governance rules | Enforcement (delegated to gates) |

**Key principle:** Each module has a clear boundary. Crossing into another module's concern requires an explicit interface call. No hidden dependencies or side effects.

## Validation Test Cases (A–G)

After changes, verify these representative cases still work correctly. These are **quick manual checks**, not automated tests:

| ID | Input | Expected Behavior |
|----|----|---|
| A | `Hallo Isaac` | Local greeting response, **no LLM call**, no tools |
| B | `Danke` | Local acknowledgment, **no LLM call**, no tools |
| C | `Was ist 2+2?` | Chat/reasoning response, **no tools triggered**, uses LLM |
| D | `Erkläre mir das Wetter als sprachliches Motiv in Literatur` | Full response, **no search/tool triggered** (weather is context, not hotword) |
| E | `Suche: Wetter Berlin` | Search executed if strategy allows, structured results |
| F | `Browser auf GitHub öffnen` | Browser tool only if explicitly allowed by strategy |
| G | `Und?` | Continuation/follow-up, **no tools triggered**, respects conversation history |

If any of these fail after your changes, stop and investigate before continuing.

## Coding guidance

- Before adding a feature, identify which of these it affects:
  - memory
  - trust / privilege
  - meaning / values
  - state / background behavior
  - privacy / decomposition
  - causal coupling between modules
- Prefer explicit, readable logic over hidden side effects.
- Document non-obvious coupling decisions.
- Avoid introducing functionality that breaks local control or privacy posture.
- Avoid “quick fixes” that contradict long-term architecture.

## Architectural direction

Isaac should move:
- from modular adjacency
- toward causally explainable internal coupling

Important dependency classes:
- technical dependencies
- causal dependencies
- decision dependencies
- state dependencies
- temporal dependencies
- memory dependencies
- values / meaning dependencies
- educational dependencies

## Interaction philosophy

- Relationship should emerge from memory, repeated interaction, trust, context, and shared history.
- Do not simulate emotional closeness just because it seems engaging.
- Prefer meaningful, rare, contextually justified interventions over noisy interaction.

## Device / future-facing mindset

Future Isaac-related work may involve:
- physical embodiment
- situational behavior design
- sensor / environment integration
- device-to-device interaction
- adaptive personality expression without mass-produced sameness

## Change policy

When suggesting edits:
1. explain the architectural reason
2. keep changes scoped
3. preserve future extensibility
4. do not flatten Isaac into a generic assistant architecture
