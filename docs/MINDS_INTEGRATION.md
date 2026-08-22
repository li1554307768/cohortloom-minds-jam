# Minds Integration

CohortLoom uses Minds only as a persistence and recall layer for creator-approved decisions.

It does not use Minds to post, message, follow, email, or contact anyone.

## The three-session pattern

### 1. Store

After the creator approves a hypothesis, CohortLoom prepares a `store_hypothesis` packet.

That packet stores only the approved hypothesis and its supporting evidence.
It is created locally and still requires an explicit send action.

### 2. Recall and plan

When the creator opens a new session, CohortLoom prepares a `recall_and_plan` packet.

This packet:

- recalls the exact approved hypothesis
- uses 1 to 3 weekly summaries
- proposes a bounded 7-day manual experiment
- requires `manual_only = true`
- restricts each day to an approved channel

The plan is intentionally bounded. It must have exactly 7 days, unique days from 1 to 7, and no hidden outreach language.

### 3. Recall and review

At due review time, CohortLoom prepares a `recall_and_review` packet.

This packet:

- rechecks the experiment against the success and stop conditions
- returns one of `CONTINUE`, `STOP`, or `REVISE`
- keeps `manual_only = true`
- does not repeat the hypothesis body in the request data

The due-review request is built so the hypothesis is not copied back into the body. The request carries the experiment reference, due label, observed result, and the review thresholds instead.

## Transport rules

- The app refuses to send if the Mind ID or API key is missing.
- The app refuses to send if the local credit floor is below 10.
- The send action is explicit and human-triggered.
- On timeout or uncertain transport, CohortLoom checks official history before any retry logic.
- Blind resends are blocked.
- A request-hash mismatch fails closed.

## Schema rules

The packet schema is strict:

- JSON objects only
- exact `schema_version`
- exact `operation`
- exact `memory_key`
- exact response contract
- no extra fields
- no auto-generated outreach verbs

For plan packets, the seven-day plan must stay within the approved platform set derived from the weekly summaries.

## Why this matters

The integration is the difference between "remembering" and "automating."

CohortLoom uses Minds to preserve a creator's approved decision loop across sessions, while keeping the actual action loop local, bounded, and reviewable.

## Verified continuity boundary

The three-session pattern has been verified for one synthetic approved hypothesis through
official history: same Mind, three distinct conversations, strict schemas, correct timestamp
ordering, and matching continuity in both recall sessions. Public documentation exposes only
hashes and boolean conclusions. See [LIVE_MINDS_EVIDENCE.md](LIVE_MINDS_EVIDENCE.md).

This does not verify real creator adoption, audience growth, revenue, public upload, or public
submission.
