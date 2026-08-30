# PLAN: contention-aware fix for hardcoded pass/fail timeouts waiting on real infra
Status: done

## Implementation notes (2026-08-30, post-plan)

Implemented 5a, 5b, 5d as written. Skipped 5c (helper consolidation) per the
plan's own instruction that it is hygiene, not the fix, to do after landing
the numeric bumps as standalone value -- not blocking. 5e required no work
(verified `check_job_timeout_headroom.py` already covers item 3, deliberately
scoped, no job here near its ceiling).

- `ci-start-elite.sh`: `wait_for_web` timeout 60s -> 180s, load/core diagnostic
  added to the failure path.
- `ci-start-account.sh`: `wait_for_account_server` timeout 120s -> 180s, same
  diagnostic added.
- `wait-for-vm-ssh.sh`: per-VM budget 30x5s=150s -> 36x5s=180s, docstring and
  error message numbers kept in sync, same diagnostic added (this script runs
  on the runner host directly, not inside a container).
- `check_tutorial_healthcheck_headroom.py`: widened scope via a new
  `EXTRA_PATHS` list (not a glob widening, since the target is a single named
  file, not a pattern) to also cover `.ci/docker/ci/docker-compose.yml`.
  `private/elite/docker-compose.yml` deliberately excluded (submodule,
  ownership boundary, noted in the module docstring).
- `.ci/docker/ci/docker-compose.yml`: account-server healthcheck
  `start_period` 10s -> 150s (budget 70s -> 210s, clears the 180s floor).

Verified: `bash -n` on all 3 shell scripts, `check:ci-shell-lint` (535 files,
clean), `check:ci-python-lint` (69 files, clean), the healthcheck gate's own
`--selftest` (3/3 controls pass) and real run (`4 healthcheck(s) in 4 compose
file(s)`, up from 3, all now clearing the floor, exit 0), YAML syntax on the
edited compose file, and `check:ci-git-op-conditionals` /
`check:ci-baseline-key-semantics` unaffected (both still green, confirming no
collateral damage from this pass).
Owner: e580532b
Updated: 2026-08-28

## 0. What this plan is answering

A stop-hook judge asked for a repo-wide sweep for siblings of the bug fixed in
`packages/www/scripts/test-tutorial-player-release-gate.js` this session: a fixed
wall-clock timeout that GATES A PASS/FAIL VERDICT (reject/exit-1/step-failure)
waiting on real wall-clock work (booting a server, a container, a VM, a deploy),
sized by someone watching a fast/idle machine, that fires as a FALSE FAILURE on
this repo's shared devboxes/CI runners under contention.

The judge's literal grep (`setTimeout.*[0-9]{3,}|sleep [0-9]|timeout.*[0-9]{2,}`
over `.ci/scripts`, `packages`, `.github/workflows`) returns **505-506 matches**.
Verified by re-running it. The overwhelming majority are retry backoffs,
animation/UI delays, unrelated timing constants, and fixed-attempt loops that
degrade gracefully instead of failing — not this bug class.

After reading every real candidate file (not just grepping), the count of things
that genuinely belong to this class and are worth fixing is **3**, plus 2 related
structural findings (one dead-code duplication, one existing-gate scope gap).
Below is the full breakdown: what's real, what's a false positive and why, and
what to do about the real ones.

## 1. Genuine candidates (the same class as the tutorial-player fix)

### 1a. `.ci/scripts/infra/ci-start-elite.sh:75-91` — `wait_for_web`, timeout=60s

```
75  wait_for_web() {
76      local timeout=60
77      local elapsed=0
78      local interval=2
...
89      echo "  Web failed to start within ${timeout}s"
90      return 1
91  }
```
Failure path at `93-99`: `wait_for_web || { ... exit 1; }` (line 98 is the `exit 1`).

Runs inside the `Elite Run` job (`.github/workflows/ci.yml:974` name, `:983
timeout-minutes: 14`), called at `.github/workflows/ci.yml:1021`. Images are
pre-pulled in a *separate, earlier* step (`ci-pull-images.sh`, `ci.yml:1004`), so
this 60s window is pure container-startup + nginx-health time, not pull time —
and the job has 14 minutes of total budget, most of it unused by this one wait.

The container's own Docker healthcheck it's polling
(`private/elite/docker-compose.yml:57-62`, a submodule file but checked out in
this tree) is `start_period: 10s` + `interval: 10s` × `retries: 6` = **70s**
before Docker itself would call it unhealthy — already tighter than this repo's
own evidence-based floor for "how long a slow/contended host needs" (see §2).
60s doesn't even cover the container's own internal healthcheck budget.

**Evidence quality: no direct git-history proof this has fired** (repo history
is shallow — 166 commits — and `git log` on this file shows one squashed-import
commit). This is a preventive fix by analogy to the 180s floor established twice
elsewhere in this exact repo (§2), not a "measured 84s vs 60s" incident like the
tutorial-player gate. Say so honestly in the fix; don't claim more than is known.

### 1b. `.ci/scripts/infra/ci-start-account.sh:94-120` — `wait_for_account_server`, timeout=120s

```
94  wait_for_account_server() {
95      local timeout=120
...
117     echo "  Account server failed to become healthy within ${timeout}s"
118     docker logs rediacc-account-server --tail 100 || true
119     return 1
120  }
```
Failure path at `122-126`, `exit 1` at line 125.

Runs inside the `Stripe Sandbox` job (`ci.yml:618` name, `:621 timeout-minutes:
30`), called at `ci.yml:674`. The compose healthcheck it polls
(`.ci/docker/ci/docker-compose.yml:52-57`, this file is IN the console repo, not
a submodule) is `start_period: 10s` + `interval: 10s` × `retries: 6` = 70s. 120s
has more margin than Elite's 60s but is still below the repo's own 180s floor.
Same evidence caveat as 1a: no proven past failure in this shallow history,
fix is preventive-by-analogy.

### 1c. `.ci/scripts/infra/wait-for-vm-ssh.sh:37-55` — per-VM SSH wait, 30×5s=150s

```
40      for i in $(seq 1 30); do
...
49          sleep 5
50      done
51      if [[ "$ready" != "true" ]]; then
52          log_error "VM $vm SSH not ready after 150s"
53          exit 1
```
Waits for a **nested-KVM VM to finish booting** (line 4-6 comment: "the guest is
still booting" after `ops up` returns) on a self-hosted/shared runner —
`runs-on: ubuntu-latest` per `.github/workflows/ct-tests.yml:1326`, inside the
`Concurrent Fork Isolation` job (`:1324` name, `:1329 timeout-minutes: 35`,
call site `:1439`). Default target list is two VMs, waited **sequentially**, so
worst case is 300s consumed by this step alone inside a 35-minute job — plenty
of job-level headroom, same as 1a/1b; the SCRIPT's own per-VM cap is what's tight.

**This is the strongest evidence-backed candidate of the three**, not because
this exact script has failed, but because **150s is the exact number this repo
has already documented, in writing, as insufficient** for a slow/downclocked
host to finish booting/becoming ready — see
`docs/ci-overhaul/06-progress.md:3894-3901`, about a *different* subsystem
(pgAdmin's Docker healthcheck during tutorial recording): "the configuration
observed to fail had a budget of exactly 150s." Nested VM boot under contention
and container boot under contention are the same physical phenomenon (CPU
scheduling pressure slowing down a cold-start), and this repo already has a
data point that 150s is not a safe number for it.

## 2. Institutional context: this repo already has TWO working gates for this exact bug class

This matters for the fix design — don't reinvent, extend what already exists
and works.

**`.ci/scripts/quality/check_job_timeout_headroom.py`** (wired as
`check:ci-timeout-headroom`, `package.json:142`) exists because, per its own
docstring (`check_job_timeout_headroom.py:4-19`), `Validate Promotion` hit
`timeout-minutes: 30` on 2026-08-07 and again on 2026-07-28, cascading into a
missed release with no message anywhere containing the word "timeout" (a
timed-out job's conclusion is `cancelled`, which `assert-ci-complete.sh`
doesn't forgive). It requires `MIN_HEADROOM = 1.5`× (`:53`) between a
committed, evidence-based `observed_max_seconds` baseline
(`.ci/scripts/quality/job-timeout-baseline.json`) and each job's declared
`timeout-minutes`, refreshed manually from the Actions API. **This is item 3 of
the ask** ("check `timeout-minutes` on jobs with variable-cost work") — already
solved, by a purpose-built, control-tested gate. It currently tracks exactly 2
jobs (`Validate Promotion`, `Stage Artifacts`) — the two known to have actually
overrun — deliberately narrow (`job-timeout-baseline.json:10-42` explains the
scope reasoning: PR-run cost is roughly constant; only main-branch
promotion-style jobs whose cost scales with a growing channel are this class).
I found **no evidence** that `Elite Run` (14m), `Stripe Sandbox` (30m), or
`Concurrent Fork Isolation` (35m) are anywhere near their ceilings — their
inner wait-loop budgets (60-300s) are a small fraction of the job timeout, so
there's no new `timeout-minutes` candidate to add here. **Recommendation:
leave this gate as-is; do not expand it speculatively.**

**`.ci/scripts/quality/check_tutorial_healthcheck_headroom.py`** (wired as
`check:ci-tutorial-healthcheck-headroom`, `package.json:221`) is the closer
sibling. Its docstring (`:4-16`) describes almost exactly the tutorial-player
incident's shape: an 18-tutorial recording run aborted non-resumably at
tutorial 9 because pgAdmin's Docker healthcheck budget
(`start_period + interval*retries` = 150s) wasn't enough on a downclocked host
— "nothing was wrong with the tutorial... only a slow host disagreed." The
fix: `MIN_BUDGET_SECONDS = 180.0` (`:59`), enforced over every
`.ci/tutorials/apps/**/docker-compose.y*ml` (`:62`), with a `--selftest`
control that plants both a too-tight (the actual failing config) and a
generous healthcheck and requires the detector to flag exactly the tight one.

**The gap**: this gate's glob only covers tutorial-recording compose files. It
does **not** cover `.ci/docker/ci/docker-compose.yml` (the account-server
compose file candidate 1b wraps a wait loop around) or
`private/elite/docker-compose.yml` (candidate 1a's target). Both of those
files currently declare a 70s healthcheck budget — under the very floor
(180s) this repo already proved necessary in a live incident, in the same
repo, for the same reason (a container/service not becoming healthy fast
enough on a contended host).

**180s recurs twice in this codebase already** (the tutorial-player gate's
`180000` and this gate's `180.0`) as the evidence-based floor for "how long a
slow/contended host needs to finish booting something." That is the number to
anchor 1a/1b's fix to, not an arbitrary round number.

## 3. Related structural finding: duplicated, and dead, wait-loop code

`.ci/scripts/lib/common.sh` already defines a generic, reusable wait helper:

```
212 # Wait for a condition with timeout
213 # Usage: wait_for <timeout_seconds> <interval_seconds> <command...>
214 wait_for() {
...
232 # Run a command with a timeout (portable...)
235 run_with_timeout() {
```

**Verified via `grep -rn "wait_for \|run_with_timeout " --include='*.sh' .`
(excluding `common.sh` itself): zero call sites in the entire repo.** Both
functions are dead code. Meanwhile `ci-start-elite.sh` (1a) and
`ci-start-account.sh` (1b) each independently hand-roll the *identical*
`elapsed`/`while [[ $elapsed -lt $timeout ]]`/`sleep $interval` loop shape,
each with its own magic number (60, 120) and no shared floor or diagnostic.
This is exactly the "real duplication" item 4 asked about — a shared helper
already exists, is unused, and the two real candidates would have been one
change instead of two divergent ones if it had been used.

## 4. Explicitly ruled out (same surface shape, not this bug class) — read before assuming these are additional candidates

- **`.ci/scripts/deploy/wait-for-preview-worker.sh`** (`MAX_ATTEMPTS=60` ×
  `PROBE_INTERVAL_SECONDS=2` = 120s, `exit 1` at line 123). Same shape (fixed
  budget gates a verdict, waits on a real deploy), but its own extensive
  comments (`:37-97`) document THREE real incidents (commits `8b7840ed4`,
  `cefa43ca7`, runs `30968082228`/`30995469629`), and every one of them was
  Cloudflare D1/Worker propagation flakiness and probing the wrong
  endpoint/body — not local machine contention. Cloudflare's edge isn't this
  repo's shared devbox or runner; `os.loadavg()` on the runner would say
  nothing about D1 replication lag. Its existing fix (a `REQUIRED_STREAK`-of-3
  consecutive-success gate) already addresses its real failure mode. Adding a
  contention diagnostic here would be noise dressed as signal. Ruled out.
- **`.ci/scripts/ci/cancel-older-runs.sh`** (`TIMEOUT=60`, `:92-94`) and
  **`.ci/scripts/ci/scope-shadow.sh`** (`SCOPE_TIMEOUT=120` via `bounded()`,
  `:115-116`, `:427`) — both **fail open** on timeout: `exit 0` with a warning
  (`cancel-older-runs.sh:93`), or `return 0` and fall back to the safe/original
  scope decision (`scope-shadow.sh:421-424`). Exceeding the timeout does not
  produce a false CI failure here, it produces a graceful degradation. Not
  this class — and worth naming as the *correct* pattern for cases where
  failing open is safe (contrast with 1a-1c, where failing open isn't an
  option because the tests genuinely need the service up).
- **`packages/e2e-tests/playwright*.config.ts`** (7 files, `timeout:
  300000`-`2100000`ms) — `packages/e2e-tests/playwright.config.ts:43`:
  `timeout: process.env.CI ? 600000 : 300000`. This is the pattern already
  working correctly: contention-aware by construction (doubles the budget
  specifically because CI is assumed slower/busier than a local machine). A
  positive counter-example, not a candidate.
- **`.ci/scripts/test/run-account-e2e.sh:113-126`** (`LISTEN_TIMEOUT=30` for
  `stripe listen`) — on timeout it logs a warning and **skips** the Stripe
  tests (`:126`), it does not fail the job. Same fail-open pattern as above.
- **`.ci/scripts/env/create-e2e-env.sh:49`** (`BRIDGE_TIMEOUT` default
  120000ms) — this value is written to a `.env` consumed by the `renet`
  binary, which lives in the **`private/renet` submodule** (a separate git
  repository, `rediacc/renet`, with its own CI). The actual wait/gate loop is
  Go code there (e.g. `private/renet/pkg/daemon/start_foreground.go:226`), not
  a console-repo script. Flagged for awareness; out of scope for a plan whose
  deliverable is a console-repo PR.
- **`.ci/scripts/test/smoke-test-preview.ts:79-103`** (`HEALTH_ATTEMPTS=3` ×
  2s = 6s) — a tiny defensive re-check that only runs after
  `wait-for-preview-worker.sh` has already required a 3-probe consecutive
  streak. Already backstopped; too small a blast radius to be worth touching.
- **The remaining ~495 grep hits**: exponential retry backoffs
  (`common.sh`'s `retry_with_backoff`), `watchdog-monitor.cjs`'s `AI_TIMEOUT =
  25000` (an LLM-classifier call that falls back to a non-AI path rather than
  failing the job, `:683`, `:845`), UI/animation delays and debounce timers in
  `packages/www`, arbitrary fixture `sleep`s in unit tests that don't gate a
  verdict, and unrelated numeric constants the regex happened to match (cache
  TTLs, port numbers, version strings). None reject/exit gating a real-infra
  wait tied to shared-machine speed.

## 5. Concrete fix plan

Ordered by confidence/priority. All of 5a-5c are additive, low-risk console-repo
changes; none touch a submodule.

**5a. Bump the two script-level candidates to the repo's own evidenced floor,
add the same load-diagnostic pattern already proven in the tutorial-player fix.**
- `.ci/scripts/infra/ci-start-elite.sh:76` — raise `timeout=60` to `180`
  (matching `MIN_BUDGET_SECONDS` in `check_tutorial_healthcheck_headroom.py`
  and the tutorial-player gate's `180000`ms, not a fresh guess).
- `.ci/scripts/infra/ci-start-account.sh:95` — raise `timeout=120` to `180`
  for the same reason.
- On the failure path of each (`ci-start-elite.sh:93-99`,
  `ci-start-account.sh:122-126`), print a load-per-core reading
  (`nproc`/`/proc/loadavg` — bash-native, no Node dependency needed here
  unlike the www gate) alongside the elapsed time, so a red run's log states
  whether the runner was under load at failure time — the same "possibly
  contention, not necessarily a real regression" signal the tutorial-player
  fix added, adapted to bash.
- Do NOT claim a measured incident for either (unlike the tutorial-player
  fix's "measured 84s" comment) — say explicitly in the comment that this is a
  preventive alignment to the repo's own 180s floor, established elsewhere by
  two real incidents, not a repro on this exact script.

**5b. `.ci/scripts/infra/wait-for-vm-ssh.sh` — raise the per-VM budget.**
Raise from 30 attempts × 5s (150s) to at least 180s-equivalent (e.g. 36
attempts × 5s = 180s, or keep 5s spacing and go to 40 attempts = 200s for
headroom over the 150s number this repo already knows failed elsewhere).
Update the docstring's "30 attempts, 5s apart -> 150s per VM" line (`:19`) and
the `log_error`/exit message (`:52`) to match. Since this script runs ON the
runner host (not inside a container), a `loadavg`-style diagnostic on failure
is directly meaningful here too — recommend adding it.

**5c. Consolidate onto the existing (currently dead) shared helper instead of
three divergent hand-rolled loops.** Extend `wait_for()` in
`.ci/scripts/lib/common.sh:212-229` to optionally emit the same
load/elapsed-vs-budget diagnostic on failure, then migrate `ci-start-elite.sh`
and `ci-start-account.sh` (and, if practical, `wait-for-vm-ssh.sh`, which has a
slightly different per-attempt SSH-vs-generic-command shape) onto it. This
turns "three magic numbers, three copies of the loop" into "one helper, one
floor constant, three call sites" — the fix item 4 asked to consider when real
duplication exists. Do this AFTER 5a/5b land as standalone value, not as a
blocking prerequisite — the numeric bumps are the actual bug fix; the
consolidation is hygiene that prevents a fourth copy next time.

**5d. Widen `check_tutorial_healthcheck_headroom.py`'s scope rather than
inventing a new gate.** Change `APPS_GLOB`
(`.ci/scripts/quality/check_tutorial_healthcheck_headroom.py:62`) to also
match `.ci/docker/ci/docker-compose.yml` (in-repo, no submodule concerns), and
either raise its `start_period`/`retries` (`:52-57`) to clear the 180s floor,
or accept the gate's failure as the trigger to do so. This makes the *existing,
already-control-tested, already-registered* institutional gate cover the
account-server container that 1b waits on, instead of leaving that healthcheck
invisible to the one check purpose-built to catch exactly this. `private/elite/
docker-compose.yml`'s healthcheck (`:57-62`) is a submodule file — note it in
the same PR's description as a known-related gap to raise with the `elite`
repo's own owners, but do not fold it into this gate's glob (ownership
boundary; the console repo's gate has no business asserting on a file it
doesn't control the source of truth for).

**5e. Item 3 (workflow `timeout-minutes`): no new work.** Verified
`check_job_timeout_headroom.py` already exists, is control-tested, and is
deliberately scoped to the two jobs with a proven incident. No job touched by
this plan (`Elite Run`, `Stripe Sandbox`, `Concurrent Fork Isolation`) shows
any sign of approaching its ceiling — their internal wait budgets (60-300s)
are a small fraction of their 14/30/35-minute job timeouts. Do not add them to
`job-timeout-baseline.json` speculatively; that gate's own design doc
(`job-timeout-baseline.json:19-42`) is explicit that a baseline should be
evidence-refreshed from real runs, not hand-guessed.

## 6. What "done" looks like

- `ci-start-elite.sh` and `ci-start-account.sh` wait at least 180s (or route
  through a shared helper doing so) and print a contention signal on failure.
- `wait-for-vm-ssh.sh`'s per-VM budget is raised above the 150s this repo has
  already proven insufficient elsewhere, with the docstring/error message
  numbers kept in sync.
- `check_tutorial_healthcheck_headroom.py` (or a documented follow-up ticket,
  if the console-side compose healthcheck itself also needs raising) covers
  `.ci/docker/ci/docker-compose.yml`.
- The three fixes are NOT accompanied by a claim of "measured contention
  failure" the way the tutorial-player fix could honestly make — they are
  preventive, evidence-anchored-by-analogy fixes, and the PR/commit messages
  should say so plainly rather than overstating direct proof.
