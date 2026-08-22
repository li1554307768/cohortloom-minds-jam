# Security

CohortLoom is designed to fail closed.

The main security goal is simple: do not let a synthetic demo, a stale reply, or a prompt injection turn into an automatic external action.

## Threat model

The main risks are:

- prompt injection in hypothesis text or weekly summaries
- accidental auto-send
- blind retry after an uncertain transport result
- leaking API keys or other secrets
- confusing synthetic demo data with real user evidence
- cross-site form abuse in the local dashboard

## Built-in controls

### Local dashboard protection

- CSRF token + cookie check on mutating forms
- `X-Frame-Options: DENY`
- `X-Content-Type-Options: nosniff`
- `Referrer-Policy: no-referrer`
- restrictive Content Security Policy

### Database protection

- SQLite with foreign keys enabled
- WAL mode
- unique constraints on core workflow records
- explicit paused state and audit trail

### Minds protection

- explicit approval before a packet is prepared for send
- strict JSON schema checks
- request-hash verification
- no blind resend on timeout
- official-history verification before continuing uncertain sends
- local credit floor with a hard lower bound of 10

### Prompt injection isolation

The app treats human text as untrusted data.

It checks hypothesis text, evidence text, and weekly observations for suspicious instruction patterns before building the Minds packet.
It also keeps the packet contract narrow so that the model cannot drift into posting or outreach language.

## Release gates

The repository includes local security checks:

- `scripts/security_scan.py` for secrets and sensitive artifacts
- `scripts/check_licenses.py` for dependency license sanity
- the test suite for workflow and packet rules

These checks do not prove the app is production-safe, but they do catch the most likely hackathon failure modes.

## What is still unsafe by design

- The demo data is synthetic, so it cannot prove real-market demand.
- A local pass alone does not prove live Minds continuity; CohortLoom keeps a separate redacted
  official-history evidence artifact for that claim.
- A verified live continuity exchange does not prove real users, growth, revenue, public upload,
  or public submission.

Those are evidence gaps, not security bugs.
