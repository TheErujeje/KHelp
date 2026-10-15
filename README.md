# Klaudesk

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

## Try the live demo

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

## Run it yourself

You need **Docker** (with Compose v2) and **Git**. Everything else (Postgres, the API, the agent, both
MCP servers, the web UI) runs in containers.

```bash
git clone https://github.com/TheErujeje/KHelp.git
cd KHelp
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

## How it works

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

- The **agent** reads the note, calls tools in order, and corrects itself when a tool rejects its
  answer. The model never does the arithmetic and cannot change the queue.
- **triage-tools** (our MCP server, `packages/mcp-triage-tools`) has five tools. Scoring is
  deterministic Python (`packages/scoring`) driven by the SATS tables in `sats/*.yaml`.
  `propose_priority` recomputes the priority from the cited inputs, checks every vital and the age
  actually appear in the note, requires every emergency sign found in the note to be cited, and
  rejects diagnostic or treatment language. It returns a structured error the agent must fix.
- **filesystem** (the official MCP reference server, not written by us) reads the intake note,
  limited to one folder and one read-only tool. We borrowed it rather than writing a file reader
  because it is maintained and already guards against path escapes.
- Every tool call and every human decision goes to an append-only audit log, shown live in the UI.

A plain-language walk-through, including what MCP is and where each safety rule is enforced, is in
**[docs/WORKFLOW.md](docs/WORKFLOW.md)**. One-page design: **[ARCHITECTURE.md](ARCHITECTURE.md)**.
Results on 15 synthetic cases, 3 runs each, with failures: **[EVALS.md](EVALS.md)**.

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

## What is unfinished (read this)

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
