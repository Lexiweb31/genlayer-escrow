# Task 3: Durable reconciliation and truthful payment state report

## Requirements addressed

- Added durable SQLite job fields for `reconcile_state`, `reconcile_attempted_at`, and `reconcile_error_code`; `reconcile_age_seconds` is derived from the persisted timestamp when a row is read.
- Reconciliation now skips legacy and verified-final records, persists a bounded `BACKING_OFF` state after failed non-final reads, and clears the public error field after a successful refresh.
- Stable, non-diagnostic read-failure categories are exposed as `TESTNET_UNAVAILABLE`, `TESTNET_RATE_LIMITED`, `TESTNET_NOT_FOUND`, or `TESTNET_READ_FAILED`.
- A failed refresh never writes a replacement snapshot. List and detail responses retain the last verified lifecycle state and mark it `stale: true`; direct detail reads also respect the persisted backoff after restart.
- Added typed reconciliation fields and a presentation mapper with `SUBMITTED`, `ACCEPTED_NOT_FINALIZED`, `FINALIZED`, `FAILED`, `CANCELLED`, and `RECOVERY_REQUIRED` states. Pending presentations include the transaction reference/link when known, reconciliation age, and one explicit next action.

## Files changed

- `dashboard/store.py`
- `dashboard/api.py`
- `lib/types.ts`
- `lib/job-presentation.ts`
- `tests/backend/test_store_and_demo_roles.py`
- `tests/frontend/job-presentation.test.ts`

## TDD evidence

### RED

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend/test_store_and_demo_roles.py -k reconcile`

Result: `1 failed, 1 passed, 45 deselected`. The new durable-reconciliation assertion failed with `KeyError: 'reconcile_state'`, proving the registry metadata did not yet exist.

`npm test -- --run tests/frontend/job-presentation.test.ts`

Result: `3 failed, 3 passed`. Every new truthfulness case failed because `reconciliationPresentation` was not implemented.

### GREEN

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend/test_store_and_demo_roles.py -k reconcile`

Result: `2 passed, 45 deselected`.

`npm test -- --run tests/frontend/job-presentation.test.ts`

Result: `1 file, 6 tests passed`.

## Final verification

- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend` — `47 passed` (one pre-existing third-party `websockets.legacy` deprecation warning).
- `npm test -- --run tests/frontend/job-presentation.test.ts tests/frontend/settlement.test.ts` — `2 files, 14 tests passed`.
- `npm run typecheck` — passed.
- `npm run lint` — passed.
- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m py_compile dashboard/api.py dashboard/store.py` — passed.
- `git diff --check` — passed.

## Decisions

- The retry deadline is represented by `BACKING_OFF` plus the durable last-attempt timestamp, rather than process memory. It uses `MARKETPLACE_RECONCILE_BACKOFF_SECONDS`, bounded to 10–300 seconds and defaulting to 30 seconds.
- The previous verified snapshot remains the sole source for stale lifecycle/payment data. Read errors store only a stable public error category, not raw SDK or network diagnostics.
- A settlement is presented as `ACCEPTED_NOT_FINALIZED` until outbound transfer finality is verified. Missing hashes require hash recovery; cancelled and failed hashes explicitly direct the user to reconnect the assigned client wallet.

## Risks and follow-up

- Reconciliation failure categories intentionally classify only stable public conditions. New SDK-specific exception patterns can be added to the classifier without changing the response shape.
- `reconcile_age_seconds` is computed at read time from the durable timestamp, so it remains accurate across process restarts but is not a stored counter.

## Commits

- Implementation: `c4bab4295fea9690bd1f2ef10a5251cb65b6b759` (`feat: expose truthful reconciliation states`)

## Review follow-up: truthful detail responses and rendered guidance

### Requirements addressed

- No-snapshot detail reads now classify failures with `_reconciliation_error_code` and return only the public code and generic message; raw SDK/network diagnostics are not exposed.
- Detail read success and stale fallback paths now use the row returned by `store.update_job`, so callers receive current `CURRENT`/cleared metadata or current `BACKING_OFF`/error metadata alongside `stale: true`.
- The manage view now renders `reconciliationPresentation` for pending payments. It shows state-specific wording, the safe transaction link when known, elapsed reconciliation context, stale-data context, and an explicit action label for refresh, recovery, reconnect, or finality.

### RED

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend/test_store_and_demo_roles.py -k 'detail_read'`

Result: `3 failed, 47 deselected`. The no-snapshot route returned `TESTNET_READ_FAILED` plus the private RPC diagnostic; stale and recovery responses returned their pre-update `IDLE` and `BACKING_OFF` metadata.

`npm test -- --run tests/frontend/manage-reconciliation.test.ts`

Result: `1 failed`. Server-rendered manage output contained the old hard-coded acceptance copy and lacked the mapper's elapsed context, transaction action link, and finality action.

### GREEN

- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend/test_store_and_demo_roles.py -k 'detail_read'` — `3 passed, 47 deselected`.
- `npm test -- --run tests/frontend/manage-reconciliation.test.ts` — `1 file, 1 test passed`.
- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend` — `50 passed` (one pre-existing third-party `websockets.legacy` deprecation warning).
- `npm test -- --run tests/frontend/job-presentation.test.ts tests/frontend/settlement.test.ts tests/frontend/manage-reconciliation.test.ts` — `3 files, 15 tests passed`.
- `npm run typecheck` and `npm run lint` — passed.
- `npm run build` — passed.

### Review fix commit

- `4a55b96202f8be295c47286caad2841c6e4aa435` (`fix: return truthful reconciliation detail`)
