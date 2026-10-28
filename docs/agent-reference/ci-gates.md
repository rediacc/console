<!-- Split out of CLAUDE.md. CLAUDE.md carries the standing rules that must be
obeyed every turn; this file is lookup material, read when the thing it describes actually happens. Keep the pointer line in CLAUDE.md in sync. -->

# Quality Gates (`npm run ci`)

`npm run ci` runs the whole local gate set, which mirrors CI's quality tier. Run it before pushing to catch issues early. The gates cover version consistency, dependency freshness, biome lint and formatting, i18n completeness, TypeScript types, unit tests, security audit, shell linting, Go lint (renet), E2E coverage, the 57 quality-gate unit tests, and more.

### The runner

`npm run ci` is a parallel worker pool (`scripts/ci-runner/run.ts`), not a shell chain. It used to be a 93-step `&&` string measured at 1041.6 s serial, and that shape cost both time and signal: `&&` stops at the first red, so one failure hid every other one, and `check:ci-quality-gates` was 443 s of the total as a single opaque unit.

## The pre-push lane (`npm run ci:quick`)

`git push` is refused unless `.ci/cache/prepush-receipt.json` shows a green, whole run of this lane against the CURRENT `HEAD^{tree}` (`.claude/hooks/pre-bash/block-unverified-push.sh`). That is enforced, not advised, because advice was already here and did not work: three of the five CI reds on PR #579 were `check:format` (1.72s), `check:ci-python-lint` (0.59s) and
`check:ci-parity` (1.29s) — 3.6 seconds of gate time that cost roughly 45 minutes of CI.

- **It is ONE PASS, and PARTIAL only where the change set allows.** The fast gates and
every `slow: true` gate the change set since the last push touches run in the same scheduler pass, so the long ones start at t=0 and the fast ones fill around them; there is no wall budget and no second `--only` pass (`scripts/ci-runner/quick-select.ts`, operator ruling 2026-10-05). An untouched slow gate, and any gate whose `needs` closure reaches one, is deferred to CI, and the footer names every deferral. `npm run ci` is still the whole set.
- **No gate carries a static width.** A gate whose tool has a width knob declares
`cores: { min, max }` and reads `$CI_RUNNER_CORES`, which the pool sets at admission by the area rule (`scripts/ci-runner/pool.ts` `elasticGrant`); a Python tool sizes itself with `core_lease.granted_cores()`, which falls back to the process's CPU affinity. The few network fan-outs that must stay fixed are listed in `.ci/policy/fixed-widths.json`, and `check:ci-record-paths` refuses an unlisted width or a core cap.
- **Concurrent runs share the machine through the core lease.** `.ci/rediacc_ci/core_lease.py`
hands out one flock token per core under `/run/user/<uid>/rediacc-cores` (bound into the devbox at `/run/rediacc-cores`), so two sessions' pre-pushes split the cores instead of each assuming all of them. `PYTHONPATH=.ci python3 -m rediacc_ci.core_lease status` shows how many tokens are free; the runner falls back to the whole machine, saying why, when no lease directory is usable.
- **A record-only commit advances the receipt instead of voiding it.** When HEAD moved since
the receipt only through paths in `.ci/policy/record-paths.json` (review records, ledgers), `ci:quick` runs only those paths' readers and appends an `advances` step; `block_unverified_push` follows the chain, recomputes each step's diff with `--no-renames`, and admits only record-only steps whose readers passed.
- **A code commit re-runs only the gates whose inputs it changed.** The receipt is schema 2
(agent/plans/PLAN-fast-loop.md Part 1): each gate entry carries an input hash over its lock entry and npm script closure, the tracked files its `paths` and leaf closure reach plus the global inputs (every lockfile, `.devcontainer/toolchain.env`, `pyproject.toml`, `scripts/ci-runner/**`), the toolchain salt and its `needs`. In a clean clone (`--receipt-out` outside the checkout), a whole `ci:quick` carries every gate whose hash is unchanged from the prior receipt and runs the rest; the log says `incremental: N carried, M run`. A gate with no declared `paths`, an `env` entry or a row in `.ci/policy/carry-exempt.json` (clock, history, network or cache readers) always runs. A carried red stays red. `block_unverified_push` re-derives each carried gate's hashes at the pushed tree and checks it against its origin receipt under `.ci/cache/receipts/`, and refuses a receipt that is not schema 2.
- **The hooks advise on loop speed and never block it.** The Stop and post-tool hooks remind
the session to commit when its own edits sit uncommitted with no commit for `commit_remind_min` minutes (QUEUE.md `## Settings`, default 15). One receipt per push: the post-bash hook advises against starting `ci:quick` before a push is due, and the Stop hook names how many code commits the receipt is behind HEAD. While the PR's run on the pushed head is in progress and not red, the hooks advise holding local commits until it settles; a red with a fix in hand pushes at once.
- **`slow` is measured, not judged.** `.ci/cache/gate-durations.json` holds an
EWMA per gate, and `check:ci-gate-manifest` asserts the marking against it in BOTH directions. Those numbers are CONTENDED wall time and run ~2-3x above a stopwatch (`check:ci-pipefail-grep-q`: 37.0s cached, 13.5s standalone).
- **BLOCKED is not FAIL.** A gate that cannot run here (a toolchain this machine
lacks) exits 77, is reported separately, and does NOT redden the run or block the push — it warns. A gate that ran and judged your code red still refuses. Before assuming a red is a missing tool, check the obvious: an empty `private/account/node_modules` presented as four separate gate failures including a "missing @cloudflare/workers-types".
- **If a red is not yours** — this tree usually holds another session's
uncommitted work — do not route around it and do not edit their file. Ask the operator, or leave a `[?]` worklist item naming the conflict.


The gate set lives in `scripts/ci-runner/manifest.ts`, which is also the input to `npm run check:ci-parity`. Every individual `check:*` npm key still exists and still works on its own; the manifest schedules them.

Gate tests are pytest modules under `.ci/rediacc_ci/tests/gates/`, collected by `npm run check:ci-pytest` and run in CI by the `quality-pytest` job. The bash gate-test battery (`.ci/rediacc_ci/battery.py` over `.ci/scripts/test/gates/test-*.sh`, the `quality-gate-tests` job) was retired on 2026-10-09 once its last test was ported. A module that shares a resource the scheduler cannot see declares `XDIST_GROUP`, and a lock entry claiming `tree:` under `mutex` or `reads` groups the ported module it names; `.ci/rediacc_ci/xdist_groups.py` derives both.

| Command | What it does |
|---|---|
| `npm run ci` | Full run at `availableParallelism() - 2` workers, keep-going |
| `npm run ci:quick` | **The pre-push lane.** The fast subset of the manifest; `npm run ci -- --quick --list` prints the live set and its count. `git push` is REFUSED without a green receipt from it |
| `npm run ci -- --quick` | The same selection without minting a receipt |
| `npm run ci -- --quick --no-diff-slow` | The fast lane alone, without the slow gates the diff would add. A narrowing flag, so it never mints a receipt. Housekeeping's gate-cost capture uses it for its quick phase, because its rotation phase measures the slow set |
| `npm run ci:serial` | The same set at `--jobs 1`. Use this to decide whether a red is caused by parallelism |
| `npm run ci:list` | Every gate id and the exact command it runs |
| `npm run ci -- --only 'check:ci-embed-*'` | Run a subset. Glob or comma-separated ids |
| `npm run ci -- --lane quality-code --shard 2/4` | Run exactly one CI shard leg locally, from the committed `.ci/config/shards/<lane>.json` manifest (PLAN-ci-time-budget T2.10) |
| `npm run ci -- --list-units test-account-e2e` | Print a test lane's units, one JSON object per line: the input to its shard manifest and its per-unit durations (T2.8) |
| `npm run shard:place -- <lane>` | Place a new test or unit into the lane's shard manifest: only missing units are placed (a mutex/together/needs group joins its group's leg, anything else the lightest leg), a placed unit never moves, and the npm verb writes the manifest (`npx tsx scripts/ci-runner/shard-place.ts <lane>` without `--write` previews). `test-e2e-workers` and `quality-code` refuse it (`check-lane-budget --rebalance`, `gate-bind --write`) |
| `npm run ci -- --skip check:ci-renet` | Run everything except a subset |
| `npm run ci -- --fail-fast` | Stop at the first failure. Off by default, see below |
| `npm run ci -- --json` | Machine-readable document on stdout, human stream on stderr |
| `npm run ci -- --jobs N` | Override the worker budget (`CI_JOBS=N` also works) |
| `npm run ci -- --heavy-limit N` | Cap concurrent "heavy" gates specifically, separate from `--jobs`. Defaults to `max(2, jobs / 4)` |
| `npm run ci -- --sched cores` | Pack gates against a CPU budget by each gate's measured cores (the duration cache's `cpu` samples) instead of one slot per gate; `--jobs N` then sets the core budget. The default since 2026-09-30; `--sched slots` (or `CI_SCHED=slots`) restores the one-slot rule for an A/B |
| `npm run ci -- --manifest <path>` | Schedule from an alternate manifest file instead of `scripts/ci-runner/manifest.ts` |
| `npm run ci -- --list` | List every gate id and its command without running any of them (what `npm run ci:list` wraps) |
| `npm run ci -- --verbose` | Also print a line when each gate starts. Worth it at `--jobs 1`, where a five-minute gate is otherwise indistinguishable from a hang |
| `npm run ci -- --gate-timeout <s>` | One kill timer of `<s>` seconds for every gate, in place of each gate's derived limit (4x its slowest measurement, never under 300 s; `scripts/ci-runner/gate-timeout.ts`). A gate past its limit gets SIGTERM, then SIGKILL, and is reported failed and named, while the pool continues |
| `npm run ci -- --slow-rotation i/N` | Run only bucket `i` of the slow gates split `N` ways by CI step p90, prerequisites included. Its own selection: it does not combine with `--quick`, `--changed`, `--only` or `--lane`. Housekeeping's gate-cost capture (`rediacc_ci.ci.capture_gate_costs rotation`) runs `i/3` by day of year, since the 3-day artifact retention keeps at most three captures |
| `npm run ci -- --narrow` | Run the last receipt's non-carried fails, their learned clusters, the gates the fix touched and the gates associated with the changed classes; never writes a receipt. `--narrow --print` prints that set and its command and runs nothing |
| `npm run ci -- --stop-on-stage-red[=preflight\|1]` | Stop, with no receipt and exit 3, once the named stage (bare means stage 1) settles with a red that `carried-reds.json` does not cover |
| `npm run ci -- --events <abs>` | Write the machine stream (run-start, gate-red, stage-done, run-end) to the absolute path; a `--quick` run defaults to `<receipt dir>/ci-quick-events/<runId>.jsonl` |

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

**`--receipt-out <absolute path>` judges the pushed tree when the worktree is shared.** `ci:quick` judges the worktree it runs in, while the push carries `HEAD^{tree}`, so other writers' uncommitted edits can turn the receipt red for a tree that does not contain them. Run `npm run ci:quick -- --receipt-out <checkout>/.ci/cache/prepush-receipt.json` in a clean clone checked out at the same HEAD, and the receipt lands where the pushing checkout's guard reads it. The guard still refuses unless the receipt's recorded tree equals the pushing `HEAD^{tree}`.

**A touched slow gate that ci:quick drops is recorded, and the push waits for it.** The receipt carries `droppedTouched` (each id, its kind `tree` (the one drop left: a tree-writing gate in a shared checkout), and the exact `--only` rerun line), `droppedVerified` and `pushBase`. `block_unverified_push` refuses while a dropped id has no passing `droppedVerified` entry at the pushed tree, and a receipt without the field fails closed. `npx tsx scripts/ci-runner/run.ts --only a,b,c --receipt-out <same path>` merges (not `npm run ci:quick -- --only`, which narrows the quick selection and matches zero gates) into a whole receipt for the same tree, so several drops clear in one run. The push base is `@{push}`, then `origin/<branch>`, then `@{upstream}`, then `origin/main`. In a disposable clone (receipt outside the checkout, clean status) tree-writing gates are admitted like any other, so the list is empty there. `check:ci-plan-record` appends its census only under `--census`, so a plain run never writes the tree.

**Ordering and isolation.** Gates declare `needs` (ordering) and `mutex` (shared mutable resources: the per-package dist trees, `private/renet/bin`, the account vitest state, `packages/www/dist`). A gate whose dependency failed is reported `SKIP`, never as passed, and a skip still makes the run exit 1. If a gate passes at `--jobs 1` and fails under load, the fix is a new `mutex`
group naming the resource, never a retry.

**A gate that writes the real tree declares it, and `check:ci-gate-tree-writes` checks.** It follows every scheduled gate's leaves through imports and spawns and resolves each write's target to temp, `.ci/cache` scratch, or the tree. A proven tree write needs `mutex: ['tree:repo']` plus `writesTree: '<what it writes>'` on the manifest entry, and each of the two without the other is red. That pair is the weak fix: it serialises only against the other `tree:` claimants, and it does nothing for what a hard kill leaves behind, so write to a temp copy where possible. A write the scanner cannot resolve takes `# tree-write: safe <reason>` (`//` in TS/JS) on its line or the line above. A write that only a flag reaches, under a guard the scanner does not recognise, takes `# tree-write: mode --flag <reason>`, which holds while no registered invocation passes that flag. The reason is at least 20 characters, and a `safe` pragma on a write the scanner already resolves is red. `--report` lists every site.

`.ci/cache/gate-durations.json` (gitignored) records per-gate timings so the pool starts the longest gates first. Deleting it is harmless.

`npm run ci` runs `--selftest` first: a synthetic failing gate that must produce exit 1, both captured streams, and a skipped dependent. If it prints `CONTROL FAILED`, the runner's green means nothing and nothing else should be trusted until it is fixed.

### Bumping anything

One command moves every pinned version: `npm run pins -- bump <id>`, where the id is a leaf or family of `.ci/config/pins.json` (`npm`, `go-mod`, `actions`, `embed:criu`, `devcontainer:gopls`, `toolchain:go`, `os:opensuse-16.0-ceph`, `real-provider:bitwarden`, `ceph-image`, `image:ci-node`). Every Dockerfile `FROM` image has its own `image:<name>` leaf. The gate that found the pin prints the exact line.

`npm run pins -- status [<id>]` shows each pin and what it could move to, `plan <id>` prints the rewrite without writing, and `when <id>` prints the instant the newest too-new release clears the window. `bump --all` moves everything bumpable; `apply-soaked` does the same for patches and in-range minors only. `bump <id> --to <version>` picks a target inside the window rules. Every verb takes `--json`; `bump` takes `--task <id>` for the commit trailer and `--out <dir>` for the drafts.

A bump is one transaction. It plans every site first and refuses the whole pin when a site does not match its `expect` count or a site file holds changes the run did not make. It then writes the sites, runs the derive steps (credits, goldens, `gate-bind --write`, `go mod tidy`) and the canonical lockfile pass under `npx -y npm@<NPM_VERSION>`, and runs the pin's gates. On failure it restores only files that still hold the bytes it wrote and names any it leaves alone. It never commits and never pushes: it prints per repo, submodules first, the `git add` and `git commit -F <draft> -- <paths>` lines, with message drafts (versions, publish times, gate exit codes) under `.ci/cache/pins/<stamp>/`.

A major is refused unless the run carries `--major --reason "<why>"`; Go majors are always refused. `check:ci-pin-freshness` prints a newer major while its line's first release is younger than `major_grace_days` (40) in `.ci/config/pin-major-grace.json`, and turns red once it is that old, or at once when its first release cannot be dated, until the pin is bumped or held with an expiry. `npm run pins -- hold <id> --reason "<why>" [--expires YYYY-MM-DD]` records a hold in the leaf's first `holds` file (`.ci/policy/.pins-upgrade-blocklist` for the toolchain and docker leaves), renewing an expired line in place; only a hold that carries `--expires` excuses an aged major. Separately, `npm run pins -- remove <pkg>` uninstalls an npm package from every declaring manifest and drops its blocklist, exception, allow, override, syncpack and knip lines. `check:deps -- --upgrade` no longer exists; `npm run pins -- bump npm` replaces it.

`npm run pins -- verify` checks that every site matches its count and agrees with its leaf, and that no earlier run was killed mid-write. It needs the declared submodules checked out.

### Quick fixes for common failures

| Check | Fix |
|-------|-----|
| `check:deps` | `npm run pins -- bump npm`, the npm driver: check-deps' planner under the pinned npm, the canonical lockfile pass and the gates in one transaction. The `.syncpackrc.json` pin groups (`@types/node`, the `@opentelemetry/*` sets, `i18next`, `vite-tsconfig-paths`) move with the bump through its pin-sync step, never by a hand edit of one package.json. A hold is a line in `.ci/policy/.deps-upgrade-blocklist` with a `# BLOCKER:` reason (today only `@types/node`). A major is `npm run pins -- bump npm --to <key> --major --reason "<why>"`, the key (`vite@8`, `private/account/web:vite@8`) being the one `check:deps` prints beside the major |
| `check:ci-real-provider-pins` | The Bitwarden extension or the Vaultwarden server pinned in `private/account/e2e/real-provider.lock.json` is behind a stable upstream release that is past the release-age window. Run the line the message prints, `npm run pins -- bump real-provider:<pin>`, which runs `npm run real-provider:bump` in `private/account/e2e` inside one transaction; then `npm run test:real-provider` there five times against a running account backend, and commit the lock file in `private/account` once it passes. A release list that answers and cannot be read is red too. The gate has no hold list |
| `check:ci-devcontainer-pins` | A tool pinned by `ARG <BASE>_VERSION` in `.devcontainer/Dockerfile` (the Bitwarden CLIs, gopls, Delve, golangci-lint) is behind a stable upstream release that is past the release-age window. `npm run pins -- bump devcontainer:<base>`, the line the message prints, rewrites the version and its sha256 ARGs together and refuses the pin when a digest is missing; `docker build -t rediacc/devcontainer:bump -f .devcontainer/Dockerfile .devcontainer` then proves the hashes. A pin that must stay back goes into `.ci/policy/.devcontainer-upgrade-blocklist` with a `# BLOCKER:` reason |
| `check:ci-embed-asset-freshness` | A binary renet embeds (criu, rsync, zot, k3s, the CSI sidecars), pinned in `private/renet/Dockerfile`, is behind upstream. `npm run pins -- bump embed:<base>`, the line the message prints, moves every pin tied to the component in one transaction: the Dockerfile VERSION, COMMIT and SHA256 ARGs, `embed-assets.lock.json`, the Go constants and goldens, the credits inventories and the vendored-CRD claim. A pin it cannot resolve (rsync publishes no checksum file) is refused whole. A pin that must stay back goes into `.ci/policy/.embed-assets-upgrade-blocklist` with a `# BLOCKER:` reason |
| `check:actions` | An action pinned as `uses: owner/repo@<sha> # vX.Y.Z` is behind its latest release past the window. `npm run pins -- bump actions` resolves the sha from the tag and rewrites every `uses:` pin, `UPLOAD_ARTIFACT_PIN` in `scripts/gate-bind.ts` (a sed bump of the workflows alone is reverted by the next `gate-bind --write`) and the `@sha` patterns in `.ci/config/actions-allowlist.json`, then runs `gate-bind --write`. A hold goes into `.ci/policy/.actions-upgrade-blocklist` with a `# BLOCKER:` reason |
| `check:ci-go-deps` | A Go module of `private/renet/go.mod` is behind a release past the window, or carries an advisory. `npm run pins -- bump go-mod` runs `go get` and `go mod tidy` in renet and mirrors `.ci/scripts/private/license-mint/go.mod`. A Go major is refused whole, since the import path changes with it. A hold goes into `.ci/policy/.go-deps-upgrade-blocklist` with a `# BLOCKER:` reason |
| `check:ci-ceph-image-pin` | The Ceph image or the Leap host pin of `private/renet/.ceph-image-pin` is overdue for review or behind. `npm run pins -- bump ceph-image` moves the dated quay tag within the same host version and sets the review date 90 days out; `npm run pins -- bump os:opensuse-16.0-ceph` moves the Leap pin in its three sites and is refused when the upstream version moved or the mirror tag is absent (no soak, the old build is already gone). A move of the host version is the operator's call |
| `check:ci-docker-image-freshness` | A floating `FROM` tag moved to a newer series. The line is `npm run pins -- bump image:<name> --major --reason "<why>"`, naming the docker leaf whose site matches that `FROM` line (a file with several images, such as `private/renet/Dockerfile`, is matched by line); a docker move is always a judgment call, so there is no unreasoned bump. A `FROM` line no leaf claims is red on every run, stale or not, with the leaf to add (driver `docker`, a version site whose match covers the line; `image:proxy-node` is the shape). `debian:bookworm` is a leaf with `source: none`, since a codename tag has no newer tag to name |
| `check:ci-pin-freshness` | A registry leaf with an upstream source and no freshness gate of its own (the toolchains Go, npm, ruff, uv, mypy, pytest, shfmt, shellcheck, actionlint, nfpm and wrangler, and the devcontainer ARGs outside `check:ci-devcontainer-pins`) is behind. A bumpable leaf is red with `npm run pins -- bump <id>`. A release inside the window is printed as `deferred` with its clear instant and is not red; `npm run pins -- when <id>` gives the instant and a ready worklist DEFAULT line. A major is printed on every run with `bump <id> --major --reason "<why>"`, and so is every newer major line with its first release and the instant it turns red. A newer major whose first release is 40 days old (`major_grace_days` in `.ci/config/pin-major-grace.json`) is red, and so is one whose first release carries no date; the fix is `bump <id> --major --reason "<why>"` or `npm run pins -- hold <id> --reason "<why>" --expires YYYY-MM-DD`, and a held major is printed naming its hold on every run. An undated or expired hold excuses nothing. A docker line is dated from Docker Hub's tag list: a tag's `last_updated` is its last push, so the line is dated by the earliest push among the tags created after the line began (tag `id` order), which can only read younger than the truth. A line in `.ci/policy/.pins-upgrade-blocklist` that no leaf answers to is red. A source that cannot be reached is red, never a pass |
| `check:ci-pin-registry` | A pin site is not in `.ci/config/pins.json`, matches other than its `expect` count, or a copy of a pin's current value sits outside every site. The message prints the entry shape to add. A dead site or ignore is red too: delete it |
| Any external gate says `... were NOT compared with upstream` and `UPSTREAM REACHABILITY FAILURE (<host>)` | Not a finding in the tree, and nothing in the tree fixes it: the gate could not get an answer from the host it names after three tries, and it fails closed instead of passing unchecked. The pin gates, `check:actions`, `check:ci-external-links`, `check:ci-dkim-notify` and `check:ci-go-deps` all print it. Re-run the failed job once the host answers (`gh run rerun <run-id> --failed`); locally, a GitHub rate limit means the request went out with no token (`gh auth login`). On the nightly this red is expected on an upstream blip, see *External gates* below |
| `Quality / Code` (`syncpack lint`) | `.syncpackrc.json` defines `versionGroups` with `pinVersion` and a `sameRange highestSemver` policy. A mismatch means either: (a) you bumped a pinned package beyond its pin — revert to the pin version, or (b) two workspaces disagree on a range — bump the lower one. Run `npx syncpack lint` locally to see exactly which dep violates which group. |
| Lockfile native-binary drift (`Cannot find module @rollup/rollup-*-*` or `lightningcss.*-*.node` or `Expected "0.25.12" but got "..."`) | Lockfile is missing platform-specific native binary entries. npm issue #4828: regenerating `package-lock.json` on a single platform drops optional `@rollup/rollup-*`, `@esbuild/*`, `lightningcss-*-*`, `@tailwindcss/oxide-*-*`, `@img/sharp-*-*`, `@biomejs/biome-*-*`, `oxc-parser-*-*`, `oxc-resolver-*-*`, `syncpack-*-*`, `unrs-resolver-*-*` entries for other OS/CPU combinations. **Never `rm package-lock.json`** on a single-platform checkout; use targeted `npm install <pkg>@<ver> -w <workspace>` instead. If you must regenerate, copy `package-lock.json` from `main` first and let `npm install` reconcile only the diffs. |
| Lockfile npm-version drift (`check:ci-lockfile` says a lockfile is not in `npm@<pin>`'s form, or `npm ci` fails with `Missing: <pkg>@<ver> from lock file`) | npm 11 at the exact `NPM_VERSION` in `.devcontainer/toolchain.env` is the only npm, locally and in CI (`.github/actions/setup-node-npm`). A lockfile written by any other npm, npm 10 in particular, is refused. `check:ci-lockfile` prints `npm run pins -- lockfiles <dir>` for each lockfile it refuses, which rewrites it with the pinned npm; a `npm run pins -- bump` runs that pass itself over every lockfile it touched. |
| `check:ci-budget-freshness` | Read the finding before refreshing. A `drift:unit`, `drift:leg-sum` or `unpriced-unit` finding is a move two sampled runs agree on, or a missing row, of at least half a minute of leg wall: `PYTHONPATH=.ci python3 -m rediacc_ci.ci.freshness --refresh .ci/config/lane-durations.json` writes it, and the check that follows on the same sample is green by construction. A red that a local run does not reproduce read a different sample: re-run with the `--as-of` the red printed (see *The duration tables* below). A unit named as thin or pending is not a finding and needs no refresh |
| `check:ci-shard-manifest-coverage` (unit missing) | `npm run shard:place -- <lane>` places each missing unit and drops the ids of units that no longer exist. Never hand-edit a leg list |
| `check:ci-scope-mirrors` | C2 red (a CLAUDE.md PR-scope clause changed): edit the mirror spans the message lists, then `python3 .ci/scripts/quality/check_scope_mirrors.py --repin <id>`; never repin first, and the repin refuses while a mirror disagrees. C4/C5/C6: restore the `<!-- scope: pr.* -->` anchor or restate the missing atoms from the canonical span. C7: quote CLAUDE.md exactly and mark every cut with `...`. C9: register the restatement in `.ci/config/scope-mirrors.json` and anchor it, or point at CLAUDE.md instead. Never add a finding to `.ci/config/scope-mirrors-baseline.json` |
| `check:ci-env-manifest`, `check:ci-worklist-env-registry`, `check:ci-python-env-registry` | A new environment variable is registered with one command, `npm run env:register` (`rediacc_ci.quality.env_register`). It runs every check before any write, and a re-registration leaves the files byte-identical. The manifest's WORKLIST shard lists are derived from the registry's `class` (harness or gate-seam), so a hand-placed entry fails |
| `check:ci-gh-retry-reads` | Every `gh`/`curl` read in Python (`.ci/`, `.claude/`) must go through `rediacc_ci.core.gh_retry` or carry an allowlist BLOCKER reason; live shell scripts and workflow `run:` blocks are scanned too (curl needs `--retry`, a shell `gh` read a retry wrapper). TypeScript is not scanned. The Stop hook never spawns `gh` itself: `.claude/hooks/stop/wl_gh.py` is its single layer (reads retried, writes run once and only for an argv `gh_retry_reads.classify` calls a write, caches written atomically), and a test refuses a spawn anywhere else in `.claude/hooks/stop` |
| `check:format` | `npx biome format --write packages/ private/account/` |
| `check:i18n` | `npm run i18n:generate-hashes && npm run i18n:sync`, then translate missing keys |
| `check:ci-search-index` | Any www content edit (docs/blog/i18n, all locales) stales the committed indexes: `cd packages/www && node scripts/generate-search-index.js --write-public`, commit `public/search-index*.json` |
| `check:ci-renet` | `cd private/renet && go fmt ./...`, then fix golangci-lint issues. After signature changes also sweep tag-gated files: `go vet -tags "root ebpf_e2e" ./...` (plain `go vet ./...` skips them; OPS CI compiles them) |
| `Quality / Static` (shell format) | `shfmt -w -i 4 <file>` after any shell edit (gate = `npm run check:ci-shell-format`) |
| `lint` / `check:lint` | Fix Biome lint errors properly (never suppress with comments; a deliberate exception goes in `biome.json` with a `BLOCKER:` reason). **Never revert a dev-dep bump (or pin it in `.deps-upgrade-blocklist`) just to silence new rules it surfaces.** The repo's own `eslint-rules/` run through `check:ci-source-rules` and the line budget through `check:ci-max-lines`. When React hook findings (`useExhaustiveDependencies`, state set in an effect, ref writes during render) appear across existing files, fix each site per React 19 idioms: move ref writes into a dependency-less `useEffect`, derive state via the "previous value" pattern (`const [prev, setPrev] = useState(value); if (prev !== value) { setPrev(value); setDerived(...); }`), wrap effect-only side effects in `useEffectEvent` (from `react`, available in 19+), defer problematic setState with `queueMicrotask`, use `window.location.assign(url)` instead of direct `window.location.href = url` assignments, and initialize state lazily with `useState(() => ...)` instead of a post-mount effect. Downgrade is not a fix. |
| `lint:unused` | Add to `ignoreDependencies` in `knip.jsonc` with a `// BLOCKER:` reason if it's a transitive/runtime dep |
| `check:ci-e2e-coverage` | Add coverage for new renet functions in `packages/e2e-tests` (the gate greps e2e-tests for each generated function name) |
| `check:ci-renet` (types) | `cd private/renet && go build -tags nolicense -o /tmp/renet-types ./cmd/renet && /tmp/renet-types functions generate-types --output ../../packages/shared/src/renet-contract/data --version dev`. Never build into `private/renet/bin/renet`: that slot is deployed to machines, and a bare build there ships a binary with no baked key. |
| `check:ci-renet` (i18n orphan keys) | A locale defines a key `en.go` does not, so it is unreachable — lookups resolve against the English key set. Fix: `cd private/renet && ./bin/renet i18n prune-orphans --dry-run`, then re-run without `--dry-run` and `gofmt -w pkg/i18n/locales/`. Always safe to delete. This class hid 191 CORRUPTED KEY NAMES (machine translation rewrote the identifiers, `bridge.create_failed` -> `bridge.create_<arabic>`), invisible because validation only walked English keys. |
| `check:ci-renet` (i18n format parity) | A translation's `%s`/`%d` verbs do not match English. This is a RUNTIME bug, not cosmetic: Go substitutes positionally, so a dropped verb loses the value it should print and an extra one renders `%!s(MISSING)`. Fix the translation in `pkg/i18n/locales/<loc>.go`. If the language needs a different argument order, use explicit indices — `%[1]s`, `%.0[2]f` — numbered by position in the ENGLISH string. The index goes immediately before the verb, AFTER any precision (`%.0[2]f` is valid, `%[2].0f` is `%!f(BADINDEX)`). |
| `check:ci-renet` (i18n word blend) | An English morpheme is fused onto a translated root (`成功fully`, `başarıfully`, `Instすべてing`). Rewrite the whole string naturally; no `-ing`/`-fully` may remain welded to a translated root. Add genuine native words ending in those suffixes to `blendExceptions` in `pkg/i18n/rules.go` (e.g. Estonian `päring`). |
| i18n gating model (renet) | `./bin/renet i18n validate` exits on `.totalCertain`: untranslated, missing/orphan keys, and format-parity (incl. word blends), in EVERY locale. Only the `suspected` fragment heuristic is advisory. This was staged behind a `strictLocales` set while ~1800 pre-existing defects were fixed; all 12 locales are clean and the set is gone. It was never a baseline — a baseline exempts everything and turns "we know" into "fine forever", which is how 2837 grandfathered entries came to hide real bugs. |
| `check:ci-i18n-placeholders` | A locale DROPPED a `{{placeholder}}` English has (information silently lost) or INVENTED one it does not (renders literally to the reader). Covers three sets: `packages/cli`, `packages/www`, `private/account/web`. Fix the locale value; never add the placeholder to English unless the call site passes it. |
| `check:i18n` (orphan keys) | Same class as renet's, in the JSON catalogs: a locale defines a key English does not. English is the source of truth; remove the extra key. Reported per set by `scripts/gates/check-translation-completeness.ts`. |
| `Initialize` (PR title) | PR title must follow Conventional Commits (`type(scope): summary` or `type: summary`). Fix with `gh pr edit <N> --title "fix: ..."`. |
| `Quality / Static` (PR description stale) | Description's `updatedAt` is older than 30 min and there are new commits. Run `gh pr edit <N> --body "..."` **immediately before pushing the next commit** so the fresh timestamp is visible to the next CI run (editing alone does not trigger CI). **The body must actually change** — an edit with identical content does NOT bump `updatedAt`; summarize the new commits instead of re-sending the same text. Stale-only failure: refresh + `gh run rerun <id> --failed`, no commit needed. |

### The duration tables: what they are for and when they drift (`check:ci-budget-freshness`)

`.ci/config/lane-durations.json` and `.ci/config/gate-costs.json` are committed copies of live measurements, registered in `.ci/config/freshness.json`. `check:ci-budget-freshness` compares each with a fresh sample on every PR (Quality / Security, step "CI time budget freshness") and housekeeping runs the same registry nightly.

**What a unit's duration is for.** Three readers price with `units`, and each reads a leg, never one unit on its own. `scripts/gates/check-lane-budget.ts` sums a leg's units into its estimate (`legMinutes`: the fixed cost plus the serial sum divided by `unitParallelism`) and holds it, and any single unit, against the 12-minute budget. `scripts/ci-runner/shard-place.ts` sends a new unit to the lightest leg by the same sum. `conftest.py` starts the longest pytest files first, which reads an order.
The smallest leg difference any of them acts on is half a minute (`REBALANCE_ADVISORY_MIN`), so a unit that is 25% off in isolation changes no answer.

**The drift rule for a unit and for a leg's unit sum** (`budget_report.py`, `MIN_DRIFT_RUNS` and `MATERIAL_LEG_MS`) has three parts, and the refresh obeys the same three.

- **Evidence.** A verdict, slower or faster, needs two distinct sampled runs that measured the unit. One run is one runner: on 2026-10-13 a whole pytest leg ran 35% slower on one runner while the other two legs moved 2.5% and 6.3%. A unit below that count is printed as thin, is not judged, and keeps its committed value through a refresh.
- **Persistence.** Slower needs the median of the window and each of the two newest runs past the limit. Faster needs the slowest sample of the window under it. No single run can produce a finding, in either direction.
- **Materiality.** The move, divided by the lane's `unitParallelism`, is at least 30 s of leg wall and over 25% of the committed value. Many smaller moves in one leg are judged as that leg's sum, by the same two numbers; a leg comes from the committed shard manifest, and a lane with no manifest is one sum.

One thing is judged on a single run: a measured unit with no row in the table, when its cost is a material move from the lane's `defaultUnitMs` (`unpriced-unit`). The job-level findings (a lane's fixed cost over 12 minutes or 25% off, a headroom job's observed max 25% off, a lane with no unit-duration artifact, a stale sample) are unchanged.

**Why the rule has this shape.** The gate went red four times on branch 1008-1 on 2026-10-13 and each fix was a mechanical refresh. Replayed over that day's runs (`.ci/rediacc_ci/tests/fixtures/budget_drift/20261013.json`), 15 of the 17 findings on run 38409515814 were slower verdicts from one or two samples, and 12 of the 14 findings one run later were units the refresh had kept because a thin sample was never lowered.
Under the rule the same day gives two reds of three findings each, all of them real: a 166 s test file with no row, an Account E2E leg priced a third too high, the pytest lane's largest file 31% slower on two runs.

**The pre-push check and the CI step read windows one run apart**, because the push itself completes or cancels a run in between. The rule is built so that one run cannot change a verdict, and every verdict prints the sampled run ids with the bound that reads the same sample again:

```bash
PYTHONPATH=.ci python3 -m rediacc_ci.ci.budget_report --check --as-of 2026-10-13T15:05:49Z
```

`--as-of` keeps only the runs that had completed by that UTC time, so a CI red is re-judged locally on the sample CI read. It bounds `--refresh` the same way.

**`gate-costs.json` follows the same evidence rule** (`gate_costs.py`, `MIN_DRIFT_CAPTURES`). A gate's `cpu_s` or `eff_cores` drift is judged only when two nightly captures measured it, a `cpu_s` move has to be a cpu-second, and a refresh keeps the figures of a fast gate that one capture measured. The window holds at most three captures and shrinks to one whenever a nightly capture fails, and the committed file held against one capture alone gave 3 to 22 drift findings on 2026-10-13. The structural findings (a gate missing from the file or the manifest, one no capture measured, a changed core count) are judged on one capture.

### CI failure triage: read the whole log before diagnosing

Do NOT classify a CI failure from a handful of grepped lines. The cost of a wrong diagnosis (a wasted pipeline round, or worse, teaching the watchdog to retry a real bug) is far higher than the cost of reading one log properly.

**"My check passed" and "my check did not run" are indistinguishable without a control that can fail.** Before believing a clean result, make the check produce a RED on known-bad input through the same path. Two real examples from one five-minute stretch on 0804-1, both caught only because the control was run: a `git archive` that silently extracted nothing, so a `[ a -nt b ]`
staleness test compared two *absent* files and returned false — looking exactly like a genuine "not stale" answer; and a deliberately restricted `PATH` that also hid `bash` itself, so the command under test executed **neither** branch while appearing to run. A green from an instrument that cannot go red is not evidence, and this applies recursively — to the check, and to the check
of the check.

1. **Fetch and read the COMPLETE failed-step log** (`.ci/scripts/ci/ci-trace.py --why` names the job and step, `--job <id> --errors` slices that step, `--job <id> --log` prints the whole log), including the full error message body — error texts often name their own cause (e.g. esbuild's "could not be found" error explicitly points at `--omit=optional`/optionalDependencies; npm's EUSAGE block names the exact missing lock entries). Selective `grep error | tail` hides the sentence that matters.
2. **Suspect your own commits first.** Before reaching for "transient infra", check whether the failing signature matches a documented failure mode in this file AND whether a commit in the current PR touched a related file (`package-lock.json`, `.npmrc`, migrations, workflows). Correlation with your own push is the default hypothesis, not the fallback.
3. **Reproduce in a clean room before calling anything transient.** "Works on my machine" with a warm cache and dev node_modules proves nothing. Match CI: export the tracked tree (`git checkout-index -a --prefix=<scratch>/` — `git archive` is blocked by `.gitattributes` `* export-ignore`), use CI's exact npm via `npx -y npm@<ver>` (version is printed in the job's setup-node "Environment details"), and a cold cache (`--cache <fresh-dir>`). Compare concrete numbers against the CI log ("added N packages"). Only when the clean room passes may the failure be called transient — and say so with the evidence, not instead of it.
4. **A green rerun on identical inputs is confirmation, not the investigation.** Use it to close the loop after steps 1-3, never to skip them.

### CI fix cycle

When fixing CI failures, follow this loop:

1. **Run locally first**: Run `npm run ci` sub-commands locally before pushing to avoid costly CI round-trips. Use parallel sub-agents for independent checks.
2. **Push and watch**: After pushing, run `.ci/scripts/ci/ci-trace.py --wait` with run_in_background: true — the process exit notifies on completion. Ad-hoc watch commands are refused by `block-adhoc-sanctioned.sh` and a hand-rolled watch blocks the Stop hook, because the recipe rotted in nine places and reported superseded verdicts twice.
3. **Fix on notification**: When the background watch completes, list every job that is neither `success` nor `skipped` (filtering for `== "failure"` alone hides a cancelled gate, which did not report). A run that ends `cancelled` with a failed job means the watchdog killed it for that failure; `cancelled` with zero failed jobs is a gate that did NOT report — a newer push superseding the run is the usual cause, but it is not proof of one, so confirm a newer head actually exists before assuming it (on 2026-09-05 a cancelled `Review Status` sat on `a032863c7` while that WAS the head). `.ci/scripts/ci/ci-trace.py --run <id> --why` attributes the cancel from evidence instead (`watchdog-budget`, `watchdog-failure`, `superseded`, `timeout-kill`, `manual`, `unknown`); run 36953549081 on 2026-10-02 was a watchdog budget cancel with zero failed jobs. Cancelled NEVER means green — the run is only done when every job passes (deploy preview is among the last).

Two ways this step lies to you, both observed on 0804-1:
   - **A watch missing from the background roster means it died OR it fired.** Those look identical from the outside, and the wrong guess is expensive in both directions (concluding "terminal" when the run is still going, or waiting forever on a watch that is gone). Re-check the run itself with `.ci/scripts/ci/ci-trace.py --run <id> --jobs` before inferring anything, then re-arm — an extra watch costs nothing.
   - **The job roster GROWS as the run progresses.** It starts around 19 jobs and reaches roughly 78 (97 with the E2E legs). An early `--json jobs` snapshot showing "2 still running" is not the full roster and does NOT mean the run is nearly done. This is the same trap as reading a cancelled job as a passing one: in both cases the job list is not yet the thing it appears to be. Trust `status`/`conclusion` on the run, not your arithmetic on a partial job list.
   - **The newest run in a raw run list is usually NOT the run being traced.** It is recency-sorted, and the watchdog's `Watchdog Monitor` generations are `workflow_dispatch` runs that chain every ~8 minutes against the OLD head sha — so the newest entry is routinely a monitor generation, and its `failure` conclusion is the monitor signalling a cancellation, not CI failing. Select by head sha instead: `.ci/scripts/ci/ci-trace.py --runs` lists only the branch's Console CI runs with their head sha and event (`--watchdog` lists the monitor generations separately), and a raw run list of Console CI is refused by `block_raw_ci_read`. Watching the wrong id costs a whole round, because the watch fires immediately on an already-terminal run.
4. **Review is per commit, not per PR.** The post-bash hook reviews each commit when it is made. A clean verdict with full coverage is one line of `agent/reviews/<branch>/clean.jsonl`, and every other verdict is `agent/reviews/<branch>/<sha>.md`. Ready and merge require that every commit since the base has a per-commit review record in `agent/reviews/<branch>/` with no open finding at or above `block_at` and no deferred finding at any severity, and every record is committed (`python3 .claude/hooks/stop/wl_review.py --check`). `block_push_with_unrecorded_reviews` refuses a push until then, and `block_admin_merge` refuses a merge. In CI, `check:ci-review-resolutions` (Quality / Branch) refuses the same deferral and open finding on the PR head. The only escape from a finding is `waived #<item> ASKED:<YYYY-MM-DDTHH:MM>Z`, for a finding whose triage verdict is OPERATOR-ONLY (operator ruling 2026-10-08). Human review threads still fail `Review Gate` (console PR) and `Quality / Submodule Branches` (submodule PRs) while unreplied or unresolved: fetch `gh api repos/<owner>/<repo>/pulls/<N>/comments`, fix what is real, reply substantively, and resolve the threads via GraphQL before the gate re-runs.

**Scheduled workflows** (the nightly Console CI, housekeeping, promote-stable, the OBS mirror, the VM bake) run on no PR, so no PR watch sees them. `ci-trace.py --scheduled` lists the newest scheduled run of each with its failed jobs, and the Stop hook's `scheduled-red` check blocks the one session that claims an untracked red until an item tracks it (`sched:<stem> run:<id>`); other sessions get an advisory. A ci:quick gate was rejected for this: the quick lane is offline, and a nightly red is never caused by the commit being pushed. The CI time budget files (`.ci/config/lane-durations.json`, `.ci/config/gate-costs.json`) are compared with the newest runs on every PR by `check:ci-budget-freshness` (pull_request events only: the rolling sample drifts on main's push and scheduled runs with no PR to refresh the file, which kept the nightly Console CI red 2026-10-06..08; housekeeping's 03:00 budget-check covers those), not only in housekeeping; drift is refreshed in the open PR with `python3 -m rediacc_ci.ci.freshness --refresh <artifact>` (run from `.ci/`). Both files are registered in `.ci/config/freshness.json`, and `rediacc_ci.ci.freshness --check --cadence pr` (what `check:ci-budget-freshness` runs, and the one housekeeping step) checks every registered artifact under one shared deadline and is the only writer of the report. A new time-budget artifact is one registry entry, not a new gate.

**A nightly red whose log says `were NOT compared with upstream`** (Quality / Go, Code or Content) is an upstream reachability failure, not a defect on main. `ci-trace.py --why` reports it as `infra-likely` with the signature `upstream-unreachable` (a confirmed stale pin reads `code-likely`, `pin-stale`), and the finding names the host. The fix is a re-run of the failed job once that host answers; the tracking item is still required, and it closes on the green re-run (see *External gates and `external_quality`* below).

5. **Fix, commit, push, repeat**: Fix the issue, commit, push, and watch again. Batch pending fixes into one push — each push restarts the whole pipeline. Continue until green.

### Quality lanes and the ubuntu-slim cap

The quality phase is **ten lanes**, not one job per gate. Gates are grouped by what they need on disk (bare checkout / node / node+submodules / node+build / go), so a lane pays its setup once: `Static`, `Branch`, `Submodule Branches`, `Code`, `Content`, `Packages`, `i18n`, `Built-www Gates`, `Security`, `Go`. `.github/workflows/ci-quality.yml` opens with the rules for editing one.

Two things follow that you will hit in practice:

- **A lane runs all of its gates even after one fails.** Every gate step carries
`if: ${{ !cancelled() && steps.setup.outcome == 'success' }}`, so one push surfaces every failure in that lane. Do not "fix the first red and push" -- read the whole lane's step list first.
- **`ubuntu-slim` dies at 15 minutes, hard.** The job is marked CANCELLED with no
failed step, which reads as neither pass nor fail and poisons `CI Complete`. Every slim job must therefore declare `timeout-minutes` of 14 or less; CHECK 3 in `.ci/scripts/security/check_workflow_gates.py` enforces it. A job that genuinely needs longer moves to `ubuntu-latest` -- the number is not a dial.

Dependencies come from `./.github/actions/setup-workspace`, which restores a cached `node_modules` (200 MB, ~2.5s) instead of running `npm ci` per job. On a cache miss it falls back to `rediacc_ci.setup.install_deps`, so a miss is slow, never broken.

### Runner profiling is an invariant, not a habit (`check:ci-profiler-coverage`)

Standard runners are free and unlimited on this public repo, which is exactly what makes oversizing invisible: a job that uses ~1 core on a 4-vCPU `ubuntu-latest` VM burns four cores' worth of the world's electricity to do one core's work, and no bill ever says so. `./.github/actions/profiler` samples cpu/ram/disk/net and appends a profile to the job's own summary panel, so runner
sizing becomes a measurement instead of a guess. Coverage maintained by habit decays the first time somebody adds a job in a hurry, so `check:ci-profiler-coverage` (`.ci/rediacc_ci/quality/profiler_coverage.py`) makes it a build failure.

It asserts two relations over `.github/workflows/*.yml`:

- **Coverage.** Every job whose `runs-on` resolves to Linux (`ubuntu-*`,
including matrix legs) must use the action. Reusable-workflow callers (`uses: ./.github/workflows/...`) are excluded: they have no runner of their own, and their steps are the called workflow's jobs, which the gate sees in that file. macOS and Windows jobs are out of scope (the sampler is Linux-only).
- **Configuration.** A job that uses the action must reference it as
`./.github/actions/profiler` (a missing `./` is read as `owner/repo` and fails at workflow parse time), pass only inputs `action.yml` declares, keep `interval` a positive integer in 1..300, and pass a `runner-label` that agrees with its own `runs-on`. That last one matters most: `runner-label` arms the HOST_LEAK check, and a copy-pasted `runner-label: ubuntu-latest` on an
`ubuntu-slim` job makes the sampler read the host's 4 cores / 16 GB as the job's own, which is wrong in the direction that moves work onto a runner that cannot hold it.

Two design points worth knowing before you edit a workflow:

- **It fails CLOSED on what it cannot resolve.** `runs-on: ${{ inputs.runner }}`
has no static answer, so the job counts as REQUIRING coverage. "We could not tell" costs an allowlist line with a reason; it is never silently exempt.
- **Coverage counts `setup-workspace` as a wrapper.** The open question this
bullet used to carry — does a JavaScript action's `post:` hook fire when nested inside a composite? — was ANSWERED YES on 2026-08-08 by dispatching `profiler-probe.yml` (run 31252148469: `Post Run ./.github/actions/profiler/ nest-probe: success` on both ubuntu-slim and ubuntu-latest). The profiler is therefore wired as one early step in `.github/actions/setup-workspace`, that
composite is the gate's built-in wrapper default (`WRAPPER_DIRS`, still extendable via `PROFILER_COVERAGE_WRAPPER_DIRS`), and the 25 ledger lines for jobs covered that way are burned. The same probe settled the container facts: GitHub's slim is cgroup **v1** (the sampler's v1 fallback resolves cpu+memory), host views are container-scoped there (`nproc`=1, MemTotal≈4.8 GiB), `awk`
and `node` are present, and a sample costs ~742µs.

**Do not flip that seam without also extending the CONFIG relation.** The configuration checks only inspect DIRECT uses, and a composite forwards a fixed input, so a job covered through the wrapper passes no per-job `runner-label` and is checked for none.

How much that costs depends on runtime behaviour that lives in `.ci/scripts/ci/profiler/report.awk` (`advise()`) and `sampler-linux.sh`, and it has moved twice already, so read those rather than trusting a summary here. The stable parts:

  - **A cgroup-tier reading is self-validating.** The kernel-enforced quota is
    ground truth about the box regardless of what anyone labelled it, so the
    advisor keys on the ceiling there and a missing or wrong label costs
    nothing. A `PROC_HOST` reading is not: `/proc` is only the job's ceiling if
    the job owns the whole machine, which is exactly what the label asserts and
    cannot prove.
  - **So the label matters only when the cgroup read failed**, and there its
    absence mutes the advisor while a wrong value is what the runtime guards
    (`HOST_LEAK`, `MISLABEL SUSPECTED`) exist to catch.

The gate's runs-on/runner-label agreement check is authoring-time defence-in-depth over those runtime guards, not a substitute for them: it fires before a run exists, off the workflow text, with no dependence on fingerprint heuristics. It needs BOTH values to be literals, which the wrapper path prevents. And there is no `runs-on` value in any runner-side context (`runner.os` is
`Linux` for slim and latest alike), so the label can only be threaded by hand: either each job passes it through the wrapper, which is most of the edits the nesting was meant to avoid, or the guard needs a different signal. Settle that first, then extend the config relation to the wrapper's call sites in the same change.

**The allowlist can only shrink.** `.profiler-coverage-allowlist` takes `<workflow>.yml:<job>` entries under the usual `# BLOCKER:` convention (`docs/agent-reference/suppressions.md`). It currently carries the rollout ledger: 90 jobs unwired as of 2026-08-05, plus `breakpoint.yml` (frozen in `.ci/breakpoint/MANIFEST.sha256`, so a console-only step would fail the drift gate) and
`profiler-probe.yml`'s own experiment arms. Delete a job's line in the commit that profiles it: the gate re-derives its oracle every run and rejects an entry whose job no longer exists, is now profiled, is a caller, or does not run on Linux, so a forgotten deletion is a build failure rather than dead weight. That is the liveness half of the BLOCKER convention, enforced inside the
gate rather than by a probe in `scripts/gates/check-suppression-liveness.ts`, because the oracle IS the parse the gate already performs.

### CI watchdog and auto-retry

The CI has a watchdog (`watchdog-monitor.cjs`) and cancellation script (`cancel-older-runs.sh`) that manage run lifecycle.

The watchdog runs OUTSIDE the CI run, as a chain of short ubuntu-slim generations in the separate "Watchdog Monitor" workflow (`watchdog-monitor.yml`): the 1-vCPU runner's 15-minute job cap is a hard platform limit, so each generation polls ~8 minutes and dispatches the next via `dispatch-watchdog.sh`. The in-run `CI Watchdog` job is only a bootstrap (cancel older runs + dispatch
generation 1). The retry path lives in the SAME chain: a transient verdict sets a `pending_rerun` flag carried through generations; when the run completes, the chain reruns the failed jobs itself (with `check-rerun-attempt.sh` as a separate deterministic attempt-cap pre-step) and keeps monitoring attempt 2. Consequences when triaging: watchdog verdicts, cancellation annotations,
and retry decisions appear on `Watchdog Monitor` runs, not inside the CI run's own job list. A lost dispatch fails open -- the run finishes unwatched, and `ci-complete` still gates.

- **New push -> old runs cancelled**: `cancel-older-runs.sh` force-cancels all older in-progress runs on the same branch. **Never re-run a cancelled run** -- cancelled means superseded.
- **Scheduled (nightly) runs are NEVER cancelled.** Cancelling rewrites a run's
conclusion from `failure` to `cancelled`, and everything downstream reads `cancelled` as "superseded, ignore". On a PR that is survivable; on the nightly it is fatal, because the nightly is the only suite validating `main` (`full_suite` is `event != 'push'`) and nobody is watching it. Measured 2026-07-27: **12 of 12 scheduled runs `cancelled`, zero successes, back to 2026-07-16**,
entirely unnoticed. On a scheduled run the failure is recorded, the run is left to conclude as `failure`, and the watchdog KEEPS MONITORING so later failures are still logged and captured. See `evaluateCancelExemption`. This has to live in code: labels are read from the PR, and a scheduled run has none.

**Retries are NOT suppressed on the nightly, only cancels are.** A flaky E2E leg is still re-run under the allowlist rules below. Suppressing both would make a network blip turn the nightly red, and a nightly that cries wolf trains everyone to ignore it -- the same disease as the laundering. `forceCancel` therefore reports whether it actually cancelled, and only a real cancel ends
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
`watchdog-logs-<run-id>-gen<n>` artifact on the corresponding `Watchdog Monitor` run. A rerun makes attempt 1's logs unreachable, so retrying used to destroy the evidence for the only question worth asking afterwards. Capture happens for every handled failure regardless of which branch handles it.
- **Job failure (attempt 2+)**: Watchdog force-cancels the entire run -- no infinite retry loops.
- **Quality lane failures**: Never auto-retry, never use AI (a lint or type error is deterministic; retrying it is pointless). The force-cancel now **drains first**: it waits until every other `Quality / *` lane reaches a terminal state, then cancels once with the full failure roster. So one round reports every failing lane instead of only the first, which is what used to make gates look like they failed serially. The expensive legs (E2E, OPS) are not in the no-retry set, so they still die immediately.
- **Review Gate failures**: Never auto-retry, never use AI, and never drain. Fail immediately and force-cancel -- an outstanding review is not a red to race past.

**PR labels** to control behavior:

| Label | Effect |
|-------|--------|
| `no-cancel-push` | Don't cancel older runs on new pushes |
| `no-auto-retry` | Skip retry, force-cancel immediately on failure |
| `no-auto-cancel` | Hold a failing run open: a failed job does not cancel the rest of the run (see below) |
| `no-external-quality` | Skip the externally-dependent gates (see `external_quality` below) |
| `no-media-quality` | Hold the tutorial-media gates (see `media_quality` below) |

**`no-auto-cancel` holds a failing run open.** With it on the PR a failed job cancels nothing: every other job runs to its own conclusion, the watchdog still prints the failure roster and records the decision as `left-uncancelled` on the `Watchdog Monitor` run, and the run concludes `failure` from its own failed jobs, so CI Complete is red exactly as it would have been. The label changes how much one run reports, never a pass into a fail or back; the one exception to the hold is the time budget, where a labelled run still live is force-cancelled and concludes `cancelled`.

What it leaves alone:

- **Time budgets.** A live job over its per-job budget (15 minutes, or its `JOB_BUDGET_CAPS` cap) still force-cancels the run with the `CI BUDGET VIOLATION` annotation. A job GitHub already killed at its `timeout-minutes` is annotated and never retried, and the run stays open past it, since a cancel reclaims nothing from a dead job.
- **New pushes.** A push still cancels the PR's older run (the concurrency group, and the `Cancel older runs` step unless `no-cancel-push` is also set).
- **Auto-retry.** A failure judged retryable still holds a pending rerun, and the failed jobs are rerun once after the held-open run completes. Nothing is cancelled to make room for it. `no-auto-retry` beside it turns the rerun off as well, and the run simply finishes red.

The watchdog reads PR labels live from the API at each decision (once per generation, once per newly handled failure, and again inside `forceCancel`), so adding or removing `no-auto-cancel` or `no-auto-retry` takes effect on a run already in flight, at its next failure. `no-cancel-push` is read from the event payload by `ci.yml`, so it counts from the next push.

**The cost, and when to take the label off.** A held-open red run waits for the long E2E and OPS legs before it concludes, so each round costs the full pipeline instead of the seconds a first failure takes. The label is for a branch being DIAGNOSED, where one run that names every failure is worth more than several fast runs that name one each. Remove it once the remaining failures are known and the branch is being driven to green.

**History.** `no-cancel-failure` did this job until it was removed on 2026-08-05 for exactly that cost, on the reasoning that the full roster of deterministic reds arrives anyway (the Quality drain collects every lane, and `forceCancel` re-fetches the job list). That holds for the Quality lanes only. `no-auto-cancel` brought the hold back on 2026-09-27 (`d1f764a66`) when the sharded E2E legs could not report through any early failure, and this section went on saying no such label existed. On 2026-10-13 a `Quality / Secure Storage` macOS/Windows leg that fails within seconds twice cancelled the other 87 jobs of a PR #600 run: the K8s E2E, account E2E, Pytest shard and build legs ended `cancelled` with no verdict, and each fix cost a full extra round.
The operator ruled the same day that a PR label is the answer; the label was already there, so the ruling is carried out by documenting it here, by keeping time budgets enforced under it, and by reading labels at the decision.

Matrix `fail-fast` and `needs:` chains are out of its reach: see *GitHub matrix fail-fast beats the `no-cancel-failure` label* in [TRAPS.md](TRAPS.md).

Labels apply to PR runs only. A `push` or `schedule` run has no PR, so none of them are readable there -- which is why the nightly exemption above is in code rather than in a label.

### External gates and `external_quality` (hard / skip / soft)

The externally-dependent quality gates are `check:deps`, `check:ci-go-deps`, `check:ci-embed-asset-freshness`, `check:ci-devcontainer-pins`, `check:ci-real-provider-pins`, `check:actions`, `check:ci-external-links` and `check:ci-dkim-notify`, plus the audit.
ONE flag, `external_quality`, computed by ci.yml's initialize job and passed into ci-quality.yml as a `workflow_call` input, holds them:

`check:ci-go-module-sync` is deliberately NOT in that list, and the omission is a decision rather than an oversight. It sits next to `check:ci-go-deps` in the `quality-go` job and both are about Go dependencies, so the natural assumption is that it belongs behind the same flag. It does not: it reads only the local worktree, comparing each module that `replace`s renet against
renet's own `go.mod`, so no registry can make it fail. Putting it behind `external_quality` would let the `no-external-quality` label skip a defect we caused ourselves.

- **hard** -- normal PR: a failure blocks.
- **skip** -- PR carrying the `no-external-quality` label: the steps do not run
at all (offline branch work; the lookups cannot succeed).
- **soft** -- schedule / workflow_dispatch: the gates run exactly as under **hard**. No gate runs behind a wrapper, so nothing downgrades a failure to a warning; the value stays distinct so `check:ci-workflow-invariants` can prove that no event other than a pull request resolves to **skip**.

**Every external gate is hard on every cadence and fails closed** (operator rulings 2026-10-13, "Fail closed every time" and "Everything fails closed, nightly included", and 2026-10-14, "Extend to all seven"). Each reads only the **skip** half of the flag. Each step runs `npm run <gate>` directly with the `if:` conjunct `inputs.external_quality != 'skip'` (the gate header's `when:`, which gate-bind emits), so a finding and an upstream that could not be reached are red on a pull request, on the nightly and on a dispatch alike.
`check:ci-workflow-invariants` pins that shape (`analyse_upstream_gates`, over `UPSTREAM_GATES`): a step that gains another `if:` (a gate-bind shard conjunct aside) or loses its announcer is refused, as is a ci.yml whose `external_quality` can resolve to `skip` off a pull request.

`check:deps` asks the npm registry (`npm outdated`, and registry.npmjs.org for the packuments of uninstalled edges), so it has always been an external gate, and its `DepsProbeError` has always failed closed. Until 2026-10-14 its step carried no label hold even though this section listed it as label-held; it now carries the hold and is named by quality-content's announcer.

A thing whose upstream answer was not obtained is a red finding, with what was asked, the host and path, the HTTP status, DNS code or error code, the number of attempts, and the sentence `UPSTREAM REACHABILITY FAILURE (<host>), not <the finding it is not> and not a defect in the tree`. That covers DNS, connect and timeout failures, any transient HTTP error, a rate limit and a refused token.
Each request is tried up to 3 times, 15 s each, with 2 s and then 4 s between tries, for a network error, a timeout, 408, 429, a 5xx or a 403 carrying `Retry-After`; a primary rate limit, a 401, a 404 and a `Retry-After` above 10 s are answered at once.
A gate asks concurrently, so the worst case is 51 s per chain of requests. An answer that arrives and cannot be used (not a release list, no release under the tag prefix, an index with no tarball, an action with no published release) is red too.
The request, the retry and the wording live once, in `scripts/lib/upstream.ts`; the Go gate is Python and carries the same rule in `rediacc_ci.core.upstream`, and `test_core_upstream.py` fails when the two copies' numbers disagree.

What each gate asks, and what a definite answer means:

| Gate | Upstream | A definite answer that is a finding, not an outage |
|---|---|---|
| `check:ci-real-provider-pins` | api.github.com `GET /repos/<repo>/releases`, for bitwarden/clients and dani-garcia/vaultwarden | a listing with no stable release under the tag prefix |
| `check:ci-devcontainer-pins` | api.github.com `GET /repos/<repo>/releases`, for each repository in `scripts/lib/devcontainer-pin-sources.ts` | the same |
| `check:ci-embed-asset-freshness` | api.github.com `GET /repos/<repo>/releases/latest` for each GitHub source in `scripts/lib/embed-asset-sources.ts`, and on a 404 (a project that tags without releasing, CRIU) `GET /repos/<repo>/tags` then `GET /repos/<repo>/commits/<tag>`; download.samba.org `GET /pub/rsync/src/` and `HEAD /pub/rsync/src/rsync-<v>.tar.gz` | an index with no tarball |
| `check:actions` | api.github.com `GET /repos/<owner>/<repo>/releases/latest`, for every action pinned under `.github` | a 404 (no published release) or a pin with no version comment |
| `check:ci-external-links` | every linked host, `HEAD` then `GET` | a 4xx after the GET fallback is a BROKEN link; only no answer, a 5xx, a 408 or a 429 is an outage. Once 20 links in a row went unanswered with no host answering at all, the rest are not asked and the run says so |
| `check:ci-dkim-notify` | 1.1.1.1 then 8.8.8.8, TXT for the active selector and MX for the three MAIL FROM names | NXDOMAIN or NODATA is a missing record, a DNS finding |
| `check:ci-go-deps` | the module proxy through `go list -u -m -json all`, and `POST api.osv.dev/v1/query` for each candidate | a `go list` failure that is not network-shaped stays the toolchain probe failure; an OSV that cannot be asked is red, where it used to be a warning and an unscreened demand |
| `check:deps` | the npm registry | a registry that does not answer is a `DepsProbeError`, red, worded as its own message rather than the shared sentence |

One request is not a finding when it fails: the `HEAD` for the rsync tarball's date. The version comparison has already happened by then, a missing date means no soak, and no soak can only report a newer rsync sooner. The gate prints the failure with its host.

**The nightly goes red on an upstream blip, on purpose.** Nothing in the tree fixes that red: the failed job is re-run once the host answers (`gh run rerun <run-id> --failed`), and a green re-run attempt clears the scheduled red.
`ci-trace.py --why` and the Stop hook's scheduled-red block name it `infra-likely`, signature `upstream-unreachable`, so it is not read as an unknown or as a defect on main; a confirmed stale pin reads `code-likely`, `pin-stale`, and its fix is the bump the message prints.
The 2026-08-04 measurement that made these gates soft (5 of 8 nightlies red on external drift) still describes the cost; the rulings accept it for every external gate.

**The `no-external-quality` label still holds them on a pull request, and the log says so.** Under **skip** the steps do not run. Each job that holds one runs `rediacc_ci.quality.announce_gate_skips no-external-quality <its gates>` unconditionally (`Announce external gates held by label`, in quality-code, quality-content and quality-go): with the label it emits a `::warning::` and a step summary naming each gate that did not run, and without it it prints the count of gates enforced.
No label can apply to a `schedule` or `workflow_dispatch` run, so on those cadences every external gate always runs.

`audit.py` gets only the skip half too, by the earlier operator decision of 2026-08-04: a new production advisory against main's unchanged lockfile is a real signal about main.

A new external gate gets `when: inputs.external_quality != 'skip'` in its header, a name in its job's announcer and in `UPSTREAM_GATES`, and its requests through `scripts/lib/upstream.ts`. It never gets `continue-on-error` (banned by check-workflows.sh) or a wrapper that softens its exit code.

### Tutorial-media gates and `media_quality` (hard / skip)

Five validators read the recorded tutorial media -- the `.cast` files and the transcript, narration-audio and parity artifacts derived from them, carried by three CI steps across two jobs. They are controlled by `media_quality`, computed by ci.yml's initialize and passed into ci-quality.yml as a `workflow_call` input:

- **hard** -- everything except a labelled PR: a failure blocks.
- **skip** -- PR carrying the `no-media-quality` label: the three steps that
run them do not execute.

There are only two states, deliberately. `external_quality` keeps a third, `soft`, which now behaves as `hard`; nothing here reads the outside world, so a media failure on `schedule` means main's own media is inconsistent, which is a red the nightly should carry. For the same reason there is no wrapper: with no soft state there is nothing to downgrade.

**What the label holds, and nothing else:**

| Gate | Job |
|------|-----|
| `check:ci-tutorial-casts` | `quality-content` |
| `check:ci-tutorial-parity` | `quality-content` |
| `check:ci-i18n-media` (transcripts + narration audio + cast output) | `quality-i18n` |

**What it deliberately does NOT hold**, because each still catches a real defect while media is being re-recorded: `check:ci-tutorial-commands`, `check:ci-tutorial-noninteractive`, `check:ci-tutorial-cli-validity` and `check:ci-tutorial-no-skips` (these read the `.sh` scripts and the live command tree, so a red is genuinely new), `check:ci-tutorial-caption-sync` (fetches PUBLISHED
CDN content, so a red is a production defect until the new media is published), `check:ci-tutorial-card-fonts`, `check:ci-locale-tutorial-assets`, `check:ci-tutorial-healthcheck-headroom`, `check:ci-tutorial-render-queue`, and both solution-video gates (a different asset family entirely). Widening the set is not a convenience, it is coverage nobody asked to lose.

**The label is a HOLD, not an exemption, and the log says so.** A skipped step leaves its job `success` and prints nothing, so both consuming jobs run `rediacc_ci.quality.announce_gate_skips` UNCONDITIONALLY -- it is not behind the mode `if:`. In `skip` it emits a `::warning::` and a step summary naming every gate that did not run plus the instruction to remove the label; in
`hard` it prints the count of gates enforced, so a missing announcer and a silent one cannot look alike. It also refuses (exit 2) an unrecognised `media_quality` value, which is the only place a typo in that wiring is ever reported: the step `if:` treats anything it does not recognise as "run", which is fail-closed but completely silent. `test-gate-skip-announcer.sh` pins all of
it, including the workflow wiring itself.

Remove the label as soon as the media work it is waiting on lands, and let the run go red if the underlying defect is still there.

Re-running (`gh run rerun`) is only appropriate for transient errors (network, flaky infra) on failed — not cancelled — runs.

### The nightly is reported, not just run

A red nightly opens (or comments on) a single rolling `nightly-red` issue, labelled `bug` + `automated`, naming the failed jobs with log links; it closes itself on the next green nightly. One rolling issue rather than one per night, because the observed failure mode is a long unbroken streak and a wall of identical issues is its own kind of invisible. Driven by `nightly-status.yml`
(`workflow_run` on Console CI, filtered to `event == 'schedule'`) calling `report-nightly-status.cjs`.

**A scheduled run can also be rehearsed on demand**: `ci.yml` accepts `workflow_dispatch` on `main` (guarded; a dispatch on any other ref fails loudly). It is schedule-equivalent by construction -- `full_suite` is `event != 'push'` and the channel resolves to empty for anything that is not push or pull_request -- so it exercises the nightly path without waiting a day. That matters
because the alternative is one attempt per 24 hours, which is not a feedback loop.

### Labels: the chain from a code reference to a PR comment

Labels in this repo are kill switches (`full-ci` bypasses the scope engine's skips, `no-cancel-push` disarms the watchdog, `rollback` blocks stable promotion), and nothing about a label is self-documenting. Four links now connect a label reference to a human who can understand it, each enforced by a different thing:

| Link | Enforced by |
|------|-------------|
| code names a label -> declared in `.github/labels.yml` | `check:ci-label-refs` (`.ci/scripts/quality/check_label_references.py`) |
| declared <-> the label exists on the repo | `check:ci-label-inventory` (`.ci/scripts/quality/check_label_inventory.py`) |
| declared (and not `guide: false`) -> explained on every PR | `label-guide` job in `ci.yml` -> `.ci/scripts/ci/label-guide-comment.cjs` |

**The inventory gate** reconciles `.github/labels.yml` against the live repo in both directions. Declared-but-absent is the direction that already bit: `rollback` was declared and referenced while not existing, and `promote-stable.yml` searches `label:rollback` -- a search for a nonexistent label returns zero PRs rather than an error, so the promotion block silently never fired.
Live-but-undeclared is the quieter direction: such a label never reaches the PR guide, so people can apply it and nobody can look it up. If the live list cannot be read (no token, API error, empty response) the gate REFUSES rather than passing; an empty label list is a failed read, never a clean tree.

**Verify-at-read, for the absent direction only.** The list is a snapshot and the repo's labels change under it. A full run once accused `no-auto-retry` of not existing while it existed and `watchdog-monitor.cjs:1105` was reading it -- someone was mid-way through a delete-and-recreate, and the paginated list came back one short. The empty-list guard does not catch wrong-by-one, so
a race produced this gate's loudest message, the one about `rollback` and silent fail-open. A gate that cries wolf that hard gets ignored, and is then worth nothing on the day it is right. So a label that looks absent is re-read on its own (`gh api repos/{owner}/{repo}/labels/<name>`, URL-encoded) before it is accused: a 404 confirms the finding, a 200 drops it with a note, and
anything else (403, 500, network) counts as "could not tell" and the finding stands. Only this direction needs it -- a stale read loses entries, it never invents them, so an extra name cannot be an artifact. In injected mode (`LABEL_INVENTORY_LIVE_FILE`) there is no API to re-read, so the injected list stands as its own authority and findings are reported;
`LABEL_INVENTORY_PROBE_FILE` is the separate seam that lets the test drive both re-verify outcomes offline. One label is exempt from the absent direction, via a commented allowlist inside the script: `nightly-red` is created on demand by `report-nightly-status.cjs` right before it opens the rolling issue. The allowlist re-verifies both halves of its own entry each run, so the
exemption expires rather than rots.

Its CI coverage is `kind: 'test'`: `test_gate_label_inventory.py` drives the real gate over the real `.github/labels.yml` inside the `Python package tests` lane, with the live list injected, plus controls that drop a real label and add an undeclared one. The **live** GitHub read is the one part that lane cannot do (it holds no label-read token); run `npm run
check:ci-label-inventory` locally for that.

**The PR label guide** is a single sticky comment posted by the `label-guide` job, rendered from `.github/labels.yml` so it cannot become a second, rotting
copy. It is identified by the HTML marker `<!-- rediacc:label-guide -->` and is
idempotent in the strong sense: the job creates when absent, updates when the rendered body differs, and performs **zero API writes** when it is byte-identical -- otherwise a PR would collect one guide per push. Only a comment authored by a BOT counts as the guide, so an outsider cannot suppress it by posting a fake one. A marker comment from a human is ignored, not rewritten.

**`guide: false` separates declaring from listing.** All 26 labels must be declared (the inventory gate reconciles the whole file), but only 12 are listed on the PR: GitHub's stock defaults, bot-applied labels, and the three with zero consumers in code carry `guide: false`. The guide exists because the roster got too long to remember, so padding it with `duplicate` and `good first
issue` would recreate the problem it solves. **Absent means true**, so a new label is visible unless someone opts it out -- failing toward showing a label, because one that quietly vanishes from the guide is invisible while one that appears needlessly is a row too many. A present value must be exactly `true` or `false`; anything else is a loud parse failure rather than a coerced
truthy string, since coercion flips visibility in the direction nobody notices. The visible set carries its own anti-vacuity floor, separate from the declaration floor: a parser change that mis-read the field would otherwise leave the declaration count satisfied while the rendered table came out empty.

Three labels are declared as **historical only** and worth knowing about, because their own descriptions used to claim otherwise: `release` does not trigger CD (`finalize-release-sentinel` dispatches unconditionally and reads no label), `description-current` is not read by the PR-description gate (which uses `lastEditedAt`), and `codex` has no consumer at all. They stay declared
rather than deleted because deleting a label strips it from the history of every PR that carries it. A label's description is not evidence of its behaviour; the `check:ci-label-refs` sweep is.

The job is separate from `initialize` for one reason worth remembering: it needs `pull-requests: write`, and no other job in `ci.yml` holds that. `initialize` carries a 20-step surface (checkout, a five-repo app token, GHCR login, the scope engine), and widening its grant to buy one comment is the wrong trade. Its result is soft-required in `assert-ci-complete.sh` as `LABEL_GUIDE`
-- it legitimately skips on non-PR events, but a genuine failure still reddens `CI Complete`, which is what you want: the commenter throwing means `.github/labels.yml` stopped parsing, and that same file feeds the inventory gate.

### Draft-until-green and the merge hooks

Console PRs are opened as **drafts** (`gh pr create --draft`) and stay draft until CI is green; submodule PRs (renet/account/elite, private repos on the GitHub free plan) are opened plain because private drafts are not free. Three pre-command hooks enforce the flow: `block-nondraft-pr-create` (the draft/plain split at creation time), `block-premature-ready` (`gh pr ready` is
allowed only when the required `CI Complete` check is SUCCESS on the PR's current head; `--undo` is always allowed), and `block-admin-merge` (`gh pr merge --admin` is banned outright). The sanctioned merge is `gh pr merge --rebase --auto`, which GitHub completes once required checks are green. `allow_squash_merge` is `false` on all five repos, so `--squash` fails outright; ask with
`gh api repos/rediacc/<r> --jq .allow_squash_merge` rather than trusting this sentence.

### Review Complete: the PR review is a required check

`Review Complete` is a required check beside `CI Complete` (operator ruling 2026-10-03, agent/plans/PLAN-github-pr-review-restore.md Design 6). `claude-review.yml` runs the whole-PR Claude review after Console CI, and `review-status.yml` posts the `Review Complete` check-run on the head, its title starting with one fixed token:

| Token | Conclusion | Meaning |
|---|---|---|
| `current` | success | the head is reviewed |
| `capped` | success (warning) | the PR spent its review cap; the head's marker is stale and hygiene is clean |
| `exhausted` | success (warning) | the head's infra-class review attempts hit their ceiling; hygiene is clean |
| `outage` | success (warning) | the LLM was unavailable for the head's last attempt (`api_error_429/500/502/503/504/529`, recorded by `claude_review_gate --mark`) |
| `draft` | neutral | the PR is a draft |
| `stale` | failure | the head is not reviewed yet |
| `failed-run` | failure | the head is unreviewed and the review run concluded `failure` or `timed_out` for a reason other than an outage; the summary starts "investigate and fix:" |
| `hygiene` | failure | reviewed, and a hygiene script failed: an unanswered summary or an open finding thread |

**The outage is the only excused failure.** A `failed-run` is a defect in the review run to investigate and fix, then re-dispatch with `gh workflow run claude-review.yml -f pr_number=<n>`; a `hygiene` is answered with `python3 .claude/hooks/stop/wl_prreview.py` (`--draft`, then `--answer` before the fix is pushed, because a push over an unanswered summary fails `Review Gate`). A timeout of `wl_prreview.py --wait` is never a pass, and nothing merges on it. A summary answered with a deferral ("deferred to worklist item #<id>") is not an answer: `review_comments` reads it as the `deferred` verdict and fails `Review Gate`. `Review Complete` blocks the CI verdict in `wl_ci` and `ci_diagnose`; `Review Status` and `Claude Review` report through it and never block on their own, and all three stay out of the watchdog and the timing lists, since the review observes a Console CI run rather than belonging to it. `/pr-merge` step 3 carries the wait, triage and answer sequence. The ruleset context is added by box GR12 once both workflows are on `main`, because a required context no workflow posts would wedge every PR; until then `gh api repos/rediacc/console/rules/branches/main` lists `CI Complete` alone, and the loop treats `Review Complete` as required regardless.

### Pointer-bump fast path

A push whose commits only move submodule gitlinks to tree-identical, on-submodule-`main` commits (the post-squash pointer bump), on top of a baseline commit that already has a successful `CI Complete`, is detected by `.ci/rediacc_ci/ci/detect_pointer_bump.py`, which sets `pointer_bump_only=true` in the `initialize` job. Under that flag `ci.yml` skips `build-renet` (and everything
cascading from it: the other builds, tests, install-matrix, preview) plus `stripe-sandbox`, `package-tests`, and `ops-tests` (`tests` carries `Migration Test`, which skips itself under the flag); only `quality`, `review-gate`, and `ci-complete` still run. `assert-ci-complete.sh` accepts those skipped builds as green **only** under this flag, so the aggregated `CI Complete` still
goes green, in minutes. This is why `/pr-merge` now WAITS for the fast-path run to go green and merges with `--rebase --auto`, instead of admin-merging over a pending run (which used to leave the merged PR with a permanent red `Quality / Branch`, a wall of cancelled jobs, and no `CI Complete`). A pointer-bump-only delta is also deliberately not re-reviewed by Claude.

### Dispatching a workflow on a branch (`--ref`), and the one half nobody has proven

Console's workflow graph is already branch-aware where it can be: all 18 job-level workflow calls in `.github/workflows/` use the local `./` form, and GitHub documents that form as resolving to the caller's own commit — *"When you reference a reusable workflow in the same repository using `./` (without `{owner}/{repo}` and `@{ref}`), the called workflow is from the same commit as
the caller workflow."* (*Reuse workflows*). A PR's `ci.yml` closure therefore runs the PR's own YAML. What forces merge-first is never the ref: it is `workflow_run` and `pull_request_target` reading the default branch **by design** (they hold secrets while a PR's code is in play), the `console@main` pin the PR-level review workflow put on its scripts until its retirement on 2026-10-02 (it closed
run `30317293249`, where a PR reviewed itself with its own review logic), `ci.yml:193-199` refusing a non-`main` rehearsal dispatch, and any external caller registered in `.github/external-callers.yml`.

**Acceptance is decided from the default branch. This half is settled.** GitHub: *"This event will only trigger a workflow run if the workflow file exists on the default branch."* (*Events that trigger workflows*). Two live consequences, both already paid for here:

- Adding a `workflow_dispatch:` trigger costs **one** merge, once per workflow — never one per
change. Until it lands on `main`, `gh workflow run <file> -f …` fails closed with a 422, *"Workflow does not have 'workflow_dispatch' trigger"*. Observed on PR #546, run `30588087212` (the PR-level review workflow, retired 2026-10-02).
- The same resolution applies to the FILENAME, so a brand-new workflow cannot be dispatched
from any ref at all: `.ci/rediacc_ci/ci/dispatch_watchdog.py` fails open on exactly that bootstrap condition, observed as an HTTP 404 on both the head-ref and default-branch attempts in run `29936730679`.

**Which copy then EXECUTES is the dispatched ref's, and one rule explains every trigger.** This is not stated in one sentence anywhere, which is why two places in this tree used to disagree about it (the PR-level review workflow, retired 2026-10-02, said the default branch's copy defines the job; `agent/PLAN-branch-aware-workflows.md` said the ref's). It is the conjunction of two pages, both re-verified
2026-09-02:

> "Each workflow run will use the version of the workflow that is present in the associated
> commit SHA or Git ref of the event." — *Workflows (concepts)*

and the per-event table in *Events that trigger workflows*, which gives `workflow_dispatch` a `GITHUB_REF` of *"Branch or tag that received dispatch"* and a `GITHUB_SHA` of *"Last commit on the `GITHUB_REF` branch or tag"*. So the dispatched branch's YAML runs.

**The same rule is why `workflow_run` and `pull_request_target` read the default branch** — their table rows give both a `GITHUB_REF` of *"Default branch"* and a `GITHUB_SHA` of *"Last commit on default branch"*. That is not a separate mechanism to memorise; it is the identical "version at the event's ref" rule applied to an event whose ref IS the default branch, which is the
security property those two triggers exist to have.

Practical consequence: **acceptance and execution resolve against different refs, and only for `workflow_dispatch`.** Landing the trigger on `main` is a one-time cost; after that `--ref <branch>` genuinely tests the branch's copy.


### Never push to `main` or cut a release unasked

**`main` moves through the PR merge, and a merge releases edge through CD.** Operator ruling 2026-10-02 (agent/plans/PLAN-plan-per-pr-loop.md): `/pr-merge` and `/pr-babysit` are AI-invokable, and the loop merges a PR with `gh pr merge <n> --rebase --auto` once every box of its plan is ticked, `CI Complete` is SUCCESS on the head (`ci-trace.py`) and `wl_review.py --check` exits 0.
Every merge to `main` runs the release pipeline (`cd-v2.yml` deploys edge on green), and Console CI's `pr-labels` job decides the bump once at the green head; `bump-none` is never applied by hand.

**Edge and bench are free; stable is asked** (operator ruling ASKED 2026-10-27T09:45Z, agent/plans/PLAN-local-release.md). An agent may release edge with `npm run release:local -- --channel edge` (or `--workers-only`), as a faster path beside CD, and may deploy bench. Every stable deploy (eu, us, asia) is CI/CD only and needs the operator's request in the task. `block_unasked_release` (pre-bash) admits a stable target only when the command carries `RELEASE_ASKED=ASKED:<YYYY-MM-DDTHH:MM>Z` and that minute matches an AskUserQuestion answer in the transcript within 300 s:

```
RELEASE_ASKED=ASKED:2026-10-27T09:45Z <stable deploy command>
```

`--dry-run` always passes. The guard refuses the raw publish verbs from agent Bash: `wrangler deploy` and `wrangler rollback`, `gh release create`, a `git push` of a `v*` tag, `docker` or `buildx` with `--push`, `-m rediacc_ci.deploy.*`, and `-m` on the release publishers (`create_github_release`, `tag_submodules`, `update_homebrew_tap`, `mark_production`). Agent writes under `.ci/cache/release/` are refused too. A manual CD re-dispatch still needs the operator's request in the task.

Per *Session Defaults* rule 1, verified work is committed as it lands on the one `MMDD-N` branch and reaches `main` only through its PR. The single direct push an agent may make is the fast-forward fallback for a PR GitHub cannot rebase (see *Commit policy*, "main and the live branch"). Every other push to `main` is refused: `block_push_to_protected_branch` refuses it from an agent's Bash, and the git-level `pre-push` hook refuses it everywhere else unless `COMMIT_POLICY_OK=1` is set.

**One documented agent-initiated commit on `main`, and only one:** a MAIN-ONLY failure during a `/pr-merge` run, after that command has already merged. The fix is committed on `main` as a `[hotfix]`, and its push is not the fallback shape, so the operator pushes it with `!`. See step 5 of `.claude/commands/pr-merge.md` for the full rule and the classification test.

The reason is instrument validity, not urgency: the PR was green, so a failure that appears only after the merge lives in a path PR CI structurally cannot run (`refs/heads/main`-gated jobs, the dispatch-only Release workflow, or Docker, which PRs only dry-run). **A fresh PR would go green without exercising the fix at all** -- it is the wrong instrument, so its verdict is
worthless. The verification loop is the next `main` run.

Classify first: if the failing job RAN AND PASSED on the PR, it is transient, not main-only -- do not fix it, the watchdog auto-retries. Only a job the PR could never have run earns the `[hotfix]`. It does not extend to re-cutting a release, and it does not apply outside that command's own release path.

### Commit policy

Operator ruling 2026-09-25 (the commit-policy plan under agent/plans): verified work is committed as it lands, on one branch with one PR, and the tags a commit may carry are few. The rules live once in `.claude/rediacc_hooks/commit_policy.py`, with their data in `.ci/config/commit-policy.json`, and are enforced twice.

**The pre-bash layer**, authoritative for agents, refuses before anything runs:

| Guard | Refuses |
|---|---|
| `block_second_branch` | a second live branch in any repo: `checkout -b/-B`, `switch -c/-C`, `branch <new>`, `branch -c`, `worktree add -b`, `push <remote> <src>:<new>`, `push -u <remote> <new>`, `gh pr create --head <other>`, a `git/refs` POST. A new local branch is admitted only from `main` with no live branch left, under today's next `MMDD-N`; in a submodule, only the console's current branch name. A rename and every read or delete form pass. `gh` failing while a creation is judged is a refusal. |
| `block_second_open_pr` | `gh pr create` while this account already has an open PR in that repo. |
| `block_commit_on_main` | a commit on `main` that is not a well-formed `[hotfix]`, and `[hotfix]` on any other branch. |
| `block_ci_skip_token` | a CI skip token anywhere in a commit message (subject, body, `-F` file, heredoc, `--trailer`). |
| `block_no_review_ineligible` | `[no-review]` on a commit that is not purely writing, and on any `[hotfix]`. |
| `block_git_hook_bypass` | `commit --no-verify` / `-n`, `push --no-verify`, the same flag on `merge`/`am`/`rebase`/`cherry-pick`, `-c core.hooksPath=`, `--config-env core.hooksPath=`, `git config core.hooksPath <x>` (and its unset forms), `GIT_CONFIG_*` config by environment, and `COMMIT_POLICY_OK=1` set by an agent. Reads such as `git config --get core.hooksPath` pass. |

**`main` and the live branch** (operator ruling 2026-10-02, PLAN-plan-per-pr-loop boxes M2, M3 and M6). `main` moves by `gh pr merge <n> --rebase --auto`. When GitHub refuses with "This branch can't be rebased", `block_push_to_protected_branch` admits exactly one direct push, `git push origin <live branch>:main` (or `origin/<live branch>`, a `refs/` spelling, or the sha; never `HEAD`), and only when every condition reads true:

- one `git push` to `origin` with one refspec and no flag but `-q`/`-v`: no `--force`, `--force-with-lease`, `+`, `--delete`, `--tags`, `--follow-tags`, `--all` or `--mirror`;
- the checkout is the console's own, on its `MMDD-N` branch, and the commit is exactly `origin/<live branch>` with `origin/main` as its ancestor;
- that commit is the head of the open PR for the branch, and `CI Complete` is SUCCESS on it, read through `.ci/scripts/ci/ci-trace.py --json --ref <live branch>`;
- the PR body carries an `Operational-Reason:` line, or its `Plan:` line names a plan whose boxes are all ticked at that commit; with `turbo: on` in `agent/plans/QUEUE.md` `## Settings` at that same commit, the line may name several plans and every one of them, with every unfinished prerequisite, must be ticked (`plan_gate.plan_merge_refusal`, agent/plans/PLAN-stop-hook-turbo.md D6).

Anything unreadable is a refusal. The git-level `pre-push` hook admits the same push without the override: one ref equal to `origin/<live branch>`, with `main` as its ancestor. `block_git_force_push` admits `--force-with-lease` only to the single live `MMDD-N` branch, never `main` and never `--force`, `-f` or a `+refspec`. After a merge, once the merged branch is deleted on the remote and pruned locally, `block_second_branch` admits the next `MMDD-(MAX+1)` cut from `main`. GitHub's rulesets back the same shape server-side: 24351140 (deletion, non-fast-forward, linear history, no bypass) and 12344707 (rebase-only pull request, required `CI Complete`).

**The git-level layer** is the backstop for what never reaches a pre-bash hook: the operator's terminal, `!` commands, and subprocesses. `./run.sh setup` installs it (the `git-hooks-path` phase in `.ci/rediacc_ci/setup/githooks.py`) by pointing `core.hooksPath` at `.claude/rediacc_hooks/git/`, as local config, in the console and every checked-out submodule; `/tmp` fixtures and CI checkouts are untouched. `commit-msg` checks tags and skip tokens, `reference-transaction` refuses a branch creation that breaks the one-branch rule from local facts only (no `gh`), and `pre-push` refuses a push to `main` and a push creating a remote branch other than the current one. `COMMIT_POLICY_OK=1` in the environment is the operator's override and makes every one of these hooks exit 0; the pre-bash guards never honour it.

**Release-run admission.** `release:local` (edge) writes a git-layer record, `.ci/cache/release/run-<id>.json`, and exports `REDIACC_RELEASE_RUN`. The `pre-push` hook (`.claude/rediacc_hooks/git/release_run.py`) admits a pushed line, a version tag or a tap formula commit, only when the record's pid is in the hook's parent chain with a matching start time and a command line of `-m rediacc_ci.release.local`, the record's tree equals `HEAD^{tree}`, and that exact `(toplevel, remote_ref, oid)` is listed. A forged record, a wrong tree or an unlisted ref is refused, and `block_git_hook_bypass` refuses `REDIACC_RELEASE_RUN` set by an agent.

**`pre-commit` refuses a commit that leaves a generated doc region stale.** It runs `scripts/gen/gen-docs.ts --affected` from the commit's own index (plain `node`, about 0.15 s, no provider runs), which names every staged path that one of the generator's modules, a document carrying a region, or a provider's declared `inputs` (`scripts/lib/doc-providers.ts`) could move. No hit is the fast path. A hit checks out the commit's index in full (`checkout-index`, 0.7 s parallel) and runs verify there, about 9 s in all, so a partial `git commit -F <msg> -- <paths>` that leaves its regeneration unstaged is refused, not judged by the working tree. The refusal names the staged inputs, the drifted files and the fix: `npx tsx scripts/gen/gen-docs.ts --write`, then commit the regenerated files with the inputs. A staged generator module also re-runs `--check-inputs` (about 25 s), the trace that proves every provider reads only what its `inputs` declare; `--selftest` runs the same trace in CI. A missing `node`, a timeout or a generator that cannot run is refused as UNCHECKED. A committed generator with no `--affected` mode is skipped with a notice. There is no escape hatch beyond `COMMIT_POLICY_OK=1`. Tests: `.claude/rediacc_hooks/tests/test_githook_gen_docs.py`, where every case also runs against a copy planted to always allow and must fail there.

**`pre-commit` also refuses a commit that leaves a generated artifact stale.** `.ci/config/generated-artifacts.json` is the registry: for each generated-and-committed artifact, the globs it is generated from, the command that regenerates it, the gate that judges it, and whether a commit is checked against it. The hook reads the registry from the commit's own index and lists the paths the commit changes; a commit that changes no input of an enrolled artifact costs two git calls and prints nothing.
A commit that does is checked out in full into a scratch tree (the commit's index, never the working tree), the untracked build products the entry declares are linked in, and the entry's checker runs there under its time budget. A stale artifact is refused with the staged inputs, the checker's own words, the generator command and the output paths to add. A checker that exits with anything else, a missing build product and a run past the budget are refused as UNCHECKED. `.claude/rediacc_hooks/git/artifacts.py` is the code.

<!-- >>> gen-docs: generated-artifacts -->

Scans: .ci/config/generated-artifacts.json, one row per generated-and-committed artifact.

| Artifact | Outputs | Regenerate with | Checked |
|---|---|---|---|
| CLI contract (`cli-contract`) | `packages/shared/src/cli-contract/data/**` | `npm run generate:cli-contract -w @rediacc/cli` | at the commit, 90 s budget; then `check:ci-cli-contract` |
| Plan queue and plan index (`plan-renders`) | `agent/plans/QUEUE.md`, `agent/INDEX.md` | `npm run check:ci-plan-record -- --rendered-only --update` | at the commit, 45 s budget; then `check:ci-plan-record` |
| Gate registration lock (`gates-lock`) | `scripts/ci-runner/gates.lock.json` | `npm run gen:gates-lock` | at the commit, 45 s budget; then `check:ci-gates-lock` |
| Generated doc regions (`doc-regions`) | `scripts/data/doc-registry.md`, `CLAUDE.md`, `docs/agent-reference/*.md` | `npx tsx scripts/gen/gen-docs.ts --write` | at the commit, by the gen-docs check; then `check:ci-doc-region-parity` |
| CLI command tree (`command-tree`) | `packages/cli/scripts/command-tree.json` | `npm run export:command-tree -w @rediacc/cli` | before the push, by `check:ci-command-tree` |
| Plan box ledger (`plan-boxes`) | `.ci/config/plan-boxes.json` | `npm run check:ci-plan-boxes -- --update` | before the push, by `check:ci-plan-boxes` |
| Translation hash manifests (`i18n-hashes`) | `packages/www/src/i18n/translations/.translation-hashes.json`, `packages/cli/src/i18n/locales/.translation-hashes.json` | `npm run i18n:generate-hashes` | before the push, by `check:ci-i18n-hashes` |
| Derived locale files (`i18n-locales`) | `packages/www/src/i18n/translations/*.json` | `npm run i18n:sync` | before the push, by `check:ci-i18n-completeness` |
| Shard manifests (`shard-manifests`) | `.ci/config/shards/*.json` | `npm run shard:place` | before the push, by `check:ci-shard-manifest-coverage` |
| Python environment registry (`python-env-registry`) | `.ci/config/python-env-registry.json` | `.ci/scripts/quality/check_python_env_registry.py --write-baseline` | before the push, by `check:ci-python-env-registry` |
| Hook inventory and coverage baselines (`hook-inventory`) | `scripts/data/hook-inventory-baseline.json`, `scripts/data/hook-coverage-baseline.json` | `hand-edited: drain the one line the gate names` | before the push, by `check:ci-hook-integrity` |
| Workflow steps bound from gate headers (`gate-bind`) | `.github/workflows/ci-quality.yml` | `npm run gate:bind` | before the push, by `check:ci-gate-bind` |

12 row(s). Generated by `npx tsx scripts/gen/gen-docs.ts --write`; do not hand-edit.

<!-- <<< gen-docs -->

An artifact is left to the pre-push run when its check is too slow for a commit, not deterministic, or a hand-reviewed baseline whose regeneration is a decision; the registry carries that reason beside the entry, and `commit.blind` says what an enrolled check cannot see. The CLI contract check, for one, runs without building the workspace packages, so `check:ci-cli-contract` stays the verdict before a push. `check:ci-generated-artifacts` refuses a registry entry whose glob matches no tracked file, whose generator or gate does not exist, or whose control cannot plant.
`.claude/rediacc_hooks/tests/test_githook_generated_artifacts.py` commits each enrolled entry's declared control through the real hook: refused with the generator named, allowed once regenerated, and no checker run for an unrelated path, each case also required to fail against a hook planted to always allow.

**The committed plan renders are judged as committed.** The worklist verbs re-render `agent/plans/QUEUE.md` and `agent/INDEX.md` in the working tree, and `check:ci-plan-record` read only the working tree, so a render that was never committed stayed green locally and went red in CI (PR 600, run 38381096702). The gate now repeats R8, RQ and RQ-SETTINGS on HEAD's bytes (rule RC) on every full run, and `--rendered-only` runs those three rules alone, in about 3 s, which is the commit-time check of the `plan-renders` entry; `npm run check:ci-plan-record -- --rendered-only --update` regenerates both files.

**The tags.** A tag is a bracketed word in the SUBJECT line.

- **`[hotfix]`**, on `main` only and required there. It sits at the end of the subject, and the message carries a `Hotfix-Evidence:` trailer: the red `main` run (a bare run id or an `actions/runs` URL) when the fix is the main-only failure class of `/pr-merge` step 5, or `ASKED:<YYYY-MM-DDTHH:MMZ>` when the operator called it a hotfix in this task. At most `hotfix_max_files` (5) paths. No `PR-TASK:` trailer, since `main` has no epic. Always reviewed, never `[no-review]`. Pushed by the operator with `!`, since the fast-forward fallback never covers a commit made on `main`.
- **`[no-review]`**, on writing only. Every path must match `no_review_eligible` (`agent/**`, `docs/**`, `**/*.md`) and none `no_review_denied` (`.claude/**`, which holds agent programs, and `CLAUDE.md`, which is policy). The tag only narrows: an eligible commit left untagged is reviewed anyway. The per-commit reviewer re-checks eligibility before writing a `skipped (no-review)` verdict.

**CI skip tokens are refused, and there is no `[no-ci]`.** GitHub skips the workflow for a head commit carrying `[skip ci]`, `[ci skip]`, `[no ci]`, `[skip actions]`, `[actions skip]` or a `skip-checks: true` trailer, and a skipped workflow leaves its required checks pending: the ruleset requires `CI Complete`, so the PR sits at "Expected" until something else is pushed. On `main` a skip also skips the release, which is exactly why the two CD bot commits use one; they run as subprocesses in CI and never reach either layer. A custom `[no-ci]` was rejected rather than built: it would need a second skip path in `initialize` beside the attested scope-engine skip-plan and the pointer-bump fast path, which already make cheap commits cheap; CI runs per push, not per commit, so committing often costs nothing once pushes are batched; and the `ci:quick` receipt is required before any push anyway. `[no-ci]` is refused too, so nobody believes it does something.

**Pushing is separate from committing.** A push is a backup and a CI trigger, never one per commit: at an epic milestone, at least every 2 hours of committed work, and before a stop that leaves unpushed commits. Each push needs its `ci:quick` receipt (`block_unverified_push`; `--receipt-out` from a clean clone when the tree is shared).

**A push touching the VM trigger paths also needs a VERIFIED `vm:check` receipt.** `block_vm_unverified_push` (pre-bash, ORDER 62, the last guard) diffs the pushed range through `.ci/rediacc_ci/proof/surfaces.py` over the surface map `.ci/config/proof-tiers.json`, which sorts every hit into a renet side (the deployed renet code, the CLI remote paths) or an account side (the `private/account` served code, the account drill files), and admits it only when `.ci/cache/vm-check/` holds a schema 2 VERIFIED receipt for the pushed tree or its trigger inputs with a matching unmodified renet build, in which every touched side's phase ran (`phase-missing` otherwise), plus, on the account side, a checkout equal to the pointer and unmodified (`account-mismatch`, `modified-account`); a range whose push base cannot be resolved charges both sides. `npm run vm:check -- --changed` writes one. Each ledger line records the sides and the `private/account` gitlink. The operator escape is `VM_CHECK_PUSH_REASON` with an `ASKED:` minute, logged to `agent/ledgers/vm-check-push-reasons.jsonl`; `.claude/agents/ops-vms.md` carries the verdicts and classes.

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

- **CI workflows** (`ci.yml`, `ci-quality.yml`, `ct-tests.yml`): Use **generated throwaway keys** via `rediacc_ci.infra.ci_env`. Never pass production secrets.
- **Release workflows** (`cd-v2.yml`, `promote-stable.yml`) and the local entry (`release:local`, through `bws_env exec --profile release-local`): Use **real production credentials**, pulled from
**Bitwarden** (the workflows by `./.github/actions/bws-secrets`), not from GitHub's org secret store. That store is unused: `gh api orgs/rediacc/actions/secrets` returns `{"total_count":0,"secrets":[]}`. The only repository secrets are `BWS_ACCESS_TOKEN`, which unlocks Bitwarden, and `BREAKPOINT_TUNNEL_TOKEN`. Corrected 2026-09-06; the previous wording sent readers to an empty store and made a
live pipeline look broken.
- Generated secrets are masked via `::add-mask::` in `rediacc_ci.infra.ci_env`.
