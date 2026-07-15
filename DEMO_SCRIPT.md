# Merit — three-minute competition demo

## Before presenting

- Open the [live app](https://lexiweb31.github.io/genlayer-escrow/).
- Confirm the Bradbury network badge loads.
- Press `Cmd/Ctrl + J` and keep Judge Mode ready.
- Keep the GitHub repository and Bradbury explorer in background tabs.
- If services are slow for eight seconds, use **Enter resilient demo**. Say explicitly that it is labeled fallback data.

## 0:00–0:30 — the problem

> Freelance escrow can hold money, but it still cannot understand whether the work was actually completed. That decision usually returns to a centralized platform employee. Merit replaces that private judgment with an inspectable intelligent contract.

Show the animated escrow lifecycle and the “living protocol” telemetry.

## 0:30–1:10 — create enforceable terms

Open **Post a Job**. Apply the landing-page template.

> The client defines “done” before work begins. Merit checks whether the agreement is clear and testable, previews all payout bands, and fingerprints the exact terms. Those terms become the validator rubric and settlement rules.

Point out:

- agreement-quality score;
- full-payment and partial-payment thresholds;
- payout preview;
- SHA-256 terms fingerprint.

## 1:10–1:35 — show the marketplace

Open **Browse Jobs** and select a funded or completed listing.

> Every listing maps to a dedicated escrow contract. Merit does not custody marketplace funds.

Briefly show search, status filtering, saved jobs, and the contract-backed job timeline.

## 1:35–2:30 — reveal the technical core

Open **AI Evaluation**.

> GenLayer validators retrieve the submitted public page, isolate it as untrusted evidence, evaluate it against the exact agreement, and reach consensus. A normal smart contract cannot perform this judgment.

Show:

- fetch → sandbox → evaluate → consensus → settle pipeline;
- validator score spread;
- final rationale;
- decision evidence room;
- security checks;
- deliverable provenance;
- settlement split or refund;
- appeal path.

Do not describe score-derived rubric signals as independent on-chain scores. The UI labels them as explanatory signals.

## 2:30–2:50 — prove settlement

Open **Contracts** or the explorer.

> The final score does not merely produce a dashboard result. It controls an actual contract transfer: full payment, proportional settlement, or refund.

Show the job contract, evaluation engine, network, and explorer links.

## 2:50–3:00 — close

> Merit gives digital work something it has never had on-chain: an agreement that can understand evidence, explain its decision, and enforce payment without a private arbitrator.

Finish on the evidence report or settlement receipt.

## Likely judge questions

### Why not use a normal oracle?

A normal oracle returns structured facts. Merit requires contextual judgment: reading an arbitrary deliverable and comparing it with natural-language requirements. GenLayer provides web access, LLM execution, and decentralized equivalence consensus for that non-deterministic operation.

### Can the submitted page prompt-inject the evaluator?

The fetched page is explicitly treated as untrusted evidence and isolated from evaluator instructions. The interface surfaces that security boundary, and the contract prompt is inspectable in the repository.

### What if validators are wrong?

The result includes reasoning and supports an appeal before final settlement. The project demonstrates the appeal path without claiming a single model is infallible.

### Is the fallback fake blockchain activity?

No. Fallback state is visibly labeled, and all chain-mutating actions are blocked. It exists only to protect the presentation journey during network downtime.

### What is the business model?

Merit can charge the declared settlement fee on successful worker payouts. The fee is shown before deployment and encoded into the job configuration.
