# Merit — three-minute competition demo

## Before presenting

- Open the [live Next.js app](https://genlayer-escrow.vercel.app/).
- Confirm the Bradbury network badge loads.
- Press `Cmd/Ctrl + J` and keep Judge Mode ready.
- Keep the GitHub repository and Bradbury explorer in background tabs.
- If Render is waking up, use the visible retry state and explain that the shared registry remains authoritative.
- Use **Wallet Mode** for the primary demonstration: connect the client wallet on Bradbury, and keep a separate assigned worker wallet ready in another browser profile.
- Use Demo Mode only as a clearly labelled fallback. Confirm that its Contracts page shows different server-held client and worker addresses before attempting demo actions.

## 0:00–0:30 — the problem

> Freelance escrow can hold money, but it still cannot understand whether the work was actually completed. That decision usually returns to a centralized platform employee. Merit replaces that private judgment with an inspectable intelligent contract.

Show the animated escrow lifecycle and the “living protocol” telemetry.

## 0:30–1:10 — create enforceable terms

Open **Post a Job**. Apply the landing-page template.

> The client defines “done” before work begins. Merit checks whether the agreement is clear and testable and previews every settlement band. Those terms become the validator rubric and settlement rules encoded in the escrow.

Point out:

- agreement-quality score;
- full-payment and partial-payment thresholds;
- deterministic payout thresholds;
- connected-wallet deployment and transaction status.

## 1:10–1:35 — show the marketplace

Open **Browse Jobs** and select a funded or completed listing.

> Every live listing maps to a dedicated escrow contract. The contract separates the client actions from the assigned worker actions, and the shared registry makes the same job visible across browsers.

Briefly show search, status filtering, precise GEN values, and the contract-backed job timeline.

## 1:35–2:30 — reveal the technical core

Open **AI Evaluation**.

> GenLayer validators retrieve the submitted public page, isolate it as untrusted evidence, evaluate it against the exact agreement, and reach consensus. A normal smart contract cannot perform this judgment.

Show:

- immutable agreement, public submission, and threshold evidence;
- backend-confirmed score and rationale;
- decision evidence room;
- security checks;
- deliverable provenance;
- settlement split or refund;
- appeal path.

Do not describe score-derived rubric signals as independent on-chain scores. The UI labels them as explanatory signals.

## 2:30–2:50 — prove settlement

Open **Contracts** or the explorer.

> The final score does not merely produce a dashboard result. It queues native GEN external messages: worker payout, proportional split, or client refund. Merit reports completion only after the parent transaction finalizes and an outbound transfer reference is inspectable.

Show the job contract, distinct demo signers, settlement status, recipient, amount, transfer reference, and explorer link. For a pending record, say “pending finalization,” not “paid” or “refunded.”

## 2:50–3:00 — close

> Merit turns a plain-language agreement into inspectable evaluation and score-based settlement on GenLayer. Wallet Mode gives the client and worker control of their Bradbury actions; Demo Mode remains an explicitly labelled testnet fallback.

Finish on the evidence report or settlement receipt.

## Likely judge questions

### Why not use a normal oracle?

A normal oracle returns structured facts. Merit requires contextual judgment: reading an arbitrary deliverable and comparing it with natural-language requirements. GenLayer provides web access, LLM execution, and decentralized equivalence consensus for that non-deterministic operation.

### Can the submitted page prompt-inject the evaluator?

The fetched page is explicitly treated as untrusted evidence and isolated from evaluator instructions. The interface surfaces that security boundary, and the contract prompt is inspectable in the repository.

### What if validators are wrong?

The result includes reasoning and supports an appeal before final settlement. The project demonstrates the appeal path without claiming a single model is infallible.

### Does the interface fake blockchain activity when services are unavailable?

No. Failed reads show loading/error/retry states, and disabled live actions never manufacture a transaction or result.

### What is the business model?

Merit can charge the declared settlement fee on successful worker payouts. The fee is shown before deployment and encoded into the job configuration.
