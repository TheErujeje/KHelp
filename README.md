# Klaudesk

## Problem

In Nigeria's busy public hospital outpatient departments (OPDs) the queue starts at the triage
desk: one or two nurses, a blood pressure cuff and a stack of case cards between every arriving
patient and a doctor. Waits of 60–90 minutes before triage are common, and most queues still run
on arrival order, even in digitised clinics. Nurses must apply a triage scale by hand, from
abbreviated, often Pidgin notes, under pressure. Unless the danger is visible (bleeding, obvious
respiratory distress), a patient with chest pain or a dangerous heart rate can wait behind routine
follow-ups, and deterioration in the waiting room goes unnoticed. With too few doctors, getting the
sickest patient seen first matters more, not less.

## Solution overview

An agent that helps a triage nurse in a busy public-hospital outpatient department (OPD) in Nigeria.
The nurse types the presenting complaint and vitals the way they go on the case card (abbreviated,
sometimes in Nigerian Pidgin). The agent scores the patient with the **South African Triage Scale
(SATS)** and **proposes** a priority (RED / ORANGE / YELLOW / GREEN) with a citation for every vital
and emergency sign behind it. A **named nurse or doctor** approves or overrides it. Only that human
decision moves the patient in the queue.

It never diagnoses, never prescribes, and never changes the queue by itself.

> **Track:** Health & Wellbeing, The Triage Desk.
> **Themes:** symptom-based priority scoring, and deterioration watch (re-check while waiting).
> **All patient data in this repository and in the live demo is synthetic.**

## Target users

- **Triage nurses** at the OPD triage desk: score every arrival quickly and consistently, with the
  evidence on screen, and approve or raise the priority.
- **Doctors and senior nurses**: see who to call next, already briefed, against SATS target times;
  make the senior decisions (lowering a priority, children sent to manual triage).
- **Patients**: those with less visible but serious conditions stop being pushed down the queue.
- **Facility managers and auditors**: every tool call and decision is logged with who, when and why.

## Usage: try the live demo

**https://klaudesk.klaudverse.com**

Sign in with any name (demo sign-in, no password check) and pick a role. Each role lands on its own
work:

| Role | Lands on | Can do |
|---|---|---|
| **Triage nurse** | **Triage desk**: type the note (or pick a synthetic sample), watch the agent score it, then **Approve** or raise the priority, and move to the next patient | Approve, raise a priority, re-check a waiting patient, acknowledge flags |
| **Doctor** | **Next up**: triaged patients in call order, each with a timer against the SATS target time (RED immediate, ORANGE 10 min, YELLOW 1 h, GREEN 4 h), the note, why that priority, who triaged it, and deterioration alerts | **Call in**, **Seen**, and senior decisions: lower a priority, set the priority of a child sent to manual triage |
| **Senior nurse** | **Next up** | Same senior decisions as a doctor (SATS manual p.6, senior healthcare professional's discretion) |

The **Queue** page has the whole waiting room with a **Score** button for the seeded synthetic
patients, and the **Audit log** shows every tool call and every decision with who made it.
The live demo runs the open-weights model `gpt-oss-120b`; see [Where the model runs](#where-the-model-runs).

## What a nurse told us

We showed Klaudesk to a Registered Nurse at a private clinic in Lagos, who has worked in a fully
digitalised clinic. Lightly edited for length:

> "The queuing system was just a normal queue: you register in the queue and it keeps passing you.
> … If it is a real emergency (bleeding, visibly injured, respiratory distress) it has to be evident;
> that's when they give you emergency care, and then you are put on a bed, which is still your queue.
> … Someone with less visible symptoms will go before me … even though my problem is more severe."

> "This is a good solution. If our triage system was working, this would help to group the patients
> into triage rooms, and if there are enough doctors, they can attend to different patients in
> different triage groups."

> "It's good that the AI can triage for you, but it's also great that your medical knowledge is
> needed to approve the priority level, because in medicine there is objective and subjective."

That last point is the design: the deterministic SATS scoring is the objective part, and the named
nurse or doctor who approves, raises or (if senior) lowers the priority is the subjective part.
The "triage rooms" idea is our next step: let each doctor's **Next up** board follow one priority
group, so patients are streamed by urgency rather than by who arrived first.

## Setup and installation (run it yourself)

You need **Docker** (with Compose v2) and **Git**. Everything else (Postgres, the API, the agent, both
MCP servers, the web UI) runs in containers.

```bash
git clone https://github.com/TheErujeje/Klaudesk.git
cd Klaudesk
cp .env.example .env
```

Then pick how to run the model. **Option A is the quickest for reviewers.**

### Option A: hosted open-weights model (fastest, about 10–60 s per patient)

Get a free API key at <https://console.groq.com>, then set these lines in `.env`:

```
KHELP_USE_LOCAL_MODEL=false
KHELP_HOSTED_PROVIDER=groq
GROQ_API_KEY=gsk_...
```

```bash
docker compose up -d --build
```

### Option B: fully self-hosted (no API key, no data leaves your machine)

**With an NVIDIA GPU (Linux):**

```bash
sed -i 's/^OLLAMA_MODEL=.*/OLLAMA_MODEL=qwen2.5:14b-instruct/' .env    # 7b also works; 14b reads Pidgin better
docker compose -f docker-compose.yml -f deploy/compose.gpu.yml --profile local-model up -d --build
docker compose logs -f ollama-pull                                      # wait for "success" (one-time model download)
```

**On a Mac:** Ollama inside Docker cannot use the Apple GPU, so install Ollama natively
(<https://ollama.com/download>), then:

```bash
ollama pull qwen2.5:7b-instruct
sed -i '' 's|^OLLAMA_BASE_URL=.*|OLLAMA_BASE_URL=http://host.docker.internal:11434|' .env
docker compose up -d --build
```

**CPU only:** `docker compose --profile local-model up -d --build` works with no other setup, but a
7B model on a CPU takes several minutes per patient. Raise `KHELP_RUN_TIMEOUT_SECONDS` to `900` in
`.env` first. Models smaller than 3B do not complete the task reliably.

### Then

Open **http://localhost**, sign in with any name, and score a patient. The first start builds the
images (a few minutes), runs the database migrations, creates the restricted database role the MCP
server uses, and seeds 8 synthetic patients.

```bash
docker compose ps                  # db healthy, api and web up
curl -s localhost/api/health       # shows which model is in use
docker compose logs -f api         # agent runs as they happen
docker compose down -v             # stop and delete all data
```

Port 80 must be free. To use another port, change `"80:80"` under `web` in `docker-compose.yml`.

### Run the tests

```bash
uv sync && uv run pytest           # 111 tests: scoring (against the manual), proposal checks, roles, model settings
```

### Run one note from the command line (no web UI)

```bash
docker compose exec api khelp-agent --text "45yrs M c/o chest pain since morning, no SOB. Walked in, alert. RR 22 PR 118 BP 150/90 T 37.1C"
```

This prints every tool call, the result, tokens and latency.

## Architecture

Diagram: **[docs/klaudesk-architecture.pdf](docs/klaudesk-architecture.pdf)** ·
one-page design: **[ARCHITECTURE.md](ARCHITECTURE.md)** · plain-language walk-through: **[docs/WORKFLOW.md](docs/WORKFLOW.md)**

```
nurse ──note──> API ──starts run──> Agent (open-weights LLM, Strands Agents)
                                      │  read_text_file ─────────> filesystem MCP server (borrowed)
                                      │  lookup_discriminators ─┐
                                      │  compute_tews ──────────┤
                                      │  propose_priority ──────┼─> triage-tools MCP server (ours)
                                      │  request_recheck ───────┘    recomputes, checks, rejects
                                      ▼
                       PENDING proposal + citations ──> nurse approves / overrides (named) ──> queue
```

Components: React web UI · FastAPI (approval gate, role rules, SSE live feed) · one Strands agent per
patient run · two MCP servers · PostgreSQL (restricted role for the MCP server, append-only audit log)
· SATS rules as YAML · an open-weights LLM (Bedrock or self-hosted Ollama).

### Agent architecture

- **One agent per patient run**, started in the background when a nurse submits a note or a re-check.
  Its only job: score and cite, then propose a priority or raise a flag.
- **Loop:** plan → call a tool → read the structured result → correct → finish with exactly one action
  (`propose_priority` or `request_recheck`).
- **Self-correction:** the MCP server recomputes everything and rejects a wrong priority, a vital or
  age not in the note, an uncited emergency sign or diagnostic language, with `how_to_fix`; the agent
  retries. Visible in the live feed.
- **Bounds:** at most 12 tool calls, a timeout and two "finish the task" nudges. A run that ends without
  a valid result puts the patient on manual triage; an API restart marks in-flight runs failed.
- **Memory:** none across patients, by design. State lives in Postgres; the agent sees only what the
  tools return.
- **The judgement is not in the model:** scoring is deterministic Python (`packages/scoring`) driven by
  `sats/*.yaml`, transcribed from the SATS Training Manual 2012 with page references.

### MCP implementation: servers and tools

The agent's only abilities come through two MCP servers, started by the Strands MCP client as stdio
subprocesses for each run (tools discovered at runtime; our server process carries the run id).

**triage-tools** (ours, `packages/mcp-triage-tools`, official MCP Python SDK):

| Tool | Kind | What it does |
|---|---|---|
| `get_queue` | read-only | Waiting patients and their approved priorities |
| `lookup_discriminators` | read-only | SATS emergency signs found in the note (keywords incl. Pidgin, negation-aware; no model) |
| `compute_tews` | read-only | Triage Early Warning Score from vitals; flags missing or implausible values |
| `propose_priority` | action | Recomputes the priority, checks every cited input against the note, saves a **PENDING** proposal with citations |
| `request_recheck` | action | Raises a flag for a human: missing vitals, deterioration, manual triage |

Errors are structured results with `how_to_fix`, not exceptions. The server writes through a
restricted Postgres role that cannot approve anything or change the queue, and each tool's writes
and its audit row commit in one transaction.

**filesystem** (borrowed: the official `@modelcontextprotocol/server-filesystem`), limited to
`read_text_file` on the intake folder. Borrowed rather than written because it is maintained by the
MCP project and already guards against path escapes. We use MCP tools only (no resources or prompts).

Results on 15 synthetic cases, 3 runs each, with failures: **[EVALS.md](EVALS.md)**.

## Human-in-the-loop workflow

1. **Triage nurse** types the note → the agent proposes a priority with citations (the queue is unchanged).
2. **Triage nurse** reviews the "why" and the evidence, then **approves** or **raises** the priority.
   Only now does the patient move in the queue. Their name and role are recorded.
3. **Lowering** a priority below the SATS result, or setting the priority of a child sent to manual
   triage, needs a **doctor or senior nurse** (SATS manual p.6, senior healthcare professional's discretion).
4. **Doctor** works from **Next up**: call order, SATS target-time timers, the brief, **Call in** → **Seen**.
5. While patients wait, a **re-check** that shows deterioration raises a **second-look alert**; the
   agent never moves the patient itself. Flags are acknowledged by a named clinician.
6. Every tool call and decision is in the **audit log** (filterable, CSV export).

### Safety rules and where they are enforced

| Rule | Enforced by |
|---|---|
| The agent cannot move a patient | Postgres permissions: the MCP server's database role has no grant to write approvals or update patients |
| Every priority is cited | Citations are built server-side; the database rejects a proposal without them |
| Missing vitals are never guessed | Values must appear in the note; a missing value is bounded, not filled in; if it could change the priority, the patient is flagged for a re-check |
| No diagnosis or treatment | The server rejects rationales with doses, prescribing words, condition names or hedged diagnoses |
| Every action logged | Each tool writes its audit row in the same transaction as its action; the audit table rejects UPDATE and DELETE |
| A named human decides | Approve, override (with a reason) and manual-triage acknowledge are the only paths that set a priority; each records name and role |
| Senior discretion (SATS p.6) | Lowering a priority below the SATS result, or setting a manual-triage priority, needs a doctor or senior nurse; the API refuses a triage nurse (403) |
| Runs are bounded | Max 12 tool calls and a timeout per run; a run that ends without a valid result flags the patient for manual triage |

## Where the model runs

One setting, `KHELP_USE_LOCAL_MODEL`, chooses:

- `true`: **self-hosted Ollama** (e.g. `qwen2.5:14b-instruct` on a GPU). This is the production shape;
  patient data stays on the hospital's infrastructure.
- `false`: **hosted**, by `KHELP_HOSTED_PROVIDER`: `groq` (`gpt-oss-120b`) or `bedrock`
  (e.g. `openai.gpt-oss-120b-1:0` on Amazon Bedrock). For development and demos on synthetic data only.

All options are open-weights models. On the live server these settings live in one AWS SSM parameter
and are applied within a minute of a change, with no redeploy. Deployment: [deploy/ec2-setup.md](deploy/ec2-setup.md).

## Technology stack

| Layer | Technology |
|---|---|
| Agent orchestration | Strands Agents (Python) |
| LLMs (open-weights) | gpt-oss-120b on Amazon Bedrock (live); Qwen2.5 via Ollama (self-hosted); Groq optional |
| MCP | official MCP Python SDK (our server); `@modelcontextprotocol/server-filesystem` (borrowed) |
| Backend | Python 3.12, uv, FastAPI, Uvicorn, SQLAlchemy, Alembic, psycopg 3 |
| Database | PostgreSQL 16 |
| Frontend | React, Vite, TypeScript, Tailwind CSS, React Router, TanStack Query |
| Infrastructure | Docker Compose, Caddy (HTTPS), AWS EC2, AWS SSM Parameter Store, IAM (Bedrock) |
| External APIs | Amazon Bedrock (model); Groq (optional). Nothing else |

## Data and sources

- **Patients:** synthetic only. `data/synthetic/generate.py` (fixed seed) writes
  `data/synthetic/patients.json`: 30 messy notes with abbreviations, Pidgin, missing vitals,
  Fahrenheit, odd BP formats, typos, children under 12, a request for a diagnosis, and a
  "put him in front, he's my brother" request. No real patient data is used anywhere.
- **Triage scale:** the South African Triage Scale (SATS), adult version, transcribed from **The South
  African Triage Scale (SATS) Training Manual 2012** (Western Cape Government Health and the South
  African Triage Group): adult TEWS from p.26 Figure 14, the TEWS-to-priority rule from p.6 Figure 2
  and the Adult SATS Chart (p.8-9), and the adult emergency, very urgent and urgent signs from p.12-13.
  Every entry in `sats/*.yaml` names its page and figure, and every proposal shows those references
  to the nurse. SATS resources are published by EMSSA under CC BY-NC-SA 3.0; the manual is not
  redistributed here. Where to get it, its checksum and the page map: [docs/reference/README.md](docs/reference/README.md).

## Limitations (what is unfinished)

- **SATS values were transcribed by hand from the 2012 manual** and tested against it (`sats/*.yaml`,
  tests in `packages/scoring/tests`). A clinician should still review the transcription before any
  real use. The manual also lets a nurse score temperature by touch ("cold"/"hot"); Klaudesk scores
  only a measured temperature.
- **Adults only.** Paediatric SATS is out of scope. Patients under 12, or with no age written, are
  flagged for manual triage and never scored with the adult scale.
- **The phrase lists that recognise each sign** (English synonyms, abbreviations, Nigerian Pidgin) are
  Klaudesk's own drafts, not from the manual, and need review by Nigerian triage nurses. So does the
  mapping of pain scores (5-7/10 moderate, 8-10/10 severe).
- **Emergency-sign matching is keyword based.** It handles negation within a clause ("no SOB") but
  can miss unusual phrasing; the nurse can always override.
- **Additional investigations** from the adult chart (e.g. "if RR scores 1 point or more, check SpO2
  and hand over to a senior clinician") are not yet prompted. SpO2 is recorded but, as in the manual,
  is not itself an adult emergency sign.
- **Demo sign-in only**: no real accounts. A hospital deployment would use its own staff login.
- **Smaller models need correcting.** 3B–7B models often get the priority wrong on the first try;
  the server rejects it and they fix it, which shows in the live feed. Models under 3B fail the task.
- **Roles come from the demo sign-in.** The API enforces what each role may do, but a hospital
  deployment would take the role from its own staff login.

## Future improvements

- **Triage rooms / streaming** (a nurse's suggestion): let each doctor's Next up board follow one
  priority group, so patients are seen by urgency in parallel rather than one shared line.
- **Server-side guard for emergencies without vitals**: before accepting a manual-triage or
  missing-vitals flag, run the emergency-sign lookup on the note and require a RED/ORANGE proposal
  when a sign is present (the one evaluation failure we did not fix; see [EVALS.md](EVALS.md)).
- **SATS additional investigations** prompts (e.g. "RR scores 1 or more: check SpO2, hand over").
- **Paediatric SATS** (younger and older child TEWS) instead of manual triage for under-12s.
- **Clinical review** of the SATS transcription and of the Pidgin phrase lists by Nigerian triage nurses.
- **Self-hosted model in-country**, so real patient data never leaves the facility; real staff login.
- **A larger, fresh evaluation set**, run on every change to the prompt, tools or model.

## Repository layout

```
sats/                     SATS tables (YAML), each entry with source + verified flag
packages/scoring/         deterministic TEWS, emergency signs, priority rules (+ tests)
packages/mcp-triage-tools/ our MCP server (5 tools) + server-side proposal checks
packages/db/              Postgres models and Alembic migrations (incl. restricted MCP role)
apps/api/                 FastAPI app, agent runner (Strands), approval gate, SSE live feed
apps/web/                 React + Vite + TypeScript + Tailwind UI
data/synthetic/           synthetic note generator and seeded patients
deploy/                   Caddy config, EC2 guide and deploy scripts
docs/WORKFLOW.md          how it works, in plain language
```

## Licence

Apache-2.0. See [LICENSE](LICENSE).
