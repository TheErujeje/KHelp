"""Run the triage agent for one intake (or one re-check) and record the run.

The runner is application code, not the agent: it owns the run record, the
time and tool-call bounds, and the manual-triage fallback when the agent
does not finish with a valid action.
"""

from __future__ import annotations

import logging
import os
import sys
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from mcp import StdioServerParameters
from mcp.client.stdio import stdio_client
from sqlalchemy import select
from strands import Agent
from strands.models.bedrock import BedrockModel
from strands.models.model import Model
from strands.models.ollama import OllamaModel
from strands.models.openai import OpenAIModel
from strands.tools.executors import SequentialToolExecutor
from strands.tools.mcp import MCPClient

from khelp_db import AgentRun, AuditLog, Intake, Proposal, RecheckFlag, VitalsReading, session_factory
from khelp_scoring import tews_priority_rule

from .hooks import RunHooks
from .prompts import SYSTEM_PROMPT, intake_prompt, recheck_prompt

log = logging.getLogger(__name__)

FILESYSTEM_SERVER = "@modelcontextprotocol/server-filesystem@1.0.0"
REPO_ROOT = Path(__file__).resolve().parents[5]
MAX_NUDGES = 2
NUDGE = ("You have not finished. Make the next tool call now: propose_priority, or request_recheck if a "
         "previous error told you to. Do not reply with text until a tool has returned ok=true.")


def _env(name: str, default: str) -> Callable[[], str]:
    return lambda: os.environ.get(name, default)


HOSTED_PROVIDERS = ("groq", "bedrock")


def _flag(name: str, default: str) -> bool:
    value = os.environ.get(name, default).strip().lower()
    if value not in ("true", "false", "1", "0", "yes", "no"):
        raise ValueError(f"{name} must be true or false, not {value!r}")
    return value in ("true", "1", "yes")


def _provider() -> str:
    if _flag("KHELP_USE_LOCAL_MODEL", "true"):
        return "ollama"
    hosted = os.environ.get("KHELP_HOSTED_PROVIDER", "groq").strip().lower()
    if hosted not in HOSTED_PROVIDERS:
        raise ValueError(f"KHELP_HOSTED_PROVIDER must be one of {HOSTED_PROVIDERS}, not {hosted!r}")
    return hosted


def _model() -> str:
    return {
        "ollama": lambda: os.environ.get("OLLAMA_MODEL", "qwen2.5:7b-instruct"),
        "groq": lambda: os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b"),
        "bedrock": lambda: os.environ.get("BEDROCK_MODEL_ID", "openai.gpt-oss-120b-1:0"),
    }[_provider()]()


@dataclass
class Settings:
    """Which model runs is decided by settings alone:

    - KHELP_USE_LOCAL_MODEL=true  -> self-hosted Ollama at OLLAMA_BASE_URL, model OLLAMA_MODEL
    - KHELP_USE_LOCAL_MODEL=false -> KHELP_HOSTED_PROVIDER:
        groq     GROQ_API_KEY, GROQ_MODEL
        bedrock  BEDROCK_MODEL_ID, BEDROCK_REGION (credentials from the instance role)

    Read at construction time (once per run), after .env has been loaded.
    """

    provider: str = field(default_factory=_provider)
    model: str = field(default_factory=_model)
    ollama_url: str = field(default_factory=_env("OLLAMA_BASE_URL", "http://localhost:11434"))
    groq_url: str = field(default_factory=_env("GROQ_BASE_URL", "https://api.groq.com/openai/v1"))
    bedrock_region: str = field(default_factory=_env("BEDROCK_REGION", "eu-west-1"))
    max_tool_calls: int = field(default_factory=lambda: int(os.environ.get("KHELP_MAX_TOOL_CALLS", "12")))
    timeout_s: int = field(default_factory=lambda: int(os.environ.get("KHELP_RUN_TIMEOUT_SECONDS", "180")))
    intake_dir: Path = field(default_factory=lambda: Path(
        os.environ.get("KHELP_INTAKE_DIR", REPO_ROOT / "data" / "intake")).resolve())

    @property
    def model_label(self) -> str:
        return f"{self.provider}:{self.model}"


def _groq_params(model: str) -> dict[str, Any]:
    params: dict[str, Any] = {"temperature": 0.0}
    effort = os.environ.get("KHELP_REASONING_EFFORT", "low")
    if model.startswith("openai/gpt-oss") and effort:
        params["reasoning_effort"] = effort  # scoring is rule-checked server-side; long reasoning only adds latency
    return params


def build_model(settings: Settings) -> Model:
    """Self-hosted Ollama, or a hosted model (Groq / Bedrock) for synthetic-data use."""
    if settings.provider == "ollama":
        return OllamaModel(host=settings.ollama_url, model_id=settings.model, temperature=0.0,
                           keep_alive="10m", options={"num_ctx": 8192})
    if settings.provider == "groq":
        api_key = os.environ.get("GROQ_API_KEY")
        if not api_key:
            raise RuntimeError("KHELP_HOSTED_PROVIDER=groq needs GROQ_API_KEY")
        return OpenAIModel(client_args={"api_key": api_key, "base_url": settings.groq_url},
                           model_id=settings.model, params=_groq_params(settings.model))
    if settings.provider == "bedrock":
        # Credentials come from the default AWS chain (the instance role on EC2).
        return BedrockModel(model_id=settings.model, region_name=settings.bedrock_region, temperature=0.0)
    raise ValueError(f"Unknown model provider {settings.provider!r}")


# Subprocesses get only what they need: never the model API key.
_BASE_ENV = ("PATH", "HOME", "LANG", "TMPDIR", "SYSTEMROOT")


def _subprocess_env(**extra: str) -> dict[str, str]:
    env = {k: os.environ[k] for k in _BASE_ENV if k in os.environ}
    env.update(extra)
    return env


def write_note_file(settings: Settings, patient_id: int, intake_id: int, text: str) -> Path:
    settings.intake_dir.mkdir(parents=True, exist_ok=True)
    path = settings.intake_dir / f"patient-{patient_id}-intake-{intake_id}.txt"
    path.write_text(text, encoding="utf-8")
    return path


def _triage_tools_client(run_id: str, settings: Settings) -> MCPClient:
    passthrough = {k: os.environ[k] for k in ("MCP_DATABASE_URL", "DATABASE_URL", "KHELP_SATS_DIR")
                   if k in os.environ}
    env = _subprocess_env(KHELP_RUN_ID=run_id, KHELP_MODEL_LABEL=settings.model_label, **passthrough)
    params = StdioServerParameters(command=sys.executable, args=["-m", "khelp_triage_tools.server"], env=env)
    return MCPClient(lambda: stdio_client(params))


def _filesystem_client(settings: Settings) -> MCPClient:
    # Borrowed server, limited to reading files in the intake directory.
    # In the Docker image the server is preinstalled (KHELP_FILESYSTEM_SERVER_BIN); locally npx fetches it.
    binary = os.environ.get("KHELP_FILESYSTEM_SERVER_BIN")
    command, args = (binary, []) if binary else ("npx", ["-y", FILESYSTEM_SERVER])
    params = StdioServerParameters(command=command, args=[*args, str(settings.intake_dir)], env=_subprocess_env())
    return MCPClient(lambda: stdio_client(params), tool_filters={"allowed": ["read_text_file"]})


def _previous_tews(patient_id: int) -> dict[str, Any] | None:
    with session_factory()() as s:
        reading = s.scalars(select(VitalsReading).where(VitalsReading.patient_id == patient_id)
                            .order_by(VitalsReading.id.desc()).limit(1)).first()
    if reading is None:
        return None
    t = reading.tews
    return {"total_min": t["total_min"], "total_max": t["total_max"],
            "priority_low": tews_priority_rule(t["total_min"])["priority"],
            "priority_high": tews_priority_rule(t["total_max"])["priority"]}


def _audit(s, run_id: str, patient_id: int, event_type: str, outputs: dict[str, Any], model: str,
           is_error: bool = False) -> None:
    s.add(AuditLog(run_id=run_id, patient_id=patient_id, event_type=event_type, source="runner",
                   outputs=outputs, model=model, is_error=is_error))


def _has_action(run_id: str) -> bool:
    with session_factory()() as s:
        return bool(s.scalars(select(Proposal.id).where(Proposal.run_id == run_id)).first()
                    or s.scalars(select(RecheckFlag.id).where(RecheckFlag.run_id == run_id)).first())


def _audit_nudge(run_id: str, patient_id: int, model: str, last_message: str) -> None:
    with session_factory()() as s, s.begin():
        _audit(s, run_id, patient_id, "NUDGE", {"last_message": last_message[:1000], "nudge": NUDGE}, model)


def run_agent(patient_id: int, intake_id: int, kind: str = "INITIAL", settings: Settings | None = None,
              on_event: Callable[[dict[str, Any]], None] | None = None, run_id: str | None = None) -> str:
    settings = settings or Settings()
    run_id = run_id or str(uuid.uuid4())
    Session = session_factory()

    with Session() as s, s.begin():
        intake = s.get(Intake, intake_id)
        s.add(AgentRun(id=run_id, patient_id=patient_id, intake_id=intake_id, kind=kind,
                       model=settings.model_label))
        s.flush()
        _audit(s, run_id, patient_id, "RUN_START", {"kind": kind, "intake_id": intake_id},
               settings.model_label)
        note_path = Path(intake.note_path) if intake.note_path else write_note_file(
            settings, patient_id, intake_id, intake.note_text)
        intake.note_path = str(note_path)

    prompt = (intake_prompt(patient_id, str(note_path)) if kind == "INITIAL"
              else recheck_prompt(patient_id, str(note_path), _previous_tews(patient_id)))

    hooks = RunHooks(run_id, patient_id, settings.model_label, settings.max_tool_calls, on_event)
    started = time.perf_counter()
    status, error, final_message, usage = "COMPLETED", None, None, {}

    try:
        with _triage_tools_client(run_id, settings) as triage, _filesystem_client(settings) as fs:
            tools = triage.list_tools_sync() + fs.list_tools_sync()
            agent = Agent(model=build_model(settings), tools=tools, system_prompt=SYSTEM_PROMPT, hooks=[hooks],
                          callback_handler=None, tool_executor=SequentialToolExecutor())
            timed_out = threading.Event()

            def on_timeout() -> None:
                timed_out.set()
                agent.cancel()

            timer = threading.Timer(settings.timeout_s, on_timeout)
            timer.start()
            try:
                result = agent(prompt)
                # Small models sometimes announce the next step and stop. Nudge
                # them, a bounded number of times, to actually make the call.
                for _ in range(MAX_NUDGES):
                    if (kind != "INITIAL" or timed_out.is_set() or hooks.limit_hit
                            or result.stop_reason == "cancelled" or _has_action(run_id)):
                        break
                    _audit_nudge(run_id, patient_id, settings.model_label, str(result))
                    result = agent(NUDGE)
            finally:
                timer.cancel()
            final_message = str(result).strip()[:2000]
            usage = dict(result.metrics.accumulated_usage)
            if timed_out.is_set():
                status = "TIMEOUT"
            elif hooks.limit_hit:
                status = "LIMIT_EXCEEDED"
    except Exception as exc:  # model down, MCP server failed to start, ...
        log.exception("agent run %s failed", run_id)
        status, error = "FAILED", f"{type(exc).__name__}: {exc}"

    latency_ms = int((time.perf_counter() - started) * 1000)
    _finish(run_id, patient_id, kind, status, error, final_message, usage, latency_ms, hooks.tool_calls,
            settings.model_label)
    return run_id


def _finish(run_id: str, patient_id: int, kind: str, status: str, error: str | None, final_message: str | None,
            usage: dict[str, Any], latency_ms: int, tool_calls: int, model: str) -> None:
    with session_factory()() as s, s.begin():
        proposals = s.scalars(select(Proposal).where(Proposal.run_id == run_id)).all()
        flags = s.scalars(select(RecheckFlag).where(RecheckFlag.run_id == run_id)).all()

        # Safety net: an initial intake must end in a proposal or a flag. If the
        # agent stopped early, failed, or ran out of time, a human takes over.
        fallback_flag = None
        if kind == "INITIAL" and not proposals and not flags:
            fallback_flag = RecheckFlag(
                patient_id=patient_id, run_id=run_id, flag_type="MANUAL_TRIAGE",
                reason=f"Agent run ended without a valid proposal or flag ({status}). Triage manually.",
                details={"status": status, "error": error}, status="PENDING")
            s.add(fallback_flag)

        run = s.get(AgentRun, run_id)
        run.status = status
        run.error = error
        run.final_message = final_message
        run.finished_at = datetime.now(timezone.utc)
        run.latency_ms = latency_ms
        run.tool_calls = tool_calls
        run.input_tokens = usage.get("inputTokens")
        run.output_tokens = usage.get("outputTokens")
        s.flush()
        _audit(s, run_id, patient_id, "RUN_END", {
            "status": status, "error": error, "final_message": final_message, "tool_calls": tool_calls,
            "latency_ms": latency_ms, "usage": usage,
            "proposal_ids": [p.id for p in proposals], "recheck_flag_ids": [f.id for f in flags],
            "fallback_flag_id": fallback_flag.id if fallback_flag else None,
        }, model, is_error=status != "COMPLETED")
