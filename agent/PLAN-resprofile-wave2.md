# Resource profiling, wave 2: make the layer true, then make it readable
Status: approved
Owner: 74de73ca (2026-09-03)

The operator ruled 2026-09-03: the whole cluster as ONE
change; it rides the open PR #585 on branch `0903-1`; the gate stays UNSEEDED
and report-only. Those three answers close the packaging questions -- do not
re-ask them, and do not quietly descope a piece into a follow-up. Four Plan agents
(fable) ran the four angles separately; this is the synthesis. Every claim below
marked **[V]** I re-verified myself after the agents reported, because the
operator's instruction was to verify any claim that a binary or measurement
exists before proposing on it.

## The finding that reframes the wave

`docs/ci-overhaul/06-progress.md:6645` says "Every Bash and Python invocation now
leaves a record." **That sentence is false today**, in three independent ways:

- **[V] Plain `python3` leaves nothing.** `wl_core.py:952-955` is the only site
  that arms the exit recorder, so coverage is "processes that import wl_core",
  not "every python3". Measured: 3x `python3 -c pass`, `exit.jsonl` delta **0**.
- **[V] The devbox records no bash at all.** `bash_env.sh:30-32` probes two paths
  for `bashcov-sup`; inside the running devbox `/usr/local/bin/bashcov-sup` does
  not exist. The Dockerfile builds it, the running image predates that line --
  the same "pinned but absent" shape as `bws`. The env file skips silently, so
  nothing reports the hole.
- **[V] The bash half is write-only.** `grep -rln 'bash\.jsonl'` over the tree
  returns exactly ONE file: `bash_env.sh`, the writer. No reader anywhere.
  `wl_profile.rank()` reads `exit.jsonl` and CI capture dirs only.

So the layer measures less than it claims, and half of what it does measure
cannot be attributed to anything (bash records carry pid/rusage/wchan but no
script identity). Wave 2 is about making the sentence true and the corpus
readable -- not about adding predicates.

## Corpus, measured today [V]

`~/.claude/resprofile/home-developer-console/<today>` = **223 MB, 17,300 files**
after one day. `wl_resprofile.py:310` claims one day is 32 MB / 2,363 files --
**7x low**, because CI capture folders (one per gate per run) dominate. At
`RAW_RETENTION_DAYS = 14` steady state is ~3 GB and ~230k inodes.

## The instrument: keep it, close its holes

Angle 1 surveyed the alternatives and every one is unavailable or adds nothing
**[V]**: `perf` and `bpftrace` absent on host AND devbox with
`perf_event_paranoid=2`, `unprivileged_bpf_disabled=2`, `CapEff=0`; cgroup v2 is
`ro` in the devbox and the host's scope is shared with all of WSL init, so both
give ambient attribution, never per-command; `btm` is present (`/usr/bin/btm`,
hash-pinned in the Dockerfile) but is a TUI with no batch/JSON mode; psutil is
absent from both, the host python has no `pip` at all, and it reads the same
`/proc` files anyway. So: **keep `wait4` + `getrusage` + the forkless `/proc`
sampler.** Nothing else measures more here.

## One signal the layer reports DEAD and is not [V]

`wl_resprofile.py:217-220` emits `avail.run_delay = false` from
`kernel.sched_schedstats=0`. Measured: an idle process reads `run_delay=0`, but
two burners pinned to one core read **`run=747ms run_delay=752ms`** while a third
alone on its own core reads `run_delay=0`. Field 2 of `/proc/<pid>/schedstat` is
live regardless of the sysctl. This matters because run-delay is the
counter-signal that stops a "parallelise this" recommendation on an already
oversubscribed box -- the layer currently throws it away.

Note for whoever checks this: an idle read shows 0 and looks like a refutation.
The measurement only means anything under contention.

## The plan (one change, six pieces)

1. **`sitecustomize.py` on `PYTHONPATH`, delivered by `bash_env.sh`.** The one
   seam proven to arrive carries the second. New dir `.claude/hooks/profile/py/`
   holding only `sitecustomize.py`; it imports `os,sys,time,resource,atexit`
   only (the full `wl_resprofile` import costs +33 ms at interpreter start,
   measured by angle 1 -- unacceptable on every python3), re-exports the distro
   `apport_python_hook` it shadows, refuses a repo root of `/`, and sets a marker
   so `wl_core`'s arming becomes a no-op and nothing double-records.
2. **Make absence loud.** Build `bashcov-sup` in `devbox-autostart.sh` where the
   devbox actually looks, and make the gate treat "zero bash records from this
   scope today" as UNJUDGEABLE rather than clean -- the same anti-vacuity rule it
   already applies to captures.
3. **Give bash records a shape.** `BASHCOV_SHAPE` = repo-relative `$0`, or
   `sh:-c`; never `BASH_EXECUTION_STRING`. The supervisor copies it into the
   record. Then `rank()` folds `bash.jsonl` and 35 MB/day stops being ballast.
   Extend the planted-secret control to the bash record.
4. **Fix the signals that lie.** `avail.run_delay` becomes a probe, not a sysctl
   read; `r_fraction` reads per-thread states (the leader thread is `futex` for
   59/62 ticks on go and 66/82 on biome, so every multi-threaded tool currently
   reads as idle); `rank()`'s "blocked share" is 0% by construction because it
   reads the supervisor's own wchan -- retire it.
5. **The stall discriminator**, which the operator named as the reject condition:
   a window is STALLED only if, for every tick, the live pid set is unchanged AND
   tree CPU (incl. `cutime/cstime`) is unchanged AND no thread anywhere is R or D
   AND no frontier node's read-pipe has a live writer in the tree. Measured over
   the six largest real captures: **0 stalls**, tree CPU rising monotonically in
   all six -- so it does not fire on the healthy `$( )` captures that cost two
   killed battery runs.
6. **Fix the retirement trigger so it can fire.** Today it is evaluated AFTER the
   pristine return, so an unseeded gate never reaches it; every `--seed` resets
   the sunset; and it greps prose rather than a trailer. Replace with: evaluated
   before the pristine return, a `Resprofile: <key>` trailer that must name a
   real shape and touch a file outside the layer, two such commits in 30 days or
   the layer is removed.

## What I would leave OUT, and why

- **Seeding the gate.** Angle 3 measured today's corpus at run granularity: E4
  fires in 3/55 runs and E6 in 5/55, both far above the 5% bound, and all eight
  are non-defects (E4 is git's own `index.lock`; E6 is tsx/node zombies under a
  script with no spawn calls). Seeding now enshrines one red per ~10 runs.
- **Enforcement in CI at all.** No workflow runs the ci-runner, so
  `quality-branch` has no captures; seeded, the gate would red every CI run
  forever. Enforcement belongs on the local runner where the evidence is made.
- **E3/E7/E8 as enforcing predicates.** Report-only until the frontier walk has a
  corpus behind it.
- **A dashboard, a daily RANK.md regeneration, worklist items per finding.** Each
  is a second write path dressed as a read path.

## Retirement trigger (measurable, in advance)

Evaluate 2026-10-03 and every 30 days: fewer than **2** commits carrying a
`Resprofile:` trailer naming a real shape and touching a file outside the
layer => retire; OR both top-1 rows (by CPU and by idle wall) unchanged and
neither down 20% => the ranking drove no work => retire. Cost guard, separate:
`du` over the root above 3 GB or 250k files => prune captures at 7 days.
