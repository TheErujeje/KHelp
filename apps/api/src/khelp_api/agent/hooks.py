"""Strands hooks: audit every tool call, and bound the number of calls per run."""

from __future__ import annotations

import json
import logging
from typing import Any, Callable

from strands.hooks import AfterToolCallEvent, BeforeToolCallEvent, HookProvider, HookRegistry

from khelp_db import AuditLog, session_factory

log = logging.getLogger(__name__)


def _result_payload(result: Any) -> dict[str, Any]:
    """Tool results arrive as {"status", "content": [{"json"|"text": ...}]}; keep the useful part."""
    if not isinstance(result, dict):
        return {"raw": str(result)}
    payload: dict[str, Any] = {"status": result.get("status")}
    for block in result.get("content", []):
        if "json" in block:
            payload["json"] = block["json"]
        elif "text" in block:
            text = block["text"]
            try:
                payload["json"] = json.loads(text)
            except (TypeError, ValueError):
                payload["text"] = text[:4000]
    return payload


def _is_error(payload: dict[str, Any]) -> bool:
    if payload.get("status") == "error":
        return True
    body = payload.get("json")
    return isinstance(body, dict) and body.get("ok") is False


class RunHooks(HookProvider):
    """One instance per agent run."""

    def __init__(self, run_id: str, patient_id: int, model: str, max_tool_calls: int,
                 on_event: Callable[[dict[str, Any]], None] | None = None) -> None:
        self.run_id = run_id
        self.patient_id = patient_id
        self.model = model
        self.max_tool_calls = max_tool_calls
        self.tool_calls = 0
        self.limit_hit = False
        self.on_event = on_event
        self._session = session_factory()

    def register_hooks(self, registry: HookRegistry, **_: Any) -> None:
        registry.add_callback(BeforeToolCallEvent, self.before_tool)
        registry.add_callback(AfterToolCallEvent, self.after_tool)

    def before_tool(self, event: BeforeToolCallEvent) -> None:
        self.tool_calls += 1
        if self.tool_calls > self.max_tool_calls:
            self.limit_hit = True
            event.cancel_tool = (f"Tool call limit ({self.max_tool_calls}) reached. Stop now; "
                                 "the patient will be flagged for manual triage.")
            event.agent.cancel()

    def after_tool(self, event: AfterToolCallEvent) -> None:
        tool_use = event.tool_use
        payload = _result_payload(event.result)
        if event.exception is not None:
            payload["exception"] = repr(event.exception)
        is_error = _is_error(payload) or event.exception is not None
        latency_ms = int(event.duration * 1000) if event.duration is not None else None
        row = AuditLog(
            run_id=self.run_id, patient_id=self.patient_id, event_type="TOOL_CALL", source="agent",
            tool_name=tool_use.get("name"), inputs=tool_use.get("input") or {}, outputs=payload,
            is_error=is_error, model=self.model, latency_ms=latency_ms,
        )
        with self._session() as s, s.begin():
            s.add(row)
        if self.on_event:
            self.on_event({"tool": row.tool_name, "inputs": row.inputs, "outputs": payload,
                           "is_error": is_error, "latency_ms": latency_ms, "n": self.tool_calls})
