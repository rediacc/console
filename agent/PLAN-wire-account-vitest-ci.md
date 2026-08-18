# PLAN: Wire the unrun vitest suites into CI (the account gap is elsewhere)
Status: draft
Owner: 97604f47
Updated: 2026-08-14

## 0. The premise is wrong, and that matters more than the fix

The brief says private/account's vitest integration suite is NEVER run by CI. It is
run, on every non-bot CI run, and has been. The grep that produced the finding
searched for the literal `vitest`; the invocation is three hops deep and never
spells that word in a workflow or a `.ci` script.

The chain, every link verified:

| # | Anchor | Content |
|---|--------|---------|
| 1 | `.github/workflows/ci-quality.yml:1261-1263` | job `quality-go`, step `Run account integration tests`, `run: .ci/scripts/private/run-account.sh test` |
| 2 | `.ci/scripts/private/run-account.sh:42-45` | `case "$STAGE" in quality \| test) ... npm run test` after `cd "$ACCOUNT_DIR"` (line 35) |
| 3 | `private/account/package.json:12` | `"test": "vitest run"` |

It is also declared, not accidental: `scripts/ci-runner/manifest.ts:182` carries

```
{ id: 'check:ci-account-server', ..., leaves: ['.ci/scripts/private/run-account.sh'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-go',
        step: "Run account integration tests" } }
```

and `check-ci-parity.ts:424-468` (R3) re-verifies that pointer against the parsed
workflow on every run, so the step name and its `run:` body cannot drift silently.

Two follow-on claims in the brief also fail:

- **It cannot be scope-skipped.** `.ci/scripts/ci/scope-map.cjs:42` states that
  ci-quality.yml carries no `run_*` gate; `grep -c "run_" .github/workflows/ci-quality.yml`
  returns **0**, so the scope engine has no lever to turn `quality-go` off. The only
  condition on the job is `if: inputs.is_bot != 'true'` (`ci-quality.yml:1140`).
- **The 21 backup control-plane tests are covered.** `private/account/tests/integration/backup-storage.test.ts`
  is inside `vitest.config.ts`'s `include: ['tests/integration/**/*.test.ts', ...]`,
  so it rides the same step. Measured: `npx vitest run tests/integration/backup-storage.test.ts`
  → `Test Files 1 passed (1) / Tests 21 passed (21)`, 2.79s.

**Do not add a second account-vitest job.** It would duplicate ~14s of work, and the
parity gate would then have two manifest entries pointing at two steps running the
same suite — the maintenance cost of a gate that proves nothing new.

There is a real gap, three of them, found by sweeping the class. The rest of this
plan is about those.

## 1. What the class sweep actually found

Every package with a test script, and whether CI runs it:

| Package / tree | Script | Run by CI? | Evidence |
|---|---|---|---|
| `private/account` | `test` = `vitest run` | **YES, full suite** | `ci-quality.yml:1261` → `run-account.sh:45` |
| `packages/shared` | `test` = `vitest run` | **YES** | `ci-quality.yml:822-824` `Run shared package tests` |
| `packages/cli` | `test:unit` | **YES** | `ci-quality.yml:826-828`; manifest `check:test-cli` (`manifest.ts:105`) |
| `workers/www` | `test:unit` | **YES** | manifest `check:test-workers` (`manifest.ts:115`) → `quality-www-build` |
| `packages/provisioning` | `test` = `vitest run` | **partial** | only `.ci/scripts/test/run-unit.sh:41-44`, invoked at `ct-tests.yml:193`, whose job `test-unit` is gated `if: inputs.full_suite == 'true' && inputs.run_unit != 'false'` (`ct-tests.yml:185`) |
| `packages/e2e-tests` | `test:unit` | **partial** | same job, `run-unit.sh:47` |
| **`private/account/web`** | `test` = `vitest run` (34 files, 592 tests) | **NO — 1 of 34 files** | `package.json:105` runs exactly `src/components/console/__tests__/contract-coverage.test.tsx` |
| **`packages/www`** | `test:unit` (2 files, 27 tests) | **NO** | no workflow or `.ci` script invokes it; `run-unit.sh` does not list it |
| **`packages/json`** | `test` = `./test-templates.sh` | **NO** | only `build-json.sh` touches the package in CI |

Note the same shape one level down: `package.json:104`
`check:ci-account-scope-audit` also runs a single account file
(`tests/integration/scope-audit.test.ts`). That one is harmless — the full suite
already covers it at `ci-quality.yml:1261`, so it is a fast-fail duplicate, not a gap.
`check:ci-console-coverage` has no such backstop, which is exactly why it is gap A.

### Gap A — `private/account/web`: 33 of 34 test files never run in CI

`package.json:105`:

```
"check:ci-console-coverage": "cd private/account/web && npx vitest run src/components/console/__tests__/contract-coverage.test.tsx --reporter=dot",
```

That is the only invocation of that tree's vitest anywhere in `.github/` or `.ci/`
(the other `private/account/web` hits are Vite *builds* at `ci.yml:1112`,
`cd-deploy-worker.yml:124`, `cd-deploy-account.yml:135`, and biome at
`check-account-portal.sh:51`). The other 33 files — `config-key-slots`,
`config-session-provider`, `useJobStream`, `executor-session`, the whole
`src/lib/__tests__` set — can go red and CI stays green.

Measured full suite (this tree, local): **34 files / 592 tests / 17.7s wall**, all green.

### Gap B — `packages/www` `test:unit`: 2 files, never run

`packages/www/package.json:15` `"test:unit": "vitest run"`, config at
`packages/www/vitest.config.ts` including `src/**/__tests__/**/*.test.ts`, which
resolves to `src/utils/__tests__/account-url.test.ts` and `marketing-host.test.ts`.
Measured: **2 files / 27 tests / 0.14s**. Cheapest possible fix; no reason for it to
be unrun.

### Gap C — `packages/json` `test`: deliberately out of scope for this plan

`packages/json/package.json:7` `"test": "./test-templates.sh"`. Read the script
before wiring it: `test-templates.sh:20-22` sets `TEST_TIMEOUT=240` per lifecycle
function and `HEALTH_CHECK_TIMEOUT=360` for "slow-starting services like GitLab",
and it executes real `up()`/`down()` lifecycles against Docker per template. This is
an E2E surface with a many-minute ceiling, not a quality gate. Wiring it belongs in
`ct-tests.yml` behind a `run_*` flag, sized against its own measured runtime, and is
a separate decision. **Listed here as a finding with evidence; not designed here.**

## 2. The fix

Two changes. Both are wiring; neither writes a test.

### A1. Widen `check:ci-console-coverage` to the whole tree, and rename it

`package.json:105` becomes:

```json
"check:ci-test-account-web": "cd private/account/web && npx vitest run --reporter=dot",
```

`scripts/ci-runner/manifest.ts:188` becomes:

```ts
{ id: 'check:ci-test-account-web', run: 'npm run check:ci-test-account-web', gate: true,
  mutex: ['account-vitest'], weight: 2, heavy: true, leaves: ['vitest'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-packages', step: "Account portal unit tests" } },
```

`.github/workflows/ci-quality.yml:810-812` becomes:

```yaml
      - name: Account portal unit tests
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: npm run check:ci-test-account-web
```

Why a rename rather than just a wider body: the name is the only thing a reader of a
red CI log sees, and "Console contract coverage" would then be lying about 33 of the
34 files it runs. Per the repo's clean-break rule there is no alias to keep. All three
edits are one atomic change — see §3 for why they cannot be split.

`quality-packages` is the right home, not a new job: it already carries
`account: 'true'` (`ci-quality.yml:802`), so the three account npm trees are already
installed and cached there. The gap costs **+17.7s** on a job whose ceiling is
`timeout-minutes: 15` (`ci-quality.yml:780`). No new job, no new cache key, no change
to any job's account-cache invalidation surface.

**This does not disturb the `ct-tests.yml:287-298` reasoning.** That comment explains
why `account: 'true'` was *removed* from eight VM/E2E jobs in ct-tests.yml. This plan
adds `account: 'true'` to nothing. `quality-packages` and `quality-go` already declare
it, for reasons stated inline at `ci-quality.yml:795-798` and `1169-1171`, and both
genuinely need the account trees: `quality-packages` runs `check-account-portal.sh`
plus the portal vitest, `quality-go` runs the account integration suite out of
`private/account`'s own tree. The eight jobs that dropped it stay untouched.

### A2. Run `packages/www`'s unit tests

Add to `quality-packages`, immediately after the existing shared/CLI test steps
(`ci-quality.yml:822-828`), matching their shape:

```yaml
      - name: Run www unit tests
        if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
        run: npm run test:unit --workspace=@rediacc/www
```

Cost: 0.14s.

**Also give it a manifest entry**, and here the plan deliberately fixes an asymmetry
it found rather than copying it. `Run shared package tests` (`ci-quality.yml:822`) has
**no** manifest entry, so a local `npm run ci` never runs `packages/shared`'s tests —
CI catches them, a developer's pre-push run does not. R2 does not complain because
`GATE_SHAPED` (`check-ci-parity.ts:68-69`) only matches `.ci/scripts/**` paths, and a
bare `vitest` leaf is not one. So the hole is invisible to the parity gate by
construction. Add both:

```ts
{ id: 'check:test-www', run: 'npm run check:test-www', gate: true, leaves: ['vitest'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-packages', step: "Run www unit tests" } },
{ id: 'check:test-shared', run: 'npm run check:test-shared', gate: true, leaves: ['vitest'],
  ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml',
        job: 'quality-packages', step: "Run shared package tests" } },
```

with `package.json` keys `"check:test-www": "npm run test:unit -w @rediacc/www"` and
`"check:test-shared": "npm run test -w @rediacc/shared"`, mirroring `check:test-cli`
at `package.json:147`. Note these are `check:test-*`, **not** `check:ci-*`: R1
(`check-ci-parity.ts:398-406`) only demands manifest membership for `check:ci-*` keys,
and `check:test-cli` / `check:test-workers` set the precedent for the other prefix.
The `Run shared package tests` step name is left exactly as it is so the new pointer
resolves.

## 3. What the parity gate demands, in both directions

`npm run check:ci-parity` (script `scripts/check-ci-parity.ts`, gate test
`.ci/scripts/test/gates/test-ci-parity.sh`) is the gate that will reject a half-done
version of this change. The three relations, from `check-ci-parity.ts:9-11`:

- **R1 (`:398-406`)** — every `check:ci-*` key in root `package.json` must be a
  manifest id. Renaming `check:ci-console-coverage` → `check:ci-test-account-web`
  therefore requires the `manifest.ts` id to change **in the same commit**. Change the
  key alone and R1 fires on the new key; change the manifest alone and hygiene
  (`:479-486`) fires because the id is no longer a package.json script.
- **R2 (`:408-422`)** — a gate-shaped leaf CI runs must be a manifest leaf. Nothing
  here adds a `.ci/scripts/**` leaf, so R2 is not engaged by this change. Stated so
  nobody adds a `.ci/scripts/quality/check-*.sh` wrapper "for tidiness" and trips it.
- **R3 (`:424-468`)** — every manifest `ci: {kind:'step'}` pointer must name a real
  workflow, a real job, a real step **by exact name**, and that step's `run:` must
  resolve to one of the entry's declared `leaves`. So the workflow step rename and the
  `manifest.ts` `ci.step` string must match character for character, including the
  quoting style already used on that line.

Concretely, the manifest edits required:

1. `manifest.ts:188` — id, `run`, and `ci.step` all change (A1). `leaves: ['vitest']`
   is unchanged and stays correct: the body still resolves to `vitest`.
2. `manifest.ts` — two new entries, `check:test-www` and `check:test-shared` (A2).
3. Nothing else. `qualityGateTest` is not set on any of these (they are not files
   under `.ci/scripts/test/gates/`), so assertion 7's on-disk glob comparison is
   untouched.

## 4. Missing submodule: fail, do not skip

`private/account` can be absent from a checkout. The repo has already answered this
question once, and the answer is in `run-account.sh:20-32`:

```
# A missing submodule must not read as "tests passed". `check:ci-account-server`
# is a gate in ci-quality.yml, and a silent exit 0 there means the account suite
# never ran while the job reported green.
if [[ ! -f "$ACCOUNT_DIR/package.json" ]]; then
    if [[ "${CI:-}" == "true" ]]; then
        log_error ...; exit 1
    fi
    log_warn "... CI is not 'true', so absence is a soft skip here; in CI it is a hard failure."
    exit 0
fi
```

Adopt exactly that split for `check:ci-test-account-web`, for the same reason and with
the same visibility: **hard fail under `CI=true`, loud warn-and-skip locally.** Do not
invent a new convention.

Mechanically, `cd private/account/web && npx vitest run` on an absent submodule fails
at the `cd` with a nonzero exit and a legible message, so CI already behaves correctly
with no guard at all. The guard is worth adding only for the *local* half, so a
developer without the submodule gets a warning rather than a bare `cd: no such file`.
If you add it, it must print at WARN level and name the submodule — an invisible skip
is the failure mode this whole plan exists to close. The existing
`check:ci-console-coverage` has no guard today and neither behaviour changes for the
worse without one; this is a nice-to-have, not a blocker.

## 5. Runtime budget

All numbers measured locally on this branch, 2026-08-14, not estimated:

| Suite | Files | Tests | Wall |
|---|---|---|---|
| `private/account` (already wired) | 87 | 1557 | 13.85s (`real 0m14.178s`) |
| `private/account/web` (gap A) | 34 | 592 | 17.74s (`real 0m18.201s`) |
| `packages/www` (gap B) | 2 | 27 | 0.14s (`real 0m0.650s`) |

Gap A replaces a step that already runs one of those 34 files, so the true delta on
`quality-packages` is roughly **+16s**, plus **+0.2s** for gap B. `quality-packages`
runs on `ubuntu-latest` with `timeout-minutes: 15` (`ci-quality.yml:779-780`). The
15-minute **`ubuntu-slim`** cap cited in the brief does not apply to this job — it is
the hard platform cap on the slim tier discussed at `ci-quality.yml:36` and
`:955-968`, and `quality-packages` is not on that tier. Sixteen seconds is noise
against either ceiling.

Runner-sizing note: `check:ci-runner-advice` (`.ci/scripts/quality/check_runner_advice.py`,
baseline `.ci/scripts/quality/runner-sizing-baseline.json`) reads `runs-on:` against
recorded job durations. Adding ~16s to one `ubuntu-latest` job should not move its
advice, but the gate must be run — see §6.

## 6. Control-first: prove the new coverage CAN FAIL

This repo has shipped gates that could not fail (`check-ci-parity.ts:36-42` documents
one that ran green for weeks while its real scan never executed). Treat that as the
primary risk here, because the whole change is "make CI run more tests" and a
misrouted step produces exactly the same green as before.

**Do the local half first, then the CI half. Both, in order.**

### 6.1 Local, before pushing (2 minutes)

1. **Baseline.** `npm run check:ci-test-account-web` → expect 34 files / 592 tests
   passing, ~18s. If it reports 1 file, the rename shipped without the body change.
2. **Plant.** In a file the OLD key never ran — use
   `private/account/web/src/lib/__tests__/discovery-cache.test.ts`, deliberately not
   `contract-coverage.test.tsx` — flip one assertion to a wrong value.
3. **Re-run.** The command must now exit nonzero and name `discovery-cache.test.ts`.
   *If it stays green, the include glob or the working directory is wrong and the
   change is worthless.*
4. **Revert the plant** (edit it back by hand; never `git checkout`/`restore` — the
   tree carries other sessions' uncommitted work).
5. Repeat 2-4 for gap B against `packages/www/src/utils/__tests__/marketing-host.test.ts`.
6. **Prove the routing, not just the suite:** `npm run check:ci-parity`. It must pass.
   Then temporarily mistype `ci.step` in the new manifest entry and re-run — R3 must
   fire with "points at step ... which has no such `run:` step". Restore. This is the
   control for the *wiring*, distinct from the control for the *tests*.

### 6.2 In CI, on the PR (the half that actually counts)

Local vitest passing proves nothing about whether the GitHub job invokes it. Push the
change with **one planted failure still in place** in `discovery-cache.test.ts`, and
confirm on the run page that the `Packages` job fails at the step named
`Account portal unit tests` with that file in the output. Then push the revert and
confirm green. A run where the job passes with the plant in place means the step is
not reaching the suite — investigate before merging, do not rationalise it.

Cheap and sufficient substitute if a planted-failure push is unwelcome: on the first
real run, open the `Account portal unit tests` step log and read the vitest summary
line. It must say `Test Files 34 passed (34)`. `1 passed (1)` means the rename landed
and the body did not.

## 7. Gates this change touches, and whether they must be re-run

| Gate | Why it is touched | Re-run? |
|---|---|---|
| `check:ci-parity` | manifest ids, `ci.step` pointers, package.json keys all change | **Yes, mandatory.** The one gate that can reject this change |
| `.ci/scripts/test/gates/test-ci-parity.sh` | the parity gate's own both-directions test; runs under `check:ci-quality-gates` | **Yes** |
| `check:ci-gate-id-convention` (`.ci/scripts/quality/check-gate-id-convention.sh`) | NOT actually engaged: its invariant is narrow by design (`check-gate-id-convention.sh:17-23`) and applies only to manifest entries whose `run` executes a `.ci/scripts/test/gates/` script. None of the entries here do | Runs anyway inside `npm run ci`; no action |
| `check:ci-timeout-headroom` (`.ci/scripts/quality/check_job_timeout_headroom.py`) | `quality-packages` gains ~16s | **Yes** |
| `check:ci-runner-advice` | `runs-on` vs measured duration | **Yes** |
| `check:ci-scope-completeness`, `check:ci-secret-reachability` | workflow text edited | Yes (they run in `quality-security` anyway) |
| `check:ci-shell-lint` / `shfmt` | only if a submodule guard shell block is added (§4) | Only then |
| `check:ci-workflow-*` / actionlint | ci-quality.yml edited | Yes |
| `check:test-cli`, `check:test-workers`, `check:ci-account-server` | untouched | No |

Practical answer: run `npm run ci` once. The runner schedules the set.

## 8. Out of scope, stated so nobody has to guess

- No new tests for any suite. Wiring only.
- No second account-vitest job (§0).
- No change to `ct-tests.yml`'s eight `account: 'true'`-dropped jobs (§2 A1).
- `packages/json`'s Docker-driven template suite (§1 gap C) — a real finding, a
  separate decision, sized differently.
- Promoting `packages/provisioning` / `packages/e2e-tests` unit tests out of the
  `full_suite`-gated `test-unit` job into the always-on quality lane. They ARE wired,
  just conditionally; whether "only on the full suite" is the intended contract is an
  operator call, not a defect this plan should silently redefine.

## 9. One measurement artifact, recorded so it is not re-chased

The first full run of `private/account`'s suite during this investigation reported
`tests/integration/backup-storage.test.ts` failing with
`ReferenceError: BACKUP_GRANT_ACTIONS is not defined` pointing at
`private/account/src/services/backup-chunk-store.ts:629`. That identifier does not
exist in the file; line 631 reads `actions: BACKUP_WRITE_GRANT_ACTIONS`, defined at
`backup-chunk-store.ts:361`. An immediate re-run of the same file was green
(`Tests 21 passed (21)`, 2.79s), and the full suite is otherwise
`Test Files 86 passed / Tests 1556 passed`.

Diagnosis: a concurrent agent was mid-edit in `private/account` during the run — this
session has several writers active in the same shared checkout. **It is a race against
a live edit, not a defect in the suite and not a defect in the wiring.** Recorded
because a stale-transform failure in that exact file is going to look like a real bug
to the next reader, and because it is a live demonstration that timing a suite in a
shared tree can lie.

## 10. Independent verification pass (second agent, same day)

A second session re-derived every load-bearing claim above from the tree rather than
from this document. Result: **the plan stands.** What was re-run and what it returned:

- **The refuted premise.** `ci-quality.yml:1261-1263` → `run-account.sh:42-45` →
  `private/account/package.json:12` confirmed link by link. `scripts/ci-runner/manifest.ts:182`
  carries the `check:ci-account-server` entry with `ci.job: 'quality-go'`,
  `ci.step: "Run account integration tests"`. The step is committed at HEAD, not a
  working-tree artifact (`git show HEAD:.github/workflows/ci-quality.yml` line 1237).
  The brief's grep missed it because no workflow or `.ci` script contains the word
  `vitest` on this path — the invocation is three hops deep.
- **Why the missing-submodule question is already answered.** `run-account.sh:20-33` is
  itself an *uncommitted* working-tree change on this branch (`git diff` shows the
  previous body was a bare `log_warn ... exit 0`). So the hard-fail-under-CI behaviour
  §4 tells you to copy exists but is not yet committed; it must ship with, or before,
  the change this plan describes.
- **Re-measured, independently, on the same box:**

  | Suite | Files | Tests | Wall (`/usr/bin/time`) |
  |---|---|---|---|
  | `private/account` | 87 | 1557 | 15.58s |
  | `private/account/web` | 34 | 592 | 15.70s |
  | `packages/www` | 2 | 27 | 0.84s |

  All three green. The §5 figures and these differ by a couple of seconds in both
  directions, which is scheduling noise on a loaded shared box; the conclusion
  ("seconds, not minutes; no job needs to move tier") is unaffected.
- **Anchors spot-checked and resolving:** `ci-quality.yml:780` (`timeout-minutes: 15`),
  `:800-803` (`account: 'true'` in `quality-packages`), `:810-812` (the one-file console
  coverage step), `:822-828` (shared + CLI test steps), `:1140` (`quality-go`'s only
  condition), `package.json:104,105,147`, `packages/www/package.json:15`,
  `manifest.ts:105,115,182,187,188`, `check-ci-parity.ts:68-69` (`GATE_SHAPED`),
  `:398` (R1), `:408` (R2), `:424` (R3), `:479-486` (hygiene),
  `scope-map.cjs:41-43` plus `grep -c "run_" .github/workflows/ci-quality.yml` → `0`.
- **The §2 A2 asymmetry is real:** `grep -n "test-shared\|test-www" scripts/ci-runner/manifest.ts`
  returns nothing, so `packages/shared`'s tests genuinely run in CI and nowhere in the
  local gate set.
- **Sibling sweep completed in the other direction too.** `private/renet` has **no**
  `package.json` anywhere outside `node_modules`, so it has no npm test tree to be
  unrun; its Go tests are invoked directly (`ci-quality.yml:1238,1243,1268`,
  `ci-build-renet.yml:110,113,277`, `ct-tests.yml:1538`, `ci-ops-test.yml:136`).
  `private/account/e2e` (Playwright) runs at `ct-tests.yml:1636` `test-account-e2e`.
  That leaves gaps A, B and C exactly as listed in §1 — no fourth one.
