# Open-Source-Muster für Isaac (bounded)

Isaac importiert **keine** Agent-Frameworks wholesale. Stattdessen werden erprobte
Ideen als *kleine, lokale Muster* auf bestehende Module abgebildet.

## Was wir bewusst nicht übernehmen

| Projekt | Warum nicht wholesale |
|---------|------------------------|
| LangGraph / CrewAI / OpenHands | Fremder Orchestrator würde Kernel-Pipeline ersetzen |
| Mem0 SaaS / Zep Cloud | Cloud-first, widerspricht local-first Datenschutz |
| SemaClaw Multi-Agent | MCP/Subagent-Expansion ist Out-of-Scope |
| Next.js SaaS-Boilerplates (`web/`) | Nicht Kernel-Kern; unangetastet |

## Übernommene Muster (Isaac-Mapping)

### 1. Think ≠ Act (OpenParallax)

- **Muster:** Planungsprozess darf Execution nicht neu interpretieren.
- **Isaac:** Classification + Strategy im Kernel; Executor führt nur Task-/Strategy-Vertrag aus.
- **Absicherung:** Regression `test_e2_executor_does_not_reclassify_input`.

### 2. Observability-Phasen (Langfuse-ähnlich)

- **Muster:** Explizite Spans/Phasen für Routing und Bewertung.
- **Isaac:** `DecisionTrace` / `TracePhase` inkl. `evaluation` und `learning`.
- **Kein** externes Tracing-Backend.

### 3. Typed / Local Memory (Letta Blocks, Mem0 OpenMemory)

- **Muster:** Strukturierte Memory-Einheiten, local-first Retrieval.
- **Isaac:** Memory Blocks + `build_retrieval_context` + Procedure Memory.
- **Bounded Selection:** Reliability + Keyword-Overlap → Tool-Hints (`tool_runtime`).

### 4. Tool/Skill Schema (Hermes-Agent-Kompatibilität)

- **Muster:** Einheitliche Tool-Metadaten und Permission-Felder.
- **Isaac:** `hermes_compat.py` (bereits im Main).

### 5. Confirmation / Safety Gates (PermissionBridge-Idee)

- **Muster:** Explizite Freigabe vor riskanten Aktionen.
- **Isaac:** `constitution.validate_action`, `constitution_override`, `privilege`, `sudo_gate`.

### 6. Think/Act Separation an Execution-Grenzen (OpenParallax-vertieft)

- **Muster:** Execution-Pfade dürfen Policy nicht umgehen.
- **Isaac (E2.0):**
  - Shell: `computer_use._constitution_gate_shell` + destruktive Marker → `protect_user`
  - Tools: `tool_runtime.constitution_gate_for_tool` mappt Shell-Tools auf `system_command`
  - Packages: `updater.apply_package` / `rollback_last_backup` → `modify_config` braucht Owner
  - Credentials: `credential_access` + Browser-Auto-Login → Owner-only Constitution
  - Privilege: kritische `authorize()`-Aktionen laufen durch dasselbe Verfassungs-Gate
  - Konsolidierung: `critical_action_gate()` + `CONSTITUTION_BOUNDARIES` Inventar

## Auswahlregel für künftige Übernahmen

1. Passt es zur Pipeline `classify → retrieve → strategy → task → execute → evaluate → memory`?
2. Bleibt Ownership der Module (ROT/BLAU/GRÜN) klar?
3. Ist die Änderung klein, testbar und ohne neuen Framework-Layer?
4. Verletzt sie Do-NOT-expand (Human Layer, Dashboard-Redesign, Cloud, MCP-Subagents)?

Wenn nein → nur in `05_evolution2_checklist.txt` notieren, nicht implementieren.
