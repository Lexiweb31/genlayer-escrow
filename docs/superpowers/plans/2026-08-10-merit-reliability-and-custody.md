# Merit Reliability and Custody Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make every Merit wallet write retry-safe, independently reconciled, and provable through transaction and balance evidence.

**Architecture:** Extend the SQLite registry with an append-only transaction journal and reconciliation metadata. Registration endpoints validate a Bradbury hash, then upsert by network and hash in one transaction; the background reconciler advances only mutable jobs and records structured outcomes.

**Tech Stack:** FastAPI, SQLite, GenLayer Python SDK, pytest, Next.js proxy routes, Vitest.

## Global Constraints

- Do not change intelligent contract source or deployed contract behavior in this phase.
- Existing `jobs` rows and API fields must remain readable without destructive migration.
- A transaction is confirmed only when its Bradbury status and expected signer/contract relationship are verified.
- Redact private keys, authorization values, and environment values from logs and API errors.

---

### Task 1: Add an idempotent transaction journal

**Files:**
- Modify: `dashboard/store.py`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `JobStore.record_transaction(record: dict[str, Any]) -> dict[str, Any]`
- Produces: `JobStore.get_transaction(network: str, tx_hash: str) -> Optional[dict[str, Any]]`
- Produces: `JobStore.list_pending_transactions(limit: int = 100) -> list[dict[str, Any]]`

- [ ] **Step 1: Write failing store tests**

```python
def test_transaction_hash_is_idempotent(store):
    item = {"network": "testnet_bradbury", "tx_hash": "0xabc", "job_address": "0xjob", "kind": "DEPLOYMENT", "status": "ACCEPTED"}
    first = store.record_transaction(item)
    second = store.record_transaction(item)
    assert first["id"] == second["id"]
    assert len(store.list_pending_transactions()) == 1

def test_transaction_status_can_advance_but_not_regress(store):
    base = {"network": "testnet_bradbury", "tx_hash": "0xdef", "job_address": "0xjob", "kind": "SETTLEMENT", "status": "ACCEPTED"}
    store.record_transaction(base)
    store.record_transaction({**base, "status": "FINALIZED", "verified_at": "2026-08-10T00:00:00+00:00"})
    store.record_transaction(base)
    assert store.get_transaction("testnet_bradbury", "0xdef")["status"] == "FINALIZED"
```

- [ ] **Step 2: Run the focused tests and verify failure**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py -k transaction`

Expected: FAIL because the transaction journal methods do not exist.

- [ ] **Step 3: Add the journal schema and atomic upsert**

Add a `transactions` table with `UNIQUE(network, tx_hash)`, status rank validation, `payload_json`, `created_at`, `updated_at`, and `verified_at`. Use `BEGIN IMMEDIATE` and return the existing row when the same hash and immutable identity fields repeat; raise `ValueError` if the hash is reused for a different job or kind.

- [ ] **Step 4: Run the focused tests**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py -k transaction`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/store.py tests/backend/test_store_and_demo_roles.py
git commit -m "feat: add idempotent transaction journal"
```

### Task 2: Make wallet registration routes retry-safe

**Files:**
- Modify: `dashboard/api.py`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Consumes: `JobStore.record_transaction(...)`
- Produces: `_verify_transaction_identity(tx_hash: str, expected_from: str, expected_to: str | None) -> dict[str, Any]`
- Preserves: existing `/api/jobs/register-wallet` and settlement registration response fields.

- [ ] **Step 1: Write failing API tests**

```python
def test_register_wallet_job_replay_returns_same_job(client, verified_deploy):
    first = client.post("/api/jobs/register-wallet", json=verified_deploy)
    second = client.post("/api/jobs/register-wallet", json=verified_deploy)
    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["job"]["address"] == first.json()["job"]["address"]

def test_settlement_hash_cannot_attach_to_another_job(client, verified_settlement):
    assert client.post("/api/jobs/job-a/register-settlement", json=verified_settlement).status_code == 200
    response = client.post("/api/jobs/job-b/register-settlement", json=verified_settlement)
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "TRANSACTION_IDENTITY_CONFLICT"
```

- [ ] **Step 2: Verify the tests fail**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py -k 'replay or identity_conflict'`

Expected: at least one duplicate or conflict assertion fails.

- [ ] **Step 3: Journal verified writes before registry mutation**

Validate transaction status, sender, recipient/created contract, network, and expected action. Call `record_transaction` before `add_job`/`update_job`; on a replay, return the already-associated job with `replayed: true` while retaining all old response fields.

- [ ] **Step 4: Run API and frontend recovery tests**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py && npm test -- --run tests/frontend/transaction-state.test.ts tests/frontend/wallet.test.ts`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/api.py tests/backend/test_store_and_demo_roles.py
git commit -m "fix: make wallet registration retry safe"
```

### Task 3: Persist reconciliation attempts and truthful failure states

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Modify: `lib/types.ts`
- Modify: `lib/job-presentation.ts`
- Test: `tests/backend/test_store_and_demo_roles.py`
- Test: `tests/frontend/job-presentation.test.ts`

**Interfaces:**
- Produces registry fields: `reconcile_state`, `reconcile_attempted_at`, `reconcile_error_code`, `reconcile_age_seconds`.
- Produces UI states: `SUBMITTED`, `ACCEPTED_NOT_FINALIZED`, `FINALIZED`, `FAILED`, `CANCELLED`, `RECOVERY_REQUIRED`.

- [ ] **Step 1: Add failing truthfulness tests**

Assert that a missing settlement hash renders `RECOVERY_REQUIRED`, a cancelled hash renders `CANCELLED`, an accepted non-final hash renders `ACCEPTED_NOT_FINALIZED`, and stale backend data keeps the last verified lifecycle state with `stale: true`.

- [ ] **Step 2: Run the focused suites**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py -k reconcile && npm test -- --run tests/frontend/job-presentation.test.ts`

Expected: FAIL because reconciliation metadata is absent.

- [ ] **Step 3: Implement bounded reconciliation metadata**

Update only non-final jobs, save the last attempt timestamp, classify SDK/network errors into stable public codes, clear error fields after success, and calculate age from persisted timestamps. Do not replace a verified snapshot when a read fails.

- [ ] **Step 4: Replace generic indefinite copy**

Update presentation logic so every pending state includes the known transaction link, elapsed context, and a specific action: refresh, reconnect correct wallet, recover by hash, or wait for finality.

- [ ] **Step 5: Run tests and commit**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py && npm test -- --run tests/frontend/job-presentation.test.ts tests/frontend/settlement.test.ts`

```bash
git add dashboard/store.py dashboard/api.py lib/types.ts lib/job-presentation.ts tests/backend/test_store_and_demo_roles.py tests/frontend/job-presentation.test.ts
git commit -m "feat: expose truthful reconciliation states"
```

### Task 4: Add structured operational telemetry

**Files:**
- Create: `dashboard/telemetry.py`
- Modify: `dashboard/api.py`
- Modify: `render.yaml`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `log_event(name: str, **fields: Any) -> None`
- Produces: `/api/health` fields `release`, `registry`, `reconciler`, `oldest_pending_seconds`, `last_reconcile_at`.

- [ ] **Step 1: Write a failing secret-redaction test**

```python
def test_log_event_redacts_secret_fields(caplog):
    log_event("wallet_error", private_key="secret", authorization="Bearer secret", job="0xjob")
    assert "secret" not in caplog.text
    assert "0xjob" in caplog.text
```

- [ ] **Step 2: Run it and confirm failure**

Run: `pytest -q tests/backend/test_store_and_demo_roles.py -k redacts`

- [ ] **Step 3: Implement JSON logs and health evidence**

Whitelist safe field names, hash or omit unexpected values, add request latency middleware, and expose the Git release through `MERIT_RELEASE`. Emit events for registry writes, reconciliation outcomes, Bradbury failures, and settlement verification.

- [ ] **Step 4: Run backend verification**

Run: `python -m py_compile dashboard/api.py dashboard/store.py dashboard/telemetry.py && pytest -q tests/backend`

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add dashboard/telemetry.py dashboard/api.py render.yaml tests/backend/test_store_and_demo_roles.py
git commit -m "feat: add safe escrow observability"
```

### Task 5: Add a live custody matrix runner

**Files:**
- Create: `scripts/custody_matrix.py`
- Create: `tests/live/README.md`
- Modify: `DEMO_SCRIPT.md`

**Interfaces:**
- Consumes: public Render API, Bradbury RPC, two funded test wallets supplied only through environment variables.
- Produces: JSON evidence containing job address, transaction hashes, state transitions, starting/ending balances, and recipient deltas.

- [ ] **Step 1: Implement `--dry-run` validation**

Require `MERIT_API_URL`, `BRADBURY_RPC_URL`, `CLIENT_PRIVATE_KEY`, and `WORKER_PRIVATE_KEY`; print only wallet addresses and fail if they match or are unfunded. Never print the key values.

- [ ] **Step 2: Implement Direct Hire scenarios**

Run deploy → fund → accept → submit → evaluate for fixtures producing full, split, and refund results. Assert finalized transaction evidence and exact recipient balance deltas after fees.

- [ ] **Step 3: Implement Bounty scenarios**

Submit two entries from separate wallets, close the round, evaluate, and assert only the recorded qualifying winner receives the transfer; add the below-threshold refund case.

- [ ] **Step 4: Add interruption and replay checks**

Stop local polling after evaluation/settlement submission, wait through the backend, reload from the registry, and replay registration calls to prove background progress and idempotency.

- [ ] **Step 5: Run the reliability gate and commit**

Run: `python scripts/custody_matrix.py --dry-run`

Run with funded test-only credentials: `python scripts/custody_matrix.py --output /tmp/merit-custody-evidence.json`

Expected: all scenarios report `verified: true`; balance deltas equal contract evidence.

```bash
git add scripts/custody_matrix.py tests/live/README.md DEMO_SCRIPT.md
git commit -m "test: add Bradbury custody matrix"
```

