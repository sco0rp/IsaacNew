from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Any


# Sensitive key fragments — values redacted in portable export (not dropped).
_REDACT_KEY_FRAGMENTS = (
    "api_key",
    "apikey",
    "authorization",
    "password",
    "secret",
    "token",
    "credential",
    "cookie",
    "private_key",
)


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
        Redaction sensibler Keys; gen_ai.*-Aliase aus EXECUTION-Daten.
        """
        rid = (request_id or "").strip() or "isaac-trace"
        if not self.entries:
            return {
                "schema": "isaac.decision_trace.portable_v1_1",
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
        redacted_entries: list[dict[str, Any]] = []
        for entry in self.entries:
            phase_key = entry.phase.value
            safe_data = redact_trace_data(dict(entry.data or {}))
            enriched = enrich_gen_ai_attributes(safe_data)
            redacted_entries.append(
                {
                    "sequence": entry.sequence,
                    "ts": entry.ts,
                    "phase": phase_key,
                    "event": entry.event,
                    "data": enriched,
                }
            )
            if phase_key not in phase_spans:
                span_attrs: dict[str, Any] = {"isaac.phase": phase_key}
                # Lift gen_ai / model keys onto the phase span when present.
                for key in (
                    "gen_ai.system",
                    "gen_ai.request.model",
                    "gen_ai.response.model",
                    "provider",
                    "model",
                    "latency_ms",
                ):
                    if key in enriched and enriched[key] not in (None, ""):
                        span_attrs[key] = enriched[key]
                span = {
                    "traceId": rid,
                    "spanId": f"{phase_key}-{rid[:12]}",
                    "parentSpanId": root_span_id,
                    "name": _portable_span_name(entry.phase),
                    "kind": "INTERNAL",
                    "startTimeUnixNano": int(entry.ts * 1_000_000_000),
                    "endTimeUnixNano": int(entry.ts * 1_000_000_000),
                    "attributes": span_attrs,
                    "events": [],
                }
                phase_spans[phase_key] = span
                spans.append(span)
            else:
                # Update span-level attrs if later events carry model metadata.
                for key in (
                    "gen_ai.system",
                    "gen_ai.request.model",
                    "gen_ai.response.model",
                    "provider",
                    "model",
                    "latency_ms",
                ):
                    if key in enriched and enriched[key] not in (None, ""):
                        phase_spans[phase_key]["attributes"][key] = enriched[key]
            phase_spans[phase_key]["events"].append(
                {
                    "timeUnixNano": int(entry.ts * 1_000_000_000),
                    "name": entry.event,
                    "attributes": enriched,
                }
            )
            phase_spans[phase_key]["endTimeUnixNano"] = int(entry.ts * 1_000_000_000)

        return {
            "schema": "isaac.decision_trace.portable_v1_1",
            "request_id": rid,
            "service": "isaac-cognitive-kernel",
            "entries": redacted_entries,
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


def redact_trace_data(data: dict[str, Any], *, max_str: int = 400) -> dict[str, Any]:
    """Redact sensitive keys and truncate long strings for portable export."""
    out: dict[str, Any] = {}
    for key, value in (data or {}).items():
        k = str(key)
        kl = k.lower()
        if any(frag in kl for frag in _REDACT_KEY_FRAGMENTS):
            out[k] = "[REDACTED]"
            continue
        if isinstance(value, dict):
            out[k] = redact_trace_data(value, max_str=max_str)
        elif isinstance(value, list):
            out[k] = [
                redact_trace_data(v, max_str=max_str) if isinstance(v, dict) else _truncate_scalar(v, max_str)
                for v in value[:40]
            ]
        else:
            out[k] = _truncate_scalar(value, max_str)
    return out


def _truncate_scalar(value: Any, max_str: int) -> Any:
    if isinstance(value, str) and len(value) > max_str:
        return value[:max_str] + "…"
    return value


def enrich_gen_ai_attributes(data: dict[str, Any]) -> dict[str, Any]:
    """
    Add OTel-GenAI-style aliases from Isaac EXECUTION fields without dropping originals.

    Mapping (local-first, no SDK):
      provider / provider_id  → gen_ai.system
      model                   → gen_ai.request.model (+ response.model if absent)
      latency_ms / model_call_ms → kept; also gen_ai.request latency not standardized as ms field
    """
    out = dict(data or {})
    provider = str(out.get("provider") or out.get("provider_id") or out.get("gen_ai.system") or "").strip()
    model = str(out.get("model") or out.get("gen_ai.request.model") or "").strip()
    if provider and "gen_ai.system" not in out:
        out["gen_ai.system"] = provider
    if model:
        out.setdefault("gen_ai.request.model", model)
        out.setdefault("gen_ai.response.model", model)
    if "latency_ms" not in out and "model_call_ms" in out:
        try:
            out["latency_ms"] = float(out["model_call_ms"])
        except (TypeError, ValueError):
            pass
    # Approximate usage only if callers already estimated tokens
    for src, dst in (
        ("input_tokens", "gen_ai.usage.input_tokens"),
        ("output_tokens", "gen_ai.usage.output_tokens"),
        ("prompt_tokens", "gen_ai.usage.input_tokens"),
        ("completion_tokens", "gen_ai.usage.output_tokens"),
    ):
        if src in out and dst not in out:
            out[dst] = out[src]
    return out


def build_execution_llm_trace_data(
    *,
    provider: str = "",
    model: str = "",
    latency_ms: float | None = None,
    iteration: int = 0,
    prompt_chars: int = 0,
    response_chars: int = 0,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    ok: bool = True,
    error: str = "",
    extra: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Canonical payload for TracePhase.EXECUTION model-call events."""
    data: dict[str, Any] = {
        "provider": (provider or "")[:80],
        "model": (model or "")[:120],
        "iteration": int(iteration),
        "prompt_chars": int(max(0, prompt_chars)),
        "response_chars": int(max(0, response_chars)),
        "ok": bool(ok),
    }
    if latency_ms is not None:
        data["latency_ms"] = round(float(latency_ms), 2)
        data["model_call_ms"] = data["latency_ms"]
    if input_tokens is not None:
        data["input_tokens"] = int(input_tokens)
    if output_tokens is not None:
        data["output_tokens"] = int(output_tokens)
    if error:
        data["error"] = str(error)[:200]
    if extra:
        data.update(extra)
    return enrich_gen_ai_attributes(data)


def export_portable_trace(
    trace: DecisionTrace,
    request_id: str = "",
    output_path: str | Path = "",
) -> Path:
    """Write portable export JSON to disk (local-first, redacted)."""
    path = Path(output_path or f"traces/{(request_id or 'isaac-trace').strip() or 'isaac-trace'}.portable.json")
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = trace.to_portable_export(request_id=request_id)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return path


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
        TracePhase.EXECUTION: "gen_ai.chat",
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
