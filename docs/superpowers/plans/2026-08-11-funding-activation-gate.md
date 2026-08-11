# Funding Activation Gate Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make verified funding the activation boundary for every Direct Hire and Bounty job so clients cannot forget the deposit and workers never see actionable unfunded work.

**Architecture:** Keep the existing GenLayer contracts authoritative and introduce a normalized frontend activation-state helper backed by the durable transaction journal. The public `/api/jobs` response excludes `UNFUNDED` records; a separate wallet-signed recovery request returns only the connected client’s unfunded jobs. Job creation redirects directly to the manage-page funding panel, while wallet funding hashes survive refresh and are registered with the backend after Bradbury verifies them.

**Tech Stack:** Next.js 16, React 19, TypeScript 5.9, Vitest, FastAPI, SQLite, `eth-account`, GenLayerJS, GenLayer Python SDK, Bradbury testnet.

## Global Constraints

- Funding requires an explicit wallet approval or the existing server-signed demo client; Merit never signs for a personal wallet.
- Public visibility changes only after the shared backend snapshot verifies contract state `OPEN` or a later funded lifecycle state.
- `UNFUNDED` Direct Hire and Bounty records never appear in the public marketplace response.
- Client recovery data is returned only after a short-lived `personal_sign` proof recovers the recorded client address; an address string alone is not authorization.
- A transaction hash is evidence of submission, not confirmation.
- A pending funding hash suppresses duplicate funding and remains recoverable after refresh.
- Visitors and workers never receive a client’s funding reminder.
- Existing contract interfaces, Demo Mode, Wallet Mode, Direct Hire, Bounty, evaluation, and settlement behavior remain unchanged.
- No email, SMS, browser push, or third-party notification service is added.
- All new status UI works at a 390-pixel viewport, uses text and icons in addition to color, and avoids horizontal overflow.

---

## File Structure

- Create `lib/funding-activation.ts`: the single pure function that converts job and funding-transaction evidence into one of five UI states.
- Create `lib/wallet-ownership.ts`: canonical short-lived ownership-message creation, parsing metadata, and browser signing.
- Create `components/funding-activation-banner.tsx`: reusable client-only warning and deep link.
- Modify `lib/types.ts`: funding transaction, owned-jobs request/response, and activation-state types.
- Modify `dashboard/store.py`: lookup for the latest transaction by job and kind.
- Modify `dashboard/api.py`: public filtering, signed client recovery, wallet funding registration, and duplicate-preflight checks.
- Modify `lib/server/proxy-policy.ts`: explicitly allow only the new recovery and funding-registration routes.
- Modify `app/api/[...path]/route.ts`: forward the ownership proof body through the existing same-origin boundary without accepting query-string identity.
- Modify `lib/api.ts`: typed client methods for public jobs, owned unfunded jobs, and funding registration.
- Modify `lib/hooks.ts`: public marketplace and opt-in client recovery resource hooks.
- Modify `app/jobs/new/page.tsx`: route every successful deployment to the funding action.
- Modify `app/jobs/page.tsx`: render the client-only **Needs funding** group separately from public live jobs.
- Modify `app/jobs/[id]/manage/page.tsx`: truthful five-state funding panel, focus handoff, registration/recovery, and role blocking.
- Modify `components/notification-center.tsx`: derive the client’s funding reminder from authenticated owned-job state.
- Modify `lib/notifications.ts`: client-only `UNFUNDED` copy and stable reminder ID.
- Modify `app/globals.css`: activation banner, recovery group, state panel, and responsive styles.
- Modify `requirements.txt`: make `eth-account` an explicit backend dependency rather than relying on a transitive install.
- Modify `README.md`: document funding-as-activation and the one-time recovery signature.
- Add/modify focused tests under `tests/backend/` and `tests/frontend/` as listed below.

---

### Task 1: Normalize Funding Activation State

**Files:**
- Create: `lib/funding-activation.ts`
- Modify: `lib/types.ts`
- Create: `tests/frontend/funding-activation.test.ts`

**Interfaces:**
- Consumes: `JobRecord`, optional `FundingTransactionRecord`, optional `PendingWalletAction`.
- Produces: `fundingActivationState(input: FundingActivationInput): FundingActivationView`.
- Produces: `FundingActivationKind = "REQUIRED" | "AWAITING_WALLET" | "CONFIRMING" | "ACTIVE" | "FAILED"`.

Add these exact shared types to `lib/types.ts`:

```ts
export interface FundingTransactionRecord {
  tx_hash: string;
  status: string;
  kind?: "FUNDING";
  created_at?: string;
  updated_at?: string;
}

export interface PendingWalletAction {
  stage: "awaiting_wallet" | "submitted" | "confirming";
  hash?: string;
}

export interface FundingActivationInput {
  job: Pick<JobRecord, "status">;
  fundingTransaction?: FundingTransactionRecord | null;
  pendingAction?: PendingWalletAction | null;
}
```

- [ ] **Step 1: Write failing classification tests**

```ts
import { describe, expect, it } from "vitest";
import { fundingActivationState } from "@/lib/funding-activation";

const job = { address: "0x1111111111111111111111111111111111111111", status: "UNFUNDED" as const };

describe("funding activation state", () => {
  it("requires funding when no transaction exists", () => {
    expect(fundingActivationState({ job }).kind).toBe("REQUIRED");
  });
  it("shows wallet approval before a hash exists", () => {
    expect(fundingActivationState({ job, pendingAction: { stage: "awaiting_wallet" } }).kind).toBe("AWAITING_WALLET");
  });
  it("treats a non-terminal hash as confirming", () => {
    expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status: "ACCEPTED" } }).kind).toBe("CONFIRMING");
  });
  it("uses verified OPEN state as activation", () => {
    expect(fundingActivationState({ job: { ...job, status: "OPEN" } }).kind).toBe("ACTIVE");
  });
  it("makes a cancelled transaction safely retryable", () => {
    expect(fundingActivationState({ job, fundingTransaction: { tx_hash: "0xabc", status: "CANCELED" } })).toMatchObject({ kind: "FAILED", canFund: true });
  });
});
```

- [ ] **Step 2: Run the focused test and verify RED**

Run: `npm test -- tests/frontend/funding-activation.test.ts`

Expected: FAIL because `@/lib/funding-activation` and its exported types do not exist.

- [ ] **Step 3: Implement the minimal pure state helper**

```ts
export type FundingActivationKind = "REQUIRED" | "AWAITING_WALLET" | "CONFIRMING" | "ACTIVE" | "FAILED";

export interface FundingActivationView {
  kind: FundingActivationKind;
  label: string;
  detail: string;
  canFund: boolean;
  transactionHash?: string;
}

export function fundingActivationState({ job, fundingTransaction, pendingAction }: FundingActivationInput): FundingActivationView {
  if (job.status !== "UNFUNDED") return { kind: "ACTIVE", label: "Job funded and publicly visible", detail: "Protected payment is verified by the shared contract snapshot.", canFund: false };
  if (fundingTransaction && ["CANCELED", "CANCELLED", "FAILED"].includes(fundingTransaction.status.toUpperCase())) {
    return { kind: "FAILED", label: "Funding failed", detail: "No protected payment was activated. Review the transaction and retry safely.", canFund: true, transactionHash: fundingTransaction.tx_hash };
  }
  if (fundingTransaction?.tx_hash || pendingAction?.hash) return { kind: "CONFIRMING", label: "Transaction submitted — confirming on Bradbury", detail: "Do not submit another funding transaction.", canFund: false, transactionHash: fundingTransaction?.tx_hash || pendingAction?.hash };
  if (pendingAction?.stage === "awaiting_wallet") return { kind: "AWAITING_WALLET", label: "Awaiting wallet approval", detail: "Confirm or reject the funding request in your wallet.", canFund: false };
  return { kind: "REQUIRED", label: "Funding required", detail: "Your job is created but not active yet.", canFund: true };
}
```

- [ ] **Step 4: Run the focused test and verify GREEN**

Run: `npm test -- tests/frontend/funding-activation.test.ts`

Expected: 5 tests pass.

- [ ] **Step 5: Commit the domain helper**

```bash
git add lib/types.ts lib/funding-activation.ts tests/frontend/funding-activation.test.ts
git commit -m "feat: model truthful funding activation states"
```

---

### Task 2: Filter the Public Marketplace and Add Signed Client Recovery

**Files:**
- Modify: `dashboard/api.py`
- Modify: `requirements.txt`
- Modify: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Consumes: `store.list_jobs()`, the existing `_list_jobs_snapshot()` normalizer, and Ethereum-compatible `personal_sign` signatures.
- Produces: `_public_jobs_snapshot() -> dict[str, Any]` with no `UNFUNDED` jobs.
- Produces: `POST /api/jobs/owned` accepting `OwnedJobsRequest(address, message, signature, demo_mode)`.
- Produces: `_verify_owned_jobs_request(req) -> str`, returning the normalized proven client address or the configured demo-client address.

- [ ] **Step 1: Add failing backend tests for public exclusion and role isolation**

```python
def test_public_jobs_exclude_unfunded_direct_hire_and_bounty(monkeypatch):
    monkeypatch.setattr(api.store, "list_jobs", lambda: [
        {**_record("0xdirect"), "job_type": "DIRECT_HIRE"},
        {**_record("0xbounty"), "job_type": "BOUNTY"},
        {**_record("0xopen"), "lifecycle_status": "OPEN", "state_snapshot": {"status": "OPEN", "amount": "1000"}},
    ])
    response = api._public_jobs_snapshot()
    assert [job["address"] for job in response["jobs"]] == ["0xopen"]
    assert response["stats"]["total_jobs"] == 1

def test_owned_jobs_requires_a_signature_matching_the_recorded_client(monkeypatch):
    account = Account.create()
    other = Account.create()
    monkeypatch.setattr(api.store, "list_jobs", lambda: [{**_record("0xmine"), "client_address": account.address}])
    message = api._ownership_message(account.address, datetime.now(timezone.utc) + timedelta(minutes=10))
    signature = Account.sign_message(encode_defunct(text=message), account.key).signature.hex()
    owned = api.owned_jobs(api.OwnedJobsRequest(address=account.address, message=message, signature=signature))
    assert [job["address"] for job in owned["jobs"]] == ["0xmine"]
    with pytest.raises(HTTPException) as error:
        api.owned_jobs(api.OwnedJobsRequest(address=other.address, message=message, signature=signature))
    assert error.value.status_code == 403
```

- [ ] **Step 2: Run the focused backend tests and verify RED**

Run: `PYTHONPATH=. DEPLOYER_PRIVATE_KEY=placeholder .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k "public_jobs_exclude or owned_jobs_requires"`

Expected: FAIL because the public snapshot, request model, and ownership verifier do not exist.

- [ ] **Step 3: Implement canonical message validation and public filtering**

```python
OWNERSHIP_PREFIX = "Merit needs-funding access"
OWNERSHIP_MAX_SECONDS = 15 * 60

class OwnedJobsRequest(BaseModel):
    address: str = ""
    message: str = ""
    signature: str = ""
    demo_mode: bool = False

def _verify_owned_jobs_request(req: OwnedJobsRequest) -> str:
    if req.demo_mode:
        _require_live_roles()
        return str(demo_client_account.address).lower()
    if not ADDRESS_PATTERN.fullmatch(req.address):
        raise HTTPException(status_code=422, detail={"code": "INVALID_ROLE_ADDRESS", "message": "Invalid client address."})
    address, expires_at = _parse_ownership_message(req.message)
    now = datetime.now(timezone.utc)
    if address.lower() != req.address.lower() or expires_at <= now or expires_at > now + timedelta(seconds=OWNERSHIP_MAX_SECONDS):
        raise HTTPException(status_code=403, detail={"code": "OWNERSHIP_PROOF_EXPIRED", "message": "Sign a fresh Merit recovery message."})
    recovered = Account.recover_message(encode_defunct(text=req.message), signature=req.signature)
    if recovered.lower() != req.address.lower():
        raise HTTPException(status_code=403, detail={"code": "OWNERSHIP_PROOF_INVALID", "message": "The signature does not match this client wallet."})
    return recovered.lower()
```

Build `_public_jobs_snapshot()` by normalizing once, filtering `job["status"] != "UNFUNDED"`, and recalculating stats from only the filtered list. Build `owned_jobs()` from the same normalized rows, selecting only `status == "UNFUNDED"` and a case-insensitive `client_address` match.

```python
def _public_jobs_snapshot() -> dict[str, Any]:
    snapshot = _list_jobs_snapshot()
    jobs = [job for job in snapshot["jobs"] if job.get("status") != "UNFUNDED"]
    return {**snapshot, "jobs": jobs, "stats": _job_stats(jobs)}

@app.post("/api/jobs/owned")
def owned_jobs(req: OwnedJobsRequest) -> dict[str, Any]:
    proven_client = _verify_owned_jobs_request(req)
    jobs = [
        job for job in _list_jobs_snapshot()["jobs"]
        if job.get("status") == "UNFUNDED"
        and str(job.get("client_address", "")).lower() == proven_client
    ]
    return {"jobs": jobs}
```

- [ ] **Step 4: Make `eth-account` explicit and run backend tests**

Add `eth-account>=0.13,<0.14` to `requirements.txt`.

Run: `PYTHONPATH=. DEPLOYER_PRIVATE_KEY=placeholder .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k "public_jobs_exclude or owned_jobs_requires"`

Expected: focused tests pass.

- [ ] **Step 5: Commit public filtering and signed recovery**

```bash
git add dashboard/api.py requirements.txt tests/backend/test_store_and_demo_roles.py
git commit -m "feat: hide unfunded jobs behind client recovery"
```

---

### Task 3: Expose the Recovery Route Through the Same-Origin Boundary

**Files:**
- Create: `lib/wallet-ownership.ts`
- Modify: `lib/types.ts`
- Modify: `lib/api.ts`
- Modify: `lib/server/proxy-policy.ts`
- Modify: `tests/frontend/proxy-policy.test.ts`
- Create: `tests/frontend/wallet-ownership.test.ts`

**Interfaces:**
- Consumes: the injected wallet’s `personal_sign` method and backend `POST /api/jobs/owned`.
- Produces: `ownershipMessage(address: string, expiresAt: Date): string`.
- Produces: `signOwnedJobsAccess(address: string): Promise<OwnedJobsRequest>`.
- Produces: `meritApi.ownedJobs(input: OwnedJobsRequest): Promise<OwnedJobsResponse>`.

- [ ] **Step 1: Write failing message and proxy allowlist tests**

```ts
it("creates the exact bounded Bradbury ownership message", () => {
  expect(ownershipMessage("0xAbC", new Date("2026-08-11T12:15:00.000Z"))).toBe(
    "Merit needs-funding access\nAddress: 0xabc\nNetwork: testnet_bradbury\nExpires: 2026-08-11T12:15:00.000Z",
  );
});

expect(isAllowedMeritApiRoute("POST", ["jobs", "owned"])).toBe(true);
expect(isAllowedMeritApiRoute("GET", ["jobs", "owned"])).toBe(false);
```

- [ ] **Step 2: Run frontend tests and verify RED**

Run: `npm test -- tests/frontend/wallet-ownership.test.ts tests/frontend/proxy-policy.test.ts`

Expected: FAIL because `wallet-ownership.ts` and the owned route are absent.

- [ ] **Step 3: Implement the canonical signer and typed API call**

```ts
export function ownershipMessage(address: string, expiresAt: Date): string {
  return ["Merit needs-funding access", `Address: ${address.toLowerCase()}`, "Network: testnet_bradbury", `Expires: ${expiresAt.toISOString()}`].join("\n");
}

export async function signOwnedJobsAccess(address: string): Promise<OwnedJobsRequest> {
  const provider = browserProvider();
  if (!provider) throw new Error("Connect the client wallet to load jobs that still need funding.");
  const expiresAt = new Date(Date.now() + 10 * 60_000);
  const message = ownershipMessage(address, expiresAt);
  const signature = String(await provider.request({ method: "personal_sign", params: [message, address] }));
  return { address, message, signature, demo_mode: false };
}
```

Cache the request object only in `sessionStorage` and reuse it only while its parsed expiry is in the future. Never place signatures in URLs or logs.

- [ ] **Step 4: Run the focused tests and verify GREEN**

Run: `npm test -- tests/frontend/wallet-ownership.test.ts tests/frontend/proxy-policy.test.ts`

Expected: all focused tests pass.

- [ ] **Step 5: Commit the same-origin recovery client**

```bash
git add lib/types.ts lib/api.ts lib/wallet-ownership.ts lib/server/proxy-policy.ts tests/frontend/wallet-ownership.test.ts tests/frontend/proxy-policy.test.ts
git commit -m "feat: add signed client job recovery"
```

---

### Task 4: Add the Client-Only Needs Funding Queue and Reminder

**Files:**
- Modify: `lib/hooks.ts`
- Modify: `lib/notifications.ts`
- Modify: `components/notification-center.tsx`
- Modify: `app/jobs/page.tsx`
- Modify: `app/globals.css`
- Modify: `tests/frontend/notifications.test.ts`
- Create: `tests/frontend/owned-jobs.test.ts`

**Interfaces:**
- Consumes: `meritApi.ownedJobs()`, `signOwnedJobsAccess()`, connected wallet mode/address.
- Produces: `useOwnedUnfundedJobs(): ResourceState<OwnedJobsResponse> & { load(): Promise<void> }`.
- Produces: `notificationForStatus(job, "UNFUNDED", ..., clientAddress)` with title **Fund your job to publish it**.

- [ ] **Step 1: Write failing role-scoped reminder and queue tests**

```ts
it("creates an unfunded reminder only for the recorded client", () => {
  const unfunded = { ...job, status: "UNFUNDED" as const };
  expect(notificationForStatus(unfunded, "UNFUNDED", now, job.client_address)?.title).toBe("Fund your job to publish it");
  expect(notificationForStatus(unfunded, "UNFUNDED", now, job.worker_address)).toBeNull();
  expect(notificationForStatus(unfunded, "UNFUNDED", now, "0xcccccccccccccccccccccccccccccccccccccccc")).toBeNull();
});
```

In `owned-jobs.test.ts`, extract and test `partitionJobs(publicJobs, ownedJobs)` so `UNFUNDED` records can appear only in `needsFunding`, never `liveJobs`.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `npm test -- tests/frontend/notifications.test.ts tests/frontend/owned-jobs.test.ts`

Expected: FAIL because no client `UNFUNDED` copy or partition helper exists.

- [ ] **Step 3: Implement the opt-in recovery queue**

On `/jobs`, show a compact **Needs funding** section above marketplace stats when:

1. Demo Mode is active and the backend returns shared demo-client drafts, or
2. Wallet Mode is active and the client clicks **Load my unpublished jobs**, signs the short-lived recovery message once, and receives matching drafts.

Each draft card must show title, contract address, creation time, **Not visible to workers**, and a primary link to `/jobs/{address}/manage#funding` labelled **Fund and activate**. Do not merge these records into public stats, filters, pagination, or `JobCard` results.

```tsx
const { data: owned, load: loadOwned, loading: loadingOwned } = useOwnedUnfundedJobs();
const { liveJobs, needsFunding } = partitionJobs(publicJobs, owned?.jobs ?? []);

<NeedsFundingSection
  jobs={needsFunding}
  loading={loadingOwned}
  onLoad={loadOwned}
  manageHref={(job) => `/jobs/${encodeURIComponent(job.address)}/manage#funding`}
/>
<MarketplaceResults jobs={liveJobs} />
```

- [ ] **Step 4: Derive the notification without leaking it globally**

After owned drafts have been authenticated, prepend one stable notification per draft using ID `${job.address}:UNFUNDED`. On refresh, remove that reminder when the owned endpoint no longer returns the job. Keep the existing per-wallet localStorage namespace and never add reminders while `viewer` is null.

- [ ] **Step 5: Add responsive and accessible styles**

Use `.needs-funding-section`, `.needs-funding-grid`, and `.needs-funding-card`; collapse to one column below `720px`. The heading includes a warning icon and explanatory copy, but the CTA remains the only primary-colored control.

- [ ] **Step 6: Run focused tests and commit**

Run: `npm test -- tests/frontend/notifications.test.ts tests/frontend/owned-jobs.test.ts`

Expected: focused tests pass.

```bash
git add lib/hooks.ts lib/notifications.ts components/notification-center.tsx app/jobs/page.tsx app/globals.css tests/frontend/notifications.test.ts tests/frontend/owned-jobs.test.ts
git commit -m "feat: add client funding recovery queue"
```

---

### Task 5: Redirect Publishing Directly to Funding and Add the Persistent Banner

**Files:**
- Create: `components/funding-activation-banner.tsx`
- Modify: `app/jobs/new/page.tsx`
- Modify: `app/jobs/[id]/manage/page.tsx`
- Modify: `app/jobs/[id]/page.tsx`
- Modify: `app/globals.css`
- Modify: `tests/frontend/manage-reconciliation.test.ts`
- Create: `tests/frontend/funding-handoff.test.ts`

**Interfaces:**
- Consumes: `fundingActivationState()`, viewer role, and `/jobs/{id}/manage#funding`.
- Produces: `fundingManageHref(address: string): string`.
- Produces: `<FundingActivationBanner job viewerAddress />`, which returns `null` unless the connected viewer is the recorded client and the job is `UNFUNDED`.

- [ ] **Step 1: Write failing redirect and banner visibility tests**

```ts
it("routes a deployed job to its funding panel", () => {
  expect(fundingManageHref("0xabc")).toBe("/jobs/0xabc/manage#funding");
});

it("does not expose the client funding banner to the worker", () => {
  expect(shouldShowFundingBanner(unfundedJob, unfundedJob.worker_address)).toBe(false);
  expect(shouldShowFundingBanner(unfundedJob, unfundedJob.client_address)).toBe(true);
});
```

- [ ] **Step 2: Run focused tests and verify RED**

Run: `npm test -- tests/frontend/funding-handoff.test.ts tests/frontend/manage-reconciliation.test.ts`

Expected: FAIL because the handoff and banner helpers are absent.

- [ ] **Step 3: Replace both post-deployment destinations**

Change successful `createJob`, `registerWalletJob`, and `resumeRegistration` navigation from the public overview to:

```ts
router.push(`/jobs/${encodeURIComponent(response.job.address)}/manage#funding`);
```

The manage page gives the funding panel `id="funding"`, `tabIndex={-1}`, and moves focus to its heading only when the hash is `#funding` and the verified job state is `UNFUNDED`.

- [ ] **Step 4: Add truthful client, worker, and visitor presentations**

- Client: banner text **Your job is created but not active yet** with **Fund and activate job**.
- Worker: **Waiting for protected payment** and no accept/submit control.
- Visitor: **This job is awaiting client funding** with no client address reminder or funding control.
- Bounty entrant: **This Bounty opens after the reward is funded** and no submission form.

```tsx
<FundingActivationBanner
  state={fundingState}
  role={viewerRole}
  onFund={viewerRole === "client" && fundingState.canFund ? fundEscrow : undefined}
/>
```

Render the CTA only when `viewerRole === "client" && fundingState.canFund`; role copy must never be inferred from a query parameter.

- [ ] **Step 5: Run focused tests and commit**

Run: `npm test -- tests/frontend/funding-handoff.test.ts tests/frontend/manage-reconciliation.test.ts`

Expected: focused tests pass.

```bash
git add components/funding-activation-banner.tsx app/jobs/new/page.tsx app/jobs/[id]/manage/page.tsx app/jobs/[id]/page.tsx app/globals.css tests/frontend/funding-handoff.test.ts tests/frontend/manage-reconciliation.test.ts
git commit -m "feat: make funding the publishing handoff"
```

---

### Task 6: Persist and Recover Wallet Funding Transactions

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Modify: `lib/types.ts`
- Modify: `lib/api.ts`
- Modify: `lib/server/proxy-policy.ts`
- Modify: `app/jobs/[id]/manage/page.tsx`
- Modify: `tests/backend/test_store_and_demo_roles.py`
- Modify: `tests/frontend/proxy-policy.test.ts`
- Modify: `tests/frontend/manage-reconciliation.test.ts`

**Interfaces:**
- Consumes: accepted Bradbury funding hash and existing `_verify_transaction_identity(..., "FUND")` logic.
- Produces: `store.latest_transaction_for_job(job_address: str, kind: str) -> Optional[dict[str, Any]]`.
- Produces: `POST /api/jobs/{id}/register_funding` with `{ transaction_hash }`.
- Produces: `meritApi.registerWalletFunding(id, transactionHash)`.
- Adds `funding_transaction?: FundingTransactionRecord` to detail responses.

- [ ] **Step 1: Write failing journal and registration tests**

```python
def test_latest_funding_transaction_is_scoped_to_job_and_kind(store):
    store.record_transaction({"network": "testnet_bradbury", "tx_hash": "0xold", "job_address": "0xjob", "kind": "FUNDING", "status": "CANCELED"})
    store.record_transaction({"network": "testnet_bradbury", "tx_hash": "0xnew", "job_address": "0xjob", "kind": "FUNDING", "status": "ACCEPTED"})
    assert store.latest_transaction_for_job("0xJOB", "FUNDING")["tx_hash"] == "0xnew"

def test_register_wallet_funding_rejects_wrong_signer_or_contract(monkeypatch):
    # Stub Bradbury with an accepted FUND call from a different signer.
    with pytest.raises(HTTPException) as error:
        api.register_wallet_funding(job["address"], api.RegisterWalletFundingRequest(transaction_hash=tx_hash))
    assert error.value.detail["code"] == "FUNDING_SIGNER_MISMATCH"
```

Add a frontend assertion that `register_funding` is allowed while arbitrary actions remain blocked.

- [ ] **Step 2: Run focused tests and verify RED**

Run: `PYTHONPATH=. DEPLOYER_PRIVATE_KEY=placeholder .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k "latest_funding or register_wallet_funding"`

Run: `npm test -- tests/frontend/proxy-policy.test.ts tests/frontend/manage-reconciliation.test.ts`

Expected: tests fail because the storage method, endpoint, and client recovery path do not exist.

- [ ] **Step 3: Implement transaction lookup and verified registration**

The store query is:

```sql
SELECT * FROM transactions
WHERE lower(job_address) = lower(?) AND kind = ?
ORDER BY created_at DESC, id DESC
LIMIT 1
```

`register_wallet_funding` must verify:

- valid 32-byte hash;
- job is not legacy;
- Bradbury network matches;
- recipient is the selected escrow;
- decoded action is `fund`;
- signer matches `client_address`;
- successful execution;
- transaction hash is not attached to another job or operation.

Then record kind `FUNDING`, refresh the contract snapshot, and return `job_status`. Never mark the job active unless that refreshed status is `OPEN` or later.

- [ ] **Step 4: Add duplicate suppression and refresh recovery**

Before showing an enabled funding button:

1. Read `merit-pending-action:{id}`.
2. If it contains a funding hash, call `readBradburyTransaction(hash)`.
3. When successful, call `registerWalletFunding(id, hash)` and refresh.
4. When still pending, keep **Transaction submitted — confirming on Bradbury**.
5. When failed/cancelled, clear the local pending action only after rendering the failed transaction reference and enabling retry.

The backend demo `fund` route checks `latest_transaction_for_job(..., "FUNDING")` and the live snapshot before submitting. If a non-terminal journal entry exists while state is still `UNFUNDED`, return `409 FUNDING_ALREADY_PENDING`. `_run_action` records the verified funding receipt as kind `FUNDING`.

```ts
const pending = readPendingAction(job.address);
if (job.status === "UNFUNDED" && pending?.hash) {
  const receipt = await readBradburyTransaction(pending.hash);
  if (receipt.isSuccessful) {
    await meritApi.registerWalletFunding(job.address, pending.hash);
    await refreshJob();
  }
}
```

`FINALIZED` is not classified as a failed funding transaction. Until the refreshed contract snapshot becomes `OPEN` (or later), a successful/finalized hash remains `CONFIRMING`; a decoded failed or cancelled receipt becomes `FAILED`.

- [ ] **Step 5: Run focused tests and commit**

Run: `PYTHONPATH=. DEPLOYER_PRIVATE_KEY=placeholder .venv/bin/pytest -q tests/backend/test_store_and_demo_roles.py -k "funding"`

Run: `npm test -- tests/frontend/proxy-policy.test.ts tests/frontend/manage-reconciliation.test.ts tests/frontend/funding-activation.test.ts`

Expected: focused tests pass.

```bash
git add dashboard/store.py dashboard/api.py lib/types.ts lib/api.ts lib/server/proxy-policy.ts app/jobs/[id]/manage/page.tsx tests/backend/test_store_and_demo_roles.py tests/frontend/proxy-policy.test.ts tests/frontend/manage-reconciliation.test.ts
git commit -m "feat: persist and recover funding transactions"
```

---

### Task 7: Regression, Accessibility, Documentation, and Production Verification

**Files:**
- Modify: `README.md`
- Modify: `tests/frontend/environment-boundary.test.ts`
- Modify: `tests/frontend/vercel-package.test.ts`
- Modify: `tests/live/test_custody_matrix.py`

**Interfaces:**
- Consumes: all activation-gate routes and UI states from Tasks 1–6.
- Produces: documented operator/tester flow and a full green release gate.

- [ ] **Step 1: Add final boundary and live-flow assertions**

Add assertions that:

- signatures never appear in generated browser bundles, URLs, logs, or backend responses;
- no `NEXT_PUBLIC_*` secret is introduced;
- the public jobs fixture contains no `UNFUNDED` record;
- an authenticated client recovery fixture contains only that client’s unfunded record;
- the custody runner refuses accept/submit when a contract remains `UNFUNDED`.

Add explicit UI/state regressions for every error branch from the approved design:

```ts
it.each([
  ["wallet rejection", "REQUIRED", "No GEN moved"],
  ["malformed hash", "FAILED", "transaction hash"],
  ["network timeout", "CONFIRMING", "Check funding status"],
  ["stale snapshot", "CONFIRMING", "confirming on Bradbury"],
  ["contract rejection", "FAILED", "Funding failed"],
  ["API unavailable", "CONFIRMING", "Live updates unavailable"],
])("keeps %s truthful", (_case, expectedKind, expectedCopy) => {
  expect(renderFundingFailureFixture(_case)).toMatchObject({ kind: expectedKind, copy: expect.stringContaining(expectedCopy) });
});
```

Also assert that an empty public marketplace explains that unpublished jobs may still need client funding without exposing any address, title, or notification from the owned-jobs response.

- [ ] **Step 2: Document the tester flow**

Add a README section with this exact sequence:

1. Deploy the job.
2. Merit opens **Fund and activate job** automatically.
3. Approve the GEN deposit and wait for **Job funded and publicly visible**.
4. Only then switch to the worker or contributor wallet.
5. If the page was closed, open **Browse jobs → Needs funding**, sign the view-only recovery message, and resume without redeploying.

State explicitly that the recovery signature cannot move funds or submit contract actions.

- [ ] **Step 3: Run the complete verification matrix**

Run:

```bash
npm test
npm run lint
npm run typecheck
npm run build
PYTHONPATH=. DEPLOYER_PRIVATE_KEY=placeholder .venv/bin/pytest -q tests/backend tests/live
```

Expected:

- all frontend tests pass;
- ESLint exits 0;
- TypeScript exits 0;
- Next.js production build exits 0;
- all backend/live tests pass;
- `git diff --check` prints no errors.

- [ ] **Step 4: Run the 390-pixel and desktop smoke test**

At 390×844 and 1440×900 verify:

- creation redirects to `manage#funding`;
- the funding heading receives focus;
- Needs funding cards do not overflow;
- worker and visitor states contain no funding CTA or client notification;
- pending refresh never re-enables funding;
- confirmed `OPEN` state removes the banner/reminder and adds the job to Browse Jobs.

- [ ] **Step 5: Commit documentation and final regressions**

```bash
git add README.md tests/frontend/environment-boundary.test.ts tests/frontend/vercel-package.test.ts tests/live/test_custody_matrix.py
git commit -m "test: verify funding activation gate end to end"
```

- [ ] **Step 6: Request code review before integration**

Invoke `superpowers:requesting-code-review`, address only verified actionable findings, rerun the complete verification matrix, then use `superpowers:finishing-a-development-branch` to present merge/deploy options. Do not push, merge, or deploy until the user selects that integration action.
