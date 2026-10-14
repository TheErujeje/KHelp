# Reference: SATS Training Manual 2012

The rule values in `sats/*.yaml` are transcribed from:

**The South African Triage Scale (SATS) Training Manual 2012**, Western Cape Government Health and
the South African Triage Group.

- Copy used: <https://medbox.org/index.php/dl/610cf5bbe58a3f709b7a50d4>
  (PDF, 1,636,761 bytes, SHA-256 `410c8d4b11b59eb41c5c283419ba85f4b7507ccd9569ab4b987b8512f9cc30b5`)
- Publisher of SATS resources: Emergency Medicine Society of South Africa (EMSSA), <https://emssa.org.za/?p=48>,
  under Creative Commons Attribution-NonCommercial-ShareAlike 3.0.

The PDF is not committed to this repository. Download it here as `sats-2012.pdf` to check entries.

| Klaudesk file | Manual pages |
|---|---|
| `sats/tews.yaml` (adult TEWS bands) | p.26 Figure 14 "Adult TEWS"; p.9 Figure 4; observation definitions p.26-27 |
| `sats/priority_rules.yaml` (TEWS to priority) | p.6 Figure 2 "SATS process flowchart"; p.8-9 Figure 4 "Adult SATS Chart" |
| `sats/discriminators.yaml` (adult clinical signs) | p.12 (3.1 Emergency, 3.2 Very urgent), p.13 (3.3 Urgent) |

Not from the manual (Klaudesk's own, labelled in the files): the phrase lists used to recognise each
sign in free text (English synonyms, abbreviations, Nigerian Pidgin), the 5-7/10 and 8-10/10 pain-score
mapping, and the missing-vitals rule.
