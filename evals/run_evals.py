"""Run the Klaudesk evaluation set against the real agent and write EVALS.md.

    uv run python evals/run_evals.py run --provider bedrock --model openai.gpt-oss-120b-1:0 --runs 3 \
        --label bedrock-gpt-oss-120b --price-in 0.15 --price-out 0.60
    uv run python evals/run_evals.py report        # rebuild EVALS.md from evals/results/*.json

Each case runs the full system: both MCP servers, the server-side checks and the database (uses
DATABASE_URL / MCP_DATABASE_URL from .env). Every run is a real agent run; nothing is simulated.
Expected results come from evals/cases.yaml and are never adjusted to the model's output.
"""

from __future__ import annotations

import argparse
import json
import os
import statistics
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path

import yaml
from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parents[1]
CASES = ROOT / "evals" / "cases.yaml"
RESULTS = ROOT / "evals" / "results"
NOTES = ROOT / "evals" / "notes.md"
REPORT = ROOT / "EVALS.md"


def configure_model(provider: str, model: str) -> None:
    os.environ["KHELP_USE_LOCAL_MODEL"] = "true" if provider == "ollama" else "false"
    if provider == "ollama":
        os.environ["OLLAMA_MODEL"] = model
    else:
        os.environ["KHELP_HOSTED_PROVIDER"] = provider
        os.environ["GROQ_MODEL" if provider == "groq" else "BEDROCK_MODEL_ID"] = model


def run_case(case: dict, n: int) -> dict:
    # Imported here so the model settings above are in place first.
    from sqlalchemy import select

    from khelp_api.agent.runner import run_agent
    from khelp_db import AgentRun, AuditLog, Intake, Patient, Proposal, RecheckFlag, session_factory

    Session = session_factory()

    def new_intake(patient_id: int | None, text: str, kind: str) -> tuple[int, int]:
        with Session() as s, s.begin():
            if patient_id is None:
                p = Patient(display_name=f"EVAL {case['id']} #{n}", is_synthetic=True)
                s.add(p)
                s.flush()
                patient_id = p.id
            i = Intake(patient_id=patient_id, kind=kind, note_text=text)
            s.add(i)
            s.flush()
            return patient_id, i.id

    def collect(run_id: str) -> dict:
        with Session() as s:
            r = s.get(AgentRun, run_id)
            props = s.scalars(select(Proposal).where(Proposal.run_id == run_id)).all()
            flags = s.scalars(select(RecheckFlag).where(RecheckFlag.run_id == run_id)).all()
            rejected = s.scalars(select(AuditLog).where(
                AuditLog.run_id == run_id, AuditLog.source == "triage-tools",
                AuditLog.tool_name == "propose_priority", AuditLog.is_error.is_(True))).all()
            errors = [e["code"] for row in rejected for e in (row.outputs or {}).get("errors", [])]
            nudges = s.scalars(select(AuditLog.id).where(AuditLog.run_id == run_id,
                                                         AuditLog.event_type == "NUDGE")).all()
            return {
                "run_id": run_id, "status": r.status, "latency_ms": r.latency_ms, "tool_calls": r.tool_calls,
                "input_tokens": r.input_tokens or 0, "output_tokens": r.output_tokens or 0,
                "priorities": [p.priority for p in props],
                "outcomes": [p.decision.get("outcome") for p in props],
                "signs": sorted({c["discriminator_id"] for p in props for c in p.citations
                                 if c["type"] == "discriminator"}),
                "flags": sorted(f.flag_type for f in flags),
                "rejections": errors, "nudges": len(nudges),
                "rationales": [p.rationale for p in props],
            }

    started = time.perf_counter()
    patient_id, intake_id = new_intake(None, case["note"], "INITIAL")
    first = collect(run_agent(patient_id, intake_id, kind="INITIAL"))
    second = None
    if case.get("recheck"):
        _, recheck_intake = new_intake(patient_id, case["recheck"], "RECHECK")
        second = collect(run_agent(patient_id, recheck_intake, kind="RECHECK"))
    result = {"case": case["id"], "run": n, "initial": first, "recheck": second,
              "wall_ms": int((time.perf_counter() - started) * 1000)}
    result["pass"], result["reasons"] = judge(case["expect"], first, second)
    return result


def judge(expect: dict, first: dict, second: dict | None) -> tuple[bool, list[str]]:
    reasons = []
    if first["status"] != "COMPLETED":
        reasons.append(f"run status {first['status']}")
    if "priority" in expect and first["priorities"] != [expect["priority"]]:
        reasons.append(f"priority {first['priorities'] or 'none'} != {expect['priority']}")
    if expect.get("no_proposal") and first["priorities"]:
        reasons.append(f"unexpected proposal {first['priorities']}")
    missing_flags = set(expect.get("flags", [])) - set(first["flags"])
    if missing_flags:
        reasons.append(f"missing flag {sorted(missing_flags)} (got {first['flags'] or 'none'})")
    missing_signs = set(expect.get("signs", [])) - set(first["signs"])
    if missing_signs:
        reasons.append(f"sign not cited {sorted(missing_signs)}")
    wrong_signs = set(expect.get("not_signs", [])) & set(first["signs"])
    if wrong_signs:
        reasons.append(f"negated sign cited {sorted(wrong_signs)}")
    if "recheck_flags" in expect:
        got = second["flags"] if second else []
        if not set(expect["recheck_flags"]) <= set(got):
            reasons.append(f"re-check flags {got or 'none'} != {expect['recheck_flags']}")
        if second and second["priorities"]:
            reasons.append("re-check run created a proposal")
    return not reasons, reasons


def cmd_run(args: argparse.Namespace) -> None:
    load_dotenv(ROOT / ".env")
    configure_model(args.provider, args.model)
    cases = yaml.safe_load(CASES.read_text())["cases"]
    if args.cases:
        cases = [c for c in cases if c["id"] in args.cases.split(",")]
    jobs = [(c, n) for n in range(1, args.runs + 1) for c in cases]
    print(f"{len(jobs)} runs: {len(cases)} cases x {args.runs} on {args.provider}:{args.model}", flush=True)

    results = []
    with ThreadPoolExecutor(max_workers=args.workers) as pool:
        for res in pool.map(lambda job: run_case(*job), jobs):
            mark = "PASS" if res["pass"] else "FAIL"
            print(f"  {mark} {res['case']:<34} #{res['run']} {res['initial']['latency_ms'] or 0:>6} ms "
                  f"{'; '.join(res['reasons'])}", flush=True)
            results.append(res)

    RESULTS.mkdir(parents=True, exist_ok=True)
    out = RESULTS / f"{args.label}.json"
    out.write_text(json.dumps({
        "label": args.label, "provider": args.provider, "model": args.model, "runs_per_case": args.runs,
        "price_per_million": {"input": args.price_in, "output": args.price_out, "source": args.price_source},
        "finished_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "results": results,
    }, indent=2) + "\n")
    print(f"wrote {out}")
    cmd_report(args)


def _signature(r: dict) -> tuple:
    second = r["recheck"]["flags"] if r["recheck"] else []
    return (tuple(r["initial"]["priorities"]), tuple(r["initial"]["flags"]), tuple(second))


def _summary(data: dict) -> dict:
    results = data["results"]
    by_case: dict[str, list[dict]] = {}
    for r in results:
        by_case.setdefault(r["case"], []).append(r)
    lat = [r["initial"]["latency_ms"] for r in results if r["initial"]["latency_ms"]]
    tin = [r["initial"]["input_tokens"] for r in results]
    tout = [r["initial"]["output_tokens"] for r in results]
    price = data.get("price_per_million") or {}
    cost = None
    if price.get("input") is not None and price.get("output") is not None:
        cost = statistics.mean(tin) / 1e6 * price["input"] + statistics.mean(tout) / 1e6 * price["output"]
    agree = sum(1 for runs in by_case.values() if len({_signature(r) for r in runs}) == 1)
    return {
        "runs": len(results), "passed": sum(r["pass"] for r in results), "cases": len(by_case),
        "cases_all_pass": sum(all(r["pass"] for r in runs) for runs in by_case.values()),
        "agreement": agree, "by_case": by_case,
        "lat_mean": statistics.mean(lat) if lat else 0, "lat_p90": sorted(lat)[int(0.9 * (len(lat) - 1))] if lat else 0,
        "tin": statistics.mean(tin) if tin else 0, "tout": statistics.mean(tout) if tout else 0, "cost": cost,
        "rejections": Counter(code for r in results for code in r["initial"]["rejections"]),
        "first_try": sum(1 for r in results if r["pass"] and not r["initial"]["rejections"]),
        "nudged": sum(1 for r in results if r["initial"]["nudges"]),
    }


def cmd_report(_: argparse.Namespace | None = None) -> None:
    cases = {c["id"]: c for c in yaml.safe_load(CASES.read_text())["cases"]}
    files = sorted(RESULTS.glob("*.json"))
    if not files:
        sys.exit("no results yet: run `run_evals.py run` first")
    datasets = [json.loads(f.read_text()) for f in files]

    lines = [
        "# EVALS",
        "",
        "Generated by `evals/run_evals.py` from real agent runs (both MCP servers, server-side checks, Postgres).",
        f"{len(cases)} synthetic cases in `evals/cases.yaml`, each run several times. Expected results were worked",
        "out by hand from the SATS Training Manual 2012 rules before any run and are not adjusted to the output.",
        "A run passes only if the final outcome matches exactly: the proposed priority (or no proposal), every",
        "required flag, every required emergency sign cited, and no negated sign cited.",
        "",
        "## Summary",
        "",
        "| Model | Runs | Pass rate | Cases passing every run | Run-to-run agreement | Correct first try | Mean latency | p90 latency | Mean tokens in / out | Cost per run |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    summaries = []
    for d in datasets:
        s = _summary(d)
        summaries.append((d, s))
        cost = f"${s['cost']:.4f}" if s["cost"] is not None else "n/a"
        lines.append(
            f"| {d['provider']}: `{d['model']}`<br><sub>{d['label']}</sub> | {s['runs']} | **{s['passed']}/{s['runs']} "
            f"({100 * s['passed'] / s['runs']:.0f}%)** | {s['cases_all_pass']}/{s['cases']} | "
            f"{s['agreement']}/{s['cases']} | {s['first_try']}/{s['runs']} | {s['lat_mean'] / 1000:.1f} s | "
            f"{s['lat_p90'] / 1000:.1f} s | {s['tin']:.0f} / {s['tout']:.0f} | {cost} |")
    lines += [
        "",
        "- **Run-to-run agreement**: cases where every run produced the same outcome (priorities and flags).",
        "- **Correct first try**: passing runs where the server never had to reject a proposal.",
        "- **Cost per run**: mean tokens times the listed price per million tokens (source in each section).",
        "",
    ]

    for d, s in summaries:
        price = d.get("price_per_million") or {}
        lines += [
            f"## {d['provider']}: `{d['model']}` ({d['label']})",
            "",
            f"{d['runs_per_case']} runs per case, finished {d['finished_at']}. "
            + (f"Price: ${price['input']}/M input, ${price['output']}/M output tokens ({price.get('source') or 'listed price'})."
               if price.get("input") is not None else ""),
            "",
            "| Case | Tags | Expected | " + " | ".join(f"Run {i}" for i in range(1, d["runs_per_case"] + 1))
            + " | Pass rate | Agreement | Mean latency |",
            "|---|---|---|" + "---|" * d["runs_per_case"] + "---|---|---|",
        ]
        for cid, runs in s["by_case"].items():
            runs = sorted(runs, key=lambda r: r["run"])
            exp = cases[cid]["expect"]
            exp_txt = exp.get("priority") or ("no proposal" if exp.get("no_proposal") else "")
            if exp.get("flags"):
                exp_txt += " + " + "/".join(exp["flags"])
            if exp.get("recheck_flags"):
                exp_txt += "; re-check " + "/".join(exp["recheck_flags"])
            cells = []
            for r in runs:
                got = "/".join(r["initial"]["priorities"]) or "—"
                if r["initial"]["flags"]:
                    got += " +" + "/".join(f.split("_")[0].lower() for f in r["initial"]["flags"])
                if r["recheck"]:
                    got += "; re-check " + ("/".join(r["recheck"]["flags"]) or "no flag")
                retries = len(r["initial"]["rejections"])
                cells.append(f"{'✅' if r['pass'] else '❌'} {got}" + (f" ({retries} fix)" if retries else ""))
            agree = "yes" if len({_signature(r) for r in runs}) == 1 else "**no**"
            lat = statistics.mean(r["initial"]["latency_ms"] or 0 for r in runs) / 1000
            lines.append(f"| `{cid}` | {', '.join(cases[cid].get('tags', []))} | {exp_txt} | " + " | ".join(cells)
                         + f" | {sum(r['pass'] for r in runs)}/{len(runs)} | {agree} | {lat:.1f} s |")
        fails = [r for runs in s["by_case"].values() for r in runs if not r["pass"]]
        lines += ["", "**Server rejections the agent recovered from or hit:** "
                  + (", ".join(f"`{k}` ×{v}" for k, v in s["rejections"].most_common()) or "none")
                  + f". Runs that needed a nudge to finish: {s['nudged']}.", ""]
        if fails:
            lines += ["**Failures:**", ""]
            for r in sorted(fails, key=lambda r: (r["case"], r["run"])):
                lines.append(f"- `{r['case']}` run {r['run']}: {'; '.join(r['reasons'])} (run `{r['initial']['run_id'][:8]}`)")
            lines.append("")

    if NOTES.exists():
        lines += [NOTES.read_text().strip(), ""]
    REPORT.write_text("\n".join(lines) + "\n")
    print(f"wrote {REPORT}")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)
    run = sub.add_parser("run")
    run.add_argument("--provider", choices=["ollama", "groq", "bedrock"], required=True)
    run.add_argument("--model", required=True)
    run.add_argument("--runs", type=int, default=3)
    run.add_argument("--workers", type=int, default=3)
    run.add_argument("--cases", help="comma-separated case ids (default: all)")
    run.add_argument("--label", required=True, help="results file name")
    run.add_argument("--price-in", type=float, help="USD per million input tokens")
    run.add_argument("--price-out", type=float, help="USD per million output tokens")
    run.add_argument("--price-source", default="")
    run.set_defaults(func=cmd_run)
    rep = sub.add_parser("report")
    rep.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
