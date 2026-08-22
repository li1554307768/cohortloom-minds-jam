# CohortLoom

**The persistent experiment memory for creator growth.**

CohortLoom turns a synthetic weekly engagement summary into one falsifiable audience
hypothesis, one seven-day experiment, explicit success/stop conditions, and a due review.
It is **not an inbox, content-idea generator, social scheduler, or outreach tool**.

The local deterministic layer owns metrics, approval, deduplication, safety gates, and the
audit trail. Minds is used only after explicit approval to remember the exact hypothesis and
recall it in new sessions. No code can post, message, follow, email, or contact anyone.

## Run locally

Requirements: macOS or Linux, Python 3.10+, and [`uv`](https://docs.astral.sh/uv/).

```bash
uv sync --all-groups
cp .env.example .env
uv run uvicorn app.main:app --host 127.0.0.1 --port 8020
```

Open `http://127.0.0.1:8020`, load the synthetic week, record the prefilled hypothesis,
and approve it. Approval prepares a private Minds packet but never sends it automatically.

## Offline verification

```bash
make verify
```

The suite enforces at least 85% application coverage and runs pytest, Ruff, mypy, Bandit,
pip-audit, package build, secret scans, and a dependency-license check.

## Live proof safety gate

The proof script is offline by default because it requires an explicit mutually exclusive mode.
It uses one store, one plan recall, and one automatically prepared due-review recall in three
different conversations under the same Mind. The due review does not repeat the hypothesis in
its request body. A timeout is recovered only from official history; it is never blindly resent.

That three-session continuity proof is now verified for the synthetic demo case. The public
record contains only hashes and boolean conclusions; the redacted evidence artifact, raw
identifiers, aliases, conversation/message identifiers, and replies remain private and untracked.

```bash
# Network use and cognition spend: run only after explicit human confirmation.
uv run python scripts/run_live_minds_proof.py --confirm-live

# If a checkpoint exists, recover attempted stages from official history first.
uv run python scripts/run_live_minds_proof.py --recover-checkpoint
```

At a reported balance of 10 or lower, every new call stops. There is no recharge path.
If a checkpoint or final evidence artifact already exists, do not start a fresh proof; use the
read-only recovery path or stop.

## Project structure

```text
app/       FastAPI dashboard, SQLite workflow, strict Minds protocol
data/      explicitly synthetic weekly engagement summaries
docs/      architecture, safety, differentiation, evidence and submission copy
scripts/   live proof, security/license checks and deterministic video tools
tests/     unit, integration, web and offline live-proof tests
output/    generated logo and video artifacts (live evidence stays untracked)
```

## Evidence boundary

- All personas, metrics, hypotheses, experiments, and results in the demo are synthetic.
- Local tests alone do not prove live Minds persistence.
- The redacted evidence artifact verifies continuity under one Mind across three distinct
  conversations, with strict schemas and timestamp ordering.
- The final video keeps `SYNTHETIC DEMO` visible and displays
  `LIVE MINDS CONTINUITY VERIFIED` only because that evidence passed the fail-closed gate.
- Real users: 0. Real revenue: $0. Automated posts or outreach: 0.
- The source repository is public, while the YouTube demo is uploaded as **Unlisted**.
- DoraHacks BUIDL **#48044** was submitted to the
  **Audience growth & community engagement** track and is **Under Review**. This does not
  mean the BUIDL has been publicly showcased, approved, shortlisted, or awarded.

See [docs/EVIDENCE_STATUS.md](docs/EVIDENCE_STATUS.md) and
[docs/LIVE_MINDS_EVIDENCE.md](docs/LIVE_MINDS_EVIDENCE.md).

## Submission links

- Public repository: https://github.com/li1554307768/cohortloom-minds-jam
- Unlisted demo video: https://youtu.be/wpb5nt1uYV4
- DoraHacks submission: BUIDL #48044 — Under Review

## License

MIT.
