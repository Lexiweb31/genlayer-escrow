# Merit

**AI-arbitrated freelance escrow on GenLayer’s Bradbury testnet.**

Merit combines a Next.js product interface, a trusted Render demo API, durable marketplace data, and GenLayer intelligent contracts. A plain-English acceptance specification becomes an inspectable evaluation and a full payout, proportional split, or refund path.

[Live Next.js application](https://genlayer-escrow.vercel.app/) · [Bradbury explorer](https://explorer-bradbury.genlayer.com) · [Demo script](DEMO_SCRIPT.md)

## Trust model

The current competition experience is a **server-signed, testnet-only demo**. It does not connect a visitor’s browser wallet, and visitors do not personally control deposited GEN.

- Render owns `DEMO_CLIENT_PRIVATE_KEY` and `DEMO_WORKER_PRIVATE_KEY`.
- The two keys must derive to different addresses.
- The demo client signs deploy, fund, evaluate, appeal, and finalize actions.
- The demo worker signs accept and submit actions.
- If both roles are not configured safely, live actions are disabled. The frontend never invents an on-chain transaction.
- Contracts deployed before the safe EOA transfer patch remain visibly read-only: **legacy settlement contract — do not fund**.

The browser receives public role addresses and transaction evidence only. Private keys, database paths, and server signer configuration must never use a `NEXT_PUBLIC_` name.

## Frontend architecture

The production frontend uses Next.js, TypeScript, and the App Router. It is a normal Vercel deployment—not a static export and not a GitHub Pages application.

Real routes:

- `/` — homepage and animated escrow explainer;
- `/jobs` — durable marketplace, filters, and distinct locked/pending/finalized totals;
- `/jobs/new` — guided agreement creation;
- `/jobs/[id]` — escrow overview;
- `/jobs/[id]/manage` — role-gated lifecycle actions;
- `/jobs/[id]/evaluation` — confirmed evaluation evidence;
- `/contracts` and `/jobs/[id]/contracts` — infrastructure and deployed addresses.

Reusable components live in `components/`. Typed Render API calls live in `lib/api.ts`. Exact GEN/wei conversion and finality-aware settlement mapping live in `lib/amount.ts` and `lib/settlement.ts`.

## Safe settlement language

Merit separates the contract decision from transfer finality:

```text
Submitted → Evaluated → Settlement queued → Transfer finalized
```

`ACCEPTED`, `PARTIAL`, and `REFUNDED` may be recorded decisions, but the UI continues to show **Settlement pending** until the backend verifies the outbound external-message transfer. Pending and finalized views expose recipients, exact GEN amounts, parent transaction references, and Bradbury explorer links.

## Local frontend setup

Requirements: Node.js 20.9 or newer and npm.

```bash
npm install
cp .env.example .env.local
npm run dev
```

Configure these browser-safe values in `.env.local`:

```bash
NEXT_PUBLIC_API_BASE_URL=http://localhost:8000
NEXT_PUBLIC_GENLAYER_NETWORK=testnet_bradbury
NEXT_PUBLIC_EXPLORER_BASE_URL=https://explorer-bradbury.genlayer.com
```

Open `http://localhost:3000`. Never place private keys or Render secrets in `.env.local` or any `NEXT_PUBLIC_` variable.

## Local Render API setup

The Python API remains the trusted signer and persistence owner:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export DEMO_CLIENT_PRIVATE_KEY=your_local_testnet_demo_client_key
export DEMO_WORKER_PRIVATE_KEY=your_different_local_testnet_demo_worker_key
export PERSIST_DATA_DIR=.data
uvicorn dashboard.api:app --reload
```

Use testnet-only keys and never commit them. When the keys are absent, the API starts with live multi-role actions disabled.

## Vercel deployment

Create or link a Vercel project from this repository and configure these public environment variable names for Production and Preview:

- `NEXT_PUBLIC_API_BASE_URL`
- `NEXT_PUBLIC_GENLAYER_NETWORK`
- `NEXT_PUBLIC_EXPLORER_BASE_URL`

Set `NEXT_PUBLIC_API_BASE_URL` to the Render service origin, without a trailing slash. Vercel automatically detects Next.js; `vercel.json` declares the framework and does not define a static output directory.

Before deployment:

```bash
npm run lint
npm run typecheck
npm test
npm run build
```

## Render environment ownership

Only Render receives server secrets and durable-storage configuration:

- `DEMO_CLIENT_PRIVATE_KEY`
- `DEMO_WORKER_PRIVATE_KEY`
- `PERSIST_DATA_DIR`

On Render, attach a persistent disk and point `PERSIST_DATA_DIR` to its mount, currently `/var/data/merit`. Jobs are stored in SQLite so all browsers see the same registry and redeploys do not discard jobs when the disk is configured.

## Wallet-mode roadmap

The interface explicitly distinguishes two architectures:

- **Demo mode:** available now; separate server-held Bradbury accounts sign transactions; testnet-only; not visitor custody.
- **Wallet mode:** disabled and labelled **Coming soon — connect a Bradbury wallet**.

Wallet mode must remain disabled until browser wallet support, contract-side caller/role behavior, chain/network checks, transaction status recovery, and end-to-end custody tests are implemented. Enabling a connect button alone is not sufficient.

## Backend and contract verification

```bash
python3 -m pytest tests/direct -q
python3 -m pytest tests/backend -q
python3 -m py_compile dashboard/api.py dashboard/store.py scripts/*.py
genvm-lint contracts/freelance_escrow.py
```

GenLayer executes external messages only when their parent transaction finalizes. See the official [value-transfer](https://docs.genlayer.com/developers/intelligent-contracts/features/value-transfers) and [message](https://docs.genlayer.com/developers/intelligent-contracts/features/messages) documentation.

## License

Built as an open competition prototype for GenLayer’s Bradbury testnet.
