# How Klaudesk works

A plain walk-through of what happens when a nurse uses Klaudesk, and what each part is for.

## The one-sentence version

A nurse types a patient's complaint and vitals; an AI agent uses a small set of **tools** to score them
with the South African Triage Scale (SATS) and **proposes** a priority with a citation for every number;
a **named nurse or doctor** approves or overrides it; only that human decision moves the patient in the queue.

## The parts

| Part | What it is | Where |
|---|---|---|
| **Web UI** | What the nurse sees: sign-in, dashboard/queue, triage desk, approvals, audit log | `apps/web` |
| **API** | The web server. Stores patients, starts agent runs, and holds the **approval gate** | `apps/api` |
| **Agent** | An open-weights language model (e.g. `gpt-oss-120b`, `qwen2.5`) driven by Strands Agents. It reads the note and decides which tool to call next | `apps/api/src/khelp_api/agent` |
| **triage-tools MCP server** | Our own tool server: 5 tools that do the actual scoring and record the result | `packages/mcp-triage-tools` |
| **Filesystem MCP server** | A tool server we did not write (official MCP reference server). Lets the agent read the intake note file | installed with `npx` |
| **Scoring library** | Plain Python, no AI: TEWS calculation, emergency-sign matching, priority rules | `packages/scoring` |
| **SATS rules** | The scoring tables as YAML, transcribed from the SATS Training Manual 2012, each line citing its page and figure | `sats/` |
| **Postgres** | Patients, notes, vitals, proposals, flags, approvals, and the append-only audit log | `packages/db` |

## What is MCP, and what is it doing here?

**MCP (Model Context Protocol)** is an open standard for giving an AI model *tools*. A tool server
publishes a list of tools — each with a name, a description and typed inputs — and any MCP-capable
agent can discover and call them. Think of it like a USB socket for tools: the agent does not need to
know how a tool works inside, only what it is called and what it takes.

In Klaudesk the agent has **no abilities of its own** beyond reading text and choosing which tool to call.
Everything it can *do* comes through two MCP servers:

1. **triage-tools (ours)** — five tools:

   | Tool | Kind | What it does |
   |---|---|---|
   | `get_queue` | read-only | Shows who is waiting and their approved priority |
   | `lookup_discriminators` | read-only | Finds SATS emergency signs in the note (e.g. "chest pain", "belle dey pain me", "SOB"). Keyword matching, no AI |
   | `compute_tews` | read-only | Calculates the Triage Early Warning Score from vitals. Flags missing or impossible values (SpO2 104%, "T 101" with no unit) |
   | `propose_priority` | **action** | Saves a *PENDING* proposal. The server **re-does the whole calculation itself** and rejects the proposal if the priority is wrong, a vital isn't in the note, an emergency sign is left out, or the rationale sounds like a diagnosis |
   | `request_recheck` | **action** | Raises a flag for a human: missing vitals, the patient got worse, or manual triage (e.g. a child) |

2. **filesystem (borrowed)** — the official MCP filesystem server, restricted to one tool
   (`read_text_file`) and one folder (`data/intake/`). We use it rather than writing our own file
   reader because it is maintained, already handles path-escape attacks, and is the standard way MCP
   agents read files.

Why this split matters: the **judgement-free arithmetic lives in tools, not in the model.** The model
can be wrong about the priority; the tool server cannot be argued with. And because the tools are a
standard MCP server, any other MCP agent (a different framework, a different hospital's system) can
reuse them.

## A patient's journey, step by step

```
Nurse                 API                   Agent (LLM)                 triage-tools MCP           Database
  |  type note  ------> |                        |                              |                        |
  |                     | save patient + note -----------------------------------------------------------> |
  |                     | write note to data/intake/patient-12-intake-13.txt    |                        |
  |                     | start run ------------> |                              |                        |
  |                     |                        | read_text_file (filesystem MCP)                        |
  |                     |                        | lookup_discriminators ------> | keyword match          |
  |                     |                        | compute_tews ---------------> | TEWS arithmetic        |
  |                     |                        | propose_priority -----------> | recompute + check      |
  |                     |                        |   <-- rejected: "rules give ORANGE, not RED"           |
  |                     |                        | propose_priority (ORANGE) --> | PENDING proposal ----> |
  |  <-- live feed of every tool call (from the audit log) ------------------------------------------------ |
  |  review citations                            |                              |                        |
  |  Approve / Override (named) -> | set approved priority, log who and why ------------------------------> |
  |  queue reorders                |                                                                       |
```

1. **Sign in.** The nurse signs in (demo sign-in: name and role only). Their name is attached to every
   decision they make.
2. **Intake.** The nurse types the note the way it would go on the case card:
   `45yrs M c/o chest pain, no SOB. walked in, alert. RR 22 PR 118 BP 150/90 T 37.1C`.
3. **The agent runs** (about 5–60 seconds depending on the model):
   - reads the note through the filesystem MCP server;
   - asks `lookup_discriminators` for emergency signs → *chest pain (ORANGE)*; "no SOB" is recognised as negated;
   - asks `compute_tews` with the vitals it found → *RR 22 = 2 pts, HR 118 = 2 pts … TEWS 4 (YELLOW)*;
   - calls `propose_priority` with ORANGE (the higher of TEWS and the emergency sign) and its citations.
4. **The server checks the agent.** If the agent got anything wrong, the tool returns a structured error
   with `how_to_fix`, and the agent corrects itself and tries again. This is visible in the live feed.
5. **Missing vitals.** If a vital that could change the priority is missing, the agent does not guess:
   - if the patient is already ORANGE/RED on what *is* known, it proposes that **and** raises a
     "vitals needed" flag;
   - otherwise it only raises the flag, and the nurse re-takes the vitals.
6. **A child (under 12) or no age written** → manual triage flag. The adult scale is never applied to children.
7. **Human decision.** The nurse sees the proposal with every citation
   (`HR 118 → band 111–129 → 2 pts → SATS manual, Adult TEWS table`) and clicks **Approve**, or
   **Override** with a new priority and a reason. Only now does the patient move in the queue.
8. **While waiting.** If the nurse re-takes vitals later, the agent re-scores; if worse, it raises a
   **"second look"** flag. It never moves the patient itself.

## The safety rules, and where each is enforced

| Rule | Enforced by |
|---|---|
| The agent cannot change queue position | Database permissions: the MCP server's database user has **no permission** to write approvals or update patients. Not a prompt instruction — Postgres refuses |
| Every priority is cited | `propose_priority` builds the citations server-side; the database rejects a proposal with none |
| No guessing vitals | Server checks every number the agent passes actually appears in the note; missing values are bounded, never filled in |
| No diagnosis / treatment | Server rejects rationales with doses, prescribing words, condition names or "likely/possible/suggests" |
| Every tool call logged | Each tool writes its audit row in the same database transaction as its action; the audit table rejects UPDATE/DELETE |
| A human decides | Approve / override / acknowledge are the only code paths that set a priority, and each needs a name |
| Runs can't loop forever | Max 12 tool calls and a time limit per run; if a run ends without a valid result, the patient is flagged for manual triage |

## Where the model runs

The challenge requires the task to run on an **open-weights** model and says patient data must not
leave the country. One setting, `KHELP_USE_LOCAL_MODEL`, chooses:

- **`true`: self-hosted (Ollama)**, e.g. `qwen2.5:14b-instruct` on our own GPU instance. This is the
  production shape: patient data never leaves the hospital's infrastructure.
- **`false`: hosted**, picked by `KHELP_HOSTED_PROVIDER`:
  - `groq`: open-weights `gpt-oss-120b` on Groq, fast; development and demos on **synthetic data only**;
  - `bedrock`: a model on Amazon Bedrock in eu-west-1 (e.g. open-weights `openai.gpt-oss-120b-1:0`),
    using the server's IAM role.

On the deployed server these settings live in one SSM parameter; changing the switch there takes
effect within about a minute, without a redeploy.

## What is *not* AI

Everything that produces a number is deterministic code: TEWS bands, emergency-sign matching, the
priority rule, the missing-vitals rule. The model's job is narrow: read messy text, pull out the
vitals, call tools in the right order, and recover when a tool says it got something wrong.
