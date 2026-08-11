# Task 4: Structured Operational Telemetry Report

## Scope

Added structured, secret-safe operational telemetry for the trusted Render API.
The public API remains unchanged except for the approved additional fields on
`/api/health`.

## Files

- `dashboard/telemetry.py` — JSON event logger with an explicit field allowlist.
- `dashboard/api.py` — request-latency logging; registry, reconciliation,
  Bradbury-failure, and settlement-verification events; operational health data.
- `render.yaml` — declares the Render-owned `MERIT_RELEASE` environment value.
- `tests/backend/test_store_and_demo_roles.py` — secret-redaction and health
  evidence coverage.

## RED / GREEN

1. RED: added `test_log_event_redacts_secret_fields`; it failed at collection
   because `dashboard.telemetry` did not exist.
2. RED: added the health evidence test; after the telemetry module existed it
   failed with `KeyError: 'release'` from `/api/health`.
3. GREEN: both new tests passed after the smallest telemetry and health
   implementation.
4. Follow-up RED: a refreshed 120-second-old pending transaction was reported
   as 60 seconds old because selection used `updated_at` but age used
   `created_at`.
5. Follow-up GREEN: the durable store now selects the oldest non-terminal
   transaction by `created_at`; the divergent-order regression passes.

## Decisions

- Unknown field names are omitted. Safe field values are constrained to a
  bounded identifier-like format or replaced with `redacted`; exception text,
  environment values, request headers, and request bodies are never logged.
- Request logs include only method, path, HTTP status, and duration.
- `MERIT_RELEASE` defaults to `unknown` locally and is supplied by Render as a
  secret-style deployment setting.
- `oldest_pending_seconds` is derived from the oldest non-terminal durable
  transaction's `created_at`, never its refresh time; `last_reconcile_at`
  records the latest reconciliation attempt.

## Verification

- `PYTHONPATH=<worktree> DEPLOYER_PRIVATE_KEY=<non-secret placeholder> .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k 'redacts or health_reports'` — 2 passed.
- `PYTHONPATH=<worktree> DEPLOYER_PRIVATE_KEY=<non-secret placeholder> .venv/bin/pytest -q tests/backend` — 52 passed.
- `.venv/bin/python -m py_compile dashboard/api.py dashboard/store.py dashboard/telemetry.py` — passed.
- `npm run lint` — passed.
- `git diff --check` — passed.
- Follow-up regression (`-k oldest_pending`) — 1 passed.
- Follow-up full backend suite — 53 passed.

The repository-local pytest invocation requires `DEPLOYER_PRIVATE_KEY` because
the installed `gltest` plugin initializes before these backend tests collect.
Verification used the project venv from `/private/tmp` with the worktree on
`PYTHONPATH`, so the plugin could not clear tracked `artifacts/` files; no live
chain operation was invoked.

## Risks

- Operators must set `MERIT_RELEASE` during Render deployment for an exact
  release identifier; otherwise health reports `unknown`.
- Structured logs intentionally omit unexpected data, which favors custody and
  credential safety over retaining arbitrary third-party diagnostics.

## Commit

`feat: add safe escrow observability`
