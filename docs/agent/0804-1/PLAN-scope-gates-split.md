# PLAN: narrow the `scripts/` harness rule in the CI scope map

**Status: APPROVED by the operator 2026-08-06 ("go with the recommendation").
Land D+F together, AFTER wave 0804-1 / PR #551 closes. Not started.**

## What was approved

- **D** — split `scripts-harness` so gate sources stop forcing the full infra
  matrix, with two carve-outs that stay `full`.
- **F** — correct the comment at `scope-map.cjs:172`, which gives the WRONG
  reason for the rule (it cites gate-immunity, which the workflow already
  guarantees independently). A comment that misstates why a conservative rule
  exists is how the rule later gets removed for bad reasons.
- All four mutations below. **M4 is non-negotiable**: it pins the ZERO-JOB
  property, so a future edit adding `gates` to a `JOB_SURFACES` entry cannot
  silently undo the change while every test row still reads `reduced`.

## Why the timing

PR #551 already carries 324 files and an open flaky-CI investigation
(worklist #ef44bba8) whose whole method is distinguishing "battery executed"
from "battery cancelled". Changing what CI schedules mid-investigation muddies
the only instrument for that. This is a clean standalone PR once #551 lands.

## Operator-verified claims (re-checked by the lead, not taken on report)

- `ci-quality.yml` contains **zero** `run_` references, so quality lanes are not
  scopeable at all. This is the whole safety argument and it is structural.
- `scope-map.cjs:294` is `RULES.find(...)` — first-match-wins, so rule ORDER is
  load-bearing.
- `package.json` is a ROOT_MANIFEST (`scope-map.cjs:75`) → full. This is the
  ceiling on the expected value.
- `ct-tests.yml:1787` runs `./run.sh drill universe` → `run.sh:1987` →
  `scripts/drills/universe.sh`. The drills carve-out is real, confirmed by hand.

## Honest expected value

**1.28% of commits** (29 of 2263) newly skip the infra matrix; ~0.36 min of
wallclock per commit, but ~10,200 job-minutes across the sample — the
job-minutes figure is the better argument. The per-PUSH rate is plausibly
several times higher (single-file gate tweaks are over-represented during a
babysit loop) but that was NOT measured and must not be counted as benefit.

The real reason to land it is that it removes a class of result — "an
Apache-2.0 attribution-string check ran a ceph fork test" — that makes the
scope engine look untrustworthy even when it is working correctly.

---

# The plan as written by the planning agent


I have everything. Here is the plan.

## Verdict

**Do the split, and it is bigger and safer than "a narrow subset".** Almost all of root `scripts/` can be narrowed. Exactly two subsets must stay full, and I found both by tracing execution, not by reading names. But the honest expected value is small: **1.28% of commits** flip, because gate work almost always drags `package.json`/`.ci/`/`.github/` along, and those force full independently.

---

## 1. The structural fact that makes this safe (verify this first, everything rests on it)

The scope engine can only turn off the 18 `JOB_SURFACES` keys. **No quality lane is among them.** `.github/workflows/ci-quality.yml` contains zero `run_` references (grepped; empty result). The gated jobs are exactly 13 in `ct-tests.yml` (`:185, :197, :394, :527, :669, :804, :945, :1144, :1307, :1467, :1598, :1638, :1730`) and 5 in `ci.yml` (`:691, :707, :863, :884, :1247`).

Ungated, therefore always running: **every quality gate, every build job, docker, dry-run, release-state, and `Validate Promotion`** (the new ~47-52 min tail you measured).

So **constraint 1 is satisfied structurally, not by rule design**: a `scripts/` rule cannot scope out a quality gate because quality gates are not scopeable at all. The comment at `scope-map.cjs:172-175` describes this correctly but then draws the wrong conclusion from it: it cites gate-immunity as the reason for `full`, when gate-immunity is already guaranteed by the workflow. The actual load-bearing half of that comment is the second clause, "these also feed hooks and dev flows whose surface is unmapped", and that is what I mapped.

---

## 2. Taxonomy: what actually lives under `scripts/`

| Subset | Files | Reachable from a gated job? | Verdict |
|---|---|---|---|
| 43 top-level `check-*.ts` | e.g. `check-embed-credits.ts`, `check-cli-docs.ts`, `check-external-links.ts` | No. Every one runs only via a `check:ci-*` npm script in `ci-quality.yml` (steps `:394`-`:1082`) | **narrow** |
| `scripts/lib/` (9) | `blocker-validator.ts`, `positional-cli-detector.ts`, `release-age.ts`, `suppression-liveness.ts`, `action-refs.ts`, `command-path-checker.ts`, `dockerfile-versions.ts`, `nis2-langs.ts`, `embed-asset-sources.ts` | No. Imported only by the `check-*.ts` gates, plus `.ci/scripts/test/gates/test-positional-detector.sh:35` and `.ci/scripts/quality/check-command-tree.sh:7` (both quality) | **narrow** |
| `scripts/utils/` (3) | `console.ts`, `crc32.ts`, `translation-diff.ts` | No external consumer at all | **narrow** |
| `scripts/data/` (15) | NIS2 snapshots, `locale-de-contamination-baseline.json` | Read by 2 quality gates only | **narrow** |
| `scripts/ci-runner/` (5) | `manifest.ts`, `run.ts`, `pool.ts`, `exec.ts`, `report.ts` | No. `npm run ci` is deliberately never run by a workflow (`ci-quality.yml:615` documents why). Its code is CI-*tested* by `test-ci-runner.sh` (quality) | **narrow** |
| `scripts/dev/` (11) | `scrub-sentinel.sh`, `worktree.sh`, `deploy-bench.sh`, `backup-d1.sh`, ... | No. `scrub-sentinel.sh` is **named in error text only**, never invoked (`upload-to-r2.sh:223`, `release-state-validator.sh:341`, `assert-r2-sentinel.sh:66`, `cleanup-versions.sh:1258` are all `log_error` strings). Tested by a quality gate | **narrow** |
| `scripts/docker/build-server.sh` | 1 | No. Only Dockerfile *comments* (lines 12, 32); the docker build job uses the Dockerfile directly, and is ungated anyway | **narrow** |
| `pre-commit-check.sh`, `tsconfig.json`, remaining generators (`generate-embed-credits.ts`, `generate-translation-hashes.ts`, `sign-regions.ts`, `generate-update-index.ts`, `fetch-directive-snapshot.ts`, `sync-translations.ts`, `i18n-*.ts`) | 9 | No. `tsconfig.json` feeds `npm run typecheck` (`ci-quality.yml:433`); the rest are local generators or dead | **narrow** |
| **`scripts/drills/`** (4) | `lib.sh`, `universe.sh`, `transfer.sh`, `license.sh` | **YES.** `ct-tests.yml:1730` job `test-drills` (gated by `run_drills`) executes `./run.sh drill universe` (`:1787`) and `drill transfer` (`:1801`), which dispatch to `run.sh:1987`/`:1991` → these files; all three source `lib.sh` | **STAYS FULL** |
| **`scripts/generate-third-party-licenses.ts`** | 1 | **YES, indirectly and worse.** `.ci/scripts/build/prepare-cli-assets.sh:190` runs it, reached from `build-cli-executables.sh:123` (SEA build). Its output is `packages/cli/src/data/third-party-credits.json`, which **ships inside the CLI binary**. The build job is ungated so a *throw* is caught, but a silently-wrong credits file is caught by `install_methods`/`package_tests`, which are gated | **STAYS FULL** |

**Things I checked and ruled out as counterexamples:**
- `packages/cli/src/config/__tests__/plane-leaf-rule.test.ts:28` imports `'../../../scripts/lib/plane-rules.js'` and `packages/www/src/utils/solution-video.ts:3` imports `'../../scripts/lib/update-video-manifest.ts'`. Both resolve to **package-local** `packages/cli/scripts/lib/` and `packages/www/scripts/lib/` (confirmed both directories exist with those files). `matchPrefix('scripts/')` never matches them. No unit test reaches root `scripts/`.
- `ci.yml:576, :1093, :1128` reference `scripts/setup-sandbox.ts` and `scripts/preview-turnstile.ts`, but every one carries `working-directory: private/account`. Neither exists at root.
- `npm ci` pulls in nothing: the root `package.json` has no `prepare`/`postinstall`/`preinstall`/`prepack` key, and `setup-workspace/action.yml` runs only `.ci/` scripts plus `npm run install:natives` (pure `npm rebuild`).
- The `ops` job reaches tutorials via `.ci/tutorials/`, not `scripts/`. `ct-tests.yml` has exactly one `npm run` in the whole file (`:1656`, `build:packages`); `ci-ops-test.yml` has three, all `build -w @rediacc/cli`.

---

## 3. The rule shape

**Order is first-match-wins**: `RULES.find((r) => r.match(path, ctx))` at `scope-map.cjs:294`. Verified, and already load-bearing (`ci-lib` before `ci-harness`), and already tested (`test-scope-engine.sh:126-149`).

Add one module to `KNOWN_MODULES` (`scope-map.cjs:26-41`), after `devcontainer`:

```js
  // Quality-gate sources: scripts/**, minus the two subsets below that a gated
  // job actually executes. A ZERO-JOB module, like `docs` and `devcontainer`:
  // no JOB_SURFACES entry names it, so it pulls nothing into scope. That is
  // correct rather than lazy, because every consumer of these files is a
  // quality lane, and quality lanes carry no run_* gate in ci-quality.yml at
  // all. Deliberately NOT `docs`: a future edit that gives `docs` a job surface
  // must not silently drag the gate sources with it.
  'gates',
```

Replace the single line at `scope-map.cjs:176` with three rules, in this order:

```js
  // scripts/drills/*.sh are EXECUTED by the gated `Drills` job:
  // ct-tests.yml:1730 -> ./run.sh drill universe|transfer (:1787,:1801)
  // -> run.sh:1987,:1991 -> these files. Mapping them to a module would need
  // `drills` in a surface, and the drills surface (cli, shared, account) would
  // then drag the whole VM matrix in; full is both cheaper and honest.
  { name: 'scripts-drills', match: matchPrefix('scripts/drills/'), full: 'harness' },

  // Runs INSIDE the executable build (.ci/scripts/build/prepare-cli-assets.sh:190,
  // reached from build-cli-executables.sh:123) and its output ships in the CLI
  // binary. A throw reds the ungated build job, but a silently-wrong credits
  // file is only caught by install_methods/package_tests, which ARE gated.
  {
    name: 'scripts-license-gen',
    match: (p) => p === 'scripts/generate-third-party-licenses.ts',
    full: 'harness',
  },

  // Everything else under scripts/ is a quality-gate source, its shared libs,
  // its data snapshots, the local ci-runner, or operator tooling. Traced
  // 2026-08-06: nothing else here is reachable from any of the 18 scoped keys.
  { name: 'scripts-gates', match: matchPrefix('scripts/'), modules: ['gates'] },
```

`eslint-harness` and `compose-harness` (`:177-178`) stay as they are; I did not trace them and will not narrow what I have not traced.

**No other file in the engine changes.** No new `JOB_SURFACES` key, so no `ci.yml` outputs, no `ct-tests.yml` inputs, no `skip-plan-reconcile.cjs` `EXPECTED_JOB_NAMES`, no `|18|` edits. The `scope-shadow.sh:214-220` key-set drift check is untouched.

**`exfil-tripwire.cjs` needs no edit, and this is worth stating explicitly.** `MODULE_PREFIXES` (`:50-63`) contains only the 12 modules that appear in a surface; `docs` and `devcontainer` are absent, and the drift test at `test-autopilot-harness.sh:407-437` only requires a prefix for *surface* modules. `gates` is not a surface module, so neither direction fires. And because `gates` has no prefix there, a `scripts/` edit stays **out-of-scope for every failed job**, so the tripwire still trips on it. The change does not loosen the tripwire.

**CI parity is explicitly NOT triggered.** `scope-map.cjs` is not an npm script, not a manifest `id`, not a `leaf`. `check-ci-parity.ts` never mentions it; `grep scope package.json` finds only the unrelated `check:ci-account-scope-audit`. **This is why the new test rows must go into the existing `test-scope-engine.sh` and not a new file**: assertion 7 in `check-ci-parity.ts:526-543` requires the `.ci/scripts/test/gates/` glob to equal the `qualityGateTest` manifest set exactly, so a new gate file would need a `manifest.ts` entry.

---

## 4. Blast-radius argument, adversarially

For each narrowed subset, the claim is not "it feels unrelated to ceph", it is **"no gated job executes it"**, traced above. The residual risk classes I looked for:

- *A gate source that also ships.* Found one: `generate-third-party-licenses.ts`. Excluded. `generate-embed-credits.ts` looked like a sibling but writes only via `check-embed-credits.ts:44` (a quality gate); it does not run in the build.
- *A generator whose committed output feeds infra.* `generate-translation-hashes.ts`, `sign-regions.ts`: outputs are `packages/www/**` and `regions.json`, which classify on their own paths (and `regions.json` is a `ROOT_MANIFEST` → full). A stale output is caught by its own always-running quality gate.
- *A dispatcher.* `run.sh` routes `drill` to `scripts/drills/`, but `run.sh` is a `ROOT_MANIFEST` (`:80`) → full. Editing the dispatcher stays full.
- *A shared lib under the narrowed set imported by the excluded set.* `generate-third-party-licenses.ts` imports **only node builtins** (`:26-29`). No `scripts/lib` or `scripts/utils` leaks into the build path. This one genuinely worried me and it came back clean.
- *Test infrastructure.* No vitest/jest test anywhere imports root `scripts/` (the two apparent hits resolve to package-local dirs, checked above).

The counterexample I could not construct: a path under `scripts/` (excluding the two carve-outs) whose change can red an E2E, ceph, k8s, fork-isolation, migrate, renet, license-enforcement, account-e2e, ops, elite-run, update-flow, package-tests, or install-methods job. If you can name one, that subset moves back to full.

---

## 5. Proof plan

**Anti-vacuity registration: nothing to add, and that is a finding, not an omission.** `test-gate-anti-vacuity.sh` registers *gate scripts* by "runs against an empty tree and must fail with this needle". A scope rule is not a gate script. The file's only scope entry is `".ci/scripts/test/gates/test-scope-engine.sh|closure"` (`:119-124`), whose needle is `test_workflow_closure_is_computed_not_name_matched`. The other three scope tests are documented as deliberately unregistrable, each with a measurement (`:152-159`, `:161-171`, `:173-187`). Adding a rule changes none of that.

**The real instrument is the classification regression table** at `test-scope-engine.sh:588-656`. Add inside `test_representative_deltas_classify_to_pinned_verdicts` (already called last, `:678`, so the closure registration at `:665` is not retired):

```bash
# THE REPORTED CASE (commit bcc4f1ee1): an Apache-2.0 attribution-URL check
# that ran the ceph fork test. Kept recognisable as the incident it came from.
expect_classify "gate source only" "reduced|18|" 'scripts/check-embed-credits.ts'
expect_classify "gate lib only"    "reduced|18|" 'scripts/lib/blocker-validator.ts'
expect_classify "ci-runner only"   "reduced|18|" 'scripts/ci-runner/manifest.ts'
# The over-eager-skip direction, matching the MIXED docs row above.
expect_classify "MIXED gate source + one cli file" "reduced|18|$cli_keys" \
    'scripts/check-cli-docs.ts' 'packages/cli/src/commands/repo.ts'
```

and two rows into the `full_row` loop (`:629-632`):

```bash
'scripts/drills/lib.sh|harness:scripts/drills/lib.sh' \
'scripts/generate-third-party-licenses.ts|harness:scripts/generate-third-party-licenses.ts' \
```

**Planted-defect procedure. Four mutations, each applied, run, red observed, reverted, with the exact diagnostic recorded in the report:**

| # | Mutation | Row that must go red | What it proves |
|---|---|---|---|
| M1 | Delete the `scripts-gates` rule | "gate source only" → `full\|18\|<all>` | the reduced verdict comes from the new rule, not from something else already in the table |
| M2 | Move `scripts-gates` above `scripts-drills` | `scripts/drills/lib.sh` full row | first-match order is load-bearing **and tested** |
| M3 | Typo the drills matcher to `scripts/drill/` | same row | an under-matching prefix cannot pass silently |
| M4 | Change `modules: ['gates']` to `modules: ['cli']` | "gate source only" (MIXED row stays green) | the **zero-job** property is pinned, not merely "mode is reduced" |

M4 is the one that matters most: without it, a future edit adding `gates` to a `JOB_SURFACES` entry would silently undo the whole change while every row still said `reduced`.

**Dry run before landing.** `scope-shadow.sh` is no longer shadow, and its own header says so (`:2-7`: "the FILENAME is deliberately unchanged"). There is no `SHADOW=1`. But two real dry-run channels exist:
1. **`OUTPUT_FILE` unset means "decide nothing"** (`:222-223`, documented `:59-62`: "that is what a local run gets, and it is the old shadow behaviour exactly"). Running the script locally writes the full plan and gates nothing. This is the pre-merge rehearsal.
2. `scope-classify.json` (`:404-417`) is a pure diagnostic; `:408` says "Nothing downstream reads scope-classify.json". It is uploaded as an artifact on every PR run, so a landed rule is observable there independently of the deciding plan.

**Live-fire after landing.** Push a one-file `scripts/check-*.ts` change and read the `ci-skip-plan` artifact (`ci.yml:330-341`) for `"mode": "reduced"` and `scripts/... -> gates` in `reasons`, plus the infra jobs showing skipped. Then confirm the reconciler stays green: `scope-reconcile-shadow.sh:102-103` arms a **hard gate** whenever `SCOPE_MODE == 'reduced'`, so an unverifiable reduced plan reds `ci-complete`. That is the standing net, not a one-off check.

---

## 6. Risk and rollback

- **Failure mode if the taxonomy is wrong:** a `scripts/` change that breaks an infra job is not caught until the next PR touching cli/shared/renet/account. It is a *deferral*, never a hole: quality, every build job, docker, dry-run and `Validate Promotion` still run on the same push, and the baseline machinery cannot chain scope evidence (`planCoverageIsFull`, `scope-engine.cjs:195-218`, requires `run===true` or `greenlight:<n>`), so an out-of-scope skip never launders itself into a green baseline.
- **Detection:** the reconciler hard gate above, plus the M1-M4 rows going red on any future edit that widens or breaks the rules.
- **Rollback:** revert the three rules to the single `{ name: 'scripts-harness', match: matchPrefix('scripts/'), full: 'harness' }` line, drop `'gates'` from `KNOWN_MODULES`, revert the test rows. One commit, no state, no migration.
- **Emergency stop without a revert:** set repo variable `FULL_CI=true` (`ci.yml:299`) or apply the `full-ci` PR label (`ci.yml:300`). Both are checked before the engine runs (`scope-shadow.sh:22-28`, `:387-402`) and force full immediately.

---

## 7. Expected saving, measured

Measured by driving the **real `classify()`** with the proposed rules spliced in, over **2263 non-merge commits across all refs** (this checkout is shallow: `main` carries only 50 commits, `git rev-parse --is-shallow-repository` = true, so per-branch commits are the available population). "Infra" = the 9 keys `e2e_*`, `fork_isolation`, `ops`.

| | commits | % |
|---|---|---|
| total sampled | 2263 | |
| touch root `scripts/` | 152 | 6.7% |
| ... which also touch `package.json`/`package-lock.json` | 79 | |
| ... which also touch `.ci/` | 98 | |
| ... which also touch `.github/` | 79 | |
| ... which touch **at least one** of those (full regardless) | **114** | 75% of scripts-touching |
| skip infra **today** | 135 | 6.0% |
| skip infra **after the split** | 164 | 7.2% |
| **newly skipped** | **29** | **1.28%** |

At your measured 18.7-43.4 min: **EV ≈ 0.36 min of wallclock per commit**, ≈ 810 min of wallclock and ≈ **10,200 job-minutes** (29 × 352) across the sample. The job-minutes number is the better argument than the wallclock one.

The ceiling is `package.json`: gate work usually adds or renames a `check:ci-*` script, and `package.json` is a `ROOT_MANIFEST` (`:75`) → full. **I measured the obvious follow-up and it is worth zero:** commits whose only non-`scripts/` blocker is `package.json` = **0** in 2263. Every one of the 79 carries `.ci/` or `.github/` too. Do not build content-aware `package.json` classification; there is nothing there.

I also checked the adjacent prize you did not ask about: `.ci/scripts/test/gates/`-only commits = **6** in 2263. Smaller than this one, and constraint 2 puts it out of bounds anyway.

**Uncertainty I will not paper over:** the engine is baseline-and-net-delta, so the real unit is a *push* during PR iteration, not a commit. Single-file gate tweaks during a babysit loop (exactly `bcc4f1ee1`'s shape) are over-represented in pushes relative to squashed history, so the per-push hit rate is plausibly several times the 1.28%. I could not measure it: it needs the run/artifact history, not the git log. I am flagging that as a hypothesis, not counting it.

**Recommendation: land it.** Not for the 1.28%, but because it costs about 15 lines in one lookup table plus 6 test rows and 4 mutations, the risk is structurally bounded by the fact that quality, build and promotion are unscopeable, and it removes a class of result ("an attribution-string check ran a ceph fork test") that makes the whole scope engine look untrustworthy even when it is working.

**Dropping OPS as well: I agree with you, do not.** `ops` surface is `cli, shared, provisioning, json, renet, account, tutorials` (`scope-map.cjs:250`), it is a genuinely broad job, ~1 extra minute does not pay for reasoning about it, and it is not what this change is about.

Files a reviewer will want: `/home/muhammed/monorepo/console/.ci/scripts/ci/scope-map.cjs` (rules at `:111-182`, modules at `:26-41`), `/home/muhammed/monorepo/console/.ci/scripts/test/gates/test-scope-engine.sh` (table at `:588-656`, call order at `:658-678`), `/home/muhammed/monorepo/console/.ci/scripts/ci/scope-shadow.sh` (`:2-7`, `:59-62`, `:222-223`, `:404-417`), `/home/muhammed/monorepo/console/.ci/scripts/ci/scope-reconcile-shadow.sh:102-103`, `/home/muhammed/monorepo/console/.ci/scripts/autopilot/exfil-tripwire.cjs:50-63`.
