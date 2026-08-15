# PLAN: Testing-surface audit, and the gates that close it
Status: draft
Owner: 97604f47
Updated: 2026-08-15

Scope: the whole console monorepo on branch `backup-storage`, its submodules, and
every workflow reachable from `.github/workflows/ci.yml`. Audited against a still
tree: all writer agents reaped, all feature work landed.

## THE OPERATOR'S INSTRUCTION, VERBATIM

"no gap for testing". Every item must have solid LOCAL testing, and those tests must
be WIRED INTO CI. This audit was deliberately scheduled LAST so it examines a
FINISHED tree rather than a moving one.

## THE QUESTION

The gap between three things that are easy to conflate:

1. what is tested LOCALLY,
2. what CI ACTUALLY RUNS (traced, not assumed from names),
3. what the SYSTEM DOES.

A test that exists but CI never runs is the failure mode this repo has hit
repeatedly. So is a check that runs but cannot fail.

## HOW THIS AUDIT VERIFIED THINGS

Every anchor below was opened. The five facts handed to this audit were each
re-derived rather than accepted:

- `private/account`'s vitest suite IS run by CI, three hops deep, and it is stronger
  than stated: `.github/workflows/ci-quality.yml:1275` (`run: .ci/scripts/private/run-account.sh test`)
  -> `.ci/scripts/private/run-account.sh:43-45` (`quality | test)` -> `npm run test`)
  -> `private/account/package.json` `"test": "vitest run"` -> `private/account/vitest.config.ts:7`
  (`include: ['tests/integration/**/*.test.ts', 'tests/pricing/**/*.test.ts']`).
  The word `vitest` appears nowhere on that path. The job is `quality-go`
  (`ci-quality.yml:1148-1152`), whose only condition is `if: inputs.is_bot != 'true'`,
  so it runs on push-to-main as well as PR. The wrapper fails closed on a missing
  submodule under `CI=true` (`run-account.sh:23-29`).
- renet's Go tests ride `ct-tests.yml:1516` -> `.ci/scripts/private/run-renet.sh:27`
  -> `private/renet/.ci/ci.sh:33` -> `private/renet/.ci/scripts/test/run-tests.sh:59`
  (`-race`, no `-tags`, over `./pkg/... ./cmd/...`). Correction to the brief: the
  runner is `private/renet/.ci/scripts/test/run-tests.sh`, not a console-root path.
- `check:ci-parity` is green. Run this session: `221 manifest gate(s); 2 workflow
  scope(s) in the parity surface; 8 exempt; 90 battery test(s)`, all five of its
  own controls PASS. R1/R2/R3 read at `scripts/check-ci-parity.ts:9-11, 398, 408, 424`.
- `packages/e2e-tests/README.md:31` "Deliberately not in CI" carries 8 entries.
  Suite 26 is correctly documented (`README.md:68-100`). Two omissions are NOT
  documented, and one documented entry is stale. See section 3.
- `scripts/drills/backup.sh` is wired: `ct-tests.yml:1815-1818`, alongside
  `universe` (`:1787`) and `transfer` (`:1803`).
- `packages/json`'s `test-templates.sh` is invoked by nothing. Confirmed by grep over
  `.github/`, `.ci/`, and `run.sh`: zero hits.

---

## 1. TRACED INVENTORY

### 1.1 The two lanes, and why the distinction decides everything

There are exactly two lanes, and they differ in when they run and in whether any
gate polices them.

**Lane Q, the quality surface.** `ci.yml` job `quality` -> `ci-quality.yml`. Jobs are
gated only on `is_bot`, so **Lane Q runs on every push and every PR**. This lane and
`ci.yml#review-gate` are the *entire* parity surface: `scripts/ci-runner/manifest.ts:480-482`
sets `ENTRY_WORKFLOW = '.github/workflows/ci.yml'` and `ENTRY_JOBS = ['quality', 'review-gate']`,
and `paritySurface()` (`:508-548`) walks only the `uses:` closure of those two.

**Lane T, the test surface.** `ci.yml:823` -> `ct-tests.yml`, plus `ci-build-renet.yml`,
`ci-ops-test.yml`, `ct-install-methods.yml`, `ct-update-flow.yml`. Every test job in
`ct-tests.yml` carries `if: inputs.full_suite == 'true' && inputs.run_<leaf> != 'false'`
(`ct-tests.yml:185, 197, 394, 527, 669, 804, 945, 1144, 1307, 1467, 1598, 1638, 1730`),
and `full_suite: ${{ github.event_name != 'push' }}` (`ci.yml:118`). **Lane T does not
run on push-to-main.** Nothing enforces parity in either direction for Lane T.

That asymmetry is the structural root of most of what follows. `check:ci-parity` is a
strong gate, correctly built, pointed at half the repo's testing.

### 1.2 Package-by-package, with the chain that proves it

| Package / dir | test script | `npm run ci` (local) | CI | Chain |
|---|---|---|---|---|
| `packages/cli` | `test:unit` (vitest) | YES, `manifest.ts:105` | YES, Lane Q | `ci-quality.yml` `quality-packages` / "Run CLI unit tests"; also `run-unit.sh:35` in Lane T |
| `packages/shared` | `test` (vitest) | YES, `manifest.ts:112` | YES, Lane Q | `quality-packages` / "Run shared package tests"; also `run-unit.sh:29` |
| `packages/www` | `test:unit` (vitest) | YES, `manifest.ts:113` | YES, Lane Q | `quality-packages` / "Run www unit tests" |
| `packages/provisioning` | `test` (vitest, 8 cases in `src/ops/OpsManager.group-env.test.ts`) | **NO** | Lane T only | `ct-tests.yml:193` -> `.ci/scripts/test/run-unit.sh:41` |
| `packages/e2e-tests` | `test:unit` (vitest, 4 files under `src/utils/`) | **NO** | Lane T only | `run-unit.sh:47` |
| `packages/e2e-tests` | `test` (playwright) | no | Lane T, per config | section 3 |
| `packages/json` | `test` (`./test-templates.sh`) | **NO** | **NEVER** | no invoker exists |
| `packages/locales` | none | n/a | n/a | data package |
| `workers/www` | `test:unit` (vitest, 3 files) | YES, `manifest.ts:123` | YES, Lane Q | `quality-www-build` / "Worker unit tests (workers/www)" |
| `workers/{account,proxy,mta-sts}` | none | n/a | n/a | no test files exist; not a gap |
| `private/account` | `test` (vitest, ~91 files) | YES, `manifest.ts:201` | YES, Lane Q | chain in "how this audit verified things" |
| `private/account/web` | vitest, 28 files | YES, `manifest.ts:213` | YES, Lane Q | `quality-packages`; config `web/vitest.config.ts:16` |
| `private/account/e2e` | playwright, 94 files | no | Lane T only | `ct-tests.yml:1666` -> `.ci/scripts/test/run-account-e2e.sh:214` |
| `private/renet` | Go | partial (`check:ci-renet` = quality only) | Lane T for tests; Lane Q for one cross-language leg (`ci-quality.yml:1280`) | section 1.3 |
| `private/elite` | none; `scripts/s3-conformance-probe.sh` exists | n/a | **NEVER** (no caller; grep confirms) | started as a service by `.ci/scripts/infra/ci-start-elite.sh:14`, health-probed at `ci.yml:939` |
| `private/homebrew-tap` | none | n/a | n/a | Formula only |
| `eslint-rules/` (38 rule files) | **none exist** | n/a | n/a | section 4.4 |
| `scripts/` | one control harness | YES via `check:i18n` | YES, Lane Q | `package.json` `check:i18n` chains `scripts/__tests__/check-translation-key-usage.control.ts`; `ci-quality.yml` `quality-i18n` |
| `private/growth`, `private/generative` | pytest | n/a | **NEVER** (by design) | not submodules; gitignored at `.gitignore:69-70`; documented at `.ci/scripts/test/gates/test-gate-paths-exist.sh:173` |

**Packages whose test script CI never invokes: exactly one, `packages/json`.**
Packages whose test script the LOCAL gate run never invokes: `packages/provisioning`
and `packages/e2e-tests` (unit). Those two are the honest answer to "wired into CI":
they are in CI, but only in the lane that skips on push and that no parity gate sees.

### 1.3 renet Go tests that no CI path reaches

Reported by a read-only sweep, spot-checked here against the runner script:

- `private/renet/pkg/repodiff/integration_test.go` (`//go:build btrfs`): the btrfs
  tier at `run-tests.sh:173` targets only `./pkg/delta/... ./pkg/chunkstore/...`.
  Its 4 tests run nowhere, and the loud-skip warning at `run-tests.sh:139-147` does
  not even name repodiff, so its absence is silent rather than declared.
- `private/renet/tests/system/{compose_e2e,execute_e2e}_test.go` (`//go:build e2e`):
  no `-tags e2e` invocation exists anywhere.
- `private/renet/tests/system/functions_executor_test.go` (`//go:build system`): the
  only `-tags system` run (`run-tests.sh:79`) filters `-run TestAccountServer`.
- `private/renet/tests/system/subscription_e2e_test.go`: declared-skipped in CI via
  `RENET_EXPECT_NO_ACCOUNT_SERVER` (`ct-tests.yml:1512-1515`). Declared, so honest,
  but zero coverage.
- The **btrfs tier soft-skips** when `mkfs.btrfs`/`losetup` are absent
  (`run-tests.sh:135-151`), and `ct-tests.yml` never installs `btrfs-progs`
  (grep for `btrfs-progs` in that file: zero hits). `pkg/chunkstore/pipeline_integration_test.go`
  and `pkg/delta/*_integration_test.go` are therefore plausibly running nowhere.
  This one matters: see section 5.

All four dark tags are at least COMPILED by
`private/renet/.ci/scripts/quality/deadcode.sh:91` (`TEST_BUILD_TAGS="btrfs root ebpf_e2e e2e system"`),
so they do not rot into non-compiling code. They just never assert anything.

---

## 2. CHECKS THAT CANNOT FAIL

This is the highest-value section. Three instances are proven below by running them
against a planted defect. The class-level fix is in 2.5.

### 2.1 The mutation instrument exists and CI applies it to zero gates

`.ci/scripts/test/mutate-check.sh` is a well-built two-direction mutation runner
(`:1-23`), and `check:ci-mutate-check` (`ci-quality.yml:171`) proves the *runner*
works through five scenarios against a miniature fixture
(`.ci/scripts/quality/check-mutate-check.sh:46-103`). That gate's own header says so
at `:5-12`: it tests the instrument, not gate coverage.

Grep for callers of `mutate-check.sh`: `package.json` (the self-test), the fixture,
the script itself, and one workflow comment. **No production gate is ever mutation-
tested in CI.** Its default `SUITE` is even hardcoded to the worklist hook test suite
(`mutate-check.sh:27`). The repo owns the right instrument and does not point it at
anything.

### 2.2 `check:ci-account-no-admin-role` is blind to the defect it names, PROVEN

The gate body (`package.json`):

```
! grep -rn "enum.*customer.*admin\|enum.*admin.*customer" \
    private/account/src/db/schema.ts private/account/src/types/user.ts 2>/dev/null \
  && echo 'OK: no admin user role'
```

Two independent failures, both demonstrated this session against copies in a
scratch directory (no repo file was modified):

1. **Line-anchored pattern.** Planting `'admin'` into the users role enum in the
   wrapped form
   ```
   role: text('role', {
     enum: [
       'customer',
       'admin',
       'root',
     ],
   })
   ```
   yields `OK: no admin user role`, rc 0. Biome's `lineWidth: 100` (`biome.json:7`)
   already wraps enum objects in this file (`private/account/src/db/schema.ts:94, 416, 508, 559, 588, 594`),
   so the wrapped shape is not hypothetical, only currently short enough to fit.
   The narrower single-line plant IS caught, so the gate is not wholly dead; it is
   dead against exactly the formatting the repo's own formatter produces at length.
2. **Vacuous on a missing path, unconditionally.** In an empty directory the same
   command prints `OK: no admin user role`, rc 0. `grep` exits 2, `!` inverts it to
   success, and `2>/dev/null` discards the "No such file" diagnostic. A submodule
   that is not checked out turns this security gate into a rubber stamp.

`check:ci-account-no-node-env-routes` has failure 2 identically: in an empty tree it
prints `OK`, rc 0.

`.ci/scripts/test/gates/test-gate-paths-exist.sh` is the gate that would normally
catch a hardcoded path that stopped resolving, but its `scan_targets` (`:109-120`)
runs exactly three `find` calls, over `scripts/`, `packages/www/scripts`, and
`.ci/scripts`. **It never reads `package.json`**, so inline gate bodies are precisely
the class of path constant it cannot see.

### 2.3 `check:ci-tutorial-render-queue` runs only its own fixture, and a gate test locks that in

`package.json`: `check:ci-tutorial-render-queue` = `node packages/www/scripts/list-tutorial-render-pairs.js --selftest`.
`main()` at `list-tutorial-render-pairs.js:274-276` returns from `selftest()` before
ever calling `listRenderPairs(opts)` at `:278`. Run this session: 10 fixture PASSes,
zero bytes of the real tree read.

The manifest declares this honestly (`manifest.ts:249`, a `kind: 'test'` BLOCKER
stating the ledger only exists after the pipeline runs), so this is a *documented*
choice, not a lie. But `.ci/scripts/test/gates/test-tutorial-render-queue.sh:98-110`
(`test_gate_runs_the_selftest`) asserts that the npm gate MUST invoke `--selftest`,
which pins the fixture-only form in place. If the real predicate ever became runnable
in CI, a gate would resist the fix.

Shape to name and avoid: **a `kind: 'test'` BLOCKER whose evidence line is a selftest
run rather than a real scan**. `check-ci-parity.ts:37-42` warns about exactly this
("Mentioning a script is not executing it"), and this is the one entry where the
declared evidence is a fixture.

### 2.4 Vacuous empty-set passes, verified in source

- `.ci/scripts/quality/check-go-deps.sh:159-162`: `GO_DIRS` is globbed from
  `private/*/go.mod` (`:154-157`); an empty set logs "No Go submodules found to
  check" and exits 0. Its siblings `check-renet-types.sh` and `check-renet-tier-map.sh`
  ARE in the anti-vacuity registry for this exact shape; `check-go-deps.sh` is not.
- `.ci/scripts/quality/check-no-otlp-creds.sh:47-49` and `:117-120`: no renet binary
  found, or no `packages/cli/dist/cli-bundle.cjs`, and the credential-leak gate warns
  and proceeds. Its error tally is then computed over zero inspected artifacts and it
  reports success. It runs at `ci-build-renet.yml:130-131`, where the binaries do
  exist, so it is not currently vacuous in CI. It is one job re-ordering away.

### 2.5 The anti-vacuity meta-gate covers 26 of 114

`.ci/scripts/test/gates/test-gate-anti-vacuity.sh` is the right idea: point a
validator at an empty tree and require a non-zero exit. Its `REGISTRY` (`:47-244`)
holds **26 entries**. The repo defines **114** `check:ci-*` scripts. The registry is
hand-maintained, so the coverage ratio decays with every gate added.

Its own control, `test_registry_is_not_empty` (`:314-321`), asserts
`${#REGISTRY[@]} -ne 0` against a source literal. That is a compile-time constant: it
can only fail if someone deletes the array in the same edit. It is the "control that
asserts a hardcoded array's length" shape the operator named. The file's real control
is `test_harness_catches_a_vacuous_validator` (`:339-356`), which does plant a fixture
and does fire; the registry-emptiness check adds nothing.

### 2.6 Gate scripts with no control at all

Reported by sweep, not individually re-run here: roughly 20 gate scripts carry
neither a `--selftest` nor an inline control, including
`check-audit-coverage.sh`, `check-cli-contract.sh`, `check-command-tree.sh`,
`check-compose-env.sh`, `check-e2e-coverage.sh`, `check-go-deps.sh`,
`check-lockfile.sh`, `check-npmrc.sh`, `check-peer-deps.sh`, `check-release-state.sh`,
`check-renet-types.sh`, `check-renet-tier-map.sh`, `check-subscription-schema.sh`,
and all of `.ci/scripts/security/` (`actionlint.sh`, `audit.sh`, `check-commands.sh`,
`check-workflow-gates.sh`, `shellcheck.sh`, `shfmt.sh`). Several are covered
externally by a `gates/` test; the residue is the list to attack.

---

## 3. E2E: WHAT CI COLLECTS, AND THE FOUR FILES IT DOES NOT

37 `*.test.ts` files exist under `packages/e2e-tests/tests/`. `check:ci-e2e-coverage`,
run this session, expands the 7 live configs into **33 distinct test files**. The four
that no live config selects:

| File | Reason | Documented in README "Deliberately not in CI"? |
|---|---|---|
| `tests/20-image-build.test.ts` | `playwright.config.ts:96` excludes on `CI` | YES, item 3 (`README.md:48-50`) |
| `tests/23-cli-migrate-routing.test.ts` | `playwright.config.ts:103-105`, and no matrix leg sets `cli-suite: '1'` | YES, item 8 (`README.md:102-108`) |
| `tests/26-backup-storage-cli.test.ts` | `playwright.config.ts:117-119`, `BACKUP_STORAGE_SUITE` set nowhere in the repo | YES, item 7 (`README.md:68-100`) |
| `tests/ops-lifecycle/18-ops-lifecycle.test.ts` | `playwright.config.ts:30` `testIgnore`, and **no dedicated config exists** | **NO** |

Plus one describe block excluded at runtime and undocumented:

- `tests/kube/24-cluster-licensing.test.ts:413` "rdc cluster licensing on the fleet"
  (6 tests, `:491-635`) is removed by `--grep-invert "licensing on the fleet"`
  (`ct-tests.yml:1114`). The reasoning is written at length in the workflow
  (`:1082-1100`) but suite 24 appears nowhere in the README's list.

### 3.1 The ops-lifecycle orphan, and a coverage claim that is false

`tests/ops-lifecycle/18-ops-lifecycle.test.ts` holds 10 tests. Its own header
(`:15-18`) claims "The ops lifecycle itself IS exercised in CI by the dedicated OPS
Tests job (`.github/workflows/ci-ops-test.yml` drives the ops lifecycle verbs up/status/down plus a "reset" that DOES NOT EXIST
on throwaway VMs), so excluding these playwright wrappers loses no CI coverage."

`ci-ops-test.yml` drives `ops setup` (`:168`), `ops check` (`:171`), `ops up --basic`
(`:175`), `ops status` (`:178`), `ops up --skip-orchestration` (`:224`), and
`ops down` (`:303`). It never runs an ops "reset" verb, and it could not: the single occurrence of the string
"reset" in that file is `preset: readonly` at `:52`.

So the orphan's two reset tests (`:170` "should perform soft reset", `:195` "should
have clean state after reset") are the only automated coverage of an ops "reset"
verb anywhere in the repo, and they execute in no configuration. Worse than
untested: VERIFIED 2026-08-15, that verb DOES NOT EXIST. command-tree.json gives
ops exactly up, down, status, ssh, setup and check, and no `command('reset')`
appears anywhere in packages/cli/src. So the two tests exercise a phantom, and
the file header at :16 asserts CI coverage of it.

The listed README entry that should cover this is stale in both halves. Item 4
(`README.md:52-54`) reads: "**Suite 18 ops-workflow destructive VM tests.**
Self-skipped in CI by design (`tests/18-ops-workflow.test.ts`)". That file is 35
lines, holds one `test.describe('Parallel Execution @bridge @ops')`, contains no
skip, and RUNS in CI as project `test-18` (`playwright.config.ts:93`). The
destructive tests moved to the `ops-lifecycle/` subdir and the README anchor never
followed.

### 3.2 Why no gate catches this

- `scripts/check-e2e-skip-hygiene.ts` checks one direction only: every test-bearing
  subdir of `tests/` must appear in the base config's `testIgnore` (`:72-84`). An
  orphan subdir passes by construction. Its own docstring (`:6-11`) asserts the
  invariant that is actually violated: each topology subdir "has a dedicated
  `playwright.<topology>.config.ts` that scopes to it". There is no
  `playwright.ops-lifecycle.config.ts`; the 8 configs on disk are ceph, ceph-workers,
  base, image, k8s-ceph, k8s-multinode, k8s, migrate.
- `.ci/scripts/quality/check-e2e-coverage.sh` measures *renet-verb* coverage against
  the live-config registry, not test-file membership. Its output even prints "33
  distinct test file(s)" without knowing 37 exist.
- Neither gate reads the README, so "Deliberately not in CI" is prose with no
  enforcement behind it.

---

## 4. GAPS BY CONSEQUENCE

Ranked by what a defect would cost. Silent data loss first, a red CI run last.

### 4.1 SILENT DATA LOSS: no deletion path has ever run against a real object store

Every site in the backup program that destroys data lives in
`private/account/src/services/backup-gc.service.ts`:

| Call | Line | What it destroys |
|---|---|---|
| `gcSubscriptionChunks` -> `await store.delete(toDelete.map((o) => o.key))` | `:283` | unreferenced chunks, guarded by `referenced`/`pinned`/grace at `:271-274` and the `lineageReadable` fail-safe at `:260-263` |
| `pruneManifests` | `:486`, `:491` | manifest rows, then manifest objects, after re-parenting rewrites at `:472-487` |
| `orphanManifestSweep` -> `store.delete(orphans)` | `:707` | orphaned manifests |
| `deleteSubscriptionBackups` -> `store.deletePrefix(tenantPrefix)` | `:819`, plus 7 table deletes `:829-831` | an entire tenant |
| `sweepExpired` | `:157-166` | lease/pin/session rows |

renet's local-disk equivalent: `private/renet/pkg/prune/datastore.go:926` and `:1090`
(`pruneStaleBackupAnchors`), and `.restore-*` staging reclamation at `:798`.

These are covered by 12 cases in `private/account/tests/integration/backup-gc.test.ts`
and 22 in `backup-retention.test.ts`, which run in Lane Q on every push. That is real
coverage, and it is all in-process: **`store` is an in-memory fake in every one of
them.** No test, drill, or e2e suite has ever executed a `store.delete` or
`deletePrefix` against RustFS or R2.

The backup drill is the closest thing and does not close it. `scripts/drills/backup.sh`
runs 86 assertions across legs a,b,c,d,e,f,g,h,j,k (`:95`) with a live RustFS on the
box the whole time, and its only prune leg is
`renet repository prune --datastore ... --dry-run --output json` (`:1141`). Nothing is
deleted. No account GC entry point is called. Suite 26 has no GC tier.

**Consequence:** an S3-semantics defect in the delete path (prefix scoping, batch
size, pagination on `deletePrefix`, a key-encoding mismatch between write and delete)
is undetectable by anything in this repo, and the blast radius of `deletePrefix` is
one tenant's entire backup history.

### 4.2 SILENT DATA LOSS: `rdc backup retention set|clear` has no behavioural test

`packages/cli/src/commands/backup-storage.ts:381` (`set`) and `:428` (`clear`) are the
operator's only handle on which snapshots the server will delete.
`packages/cli/src/commands/__tests__/backup-storage.test.ts` covers `usage` (`:84`),
`verify` (`:118`), and `manifests` (`:150`). Retention is absent. The only protection
is `check:ci-retention-knob-parity` (`ci-quality.yml:558`), which compares spellings
across four layers, not behaviour.

**Consequence:** a wrong flag-to-field mapping silently widens what
`retentionPolicySweep` (`backup-gc.service.ts:640`) deletes. The user typed a correct
command and lost the snapshots they asked to keep.

### 4.3 SILENT WRONG SCOPE: point-in-time restore resolution is untested

`packages/cli/src/commands/backup.ts:329` (`resolveSnapshotAt`) and `:363`
(`runChunkRestore`) have **zero test references anywhere in the repo**. Grep across
`packages/` and `private/account/` returns only their definition sites, the one call
site at `:241`, and a doc comment in `backup-storage.ts:57`.

This is the code that turns `--at <time>` into a snapshot id. A boundary error
restores the wrong point in time, and the restore SUCCEEDS, so nothing surfaces the
mistake. The only test that touches it is suite 26's RESTORE tier, which never runs.

### 4.4 SILENT WRONG SCOPE: 38 eslint rules with no tests

`eslint-rules/` holds 38 rule implementations (22 at the top level plus
`eslint-rules/i18n/`) and no test files and no `package.json`. They are exercised only
transitively, by ESLint passing over the repo. Load-bearing rules such as
`no-hardcoded-cli-text.js` and `translation-coverage.js` are exactly the kind that go
quiet on a refactor: an AST selector that stops matching produces a GREEN lint run.
`.ci/scripts/quality/check_lint_rule_liveness.py` exists as a partial answer; whether
it covers all 38 was not verified here (see section 7).

### 4.5 A RED CI RUN, or the absence of one

- **`packages/json` templates.** Never tested. Confirmed unwireable today: every
  Rediaccfile calls `renet compose`, which fails with "--network-id is required" on a
  bare fleet member, so the suite needs a licensed repo on a VM. This is an open
  operator decision, not an oversight, and it is the one item in this plan that is
  correctly left as an ask.
- **`private/elite/scripts/s3-conformance-probe.sh`** has no caller. Elite is the S3
  backend the backup program writes through; a conformance probe that never runs is
  the one that would have caught 4.1's class.
- **`packages/provisioning` and `packages/e2e-tests` unit tests** run in Lane T only,
  so a push to main never runs them, and `npm run ci` never runs them locally either.
- **The `drill backup` log is not uploaded on failure.** `ct-tests.yml:1818` tees to
  `$RUNNER_TEMP/drill-backup.log`; the artifact block at `:1828-1831` lists only
  `drill-universe.log` and `drill-transfer.log`, with `if-no-files-found: ignore`
  (`:1833`) so the omission is silent. The newest drill is the one whose failures
  arrive without evidence.
- **`drill backup` does not run on a renet-only change.** `.ci/scripts/ci/scope-map.cjs:295`
  sets `drills: ['cli', 'shared', 'account']`. The submodule holding the chunk engine
  and the restore path is not a trigger for the drill that exercises them.

---

## 5. COVERED ONLY BY A GATED OR SOFT-SKIPPING TIER

These surfaces have tests. The tests do not run.

| Claim the program rests on | Only test | Why it does not run |
|---|---|---|
| **Byte-identical cross-machine restore** | `tests/26-backup-storage-cli.test.ts:715` ("a restore onto a second machine is BYTE-IDENTICAL"), RESTORE tier `:182-202` | `playwright.config.ts:117-119`; `BACKUP_STORAGE_SUITE` is set in no workflow, script, or package.json |
| Real renet chunk upload, machine to bucket | suite 26 ENGINE tier `:146-151`, tests `:466-560` | same gate |
| FIEMAP / reflink / incremental-equals-full-rehash | `private/renet/pkg/chunkstore/pipeline_integration_test.go` (`//go:build btrfs`), `TestIntegration_PipelineIncrementalMatchesFullRehash:152` | `run-tests.sh:135-151` soft-skips without `mkfs.btrfs`/`losetup`; `ct-tests.yml` never installs `btrfs-progs` |
| repodiff precise-vs-fast agreement | `pkg/repodiff/integration_test.go`, 4 tests | btrfs tier's package list excludes repodiff entirely; not even named in the skip warning |
| cluster licensing on a real fleet (a SUITE name, not a CLI verb: cluster has no `licensing` subcommand) | `tests/kube/24-cluster-licensing.test.ts:491-635` | `--grep-invert` at `ct-tests.yml:1114` |
| an ops "reset" verb (which does not exist) | `tests/ops-lifecycle/18-ops-lifecycle.test.ts:170,195` | no config selects the file |

The RESTORE tier is the load-bearing one. The whole backup program's promise is that
a restore on a different machine reproduces the bytes. Today that promise is asserted
by exactly one test, and CI has never collected it. What CI does verify is adjacent
and real but weaker: renet's own restore unit tests
(`pkg/chunkstore/restore_test.go`, including `TestRestore_ByteIdenticalWithShortTailAndHoles:232`
and `TestRestore_ResumeAfterAKillFinishesWithTheSameBytes:482`) prove the reassembler
in-process, and drill leg d (`backup.sh:1004-1030`) proves SHA-256 equality end to end
but through the drill's OWN shell/node reassembler (`restore_snapshot()` at `:948`),
not through `pkg/chunkstore/restore.go`. The integration seam between them is the
untested part.

The drill's synthetic data plane deserves stating plainly, because it is easy to read
86 green assertions as more than they are. Fixture cells and hashes come from a
heredoc node helper written at run time (`backup.sh:481-482`, `image_js()` at `:553`);
the manifest document is hand-built by a second inline script (`manifest_body()` at
`:738-744`); uploads are `curl` PUTs; leg h is a hand-transcribed replica of renet's
wire shapes pinned to `session.go` by file:line comments (`:1202-1250`). The only leg
that runs the `renet` binary at all is leg g. The drill's own header says this at
`:59-77`. It is an excellent control-plane test and it is not an integration test.

---

## 6. PROPOSED FIXES

Ordered by consequence. Each names the DEFECT it catches, WHERE it lands, and HOW
someone proves it can fail. Every one of these is a new gate or a wiring change;
none requires new product code.

### F1. A GC leg against the live RustFS in `drill backup`

- **Defect caught:** any S3-semantics error in `store.delete` / `deletePrefix`
  (prefix scoping, pagination, key encoding, batch limits). Today: undetectable.
- **Lands in:** a new leg `l` in `scripts/drills/backup.sh`, after leg k. The drill
  already has a live RustFS and a committed manifest with real chunk objects. Call
  the account server's TEST_MODE maintenance hook (`private/account/src/routes/test.ts:1077`)
  to drive `runMaintenance` (`backup-gc.service.ts:115`), then assert against the
  bucket: unreferenced chunks gone, referenced chunks PRESENT, pinned chunks PRESENT.
- **Proof it can fail:** the leg must carry a `--selftest` mode that inverts the
  guard (mark a referenced chunk unreferenced) and requires the leg to go RED. Also
  run it under `mutate-check.sh --file backup-gc.service.ts --from '!referenced' --to 'false'`
  and require a red. The keep-assertions are the control: without them a `delete`
  that removes everything passes.
- **Cost note:** this is the single highest-value item in the plan. It converts the
  top data-loss risk from untested to tested, and it rides infrastructure that
  already runs in CI on every PR.

### F2. Behavioural tests for `rdc backup retention set|clear`

- **Defect caught:** a flag-to-field mapping that changes what the server deletes.
- **Lands in:** `packages/cli/src/commands/__tests__/backup-storage.test.ts`, matching
  the existing `describe`/`it` shape at `:84-165`. Assert the exact PUT body sent to
  `/backups/retention` for each flag combination, and that `clear` sends the clearing
  shape rather than an empty object.
- **Proof it can fail:** swap two field names in `backup-storage.ts:381` and require
  the suite to go red. Mechanically: `mutate-check.sh --file packages/cli/src/commands/backup-storage.ts --from <field> --to <other field>`.

### F3. Tests for `resolveSnapshotAt`

- **Defect caught:** off-by-one at a snapshot boundary; restoring the wrong point in
  time silently and successfully.
- **Lands in:** a new `describe('backup restore --at')` in the same CLI test file.
  Table-drive it: `--at` exactly on a snapshot timestamp, one second before, one
  second after, before the first snapshot (must refuse), after the last (must pick
  the last). The "before the first" refusal is the control.
- **Proof it can fail:** flip `<=` to `<` in `backup.ts:329`'s comparison and require
  a red.

### F4. A gate: every e2e test file is selected by a live config or listed as deliberate

- **Defect caught:** the ops-lifecycle orphan class. A test file nobody deletes and
  nobody runs.
- **Lands in:** extend `scripts/check-e2e-skip-hygiene.ts` (it already parses configs
  and walks `tests/`). Add a second direction: enumerate every `*.test.ts` under
  `tests/`, expand every `playwright*.config.ts` projects array, and require each file
  to be either selected by at least one config or named in a machine-readable
  deliberate-omission list. Make that list the README's own section, parsed, so
  "Deliberately not in CI" becomes enforced prose rather than prose.
- **Proof it can fail:** the gate ships with a control that adds a fabricated
  `tests/nowhere/99-x.test.ts` to a fixture tree and requires a non-zero exit, in the
  style of `test-gate-anti-vacuity.sh:339-356`. Additionally, run it once on the
  CURRENT tree before fixing anything: it must report `ops-lifecycle/18-ops-lifecycle.test.ts`.
  A new gate that is green on its first run against a tree with a known violation is
  a gate that does not work.
- **Immediate finding it will force:** either give `ops-lifecycle/` a dedicated
  config, or document it; and correct README item 4's stale anchor and its false
  "self-skipped" mechanism, and add suite 24's fleet tier.

### F5. `check-ci-parity` extended to Lane T, or an explicit test-lane manifest

- **Defect caught:** a test suite that exists, runs in one lane only, and is invisible
  to the gate that exists to prevent exactly that. Concretely today:
  `packages/provisioning` and `packages/e2e-tests` unit tests.
- **Lands in:** `scripts/ci-runner/manifest.ts`. Two options, and the second is the
  recommendation:
  - Widen `ENTRY_JOBS` (`:482`) to include `tests`. This drags every e2e and drill
    invocation into the parity relation and will produce a large exemption list,
    which the file's own design note at `:487-494` argues against.
  - **Recommended:** add `check:test-provisioning` and `check:test-e2e-unit` npm
    scripts, give them manifest entries with `ci: { kind: 'step', workflow:
    '.github/workflows/ci-quality.yml', ... }`, and move those two vitest runs into
    `quality-packages` beside the other three. They are seconds-scale (8 cases and 4
    files). This makes them run on push, run locally under `npm run ci`, and become
    subject to R1/R2/R3 without widening the surface. `run-unit.sh` keeps its calls;
    the duplication is cheap and the existing manifest already accepts that trade for
    four i18n gates (`manifest.ts:86-91`).
- **Proof it can fail:** delete the new manifest entry and require `check:ci-parity`
  to report an R2 finding; delete the workflow step and require an R3 finding. Both
  directions are already exercised by that gate's own controls.

### F6. A mutation registry: point the instrument at real gates

- **Defect caught:** the whole class. A gate that runs, prints green, and would print
  green with its subject broken.
- **Lands in:** a declared registry, in the manifest rather than a new file, since
  `check-ci-parity` already enforces manifest hygiene. Add an optional
  `mutation?: { file: string; from: string; to: string }` to `GateSpec`
  (`manifest.ts:27-58`). A new `check:ci-gate-mutation` iterates entries that declare
  one, runs `mutate-check.sh`, and requires RED-then-GREEN. Start with the gates whose
  failure is a security or data-loss event, not with all 114: the four backup gates
  (`ci-quality.yml:546-558`), `check-no-client-key-composition`,
  `check-backup-protocol-conformance`, `check-backup-manifest-shape-parity`,
  `check-retention-knob-parity`.
- **Proof it can fail:** it is self-proving by construction, which is the point of
  choosing mutation over inspection. A gate that has gone blind produces a GREEN
  mutant run and the check reports "does not detect this defect"
  (`check-mutate-check.sh:71-79` already pins that exact diagnostic).
- **Second-order:** add a coverage floor so the registry cannot decay the way
  `test-gate-anti-vacuity.sh`'s has. Not a hardcoded count: require that every gate
  whose manifest entry declares `paths` touching `private/account/src/services/backup-*`
  or `packages/shared/src/**/backup*` carries a `mutation` entry. Rule-based, so a new
  backup gate is enrolled by existing.

### F7. Replace the two inline-`grep` account gates with real scripts

- **Defect caught:** the proven blindness in 2.2, both halves.
- **Lands in:** `.ci/scripts/quality/check-account-role-enum.sh` (and one for
  NODE_ENV), replacing the `package.json` one-liners. Requirements: fail if the target
  file does not exist (never `2>/dev/null` a missing path into a pass), and parse the
  enum array rather than line-matching, so wrapping is irrelevant.
- **Proof it can fail:** a `gates/test-account-role-enum.sh` with three cases: the
  single-line plant (must fail), the wrapped plant from 2.2 (must fail), and a clean
  tree (must pass, the control). The wrapped fixture is already written and reproduced
  in section 2.2.
- **Also:** extend `test-gate-paths-exist.sh`'s `scan_targets` to read `package.json`
  script bodies, so no future inline gate can carry an unresolvable path.

### F8. Anti-vacuity registry by rule, not by hand

- **Defect caught:** decay. 26 of 114 today, and the ratio only worsens.
- **Lands in:** `.ci/scripts/test/gates/test-gate-anti-vacuity.sh`. Replace
  `test_registry_is_not_empty` (`:314-321`, which cannot fail) with a coverage
  assertion: every `check:ci-*` gate whose leaves include a `.ci/scripts/quality/check-*.sh`
  or `scripts/check-*.ts` must either be in `REGISTRY` or carry a BLOCKER-tagged
  exemption. Add `check-go-deps.sh` and `check-no-otlp-creds.sh` to the registry as
  part of the same change, since both are proven vacuous on an empty input (2.4).
- **Proof it can fail:** add a fabricated `check:ci-fake` npm entry pointing at a
  new script and require the meta-gate to report it as unregistered.

### F9. Wire the btrfs tier, or declare it

- **Defect caught:** an incremental chunker that diverges from a full rehash. The
  test exists (`pipeline_integration_test.go:152`) and quietly does not run.
- **Lands in:** `ct-tests.yml` `test-renet` job: add an `apt-get install -y btrfs-progs`
  step before `run-renet.sh test`, and add `./pkg/repodiff/...` to the btrfs tier's
  package list at `run-tests.sh:173`. If the runner genuinely cannot host a loopback
  btrfs image, then convert `run-tests.sh:135-151`'s soft skip into a DECLARED skip
  requiring an env var, in the pattern the drills already use
  (`RENET_EXPECT_NO_ACCOUNT_SERVER`, `ct-tests.yml:1512-1515`), so the absence is
  loud.
- **Proof it can fail:** with the install step in place, break
  `pkg/chunkstore/pipeline_linux.go`'s incremental path and require a red. Before
  that, prove the tier currently does NOT run by grepping a CI log for the skip
  warning at `run-tests.sh:139-147`.

### F10. Three small wiring fixes

- **`drill-backup.log` on failure.** Add `${{ runner.temp }}/drill-backup.log` to the
  artifact path list at `ct-tests.yml:1831`. Proof it can fail: force the leg red on a
  branch and confirm the artifact contains three logs.
- **Drill scope for renet.** Add `renet` to `drills:` at `.ci/scripts/ci/scope-map.cjs:295`.
  Proof: `test-scope-engine.sh` already drives the scope map; add a case asserting a
  `private/renet/**` change selects `drills`.
- **Elite S3 conformance probe.** Call `private/elite/scripts/s3-conformance-probe.sh`
  from the job that already starts elite (`.ci/scripts/infra/ci-start-elite.sh:14`,
  invoked from `ci.yml:939`). Proof: point it at a deliberately non-conformant stub and
  require a red. This is the cheapest partial mitigation for 4.1 while F1 is built.

---

## 7. WHAT THIS AUDIT DELIBERATELY LEFT OUT, AND THE COST

- **Suite-level quality of the ~91 account vitest files and the 94 account e2e
  Playwright files.** Membership was traced; assertion strength was not. Cost: a suite
  that runs but asserts weakly reads as coverage here. The mutation registry (F6) is
  the general answer and is scoped in this plan to the backup gates only.
- **Whether `check_lint_rule_liveness.py` covers all 38 eslint rules.** Named in 4.4
  as a partial answer; not verified. Cost: 4.4 may be smaller than stated. It cannot
  be larger, since no rule has a unit test.
- **`packages/www` content, SEO, tutorial and video gates** (roughly 20 `check:ci-*`
  entries). They are in Lane Q and green; their failure mode is a bad page, not lost
  data. Cost: some of them are likely vacuous in the 2.4 shape (skipping when a build
  artifact or media manifest is absent). F8's rule-based registry will surface them
  without anyone auditing them by hand, which is why it is scoped as a rule.
- **`private/growth` and `private/generative` pytest suites.** Separate repos, not
  submodules, deliberately outside console CI. Cost: none to this repo; those
  pipelines carry their own risk.
- **Actually running the e2e suites or the drills.** This audit ran `check:ci-parity`,
  `check:ci-e2e-coverage`, `check:ci-tutorial-render-queue`, and
  `check:ci-account-no-admin-role` (plus planted-defect variants of the last, against
  scratch copies). It did not run the playwright suites or `./run.sh drill backup`,
  both of which need a fleet or an account server. Cost: section 5's claims about what
  suite 26 would prove rest on reading it, not on watching it pass. That is the right
  cost to accept, because the finding is that CI never watches it either.
- **`packages/json`.** Left as the operator ask it already is. Cost: template
  regressions ship unnoticed. Wiring it needs a licensed rediacc repo on a VM, which
  is an infrastructure decision, not a gate.

## 8. NO BLOCKERS

Nothing prevented this audit. The tree was still, every anchor cited resolves, and
every gate cited was run or read in full. The three "cannot fail" instances in section
2 were each demonstrated against a planted defect in a scratch directory; no file in
the repository was modified by this audit.
