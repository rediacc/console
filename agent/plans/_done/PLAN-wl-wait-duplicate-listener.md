# PLAN: wl_wait duplicate listeners -- `--timeout 60` is SIXTY MINUTES and nothing refuses a second instance

Status: done
First-Seen: 2026-09-23
Owner: d778be9d
Updated: 2026-09-23

Thirteen simultaneous `wl_wait.py d778be9d --timeout 60` processes accumulated over roughly 55 minutes in one session. The operator found them with `ps aux` and cleared them by hand (`pkill -f "wl_wait.py d778be9d"`). Neither the script nor the Stop hook nor the PostToolUse nudge could see the pile, and one of the three was actively disabled by it.

## The finding

### 1. `--timeout 60` means SIXTY MINUTES, not sixty seconds, and only `--help` says so

The units claim in this session's memory note is correct, and it is the whole magnitude of the incident.

- `.claude/hooks/stop/wl_wait.py:38` -- `DEFAULT_TIMEOUT_MIN = float(os.environ.get("WORKLIST_WAIT_TIMEOUT_MIN", "60"))`, with the comment on line 37 naming "60 minutes, matching the hourly work-loop cadence".
- `.claude/hooks/stop/wl_wait.py:204` -- `deadline = time.monotonic() + timeout_min * 60.0`. The `* 60.0` is the conversion; the flag value is minutes.
- `.claude/hooks/stop/wl_wait.py:491-501` -- `main()` parses `--timeout` as a bare float into `timeout_min` with no unit anywhere in the token.
- `.claude/hooks/stop/wl_wait.py:314` -- the only user-visible statement of the unit is one line inside `HELP`: `--timeout <minutes>   default %d`.

So `--timeout 60` blocks for 3600 seconds. Relaunching on a several-minute cadence for 55 minutes produces exactly the observed 13 overlapping instances, and none of them was ever late: each was 5 to 55 minutes into a 60-minute deadline.

**This exact misreading has already been paid for once in this file's own history.** `.claude/hooks/stop/worklist_messages.py:621` carries the post-mortem comment: "SIXTY, not 900. `--timeout` is in MINUTES (wl_wait.DEFAULT_TIMEOUT_MIN, `timeout_min * 60.0`), so 900 asked for a FIFTEEN-HOUR wait". The repair then was to correct one literal in one message.
The ambiguity in the flag itself was left standing, and it fired again.

**The ambiguity has a sibling that makes it worse.** The other sanctioned long-lived background instrument in this repo takes the same flag name in the opposite unit: `.ci/scripts/ci/ci-trace.py:346` defaults `--timeout` to `5400` SECONDS (`CI_TRACE_TIMEOUT_S`), and `.claude/skills/ci-watch/SKILL.md:18` documents it as "`--timeout` overrides the 5400s default".
A session that has internalised `--timeout` from `ci-trace` reads `--timeout 60` on `wl_wait` as a minute.

### 2. What a running instance actually does: a lock-free poll of two file stats, fully independent of every other instance

- `.claude/hooks/stop/wl_wait.py:207-220` -- the wait loop. Each pass touches a heartbeat, checks the deadline, then `time.sleep(min(TICK_S, remaining))` with `TICK_S = 2` seconds (`:36`).
- `.claude/hooks/stop/wl_wait.py:43-49` -- `_stat()` returns `(size, mtime_ns)`. The two watched paths are the requests log (`S.requests_path`, `:197`) and the report index (`RPT.index_path`, `:198`). A change in either triggers a fold; `_new_requests` (`:73-82`) and `RPT.unread` (`:240`) diff against the launch-time baseline from `arm()` (`:52-70`).
- It is NOT blocking on a subprocess and NOT watching for a worklist event through any queue. It is a two-stat poller, by declared necessity (module docstring `:21`: no inotify, no epoll portability, `pip install` refused under PEP 668).
- **It holds no lock, and that is deliberate and load-bearing.** Module docstring `:15-17`: "IT NEVER TAKES A LOCK, AND THAT IS THE SHARPEST HAZARD IN THE WHOLE DESIGN", because `_append_lines` takes a blocking `LOCK_EX` and the two `LOCK_EX|LOCK_NB` paths (`wl_requests.py:165`, `wl_store.py:1981`) give up SILENTLY on contention, so an hour-long holder would turn them into invisible no-ops. Any fix must not violate this.

**Consequence: every instance is fully duplicative.** All 13 armed their own baseline, stat'ed the same two files every 2 seconds, and each ran `RPT.scan(store, start)` every 300 seconds (`:40`, `:222-224`, `_safe_scan` at `:85-92`) against the same shared report store.

### 3. The duplicates actively DISABLED the lapse detector, because the heartbeat is a single-writer file used by N writers

This is the harm beyond wasted processes, and it is structural.

- `.claude/hooks/stop/wl_wait.py:103` -- `heartbeat_path()` returns ONE path per session: `worklist.with_suffix(".waiter-<me8>")`. It carries a timestamp and no pid.
- `.claude/hooks/stop/wl_wait.py:208` -- every instance `_touch(hb)` on that same path every 2 seconds.
- `.claude/hooks/stop/wl_wait.py:218` and `:268` -- on exit an instance writes a TOMBSTONE to that same path instead of unlinking it (`tombstone()`, `:150-161`).

With 13 writers, a tombstone written by an exiting instance is overwritten by a survivor's `_touch` within 2 seconds. So:

- `waiter_lapsed()` (`:164-180`) can never return a lapse while any duplicate survives, because it reads the CONTENT of a file the survivors keep rewriting as a live pulse.
- The Stop-hook `waiter-lapsed` violation (`.claude/hooks/stop/wl_checks.py:3755-3771`, message `worklist_messages.py:644-656`) is therefore unreachable for a session with duplicates. The mechanism built specifically to catch "the waiter died and was not relaunched" is switched off by the pile.
- `_is_tombstone` in the PostToolUse nudge (`:421`, `:334-339`) reads the same clobbered file.

The tombstone design (landed per `agent/plans/PLAN-stop-always-tier.md`) assumes exactly one live waiter per session. Nothing enforces that assumption.

### 4. Nothing anywhere counts waiters. Every consumer treats the list as a boolean

The Stop hook does see all 13.
`.claude/hooks/stop/wl_checks.py:2316` takes `live_bg` from the event's running `background_tasks`; `:2578-2582` computes `_waiters_confirmed = wl_liveness.confirmed_waiters(live_bg, bg_verdicts)`, which returns a LIST (`wl_liveness.py:244-257`) of every task whose command contains `WAITER_MARK = "wl_wait.py"` (`:230-241`) and whose process the OS confirms (`verify_background`, `:205-226`).

Verified against the live process tree in this checkout: the harness spawns the waiter under a `bashcov-sup` wrapper whose ppid IS the harness pid, and whose cmdline embeds `eval 'python3 .claude/hooks/stop/wl_wait.py d778be9d --timeout 60'`.
`_needle` (`wl_liveness.py:152-165`) takes the whole quote-free declared command, `harness_ancestors` (`:137-150`) contains the harness pid, so the verdict is `confirmed`. Duplicates are confirmed just as readily as a single instance.

And then every consumer discards the count:

| Site | Use |
|---|---|
| `wl_checks.py:2586` | `_only_waiters = bool(_waiters_confirmed) and len(_waiters_confirmed) == len(live_bg)` -- 13 waiters and no other job still satisfies this |
| `wl_checks.py:3712` | `not _waiters_confirmed` (no-poll relaxation) |
| `wl_checks.py:3735` | `not _waiters_confirmed` (no-waiter violation) |
| `wl_checks.py:3783` | `not _waiters_confirmed` (no-waiter-asked ladder) |
| `wl_checks.py:3833` | `_waiters_confirmed and _only_waiters and not actionable_remains` (waiter-drained report) |

The one place a count is ever rendered is `N_WAITER_DRAINED` (`worklist_messages.py:550-560`), which prints `%d` waiters and a `TaskStop <id>` line each -- and it fires ONLY for a session with nothing open, in flight or pending (`wl_checks.py:3833`). A busy session accumulating duplicates never reaches that state, which is why the pile stayed invisible for 55 minutes.

The precedent for the check that is missing is two dozen lines further down the same function: `wl_checks.py:3849-3860` fires `many-work-crons` on `len(live_work_crons) > 1`, and `:3861-3862` fires `many-poll-crons` the same way. "More than one of this instrument is a violation" is an established shape here. It was never applied to waiters.

### 5. The PostToolUse nudge was not the driver, and the Stop hook was not either

Both gate correctly, which narrows the cause to the session's own relaunch behaviour and confirms that no amount of message-tuning closes this.

- `wl_wait.py:418-425` -- `nudge()` returns silently when the heartbeat is fresh and not a tombstone. With 13 instances refreshing it every 2 seconds it was permanently fresh, so the nudge said nothing.
- Every Stop-side relaunch demand (`no-waiter` `:3735`, `waiter-lapsed` `:3755`, `no-waiter-asked` `:3783`) is gated on `not _waiters_confirmed`, which was false.

So the relaunches came from the session acting on the standing instruction that the waiter "FIRES ONCE" and must be relaunched (`wl_wait.py:262-267`, `HELP` `:299-301`, `V_NO_WAITER` `worklist_messages.py:627-642`), combined with the belief that a 60-second process had already finished. **Prose cannot fix that.** The script must refuse.

### 6. Existing mechanism a fix can reuse

Three, and no new convention is needed:

- **A per-session marker file already exists.** `heartbeat_path()` (`:103`) resolves to `/tmp/claude-worklist/home_developer_console.waiter-<me8>` in this checkout, is refreshed every 2 seconds by a live instance, goes stale in `HEARTBEAT_STALE_S = 60` (`:322`), and already has a reader predicate: `_fresh(hb, HEARTBEAT_STALE_S) and not _is_tombstone(hb)` (`:421`).
- **A non-blocking flock idiom on a dedicated sidecar.** `wl_requests.py:162-166` opens `str(S.requests_path(worklist)) + ".lock"` and takes `S._flock(lock, S.LOCK_EX | S.LOCK_NB)`, returning on `OSError` ("another stop is escalating; it wins, next stop retries").
`S._flock` (`wl_store.py:50-66`) is the portability shim that raises a NAMED refusal rather than an `ImportError` where `fcntl` is absent.
This is a lock on a PRIVATE file, not on the worklist store, so it does not violate the module docstring's prohibition (`:15-17`).

- **A Stop-hook "more than one is a violation" check.** `many-work-crons` / `V_MANY_WORK_CRONS` (`wl_checks.py:3849`, `worklist_messages.py:384-389`) is the template, including the "delete the redundant one with `<verb>`" closing line.

Nothing needs to be invented. The gap is that none of it was pointed at duplicate waiters.

### 7. Scope of the class

Within `.claude/hooks/stop/`, `wl_wait.py` is the only script launched as a long-lived background task. `wl_profile.py` and `wl_ressample.py` also call `time.sleep`, but both are in-process instruments driven by the hook, not background pollers a session relaunches.

The class member OUTSIDE that directory is `.ci/scripts/ci/ci-trace.py --wait`: a 25-second poll loop (`:40`, `:119`, `:164`, `:379`, `:408`) with a 5400-second deadline (`:346`), launched `run_in_background: true` by `.claude/commands/pr-merge.md:134,188,189` and `.claude/skills/ci-watch/SKILL.md:18`. It has **no instance guard of any kind** (no flock, no pidfile, no argv scan).
`pr-merge.md:134` carries the rule "**One wait per command**" as prose only. Two `--wait` traces on the same head is the same shape of waste, and the opposite-unit `--timeout` is the shared root of the misreading. A fix to `wl_wait.py` alone is incomplete under the sweep-the-class rule.

## The fix

**Fail-fast in the script, with a private non-blocking flock as the authoritative mutex and the existing heartbeat as the message source; plus a Stop-side `many-waiters` violation as the OS-truth backstop; plus a mandatory unit suffix on `--timeout` on both long-lived instruments.**

The script refusing is what closes the failure, because the failure arrives through a channel prose does not reach: a session that believes the previous instance already exited. Every message can stay exactly as correct as it is today and the pile still cannot form.

### Why not "one long-lived listener instead of relaunch-per-stop"

Refuted by the mechanism, not by preference. `wl_wait.py:6` and `:8-9`: "Launched as a BACKGROUND SHELL TASK. Its exit is the ping. [...] the one push channel that exists is the harness notifying the session when a background task finishes".
`:262`: "THE WAITER FIRES ONCE AND IS THEN GONE." A listener that stays alive across Stop cycles delivers nothing, because staying alive IS silence. The exit is the entire product.

The distinction that matters is which exit was relaunched over. A waiter that FIRED is already gone, so a relaunch after a fire can never duplicate. Duplicates can only be created by relaunching over the TIMEOUT branch (`:210-219`), which is a process still counting down 60 minutes.
Fail-fast closes exactly that window, and it does so without changing the fire-path guidance at `:263-267` -- which stays correct and must stay loud, since a session that does not re-arm after a fire goes deaf (measured case recorded at `:262`: "a waiter fired at 16:13, a peer answered at 16:16, and the answer was never seen").

So no `RELAUNCH THE WAITER NOW` text needs to stop instructing a relaunch. Under fail-fast the instruction becomes idempotent: relaunching is always safe to attempt, because a redundant attempt refuses in milliseconds. That is a strictly better property than a message that tries to predict whether a relaunch is warranted.

### Why not self-cleanup (kill the prior instance on start)

Rejected as the start-time action, on three concrete grounds:

1. **It kills the wrong process.** An incumbent 55 minutes into its deadline may be seconds from firing with a peer's answer in hand. The duplicate has nothing to lose; the incumbent has the whole baseline. Fail-fast kills the one with no value.
2. **The heartbeat is process-anonymous** (`:103`, `:140-143` write a timestamp and no pid), so a killer must scan argv instead -- and this repo's own guards document why that is a trap: `block_shell_background_waiter.py:44` ("a bare `pgrep -f` self-matches the Bash tool wrapper containing the caller's own pattern text") and `block_self_matching_pgrep.py:84`.
3. **It leaves a phantom in the harness task table, which is worse than the duplicate.** Killing the OS process does not retire the harness task; `TaskStop` is the only clean teardown, which is why `N_WAITER_DRAINED` (`worklist_messages.py:550-560`) teaches `TaskStop <id>` as the verb.
A killed-but-still-declared task then rates `suspect` under `verify_background` (`wl_liveness.py:224-226`), `suspect` does not satisfy `confirmed_waiters` (`:244-257`), and the session gets nagged by `no-waiter` into launching yet another one.
Self-cleanup would convert a wasteful state into a self-amplifying one.


Teardown of a genuine surplus stays a `TaskStop`, surfaced by the new `many-waiters` check, not a `kill` issued by a competing process.

### Shape of the guard

Placed in `wait()` immediately after the path computations (`wl_wait.py:188-191`) and BEFORE `_safe_scan`/`arm` (`:194-195`), so a duplicate pays for nothing:

- Open `str(worklist) + ".waiterlock-<me8>"` and take `S._flock(fh, S.LOCK_EX | S.LOCK_NB)`, holding the handle for the process lifetime. The fd closes on return, releasing it. Dedicated file, never the worklist store, so the `:15-17` prohibition holds.
- On `OSError` (contention): print a refusal naming the incumbent's heartbeat age from `_fresh`/`stat`, and return a NEW exit code **3**.
- On `RuntimeError` from `_flock` (no `fcntl`): degrade to the heartbeat predicate alone (`_fresh(hb, HEARTBEAT_STALE_S) and not _is_tombstone(hb)`), which is the same predicate `nudge()` already trusts at `:421`.
- **The duplicate must touch nothing**: no `_touch`, no `tombstone`, no `_safe_scan`. Writing a tombstone from a refusing duplicate would falsely mark the incumbent lapsed.

Exit 3 rather than 0 or 2: exit 0 would make the harness notification indistinguishable from a fired waiter, and a session acting on it would relaunch again -- turning a slow pile-up into a fast spin. Exit 2 is the misuse bucket (`:480`, `:485`, `:498`, `:501`) and a redundant relaunch is a correct reflex, not misuse.
`HELP`'s EXIT CODES block (`:309-313`) already documents codes and gains one line.

The refusal text must say, explicitly, DO NOT RELAUNCH and must name the incumbent, or the session reads a fast exit as "the waiter is gone".

### Shape of the unit fix

`--timeout` on `wl_wait.py` requires an explicit unit suffix (`60m`, `3600s`, `1h`); a bare number is refused with exit 2 and a message naming both readings and the `ci-trace` asymmetry. Same treatment on `.ci/scripts/ci/ci-trace.py`, whose `--timeout` is seconds.
One flag name, one spelling, self-documenting at every call site, and the class ambiguity is removed rather than commented on for a third time. Per the clean-break rule there is no bare-number fallback and no deprecation window; the sweep of the emitters is mechanical and enumerated below.

## Execution notes (2026-09-23)

Three things the boxes did not anticipate, recorded rather than left in the diff:

- **`test_16_wl_wait_takes_no_lock` had to be re-pointed, not deleted.** `.claude/rediacc_hooks/tests/test_wl_report_inbox.py` asserted `_flock(|fcntl.flock(|import fcntl` matched ZERO lines in `wl_wait.py`, so the guard reds it by construction. The assertion is now the one that was actually meant: no BLOCKING lock anywhere in the file (every `_flock` line must carry `LOCK_NB`),
  with `wl_store.py` as the control proving a blocking line is detectable, plus a new `test_16b` pinning that the locked path is the private `.waiterlock-` sidecar and none of the shared ones. The behavioural half, `test_21` (a concurrent worklist write is not delayed while a waiter runs), was already there and still passes.

- **The unit-refusal pair went to `test_wl_report_inbox.py`, not `hookcases.py`.** Every entry in `hookcases.py` is a `check <rc> guards/<name>.py` payload for a pre-bash GUARD; there is no shape there for a CLI invocation of `wl_wait.py`, and a case added there could not execute. The pair is `test_15b`, beside `test_15_wl_wait_misuse`, which is the module that already owns
  wl_wait's argument refusals. `hookcases.py`'s two waiter payloads were swept to the suffixed spelling as the box asked.

- **The `--timeout` sweep reached the test suite too.** `test_wl_background_waits.py`, `test_wl_waiter_controls.py`, `test_wl_report_inbox.py` and `test_wl_identity.py` all launched real waiters with bare numbers (`3`, `0.15`, `0.05`, `0.01`); under the clean break every one of them would have exited 2. Each was rewritten with the `m` suffix, which preserves the value exactly.
  The same sweep exposed a latent defect in the relaunch lines: `--timeout %d` rendered a sub-minute timeout as the literal `0`, a command this script refuses as non-positive. `fmt_timeout` uses `%g` and `test_15b` asserts the printed relaunch command parses back.

## Boxes

- [x] Add the instance guard to `wait()` in `.claude/hooks/stop/wl_wait.py`, between the path computations (`:188-191`) and `_safe_scan` (`:194`): private `.waiterlock-<me8>` sidecar, `S._flock(..., S.LOCK_EX | S.LOCK_NB)`, handle held for the process lifetime, heartbeat-age fallback when `S._flock` raises `RuntimeError` (no `fcntl`).
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
The duplicate path must perform no write of any kind (no `_touch`, no `tombstone`, no `_safe_scan`).

- [x] Return a new exit code `3` from the refusal, and give it a refusal line that names the incumbent's heartbeat age and states DO NOT RELAUNCH in so many words.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Extend the `HELP` EXIT CODES block (`.claude/hooks/stop/wl_wait.py:309-313`) with the `3` row, and add a paragraph stating that a relaunch attempt is always safe because a redundant one refuses.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Record the single-writer assumption in `heartbeat_path()`'s docstring (`.claude/hooks/stop/wl_wait.py:95-104`) and `tombstone()`'s (`:150-161`): N writers on one path clobber a tombstone within `TICK_S`, which is what disabled `waiter_lapsed` (`:164-180`) and the Stop-side `waiter-lapsed` check (`wl_checks.py:3755-3771`).
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
Name the guard as what makes the assumption true by construction.

- [x] Require an explicit unit suffix on `--timeout` in `.claude/hooks/stop/wl_wait.py:492-501`: accept `m`/`s`/`h`, refuse a bare number with exit 2 and a message naming both readings and the `ci-trace` seconds asymmetry. Update the `HELP` line at `:314`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Sweep every emitter of the bare literal to the suffixed form: `.claude/hooks/stop/wl_wait.py:4,214,265,274`; `.claude/hooks/stop/worklist_messages.py:366,545,559,622,635,651`; `.claude/rediacc_hooks/guards/block_shell_background_waiter.py:42,48`; `.claude/oracles/pre-bash/block-shell-background-waiter.sh:63`; `.claude/rediacc_hooks/tests/hookcases.py:2015,2020,2049`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
Keep the guard and its bash oracle byte-identical (they are run as a differential pair).

- [x] Same unit requirement on `.ci/scripts/ci/ci-trace.py:346` (`--timeout`, seconds, default 5400), plus its call sites in `.claude/commands/pr-merge.md:134,188,189` and `.claude/skills/ci-watch/SKILL.md:18`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Add `V_MANY_WAITERS` to `.claude/hooks/stop/worklist_messages.py`, modelled on `V_MANY_WORK_CRONS` (`:384-389`): the count, one `TaskStop <id>` line per surplus task, and the reason (a second waiter is pure cost, and its heartbeat writes destroy the lapse detector). `TaskStop`, never `kill`, for the reason in the self-cleanup rejection above.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Fire it from `.claude/hooks/stop/wl_checks.py` beside the existing `many-work-crons` block (`:3849-3860`): `if len(_waiters_confirmed) > 1: vadd("many-waiters", False, ...)`. Non-always tier, matching `many-work-crons`; `test-always-tier.py`'s pinned set needs no change. Note in the comment that promotion to always-tier is warranted if it ever fires twice.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Verify `_only_waiters` (`.claude/hooks/stop/wl_checks.py:2586`) still behaves for a surplus roster, and that `N_WAITER_DRAINED` (`worklist_messages.py:550-560`) and the new `many-waiters` do not both fire on a drained session with duplicates; if they can, the drained report wins (it already prints every `TaskStop` line).
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Regression test in `.claude/rediacc_hooks/tests/test_wl_background_waits.py` (which already spawns a REAL `wl_wait.py` child, `:106-128`): launch one, assert it holds; launch a second with the same prefix, assert exit 3 and the refusal text; assert the second wrote NOTHING to the heartbeat path (the incumbent's mtime must keep advancing and the content must not become a tombstone). Pair each with the control the file's own docstring demands.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Regression test for the unit refusal: `--timeout 60` (bare) exits 2 with a message naming minutes; `--timeout 60m` is accepted. Add the paired case to `.claude/rediacc_hooks/tests/hookcases.py`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Stop-hook case in `.claude/rediacc_hooks/tests/test_wl_waiter_controls.py` for `many-waiters`: two confirmed waiter tasks in `background_tasks` fires it; one does not (the control).
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Run `python3 -m pytest .claude/rediacc_hooks/tests/` and record the pass count, then prove the new tests can go red by reverting the guard temporarily and restoring it (the recipe `PLAN-git-ignore-aware-discover.md` used).
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] Confirm no waiter of this session is left running after the change (`ps -eo pid,args | grep "[p]ython3.*wl_wait"`), and retire any surplus with `TaskStop` rather than `kill`.
    (ticked) 2026-09-23T11:19:19Z by d778be9d: retroactive record: closed by def57d384 (2026-09-23) docs(agent): fourteen citation-remainder boxes close, one plan at a ti -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
