# Merit Cinematic Trust Upgrade Design

**Date:** 2026-08-10  
**Status:** Approved design direction; pending user review of this written specification  
**Product:** Merit intelligent escrow on GenLayer Bradbury

## 1. Outcome

Upgrade Merit into a production-oriented intelligent escrow product that is simultaneously:

1. visually distinctive enough to present as a leading GenLayer application;
2. reliable enough for real wallet users to trust funding and settlement;
3. faster and calmer during slow or asynchronous blockchain operations; and
4. useful after the initial submission through stronger marketplace discovery and wallet-based history.

The approved visual direction is **Cinematic Trust**: an atmospheric, motion-led marketing surface that transitions into a precise, evidence-led application workspace.

## 2. Safety boundary

The redesign must not invalidate or mutate existing user work. The following are frozen unless a separate contract migration is explicitly designed and approved:

- deployed intelligent contract addresses and current contract storage;
- Direct Hire and Bounty lifecycle rules;
- ABI method names, parameters, and wallet role authorization;
- existing API response fields consumed by the frontend;
- persistent job registry records, transaction references, evidence URLs, and settlement results;
- existing public job routes and evidence links; and
- server-only secrets and signer boundaries.

No UI state may claim that a wallet action, contract state, evaluation, payout, or refund is confirmed without verifiable backend or Bradbury evidence.

## 3. Design approaches considered

### A. Cinematic Trust — selected

Use ambient GenLayer-inspired motion, deep navy space, luminous consensus orbits, and one frosted agreement composer on the homepage. Remove ambient media inside transactional workflows and use opaque, high-contrast panels for job workspaces.

This provides the strongest balance of memorability, trust, readability, and performance.

### B. Live Command Center

Lead with marketplace metrics and lifecycle activity. This is credible and product-forward but visually dense and less emotionally memorable.

### C. Clear Trust Ledger

Use a minimal light-first ledger aesthetic. This is the safest accessibility direction but does not provide the distinctive atmosphere requested for the submission.

## 4. Visual system

### 4.1 Homepage

The homepage becomes a cinematic product introduction rather than a generic dashboard preview.

- Headline: **“Define the work. Let consensus settle it.”**
- Supporting copy explains protected digital work, independent AI evaluation, and inspectable settlement.
- The primary interactive element is an **agreement composer**, adapted from the reference prompt card. It describes an outcome rather than a trip.
- The composer offers Direct Hire and Bounty choices and sends the user into the existing protected-job creation flow.
- Navigation emphasizes How it works, Marketplace, Security, Contracts, and Open app.
- A lower proof section demonstrates the four real stages: define, fund, verify, settle.
- Real contract evidence and a recorded transaction example replace invented vanity metrics.

The reference travel video, Wandor branding, travel copy, Special Elite wordmark, and external media URL are not reused.

### 4.2 Motion

Ambient motion is generated with lightweight CSS and SVG layers representing validators, agreement boundaries, and settlement paths. It must:

- lazy-load after essential content;
- stop when the page is not visible;
- respect `prefers-reduced-motion`;
- avoid blocking navigation or primary actions;
- use no autoplay audio; and
- remain absent from transaction-heavy job pages.

### 4.3 Typography and color

- Keep self-hosted Manrope for interface and marketing copy to avoid a new external font dependency.
- Keep DM Mono for addresses, transaction states, network evidence, and technical labels.
- Preserve Merit’s deep navy base, cobalt action color, emerald confirmation, amber pending, and red failure semantics.
- Glass is reserved for the homepage composer and limited marketing accents. Transaction panels remain sufficiently opaque in dark and light themes.

### 4.4 Product workspace

Existing application pages are restyled, not restructured around invented functionality.

- Maintain distinct client, worker, Bounty entrant, visitor, demo, and judge views.
- Keep the current sidebar and route model, with improved visual hierarchy and responsive behavior.
- Promote the verified current state and the single available next action.
- Place transaction evidence, recipient, amount, and explorer links near settlement states.
- Keep technical detail collapsible but accessible.
- Avoid oversized empty canvases and decorative motion that competes with wallet actions.

## 5. Reliability upgrade

### 5.1 End-to-end wallet custody matrix

Build an automated test harness covering the complete Bradbury lifecycle for both Direct Hire and Bounty:

- deployment and durable registration;
- funding and locked-balance verification;
- worker acceptance or Bounty entry submission;
- public evidence submission;
- GenLayer evaluation and confirmed result retrieval;
- full payment, split payment, and refund;
- final wallet balance deltas and recipient verification;
- refresh, tab close, and browser return during pending operations;
- rejected, cancelled, failed, and missing-reference transactions; and
- orphaned deployment or settlement recovery without duplicate writes.

Tests must assert contract state and transfer evidence, not only visible labels.

### 5.2 Idempotent transaction recording

Every deployment and settlement registration endpoint must be safe to retry with the same verified transaction hash. Duplicate UI clicks or network retries must never create duplicate jobs or settlement records.

### 5.3 Background reconciliation

Pending evaluations and settlements must continue independently of an open browser tab. The backend reconciler owns shared recovery; frontend polling only presents current state.

The UI must show:

- transaction submitted;
- accepted but not finalized;
- finalized and verified;
- failed or cancelled; or
- missing transaction reference requiring recovery.

It must not show indefinite generic “processing” language without a transaction link, elapsed context, and recovery action.

### 5.4 Observability

Add structured logs and safe operational metrics for API latency, Bradbury read failures, reconciliation age, settlement failures, registry persistence, and deployment version. Never log private keys or secret environment values.

## 6. Performance upgrade

### 6.1 Read strategy

- Serve durable registry snapshots immediately for list and completed-job views.
- Reconcile only active, unknown, or pending jobs against Bradbury.
- Deduplicate concurrent reads for the same contract.
- Bound chain-read concurrency and use timeouts with explicit degraded states.
- Cache immutable finalized evidence longer than active state.

### 6.2 Frontend behavior

- Preserve route-level loading states and stale data while background refresh runs.
- Poll only when a job can still change.
- Pause polling in hidden tabs and refresh when visibility returns.
- Dynamically load marketing motion and wallet-heavy libraries only where needed.
- Keep the homepage’s essential text and calls to action server-rendered.

### 6.3 Performance budgets

On a normal production connection:

- homepage meaningful content should appear within 2 seconds;
- cached marketplace and finalized job responses should target sub-second server response;
- primary pages must remain usable before ambient motion loads;
- no horizontal overflow at 390px; and
- no layout shift from fonts, video, wallet controls, or notification badges.

## 7. Marketplace functionality upgrade

### 7.1 Discovery

Add URL-backed search and filters for job type, lifecycle state, reward range, and open participation. Filters must work on mobile and remain shareable through query parameters.

### 7.2 Wallet activity and reputation

Provide a wallet-scoped activity page derived only from verified Merit records:

- jobs created;
- work accepted or Bounty entries submitted;
- evaluations completed;
- confirmed payouts and refunds; and
- completion and qualification history.

This is verifiable history, not an arbitrary star rating. Visitors must not see another wallet’s private notifications.

### 7.3 Persistent role-scoped notifications

Move critical notification state from browser-only storage to the backend registry. Notifications are derived from verified state transitions and scoped to the connected wallet’s role.

Priority events include funding confirmed, job accepted, work submitted, Bounty round closed, evaluation confirmed, settlement submitted, payout/refund confirmed, transaction failed, and recovery required.

### 7.4 Drafts and requirement templates

Allow users to save a protected-job draft before deploying. Provide templates for landing pages, audits, research briefs, and content packages. Templates populate editable acceptance criteria and never bypass final user review.

## 8. Architecture and data flow

1. Next.js renders marketing and application routes.
2. Wallet writes continue through the connected Bradbury wallet and existing GenLayerJS boundary.
3. The Render API validates confirmed transactions, owns the durable marketplace registry, and exposes role-safe views.
4. Intelligent contracts remain the source of truth for lifecycle and settlement.
5. The background reconciler updates pending registry records from Bradbury.
6. The frontend reads fast snapshots, then refreshes only mutable states.
7. Notifications and wallet activity are derived from verified registry transitions.

The marketing redesign does not sit in the transaction path.

## 9. Error handling

- Network errors retain the last verified state and clearly mark it as stale.
- Wrong-network and wrong-role actions are blocked before a wallet signature request.
- Rejected wallet prompts return the user to an actionable idle state.
- Confirmed transactions that fail durable registration expose a recovery path using the same hash.
- Failed or cancelled transactions never display success language.
- Unavailable Render or Bradbury services show component-specific recovery guidance instead of a generic broken page.

## 10. Verification and rollout

Implementation occurs on a separate branch and is released in four gates:

1. **Reliability gate:** custody matrix, idempotency, reconciliation, and observability.
2. **Performance gate:** snapshot reads, conditional polling, code splitting, and budgets.
3. **Functionality gate:** discovery, wallet activity, notifications, and drafts.
4. **Visual gate:** Cinematic Trust homepage and restrained workspace restyle.

Before production deployment:

- frontend unit and regression tests pass;
- Python contract and backend tests pass;
- production Next.js build passes;
- desktop and 390px mobile flows are visually checked in both themes;
- Direct Hire and Bounty wallet lifecycles complete on Bradbury;
- current production job URLs still resolve; and
- a Vercel preview is reviewed before promotion.

## 11. Success criteria

The upgrade is successful when:

- existing jobs and settlement records remain intact;
- no user needs Codex or a manual backend intervention for a normal lifecycle;
- every pending state identifies its transaction or explains why no reference exists;
- returning users see the latest shared state without keeping a tab open;
- marketplace browsing is meaningfully faster and filterable;
- wallet users see only their relevant actions and notifications;
- the homepage communicates Merit’s purpose in one screen; and
- visual polish never weakens evidence, accessibility, or transaction truthfulness.
