# Klaudesk: a cited triage desk for Nigerian outpatient departments

In a busy public hospital outpatient department, the queue starts at the triage desk. One or two
nurses work through a stack of case cards, and a patient with chest pain can sit behind a routine
follow-up until someone reaches their card. Klaudesk helps that nurse do the right thing faster,
without taking the decision away.

The nurse types the complaint and vitals the way they write the case card, abbreviations and
Nigerian Pidgin included ("c/o", "DIB", "belle dey pain me"). An open-weights agent (gpt-oss-120b;
self-hostable with Ollama) reads the note and calls tools on our own MCP server, which scores the
patient with the South African Triage Scale (SATS): adult emergency signs and the Triage Early
Warning Score, transcribed from the SATS Training Manual 2012 with page references. The server
recomputes every result, rejects anything the note doesn't support, and sends the agent back to
correct itself. The agent never guesses a missing vital, never diagnoses, and cannot move a patient.
Postgres permissions forbid it.

The output is a proposed priority with a citation for every number: vital → band → points → manual
page. The triage nurse approves it or raises it. Lowering it needs a doctor or senior nurse,
following SATS's own senior-discretion rule. Only then does the queue change. Doctors get a "Next up"
board showing who to call, already briefed, with timers against SATS target times. While patients
wait, re-checks that show deterioration raise a second-look alert for a human.

**Sub-themes:** symptom-based priority scoring; deterioration watch.
**Facility and workflow:** the triage desk of a public hospital outpatient department, from arrival
to the consulting room.

On 15 synthetic cases run three times each, the agent chose the right action in 45/45 runs after
three fixes the evals uncovered, at about 8 s and $0.003 per patient. Every tool call and decision
is audited.

<!-- NURSE QUOTE: one or two sentences from the conversation, with their role and facility type,
     e.g. "Triage nurse, general hospital OPD, Lagos". -->

Live demo: https://klaudesk.klaudverse.com · Code: https://github.com/TheErujeje/KHelp
