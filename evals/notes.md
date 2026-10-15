## What the failures were, and what we changed

Every failure above was traced through the audit log of that run (tool calls, inputs, server
responses). None was "the model got the arithmetic wrong": the server recomputes every score, so
wrong numbers never reach a nurse. The failures are about the agent choosing the wrong *action*.

**1. Fixed: a tool default mislabelled a flag (gpt-oss-120b, `no_age_collapsed`, run A #1).**
The agent correctly decided the patient (no age written) needed manual triage and said so in its
reason, but omitted the `flag_type` argument. Our `request_recheck` tool defaulted it to
`MISSING_VITALS`, so the flag reached the nurse as "vitals needed" instead of "manual triage". The
patient was still flagged for a human, but with a less urgent label. This was our tool-design bug,
not the model's: a silent default on a safety-relevant field. `flag_type` no longer has a default; a
missing value returns `INVALID_FLAG_TYPE` with `how_to_fix`, and the agent retries. Run B is the full
set re-run after this change.

**2. Fixed: the agent added a unit that was not written (gpt-oss-120b, `fahrenheit_no_unit_bp_single`,
run B #1).** The note said `T 101 BP 160`. The agent sent `temp: "101F"` and `systolic_bp: 160`; our
grounding check only confirmed that the *numbers* 101 and 160 appear in the note, so the invented
unit and the reshaped blood pressure passed, and the patient was proposed GREEN instead of being sent
for a re-check. The brief names exactly these ("temperature in Fahrenheit", "BP not in sys/dia form")
as things to flag, not guess. The server now also requires that a temperature unit the agent passes
is written next to that number in the note, and that a systolic value comes from a "sys/dia" reading
in the note. Two regression tests cover it. Run C is the full set after this change.

**3. Fixed: a re-check run stopped before scoring the new vitals (gpt-oss-120b,
`deterioration_on_recheck`, run B #3).** The agent read the re-check note, looked up signs, and
ended without calling `compute_tews`, so the deterioration was not flagged. The runner's "finish the
task" nudge only covered first intakes; a re-check run that never scored the new vitals is now nudged
too (logged as `NUDGE` in the audit trail).

**4. Not fixed: over-cautious extraction by the smaller model (Qwen3-32B,
`diagnosis_request` and `deterioration_on_recheck`).** The note said "Alert, walked in" but the model
left `avpu` and `mobility` out of the vitals. The server correctly refused to guess, returned
`OUTCOME_RECHECK`, and the model raised a "vitals needed" flag instead of re-submitting with the
values that were in the note. Safe, but it costs the nurse a re-check. gpt-oss-120b does not do this.

## Read these numbers with care

- **Run C's 100% is on the same 15 cases that exposed the bugs.** The three fixes are general
  (a tool argument with no silent default, unit and blood-pressure grounding, a re-check nudge), not
  rules written for particular notes, but only a fresh set of cases would show how well they
  generalise. 15 cases × 3 runs is a small sample.
- **Run-to-run variation is real.** Between runs A and B, with only one change, different cases
  failed. That is why every case runs three times and agreement is reported.
- **The model does not do the scoring.** A "pass" means the agent chose the right *action* and cited
  the right signs; every score in a passing or failing run was recomputed by the server from the SATS
  rules.
- **Expectations are SATS as written**, not a clinician's judgement. In `diagnosis_request` (BP
  190/110 with blurred vision) SATS gives GREEN; a clinician might reasonably raise it, which is why a
  named clinician approves or overrides every proposal.

## The one failure we did not fix, and what we would try next

**A seizing patient was sent to manual triage instead of RED (Qwen3-32B, `seizure_no_vitals`, 3 of 3
runs).** The note: *"30yr M brought in by family, convulsing now, actively fitting on the trolley. No
vitals taken yet."* The model read the note, skipped `lookup_discriminators` and `compute_tews`
entirely, and called `request_recheck(flag_type="MANUAL_TRIAGE")` because "no vitals have been
recorded". The correct result is a RED proposal: a current seizure is an emergency sign (SATS manual
p.12) and missing vitals cannot lower it. A human is still alerted immediately (manual triage is
shown as urgent), so the patient is not lost, but the system failed to say "RED" when the rules are
unambiguous.

Why we did not fix it on the last day: the model-side fix (more prompt rules) is fragile, and the
right fix is a server-side guard that needs its own tests. The larger model (gpt-oss-120b, the one
the live demo uses) gets this case right in every run.

What we would try next, in order:

1. **Server-side guard in `request_recheck`:** before accepting `MISSING_VITALS` or `MANUAL_TRIAGE`
   for a patient with an age of 12 or more, run `lookup_discriminators` on the note itself; if a
   RED or ORANGE sign is present, reject with `how_to_fix: "an emergency sign is present - call
   propose_priority; missing vitals cannot lower it"`. This turns the failure into a recovery, the
   same way `propose_priority` already does for wrong priorities.
2. **Order the tools:** `request_recheck` refuses to run until `lookup_discriminators` has been
   called in the same run (the server knows, because every call is logged against the run id).
3. **Add these notes to the eval set as regression cases**, and run the eval on every change to the
   prompt, the tools or the model.

## How to reproduce

```bash
uv sync
# needs Postgres (DATABASE_URL, MCP_DATABASE_URL in .env) and a model; AWS credentials for Bedrock
uv run python evals/run_evals.py run --provider bedrock --model openai.gpt-oss-120b-1:0 --runs 3 \
  --label my-run --price-in 0.18 --price-out 0.70
uv run python evals/run_evals.py report    # rebuilds this file from evals/results/*.json
```

Raw results for every run (tool-call counts, tokens, latency, server rejections, rationales) are in
`evals/results/*.json`; each run id can be looked up in the audit log.
