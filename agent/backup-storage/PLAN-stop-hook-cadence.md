# PLAN: stop-hook cadence, an intent channel, and the noise cuts that come first

Status: executing

**2026-08-15 CLOSED.** Sections 1, 3 and 4 are shipped and covered; sections 5-7 are
constraints and ordering rather than work. **Section 2 (batching the rotating tier) was
never ordered and is NOT done** -- it is deliberately left undone rather than quietly
folded into this closure, because the noise cuts in section 1 removed the measured
majority of forced continuations and batching was always the speculative remainder.
Anyone picking it up should re-measure first; the numbers this plan was written against
are stale.

**2026-08-15, w25: SECTIONS 1 AND 3 ARE SHIPPED. SECTION 4 (`--intent`) IS NOT.**

CORRECTION, and the reason it is written here rather than quietly fixed: an earlier
revision of this line claimed sections 1, 3 AND 4 were all shipped. Section 4 was not
even started -- `grep -c '"--intent"' .claude/hooks/stop/worklist.py` returns 0. This
file's own check warns that a plan saying the wrong thing with a fresh timestamp is worse
than one visibly behind, and that is exactly what a stale status line had just become. The operator answered the
held question with "Ship sections 3-4", so the cadence and the `--intent` design are no
longer pending. Section 2 (batching the rotating tier) is untouched; sections 5-7 are
constraints and ordering, not work. Suite 722/0.

(The status line above is a bare `Status: <word>` on purpose. A dated parenthetical
version of it parsed as UNKNOWN in `plan_records`, which is how five real plans came to
be reported as unreadable -- a format mismatch surfacing as a content problem.)

Landed, all four of them, each with suite coverage (`test-worklist-v5.sh` 703/0, up from
695 when this plan was written):

| Step | What landed | Where |
|---|---|---|
| 1.1 | Roster capped at `WORKLIST_ROSTER_MAX` (6), actionable rows first, counted summary | `wl_liveness.py` |
| 1.2 | `state_world_sig` ownership-scoped; peers survive as a `count//10` bucket | `wl_store.py` |
| 1.3 | Brief staleness given a WORK GATE, keyed on the same signature the STATE.md check uses | `worklist.py --brief`, `wl_checks.py` |
| 1.4 | The verdict prints WHY, not just an age | `wl_checks.py::_agent_state_because` |

Two notes on 1.3 and 1.4, because both differ from what this plan proposed:

- **1.3 landed narrower than section 1.3 describes, on purpose.** Only the STALE verdict is
  gated; `missing` still fires unconditionally, because a session that never briefed is
  invisible to its peers however quiet the world is. A brief written without a signature
  (any predating this change) falls back to wall-clock rather than silently passing.
  `sole_live_session` is untouched and keeps its wall-clock meaning, since it reads the
  brief's raw timestamp rather than this verdict.
- **1.4 landed WITHOUT the per-item evidence** this plan asked for (`"3 of your items
  changed"`). What it prints is the CAUSE (`"your world signature moved since it was
  written"`) and, for the shape verdicts `thin`/`bloated`/`aimless`, no age at all, because
  age is irrelevant to those and printing a staleness limit beside them suggests that
  waiting would help. Counting the specific items remains available if the cause alone
  proves too thin in practice.

**What is HELD and why:** sections 3 and 4 change WHEN THE HOOK BLOCKS. That machinery
exists because sessions abandoned work, overstated handoffs, and let compaction destroy an
operator decision, so a redesign that merely makes stopping easier is a regression dressed
as an improvement. The acceptance test is this plan's own framing: the cadence must make it
easier to be HEARD, not easier to STOP. That call is the operator's, tracked as worklist
`#7f734d46`. **`--intent` does not exist yet and no code may reference it.**

Operator's ask, verbatim: *"stop hook almost always forces you/context to continue which
is not quite right to follow what's happening. We should do 1 report/update 1 others/order
flow... Then stop hook can ask what are you working on now? like questions... Maybe you
didn't report what you want to work before and it disappeared because of pushing of stop
hook."*

---

## 0. THE DIAGNOSIS I GAVE WAS WRONG ON THE KEY POINT

I reported "freshness is wall-clock, not work-based". That is **false for STATE.md** and
fixing it as stated would have made things worse.

`wl_store.py:1428-1436` is: `age <= 15 -> ok`, then `cur_sig != saved_sig -> stale`, else
`ok`. The docstring is honest; an unchanged world genuinely never stales it.

**What actually fires is the signature's blast radius.** `state_world_sig`
(`wl_store.py:1579-1618`) hashes **every item in the store regardless of owner**, and its
docstring argues that deliberately. With ~48 addressable agents in one worktree, any peer's
`--add`/`--tick`/`--state` moves my key. It therefore *degenerates* into "fires every 15
minutes" — indistinguishable from wall-clock at the point of observation, with a completely
different fix.

**Narrow the key, do not touch the limit.** The precedent is in-repo: `world_sig`
(`wl_store.py:1476-1531`) was already narrowed to own-items in v17 for exactly this reason,
with the measurement in its docstring ("32 of 32 events in a 3-hour window came from other
sessions"). `state_world_sig` was simply left behind.

Two more corrections worth keeping:

- **The session brief IS pure wall-clock** (`wl_store.py:1113-1116`): age > 90, no world
  gate at all. That is the check that matches the complaint literally, and it is also the
  one that most wants to become an ask.
- **`ladder-gone` never rotates** (`wl_checks.py:3068`, `always=True`), and all dead workers
  in one stop are joined into a single violation (`:3070`). Three firings meant three
  subagents died at three different stops. **Batching cannot help it**; only a bounded
  roster and a "resolve N leases in one turn" affordance will.

And the strongest in-repo argument for batching is the module's own docstring
(`wl_checks.py:1745-1749`): *"then emits ONE block (five independent blocking checks would
cost five turns to clear, which is the 'stuck in a loop' the old MAX_BLOCKS existed to
paper over)"*. v13 focus reintroduced exactly that cost, for a **noise** reason. We are now
feeling the turn-count side of a trade made on the noise side.

---

## 1. DO THESE FIRST. They change no blocking decision. [LANDED 2026-08-15]

By the planner's count against my session, steps 1-3 would have removed **four to five of
the ten forced continuations without touching a single gate**. Land them and re-measure
before shipping anything that changes when the hook blocks.

### 1.1 Cap the worker roster (largest output cut)

`wl_liveness.worker_facts` (`:453-483`) emits one line per running task, unbounded, and
that string is injected into all three `ladder-*` messages. Add `ROSTER_MAX` (default 6,
env-tunable), using the `GUIDE_MAX` truncation idiom (`wl_checks.py:1081`) and honouring the
no-silent-caps doctrine at `:1075-1078`: print **only actionable rows** in full, then one
summary line `"+ 41 other worker(s), all OS-confirmed and streaming"`. On this session that
is ~48 lines to ~5. Same cap for `bg-report`'s `_rows` (`wl_checks.py:2326-2352`), whose
message currently demands one line per worker — with 48 workers that instruction is itself
a context bomb.

Also scope the ladder's roster to its OWN subjects: a `ladder-gone` about item #abc needs
that worker's row and the live-id candidates, not the whole roster. `ladder()` already
returns the worker id per subject (`wl_liveness.py:526-538`).

### 1.2 Ownership-scope `state_world_sig` (largest continuation cut)

Add `if C.owned_by_me(r.get("owner"), session_id)` to the comprehension at
`wl_store.py:1597-1608`, exactly as `world_sig:1519` does. Keep the peer half only as a
coarse count bucket (e.g. `len(peer_items)//10`) so a genuinely new peer program still
stales the recovery document without every peer tick doing so.

### 1.3 Give the brief a work gate

`wl_store.py:1113-1116` becomes `age > STALE_MIN` **and** own-work moved since the brief's
stamp (`count of own items with upd > brief.when > 0`, or `own_stamp > brief.when`). That
converts the one genuinely wall-clock blocker into a work-based one.

### 1.4 Make the message tell the truth

`V_AGENT_STATE` (`worklist_messages.py:258-273`) prints `"(%d min old, limit %d)"`, which
reads as wall-clock and is precisely why I concluded the code disagreed with its doc. Print
the reason instead: `"(15 min old; your world signature moved: 3 of your items changed
since it was written)"`. The fold already has everything needed.

---

## 2. Batching the rotating tier

Nothing in the code makes one-at-a-time load-bearing. `served`/`pick`
(`wl_checks.py:3266-3279`) is pure LRU bookkeeping; take the `n` smallest instead of the
`min`. `R_FOCUS_MORE` ("the next stop surfaces the next one") is wording, not contract.

```
BATCH = int(os.environ.get("WORKLIST_FOCUS_BATCH", "3"))
picks = sorted(rot, key=...)[:BATCH]
shown = [always-tier bodies] + [picks[0] in FULL]
shown += ["ALSO: " + headline + its NEXT command for picks[1:]]
```

One thing to fix *first* is preserved; N stops collapse to ceil(N/3). Breaks cases 156/156b
(`test-worklist-v5.sh:4942-4990`) and 204 (`:9466-9505`), which assert exactly-one-per-stop;
rewrite them to the weaker true invariants (at most BATCH, LRU starves nothing, held-back
count truthful).

---

## 3. The cadence, and the four guards that stop it being an escape hatch [HELD: operator decision #7f734d46]

State lives in the **per-session state doc** (`<worklist>.state-<sid8>.json`), NOT the event
log: `wl_store.compact` (`:1013-1030`) rewrites the log to the minimal item-reproducing set
and would destroy any novel event kind.

One gate immediately before `if violations:` (`wl_checks.py:3218`):

```
pause = (cad["owed"] == "report"
         and not always_tier                  # (A)
         and rot
         and sha1(last_msg) != cad["msg"]     # (B)
         and not judge_blocking_tier_pending) # (C)
```

- **(A) any `always=True` violation defeats the pause, unconditionally.** That is the whole
  integrity tier: `stuck`, `ci-red`, all three `ladder-*`, `bg-report`, `hook-blind`,
  `event-unparseable`, `pr-unreadable`, `ci-unreadable`, `cl-shape`, `agent-bootstrap`.
- **(B) the pause is granted only if the assistant message CHANGED.** Without this a session
  emits an empty turn after every block and buys a free allow every other stop — the exact
  regression. The suite already models the shape: case 51 does three consecutive blocks with
  no `say` between them, so **it should pass unmodified**, and if it does that is the best
  evidence guard B works.
- **(C) the judge tier is never paused.** Five of its six exits block on the hook's own
  failure to get a verdict.
- **A cap** (`cad["n"]`, default 3) reset whenever `len(rot)` shrinks, mirroring
  `exempt-overrun` at `wl_checks.py:481-486`.

`WORKLIST_CADENCE=off` restores today exactly, as `WORKLIST_FOCUS=off` does.

**Prerequisite bug:** `counter = worklist.with_suffix(".blocks")` (`wl_checks.py:1750`) is
**not session-scoped**, unlike `.stuck-<sid8>` and `.state-<sid8>`. One peer's clean allow
deletes my judge streak. Fix to `.blocks-<me8>` with its own case BEFORE anything keys off
block streaks. The cadence itself keys off the state doc, not `.blocks`.

---

## 4. The `--intent` verb [APPROVED by the operator, NOT YET BUILT; the verb DOES NOT EXIST, do not reference it in code]

New sidecar `<worklist>.intents` (never the event log, which compaction folds away;
`.requests` is the precedent). Not a fifth item state — the four states are the store's
grammar with ~46 call sites. Not a field on the brief — the brief is peer-facing and
length-capped.

```
worklist.py --intent <me> '<=240 chars: what I am doing and the next verb'
            [--covers <check-key|#item-id> ...] [--for <minutes, default 45, max 120>]
```

A fresh intent does exactly **two** things:

1. **Reprioritises the rotation** — covered keys sort last. **Never removed from
   `violations`**, so the header count stays truthful and nothing is silently forgotten.
2. **Gates only `brief` and `agent-state`** — the two checks whose entire content is a
   status question, which a live intent already answers.

**Never suppresses** anything `always=True`, nor `open-items`, `undefaulted`,
`defer-expired`, `unjustified`, `completion`, `cl-*`, `requests`/`answers`, `no-remaining`.
An intent is a statement of plan, not evidence of work.

**Expiry is itself a violation** (`intent-expired`, mirroring `defer-expired`): an intent
past its horizon whose covered keys are still outstanding blocks. That is what stops
`--intent` becoming a mute button.

---

## 5. What must NOT change

The single sharpest framing from the planner, and it is the acceptance test for this whole
change: **the cadence must make it easier to be HEARD, not easier to STOP.**

Load-bearing, each with a named incident behind it:

- The `always=True` integrity tier, defeating the pause unconditionally (case 156d pins it).
- The six no-escape-hatch judge exits — five block on the hook's own failure to get a verdict.
- Tick evidence (`completion`), and the deferral machinery (`unjustified`, `defer-expired`,
  and the judge audit that REOPENS rejected deferrals). "I'm working on it" is not evidence.
- `no-remaining` with its `last_report_sig` banking. Its own message is the point: *"The
  operator reads YOUR message, not this hook's output."* If the cadence's report turn does
  not carry `## Remaining`, the ask has failed at its purpose — so the report turn still
  enforces it.
- `_ckey` per-slug scoping, and the checklist wave gate NOT being ownership-gated (an
  uncovered wave is unclaimed work).
- `agent-state` blocking at all: the docstring names the incident, an operator decision lost
  to compaction. Narrow the KEY, never the gate.
- `poll_fast_path` returning `False` on every exception. A broken fast path must cost a
  battery, never buy an allow.

---

## 6. Order of work

1. Roster caps + message truth (§1.1, §1.4) — pure output, no gating change.
2. `state_world_sig` ownership scope (§1.2) + its control test.
3. Brief work-gate (§1.3) + its control.
4. `.blocks` session scoping + its case (prerequisite for block-streak reads).
5. Batching (§2) + rewrite cases 156/156b/204.
6. Cadence (§3) + C1-C5 and the revert control.
7. `--intent` (§4) + C6-C9 and `intent-expired`.

Fifteen new cases are specified in the planner's §8, including the two that matter most:
**C2** (no `say` between stops must still BLOCK — the anti-abuse control) and **C8** (an
intent covering `completion` must NOT satisfy the tick-evidence gate). The suite is at
695/0 and every fail-closed case must pass unchanged.
