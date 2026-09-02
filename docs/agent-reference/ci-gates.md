<!-- Split out of CLAUDE.md. CLAUDE.md carries the standing rules that must be
obeyed every turn; this file is lookup material, read when the thing it
describes actually happens. Keep the pointer line in CLAUDE.md in sync. -->

# Quality Gates (`npm run ci`)

`npm run ci` runs the whole local gate set, which mirrors CI's quality tier. Run it before pushing to catch issues early. The gates cover version consistency, dependency freshness, ESLint, biome formatting, i18n completeness, TypeScript types, unit tests, security audit, shell linting, Go lint (renet), E2E coverage, the 57 quality-gate unit tests, and more.

### The runner

`npm run ci` is a parallel worker pool (`scripts/ci-runner/run.ts`), not a shell chain. It used to be a 93-step `&&` string measured at 1041.6 s serial, and that shape cost both time and signal: `&&` stops at the first red, so one failure hid every other one, and `check:ci-quality-gates` was 443 s of the total as a single opaque unit.

## The pre-push lane (`npm run ci:quick`)

`git push` is refused unless `.ci/cache/prepush-receipt.json` shows a green,
whole run of this lane against the CURRENT `HEAD^{tree}`
(`.claude/hooks/pre-bash/block-unverified-push.sh`). That is enforced, not
advised, because advice was already here and did not work: three of the five CI
reds on PR #579 were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and
`check:ci-parity` (1.29s) — 3.6 seconds of gate time that cost roughly 45
minutes of CI.

- **It is PARTIAL and says so.** Gates marked `slow: true` in the manifest are
  deferred to CI, along with any gate whose `needs` closure reaches one. The
  footer names every deferral. `npm run ci` is still the whole set.
- **`slow` is measured, not judged.** `.ci/cache/gate-durations.json` holds an
  EWMA per gate, and `check:ci-gate-manifest` asserts the marking against it in
  BOTH directions. Those numbers are CONTENDED wall time and run ~2-3x above a
  stopwatch (`check:ci-pipefail-grep-q`: 37.0s cached, 13.5s standalone).
- **BLOCKED is not FAIL.** A gate that cannot run here (a toolchain this machine
  lacks) exits 77, is reported separately, and does NOT redden the run or block
  the push — it warns. A gate that ran and judged your code red still refuses.
  Before assuming a red is a missing tool, check the obvious: an empty
  `private/account/node_modules` presented as four separate gate failures
  including a "missing @cloudflare/workers-types".
- **If a red is not yours** — this tree usually holds another session's
  uncommitted work — do not route around it and do not edit their file. Ask:
  `.claude/hooks/stop/worklist.py --ask <you> <them> '<gate>: <what you saw>'`.


The gate set lives in `scripts/ci-runner/manifest.ts`, which is also the input to `npm run check:ci-parity`. Every individual `check:*` npm key still exists and still works on its own; the manifest schedules them.

The CI-side quality-gate battery (`.ci/scripts/test/run-all.sh`, the "Quality-gate unit tests" step) is ALSO parallel since 2026-08-08, with a W/S/T schedule: two tests write fixtures into the real tree, so they run as a serial chain while temp-isolated tests pool, and the real-tree scanners are held back until the writers finish. Triage notes: `RUN_ALL_JOBS=1 .ci/scripts/test/run-all.sh` reproduces the exact serial behavior through the same code path; a "no result recorded" failure means the scheduler lost a test, which is a runner bug, never a skip; and a failure that appears parallel-only but not under `RUN_ALL_JOBS=1` is a real isolation leak in that test, not battery flakiness -- see the W/S/T header in run-all.sh before touching the schedule.

| Command | What it does |
|---|---|
| `npm run ci` | Full run at `availableParallelism() - 2` workers, keep-going |
| `npm run ci:quick` | **The pre-push lane.** 254 fast gates, ~48s wall. `git push` is REFUSED without a green receipt from it |
| `npm run ci -- --quick` | The same selection without minting a receipt |
| `npm run ci:serial` | The same set at `--jobs 1`. Use this to decide whether a red is caused by parallelism |
| `npm run ci:list` | Every gate id and the exact command it runs |
| `npm run ci -- --only 'check:ci-embed-*'` | Run a subset. Glob or comma-separated ids |
| `npm run ci -- --skip check:ci-renet` | Run everything except a subset |
| `npm run ci -- --fail-fast` | Stop at the first failure. Off by default, see below |
| `npm run ci -- --json` | Machine-readable document on stdout, human stream on stderr |
| `npm run ci -- --jobs N` | Override the worker budget (`CI_JOBS=N` also works) |
| `npm run ci -- --heavy-limit N` | Cap concurrent "heavy" gates specifically, separate from `--jobs`. Defaults to `max(2, jobs / 4)` |
| `npm run ci -- --manifest <path>` | Schedule from an alternate manifest file instead of `scripts/ci-runner/manifest.ts` |
| `npm run ci -- --list` | List every gate id and its command without running any of them (what `npm run ci:list` wraps) |
| `npm run ci -- --verbose` | Also print a line when each gate starts. Worth it at `--jobs 1`, where a five-minute gate is otherwise indistinguishable from a hang |

**Keep-going is the default, deliberately.** CI made the same call: every quality step carries `!cancelled()` so one push surfaces every failure in the lane. With keep-going, N independent failures cost one run; with `--fail-fast` they cost N runs. Use `--fail-fast` only in a tight edit loop where the first red is the only one you care about.

**Failure output.** A passing gate prints one line. A failing gate prints, streamed the moment it fails rather than held to the end:

```
FAIL  check:ci-foo                           12.4s   exit 1
  rerun: npm run check:ci-foo
  --- stdout ---
<complete captured stdout, unmodified and untruncated>
  --- stderr ---
<complete captured stderr, unmodified and untruncated>
```

stdout and stderr are captured separately and never merged, because merging hides progress-text-on-stdout and swallowed-output defects. `--merge-output` is the opt-in for a gate whose interleaving matters. The footer repeats every failure with a single copy-pasteable rerun line.

**`--changed` is a convenience, never a verdict.** It selects gates whose declared `paths` intersect the diff against the merge base. A gate with no declared `paths` is always selected, which is the safe direction. Any selection flag marks the run `PARTIAL` in the header, in the footer, and as `partial: true` in `--json`. A partial run that reports green has not validated the tree.

**Ordering and isolation.** Gates declare `needs` (ordering) and `mutex` (shared mutable resources: the per-package dist trees, `private/renet/bin`, the account vitest state, `packages/www/dist`). A gate whose dependency failed is reported `SKIP`, never as passed, and a skip still makes the run exit 1. If a gate passes at `--jobs 1` and fails under load, the fix is a new `mutex` group naming the resource, never a retry.

`.ci/cache/gate-durations.json` (gitignored) records per-gate timings so the pool starts the longest gates first. Deleting it is harmless.

`npm run ci` runs `--selftest` first: a synthetic failing gate that must produce exit 1, both captured streams, and a skipped dependent. If it prints `CONTROL FAILED`, the runner's green means nothing and nothing else should be trusted until it is fixed.

### Quick fixes for common failures

| Check | Fix |
|-------|-----|
| `check:deps` | `npx tsx scripts/check-deps.ts --upgrade`. **Respect `.syncpackrc.json` pins** — packages pinned there (currently `@opentelemetry/sdk-node`, `instrumentation`, `instrumentation-fetch`, `instrumentation-xml-http-request`, `exporter-trace-otlp-http`, `resources`) are deliberately held back across upgrades. Also respect `.deps-upgrade-blocklist` (zod, etc.). If `npm outdated` flags a pinned package, DO NOT bump the package.json — update the pin's `pinVersion` only if the pin is genuinely stale. |
| `Quality / Code` (`syncpack lint`) | `.syncpackrc.json` defines `versionGroups` with `pinVersion` and a `sameRange highestSemver` policy. A mismatch means either: (a) you bumped a pinned package beyond its pin — revert to the pin version, or (b) two workspaces disagree on a range — bump the lower one. Run `npx syncpack lint` locally to see exactly which dep violates which group. |
| Lockfile native-binary drift (`Cannot find module @rollup/rollup-*-*` or `lightningcss.*-*.node` or `Expected "0.25.12" but got "..."`) | Lockfile is missing platform-specific native binary entries. npm issue #4828: regenerating `package-lock.json` on a single platform drops optional `@rollup/rollup-*`, `@esbuild/*`, `lightningcss-*-*`, `@tailwindcss/oxide-*-*`, `@img/sharp-*-*`, `@biomejs/biome-*-*`, `oxc-parser-*-*`, `oxc-resolver-*-*`, `syncpack-*-*`, `unrs-resolver-*-*` entries for other OS/CPU combinations. **Never `rm package-lock.json`** on a single-platform checkout; use targeted `npm install <pkg>@<ver> -w <workspace>` instead. If you must regenerate, copy `package-lock.json` from `main` first and let `npm install` reconcile only the diffs. |
| Lockfile npm-version drift (`npm ci` fails with `Missing: <pkg>@<ver> from lock file` in CI but passes locally) | CI runs the npm bundled with setup-node's Node 22 (npm 10.x). A lockfile regenerated or updated by a newer local npm (11.x) can fail npm 10's stricter sync check, and npm 11 also emits fields npm 10 never writes (`libc`). **After ANY operation that touches a `package-lock.json`** (including `check-deps --upgrade`), validate every touched lockfile with CI's npm: `npx -y npm@10 ci --dry-run` (repo root, `private/account`, `private/account/web`, `private/account/e2e` as applicable). If it fails, reconcile with `npx -y npm@10 install --package-lock-only --ignore-scripts` in that directory and confirm the diff is additive (platform entries preserved), then re-validate under both npm 10 and your local npm. |
| `check:format` | `npx biome format --write packages/ private/account/` |
| `check:i18n` | `npm run i18n:generate-hashes && npm run i18n:sync`, then translate missing keys |
| `check:ci-search-index` | Any www content edit (docs/blog/i18n, all locales) stales the committed indexes: `cd packages/www && node scripts/generate-search-index.js`, commit `public/search-index*.json` |
| `check:ci-renet` | `cd private/renet && go fmt ./...`, then fix golangci-lint issues. After signature changes also sweep tag-gated files: `go vet -tags "root ebpf_e2e" ./...` (plain `go vet ./...` skips them; OPS CI compiles them) |
| `Quality / Static` (shell format) | `shfmt -w -i 4 <file>` after any shell edit (gate = `npm run check:ci-shell-format`) |
| `lint` / `check:lint` | Fix ESLint errors properly (never suppress with comments). **Never revert a dev-dep bump (or pin it in `.deps-upgrade-blocklist`) just to silence new rules a plugin surfaces.** When `eslint-plugin-react-hooks` 7.x flags `react-hooks/set-state-in-effect` / `refs-in-render` / `immutability` / `preserve-manual-memoization` across existing files, fix each site per React 19 idioms: move ref writes into a dependency-less `useEffect`, derive state via the "previous value" pattern (`const [prev, setPrev] = useState(value); if (prev !== value) { setPrev(value); setDerived(...); }`), wrap effect-only side effects in `useEffectEvent` (from `react`, available in 19+), defer problematic setState with `queueMicrotask`, use `window.location.assign(url)` instead of direct `window.location.href = url` assignments, and initialize state lazily with `useState(() => ...)` instead of a post-mount effect. Downgrade is not a fix. |
| `lint:unused` | Add to `ignoreDependencies` in `knip.jsonc` with a `// BLOCKER:` reason if it's a transitive/runtime dep |
| `check:ci-e2e-coverage` | Add coverage for new renet bridge functions in `packages/e2e-tests` (the gate greps e2e-tests for each generated function name) |
| `check:ci-renet` (types) | `private/renet/bin/renet functions generate-types --output packages/shared/src/renet-contract/data --version dev` |
| `check:ci-renet` (i18n orphan keys) | A locale defines a key `en.go` does not, so it is unreachable — lookups resolve against the English key set. Fix: `cd private/renet && ./bin/renet i18n prune-orphans --dry-run`, then re-run without `--dry-run` and `gofmt -w pkg/i18n/locales/`. Always safe to delete. This class hid 191 CORRUPTED KEY NAMES (machine translation rewrote the identifiers, `bridge.create_failed` -> `bridge.create_<arabic>`), invisible because validation only walked English keys. |
| `check:ci-renet` (i18n format parity) | A translation's `%s`/`%d` verbs do not match English. This is a RUNTIME bug, not cosmetic: Go substitutes positionally, so a dropped verb loses the value it should print and an extra one renders `%!s(MISSING)`. Fix the translation in `pkg/i18n/locales/<loc>.go`. If the language needs a different argument order, use explicit indices — `%[1]s`, `%.0[2]f` — numbered by position in the ENGLISH string. The index goes immediately before the verb, AFTER any precision (`%.0[2]f` is valid, `%[2].0f` is `%!f(BADINDEX)`). |
| `check:ci-renet` (i18n word blend) | An English morpheme is fused onto a translated root (`成功fully`, `başarıfully`, `Instすべてing`). Rewrite the whole string naturally; no `-ing`/`-fully` may remain welded to a translated root. Add genuine native words ending in those suffixes to `blendExceptions` in `pkg/i18n/rules.go` (e.g. Estonian `päring`). |
| i18n gating model (renet) | `./bin/renet i18n validate` exits on `.totalCertain`: untranslated, missing/orphan keys, and format-parity (incl. word blends), in EVERY locale. Only the `suspected` fragment heuristic is advisory. This was staged behind a `strictLocales` set while ~1800 pre-existing defects were fixed; all 12 locales are clean and the set is gone. It was never a baseline — a baseline exempts everything and turns "we know" into "fine forever", which is how 2837 grandfathered entries came to hide real bugs. |
| `check:ci-i18n-placeholders` | A locale DROPPED a `{{placeholder}}` English has (information silently lost) or INVENTED one it does not (renders literally to the reader). Covers three sets: `packages/cli`, `packages/www`, `private/account/web`. Fix the locale value; never add the placeholder to English unless the call site passes it. |
| `check:i18n` (orphan keys) | Same class as renet's, in the JSON catalogs: a locale defines a key English does not. English is the source of truth; remove the extra key. Reported per set by `scripts/check-translation-completeness.ts`. |
| `Initialize` (PR title) | PR title must follow Conventional Commits (`type(scope): summary` or `type: summary`). Fix with `gh pr edit <N> --title "fix: ..."`. |
| `Quality / Static` (PR description stale) | Description's `updatedAt` is older than 30 min and there are new commits. Run `gh pr edit <N> --body "..."` **immediately before pushing the next commit** so the fresh timestamp is visible to the next CI run (editing alone does not trigger CI). **The body must actually change** — an edit with identical content does NOT bump `updatedAt`; summarize the new commits instead of re-sending the same text. Stale-only failure: refresh + `gh run rerun <id> --failed`, no commit needed. |

### CI failure triage: read the whole log before diagnosing

Do NOT classify a CI failure from a handful of grepped lines. The cost of a wrong diagnosis (a wasted pipeline round, or worse, teaching the watchdog to retry a real bug) is far higher than the cost of reading one log properly.

**"My check passed" and "my check did not run" are indistinguishable without a control that can fail.** Before believing a clean result, make the check produce a RED on known-bad input through the same path. Two real examples from one five-minute stretch on 0804-1, both caught only because the control was run: a `git archive` that silently extracted nothing, so a `[ a -nt b ]` staleness test compared two *absent* files and returned false — looking exactly like a genuine "not stale" answer; and a deliberately restricted `PATH` that also hid `bash` itself, so the command under test executed **neither** branch while appearing to run. A green from an instrument that cannot go red is not evidence, and this applies recursively — to the check, and to the check of the check.

1. **Fetch and read the COMPLETE failed-step log** (`gh run view --repo rediacc/console --job <id> --log`), including the full error message body — error texts often name their own cause (e.g. esbuild's "could not be found" error explicitly points at `--omit=optional`/optionalDependencies; npm's EUSAGE block names the exact missing lock entries). Selective `grep error | tail` hides the sentence that matters.
2. **Suspect your own commits first.** Before reaching for "transient infra", check whether the failing signature matches a documented failure mode in this file AND whether a commit in the current PR touched a related file (`package-lock.json`, `.npmrc`, migrations, workflows). Correlation with your own push is the default hypothesis, not the fallback.
3. **Reproduce in a clean room before calling anything transient.** "Works on my machine" with a warm cache and dev node_modules proves nothing. Match CI: export the tracked tree (`git checkout-index -a --prefix=<scratch>/` — `git archive` is blocked by `.gitattributes` `* export-ignore`), use CI's exact npm via `npx -y npm@<ver>` (version is printed in the job's setup-node "Environment details"), and a cold cache (`--cache <fresh-dir>`). Compare concrete numbers against the CI log ("added N packages"). Only when the clean room passes may the failure be called transient — and say so with the evidence, not instead of it.
4. **A green rerun on identical inputs is confirmation, not the investigation.** Use it to close the loop after steps 1-3, never to skip them.

### CI fix cycle

When fixing CI failures, follow this loop:

1. **Run locally first**: Run `npm run ci` sub-commands locally before pushing to avoid costly CI round-trips. Use parallel sub-agents for independent checks.
2. **Push and watch**: After pushing, run `.ci/scripts/ci/ci-trace.py --wait` with run_in_background: true — the process exit notifies on completion. Ad-hoc watch commands are refused by `block-adhoc-sanctioned.sh` and a hand-rolled watch blocks the Stop hook, because the recipe rotted in nine places and reported superseded verdicts twice.
3. **Fix on notification**: When the background watch completes, list every job that is neither `success` nor `skipped` (filtering for `== "failure"` alone hides a cancelled gate, which did not report). A run that ends `cancelled` with a failed job means the watchdog killed it for that failure; `cancelled` with zero failed jobs means your own push superseded it. Cancelled NEVER means green — the run is only done when every job passes (deploy preview is among the last).

   Two ways this step lies to you, both observed on 0804-1:
   - **A watch missing from the background roster means it died OR it fired.** Those look identical from the outside, and the wrong guess is expensive in both directions (concluding "terminal" when the run is still going, or waiting forever on a watch that is gone). Re-check the run itself with `gh api repos/rediacc/console/actions/runs/<id> --jq '{status, conclusion}'` before inferring anything, then re-arm — an extra watch costs nothing.
   - **The job roster GROWS as the run progresses.** It starts around 19 jobs and reaches roughly 78 (97 with the E2E legs). An early `--json jobs` snapshot showing "2 still running" is not the full roster and does NOT mean the run is nearly done. This is the same trap as reading a cancelled job as a passing one: in both cases the job list is not yet the thing it appears to be. Trust `status`/`conclusion` on the run, not your arithmetic on a partial job list.
   - **`gh run list --limit 1` is usually NOT your run.** It is recency-sorted, and the watchdog's `Watchdog Monitor` generations are `workflow_dispatch` runs that chain every ~8 minutes against the OLD head sha — so the newest entry is routinely a monitor generation, and its `failure` conclusion is the monitor signalling a cancellation, not CI failing. Select by head sha instead: `gh run list --repo rediacc/console --branch <b> --json databaseId,headSha,event --jq '.[]|select(.headSha=="<sha>" and .event=="pull_request")'`. Watching the wrong id costs a whole round, because the watch fires immediately on an already-terminal run.
4. **The automated Claude review fires when CI is green AND the PR is non-draft**: first at the babysitter's ready-flip, then again after each green push while the PR stays ready. It never runs on a draft, a red head, or a pointer-bump-only delta. When it posts (inline threads plus one summary comment), fetch `gh api repos/<owner>/<repo>/pulls/<N>/comments`, fix what's real, reply substantively to every comment, and resolve the threads via GraphQL. Unreplied/unresolved threads still fail `Review Gate` (console PR) and `Quality / Submodule Branches` (submodule PRs); clear them before the gate re-runs.

   **A pass that posts NO report does not always cost you the head.** When it dies for an infrastructure reason (`error_max_turns`, `error_during_execution`), the attempt marker records `attempts: N of 3` and the head keeps its budget for two re-attempts — re-run them on the SAME head, no push required: `gh workflow run claude-review.yml --ref <branch> -f pr_number=<N>`. The third reportless attempt on one head, and any failure the pipeline cannot classify, are terminal: the marker then says "push a change to earn another pass" and it means it. This exists because a fully-green autopilot-driven PR has no legitimate change to push, so the old single-shot rule stalled the loop behind a human (PR #560).
5. **Fix, commit, push, repeat**: Fix the issue, commit, push, and watch again. Batch pending fixes into one push — each push restarts the whole pipeline. Continue until green.

### Quality lanes and the ubuntu-slim cap

The quality phase is **ten lanes**, not one job per gate. Gates are grouped by
what they need on disk (bare checkout / node / node+submodules / node+build /
go), so a lane pays its setup once: `Static`, `Branch`, `Submodule Branches`,
`Code`, `Content`, `Packages`, `i18n`, `Built-www Gates`, `Security`, `Go`.
`.github/workflows/ci-quality.yml` opens with the rules for editing one.

Two things follow that you will hit in practice:

- **A lane runs all of its gates even after one fails.** Every gate step carries
  `if: ${{ !cancelled() && steps.setup.outcome == 'success' }}`, so one push
  surfaces every failure in that lane. Do not "fix the first red and push" --
  read the whole lane's step list first.
- **`ubuntu-slim` dies at 15 minutes, hard.** The job is marked CANCELLED with no
  failed step, which reads as neither pass nor fail and poisons `CI Complete`.
  Every slim job must therefore declare `timeout-minutes` of 14 or less; CHECK 3
  in `.ci/scripts/security/check-workflow-gates.sh` enforces it. A job that
  genuinely needs longer moves to `ubuntu-latest` -- the number is not a dial.

Dependencies come from `./.github/actions/setup-workspace`, which restores a
cached `node_modules` (200 MB, ~2.5s) instead of running `npm ci` per job. On a
cache miss it falls back to `.ci/scripts/setup/install-deps.sh`, so a miss is
slow, never broken.

### Runner profiling is an invariant, not a habit (`check:ci-profiler-coverage`)

Standard runners are free and unlimited on this public repo, which is exactly
what makes oversizing invisible: a job that uses ~1 core on a 4-vCPU
`ubuntu-latest` VM burns four cores' worth of the world's electricity to do one
core's work, and no bill ever says so. `./.github/actions/profiler` samples
cpu/ram/disk/net and appends a profile to the job's own summary panel, so runner
sizing becomes a measurement instead of a guess. Coverage maintained by habit
decays the first time somebody adds a job in a hurry, so
`.ci/scripts/quality/check-profiler-coverage.sh` makes it a build failure.

It asserts two relations over `.github/workflows/*.yml`:

- **Coverage.** Every job whose `runs-on` resolves to Linux (`ubuntu-*`,
  including matrix legs) must use the action. Reusable-workflow callers
  (`uses: ./.github/workflows/...`) are excluded: they have no runner of their
  own, and their steps are the called workflow's jobs, which the gate sees in
  that file. macOS and Windows jobs are out of scope (the sampler is Linux-only).
- **Configuration.** A job that uses the action must reference it as
  `./.github/actions/profiler` (a missing `./` is read as `owner/repo` and fails
  at workflow parse time), pass only inputs `action.yml` declares, keep
  `interval` a positive integer in 1..300, and pass a `runner-label` that agrees
  with its own `runs-on`. That last one matters most: `runner-label` arms the
  HOST_LEAK check, and a copy-pasted `runner-label: ubuntu-latest` on an
  `ubuntu-slim` job makes the sampler read the host's 4 cores / 16 GB as the
  job's own, which is wrong in the direction that moves work onto a runner that
  cannot hold it.

Two design points worth knowing before you edit a workflow:

- **It fails CLOSED on what it cannot resolve.** `runs-on: ${{ inputs.runner }}`
  has no static answer, so the job counts as REQUIRING coverage. "We could not
  tell" costs an allowlist line with a reason; it is never silently exempt.
- **Coverage counts `setup-workspace` as a wrapper.** The open question this
  bullet used to carry — does a JavaScript action's `post:` hook fire when
  nested inside a composite? — was ANSWERED YES on 2026-08-08 by dispatching
  `profiler-probe.yml` (run 31252148469: `Post Run ./.github/actions/profiler/
  nest-probe: success` on both ubuntu-slim and ubuntu-latest). The profiler is
  therefore wired as one early step in `.github/actions/setup-workspace`, that
  composite is the gate's built-in wrapper default (`WRAPPER_DIRS`, still
  extendable via `PROFILER_COVERAGE_WRAPPER_DIRS`), and the 25 ledger lines
  for jobs covered that way are burned. The same probe settled the container
  facts: GitHub's slim is cgroup **v1** (the sampler's v1 fallback resolves
  cpu+memory), host views are container-scoped there (`nproc`=1,
  MemTotal≈4.8 GiB), `awk` and `node` are present, and a sample costs ~742µs.

  **Do not flip that seam without also extending the CONFIG relation.** The
  configuration checks only inspect DIRECT uses, and a composite forwards a
  fixed input, so a job covered through the wrapper passes no per-job
  `runner-label` and is checked for none.

  How much that costs depends on runtime behaviour that lives in
  `.ci/scripts/ci/profiler/report.awk` (`advise()`) and `sampler-linux.sh`, and
  it has moved twice already, so read those rather than trusting a summary here.
  The stable parts:

  - **A cgroup-tier reading is self-validating.** The kernel-enforced quota is
    ground truth about the box regardless of what anyone labelled it, so the
    advisor keys on the ceiling there and a missing or wrong label costs
    nothing. A `PROC_HOST` reading is not: `/proc` is only the job's ceiling if
    the job owns the whole machine, which is exactly what the label asserts and
    cannot prove.
  - **So the label matters only when the cgroup read failed**, and there its
    absence mutes the advisor while a wrong value is what the runtime guards
    (`HOST_LEAK`, `MISLABEL SUSPECTED`) exist to catch.

  The gate's runs-on/runner-label agreement check is authoring-time
  defence-in-depth over those runtime guards, not a substitute for them: it
  fires before a run exists, off the workflow text, with no dependence on
  fingerprint heuristics. It needs BOTH values to be literals, which the wrapper
  path prevents. And there is no `runs-on` value in any runner-side context
  (`runner.os` is `Linux` for slim and latest alike), so the label can only be
  threaded by hand: either each job passes it through the wrapper, which is most
  of the edits the nesting was meant to avoid, or the guard needs a different
  signal. Settle that first, then extend the config relation to the wrapper's
  call sites in the same change.

**The allowlist can only shrink.** `.profiler-coverage-allowlist` takes
`<workflow>.yml:<job>` entries under the usual `# BLOCKER:` convention
(`docs/agent-reference/suppressions.md`). It currently carries the rollout ledger: 90
jobs unwired as of 2026-08-05, plus `breakpoint.yml` (frozen in
`.ci/breakpoint/MANIFEST.sha256`, so a console-only step would fail the drift
gate) and `profiler-probe.yml`'s own experiment arms. Delete a job's line in the
commit that profiles it: the gate re-derives its oracle every run and rejects an
entry whose job no longer exists, is now profiled, is a caller, or does not run
on Linux, so a forgotten deletion is a build failure rather than dead weight.
That is the liveness half of the BLOCKER convention, enforced inside the gate
rather than by a probe in `scripts/check-suppression-liveness.ts`, because the
oracle IS the parse the gate already performs.

### CI watchdog and auto-retry

The CI has a watchdog (`watchdog-monitor.cjs`) and cancellation script (`cancel-older-runs.sh`) that manage run lifecycle.

The watchdog runs OUTSIDE the CI run, as a chain of short ubuntu-slim
generations in the separate "Watchdog Monitor" workflow (`watchdog-monitor.yml`):
the 1-vCPU runner's 15-minute job cap is a hard platform limit, so each
generation polls ~8 minutes and dispatches the next via `dispatch-watchdog.sh`.
The in-run `CI Watchdog` job is only a bootstrap (cancel older runs + dispatch
generation 1). The retry path lives in the SAME chain: a transient verdict sets
a `pending_rerun` flag carried through generations; when the run completes, the
chain reruns the failed jobs itself (with `check-rerun-attempt.sh` as a
separate deterministic attempt-cap pre-step) and keeps monitoring attempt 2.
Consequences when triaging: watchdog verdicts, cancellation annotations, and
retry decisions appear on `Watchdog Monitor` runs, not inside the CI run's own
job list. A lost dispatch fails open -- the run finishes unwatched, and
`ci-complete` still gates.

- **New push -> old runs cancelled**: `cancel-older-runs.sh` force-cancels all older in-progress runs on the same branch. **Never re-run a cancelled run** -- cancelled means superseded.
- **Scheduled (nightly) runs are NEVER cancelled.** Cancelling rewrites a run's
  conclusion from `failure` to `cancelled`, and everything downstream reads
  `cancelled` as "superseded, ignore". On a PR that is survivable; on the nightly
  it is fatal, because the nightly is the only suite validating `main`
  (`full_suite` is `event != 'push'`) and nobody is watching it. Measured
  2026-07-27: **12 of 12 scheduled runs `cancelled`, zero successes, back to
  2026-07-16**, entirely unnoticed. On a scheduled run the failure is recorded,
  the run is left to conclude as `failure`, and the watchdog KEEPS MONITORING so
  later failures are still logged and captured. See `evaluateCancelExemption`.
  This has to live in code: labels are read from the PR, and a scheduled run has
  none.

  **Retries are NOT suppressed on the nightly, only cancels are.** A flaky E2E
  leg is still re-run under the allowlist rules below. Suppressing both would
  make a network blip turn the nightly red, and a nightly that cries wolf trains
  everyone to ignore it -- the same disease as the laundering. `forceCancel`
  therefore reports whether it actually cancelled, and only a real cancel ends
  the watchdog generation.
- **Job failure (attempt 1)**: Watchdog uses AI (DeepSeek V4 Pro via Cloudflare's OpenAI-compatible endpoint) to classify the failure from the log excerpt anchored at the first `##[error]` marker (a plain tail showed only post-failure cleanup — run 29931338016):
  - **Transient** (network timeout, flaky test, npm error): the watchdog chain holds a pending rerun, lets the run finish, then reruns every failed job as attempt 2 of the SAME run; other jobs keep running.
  - **Code-change** (TypeScript error, lint failure, missing artifact): Force-cancels immediately, no retry.
  - **AI unavailable**: retries **only** jobs matching `WATCHDOG_RETRY_ALLOWLIST_PATTERNS`
    (`E2E,OPS,Fork Isolation` -- the legs that boot VMs or pull images, i.e. the
    ones whose failures are genuinely non-deterministic). Everything else fails
    fast. The classifier has been returning HTTP 402, so the old
    fall-back-to-retry meant every failure in the repo was retried on a judgment
    nobody made, at ~55 minutes a time. The allowlist governs **failures only**:
    a non-stuck CANCELLATION is a runner/infra flake, not a verdict about the
    code, and is still retried. Issue #537.
- **Failed-step logs are captured BEFORE any rerun** and uploaded as the
  `watchdog-logs-<run-id>-gen<n>` artifact on the corresponding `Watchdog
  Monitor` run. A rerun makes attempt 1's logs unreachable, so retrying used to
  destroy the evidence for the only question worth asking afterwards. Capture
  happens for every handled failure regardless of which branch handles it.
- **Job failure (attempt 2+)**: Watchdog force-cancels the entire run -- no infinite retry loops.
- **Quality lane failures**: Never auto-retry, never use AI (a lint or type error is deterministic; retrying it is pointless). The force-cancel now **drains first**: it waits until every other `Quality / *` lane reaches a terminal state, then cancels once with the full failure roster. So one round reports every failing lane instead of only the first, which is what used to make gates look like they failed serially. The expensive legs (E2E, OPS) are not in the no-retry set, so they still die immediately.
- **Review Gate failures**: Never auto-retry, never use AI, and never drain. Fail immediately and force-cancel -- an outstanding review is not a red to race past.

**PR labels** to control behavior:

| Label | Effect |
|-------|--------|
| `no-cancel-push` | Don't cancel older runs on new pushes |
| `no-auto-retry` | Skip retry, force-cancel immediately on failure |
| `no-external-quality` | Skip the externally-dependent gates (see `external_quality` below) |
| `no-media-quality` | Hold the tutorial-media gates (see `media_quality` below) |

There is no label that holds a failing run open. `no-cancel-failure` did, and it
was removed 2026-08-05: a red run kept alive still has to wait out the 44-minute
E2E and OPS legs before it concludes, so every iteration on a branch being driven
to green paid that cost. The full roster of deterministic reds arrives anyway --
the Quality drain above collects every lane, and `forceCancel` re-fetches the job
list so the annotation names every job that had failed by then.

Labels apply to PR runs only. A `push` or `schedule` run has no PR, so none of
them are readable there -- which is why the nightly exemption above is in code
rather than in a label.

### External gates and `external_quality` (hard / skip / soft)

The externally-dependent quality gates (`check:deps`, `check:ci-go-deps`,
`check:ci-embed-asset-freshness`, `check:actions`, `check:ci-external-links`,
`check:ci-dkim-notify`, plus the audit's skip half) are controlled by ONE
three-state flag, `external_quality`, computed by ci.yml's initialize job and
passed into ci-quality.yml as a `workflow_call` input:

`check:ci-go-module-sync` is deliberately NOT in that list, and the omission is a
decision rather than an oversight. It sits next to `check:ci-go-deps` in the
`quality-go` job and both are about Go dependencies, so the natural assumption is
that it belongs behind the same flag. It does not: it reads only the local
worktree, comparing each module that `replace`s renet against renet's own
`go.mod`, so no registry can make it fail. Putting it behind `external_quality`
would let the `no-external-quality` label skip a defect we caused ourselves.

- **hard** -- normal PR: a failure blocks, exactly as before.
- **skip** -- PR carrying the `no-external-quality` label: the steps do not run
  at all (offline branch work; the lookups cannot succeed).
- **soft** -- schedule / workflow_dispatch: the gate RUNS and reports, but
  `.ci/scripts/quality/run-external-gate.sh` downgrades a failure to a
  `::warning::` + step summary + exit 0. The nightly's red then means "main is
  broken", never "the world moved" (5 of the 8 nightlies before 2026-08-04 were
  red on external drift alone, and the `nightly-red` issue cried wolf).

`audit.sh` deliberately gets only the skip half: a new production advisory
against main's unchanged lockfile is a real signal about main, so it still
reddens the nightly (operator decision 2026-08-04).

Do not hand a new external gate its own `if:` expression or
`continue-on-error` (banned by check-workflows.sh): give the step
`inputs.external_quality != 'skip'`, route its command through
`run-external-gate.sh`, and pass `EXTERNAL_QUALITY_MODE`. The wrapper fails
closed (unset or unknown mode behaves as hard), check-ci-parity resolves
through it (the wrapped command stays the leaf), and
test-external-gate-wrapper.sh pins all four directions.

### Tutorial-media gates and `media_quality` (hard / skip)

Five validators read the recorded tutorial media -- the `.cast` files and the
transcript, narration-audio and parity artifacts derived from them, carried by
three CI steps across two jobs. They are controlled by `media_quality`,
computed by ci.yml's initialize and passed into ci-quality.yml as a
`workflow_call` input:

- **hard** -- everything except a labelled PR: a failure blocks.
- **skip** -- PR carrying the `no-media-quality` label: the three steps that
  run them do not execute.

There are only two states, deliberately. `external_quality` has a third
because the world moves underneath a nightly; nothing here reads the outside
world, so a media failure on `schedule` means main's own media is inconsistent,
which is a red the nightly should carry. For the same reason there is no
wrapper: with no soft state there is nothing to downgrade.

**What the label holds, and nothing else:**

| Gate | Job |
|------|-----|
| `check:ci-tutorial-casts` | `quality-content` |
| `check:ci-tutorial-parity` | `quality-content` |
| `check:ci-i18n-media` (transcripts + narration audio + cast output) | `quality-i18n` |

**What it deliberately does NOT hold**, because each still catches a real
defect while media is being re-recorded: `check:ci-tutorial-commands`,
`check:ci-tutorial-noninteractive`, `check:ci-tutorial-cli-validity` and
`check:ci-tutorial-no-skips` (these read the `.sh` scripts and the live command
tree, so a red is genuinely new), `check:ci-tutorial-caption-sync` (fetches
PUBLISHED CDN content, so a red is a production defect until the new media is
published), `check:ci-tutorial-card-fonts`, `check:ci-locale-tutorial-assets`,
`check:ci-tutorial-healthcheck-headroom`, `check:ci-tutorial-render-queue`, and
both solution-video gates (a different asset family entirely). Widening the set
is not a convenience, it is coverage nobody asked to lose.

**The label is a HOLD, not an exemption, and the log says so.** A skipped step
leaves its job `success` and prints nothing, so both consuming jobs run
`.ci/scripts/quality/announce-gate-skips.sh` UNCONDITIONALLY -- it is not
behind the mode `if:`. In `skip` it emits a `::warning::` and a step summary
naming every gate that did not run plus the instruction to remove the label; in
`hard` it prints the count of gates enforced, so a missing announcer and a
silent one cannot look alike. It also refuses (exit 2) an unrecognised
`media_quality` value, which is the only place a typo in that wiring is ever
reported: the step `if:` treats anything it does not recognise as "run", which
is fail-closed but completely silent. `test-gate-skip-announcer.sh` pins all of
it, including the workflow wiring itself.

Remove the label as soon as the media work it is waiting on lands, and let the
run go red if the underlying defect is still there.

Re-running (`gh run rerun`) is only appropriate for transient errors (network, flaky infra) on failed — not cancelled — runs.

### The nightly is reported, not just run

A red nightly opens (or comments on) a single rolling `nightly-red` issue,
labelled `bug` + `automated`, naming the failed jobs with log links; it closes
itself on the next green nightly. One rolling issue rather than one per night,
because the observed failure mode is a long unbroken streak and a wall of
identical issues is its own kind of invisible. Driven by `nightly-status.yml`
(`workflow_run` on Console CI, filtered to `event == 'schedule'`) calling
`report-nightly-status.cjs`.

**A scheduled run can also be rehearsed on demand**: `ci.yml` accepts
`workflow_dispatch` on `main` (guarded; a dispatch on any other ref fails
loudly). It is schedule-equivalent by construction -- `full_suite` is
`event != 'push'` and the channel resolves to empty for anything that is not
push or pull_request -- so it exercises the nightly path without waiting a day.
That matters because the alternative is one attempt per 24 hours, which is not a
feedback loop.

### Labels: the chain from a code reference to a PR comment

Labels in this repo are kill switches (`full-ci` bypasses the scope engine's
skips, `no-cancel-push` disarms the watchdog, `autopilot-blocked` latches the
babysit loop off, `rollback` blocks stable promotion), and nothing about a label
is self-documenting. Four links now connect a label reference to a human who can
understand it, each enforced by a different thing:

| Link | Enforced by |
|------|-------------|
| code names a label -> declared in `.github/labels.yml` | `check:ci-label-refs` (`.ci/scripts/quality/check-label-references.sh`) |
| declared <-> the label exists on the repo | `check:ci-label-inventory` (`.ci/scripts/quality/check-label-inventory.sh`) |
| declared (and not `guide: false`) -> explained on every PR | `label-guide` job in `ci.yml` -> `.ci/scripts/ci/label-guide-comment.cjs` |

**The inventory gate** reconciles `.github/labels.yml` against the live repo in
both directions. Declared-but-absent is the direction that already bit:
`rollback` was declared and referenced while not existing, and
`promote-stable.yml` searches `label:rollback` -- a search for a nonexistent
label returns zero PRs rather than an error, so the promotion block silently
never fired. Live-but-undeclared is the quieter direction: such a label never
reaches the PR guide, so people can apply it and nobody can look it up. If the
live list cannot be read (no token, API error, empty response) the gate REFUSES
rather than passing; an empty label list is a failed read, never a clean tree.

**Verify-at-read, for the absent direction only.** The list is a snapshot and
the repo's labels change under it. A full run once accused `no-auto-retry` of
not existing while it existed and `watchdog-monitor.cjs:1105` was reading it --
someone was mid-way through a delete-and-recreate, and the paginated list came
back one short. The empty-list guard does not catch wrong-by-one, so a race
produced this gate's loudest message, the one about `rollback` and silent
fail-open. A gate that cries wolf that hard gets ignored, and is then worth
nothing on the day it is right. So a label that looks absent is re-read on its
own (`gh api repos/{owner}/{repo}/labels/<name>`, URL-encoded) before it is
accused: a 404 confirms the finding, a 200 drops it with a note, and anything
else (403, 500, network) counts as "could not tell" and the finding stands.
Only this direction needs it -- a stale read loses entries, it never invents
them, so an extra name cannot be an artifact. In injected mode
(`LABEL_INVENTORY_LIVE_FILE`) there is no API to re-read, so the injected list
stands as its own authority and findings are reported; `LABEL_INVENTORY_PROBE_FILE`
is the separate seam that lets the test drive both re-verify outcomes offline.
One label is exempt from the absent direction, via a commented allowlist inside
the script: `nightly-red` is created on demand by `report-nightly-status.cjs`
right before it opens the rolling issue. The allowlist re-verifies both halves of
its own entry each run, so the exemption expires rather than rots.

Its CI coverage is `kind: 'test'`: `test-label-inventory.sh` drives the real gate
over the real `.github/labels.yml` inside the `Quality-gate unit tests` battery,
with the live list injected, plus controls that drop a real label and add an
undeclared one. The **live** GitHub read is the one part that lane cannot do (it
holds no label-read token); run `npm run check:ci-label-inventory` locally for
that.

**The PR label guide** is a single sticky comment posted by the `label-guide`
job, rendered from `.github/labels.yml` so it cannot become a second, rotting
copy. It is identified by the HTML marker `<!-- rediacc:label-guide -->` and is
idempotent in the strong sense: the job creates when absent, updates when the
rendered body differs, and performs **zero API writes** when it is byte-identical
-- otherwise a PR would collect one guide per push. Only a comment authored by a
BOT counts as the guide, so an outsider cannot suppress it by posting a fake one.
A marker comment from a human is ignored, not rewritten.

**`guide: false` separates declaring from listing.** All 26 labels must be
declared (the inventory gate reconciles the whole file), but only 12 are listed
on the PR: GitHub's stock defaults, bot-applied labels, and the three with zero
consumers in code carry `guide: false`. The guide exists because the roster got
too long to remember, so padding it with `duplicate` and `good first issue`
would recreate the problem it solves. **Absent means true**, so a new label is
visible unless someone opts it out -- failing toward showing a label, because
one that quietly vanishes from the guide is invisible while one that appears
needlessly is a row too many. A present value must be exactly `true` or `false`;
anything else is a loud parse failure rather than a coerced truthy string, since
coercion flips visibility in the direction nobody notices. The visible set
carries its own anti-vacuity floor, separate from the declaration floor: a
parser change that mis-read the field would otherwise leave the declaration
count satisfied while the rendered table came out empty.

Three labels are declared as **historical only** and worth knowing about,
because their own descriptions used to claim otherwise: `release` does not
trigger CD (`finalize-release-sentinel` dispatches unconditionally and reads no
label), `description-current` is not read by the PR-description gate (which uses
`lastEditedAt`), and `codex` has no consumer at all. They stay declared rather
than deleted because deleting a label strips it from the history of every PR
that carries it. A label's description is not evidence of its behaviour; the
`check:ci-label-refs` sweep is.

The job is separate from `initialize` for one reason worth remembering: it needs
`pull-requests: write`, and no other job in `ci.yml` holds that. `initialize`
carries a 20-step surface (checkout, a five-repo app token, GHCR login, the scope
engine), and widening its grant to buy one comment is the wrong trade. Its result
is soft-required in `assert-ci-complete.sh` as `LABEL_GUIDE` -- it legitimately
skips on non-PR events, but a genuine failure still reddens `CI Complete`, which
is what you want: the commenter throwing means `.github/labels.yml` stopped
parsing, and that same file feeds the inventory gate.

### Draft-until-green and the merge hooks

Console PRs are opened as **drafts** (`gh pr create --draft`) and stay draft until CI is green; submodule PRs (renet/account/elite, private repos on the GitHub free plan) are opened plain because private drafts are not free. Three pre-command hooks enforce the flow: `block-nondraft-pr-create` (the draft/plain split at creation time), `block-premature-ready` (`gh pr ready` is allowed only when the required `CI Complete` check is SUCCESS on the PR's current head; `--undo` is always allowed), and `block-admin-merge` (`gh pr merge --admin` is banned outright). The sanctioned merge is `gh pr merge --rebase --auto`, which GitHub completes once required checks are green. `allow_squash_merge` is `false` on all five repos, so `--squash` fails outright; ask with `gh api repos/rediacc/<r> --jq .allow_squash_merge` rather than trusting this sentence.

### Pointer-bump fast path

A push whose commits only move submodule gitlinks to tree-identical, on-submodule-`main` commits (the post-squash pointer bump), on top of a baseline commit that already has a successful `CI Complete`, is detected by `.ci/scripts/ci/detect-pointer-bump.sh`, which sets `pointer_bump_only=true` in the `initialize` job. Under that flag `ci.yml` skips `build-renet` (and everything cascading from it: the other builds, tests, install-matrix, preview) plus `stripe-sandbox`, `package-tests`, and `ops-tests` (`tests` carries `Migration Test`, which skips itself under the flag); only `quality`, `review-gate`, and `ci-complete` still run. `assert-ci-complete.sh` accepts those skipped builds as green **only** under this flag, so the aggregated `CI Complete` still goes green, in minutes. This is why `/pr-merge` now WAITS for the fast-path run to go green and merges with `--rebase --auto`, instead of admin-merging over a pending run (which used to leave the merged PR with a permanent red `Quality / Branch`, a wall of cancelled jobs, and no `CI Complete`). A pointer-bump-only delta is also deliberately not re-reviewed by Claude.

### Dispatching a workflow on a branch (`--ref`), and the one half nobody has proven

Console's workflow graph is already branch-aware where it can be: all 18 job-level workflow
calls in `.github/workflows/` use the local `./` form, and GitHub documents that form as
resolving to the caller's own commit — *"When you reference a reusable workflow in the same
repository using `./` (without `{owner}/{repo}` and `@{ref}`), the called workflow is from the
same commit as the caller workflow."* (*Reuse workflows*). A PR's `ci.yml` closure therefore
runs the PR's own YAML. What forces merge-first is never the ref: it is `workflow_run` and
`pull_request_target` reading the default branch **by design** (they hold secrets while a PR's
code is in play), the deliberate `console@main` pin on the review scripts
(`claude-review-reusable.yml:170-176`, closing run `30317293249` where a PR reviewed itself
with its own review logic), `ci.yml:193-199` refusing a non-`main` rehearsal dispatch, and the
two external callers registered in `.github/external-callers.yml`.

**Acceptance is decided from the default branch. This half is settled.** GitHub: *"This event
will only trigger a workflow run if the workflow file exists on the default branch."*
(*Events that trigger workflows*). Two live consequences, both already paid for here:

- Adding a `workflow_dispatch:` trigger costs **one** merge, once per workflow — never one per
  change. Until it lands on `main`, `gh workflow run <file> -f …` fails closed with a 422,
  *"Workflow does not have 'workflow_dispatch' trigger"*. Observed on PR #546, run
  `30588087212` (`claude-review.yml:27-35`).
- The same resolution applies to the FILENAME, so a brand-new workflow cannot be dispatched
  from any ref at all: `.ci/scripts/ci/dispatch-watchdog.sh:126-138` fails open on exactly
  that bootstrap condition, observed as an HTTP 404 on both the head-ref and default-branch
  attempts in run `29936730679`.

**Which copy then EXECUTES is the dispatched ref's, and one rule explains every trigger.**
This is not stated in one sentence anywhere, which is why two places in this tree used to
disagree about it (`claude-review.yml:27-35` said the default branch's copy defines the job;
`agent/PLAN-branch-aware-workflows.md` said the ref's). It is the conjunction of two pages,
both re-verified 2026-09-02:

> "Each workflow run will use the version of the workflow that is present in the associated
> commit SHA or Git ref of the event." — *Workflows (concepts)*

and the per-event table in *Events that trigger workflows*, which gives `workflow_dispatch`
a `GITHUB_REF` of *"Branch or tag that received dispatch"* and a `GITHUB_SHA` of *"Last commit
on the `GITHUB_REF` branch or tag"*. So the dispatched branch's YAML runs.

**The same rule is why `workflow_run` and `pull_request_target` read the default branch** —
their table rows give both a `GITHUB_REF` of *"Default branch"* and a `GITHUB_SHA` of *"Last
commit on default branch"*. That is not a separate mechanism to memorise; it is the identical
"version at the event's ref" rule applied to an event whose ref IS the default branch, which
is the security property those two triggers exist to have.

Practical consequence: **acceptance and execution resolve against different refs, and only for
`workflow_dispatch`.** Landing the trigger on `main` is a one-time cost; after that
`--ref <branch>` genuinely tests the branch's copy.


### Never push to `main` or cut a release without explicit user authorization

**AI agents MUST NOT push to `main` (console or any submodule) or trigger a release without an explicit, per-task user request.** Every push to `main` runs the full release pipeline (`cd-v2.yml` deploys edge on green), so an unprompted main push is an unprompted release. Approving an implementation plan is **not** authorization to push to `main` or release. Branch protection forbids direct pushes (`.github/CONTRIBUTING.md`); do not work around it.

Per *Session Defaults*, the standing default is to land nothing at all: leave the work uncommitted and let the operator decide. This section governs the case where the operator HAS asked for the work to land. Then the route is a feature branch and a PR for them to merge, never a direct push to `main`. When in doubt, stop and ask.

**One documented exception, and only one:** a MAIN-ONLY failure during a
`/pr-merge` run, after that command has already merged. See step 5 of
`.claude/commands/pr-merge.md` for the full rule and the classification test.

The reason is instrument validity, not urgency: the PR was green, so a failure
that appears only after the merge lives in a path PR CI structurally cannot run
(`refs/heads/main`-gated jobs, the dispatch-only Release workflow, or Docker,
which PRs only dry-run). **A fresh PR would go green without exercising the fix
at all** -- it is the wrong instrument, so its verdict is worthless. The
verification loop is the next `main` run.

Classify first: if the failing job RAN AND PASSED on the PR, it is transient, not
main-only -- do not fix it, the watchdog auto-retries. Only a job the PR could
never have run earns the direct push. It does not extend to re-cutting a release,
and it does not apply outside that command's own release path.

### Submodule commit order

Always commit submodules before the parent repo:

```bash
# 1. Commit in submodule(s)
cd private/renet && git add -A && git commit -m "fix: ..." && git push origin <branch>
cd private/account && git add -A && git commit -m "fix: ..." && git push origin HEAD

# 2. Commit in parent (updates submodule pointer)
cd /path/to/console && git add -A && git commit -m "fix: ..." && git push
```

### Secrets in CI vs CD

- **CI workflows** (`ci.yml`, `ci-quality.yml`, `ct-tests.yml`): Use **generated throwaway keys** via `ci-env.sh`. Never pass production secrets.
- **Release workflow** (`cd-v2.yml`): Uses **real org secrets** from GitHub for production deployment.
- Generated secrets are masked via `::add-mask::` in `ci-env.sh`.
