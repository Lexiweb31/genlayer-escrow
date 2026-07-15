# Merit

**AI-arbitrated freelance escrow on GenLayer’s Bradbury testnet.**

Merit turns a plain-English acceptance specification into settlement rules. GenLayer validators inspect a public deliverable and record a score; the escrow then queues a full worker payout, proportional split, or client refund.

[Live application](https://lexiweb31.github.io/genlayer-escrow/) · [Bradbury explorer](https://explorer-bradbury.genlayer.com) · [Demo script](DEMO_SCRIPT.md)

## Trust model — read before funding

The competition interface is a **server-signed, testnet-only demo**. It does not connect a visitor’s browser wallet, and visitors do not personally control deposited GEN.

- `DEMO_CLIENT_PRIVATE_KEY` signs only deploy, fund, evaluate, appeal, and finalize calls.
- `DEMO_WORKER_PRIVATE_KEY` signs only accept and submit calls.
- Both keys must be configured and must derive to different addresses. Otherwise all live actions are disabled and the UI offers a clearly labeled simulated walkthrough that never submits a transaction.
- Each newly created job rejects a client address that is also the worker address.
- Contracts deployed before the safe EOA transfer patch are marked **“legacy settlement contract — do not fund”** and remain read-only. Immutable deployed contracts are not silently migrated or deleted.

The demo server controls both testnet keys, so this is role separation—not real user custody. Browser-wallet signing must be implemented before describing Merit as user-wallet custody.

## Safe settlement

Native GEN payouts and refunds use GenLayer’s EOA external-message transfer pattern. The contract records the outcome and queued destinations before emitting transfers. Merit does not call a payout or refund complete merely because `finalize()` changed the parent contract state.

A settlement view exposes:

- outcome and settlement type;
- every recipient and amount;
- parent transaction and outbound transfer reference when available;
- `PENDING_FINALIZATION` until the parent transaction finalizes and an inspectable outbound message/triggered transaction is visible.

GenLayer executes external messages only when the parent transaction finalizes. See the official [value-transfer](https://docs.genlayer.com/developers/intelligent-contracts/features/value-transfers) and [message](https://docs.genlayer.com/developers/intelligent-contracts/features/messages) documentation.

## Settlement model

| Validator score | Queued outcome |
|---|---|
| Score ≥ full-payment threshold | Worker payout, less declared fee |
| Partial floor ≤ score < full-payment threshold | Proportional worker payout, client refund, and fee |
| Score < partial floor | Full client refund |

The client, worker, and platform cannot change these thresholds after deployment.

## Durable marketplace registry

The API stores marketplace records in SQLite instead of relying on `artifacts/jobs.json`. The schema includes the job address, terms, client and worker, lifecycle state, deployment transaction, settlement details, and timestamps. Every browser reads the same API-backed registry.

`PERSIST_DATA_DIR` selects the database directory:

- Local development: unset it to use `.data/`, or set an absolute/relative development path.
- Render production: upgrade the web service to a disk-compatible paid plan, attach a persistent disk in **Dashboard → Service → Disks**, use a mount such as `/var/data/merit`, and set `PERSIST_DATA_DIR=/var/data/merit`.

Only writes beneath the disk mount survive a Render restart or redeploy. Do not set a production `PERSIST_DATA_DIR` outside the attached mount. Existing `artifacts/jobs.json` entries, when present, are imported once as read-only legacy warnings; the source file is not rewritten or deleted.

## Required environment

```bash
DEMO_CLIENT_PRIVATE_KEY=0x...   # server secret; Bradbury testnet only
DEMO_WORKER_PRIVATE_KEY=0x...   # different server secret/address
PERSIST_DATA_DIR=/var/data/merit
```

Never expose either key to frontend code, logs, screenshots, commits, or browser environment variables. Fund only the demo client with the minimum Bradbury testnet GEN needed for the walkthrough.

`DEPLOYER_PRIVATE_KEY` is retained only for older integration tooling. The dashboard API no longer uses it for marketplace actions.

## Architecture

- `contracts/freelance_escrow.py` — role-gated lifecycle, intelligent evaluation, appeal, and EOA settlement messages.
- `dashboard/api.py` — distinct demo signers, role/state checks, testnet transaction submission, and transfer-status recovery.
- `dashboard/store.py` — shared SQLite marketplace and settlement registry.
- `docs/index.html` and `public/index.html` — identical static frontends.
- `tests/direct/` — contract behavior, including full payout, split, and refund cases.
- `tests/backend/` — durable storage, legacy import, and demo-role configuration checks.

## Run locally

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
uvicorn dashboard.api:app --reload
```

In a second terminal:

```bash
python3 -m http.server 8080 --directory docs
```

If the two demo keys are absent, the API starts safely with live actions disabled. Open `http://localhost:8080` to use the simulated walkthrough.

## Verification

```bash
python3 -m pytest tests/direct -q
python3 -m pytest tests/backend -q
python3 -m py_compile dashboard/api.py dashboard/store.py scripts/*.py
genvm-lint contracts/freelance_escrow.py
cmp -s docs/index.html public/index.html
```

Integration tests require a configured Bradbury/local validator environment and funded test accounts. The fallback demo is visibly labeled and cannot submit simulated chain activity.

## Competition UX

Merit includes Judge Mode, light/dark themes, an animated escrow explainer, agreement-quality guidance, marketplace search and filters, AI evaluation evidence, an interactive settlement simulator, a settlement receipt, deep links, mobile account access, bottom navigation, horizontally scrollable validator cards, and reduced-motion support.

## License

Built as an open competition prototype for GenLayer’s Bradbury testnet.
