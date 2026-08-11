# Task 1: Idempotent transaction journal report

## Requirements addressed

- Added `JobStore.record_transaction`, `get_transaction`, and `list_pending_transactions`.
- Added a durable SQLite `transactions` journal with a unique `(network, tx_hash)` identity, status rank, serialized payload, creation/update timestamps, and optional verification timestamp.
- Made writes atomic with `BEGIN IMMEDIATE`; identical immutable identity values return the existing journal row, while a reused hash for a different job address or kind raises `ValueError`.
- Prevented status regressions by updating only when a recognized transaction-status rank increases.

## Files changed

- `dashboard/store.py`
- `tests/backend/test_store_and_demo_roles.py`
- `.superpowers/sdd/2026-08-10-merit-reliability-and-custody/task-1-report.md`

## Test evidence

### RED

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k transaction`

Result: 2 failed, 3 passed, 33 deselected. Both new tests failed with `AttributeError: 'JobStore' object has no attribute 'record_transaction'`, as expected before implementation.

### GREEN

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k transaction`

Result: 5 passed, 33 deselected.

### Full backend regression

`PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/backend`

Result: 38 passed.

## Design decisions

- The primary journal key is SQLite-generated and stable across idempotent retries; network plus transaction hash is the durable unique identity.
- Journal payloads preserve the submitted record as JSON, while returned store rows expose a decoded `payload` field.
- Statuses are validated against the supported network lifecycle. `FINALIZED`, `FAILED`, `REJECTED`, and `CANCELLED` are terminal and excluded from pending reconciliation queries.
- Job-address comparison is case-insensitive to match Ethereum-style address semantics; kind remains exact because it identifies the operation class.

## Risks

- The supported status-rank map intentionally covers the statuses required for Bradbury-style transaction progression. A future SDK status requires an explicit map update rather than silently being persisted.
- This task provides storage only. Route-level transaction identity verification and replay response handling are intentionally deferred to Task 2.

## Commit

- Implementation: `98b33009ea107d633aff93c5e726e3c0d4b4c7d1` (`feat: add idempotent transaction journal`)
