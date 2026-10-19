# Merit Performance and Reconciliation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make cached marketplace and finalized-job reads fast while keeping mutable state fresh and recoverable.

**Architecture:** Keep SQLite snapshots as the immediate read model, add freshness metadata and a keyed in-flight read coordinator, and let the backend refresh mutable records. Frontend polling becomes lifecycle- and visibility-aware and never removes last verified data during refresh.

**Tech Stack:** FastAPI, concurrent futures, SQLite, React hooks, Vitest, pytest.

## Global Constraints

- Finalized immutable snapshots do not trigger Bradbury reads.
- Active reads have explicit timeouts and bounded concurrency.
- Failed refreshes preserve the last verified snapshot and mark it stale.
- Existing API fields remain unchanged; freshness fields are additive.

---

### Task 1: Add snapshot freshness and immutable caching

**Files:**
- Modify: `dashboard/store.py`
- Modify: `dashboard/api.py`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `snapshot_verified_at`, `snapshot_mutable`, `snapshot_stale` in job responses.
- Produces: `_snapshot_policy(record: dict[str, Any]) -> tuple[bool, int]` returning `(requires_refresh, max_age_seconds)`.

- [ ] Write failing tests proving finalized snapshots cause zero `_job_state` calls and active snapshots become stale after the configured age.

```python
def test_finalized_snapshot_never_reads_chain(client, finalized_record, monkeypatch):
    monkeypatch.setattr(api, "_job_state", lambda _: pytest.fail("unexpected chain read"))
    response = client.get(f"/api/jobs/{finalized_record['address']}")
    assert response.status_code == 200
    assert response.json()["job"]["snapshot_mutable"] is False

def test_expired_active_snapshot_is_marked_stale(client, active_record, monkeypatch):
    monkeypatch.setattr(api, "_marketplace_last_refresh", 0.0)
    response = client.get("/api/jobs")
    job = next(item for item in response.json()["jobs"] if item["address"] == active_record["address"])
    assert job["snapshot_stale"] is True
```
- [ ] Run `pytest -q tests/backend/test_store_and_demo_roles.py -k snapshot` and confirm failure.
- [ ] Add backward-compatible columns and return freshness fields from `_list_jobs_snapshot()` and `get_job()`.
- [ ] Run the focused tests and confirm PASS.
- [ ] Commit with `git commit -m "perf: add snapshot freshness policy"`.

### Task 2: Deduplicate and bound Bradbury reads

**Files:**
- Create: `dashboard/read_coordinator.py`
- Modify: `dashboard/api.py`
- Test: `tests/backend/test_store_and_demo_roles.py`

**Interfaces:**
- Produces: `ReadCoordinator.get(key: str, reader: Callable[[], T], timeout: float) -> T`.

- [ ] Write concurrency and timeout tests.

```python
def test_coordinator_deduplicates_same_key():
    calls = 0
    coordinator = ReadCoordinator()
    def reader():
        nonlocal calls
        calls += 1
        time.sleep(0.05)
        return {"status": "OPEN"}
    with ThreadPoolExecutor(max_workers=10) as pool:
        values = list(pool.map(lambda _: coordinator.get("0xjob", reader, 1.0), range(10)))
    assert calls == 1
    assert all(value == {"status": "OPEN"} for value in values)

def test_timeout_does_not_overwrite_snapshot(store, active_record):
    before = store.get_job(active_record["address"])["state_snapshot"]
    with pytest.raises(TimeoutError):
        ReadCoordinator().get("0xjob", lambda: time.sleep(1), 0.01)
    assert store.get_job(active_record["address"])["state_snapshot"] == before
```
- [ ] Implement a lock-protected future map, remove completed futures, cap workers with `MARKETPLACE_READ_WORKERS`, and use `BRADBURY_READ_TIMEOUT_SECONDS`.
- [ ] Run `pytest -q tests/backend/test_store_and_demo_roles.py -k 'deduplicate or timeout'`.
- [ ] Commit with `git commit -m "perf: deduplicate Bradbury reads"`.

### Task 3: Make frontend refresh lifecycle- and visibility-aware

**Files:**
- Modify: `lib/hooks.ts`
- Create: `lib/polling.ts`
- Test: `tests/frontend/keep-alive-workflow.test.ts`
- Test: `tests/frontend/job-presentation.test.ts`

**Interfaces:**
- Produces: `pollingIntervalForStatus(status: JobStatus, visible: boolean) -> number | null`.
- Produces: `useJob` behavior that preserves `data` during background refresh.

- [ ] Add exact polling policy tests.

```ts
expect(pollingIntervalForStatus("ACCEPTED", true)).toBeNull();
expect(pollingIntervalForStatus("SETTLEMENT_PENDING", false)).toBeNull();
expect(pollingIntervalForStatus("SETTLEMENT_PENDING", true)).toBe(12_000);
expect(pollingIntervalForStatus("OPEN", true)).toBe(30_000);
```
- [ ] Run `npm test -- --run tests/frontend/keep-alive-workflow.test.ts` and confirm failure.
- [ ] Implement `visibilitychange` subscription, lifecycle intervals, abortable requests, and stale-while-refresh state.
- [ ] Re-run both focused tests and confirm PASS.
- [ ] Commit with `git commit -m "perf: poll only mutable visible jobs"`.

### Task 4: Split marketing motion from transaction routes

**Files:**
- Create: `components/marketing/cinematic-background.tsx`
- Create: `components/marketing/agreement-composer.tsx`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Test: `tests/frontend/vercel-package.test.ts`

**Interfaces:**
- Produces dynamically imported `CinematicBackground` with no wallet dependency.
- Keeps homepage heading and primary CTAs server-renderable before motion loads.

- [ ] Add a bundle-boundary test.

```ts
const marketingFiles = readdirSync("components/marketing").filter((name) => name.endsWith(".tsx")).map((name) => `components/marketing/${name}`);
for (const file of marketingFiles) expect(readFileSync(file, "utf8")).not.toMatch(/from ["']genlayer-js["']/);
const homepage = readFileSync("app/page.tsx", "utf8");
expect(homepage).toMatch(/dynamic\(\(\) => import\(["']@\/components\/marketing\/cinematic-background["']\)/);
```
- [ ] Run the test and confirm failure.
- [ ] Extract only decorative motion and interactive composer enhancement; keep critical copy and links in the page tree.
- [ ] Run `npm run build` and inspect route chunks to ensure wallet code is absent from the initial homepage chunk.
- [ ] Commit with `git commit -m "perf: isolate homepage motion bundle"`.

### Task 5: Enforce performance budgets

**Files:**
- Create: `scripts/check-performance.mjs`
- Modify: `package.json`
- Modify: `.github/workflows/keep-alive.yml`

**Interfaces:**
- Produces command: `npm run perf:check`.

- [ ] Implement build-output budget checks with explicit limits.

```js
const limits = { homepageClientJsBytes: 220_000, maxFontFiles: 3 };
assert(homepageBytes <= limits.homepageClientJsBytes, `homepage JS ${homepageBytes} exceeds ${limits.homepageClientJsBytes}`);
assert(fontFiles.length <= limits.maxFontFiles, `expected at most ${limits.maxFontFiles} font files`);
```
- [ ] Add HTTP timing checks targeting cached `/api/jobs` and a finalized `/api/jobs/{id}` under one second after warm-up; report rather than fake success when production is unreachable.
- [ ] Run `npm run build && npm run perf:check`.
- [ ] Run the reliability regression suites to ensure caching did not alter truthfulness.
- [ ] Commit with `git commit -m "test: enforce Merit performance budgets"`.
