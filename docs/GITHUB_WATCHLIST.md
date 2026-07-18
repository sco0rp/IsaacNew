# GitHub Watchlist für Isaac (bounded)

Kuratierte Auswahl aus OpenLM/GitHub-Scan (2026). Isaac importiert **keine**
Agent-Frameworks wholesale — nur Muster in bestehende Module.

Siehe auch: `docs/OPEN_SOURCE_PATTERNS.md`, `docs/LOCAL_LLM.md`, `docs/OPEN_INTERPRETER.md`.

## Tier A — Nutzen (Infra / schon da / härten)

| Projekt | Rolle | Isaac-Status |
|---------|-------|--------------|
| [vLLM](https://github.com/vllm-project/vllm) | Lokales GPU-Serving | Ops: `ACTIVE_PROVIDER=local` |
| [SGLang](https://github.com/sgl-project/sglang) | Alternative zu vLLM | Ops: ein Backend reicht |
| [Mem0](https://github.com/mem0ai/mem0) | Memory-Layer | Adapter vorhanden (default OFF) |
| [Cognee](https://github.com/topoteretes/cognee) | Graph-Memory | Adapter vorhanden |
| [Letta](https://github.com/letta-ai/letta) | Companion + Memory-Ideen | `letta:` Companion |
| [Graphiti](https://github.com/getzep/graphiti) | Temporal facts | **Muster only** (Phase 3 Plan) |
| [Hermes Agent](https://github.com/NousResearch/hermes-agent) | Tool-Schema / computer-use | `hermes_compat` + eigene Module |
| [browser-use](https://github.com/browser-use/browser-use) | Browser-Robustheit | Muster für `browser.py` bei Bugs |
| [Agent_Memory_Techniques](https://github.com/NirDiamant/Agent_Memory_Techniques) | Lern-Notebooks | lesen, nicht installieren |

## Tier B — Goal-Autonomie (Muster → Phase 1 Plan)

| Projekt | Übernommenes Muster |
|---------|---------------------|
| [goal-driven](https://github.com/lidangzzz/goal-driven) | Stop-Kriterien, Subgoal-Gates, Verification |
| [autogoals](https://github.com/ozankasikci/autogoals) | Goal-as-contract, kein freier Loop |

Umsetzung: `goal_store` / `motivation` / `goal_inquiry` — kein Import der Repos.

## Tier C — Companion only (expliziter Prefix)

| Projekt | Isaac |
|---------|--------|
| Open Interpreter (Codex harness) | `oi:` / `interpreter:` |
| Cline / OpenCode / Goose | **nicht** einbauen (redundant zu OI) |

## Tier D — Beobachten, nicht installieren

| Projekt | Warum nur lesen |
|---------|-----------------|
| [OpenClaw](https://github.com/openclaw/openclaw) | Zweiter Kernel; Patterns: Session-Flush, Channel-Gates |
| NEOTH / Aivyx | Consent-tools / audit Ideen |

## Tier E — Anti-Liste

CrewAI, AutoGPT, LangGraph wholesale, Ray, DeepSpeed, Megatron, verl,
Mem0/Zep Cloud als Default, Companion-Theater, MCP-Subagent-Expansion.

## Aktive Arbeit

Goal-Härtung (Stop / Verify / Anti-Spam) — Checklist `06_goal_autonomy_checklist.txt`.
