# Evidence Status

This file records what is verified, what is synthetic, and what remains unverified as of August 22, 2026.

## Current status

| Area | Status | Notes |
| --- | --- | --- |
| Local dashboard flow | VERIFIED | FastAPI dashboard, CSRF protection, pause control, hypothesis creation, experiment approval, and Minds send/sync routes exist locally. |
| Synthetic demo data | VERIFIED | `data/synthetic_demo.json` is explicitly labeled synthetic and is the only demo dataset used in the submission flow. |
| Local Minds packet rules | VERIFIED | Store, recall, and due-review packets are strictly schema-checked and fail closed on injection, bad shapes, or malformed replies. |
| Demo video assets | VERIFIED LOCALLY | The 111-second 1920x1080 H.264 MP4 has narration, keeps `SYNTHETIC DEMO` visible, displays `LIVE MINDS CONTINUITY VERIFIED`, has a SHA-256 digest, and returns `MEDIA_VERIFY_OK`. |
| Live Minds continuity | VERIFIED | A redacted evidence artifact verifies one store, one plan recall, and one due-review recall under the same Mind in three distinct conversations. All three official-history exchanges passed strict schema and timestamp-order checks. |
| Real users | NONE VERIFIED | No evidence of real user adoption was produced in this task. |
| Real revenue | NONE VERIFIED | No revenue evidence was produced in this task. |
| Public submission | NOT PERFORMED | No network publication or external submission was performed in this task. |

## What counts as evidence

For this submission, strong evidence means:

- a local run that matches the documented flow
- a rendered demo artifact that matches the script and manifest
- a live Minds proof that shows the full three-session pattern through official history
- a clear distinction between synthetic demo data and real external results

## What does not count

- README claims
- synthetic demo numbers
- a local pass presented as if it were live continuity
- a placeholder video report
- an unverified manual note about revenue or users

## Recommended wording

Use these labels consistently:

- `VERIFIED`
- `VERIFIED LOCALLY`
- `UNVERIFIED`
- `NOT PERFORMED`
- `SYNTHETIC ONLY`
- `LIVE MINDS CONTINUITY VERIFIED`

Do not blur them together. The hackathon write-up should stay honest about what is actually proven.
