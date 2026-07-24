from __future__ import annotations

import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class TracePhase(Enum):
    GOVERNANCE = "governance"
    CLASSIFICATION = "classification"
    RETRIEVAL = "retrieval"
    STRATEGY = "strategy"
    MOTIVATION = "motivation"
    ELIGIBILITY = "eligibility"
    SELECTION = "selection"
    EXECUTION = "execution"
    CONTEXT_INTEGRATION = "context_integration"
    EVALUATION = "evaluation"
    LEARNING = "learning"
    FOLLOWUP = "followup"


@dataclass(frozen=True)
class TraceEntry:
    sequence: int
    ts: float
    phase: TracePhase
    event: str
    data: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "sequence": self.sequence,
            "ts": self.ts,
            "phase": self.phase.value,
            "event": self.event,
            "data": self.data,
        }


@dataclass
class DecisionTrace:
    entries: list[TraceEntry] = field(default_factory=list)

    def add(self, phase: TracePhase, event: str, data: dict[str, Any] | None = None) -> TraceEntry:
        payload = dict(data or {})
        entry = TraceEntry(
            sequence=len(self.entries) + 1,
            ts=time.time(),
            phase=phase,
            event=event,
            data=payload,
        )
        self.entries.append(entry)
        return entry

    def to_list(self) -> list[dict[str, Any]]:
        return [entry.to_dict() for entry in self.entries]

    def to_portable_export(self, request_id: str = "") -> dict[str, Any]:
        """
        Lokaler, OTel-ähnlicher Export der echten DecisionTrace-Einträge.

        Kein externes Backend, keine zweite TracePhase-Welt.
        Nutzt ausschließlich die kanonischen TracePhase-Werte.
        """
        rid = (request_id or "").strip() or "isaac-trace"
        if not self.entries:
            return {
                "schema": "isaac.decision_trace.portable_v1",
                "request_id": rid,
                "service": "isaac-cognitive-kernel",
                "resourceSpans": [],
                "entries": [],
            }

        root_start = self.entries[0].ts
        root_end = self.entries[-1].ts
        root_span_id = f"root-{rid[:12]}"
        spans: list[dict[str, Any]] = [
            {
                "traceId": rid,
                "spanId": root_span_id,
                "name": "isaac.request",
                "kind": "SERVER",
                "startTimeUnixNano": int(root_start * 1_000_000_000),
                "endTimeUnixNano": int(root_end * 1_000_000_000),
                "attributes": {
                    "isaac.request_id": rid,
                    "service.name": "isaac-cognitive-kernel",
                },
                "events": [],
            }
        ]

        phase_spans: dict[str, dict[str, Any]] = {}
        for entry in self.entries:
            phase_key = entry.phase.value
            if phase_key not in phase_spans:
                span = {
                    "traceId": rid,
                    "spanId": f"{phase_key}-{rid[:12]}",
                    "parentSpanId": root_span_id,
                    "name": _portable_span_name(entry.phase),
                    "kind": "INTERNAL",
                    "startTimeUnixNano": int(entry.ts * 1_000_000_000),
                    "endTimeUnixNano": int(entry.ts * 1_000_000_000),
                    "attributes": {"isaac.phase": phase_key},
                    "events": [],
                }
                phase_spans[phase_key] = span
                spans.append(span)
            phase_spans[phase_key]["events"].append(
                {
                    "timeUnixNano": int(entry.ts * 1_000_000_000),
                    "name": entry.event,
                    "attributes": dict(entry.data or {}),
                }
            )
            phase_spans[phase_key]["endTimeUnixNano"] = int(entry.ts * 1_000_000_000)

        return {
            "schema": "isaac.decision_trace.portable_v1",
            "request_id": rid,
            "service": "isaac-cognitive-kernel",
            "entries": self.to_list(),
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": {
                            "service.name": "isaac-cognitive-kernel",
                        }
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": "isaac.decision_trace"},
                            "spans": spans,
                        }
                    ],
                }
            ],
        }


def _portable_span_name(phase: TracePhase) -> str:
    """Semantische Span-Namen für lokalen Export (kein OTel-SDK)."""
    mapping = {
        TracePhase.GOVERNANCE: "isaac.guardrail",
        TracePhase.CLASSIFICATION: "isaac.classify",
        TracePhase.RETRIEVAL: "isaac.retrieval",
        TracePhase.STRATEGY: "isaac.strategy",
        TracePhase.MOTIVATION: "isaac.motivation",
        TracePhase.ELIGIBILITY: "isaac.eligibility",
        TracePhase.SELECTION: "isaac.selection",
        TracePhase.EXECUTION: "isaac.execution",
        TracePhase.CONTEXT_INTEGRATION: "isaac.context_integration",
        TracePhase.EVALUATION: "isaac.evaluation",
        TracePhase.LEARNING: "isaac.learning",
        TracePhase.FOLLOWUP: "isaac.followup",
    }
    return mapping.get(phase, f"isaac.{phase.value}")


def gate_trace_data(gate: dict[str, Any] | None) -> dict[str, Any]:
    """Serialisiert ein Verfassungs-Gate-Urteil für DecisionTrace/Audit."""
    payload = dict(gate or {})
    override = payload.get("override") or {}
    verdict = payload.get("verdict") or {}
    blocked_by = list(payload.get("blocked_by") or verdict.get("blocked_by") or [])
    return {
        "allowed": bool(payload.get("allowed")),
        "overridden": bool(override.get("overridden")),
        "blocked_by": blocked_by,
        "action": str(verdict.get("action") or payload.get("action") or ""),
    }


def audit_routing_trace(
    trace: DecisionTrace,
    *,
    intent: str = "",
    outcome: str = "",
) -> None:
    """Persistiert einen Routing-DecisionTrace im append-only Audit-Log."""
    from audit import AuditLog

    AuditLog._record(
        "decision_trace",
        {
            "scope": "routing",
            "intent": (intent or "")[:80],
            "outcome": (outcome or "")[:40],
            "entries": trace.to_list(),
        },
    )
