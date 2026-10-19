# Merit — GenLayer Project Submission

## One-line description

Merit is a freelance escrow marketplace where GenLayer validators inspect public work against the agreement before the contract releases, splits, or refunds GEN.

## The problem

An ordinary escrow contract can hold money, but it cannot determine whether a website, report, design, or other public deliverable actually satisfies a natural-language agreement. Traditional platforms resolve that question through a private human decision. The client must trust the platform, the worker cannot independently inspect the decision process, and the payment rule is often unclear until a dispute occurs.

## How Merit solves it

1. A client writes observable acceptance requirements and assigns a separate worker wallet.
2. A dedicated intelligent escrow is deployed on Bradbury and funded with testnet GEN.
3. The assigned worker accepts the requirements and submits a public deliverable URL.
4. GenLayer validators retrieve the public evidence, treat its contents as untrusted data, and compare it with the original agreement.
5. Validator consensus records a score and explanation.
6. The immutable thresholds select full payment, a proportional split, or a client refund.
7. Merit reports payment as confirmed only after it can verify the outbound transaction evidence.

## Why GenLayer is essential

The core decision is contextual rather than numerical. A deterministic smart contract cannot open an arbitrary public deliverable and judge whether it satisfies natural-language requirements. GenLayer supplies web access, model-based reasoning, and decentralized equivalence consensus for this non-deterministic operation. Removing GenLayer would remove the product's trust-minimizing evaluator and reduce Merit to a conventional escrow controlled by a private oracle.

## What judges can verify

- Live application: https://genlayer-escrow.vercel.app/
- Public source code: https://github.com/Lexiweb31/genlayer-escrow
- Network: GenLayer Bradbury testnet
- Contract source: `contracts/freelance_escrow.py`
- Standalone evaluation example: `contracts/evaluate_submission.py`
- Direct contract tests: `tests/direct/`
- Backend lifecycle and persistence tests: `tests/backend/`
- Frontend trust-boundary tests: `tests/frontend/`

The Contracts screens expose registered escrow addresses, deployment transactions, role addresses, network information, and settlement evidence. Bradbury explorer links are available from the interface.

## Recommended live demonstration

Use two different Bradbury wallets in separate browser profiles.

1. Connect the client wallet and create a job with a different worker address.
2. Fund the escrow with the displayed minimum testnet amount.
3. Open the same marketplace from the worker browser and accept the requirements.
4. Submit a stable, public HTTPS deliverable.
5. Return to the client wallet and request AI evaluation.
6. Leave the evaluation screen and return later to demonstrate that processing is not tied to an open tab.
7. Inspect the confirmed score and reasoning.
8. Submit settlement and show the separate processing and confirmed-payment states.

Demo Mode is available as a labelled fallback. It uses two separate server-held Bradbury accounts and never claims that the visitor controls its funds.

## Safety and honesty boundaries

- Client and worker roles must use different addresses.
- Wallet Mode never silently falls back to a server signer.
- Private signer keys remain on Render and are never exposed to Vercel or the browser.
- Public deliverables are explicitly treated as untrusted evidence to reduce prompt-injection risk.
- Failed reads produce retryable error states; the interface does not manufacture contract data.
- Evaluation decisions and payment finality are tracked separately.
- A missing settlement transaction reference is shown as unverified, never confirmed.
- Legacy contracts with unsafe settlement behavior remain visible but read-only.

## Architecture

- Next.js App Router frontend and server-only API proxy on Vercel.
- Python FastAPI service on Render for demo signing, verified contract reads, and registry persistence.
- SQLite registry on a Render persistent disk, shared across browsers.
- Periodic server-side reconciliation of registered contracts so evaluation and settlement state recover without an open browser.
- GenLayer intelligent contracts for agreement state, web evaluation, appeal, and settlement decisions.

## Current scope

Merit is a Bradbury testnet application. It does not claim mainnet readiness, production custody, perfect model judgment, or completed payment without verifiable transaction evidence. The next development milestones are independent security review, wider wallet compatibility testing, richer evaluator provenance, and pilot use with real freelance communities.

## Continued-development path

- Run structured tests with independent client and worker participants.
- Publish a short end-to-end demonstration video and explorer-backed transaction report.
- Add milestone-based jobs and multi-deliverable agreements.
- Add opt-in email or push notifications for role-specific actions.
- Measure settlement completion time and evaluator consistency across real job categories.
- Prepare a security and economic review before any mainnet deployment.
