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

The browser receives public role addresses and transaction evidence only. Private keys, environment values, database paths, and server signer configuration are never bundled into browser code or returned by the Next.js API layer.

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

Reusable components live in `components/`. The browser-side typed client in `lib/api.ts` calls only same-origin `/api/...` routes. Those allowlisted Next.js Route Handlers call Render from the server, remove private diagnostic/configuration fields, verify the configured network, and rewrite explorer references to same-origin redirects. Exact GEN/wei conversion and finality-aware settlement mapping live in `lib/amount.ts` and `lib/settlement.ts`.

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

Configure the Next.js server connection in `.env.local`:

```bash
RENDER_API_BASE_URL=http://127.0.0.1:8000
GENLAYER_NETWORK=testnet_bradbury
GENLAYER_EXPLORER_BASE_URL=https://explorer-bradbury.genlayer.com
```

Open `http://localhost:3000`. These values are read only by Next.js server routes. Never place signer keys, database credentials, or other Render secrets in the frontend project’s `.env.local`.

## Local Render API setup

The Python API remains the trusted signer and persistence owner:

```bash
python3 -m venv .venv
. .venv/bin/activate
pip install -r requirements.txt
export PERSIST_DATA_DIR=.data
uvicorn dashboard.api:app --reload
```

Do not copy production signer keys into the frontend or local environment. Without the Render-owned demo keys, the local API starts with live multi-role actions disabled and the interface remains an honest simulated walkthrough.

## Vercel deployment

Create or link a Vercel project from this repository and configure these **server-only** environment variable names for Production and Preview:

- `RENDER_API_BASE_URL`
- `GENLAYER_NETWORK`
- `GENLAYER_EXPLORER_BASE_URL`

Set `RENDER_API_BASE_URL` to the Render service origin, without a trailing slash. The browser never receives this value and never calls Render directly. `GENLAYER_NETWORK` is used server-side to reject an unexpected backend network. Explorer links first open a same-origin validation route, which redirects to the server-configured explorer. Vercel automatically detects Next.js; `vercel.json` declares the framework and does not define a static output directory.

The Next.js API boundary deliberately:

- allows only the Merit job/demo endpoints and methods used by the interface;
- accepts JSON-only same-origin mutations with bounded request sizes;
- forwards no browser cookies, authorization headers, or arbitrary headers to Render;
- returns no raw backend exception details or private configuration fields;
- disables caching and bounds upstream response sizes;
- never acts as a user-selectable or open proxy.

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

Signer keys and any future database credentials remain solely in Render environment variables. They must not be added to Vercel, browser code, API responses, or committed environment files.

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
