# PLAN: a Stop-hook orphan background-shell sweep (notify-only, session-scoped)

Status: done -- all 6 boxes closed, commit 8bea7d09d/4faa8e500.
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

## Finding

The operator: "too many background shells in the background" accumulating over a very long session. Verified live on this machine (see "Live experiment evidence" below): this session's own harness process (`comm=claude`, pid 2531105) currently has **10 leftover `bash -B -c source .../shell-snapshots/...` processes** still alive as direct descendants, aged from 61.6 to 202.9 minutes -- none of them killed, several long past any reasonable "still needed" window. `wl_liveness.py` today only ages tasks the harness's own event payload (`live_bg`) currently lists, or the output-file mtime for those same declared tasks. Nothing walks the OS process tree independently to ask "is there a live shell under this session that nothing is currently bookkeeping?" That is the gap: a pure safety-net sweep, notify-only, that cannot ever be tricked (or trick itself) into looking at a different session's processes.

## What already exists (verified live, not just read)

- `wl_liveness.proc_table()` -- full `/proc`-derived `[(pid, ppid, cmdline)]`, ~11ms for 555 processes on this box (timed live, see evidence). `_proc_table_ps()` is the macOS/no-`/proc` fallback and currently captures only pid/ppid/cmdline -- **no start time**, which is a real gap for this feature (see Design 3).
- `wl_liveness.harness_ancestors(table)` -- walks UP from the hook's own pid, up to 8 hops, collecting the **whole ancestor set** (hook -> wrapper -> harness -> shell -> tmux/session-leader -> init). This is the right primitive for `verify_background`'s purpose (matching a *declared* task's command text against any ancestor-rooted child -- the needle text is the real safety net there) but, as shown live below, it is **not** the right anchor for an unfiltered descendant sweep: the ancestor set reaches shell/tmux/init nodes that can legitimately be shared with a sibling Claude session's process tree.
- `wl_liveness.verify_background` / `bg_output_facts` / `BG_STALE_MIN` (15 min default) -- scoped strictly to tasks `event_bg` currently lists; staleness is output-file mtime, not process age.
- The 45/90/120 ladder (`wl_liveness.ladder`) -- operates on worklist items and harness task ids, not raw OS pids, and is a "declare it stuck" instrument with blocking rungs that must be latched to avoid the `poll_fast_path` deadlock documented in the module (Control from 2026-07-30/31).
- No existing code anywhere under `.claude/hooks/stop/*.py` calls `os.kill`/`terminate()`/`SIGTERM`/`SIGKILL` against a *discovered* background process (verified by grep). The only `kill()`/`os.kill()` uses are the hooks' own subprocess bookkeeping (`wl_profile.py`, `wl_ressample.py`) or a signal-0 liveness probe. `worklist.py --reap <me> <task-id>...` is the one existing "retire a roster entry" verb, and it only ever removes bookkeeping -- it never touches an OS process. This is the natural analog for where a *future* (not this plan's) `--reap-pid`/kill verb would plug in.
- `wl_admit.py` and `wl_checks.py`'s `deferred_findings()` are the two precedents for "small, focused detector module wired into `wl_checks.py` as a keyed `vadd(key, always, text)` tuple, HYGIENE-tier unless argued upward" (see `.claude/hooks/stop/wl_checks.py:2721-2740` for the tier-admission rule: I1 compute-time budget, I2 someone-else-pays, I3 hook-integrity -- none of those hold for a leftover-shell notice, so it stays `always=False`, HYGIENE tier, rotated like `wl_deflect.py`'s sibling design in `agent/plans/PLAN-deflected-finding-check.md`).
- The TypeScript `process-ancestry.ts`/`ancestry-helper.ts` (packages/cli) is a **security** ancestor-walk (proves parent linkage + captures each ancestor's `environ` for an override-gate check), has zero notion of process age, and is a different runtime -- nothing to import, only a structural pattern to note (in-process `/proc` walk on Linux, a bundled Go binary shellout on macOS/Windows). This repo's Python hook needs, and `wl_liveness.py` already substantially has, its own ancestry primitive.

## Design

### 1. Where this lives: new module `wl_bgsweep.py`, beside `wl_liveness.py`

Justification, mirroring the `wl_deflect.py` precedent: `wl_liveness.py`'s own docstring frames it as "worker verification... measured on this machine" -- i.e., checking a claim the harness *itself already makes*. This new check is the opposite shape: an unconditional, bookkeeping-agnostic sweep of *every* OS descendant, whether or not anything currently declares it. Folding that into `wl_liveness.py` would blur exactly the line `wl_liveness.py`'s own docstring draws ("THE HONESTY RULE... the event payload is authoritative for EXISTENCE") -- the sweep's whole point is to find things the event payload does *not* mention. A separate module keeps that boundary visible and testable in isolation, the same reasoning that earned `wl_admit.py` its own file beside `wl_checks.py`.

**Reused verbatim from `wl_liveness.py`:** `proc_table()` (both the Linux and `ps` fallback, extended per 3 below), the general shape of `harness_ancestors()`'s bounded 8-hop walk (reused for anchor-pid discovery, not for the descend-from set -- see 2), the `WORKLIST_HARNESS_PID` test/production override convention, and the "OS layer only ever ADDS facts, never invents a false verdict" doctrine.

**New in `wl_bgsweep.py`:** the anchor-pid resolver, the full descendant BFS, per-pid age computation, the flat-threshold classification, and the report-row formatting. No worklist-item or lease concept is touched -- this check has no join to `fold.items` at all, which is itself part of the safety story (it cannot mis-attribute a stray process to the wrong tracked item, because it never looks at items).

### 2. The sweep itself: anchor at the harness pid ITSELF, not at `harness_ancestors()`'s multi-hop set

This is the one point where the plan **deliberately departs** from the literal wording in the ask ("given `harness_ancestors()`'s existing anchor set (or a direct anchor at the harness pid itself, per the experiment)") and resolves it in favor of the single-pid anchor, for a reason proven live (see evidence c): `harness_ancestors()`'s 8-hop set reaches up through the terminal shell, the session leader, and eventually `init` -- nodes that **can** legitimately be shared with a sibling Claude session (e.g. two `claude` invocations launched from the same terminal bash would share that bash as a common ancestor). Descending from the *whole* ancestor set would then pull in the sibling's entire subtree. Descending from **only the harness's own single pid** cannot: a process has exactly one parent, so two distinct `claude`-harness processes (each a fresh top-level invocation, never spawned as a child of another running `claude` process under normal operation -- subagents run in-process, per `wl_liveness.py`'s own docstring, and background bash tasks spawn shells, not new harness processes) are structurally guaranteed to be in disjoint subtrees. This was verified live, not assumed: 3 sibling `claude` processes exist on this machine right now and share **no** ancestor with this session's own harness pid except `pid 2` (an `init`-adjacent node universally shared machine-wide, and never used as a walk-down anchor).

**Anchor resolution, in order, each cross-checked against the next:**
1. `WORKLIST_HARNESS_PID` env override (existing convention, tests + degraded setups) if set and present in the current `proc_table()`.
2. `os.environ.get("CLAUDE_PID")` -- observed live in this session's own environment (`CLAUDE_PID=2531105`), sitting alongside the documented `CLAUDE_CODE_SESSION_ID`/`CLAUDECODE` family the hooks already read elsewhere (`.claude/hooks/stop/wl_core.py:217-224`). Not currently referenced anywhere in this repo's own scripts (verified by grep), so it is treated as **harness-reported, not repo-guaranteed** -- used only after being cross-validated (below), never trusted blind.
3. Fallback / cross-check: walk up from `os.getpid()` (the hook's own pid) exactly as `harness_ancestors()` already does, bounded to 8 hops, and take the **first** ancestor whose `/proc/<pid>/comm` equals `claude`. Verified live to agree exactly with `CLAUDE_PID` in this session (both independently resolve to pid 2531105).
4. If step 2's pid and step 3's pid **disagree**, or neither resolves, the sweep reports nothing for that stop (fail silent, matching `wl_liveness`'s existing "OS layer only ADDS, never invents" posture) rather than guessing an anchor -- an unresolved anchor is exactly the situation where a wrong guess could reach outside this session.

**The descend:** one BFS over the already-built `proc_table()`'s ppid->children map, seeded *only* at the resolved single anchor pid, collecting every transitive descendant (no depth bound needed -- the table itself bounds the work, proven at 0.014ms for 33 descendants live). This intentionally **includes** shells the event payload no longer lists as `live_bg` at all (a background task the harness's own bookkeeping considers finished, but whose OS process is still alive) -- that edge case is explicitly **in scope**, because it is precisely the gap the operator described ("regardless of whether the harness's own event-payload bookkeeping currently mentions it"). `verify_background` already covers the case where bookkeeping *does* mention it; this sweep is the complement.

### 3. Age measurement

- Linux: `/proc/<pid>/stat` field 22 (`starttime`, clock ticks since boot) combined with `/proc/uptime` and `os.sysconf("SC_CLK_TCK")` -> wall-clock start epoch -> age. Verified live end-to-end (see evidence). `st_mtime` is explicitly never used (it is not process start time, and `_proc_table_linux` doesn't even stat the pid directory today -- only `/proc/<pid>/stat` and `/proc/<pid>/cmdline`).
- `_proc_table_ps()` (macOS fallback) currently returns no start-time information at all -- a real gap. Fix: add `etimes=` (elapsed seconds, a direct BSD/GNU `ps` field -- confirmed present and correctly reporting on this Linux box as a cross-check: `ps -axo pid=,ppid=,etimes=,args=`) to the existing `ps -axo pid=,ppid=,args=` fallback call, so the fallback carries `(pid, ppid, age_seconds, cmdline)` directly with no uptime arithmetic needed on that path. If a given `ps` build lacks `etimes` (older BSD variants use `etime=` as a `[[dd-]hh:]mm:ss` string instead), degrade to **no age** for that row rather than mis-parsing -- an unaged row is reported as "OS-visible, age unknown," never silently dropped and never guessed at zero.
- `proc_table()`'s return shape grows a 4th element (start time / age-seconds) behind a **new function**, not a signature change to the existing tuple everywhere it's already unpacked (`verify_background`, `harness_ancestors`, etc. all consume the current 3-tuple in several places) -- avoids a wide, cross-cutting refactor for a feature that only needs the extra field in one place. `wl_bgsweep.py` calls its own `_proc_table_with_age()` wrapper that augments `wl_liveness.proc_table()`'s Linux path with one extra `/proc/<pid>/stat` field read (already opened for ppid) and reads `/proc/uptime` once per sweep, or (fallback) calls a small variant of `_proc_table_ps()` with `etimes` added.

### 4. The 20-minute threshold: a new, distinct constant

`WORKLIST_BGSWEEP_AGE_MIN` (default `20`), **not** a rename or reuse of `BG_STALE_MIN` (15). These measure genuinely different things and merging them would hide that: `BG_STALE_MIN` is *quiescence* -- has a task the harness still declares stopped **writing output** -- and can fire on a process that is only 2 minutes old (a slow build with no stdout yet) or stay silent on a process running for hours that streams continuously. The new constant is *raw wall age since process start*, independent of output activity and independent of whether the harness still declares the task at all. A comment at the new constant's definition cross-references `BG_STALE_MIN` explicitly, naming why the two are not merged, so a future reader does not "fix" the apparent duplication.

### 5. Notification, not action

- Output rides the existing `wl_checks.py` `vadd(key, always, text)` violation-tuple plumbing, one new key (e.g. `"bg-orphan"`), `always=False` (HYGIENE tier -- see 7 for why).
- New message template `V_BG_ORPHAN` in `worklist_messages.py`, sibling to `V_DEFERRED_FINDING`/`V_MANY_WAITERS`: lists each flagged pid, its age, its cmdline (truncated, same 60-70 char convention as `worker_facts`), and states plainly this is advisory-only -- "still alive, N minutes old, not declared by any current background task; read/decide whether to kill it -- this check never kills anything."
- **Where a future kill step plugs in, without building it now**: `worklist.py` already has a "retire a roster entry" verb (`--reap <me> <task-id>...`) that only ever mutates bookkeeping, never an OS process. A future, separate change would add a parallel CLI verb (e.g. `--reap-pid <me> <pid>`) that (a) requires an explicit human/operator invocation, never something a hook calls on its own, and (b) **re-resolves** the anchor and re-confirms the target pid is still a live descendant of *that same, freshly-recomputed* anchor at the moment of the kill call (a TOCTOU guard -- the pid could have been reaped and reused by an unrelated process between the notify and the act). That re-validation requirement is the reason this plan's anchor-resolution logic (2) is written as a small, reusable, exported function rather than inlined into the report path: the future kill step is the second caller, proving the function's contract without this plan needing to build the caller.

### 6. Safety proof obligation

Claim: this design cannot surface or act on a different Claude session's process. Proof, tied directly to the live evidence in this document rather than asserted generally:

1. The sweep's descend-from set is seeded at **exactly one pid** -- the resolved harness anchor -- never at any of its own ancestors. (2)
2. A process has exactly one parent; therefore the sweep's result set (the anchor's transitive descendants) is, by definition of a tree, disjoint from the transitive-descendant set of any *other* pid that is not an ancestor or descendant of the anchor.
3. Two distinct `claude`-comm harness processes are never in an ancestor/descendant relationship with each other under normal operation (subagents are in-process; background tasks spawn shells, not new harness processes) -- verified live: this machine currently runs 4 distinct `comm=claude` processes, and pairwise ancestor-chain comparison shows the only pid any two of them share is `pid 2` (a system-wide root-adjacent node, never a sweep seed). Concretely: this session's anchor-chain is `{2531105, 742, 735, 734, 2}`; the three sibling sessions' chains are `{564910, 547633, 547626, 547625, 2}`, `{811674, 774789, 774776, 774775, 2}`, `{2041373, 901471, 901467, 901465, 2}` -- zero overlap below `pid 2`.
4. Even the pathological edge case (a user manually running `claude` as a Bash-tool child *inside* this session) does not break the proof: the nested `claude` process would genuinely be this session's own descendant, so including it is correct scoping, not a leak -- it would only be a leak if the *nested* session's own descendants were reachable from some node **above** this session's anchor, which they structurally cannot be (they're only reachable downward from the nested pid, which is itself only reachable downward from this session's anchor).
5. Read access itself is independently bounded by the OS: attempting to read a sibling session's `/proc/<pid>/environ` (same uid, `-r--------` permissions) was tested live and returned nothing -- consistent with ptrace-scope restrictions on non-ancestor processes. The design never needs or attempts that read (`/proc/<pid>/stat` and `/proc/<pid>/cmdline`, which `proc_table()` already reads today for every pid on the box regardless of owner, are the only files touched, and are world-readable) -- noted here only as an additional, independent layer, not the load-bearing one; the load-bearing guarantee is the single-pid-anchor tree property in points 1-4.

### 7. Cost

`proc_table()` (already called every stop by `verify_background`) measured live at ~11ms for 555 processes. The BFS descendant sweep over an already-built table measured live at 0.014ms for 33 descendants -- negligible. Cost is therefore **not** the deciding factor for `always` vs. rotated. The deciding factor is the tier-admission rule at `.claude/hooks/stop/wl_checks.py:2721-2740`: none of I1 (compute-time budget spent regardless of display), I2 (someone else is blocked on this), or I3 (hook/gate blindness) hold for a leftover-shell notice -- nobody but this same session is waiting on it, and showing it one stop later costs nothing. So: **`always=False`, HYGIENE tier**, rotated exactly like `wl_deflect.py`'s design and unlike the `always=True` idle-stall gate. Unlike a *blocking* rung, no latch is needed to avoid the `poll_fast_path` deadlock (this never blocks a stop), and unlike the ladder's `resolve`/`gone` rungs, no once-per-stamp firing is needed either -- the row is simply recomputed fresh from `/proc` on every stop that happens to show HYGIENE-tier output, matching the documented reasoning elsewhere in `wl_checks.py` ("everything else is recomputed from artifacts each stop, so showing one at a time loses nothing").

### 8. Test coverage plan

- **Synthetic proc-table fixtures**, matching `wl_liveness`'s/`wl_admit`'s existing convention (a fabricated `[(pid, ppid, cmdline, start_epoch)]` list passed directly to the sweep functions, `WORKLIST_HARNESS_PID` env override for anchor selection):
  - Anchor resolution: `CLAUDE_PID` agrees with the comm-walk fallback -> resolves; disagree -> refuses (reports nothing); neither present -> refuses.
  - Descendant BFS: a multi-generation fake tree where a sibling subtree hangs off a *shared grandparent* (not the anchor) -- MUST NOT appear in the sweep result (this is the fixture that directly encodes the 6 safety proof as a regression control, a RED/GREEN pair: rooting the BFS at the grandparent instead of the anchor pid must be shown to leak the sibling, proving the anchor choice is load-bearing and not just tidy).
  - Age classification: pids at 19m59s (no flag), 20m00s (flag, boundary), and one with unreadable/missing start time (reported as "OS-visible, age unknown," never silently dropped, never treated as 0 or as infinite).
  - `_proc_table_ps()` fallback: a fabricated `ps -axo pid=,ppid=,etimes=,args=`-shaped stdout string, including one line where `etimes` fails to parse (degrades to unaged row, not a crash).
- **Real smoke test**, end to end: spawn an actual `subprocess.Popen(["sleep", "2"])` as a real child of the test process, resolve the anchor to the test process's own pid via `WORKLIST_HARNESS_PID`, and confirm the sweep finds it with a real, correctly-computed age (using a mocked `time.time()`/injected "now" to age it past 20 minutes without an actual 20-minute wait -- mirrors the ask's "spawn short-lived, age past threshold via mocked clock" requirement) -- this is the one test that proves the `/proc/<pid>/stat` starttime + `/proc/uptime` arithmetic is right on a live kernel, not just algebraically consistent with a fabricated fixture.
- Run the new test file plus the full `wl_liveness`/`wl_checks` suite afterward to confirm no regression (same closing step as the `wl_deflect.py` plan).

## Boxes

- [x] Add `wl_bgsweep.py`: anchor resolution (env override -> `CLAUDE_PID` cross-checked against comm-walk fallback -> refuse), the descendant BFS seeded at the single anchor pid, `_proc_table_with_age()` (Linux: extra `/proc/<pid>/stat` field + `/proc/uptime`; fallback: `ps -axo pid=,ppid=,etimes=,args=`), and the flat `WORKLIST_BGSWEEP_AGE_MIN` (default 20) classification.
    (ticked) 2026-09-23T17:39:44Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.
- [x] Add `V_BG_ORPHAN` to `worklist_messages.py`, listing pid/age/cmdline per flagged row, explicitly stating it is advisory-only.
    (ticked) 2026-09-23T17:39:44Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.
- [x] Wire into `wl_checks.py` as `vadd("bg-orphan", False, ...)`, `try/except Exception` around the call site matching every sibling detector (a crashing detector must never crash a stop).
    (ticked) 2026-09-23T17:39:44Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.
- [x] Extend `wl_liveness._proc_table_ps()`'s `ps` invocation to add `etimes=` (or add a sibling function in `wl_bgsweep.py` if touching the shared fallback risks other callers -- decide based on whether any other caller of `_proc_table_ps()` would be broken by a 4th tuple element; keeping it additive/optional is preferred).
    (ticked) 2026-09-23T17:39:44Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.
- [x] Test file (`test-bgsweep.py` or similar): synthetic fixtures per 8, including the sibling-leak RED/GREEN control, plus the real `sleep`-and-mocked-clock smoke test.
    (ticked) 2026-09-23T17:39:44Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.
- [x] Run the new test file and the full `wl_liveness`/`wl_checks` suite; confirm no regression.
    (ticked) 2026-09-23T17:39:45Z by d778be9d: Landed in commits 8bea7d09d/4faa8e500; investigation ledger committed at c1abde472.

## Critical files

- `.claude/hooks/stop/wl_liveness.py`
- `.claude/hooks/stop/wl_bgsweep.py` (new)
- `.claude/hooks/stop/wl_checks.py`
- `.claude/hooks/stop/worklist_messages.py`
- `.claude/hooks/stop/test-teammate-idle.py` (sibling test-fixture pattern to clone)

---

## Live experiment evidence (commands and real output, this machine, this session)

**Anchor identification (2a, matches the operator's stated anchor exactly):**
```
$ pid=$$; for i in $(seq 1 12); do
    [ -d /proc/$pid ] || { echo "pid=$pid gone"; break; }
    comm=$(cat /proc/$pid/comm); echo "pid=$pid comm=$comm"
    pid=$(ps -o ppid= -p $pid | tr -d ' '); [ -z "$pid" ] && break
  done
pid=3670882 comm=bash
pid=3670881 comm=bashcov-sup
pid=2531105 comm=claude          <- this session's own harness process
pid=742 comm=bash
pid=735 comm=Relay(742)
pid=734 comm=SessionLeader
pid=2 comm=init-systemd(Ub
pid=1 comm=systemd
```

**Descendant sweep + age math (2b), anchored ONLY at pid 2531105:**
```
ANCHOR 2531105 has 33 descendants total
clk_tck 100 uptime_s 434985.13
bash-comm descendants with age:
pid=1150323 comm=bash age_min=202.9 cmd='/bin/bash -B -c source .../shell-snapshots/snapshot-bash-1790090737560'
pid=1195902 comm=bash age_min=202.2 cmd='...'
pid=1231360 comm=bash age_min=201.7 cmd='...'
pid=1261724 comm=bash age_min=200.6 cmd='...'
pid=1266177 comm=bash age_min=199.8 cmd='...'
pid=1271121 comm=bash age_min=199.1 cmd='...'
pid=1921248 comm=bash age_min=138.4 cmd='...'
pid=3116133 comm=bash age_min=67.8  cmd='...'
pid=3222434 comm=bash age_min=66.4  cmd='...'
pid=3518269 comm=bash age_min=61.6  cmd='...'
pid=3671153 comm=bash age_min=0.0   cmd='...'   (the command that just ran this experiment)
```
10 of these 11 are already past a 20-minute threshold -- direct, live confirmation of the operator's "too many background shells" observation, computed via `/proc/<pid>/stat` field 22 (starttime, ticks) + `/proc/uptime` + `sysconf(SC_CLK_TCK)`, never `st_mtime`.

**Cross-session exclusion (2c):**
```
all comm=claude pids on this machine: [564910, 811674, 2041373, 2531105]
this session's own ancestor set (own pid + ancestors up to pid<=1): [2, 734, 735, 742, 2531105]
claude pid=564910  ppid_chain=[564910, 547633, 547626, 547625, 2]   overlap_with_anchor_chain={2}
claude pid=811674  ppid_chain=[811674, 774789, 774776, 774775, 2]   overlap_with_anchor_chain={2}
claude pid=2041373 ppid_chain=[2041373, 901471, 901467, 901465, 2]  overlap_with_anchor_chain={2}
claude pid=2531105 ppid_chain=[2531105, 742, 735, 734, 2]           overlap_with_anchor_chain={2531105, 2, 742, 734, 735}
```
Every sibling session's ancestor chain intersects this session's only at `pid 2` -- never at this session's own harness pid or anything below it -- confirming the anchor-at-single-pid design in 2/6 rather than the coarser multi-hop `harness_ancestors()` set (which reaches `742`/`735`/`734`, nodes that *could* be shared by a sibling session launched from the same terminal, though none of the three observed here happen to be).

**`CLAUDE_PID` corroboration (used in 2 anchor resolution):**
```
$ env | grep -i claude
CLAUDE_PID=2531105
CLAUDE_CODE_SESSION_ID=d778be9d-a8e6-4b88-a419-e8a03e7e9888
...
```
Agrees exactly with the independently-derived comm-walk anchor above; not set by anything in this repo's own scripts (`grep -rn CLAUDE_PID .claude/` returned nothing), so treated in the design as harness-reported and cross-validated, not repo-guaranteed.

**Read-access boundary (independent, non-load-bearing layer in 6):**
```
$ cat /proc/564910/environ | tr '\0' '\n'   # sibling session, same uid
(empty; -r-------- 1 developer developer 0 ...)
```

**Cost:**
```
proc_table(): 555 processes in 11.2 ms
BFS descendant sweep: 0.014 ms for 33 descendants
```

**`ps` fallback field feasibility (for the macOS-path age fix in 3):**
```
$ ps -axo pid=,ppid=,etimes=,args= | grep -E "^\s*2531105\s"
2531105     742   80389 claude --dangerously-skip-permissions --resume d778be9d-...
```
`etimes` (elapsed seconds) parses cleanly and needs no `/proc/uptime` arithmetic on the fallback path.

Design produced by a dispatched Plan agent (2026-09-23), grounded in a live experiment on this session's own real process tree (not a hypothetical), per the operator's explicit request for an investigation + experiment agent.
