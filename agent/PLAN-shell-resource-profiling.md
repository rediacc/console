# PLAN: a resource-profiling layer for background shells

Status: LANDED 2026-09-03, live on this machine, all gates green (`ci:quick` 292/292 with profiling on by default). Baseline NOT yet seeded -- seed after a few days of real runs.

## Operator rulings, 2026-09-03

1. **Bash coverage cannot be dropped** -- "we have too many bash scripts, we cannot
   discard them." Section 0's finding stands as a FACT about BASH_ENV, not as a reason
   to go Python-only. A separate investigation (fable model) is testing mechanisms
   that survive trap replacement, `exec` and dash: shadowing the `trap` builtin with a
   function in the BASH_ENV file, the DEBUG/RETURN trap slots, kernel BSD process
   accounting (`acct(2)`, one record per process exit regardless of shell), and an
   LD_PRELOAD shim. Section 5's first bullet is therefore WITHDRAWN pending that result.
2. **Scope is collector + rollup + controls + the gate.** "We are here for long-term."
   Section 5's last bullet (no gate in change one) is WITHDRAWN. The baseline-seeding
   hazard it named is real and is handled instead by the pristine-bootstrap rule
   (section 4: while the baseline is pristine the gate warns and exits 0; seeded means
   enforced).
3. **The verdict lives in a sibling `wl_profile.py`**, suppressed, never blocking. Accepted
   as recommended.
4. **E3 (blocked sleep holding nothing) is pulled back IN as report-only.** The other
   exclusions stand. The operator also asked for more candidate findings; a second
   angle is producing them under the dilation-invariance and silence-predicate rules.
Synthesised 2026-09-03 from four Plan angles (instrument / signals / enforcement /
long-term shape). Every load-bearing claim below was re-verified by hand after the
agents reported; the verifications are named inline.

## 0. The finding that reshapes the brief

**The Bash injection point does not hold, and it fails hardest on the highest-value
target.** Verified live on this host, all three:

```
BASH_ENV trap, plain command      -> fires        (control)
BASH_ENV trap, script sets its own EXIT trap -> DOES NOT FIRE
BASH_ENV trap, `exec` in the command         -> DOES NOT FIRE
```

Bash has ONE `EXIT` trap slot, not a chain, so a later `trap ... EXIT` silently
replaces ours. And `.claude/hooks/stop/test-worklist-v5.sh:60` is literally
`trap 'rm -rf "$(dirname "$BASE")"' EXIT`. The suite named in the brief as the
richest source (~880 python3 invocations) would therefore have emitted **zero**
Bash-side records, while looking instrumented. `/bin/sh` is also `dash`, which
does not read `BASH_ENV` at all.

This is not a detail to work around. It is the reason change one is **Python-only**.

## 1. The instrument

**Primary: `/proc` deltas + `resource.getrusage`, pure stdlib, no dependency.**
The two are complementary and neither is sufficient alone:

* peak memory for CHILDREN exists only in `ru_maxrss` (and it is a MAX over
  children, not a sum, in KiB on Linux);
* disk bytes exist only in `/proc/<pid>/io` -- `ru_inblock`/`ru_oublock` measured
  **0 after 50 MB of I/O**, because page-cache reads never reach the block layer.

Measured overhead: python startup 23.0 ms -> 23.2 ms with the recorder attached
(~0.9%, ~180 ms across a whole suite run).

**Ruled out, each for a verified reason:**

| candidate | verdict |
|---|---|
| `btm` | present at /usr/bin/btm on host AND devbox, hash-pinned in the Dockerfile -- and it has **no non-interactive mode at all**. TUI only. Presence is not fitness. |
| `perf` | absent, and `kernel.perf_event_paranoid=2` -- unprivileged gets user-space only. |
| `bpftrace` | absent, and `kernel.unprivileged_bpf_disabled=2` -- unprivileged BPF fully off. `CapEff=0`. The sysctls are the blocker, not the packages. |
| `psutil` | reads the SAME /proc files -- no new measurement. No pip on the host, PEP 668 `EXTERNALLY-MANAGED`, and `/etc/rediacc/toolchain.env` does not exist on the host, so a container-installed psutil would be invisible to the python3 that actually runs the hooks. |
| per-command cgroups | `/proc/self/cgroup` is `0::/init.scope` -- one cgroup for the whole box. `/sys/fs/cgroup` is not writable and `CapEff=0`. Would need `sudo` per command. |

**Correction to the brief's premise, verified:** the Dockerfile's precedent for
PYTHON deps is `pip install --no-cache-dir --break-system-packages` with the version
pinned in `/etc/rediacc/toolchain.env` (`.devcontainer/Dockerfile:309,311`), NOT the
hash-pinned curl archive. That form is for release BINARIES (btm, bws, shfmt).

## 1b. Host vs devbox -- verified after the angles reported

The four angles probed the HOST. The devbox differs in two ways that matter, both
checked by hand inside `rediacc-devbox-94-console`:

* **`wchan` is symbolic in both.** A sleeping `sleep` inside the devbox reads
  `hrtimer_nanosleep` (`kptr_restrict=1`, `/proc/kallsyms` readable). An earlier read of
  `0` was a RUNNING process, which is what `0` means. The frontier walk in section 2
  holds in both environments.
* **The devbox root cgroup is the container's own**, `0::/`, and its root files are
  readable: `cpu.stat`, `memory.current`, `memory.peak` (5.76 GB at probe time),
  `io.stat`, `cpu.pressure`, `memory.pressure`. It is NOT writable and child cgroups
  cannot be created, so per-command attribution stays impossible -- but ambient
  attribution inside the box is per-WORKTREE-CONTAINER rather than per-machine, which
  is a materially better denominator than the host's shared `init.scope`. Record the
  cgroup root deltas as `scope: container` inside the devbox and `scope: machine` on
  the host; never let the two be compared as if they were the same thing.
* Toolchain: devbox bash 5.2.21 (`$EPOCHREALTIME` available), python 3.12.3 vs host
  3.14, `/bin/sh` is dash in both. `/proc/sys/kernel/acct` exists in the devbox with
  the default tunables `4 2 30`, and `CapEff` there is non-zero -- whether that reaches
  `CAP_SYS_PACCT` is the Bash-coverage angle's question, not settled here.

**Code seams for the sibling verdict, all confirmed by hand:** `scripts/ci-runner/exec.ts:65`
is the single spawn parent of every gate (`spawn('bash', ['-c', spec.run])`);
`wl_checks.py:1663` `outq_add` is the report channel and `:2141` the
`contextlib.suppress(Exception)` containment precedent; `worklist.py:124-166` `_MODS` is
the sibling-import probe that names a broken module instead of crashing; the judge is
gated at `wl_checks.py:5352,5379` on `(something_remains or reg_signals)`, confirming it
never runs on a clean board. And `.ci/scripts/quality/check-tracked-sidecars.sh:41`
really does PARSE the parenthesised suffix list out of `wl_store.py`'s docstring, so the
rollup's suffix MUST be added there or a resource file can be committed unnoticed.

## 1c. Bash coverage, resolved -- verified by hand after the fable angle reported

**Primary: F, a `wait4` supervisor the BASH_ENV file re-execs the shell under.** The
BASH_ENV file, before the script or `-c` string runs, `exec`s `bashcov-sup -- bash <same
flags> <same invocation>` with a recursion guard. The supervisor forwards signals,
samples the child's `wchan`/`VmHWM` at 250 ms, `wait4`s, writes ONE record (exit or
signal, wall, tree utime/stime, tree `ru_maxrss`, ctx switches, a wchan histogram) and
exits with the child's status. Because the record is written by a PARENT the script's
trap slot cannot touch, it survives everything section 0 found: a script's own EXIT
trap, `exec`, `set -o posix`, `builtin trap`, `unset -f trap`, even `kill -9`.

**Proven on the real target.** `bash .claude/hooks/stop/test-worklist-v5.sh` under F:
`passed=889 failed=0`, exit 0, **152 records** where the naive design produced zero, and
the suite's own record -- written AFTER line 60's `rm -rf` trap had run -- answers the
"blocked on what" requirement for a 9-minute run: 2,268 wchan samples, 69%
`anon_pipe_read` (reading `$( )` output from `worklist.py` children), 30% `do_wait`,
346 s CPU across the tree, tree peak RSS 179,888 kB. I re-ran F under `exec true` by
hand: 1 record.

**Fallback: A, shadow the `trap` builtin with a function** -- pure bash, no binary.
Verified by hand: a script owning its EXIT trap still runs it, `rc=3` propagates, and a
record lands. It loses `exec` (verified: 0 records), mid-script posix, `builtin`/`command
trap`, `kill -9`, and child peak RSS. Repo exposure to those gaps is small and
enumerated: 0 uses of `builtin trap`/`command trap`/`set -o posix`, ~20 `exec` sites,
2 `#!/bin/sh` scripts, 649 bash-shebang scripts.

**Optional backstop: D, kernel BSD accounting (`acct(2)`)** -- the only thing that sees
dash, static binaries and SIGKILL. Works here via `sudo -n`; the devbox would need
`--cap-add SYS_PACCT` and an `acct()` call in the entrypoint before `setpriv`. Coarse
(10 ms quantum, average not peak memory, no wchan). Not in change one.

**Costs, measured (3 x 200 `bash -c true`):** baseline 2.1-2.4 ms; A2 +1.4-1.7 ms; F2
+3.5-3.8 ms; empty BASH_ENV +0.15 ms. **The cost that needs a decision:** every Bash
tool call runs ~50 `bash <hook>.sh` processes from `.claude/settings.json`; if the env
block hands them BASH_ENV too, F adds ~175 ms and 50 records per tool call (A ~80 ms).
The env file can skip `$0` under `.claude/hooks/` or record them -- which is arguably
the point of the exercise, and the fork-multiplicity report (3b candidate 5) wants
exactly that data.

**What F costs to adopt:** a C supervisor (`sup.c`, 3.6 KB) shipped hash-pinned in
`.devcontainer/Dockerfile` like btm, AND present on the host (gcc 15.2 is on the host
today; the devbox has build-essential). Plus a `settings.json` `env` block naming an
ABSOLUTE `BASH_ENV` path (the docs are silent on variable expansion there, so
`$CLAUDE_PROJECT_DIR` cannot be assumed; a machine-specific path belongs in
`settings.local.json`). Still unverified, and stated: the live tool with `env.BASH_ENV`
set (only emulated, pipe and pty), and whether the env block reaches hook subprocesses.

**Bug found in both A and F and fixed:** the exit status of the last BASH_ENV command
leaked into an empty script's status (`false; return 0` -> `bash -s </dev/null` rc=1);
every path now ends in `:`.

**Verified live 2026-09-03, after landing:** the settings `env` block delivers `BASH_ENV`
to the Bash tool shell (read back inside a tool call), but a `PATH` set in the same
block did NOT arrive -- so `bash_env.sh` finds the supervisor by explicit path
(`~/.local/share/rediacc/bin/bashcov-sup`, then `/usr/local/bin/`), never via PATH.
`.claude/settings.local.json` is TRACKED in this repo, so the machine-absolute
`BASH_ENV` lives in user-scope `~/.claude/settings.json` instead. With that in place
`bash.jsonl` reached 584 records within minutes: every tool call and every hook.

**Operator ruling on storage (supersedes section 4's "tier 0 never persists"):** keep
the statistics in a TIME-BASED folder so what to optimise can be decided from ranked
results. Layout: `~/.claude/resprofile/<repo-slug>/<YYYY-MM-DD>/{exit.jsonl, bash.jsonl,
<run-id>/*.jsonl}`; `.ci/cache/profiles.{current,prev}` are pointer files to the last
two runs' capture folders; `wl_profile.py --rank <root>` writes `RANK.md`, shapes by
total CPU then gates by tree CPU with blocked share and findings per row.

**And the CI-gate side needs none of this.** `scripts/ci-runner/exec.ts:65` is the
single parent of every gate, so the tree SAMPLER (`wl_ressample.py`) attaches there,
outside the gate, with no trap slot to lose -- landed, opt-in via `CI_PROFILE_DIR`.

## 2. The signals, and the ones that lie

**Verified structurally dead on this box -- recording them as numbers would
manufacture findings:**

```
kernel.sched_schedstats = 0   -> /proc/<pid>/schedstat field 2 (run_delay) reads 0 forever
kernel.task_delayacct   = 0   -> /proc/<pid>/stat field 42 reads 0 forever
cpu.max = "max"               -> nr_throttled / throttled_usec are 0 by construction
```

So **runqueue wait, the textbook contention signal, is unavailable here.** The live
instrument is **PSI**: `/proc/pressure/{cpu,io,memory}` exists and is world-readable
(`some avg10=... total=...`). Each dead signal is emitted as `{available:false}`,
never as a value -- an instrument that reports the absence of what it cannot see is
the same defect class as the `pressureDetected` bug already in this tree.

**The stalled-vs-healthy discriminator, which the brief made the acceptance test.**
Two parts, both reproduced live:

1. **wchan values partition.** `do_wait` and `anon_pipe_read` are DEFERRING -- "I am
   waiting on something inside my own subtree" -- and carry no verdict; they mean
   RECURSE. Only a TERMINAL wchan at the frontier renders a verdict.
2. **The liveness signal is `cutime`/`cstime`, not the live-child count.** Measured on
   a parent doing nothing but `$( )` captures: identical state, identical wchan, self
   CPU flat at zero, and `cutime` moved 1.60 s between samples. `cutime` accumulates
   only when a child is REAPED -- exactly the between-cases moments a snapshot misses.

Define `TreeCPU = sum over {root} + live descendants of (utime+stime+cutime+cstime)`.
A healthy `$( )` capture has flat SELF CPU and climbing TREE CPU. That is the whole
answer to `test-hooks.sh:2328`, and it is why my own two killed battery runs today
were a misdiagnosis rather than a hang.

**The repo-specific trap no generic design would survive:** the worklist cases plant
IMMORTAL fixture sleepers (`10-event-store.sh:316` sleeps 987654321099 seconds). A
classifier reading "a descendant has been in `hrtimer_nanosleep` for nine minutes" as
a stall fires on every clean run. Frontier walks must exclude planted sleepers by
`cmdline`.

## 3. Enforcement

**DILATION INVARIANCE, as a testable property rather than a habit:** a predicate may
be enforced only if its verdict is unchanged when every duration field is multiplied
by k>0. The 4-vs-9-minute suite is k=2.25 on one recording. Two controls enforce it:
feed each deriver `P` and `dilate(P, 2.3)` and require byte-identical findings; and
statically refuse any comparison of a `*_ms` field against a numeric literal.

**THE SILENCE PREDICATE, the onboarding lesson made computable:** for finding class C,
with `J` = invocations the deriver could actually judge, C may enforce only while
`F(C)/J <= 0.05`; above that the CODE demotes it to report-only and says so. The
denominator is judgeable invocations, not all invocations, or a broken sampler makes
every rate look excellent.

**The verdict does NOT go in the judge**, for two verified reasons:
* `wl_checks.py:5379` gates the judge on `(something_remains or reg_signals)` -- a
  session that ran the battery, got green and has a clean board **never reaches it**,
  which is precisely the shape a resource verdict is about.
* The judge fails CLOSED by contract (`worklist.py:91-94`). This signal must never
  block a stop: the judge gates an exit so "cannot decide" must not be an escape;
  the profiler describes how work was done, so "we did not measure" must never become
  "you may not stop."

So: a sibling `wl_profile.py`, imported through the existing `_MODS` probe, called
inside `contextlib.suppress(Exception)`, no subprocess, no network, off switch
`WORKLIST_PROFILE=off` (the `WORKLIST_*` prefix is covered free by the suite's
ambient scrub).

**The one flagship finding, with the false positive that would embarrass it:**
E1 SEQUENTIAL INDEPENDENT FANOUT -- N>=8 children, pairwise-disjoint lifetimes, each
CPU-saturated, and **positively disjoint write domains**. The embarrassment is the
worklist suite itself: strictly sequential, CPU-saturated children, ~690 spawn sites
-- and `_harness.sh:50` is `rm -rf "$BASE"` against ONE shared fixture root, so
parallelising it would have cases deleting each other. Verified. The control is that
a recorded profile of the real suite must produce NO finding and must name the shared
write domain as the reason -- not an allowlist entry.

**Measurement REFUTES independence; it never PROPOSES it.** A sampled fd table is a
LOWER bound on the write set, and for a predicate whose safety depends on absence of
a shared write, a lower bound is the wrong direction.

## 3b. Corrections and additions from the brainstorm angle -- all cited lines verified by hand

**C1 -- `dilate()` scales WALL, not CPU, and that breaks E1 as first worded.** Machine
load is what produced the 4-vs-9-minute swing on identical code; load stretches wall
time and leaves CPU time nearly fixed. So the honest dilation operator multiplies
timestamps and PSI totals and leaves `cpu_user`/`cpu_sys` alone -- and under it E1's
"each child CPU-saturated" leg, if read as `cpu/wall`, drops from 0.95 to 0.42 at
k=2.25. **Not invariant.** The invariant substitute is already recorded: on Linux the
`R` state covers running AND runnable-but-preempted, so
`saturated(p) = hist_R / (hist_R + hist_S + hist_D) >= 0.9` is a ratio of counts,
unchanged by any k. Every predicate uses R-fraction; none uses `cpu/wall`. The D1
control (P vs dilate(P, 2.3) byte-identical) would have caught this on first run, which
is the point of having it, but it is cheaper to fix the design than the first run.

**C2 -- interval overlap is dilation-invariant** (`a<d and c<b` survives any k>0), which is
what legalises every concurrency finding below. E1 already leaned on the dual.

**C3 -- three cheap gaps in the record:** a `Z` bucket in the state histogram (one
bucket); a run id on every record so cross-invocation joins exist (one string); and a
note that `/proc/locks` rows carry `dev:inode` only, resolvable solely by intersecting
with a sampled fd table -- say so or the rows are decoration.

**C4 -- the silence predicate needs a denominator floor.** `F(C)/J <= 0.05` flips on one
event when J=8. A class may not enforce until `J >= 20` AND the one-sided 95% binomial
upper bound on F/J is <= 0.05. Below that it is report-only "for lack of denominator",
which is a different and more honest reason than "too noisy".

**Three findings added to change one, chosen because they fail DIFFERENTLY** (a set
relation between two trees, a ratio within one tree, a count at one instant), so the
dilation control catches a framework mistake where three variants of "used a lot of X"
would not:

* **E4 UNDECLARED CONCURRENT WRITER -- ENFORCE.** Two invocations with overlapping root
  lifetimes under one run id whose writable-fd path sets (under the repo root, minus
  any observed mktemp root) INTERSECT, with no declared exclusion (`mutex` in
  `scripts/ci-runner/manifest.ts`, or W membership in `.ci/scripts/test/run-all.sh:111`).
  It requires POSITIVE evidence of a shared write and never certifies disjointness --
  Rule 3 exactly. Why it exists: `.ci/scripts/quality/check-pool-writer-safety.sh` is a
  static taint scanner whose own header (`:32-44`) records the precision it dropped
  and whose one-directional rule (`:46-49`) says "under-declaring manufactures a
  flake"; its structural blind spot is a write performed by a CHILD program it does not
  parse (`docs/agent-reference/TRAPS.md:1020-1029`). An fd table observes the write
  instead of inferring it. **It retires a standing `Enforced-By: JUDGMENT-ONLY` trap**
  (`TRAPS.md:995-997`, residue "a comment claiming isolation is not evidence of it").
  Control: SILENT on a real `npm run ci` recording with the three declared writers
  running, naming the declared exclusion that covered each overlap; FIRES by
  re-planting the 2026-08-17 defect through the existing `RUN_ALL_WRITERS=""` seam
  (`run-all.sh:66,153-157`, already used as a control in
  `test-run-all-parallel.sh:204-211`), which must name `resolve-version.sh`. Needs
  gate-side coverage -- the `exec.ts:65` spawn is the walker's root.
* **E5 INTRA-SHAPE MEMORY OUTLIER -- REPORT-ONLY until J>=20 (the shellcheck predicate,
  done right).** Among >=5 same-`comm` siblings under one parent, fire when
  `max(peakRSS)/median(peakRSS) >= 8` across >=2 recordings of one shape. NOT "fraction
  of MemTotal": 2714 MB is 41% of the 6.6 GB box that died
  (`.ci/scripts/security/shellcheck.sh:103-106`) and 4.7% of the 58 GB box this was
  written on -- a MemTotal threshold gives the same profile two verdicts, which is not
  portable across `scope: machine` and `scope: container`. The sibling-relative form
  reproduces the incident's real structure: `xargs -n 40 -P1` (`shellcheck.sh:117`)
  made ~12 same-comm siblings and ONE batch cost 27x its peers. The `comm`-equality
  restriction is load-bearing (a `tsc` beside twenty `sh` helpers must not fire). J is
  tiny for this class today, which is exactly what C4 is for.
* **E6 ZOMBIE ACCUMULATION UNDER A NON-REAPING PARENT -- ENFORCE.** >=3 distinct pids in
  state Z sharing a live parent at one sample, non-decreasing across >=2 consecutive
  samples. A count at an instant: dilation-invariant by construction. It is a
  CORRECTNESS smell (an unreaped child is a `wait` that never ran, an exit code nobody
  read -- the `check-swallowed-failures` family), and this tree has already met it:
  `.ci/scripts/test/gates/test-breakpoint-teardown.sh:42-45` documents `kill -0`
  succeeding on a zombie. The consecutive-sample rule is what separates "transient
  before `wait`" from "never reaped". Control: SILENT on a recording of
  `run-all.sh` at `RUN_ALL_JOBS=4`, whose scheduler is `wait -n`; FIRES on a fixture
  parent that backgrounds 5 children and blocks on `read`.

**Considered and dropped, with the corpus reason:** D-state + rising majflt (fixture
re-reads from disk) -- `/tmp` is tmpfs (28.4 GB, verified with `df -T`), every fixture
is under `mktemp -d`, so `majflt` is zero by construction and the class has an empty
true-positive set here; a finding that cannot fire is unfalsifiable. Poll-loop by
context switches -- fails Rule 1 under either dilation reading, and Rule 2 outright:
`wl_wait.py` and `ci-trace.py --wait` are the sanctioned long-lived waiters. Fork depth
-- a fact, not a finding (Claude -> guard -> jq is 2; under `npm run` it is 5-6 and that
is what `npm run` costs). Write amplification -- report-only, and it settles the IO
question: `rchar`/`wchar` count syscall bytes regardless of the page cache and are the
only IO signal that survives it; the recorder already carries all four io fields.

**Two manifest observations found in passing, not resource findings:**
`manifest.ts:1250` flags `check:ci-hook-worklist-suite` as `heavy` "because it is
minutes, not seconds" -- a DURATION reason on a MEMORY field (`heavy` is documented as
>=4 GB heap at `:45`), which is the drift candidate 2 (undeclared memory-heavy gate,
change two) would detect; and `mutex: ['www-dist']` has exactly one member, so it
excludes nothing -- the real protection is the `needs: ['build:www']` edges.

## 4. Long-term shape

**Two tiers, and only the second persists.** Tier 0 is an ephemeral per-run JSONL that
is folded and truncated at exit. Tier 1 is a per-shape rollup mirroring the shape of
`.ci/cache/gate-durations.json` (verified present: 365 entries, `ewma` + `recent`
keys) -- `ewma` for the estimate, `recent[5]` as a FLOOR oracle, because this repo
already learned that one overlapping run pushed a 4.5 s gate's ewma to 21 s.

The calibration sentence: **one battery run of per-invocation records (~360 KB) is
larger than the entire worklist event log (416,478 bytes), which took three days to
accumulate every session's whole item history.** That single comparison is why the
per-invocation corpus does not persist.

**The shape key never contains command text.** `<lang>:<repo-relative-script-path>[#<verb>]`,
where every component already exists as a public string in a public tree. A hash of
argv is rejected outright: a templated command whose only variable part is a token of
known format is brute-forceable, and a hash of secret-bearing text carries the secret.

**Baseline: inherit the COMPOSITION rule, reject the shrink-only ratchet.** A defect
count has a floor of zero and a monotone-desirable direction; a resource number has
neither, and ratcheting CPU downward fails on a slower runner. What transfers is that
the SET of shapes is shrink-only and a per-shape allowance may not be raised silently.

**The kill trigger, fixed in advance and script-checkable:** the rollup carries a
`read_at` stamp written by whatever consumes it. If `read_at` is absent or older than
7 days, or 30 days pass with no commit citing a profile finding, the gate FAILS with a
message naming the remedy as `git rm`. Precedent for the failure mode is in this very
hook directory: `wl_admit.py:596-600` records a ledger that "nothing read, which made
it a write-only file."

## 4b. Measured after the recorder landed -- the volume arithmetic was off by 17x, in the safe direction

A full battery with the recorder armed: PASS=1999 FAIL=0 (up from 1973: the 16 recorder
controls plus wiring), worklist suite 889/0, CLI stdout/stderr byte-identical on vs
off. The live tier-0 file grew by **175 lines / 54,645 bytes**, not the ~3,000 records
section 4 assumed. The reason is correct isolation, not a missing recorder: the case
suite runs every `worklist.py` with `TMPDIR` under its own `mktemp` root, so
`store_paths()` resolves the store INSIDE the fixture and `_harness.sh:50`'s `rm -rf`
takes the records with it. The suite's own profile is therefore invisible to the live
store by construction -- which is right (fixture noise must not pollute the corpus) and
means the suite must be profiled by the SAMPLER rooted at its pid, not by exit
records. Two shapes carry no script: `py:-c` (51) and `py:-` (28) are inline and stdin
python -- mostly this session's own heredocs. They leak nothing (no argv is ever read)
and are worth a `py:<inline>` bucket rather than a verdict.

## 5. What I would deliberately leave OUT of change one

* **All Bash coverage.** Section 0 is the reason. Not "later" -- the hole is
  structural, and a half-instrumented Bash side that misses the suite is worse than an
  honest absence because it looks like data.
* **The `settings.json` `env` block.** Not needed at all if the seam is a single
  `atexit` in `wl_core`, which 15 hook modules already import. Zero settings change,
  zero new hook registration, and the whole ~880-invocation population covered.
* **IO counters.** `ru_inblock`/`ru_oublock` measured 0; `read_bytes` is 0 for cached
  reads. Ship `cpu` and `maxrss` -- the two this repo has actually been burned by
  (shellcheck at 2714 MB peak, OOM-killing the shell gate and surfacing as a bare
  "Killed" naming neither memory nor the tool).
* **E3 (blocked sleep holding nothing).** It needs per-process socket attribution to
  distinguish waste from a legitimate backoff against a remote service. No socket
  attribution exists in this tree. Ships report-only with its promotion trigger stated.
* **The repeated-spawn finding.** ~880 python3 invocations is the suite's isolation
  model, not waste: the process boundary IS the fixture. The remediation it would
  demand is the one change the suite must not take.
* **Any gate in change one.** Collector + rollup + selftest, accumulate real numbers,
  then seed the baseline from them. Seeding from one machine's first run is how a bad
  number gets enshrined.


## Landed 2026-09-03 -- and the two ways the profiler measured itself

Everything above is in the tree and running: exit recorder (`wl_resprofile.py`, armed
from `wl_core`), tree sampler (`wl_ressample.py`, attached per gate by `exec.ts` at
500 ms, on by default, `CI_PROFILE=off`), deriver (`wl_profile.py`: E1/E4/E5/E6, D1
wall-only dilation, D2 self-scan, Wilson admission, `--rank`), gate
(`check:ci-resprofile` + `gate-test:resprofile`, pristine bootstrap, kill trigger),
Stop-hook report channel, Bash via F (`bashcov-sup` built on host and in the image,
`bash_env.sh`, user-scope `env.BASH_ENV`), and the time-based corpus with `RANK.md`.
First profiled `ci:quick`: 292 captures, 227 judgeable, 0 findings after the E5 fix.

**Two self-measurement traps, both real, both caught by the battery or the gate:**

1. **The sampler's own fixture was supervised.** With `BASH_ENV` live, the bash tree the
   sampler selftest spawns was re-exec'd under `bashcov-sup`, every depth shifted by one,
   and three controls failed under the battery while passing standalone. Fixtures now
   run with `WORKLIST_PROFILE=off`, and -- the design consequence -- the deriver treats
   a single-child `bashcov-sup` root as transparent (`logical_root`), because under F
   EVERY gate capture has that shape and E1 could otherwise never count a fanout. A
   control plants a supervised fanout and requires E1 to fire.
2. **The gate profiled its own planted zombies.** `check:ci-resprofile` runs the deriver's
   selftest, which spawns an unreaping parent with four `true` zombies; the sampler
   attached to that gate caught it as a live E6 -- correct on a fixture, and it would
   have counted F=1 for E6 in any seed. Gates that plant defects carry `noProfile: true`
   in the manifest and `exec.ts` skips them; the run after showed 290 captures and 0
   findings.

Also paid for today: the 62 inline shadow-compare bodies I had generated tripped
`check:ci-workflows` (8-line cap, no baseline) -- extracted to
`.ci/scripts/ci/shadow-compare.sh` -- and my second-pass sweep corrupted 28 steps
(duplicated name item, dropped `run:`), caught only by a per-file steps-vs-calls
reconciliation; `test-resprofile.sh`'s mutant found a D1 control that checked only
`run.wall_ms` and not sample `t_ms`; and the "refuse a silent shrink" seed guard was
vacuous under accumulation and became an empty-seed refusal.

**Two more self-inflicted defects, both caught by looking rather than by a gate:**

* **A nested runner clobbered the pointer.** `gate-test:ci-runner` runs the runner as a
  gate, so the inner run rotated `.ci/cache/profiles.{current,prev}` and aimed them at
  its own two selftest captures -- a full 292-gate run left a pointer naming a folder
  with two files. Nested runs now inherit `CI_PROFILE_RUN` instead of rotating.
* **Profiling wrote INTO the repo tree.** That same selftest left `selftest_pass.jsonl`
  and `selftest_fail.jsonl` at the repo root, breaking the one storage rule the brief
  set. `exec.ts` now refuses a `profileDir` that is relative or resolves inside `cwd`:
  an unusable directory means no profile, never a file in the tree.

**Retention, from the measured number.** One day of real use is 32 MB / 2,363 files, so
an unbounded corpus is ~1 GB a month of data whose only consumer -- the rollup and
`RANK.md` -- has already read it. `fold()` prunes raw day folders older than
`RAW_RETENTION_DAYS = 14` and keeps the rollup forever; a control asserts an old folder
is pruned and today's is kept.

**The first ranking, on one day of real data** (`RANK.md`): `worklist.py` with no verb
is **52% of all Python CPU** -- 1,478 invocations, 357.6 CPU s, 796.7 s wall -- which is
the Stop hook itself, and is the first thing to look at. `#state` is another 15%. On the
gate side `check:test-shared` leads at 19,711 tree ticks with 212 MB peak and a 0%
blocked share, i.e. genuinely CPU-bound rather than waiting.

**Still to do, deliberately:** seed the baseline from real quiet runs after a few days
(`check_resprofile.py --seed <run-dir>`), never from one machine's first run; the
optional `acct(2)` backstop for dash/static/SIGKILL; E3 socket attribution.
