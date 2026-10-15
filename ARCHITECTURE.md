# Klaudesk architecture

One page: the agent's shape, the MCP servers we built and the one we borrowed, and why.

```
 Triage nurse ─ note ─▶ FastAPI ─ run (background, 1 per patient) ─▶ Strands agent ── open-weights LLM
   (React UI)            │  approval gate                               │        (Ollama self-hosted,
                         │  SSE live feed ◀── audit_log ◀───────────────┤         or Bedrock/Groq on
 Doctor ◀─ Next up ──────┤                                              │         synthetic data)
                         │                         ┌─────── MCP (stdio) ┴───────────────┐
                         │                         ▼                                    ▼
                         │            triage-tools (ours, Python)          filesystem (borrowed, official)
                         │            get_queue · lookup_discriminators     read_text_file only,
                         │            compute_tews · propose_priority       data/intake/ only
                         │            request_recheck
                         │                         │ restricted DB role (khelp_mcp)
                         ▼                         ▼
                      Postgres: patients, intakes, vitals, agent_runs, proposals, recheck_flags,
                                approvals (named clinician + role), audit_log (append-only)
```

## Agent shape

A single **Strands** agent per patient run, on an open-weights model chosen by one setting
(`KHELP_USE_LOCAL_MODEL`): self-hosted Ollama (production shape) or a hosted endpoint for synthetic
data. The loop is plan → call tool → read the structured result → correct → finish with exactly one
action:

1. read the intake note (filesystem MCP);
2. `lookup_discriminators` on the note text, and `compute_tews` on the vitals it read;
3. `propose_priority` with the vitals, age, cited signs and a one-line rationale; or
   `request_recheck` (missing vitals, deterioration, manual triage for children).

**Recovery is real, not prompted:** `propose_priority` recomputes everything server-side and rejects
the call with a structured error and `how_to_fix` (wrong priority, a sign left out, a vital or age
not in the note, diagnostic language). The agent reads it and retries; the live feed shows it.

**Bounds:** at most 12 tool calls, a time limit, two "finish the task" nudges; any run that ends
without a valid proposal or flag puts the patient on manual triage. Runs do not survive restarts: an API
restart marks in-flight runs failed and flags the patients.

## The judgement is not in the model

All arithmetic and every rule live in `packages/scoring` (deterministic Python) and `sats/*.yaml`,
transcribed from the SATS Training Manual 2012 with page references. The model reads messy text and
orchestrates; it cannot invent a priority, a vital, an emergency sign or a citation, and it cannot
move a patient.

## MCP servers: built versus borrowed

**Built: `triage-tools`** (`packages/mcp-triage-tools`, official `mcp` SDK, stdio). Five tools with
clear boundaries a stranger could reuse with any MCP agent: three read-only (`get_queue`,
`lookup_discriminators`, `compute_tews`) and two actions that only ever write PENDING records
(`propose_priority`, `request_recheck`). We built it because nothing existing knows SATS, and because
the safety checks must sit *behind* the tool boundary, where the model cannot skip them. Errors come
back as data the agent can act on, never as exceptions that kill the run. One server process per run
carries the run id, so every audit row is attributable without trusting the model.

**Borrowed: the official MCP filesystem server** (`@modelcontextprotocol/server-filesystem`), limited
to `read_text_file` on `data/intake/`. It beats writing our own: it is maintained by the MCP project,
already guards against path traversal, and is what any MCP client expects for reading files.

## Where the guarantees are enforced

| Guarantee | Mechanism |
|---|---|
| The agent cannot change queue position | Postgres grants: the MCP server's role cannot write approvals or update patients |
| Only a named human sets a priority | approve / override / manual-triage acknowledge are the only paths; each records name and role |
| Senior discretion (SATS p.6) | API: lowering a priority or setting a manual-triage priority needs a doctor or senior nurse (403 otherwise) |
| Every priority is cited | citations built server-side; the database rejects a proposal without them |
| Every action logged | tool writes and their audit row commit in one transaction; `audit_log` rejects UPDATE/DELETE/TRUNCATE |
| No diagnosis or treatment | server rejects rationales with doses, prescribing, condition names or hedged diagnoses |

## Deployment

`docker compose up` runs Postgres, the API (agent and both MCP servers inside), and Caddy (static UI,
`/api` proxy, automatic HTTPS). The live demo is one EC2 instance in eu-west-1 behind
https://klaudesk.klaudverse.com; its settings, including which model to use, live in one SSM
parameter that a timer applies within a minute. The self-hosted model runs on a GPU instance (or any
in-country server) with `KHELP_USE_LOCAL_MODEL=true`.
