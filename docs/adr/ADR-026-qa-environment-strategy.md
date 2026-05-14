# ADR-026: QA Environment Strategy — Vercel Preview First, Backend QA Deferred

**Status**: Accepted
**Date**: 2026-05-14

---

## Context

Satlas reached its MVP (v0.1.0) running on a single production stack: one
Fly.io app for the API + workers, one self-hosted Redis app, one
Postgres app, and Vercel hosting the frontend. Every change ships
straight to prod. With the user base growing past feedback-from-friends
scale, this gets riskier: a bad backend deploy can break the dashboard
or admin endpoints in front of real users (see the visits/recompute 500
regression that surfaced post-launch).

The instinct is to add a full QA environment that mirrors prod: a
separate Fly.io app, separate Postgres, separate Redis, separate Vercel
project. Deploy first to QA, validate, then promote to prod.

For a one-person project at this stage, that ratchets up the ongoing
maintenance burden in a way the change risk does not justify yet:

- **Two stacks to feed**: TLE refresh cron has to run somewhere for QA
  too (or QA gets stale data). Two sets of secrets to rotate.
  Two sets of Alembic migrations to apply in order.
- **Drift**: QA and prod diverge over time if not actively reconciled.
  A QA pass becomes meaningless if the environments are not equivalent.
- **Usage gap**: The dominant failure mode at 1-person scale is
  "deploys to QA but skips the validation step." The infra exists, the
  workflow doesn't.
- **Cost**: Two of every Fly.io app — even shared-cpu-1x — adds ~$10/mo
  for a benefit that goes unused most weeks.

Meanwhile, Vercel already ships free per-branch preview deployments out
of the box. Every PR or non-`main` branch automatically gets its own
URL pointing at production-API data. Frontend changes — which are most
of the visible regression risk — already have a built-in QA path; the
project just isn't using it yet.

---

## Decision

**Adopt Vercel Preview deployments as the QA layer for the frontend.
Defer a separate backend QA environment until concrete need arises.**

Concretely:

1. Frontend changes flow through a feature branch and a PR. Vercel
   builds a preview against the PR. Manual validation happens on the
   preview URL before merging to `main`.
2. Backend changes still deploy straight to prod from `main`. Risk is
   mitigated by:
   - Sentry capturing 5xx and uncaught exceptions (ADR-026 follow-on)
   - Manual local validation against `docker-compose` before push
   - Reversible via `flyctl deploy --image-label <prior>` if a deploy
     breaks behaviour
3. A full backend QA environment is **not** spun up at this time. The
   trigger to revisit:
   - A schema migration that is hard to reverse and risks data loss
   - A recompute / scheduler change with cross-cutting impact
   - Sustained pattern (3+ in a quarter) of prod regressions that QA
     would have caught

---

## Alternatives Considered

### Full QA stack (`satlas-api-qa`, `satlas-redis-qa`, separate Postgres, separate Vercel project)

- **Pros**: Mirrors production, enables real integration testing,
  protects prod from migration mistakes
- **Cons**: ~$10/mo ongoing cost; two sets of secrets / migrations / TLE
  cron to maintain; drift between QA and prod over time; high
  likelihood of being unused at 1-person ops cadence
- **Rejected because**: maintenance overhead exceeds the regression
  prevention value at current scale

### Hybrid (Vercel Preview + shared backend, no separate API for QA)

- This is what the decision lands on. Frontend gets a real QA path;
  backend stays single-stack until a concrete trigger appears.

### Branch-based promotion (`staging` branch → QA stack → `main` → prod)

- Workflow-heavy; assumes a full QA stack exists (see above)
- Useful only if there are humans gating the staging-to-prod promotion
- For 1-person ops, the staging branch tends to become a stale auto-merge
  target

### Status quo (deploy main to prod, no QA)

- This was the implicit policy through MVP. Worked because frontend
  changes were small and backend changes were rare. Now that backend
  changes are more frequent (chunked recompute, prewarm tuning,
  observability wiring), the lack of a frontend QA path is the bigger
  blind spot.

---

## Consequences

### Positive

- Frontend PRs get free isolated QA via Vercel Preview without new infra
- Backend deploys stay simple and rollback-friendly
- No new monthly cost
- Sentry continues to be the safety net for live regressions

### Negative

- Backend regressions still reach prod (the visits/recompute 500 case
  would not have been caught by this strategy alone)
- A future risky migration will need ad-hoc validation — likely a
  one-off `satlas-api-staging` machine that is created, used, and torn
  down within the change window
- Promotion to backend QA is deferred indefinitely; revisit triggers
  are spelled out above but require discipline to honour

### Operational follow-ups

- Document Vercel Preview usage in the operations runbook
- When the first trigger fires (e.g., a schema-heavy migration), spin
  up a temporary `satlas-api-staging` Fly app, run the change there,
  then tear it down. Revisit this ADR if the pattern repeats.
