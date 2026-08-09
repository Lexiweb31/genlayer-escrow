# Merit Cinematic Trust Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Ship Merit’s approved reliability, performance, marketplace, and Cinematic Trust upgrades without changing deployed contract behavior or invalidating existing jobs.

**Architecture:** Four independently releasable plans are executed in order. The Render registry remains the fast shared read model, Bradbury contracts remain the lifecycle source of truth, connected wallets remain the write authority, and Next.js remains the same-origin frontend/API boundary.

**Tech Stack:** Next.js 16, React 19, TypeScript 5.9, Vitest, FastAPI, SQLite, pytest, GenLayerJS, GenLayer Python SDK.

## Global Constraints

- Do not change deployed intelligent contract addresses, storage layout, lifecycle methods, authorization, or settlement math.
- Preserve Direct Hire and Bounty behavior and every existing public job URL.
- Preserve existing API response fields; additions must be backward compatible.
- Never expose Render signer keys, server environment variables, or secret values to browser code or validator input.
- Never display a confirmed evaluation, payment, payout, or refund without verified backend and Bradbury evidence.
- Keep self-hosted Manrope and DM Mono; add no externally hosted font.
- Respect `prefers-reduced-motion`; use no autoplay audio.
- Preserve both dark and light themes and prevent horizontal overflow at 390px.
- Run each release gate against Direct Hire and Bounty before starting the next phase.

---

## Plan map

1. [Reliability and custody](./2026-08-10-merit-reliability-and-custody.md)
2. [Performance and reconciliation](./2026-08-10-merit-performance-and-reconciliation.md)
3. [Marketplace product functionality](./2026-08-10-merit-marketplace-functionality.md)
4. [Cinematic Trust visual system](./2026-08-10-merit-cinematic-trust-visual.md)

## Specification coverage

| Approved requirement | Owning plan and task |
| --- | --- |
| Frozen contracts, storage, roles, routes, API compatibility | Global constraints in every plan; final production acceptance |
| Full Direct Hire and Bounty custody evidence | Reliability Tasks 1–5 |
| Retry-safe deployment and settlement registration | Reliability Tasks 1–2 |
| Background recovery and truthful pending/failure states | Reliability Tasks 3–4 |
| Safe logs, latency, reconciliation age, release evidence | Reliability Task 4 |
| Snapshot-first reads, immutable caching, read deduplication | Performance Tasks 1–2 |
| Visibility-aware polling and stale-data retention | Performance Task 3 |
| Motion/wallet code splitting and response budgets | Performance Tasks 4–5 |
| Shareable discovery by type, state, reward, participation | Marketplace Task 1 |
| Verified wallet history without invented ratings | Marketplace Tasks 2–3 |
| Private persistent role notifications | Marketplace Tasks 2 and 4 |
| Drafts and editable requirement templates | Marketplace Tasks 2 and 5 |
| Cinematic homepage, composer, proof narrative | Visual Tasks 1–3 |
| Client/worker/entrant/visitor workspace hierarchy | Visual Task 4 |
| Dark/light, reduced motion, keyboard, 390px layout | Visual Task 5 |
| Preview-first deployment and preserved evidence links | Visual Task 6 and final production acceptance |

## Release discipline

- [ ] Create an isolated implementation worktree using `superpowers:using-git-worktrees` before editing application code.
- [ ] Record the production `main` commit, Vercel URL, Render health payload, and current job count in the Phase 1 test evidence.
- [ ] Complete and review each linked plan independently.
- [ ] Deploy each phase to a Vercel preview and a non-production Render service or guarded backend configuration.
- [ ] Promote only after its release gate passes; do not combine an unverified backend migration with the visual redesign.
- [ ] After Phase 4, run `npm test`, `npm run typecheck`, `npm run lint`, `npm run build`, `pytest -q`, desktop visual checks, 390px visual checks, and live Bradbury lifecycle checks.

## Final production acceptance

- [ ] Existing finalized job URLs load with their previously verified settlement evidence.
- [ ] A new Direct Hire completes full payout, split payout, and refund scenarios.
- [ ] A new Bounty accepts multiple entries, closes, evaluates, and settles the recorded winner or refunds the client.
- [ ] Closing the browser during evaluation or settlement does not stop reconciliation.
- [ ] Retrying a deployment or settlement registration hash cannot duplicate a record.
- [ ] Marketplace filters survive reload and link sharing.
- [ ] Client, worker, entrant, and visitor receive distinct actions and notifications.
- [ ] Homepage essential content renders before motion and remains usable with JavaScript motion disabled.
- [ ] Production Vercel and Render versions expose the same release identifier.
