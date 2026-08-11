# Merit Funding Activation Gate

**Date:** 2026-08-11  
**Status:** Approved design  
**Base release:** `c8f0da7`

## Problem

Clients can deploy a job and leave before funding it. The resulting `UNFUNDED` job looks more complete than it is, can appear alongside actionable work, and relies on the client remembering a later step. Testers then try to accept or submit work even though no protected payment exists.

Merit must treat funding as activation. A deployed but unfunded contract is a private client draft, not a live marketplace job.

## Goals

- Make the funding action the unavoidable continuation of job publishing.
- Keep unfunded jobs out of the public marketplace.
- Give the client a durable place to recover and fund an unfinished job.
- Prevent acceptance, submission, evaluation, or settlement before funding is confirmed.
- Represent wallet approval, Bradbury confirmation, failure, and retry truthfully.
- Preserve existing contracts, transaction verification, Direct Hire, Bounty, Demo, and Wallet modes.

## Non-goals

- Email, SMS, browser push, or third-party notification delivery.
- Automatically signing or funding without explicit wallet approval.
- Combining contract deployment and funding into one irreversible transaction.
- Changing deployed GenLayer contract interfaces.

## Considered Approaches

### 1. Reminder-only UI

Keep unfunded jobs public and add banners or notifications. This is the smallest change, but it does not prevent workers from encountering unusable jobs and still depends on memory. Rejected.

### 2. Hide unfunded jobs only

Remove unfunded jobs from Browse Jobs but leave the post-deployment navigation unchanged. This protects workers, but clients can still lose the funding step and have no obvious recovery queue. Rejected as incomplete.

### 3. Staged activation gate — selected

Deploy the contract, redirect immediately to funding, hide the job publicly until funding is verified, and place unfinished jobs in a client-only Needs funding queue. This adds a clear activation boundary without changing contract semantics.

## User Experience

### Publishing handoff

After contract deployment is confirmed, Merit routes the client directly to `/jobs/{id}/manage` with the funding action in focus. The page states:

> Your job is created but not active yet.

The only primary action is **Fund and activate job**. Secondary navigation remains available, but leaving the page does not make the job public.

### Client recovery

The Jobs screen has two client-visible groups:

- **Needs funding**: jobs owned by the connected client whose verified lifecycle state is `UNFUNDED`.
- **Live jobs**: funded marketplace jobs.

The Needs funding group is not shown to visitors or unrelated wallets. Each card shows the job title, contract address, creation time, funding status, and **Fund and activate** action.

When a connected client opens any page for their unfunded job, a persistent warning banner links back to the funding action. The notification bell contains a role-scoped item: **Fund your job to publish it**. It is derived from current job state rather than stored as a global notification, so other users never see it and it disappears after verified funding.

### Public and worker behavior

- Browse Jobs excludes `UNFUNDED` jobs.
- A visitor with a direct URL may see a non-actionable “This job is awaiting client funding” state, but no private client notification.
- The assigned worker sees “Waiting for protected payment” and cannot accept or submit.
- Bounty entrants cannot enter until the reward is funded and the contract is open.
- Evaluation and settlement controls remain unavailable before their existing valid lifecycle states.

## Funding State Model

The contract lifecycle remains authoritative. The UI derives the activation presentation from the job snapshot and the transaction journal:

1. `UNFUNDED` with no active funding transaction: **Funding required**.
2. Wallet request initiated but no hash returned: **Awaiting wallet approval**.
3. Transaction hash recorded and non-terminal: **Transaction submitted — confirming on Bradbury**.
4. Confirmed funding transaction plus contract state `OPEN`: **Job funded and publicly visible**.
5. Failed or cancelled transaction: **Funding failed** with the verified reason and a safe retry action.

Local loading state must never promote the job to funded. A transaction hash alone is not confirmation. Public visibility changes only when the shared backend snapshot verifies the funded contract state.

## Backend and Data Rules

- The public jobs endpoint excludes records whose verified lifecycle status is `UNFUNDED`.
- Client-owned job queries may include `UNFUNDED` records when the requester proves the matching wallet address or uses the existing isolated demo-client role.
- Existing job-detail endpoints continue returning an unfunded job by direct ID so clients can recover it and workers receive a truthful blocked state.
- Funding transaction journal entries remain idempotent by network and transaction hash.
- Repeated funding requests are rejected while a non-terminal funding transaction exists.
- A failed terminal funding transaction may be retried without deleting its historical journal entry.
- Notifications are computed per connected role from job state; no globally shared notification payload is introduced.

## Frontend Components

- **Post-deployment handoff:** redirects to and focuses the manage-page funding panel.
- **Activation banner:** client-only persistent banner for `UNFUNDED` jobs.
- **Needs funding list:** client-scoped recovery group on Jobs.
- **Funding status panel:** renders the five truthful states above and exposes retry only after verified failure.
- **Notification item:** client-only derived reminder with job title and deep link.
- **Public empty state:** explains that unfunded work is not yet active without exposing client-specific information.

Components consume a single normalized activation state helper so labels, badges, buttons, cards, and notifications cannot disagree.

## Error Handling

- Wallet rejection returns to Funding required and explains that no GEN moved.
- Missing or malformed transaction hashes never create a confirmed state.
- Network timeouts preserve the recorded hash and offer **Check funding status**, not a second funding button.
- Confirmed transaction plus stale job snapshot triggers reconciliation and continues showing confirmation pending until `OPEN` is verified.
- A transaction confirmed on Bradbury but rejected by the contract is shown as failed with the execution result.
- API unavailability keeps the last verified state, marks live updates unavailable, and never reveals hidden unfunded jobs publicly.

## Accessibility and Responsive Behavior

- The activation banner uses `role="status"`; funding failures use `role="alert"`.
- Status is communicated with text and icons, not color alone.
- Focus moves to the funding heading after the post-publish redirect.
- Buttons have state-specific labels and disabled explanations.
- Needs funding and funding panels work at a 390-pixel viewport without horizontal overflow.

## Testing

### Backend

- Public job listing excludes `UNFUNDED` Direct Hire and Bounty records.
- Client-scoped recovery returns only unfunded jobs owned by that client.
- Unrelated wallets and visitors cannot receive another client’s funding reminder data.
- Duplicate funding is blocked while a funding transaction is non-terminal.
- Failed funding can be retried and both transaction records remain auditable.

### Frontend

- Successful deployment routes directly to the funding panel.
- An unfunded client sees the banner, notification, and Needs funding card.
- Workers and visitors see no client notification and no funding control.
- Browse Jobs contains only funded/open jobs.
- Pending transactions suppress duplicate funding and survive refresh.
- Failed, cancelled, confirmed, and stale-snapshot states render the correct action.
- Mobile layouts have no horizontal overflow and retain a visible primary funding action.

### Regression

- Existing 74 backend/live and 57 frontend tests remain green.
- Direct Hire and Bounty happy paths complete from deployment through verified settlement.
- Demo and Wallet modes preserve role separation and transaction truthfulness.

## Success Criteria

- A newly deployed job cannot appear publicly before verified funding.
- A client who leaves immediately after deployment can find the job under Needs funding and activate it in one click plus wallet confirmation.
- No worker can accept or submit against an unfunded job.
- No user sees another client’s funding reminder.
- Refreshing during Bradbury confirmation does not create a second funding request or reset the truthful pending state.
