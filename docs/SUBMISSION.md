# Klaudesk: a cited triage desk for Nigerian outpatient departments

> "I worked in a clinic where everything was digitalised … but the queuing system was just a normal
> queue: you register in the queue and it keeps passing you. … Someone with less visible symptoms
> will go before me … even though my problem is more severe."
> <br>— Registered Nurse, Private Clinic, Lagos

Klaudesk fixes that at the triage desk. The nurse types the complaint and vitals the way they write
the case card, abbreviations and Nigerian Pidgin included ("c/o", "DIB", "belle dey pain me"). An
open-weights agent (gpt-oss-120b; self-hostable with Ollama) calls tools on our own MCP server,
which scores the patient with the South African Triage Scale (SATS): adult emergency signs and the
Triage Early Warning Score, transcribed from the SATS Training Manual 2012 with page references. The
server recomputes every result, rejects anything the note doesn't support, and sends the agent back
to correct itself. It never guesses a missing vital, never diagnoses, and cannot move a patient:
database permissions forbid it.

The output is a proposed priority with a citation for every number. The triage nurse approves it or
raises it; lowering it needs a doctor or senior nurse, following SATS's own senior-discretion rule.
Only then does the queue change. Doctors get a "Next up" board showing who to call, already briefed,
with timers against SATS target times. While patients wait, re-checks that show deterioration raise
a second-look alert for a human.

> "It's good that the AI can triage for you, but it's also great that your medical knowledge is
> needed to approve the priority level, because in medicine there is objective and subjective."
> <br>— the same nurse

**Sub-themes:** symptom-based priority scoring; deterioration watch.
**Facility and workflow:** the triage desk of a public hospital outpatient department, from arrival
to the consulting room.

On 15 synthetic cases run three times each, the agent chose the right action in 45/45 runs after
three fixes the evals uncovered, at about 8 s and $0.003 per patient. Every tool call and decision
is audited.

Live demo: https://klaudesk.klaudverse.com · Code: https://github.com/TheErujeje/Klaudesk
