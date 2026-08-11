# Task 2: Wallet registration retry-safety report

## Requirements addressed

- Added `_verify_transaction_identity(tx_hash, expected_from, expected_to)` to read a Bradbury transaction and validate its status, wallet signer, destination or created contract, and any transaction-level network value.
- Wallet deployment and settlement registration now journal a verified transaction before mutating the SQLite job registry.
- Replayed deployment registrations return the persisted job and `replayed: true` while retaining every existing response field.
- A hash already journaled for a different job or action now returns HTTP 409 with `TRANSACTION_IDENTITY_CONFLICT`; it cannot be attached to another settlement.
- Deployment validation requires a created-contract address and settlement validation requires the escrow recipient plus a settlement-compatible on-chain state, preserving the distinct expected actions.

## Files changed

- `dashboard/api.py`
  - Added shared transaction identity and journal helpers.
  - Integrated retry and conflict behavior into wallet deployment and settlement registration.
- `tests/backend/test_store_and_demo_roles.py`
  - Added real-store API-boundary coverage for deployment replay and cross-job settlement-hash conflict.
  - Updated existing successful wallet fixtures with an authenticated deployment sender/network and isolated journal calls from the global store.

## TDD evidence

### RED

Command:

```sh
PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k 'replay or identity_conflict'
```

Result: `2 failed, 40 deselected`. The replay test failed with missing `replayed`; the cross-job settlement test returned `422 SETTLEMENT_CONTRACT_MISMATCH` instead of the required `409 TRANSACTION_IDENTITY_CONFLICT`.

### GREEN

The same focused command passed: `2 passed, 40 deselected`.

## Verification

- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py` — `42 passed`.
- `npm test -- --run tests/frontend/transaction-state.test.ts tests/frontend/wallet.test.ts` — `2 files, 5 tests passed`.
- `PYTHONPATH=. PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m py_compile dashboard/api.py` — passed.

## Design decisions

- The transaction journal remains the immutable hash-to-job/action authority. A preflight journal lookup reports a cross-job/action reuse conflict before a stale client request can receive a misleading recipient error; the original write was already fully verified.
- The endpoint re-reads and verifies a same-identity replay, then re-records it idempotently before any registry write. This permits recovery if a process stopped after journal persistence but before `add_job` or `update_job`.
- The Bradbury client is fixed to `testnet_bradbury`; a transaction-level network field is additionally rejected if it contradicts that network. SDK responses that omit this optional field remain compatible with current response data.
- Existing success response fields are unchanged. `replayed` is an additive field emitted only for a known transaction replay.

## Risks and follow-up

- A repository-wide `pytest -q` cannot collect both `tests/direct/test_evaluate_submission.py` and `tests/integration/test_evaluate_submission.py` because they share a module basename. This is unrelated to the change.
- Running `tests/direct` separately with the required `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1` has 27 setup errors because its `direct_deploy`/`direct_vm` fixtures are supplied by disabled external test tooling. The backend and frontend task regressions above are clean.

## Commit

- Implementation: `f271f00f717f8da2dae736ab7e93aa1b784dd141` (`fix: make wallet registration retry safe`)
