<!-- Split out of CLAUDE.md. CLAUDE.md carries the standing rules that must be
obeyed every turn; this file is lookup material, read when the thing it
describes actually happens. Keep the pointer line in CLAUDE.md in sync. -->

# Quality Gates (`npm run ci`)

`npm run ci` runs the whole local gate set, which mirrors CI's quality tier. Run it before pushing to catch issues early. The gates cover version consistency, dependency freshness, ESLint, biome formatting, i18n completeness, TypeScript types, unit tests, security audit, shell linting, Go lint (renet), E2E coverage, the 57 quality-gate unit tests, and more.

### The runner

`npm run ci` is a parallel worker pool (`scripts/ci-runner/run.ts`), not a shell chain. It used to be a 93-step `&&` string measured at 1041.6 s serial, and that shape cost both time and signal: `&&` stops at the first red, so one failure hid every other one, and `check:ci-quality-gates` was 443 s of the total as a single opaque unit.

The gate set lives in `scripts/ci-runner/manifest.ts`, which is also the input to `npm run check:ci-parity`. Every individual `check:*` npm key still exists and still works on its own; the manifest schedules them.

| Command | What it does |
|---|---|
| `npm run ci` | Full run at `availableParallelism() - 2` workers, keep-going |
| `npm run ci:serial` | The same set at `--jobs 1`. Use this to decide whether a red is caused by parallelism |
| `npm run ci:list` | Every gate id and the exact command it runs |
| `npm run ci -- --only 'check:ci-embed-*'` | Run a subset. Glob or comma-separated ids |
| `npm run ci -- --skip check:ci-renet` | Run everything except a subset |
| `npm run ci -- --fail-fast` | Stop at the first failure. Off by default, see below |
| `npm run ci -- --json` | Machine-readable document on stdout, human stream on stderr |
| `npm run ci -- --jobs N` | Override the worker budget (`CI_JOBS=N` also works) |
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

1. **Fetch and read the COMPLETE failed-step log** (`gh run view --repo rediacc/console --job <id> --log`), including the full error message body — error texts often name their own cause (e.g. esbuild's "could not be found" error explicitly points at `--omit=optional`/optionalDependencies; npm's EUSAGE block names the exact missing lock entries). Selective `grep error | tail` hides the sentence that matters.
2. **Suspect your own commits first.** Before reaching for "transient infra", check whether the failing signature matches a documented failure mode in this file AND whether a commit in the current PR touched a related file (`package-lock.json`, `.npmrc`, migrations, workflows). Correlation with your own push is the default hypothesis, not the fallback.
3. **Reproduce in a clean room before calling anything transient.** "Works on my machine" with a warm cache and dev node_modules proves nothing. Match CI: export the tracked tree (`git checkout-index -a --prefix=<scratch>/` — `git archive` is blocked by `.gitattributes` `* export-ignore`), use CI's exact npm via `npx -y npm@<ver>` (version is printed in the job's setup-node "Environment details"), and a cold cache (`--cache <fresh-dir>`). Compare concrete numbers against the CI log ("added N packages"). Only when the clean room passes may the failure be called transient — and say so with the evidence, not instead of it.
4. **A green rerun on identical inputs is confirmation, not the investigation.** Use it to close the loop after steps 1-3, never to skip them.

### CI fix cycle

When fixing CI failures, follow this loop:

1. **Run locally first**: Run `npm run ci` sub-commands locally before pushing to avoid costly CI round-trips. Use parallel sub-agents for independent checks.
2. **Push and watch**: After pushing, arm a terminal-state watch in the background: `R=<run-id>; until [ "$(gh run view $R --repo rediacc/console --json status --jq .status)" = "completed" ]; do sleep 20; done; gh run view $R --repo rediacc/console --json conclusion,jobs` with run_in_background: true — the process exit notifies on completion. Do NOT use `gh run watch` as the wake-up; it has dropped silently on terminal runs (observed 4/4).
3. **Fix on notification**: When the background watch completes, check for failures with `gh run view <id> --json jobs --jq '.jobs[] | select(.conclusion == "failure") | {name}'`. A run that ends `cancelled` with a failed job means the watchdog killed it for that failure; `cancelled` with zero failed jobs means your own push superseded it. Cancelled NEVER means green — the run is only done when every job passes (deploy preview is among the last).

   Two ways this step lies to you, both observed on 0804-1:
   - **A watch missing from the background roster means it died OR it fired.** Those look identical from the outside, and the wrong guess is expensive in both directions (concluding "terminal" when the run is still going, or waiting forever on a watch that is gone). Re-check the run itself with `gh api repos/rediacc/console/actions/runs/<id> --jq '{status, conclusion}'` before inferring anything, then re-arm — an extra watch costs nothing.
   - **The job roster GROWS as the run progresses.** It starts around 19 jobs and reaches roughly 78. An early `--json jobs` snapshot showing "2 still running" is not the full roster and does NOT mean the run is nearly done. This is the same trap as reading a cancelled job as a passing one: in both cases the job list is not yet the thing it appears to be. Trust `status`/`conclusion` on the run, not your arithmetic on a partial job list.
4. **The automated Claude review fires when CI is green AND the PR is non-draft**: first at the babysitter's ready-flip, then again after each green push while the PR stays ready. It never runs on a draft, a red head, or a pointer-bump-only delta. When it posts (inline threads plus one summary comment), fetch `gh api repos/<owner>/<repo>/pulls/<N>/comments`, fix what's real, reply substantively to every comment, and resolve the threads via GraphQL. Unreplied/unresolved threads still fail `Review Gate` (console PR) and `Quality / Submodule Branches` (submodule PRs); clear them before the gate re-runs.
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
  The `no-cancel-failure` label could never have covered this: labels live on a
  PR, and a scheduled run has none.

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
| `no-cancel-failure` | Don't cancel run when jobs fail |
| `no-auto-retry` | Skip retry, force-cancel immediately on failure |

Labels apply to PR runs only. A `push` or `schedule` run has no PR, so none of
them are readable there -- which is why the nightly exemption above is in code
rather than in a label.

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

### Draft-until-green and the merge hooks

Console PRs are opened as **drafts** (`gh pr create --draft`) and stay draft until CI is green; submodule PRs (renet/account/elite, private repos on the GitHub free plan) are opened plain because private drafts are not free. Three pre-command hooks enforce the flow: `block-nondraft-pr-create` (the draft/plain split at creation time), `block-premature-ready` (`gh pr ready` is allowed only when the required `CI Complete` check is SUCCESS on the PR's current head; `--undo` is always allowed), and `block-admin-merge` (`gh pr merge --admin` is banned outright). The sanctioned merge is `gh pr merge --squash --auto`, which GitHub completes once required checks are green.

### Pointer-bump fast path

A push whose commits only move submodule gitlinks to tree-identical, on-submodule-`main` commits (the post-squash pointer bump), on top of a baseline commit that already has a successful `CI Complete`, is detected by `.ci/scripts/ci/detect-pointer-bump.sh`, which sets `pointer_bump_only=true` in the `initialize` job. Under that flag `ci.yml` skips `build-renet` (and everything cascading from it: the other builds, tests, install-matrix, preview) plus `stripe-sandbox`, `package-tests`, and `ops-tests` (`tests` carries `Migration Test`, which skips itself under the flag); only `quality`, `review-gate`, and `ci-complete` still run. `assert-ci-complete.sh` accepts those skipped builds as green **only** under this flag, so the aggregated `CI Complete` still goes green, in minutes. This is why `/pr-merge` now WAITS for the fast-path run to go green and merges with `--squash --auto`, instead of admin-merging over a pending run (which used to leave the merged PR with a permanent red `Quality / Branch`, a wall of cancelled jobs, and no `CI Complete`). A pointer-bump-only delta is also deliberately not re-reviewed by Claude.

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
