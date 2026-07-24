# Drive-Patch-Review — IsaacNew-main Folder

**Stand:** 2026-07-24  
**Quelle:** Google Drive `IsaacNew-main`  
(`https://drive.google.com/drive/folders/1qcq_pxi3G-osyxCNQVqOBypxKGaFv6s6`)  
**Lokaler Kernel-Bezug:** `main` nach Goal-Autonomie S0–S4 + Docs-Sync  
**Verdict:** **Nicht mergen / nicht 1:1 anwenden.**

---

## Was im Ordner liegt (457 Dateien)

| Schicht | Inhalt | Bewertung |
|---------|--------|-----------|
| **~16.07. Snapshot** | Alter Tree (Root-Python, `docs/`, `evals/`, `archive/`, großer `web/`-Monorepo) | Historisches Backup, **nicht** aktueller `main` |
| **21.07. Patch-Paket** | `Isaac_Complete_Patch_Paket_v1_*.zip` (R=1-Metriken, Lab-Bridge, Vector-Patch) | Veraltete Phasenannahme |
| **21.–24.07. Roadmaps** | `MASTER_UNIFIED_ROADMAP_*` v1–v4, `PHASE3_*` | Falsche Lückenliste, Scope-Drift |
| **24.07. Code-Patches** | `task_state_machine.py`, `trace_otel.py`, Lab/Baselines, Vector-Pipeline | Parallel-Welt / Mock-Theater |

**Gelesen:** alle nicht-`web/` Text-/Code-Dateien (125 unique Downloads + Zip-Inhalt, ~7k Zeilen); `web/` ist SaaS-Boilerplate und laut AGENTS out-of-scope.

---

## Abgleich mit kanonischem Stand (`AGENTS.md`)

| Patch-Behauptung | Realität im Repo |
|------------------|------------------|
| „Phase 1–2 done, jetzt Phase 3“ | Phase **1–4 + E2.0 + Goal-Autonomie S0–S4** sind **✅**; aktiv: **consolidate core behavior** |
| „Keine durable State-Machine“ | **Falsch** — `task_checkpoint.CheckpointState` + Executor-Checkpoints + `resume_task` |
| „Constitution-Hook neu in Executor“ | **Falsch** — `constitution.validate_action`, `constitution_gate_for_tool`, Kernel-Gates, Evals |
| Parallel VectorMemory-Pipeline | **Do NOT expand** (vector-memory redesign) |
| Isaac Lab + R=1 Baselines | Kein `simulation/`; Patches sind **Mock** (random/sleep), messen den Kernel nicht |
| Neues `trace_otel.py` mit eigener TracePhase | **Kaputt** gegenüber `decision_trace.py` (andere Phasen, Duplikat-Typen) |

Validierung zum Review-Zeitpunkt: `unittest` grün; `evals.eval_runner` **66/66**.

---

## Datei-für-Datei (neue Artefakte)

### Roadmaps / Guides → **nicht als Plan**

- `ROADMAP_ISAAC_PROJECT_v1`, `MASTER_UNIFIED_*` v2–v4  
- `PHASE3_PARALLEL_PATCHES`, `PHASE3_THREE_PARALLEL_STREAMS`, `PHASE3_INTEGRATION_GUIDE`  

Idee-Sammlung mit LLM-Implementierungsstil; **widerspricht** Phasenstand und Anti-Scope-Regeln.

### `task_state_machine.py` → **redundant / riskant**

Konzept (States, History, Resume-Liste) ok, aber **doppelt** zum bestehenden Checkpoint-Pfad.  
JSON-`checkpoints/` neben Memory/DB-Checkpoints = zwei Wahrheiten.  
**Nicht einbauen.** Härten nur über `task_checkpoint.py` / Executor.

### `trace_otel.py` → **Idee ok, Code so nicht**

Reimplementiert `DecisionTrace`/`TracePhase` (UPPERCASE, unvollständige Phasen).  
Salvage im Kernel: **`DecisionTrace.to_portable_export()`** auf den echten Typen (local-first, kein OTel-SDK, kein neues Modul).

### `isaac_lab_bridge_enhanced.py` + `run_baselines.py` + Zip-Lab-Bridge → **Theater**

Mock-Env, Mock-Kernel, inkonsistente Klassennamen/Imports.  
Außerhalb Scope. **Nicht anwenden.**

### `vector_memory_pipeline_integration.py` + Zip-Vector-Patch → **Scope-Bruch**

Zweiter Retrieval-Pfad neben `build_retrieval_context()`.  
AGENTS: kein Vector-Memory-Redesign. **Nicht anwenden.**

### `r1_metrics*.py` → **optional / später**

Metrik-Ideen ungebunden; erst sinnvoll wenn echte Kernel-Traces/Evals die Daten liefern — nicht über Lab-Mocks.

---

## Was *nicht* getan werden soll

1. Drive-Dateien nach `main` kopieren oder mergen  
2. Parallel-State-Machine oder Parallel-Trace-Typen einführen  
3. Isaac Lab / R=1-Sim als nächste Phase starten  
4. `web/`-Monorepo aus dem Snapshot reaktivieren  

---

## Kanonischer nächster Schritt (nach diesem Review)

1. **Consolidate core behavior** (AGENTS) — harden, nicht expandieren  
2. Drive-Patches nur als **Negativliste** behandeln (dieses Dokument)  
3. Einzige übernommene Idee aus den Patches: **portabler DecisionTrace-Export** über bestehende API  
4. Referenz-Roadmap (Verfassung / Self-Model / Checkpoint / MCP / Evals) nur bei **expliziter** Owner-Freigabe und immer gegen den echten Code  

**Priorität bei Widersprüchen:** `AGENTS.md` → Checklisten `06`/`05` → dieses Review → Drive-Roadmaps.

---

---

## Nachtrag: Uploads 2026-07-24 ~01:28 UTC

Zusätzliche Dateien (Drive-Suche; teils Root, nicht nur IsaacNew-main):

| Upload | Urteil für Kernel-main |
|--------|-------------------------|
| Elicit Phase-3+ Roadmap / OSS-Analyse / OTel-Mapping | **Nützlich als Input** — Gap-Matrix in Master-Roadmap v5; Phasenlabels veraltet |
| Master Roadmap Gehirnähnlich + Research Brief (SNN/WBE) | **Research-Track R** — nicht consolidate-next |
| `00_MASTER_PATCH_MANIFEST` (Lab/Vector) | **Abgelehnt** (wie oben) |
| `trace_otel_adapted` / `run_baselines_adapted` | **Überholt / Schein-Messung** — portable Export + Evals 96/96 ersetzen |
| Projekt-Übersicht eclizit „Phase 1–2“ | **Veraltet** |

**Kanonische Fortschritts- und Gap-Dokumentation:**  
`docs/MASTER_ROADMAP_ISAAC_v5_2026-07-24.md`

---

*Review: Zeilenweise Text/Code der relevanten Drive-Artefakte + Diff-Check gegen lokalen Kernel.*
