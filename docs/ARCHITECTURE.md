# CohortLoom Architecture

CohortLoom is a local-first FastAPI app backed by SQLite. The product is built around one narrow loop:

weekly metrics -> one falsifiable creator-approved audience hypothesis -> one 7-day manual experiment -> explicit success and stop conditions -> due review.

It is not an inbox, content-idea generator, correction tool, social scheduler, or outreach tool.

## System shape

- `app/main.py` wires the FastAPI app, the dashboard, CSRF protection, static files, and explicit routes.
- `app/services.py` owns the workflow logic: load synthetic week, record hypothesis, approve/reject, prepare Minds packets, and persist audit history.
- `app/minds.py` owns the strict Minds packet schema, response validation, request reconstruction, and transport rules.
- `app/db.py` creates the SQLite schema and keeps the app fail-closed when required tables are missing.
- `app/config.py` loads safe local defaults from environment variables.
- `data/synthetic_demo.json` contains the synthetic demo week.
- `scripts/run_live_minds_proof.py` is the separate live-proof runner.
- `scripts/security_scan.py` and `scripts/check_licenses.py` are release gates.
- `scripts/generate_demo_video_assets.py`, `render_demo_video.swift`, and `verify_demo_video.swift` produce and validate the demo video.
- `tests/` holds the local proof that the app and packet rules behave as expected.

## Runtime flow

1. The dashboard loads a synthetic weekly snapshot.
2. The creator records one audience hypothesis from those metrics.
3. The creator approves or rejects the hypothesis.
4. If approved, CohortLoom prepares a private Minds memory packet.
5. Only an explicit human click can send the packet.
6. A second Minds session recalls the approved hypothesis and proposes a bounded 7-day plan.
7. A third Minds session handles the due review without repeating the hypothesis body in the request.
8. Every state change is written to the local SQLite audit trail.

## Data boundaries

The database stores only local workflow state:

- weekly snapshots and engagement metrics
- hypotheses and experiment state
- Minds exchanges and transport evidence
- audit events

The demo dataset is synthetic by design. No table, route, or script should present it as a real user, real revenue, or real adoption signal.

## Safety boundaries

CohortLoom is intentionally narrow:

- No automatic posting
- No automatic outreach
- No automatic follow-up
- No auto-send on startup
- No blind retry after an uncertain transport result
- No hidden network behavior in the default app flow

The only network-capable step is the explicit Minds send action, and even that is guarded by:

- a configured Mind ID and API key
- a local credit floor
- schema validation
- a request-hash check
- official-history verification before any resend logic

## Why this shape works

The design separates three different kinds of truth:

- raw weekly metrics
- creator judgment about what the metrics mean
- a constrained experiment plan that can be reviewed later

That separation keeps the app auditable. It also makes the hackathon story easy to explain: CohortLoom is not trying to automate the creator. It is trying to preserve the creator's decision loop.
