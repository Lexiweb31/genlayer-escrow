# Merit Cinematic Trust Visual Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Apply the approved Cinematic Trust design to Merit’s homepage and product workspace without changing transaction behavior, contract calls, API fields, or existing evidence routes.

**Architecture:** Build a small marketing-only visual layer around real product content, then restyle shared primitives used by application routes. Decorative motion is isolated, optional, reduced-motion safe, and never present in wallet confirmation panels.

**Tech Stack:** Next.js, React, CSS, inline SVG, self-hosted Manrope and DM Mono, Vitest, browser visual verification.

## Global Constraints

- Homepage headline is exactly “Define the work. Let consensus settle it.”
- Use no Wandor name, travel copy, travel imagery, Special Elite font, external stock video, or autoplay audio.
- Glass is limited to marketing composer/accents; transaction panels remain opaque and high contrast.
- Preserve existing application routes, wallet calls, API calls, contract evidence, and responsive role-specific views.
- Essential copy and primary CTAs remain usable before decorative motion loads.

---

### Task 1: Establish semantic visual tokens

**Files:**
- Modify: `app/globals.css`
- Modify: `app/layout.tsx`
- Modify: `components/ui.tsx`
- Test: `tests/frontend/vercel-package.test.ts`

**Interfaces:**
- Produces CSS tokens for canvas, surface, elevated surface, border, text, muted text, action, success, pending, failure, glow, radius, shadow, and motion duration in dark/light themes.

- [ ] Add static token and font tests.

```ts
for (const token of ["--canvas", "--surface", "--text", "--muted", "--action", "--success", "--pending", "--failure"]) {
  expect(css).toContain(`${token}:`);
}
expect(css).toMatch(/@font-face[\s\S]*url\(["']?\/fonts\/manrope-latin\.woff2/);
expect(css).toMatch(/font-display:\s*swap/);
```
- [ ] Run the tests and confirm failure.
- [ ] Replace page-specific color literals in shared primitives with semantic variables while preserving status meaning.
- [ ] Run `npm run typecheck`, `npm run lint`, and focused tests.
- [ ] Commit with `git commit -m "style: establish Cinematic Trust tokens"`.

### Task 2: Build the agreement composer and cinematic hero

**Files:**
- Create: `components/marketing/agreement-composer.tsx`
- Create: `components/marketing/consensus-orbit.tsx`
- Modify: `app/page.tsx`
- Modify: `app/globals.css`
- Test: `tests/frontend/rendered-evidence.test.ts`

**Interfaces:**
- Composer links to `/jobs/new?type=DIRECT_HIRE` or `/jobs/new?type=BOUNTY` and may pass a URL-encoded draft description; it performs no wallet write.

- [ ] Add exact homepage contract tests.

```ts
expect(homepage).toContain("Define the work. Let consensus settle it.");
expect(homepage).toContain('/jobs/new?type=DIRECT_HIRE');
expect(homepage).toContain('/jobs/new?type=BOUNTY');
expect(homepage).not.toMatch(/Wandor|Special Elite|https?:\/\/.*\.(mp4|webm)/i);
expect(css).toMatch(/@media\s*\(prefers-reduced-motion:\s*reduce\)/);
expect(homepage).toMatch(/explorerRedirectPath|explorer-bradbury/);
```
- [ ] Run the focused test and confirm failure.
- [ ] Implement the hero with deep navy atmosphere, validator orbit SVG, agreement boundary, and one frosted composer; keep headline and CTAs outside the dynamic motion boundary.
- [ ] Replace invented metrics with a real registry/contract proof strip and retain an explicit degraded state.
- [ ] Run tests and commit with `git commit -m "feat: build Cinematic Trust homepage hero"`.

### Task 3: Recompose the homepage narrative

**Files:**
- Modify: `app/page.tsx`
- Create: `components/marketing/how-it-works.tsx`
- Create: `components/marketing/proof-ledger.tsx`
- Modify: `app/globals.css`

**Interfaces:**
- Produces four truthful stages: Define, Fund, Verify, Settle.
- Consumes only current `/api/jobs`, `/api/stats`, explorer links, and verified job records.

- [ ] Move product explanation into a concise one-screen story followed by process, live proof, GenLayer necessity, security boundary, FAQ, and final CTA.
- [ ] Ensure empty/outage states never render illustrative values as live data.
- [ ] Add accessible pause/replay only for explanatory sequence; animation pauses in hidden tabs and under reduced motion.
- [ ] Verify keyboard navigation and heading order.
- [ ] Commit with `git commit -m "feat: add proof-led homepage narrative"`.

### Task 4: Restyle the product workspace without behavior changes

**Files:**
- Modify: `components/app-shell.tsx`
- Modify: `components/job-navigation.tsx`
- Modify: `components/lifecycle.tsx`
- Modify: `components/settlement-proof.tsx`
- Modify: `components/job-card.tsx`
- Modify: `app/jobs/[id]/page.tsx`
- Modify: `app/jobs/[id]/manage/page.tsx`
- Modify: `app/jobs/[id]/evaluation/page.tsx`
- Modify: `app/jobs/[id]/contracts/page.tsx`
- Modify: `app/globals.css`

**Interfaces:**
- Preserves all existing component props, handlers, and route behavior.

- [ ] Capture baseline screenshots for visitor, client, worker, entrant, completed, pending, failure, dark, light, desktop, and 390px states.
- [ ] Promote current verified state and one available next action; keep transaction hash, recipient, amount, and explorer link adjacent to settlement outcomes.
- [ ] Remove oversized dead space, keep technical details collapsible, and ensure role pills never overflow their lane.
- [ ] Confirm no decorative motion exists inside signing, evaluation, recovery, or settlement panels.
- [ ] Commit with `git commit -m "style: refine evidence-led job workspaces"`.

### Task 5: Accessibility and motion verification

**Files:**
- Modify: `app/globals.css`
- Modify affected components from Tasks 2–4.
- Create: `audit/cinematic-trust/README.md`

**Interfaces:**
- Produces a visual audit record with URLs, roles, themes, viewport sizes, and known test data.

- [ ] Check 390px, 768px, 1440px, and 1920px layouts with no horizontal overflow.
- [ ] Check keyboard-only composer, filters, wallet controls, notifications, accordions, and dialogs.
- [ ] Check visible focus, contrast, semantic status text, reduced motion, hidden-tab pause, and no layout shift from badges or fonts.
- [ ] Run `npm test && npm run typecheck && npm run lint && npm run build`.
- [ ] Commit screenshots/notes only when they contain no wallet secrets, then commit with `git commit -m "test: verify Cinematic Trust accessibility"`.

### Task 6: Preview and production rollout

**Files:**
- Modify: `README.md`
- Modify: `PROJECT_SUBMISSION.md`

**Interfaces:**
- Documents the same production app and repository URLs already used by Merit.

- [ ] Push the isolated branch and create a Vercel preview; do not promote automatically.
- [ ] Verify old job/evidence URLs, Direct Hire and Bounty happy paths, wrong-role blocks, pending recovery, and final settlement proof on preview.
- [ ] Record Vercel commit, Render release, and `/api/health` release identifier.
- [ ] Promote Vercel only after backend compatibility and visual review pass.
- [ ] Update README screenshots and submission notes, then commit with `git commit -m "docs: publish Cinematic Trust release evidence"`.
