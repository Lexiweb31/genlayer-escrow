# Task 5 — Custody Matrix Runner Report

## Delivered

- Added `scripts/custody_matrix.py`, a Bradbury testnet custody gate that is
  read-only by default and requires both `--execute` and
  `--confirm-testnet-custody` before it can send a transaction.
- Dry-run validates the required public API/RPC configuration and two distinct,
  funded role wallets. It emits only public addresses and never serializes or
  prints private key values.
- Live execution records JSON evidence for three Direct Hire outcomes (full,
  split, refund) and two Bounty outcomes (qualifying winner, below-threshold
  refund): job addresses, accepted transaction hashes, state transitions,
  public settlement records, starting/ending balances, recipient deltas, and
  settlement-registration replay evidence.
- Deployment and settlement are registered through the public Merit API.
  Following settlement submission, the runner waits for the durable registry
  to report finalized transfer evidence instead of locally polling chain state.
- Added `tests/live/README.md` and a Demo Script section with safe preflight,
  opt-in execution, required fixture/wallet inputs, and evidence interpretation.

## Verification

- Safety unit tests cover redacted dry-run evidence, duplicate-role rejection,
  unfunded-wallet rejection, and the explicit live-execution switch.
- `PYTEST_DISABLE_PLUGIN_AUTOLOAD=1 .venv/bin/python -m pytest -q tests/backend tests/live/test_custody_matrix.py`
- `npm test -- --run`
- `.venv/bin/python -m py_compile dashboard/api.py dashboard/store.py dashboard/telemetry.py scripts/*.py`
- `git diff --check`

## Operational constraints

- No live testnet transactions were sent during implementation: no funded
  test-only credentials were supplied.
- The Bounty contract requires two distinct non-client submitters, so a full
  matrix requires `BOUNTY_SECOND_WORKER_PRIVATE_KEY` in addition to the client
  and worker wallets required for dry-run. The runner validates all fixture
  URLs and all three wallets before its first deployment.
- The split/refund fixtures must be stable public pages that score below 100;
  an unexpected evaluator score causes verification to fail rather than being
  reclassified.
- A client refund recipient also signs `finalize`, so its raw balance movement
  includes that parent transaction fee. The evidence marks it as
  `fee_adjusted_recipient`; non-finalizer recipient deltas must match finalized
  transfer evidence exactly.

## Review follow-up

- The runner now proves the exact signing RPC reports immutable Bradbury chain
  ID `4221` before the SDK is created or a write can be broadcast.
- Lifecycle evidence now comes from asserted post-transaction contract reads,
  with each observed state tied to its transaction hash; no hard-coded state
  array remains.
- Settlement replay is now a gate: the second registration must return
  `replayed: true` for a scenario to verify.
- Timeouts are bounded to 1–3600 seconds. Live runs require an output path and
  atomically persist redacted incremental recovery evidence after every
  broadcast, including hashes available before receipt polling.
- Fixture URLs are parsed with `urlsplit` and reject malformed, credentialed,
  localhost, loopback, private, link-local, reserved, and unspecified hosts.
