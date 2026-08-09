# Merit Marketplace Functionality Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Turn Merit’s shared registry into a searchable marketplace with verified wallet history, private role-scoped notifications, and recoverable job drafts.

**Architecture:** Query parameters make discovery shareable; backend endpoints derive activity and notifications from verified registry transitions; drafts are private to the connected wallet and never deploy automatically. No arbitrary reputation score is introduced.

**Tech Stack:** Next.js App Router, React, FastAPI, SQLite, Vitest, pytest.

## Global Constraints

- Visitors may inspect public jobs but may not receive another wallet’s notifications or private drafts.
- Wallet ownership must be proven by a nonce signature before private data is returned or changed.
- Activity uses verified Merit records only; do not invent ratings or off-chain claims.
- Templates remain editable and require explicit final wallet review.

---

### Task 1: Add URL-backed marketplace discovery

**Files:**
- Modify: `app/jobs/page.tsx`
- Create: `lib/job-filters.ts`
- Test: `tests/frontend/job-presentation.test.ts`

**Interfaces:**
- Produces: `parseJobFilters(searchParams) -> JobFilters`.
- Produces: `serializeJobFilters(filters: JobFilters) -> URLSearchParams`.

- [ ] Write exact filter round-trip tests.

```ts
const expected = { q: "audit", type: "BOUNTY", status: "OPEN", min: "1", max: "5", participation: "OPEN", sort: "VALUE_HIGH", page: 2 };
expect(parseJobFilters(serializeJobFilters(expected))).toEqual(expected);
expect(parseJobFilters(new URLSearchParams("page=-1&min=nope"))).toMatchObject({ page: 1, min: "" });
```
- [ ] Run the focused tests and confirm failure.
- [ ] Replace local-only filter initialization with `useSearchParams` plus `router.replace`, preserving back/forward navigation and resetting only `page` when a filter changes.
- [ ] Add reward-range and open-participation controls and a mobile filter drawer using native `dialog` semantics.
- [ ] Run tests, typecheck, a 390px check, and commit with `git commit -m "feat: add shareable marketplace filters"`.

### Task 2: Add wallet challenge authentication

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Create: `lib/wallet-auth.ts`
- Test: `tests/backend/test_store_and_demo_roles.py`
- Test: `tests/frontend/wallet.test.ts`

**Interfaces:**
- Produces: `POST /api/wallet/challenge` and `POST /api/wallet/session`.
- Produces: HTTP-only, same-site session cookie scoped to the normalized wallet address.

- [ ] Write challenge lifecycle tests.

```python
def test_challenge_is_single_use(client, signed_challenge):
    assert client.post("/api/wallet/session", json=signed_challenge).status_code == 200
    assert client.post("/api/wallet/session", json=signed_challenge).status_code == 401

@pytest.mark.parametrize("mutation", ["expired", "address_mismatch", "wrong_chain", "invalid_signature"])
def test_invalid_challenge_is_rejected(client, challenge_for):
    assert client.post("/api/wallet/session", json=challenge_for(mutation)).status_code == 401
```
- [ ] Run focused tests and confirm failure.
- [ ] Store hashed nonces, verify signatures through the existing wallet boundary, issue a random opaque session ID, and never store the signature as authentication state.
- [ ] Add `ensureWalletSession(address)` that requests a signature only when a private feature is opened.
- [ ] Run tests and commit with `git commit -m "feat: authenticate wallet-scoped data"`.

### Task 3: Add verified wallet activity

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Create: `app/activity/page.tsx`
- Create: `components/wallet-activity.tsx`
- Modify: `components/app-shell.tsx`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `GET /api/wallet/{address}/activity` protected by matching session.
- Returns grouped `created`, `accepted`, `submitted`, `evaluated`, `settlements` events with source job and verified transaction reference.

- [ ] Write activity authorization and evidence tests.

```python
def test_wallet_activity_is_private(client, session_for):
    response = client.get("/api/wallet/0xother/activity", cookies=session_for("0xclient"))
    assert response.status_code == 403

def test_wallet_activity_uses_verified_transfer(client, finalized_job, session_for):
    data = client.get(f"/api/wallet/{finalized_job['worker']}/activity", cookies=session_for(finalized_job["worker"])).json()
    assert data["settlements"][0]["amount"] == finalized_job["verified_worker_amount"]
    assert data["settlements"][0]["transaction_hash"] == finalized_job["settlement_tx"]
```
- [ ] Implement the query from jobs, snapshots, and transaction journal; label unverified records explicitly and exclude them from confirmed totals.
- [ ] Build role-grouped activity UI with empty, stale, loading, and disconnected states.
- [ ] Run tests and visual checks in both themes.
- [ ] Commit with `git commit -m "feat: add verified wallet activity"`.

### Task 4: Persist role-scoped notifications

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Modify: `lib/notifications.ts`
- Modify: `components/notification-center.tsx`
- Modify: `components/providers.tsx`
- Test: `tests/frontend/notifications.test.ts`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `GET /api/notifications`, `POST /api/notifications/{id}/read`, `POST /api/notifications/read-all`.
- Notification identity: `(wallet_address, job_address, transition, source_tx)` unique.

- [ ] Write notification privacy and idempotency tests.

```python
def test_notification_is_emitted_once_per_verified_transition(store, verified_transition):
    store.record_notification(verified_transition)
    store.record_notification(verified_transition)
    assert len(store.list_notifications(verified_transition["wallet_address"])) == 1

def test_visitor_cannot_read_wallet_notifications(client):
    assert client.get("/api/notifications").status_code == 401
```
- [ ] Add a transition table and derive events only after verified snapshot advancement.
- [ ] Replace browser-only notification authority with backend data; local storage may cache presentation but cannot create critical events.
- [ ] Verify unread badges do not shift layout and mobile controls stay inside the viewport.
- [ ] Run tests and commit with `git commit -m "feat: persist private role notifications"`.

### Task 5: Add private drafts and requirement templates

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Create: `lib/job-drafts.ts`
- Modify: `app/jobs/new/page.tsx`
- Test: `tests/backend/test_store_and_demo_roles.py`
- Test: `tests/frontend/job-presentation.test.ts`

**Interfaces:**
- Produces authenticated CRUD `/api/wallet/{address}/drafts`.
- Draft fields: `id`, `wallet_address`, `job_type`, `title`, `spec`, `fee_bps`, `min_score`, `partial_floor`, `max_submissions`, `updated_at`.

- [ ] Write draft boundary tests.

```python
def test_saving_draft_does_not_create_job(client, session_for, store):
    before = len(store.list_jobs())
    response = client.post("/api/wallet/0xclient/drafts", json={"title": "Audit", "spec": "Inspect navigation"}, cookies=session_for("0xclient"))
    assert response.status_code == 200
    assert len(store.list_jobs()) == before

def test_draft_rejects_secret_fields(client, session_for):
    response = client.post("/api/wallet/0xclient/drafts", json={"title": "x", "spec": "y", "private_key": "secret"}, cookies=session_for("0xclient"))
    assert response.status_code == 422
    assert "secret" not in response.text
```
- [ ] Add four built-in templates—landing page, UX audit, research brief, content package—as typed constants with explicit observable criteria.
- [ ] Add save, restore, rename, and delete controls; autosave only after wallet session exists and never auto-deploy.
- [ ] Require the existing Review and publish step after loading any template or draft.
- [ ] Run tests, production build, and commit with `git commit -m "feat: add protected job drafts"`.
