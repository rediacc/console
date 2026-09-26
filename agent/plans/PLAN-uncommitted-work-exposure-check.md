# PLAN: a Stop-hook uncommitted-work exposure check (advisory-only, session-attributed)

Status: proposed
Depends-On: no-dep -- cites only finished plans: PLAN-bgsweep-orphan-shells.md
Owner: d778be9d
Updated: 2026-09-23
Priority: P3 -- seed: Status proposed, 7 open box(es)
Concurrency: exclusive -- operator ruling 2026-09-26: every plan runs alone while the token budget is limited for the next few days
Owns: .claude/hooks/stop/*.py, .claude/agents/pr-babysitter.md

## Finding

The operator: in a marathon multi-hour session on a shared git worktree, uncommitted work has no safety net if the session crashes, a concurrent peer runs a destructive command, the machine dies, or the session simply edits for hours without ever being asked to commit. CLAUDE.md's own Session Default 1 makes "uncommitted until asked" the *deliberate* norm ("This means there is **no safety net**, and the tree usually holds work from other sessions and agents"), so any new check here must raise *awareness* of that exposure without ever nudging toward committing, stashing, or otherwise mutating the tree itself.

`STATE.md`'s staleness gate (`wl_store.agent_state_state`) is the closest existing precedent for "this artifact is aging, say so" -- but it protects a different asset (the compaction-recovery narrative) with a different resolution (rewrite the doc, an action the session is always allowed to take). Committing is explicitly the one action this repo's own default forbids a check from demanding, so the new check cannot copy STATE.md's "make it fresh again" resolution verbatim; it can only copy the *shape* (age + a world-keyed signature, HYGIENE-tier, rotated) and must supply a different, commit-free notion of "resolved."

`pr-babysitter.md`'s "snapshot" is **not reusable for this purpose**: it is a one-time `git add -A` commit, taken once at the start of a babysit run, by an agent whose explicit job at that moment is to take ownership of the whole tree and give a PR loop a clean starting point. It is a commit (which the "uncommitted until asked" default forbids a background detector from ever doing unprompted), it is a single event bound to one campaign's start line rather than a recurring watch over an accumulating session, and it presumes the entire dirty tree becomes this one agent's property -- the opposite of the attribution problem this new check exists to solve (telling one session's own risk apart from a peer's).

## What already exists (verified live, not just read)

- **STATE.md staleness** (`wl_store.agent_state_state`, `.claude/hooks/stop/wl_store.py:2336`): `AGENT_STATE_STALE_MIN = 15`, `AGENT_STATE_ADOPT_MAX_MIN = 60`. Staleness is world-keyed, not clock-keyed: age alone never stales the doc, `state_world_sig` (structural: task statuses, HEAD, this session's own item structure, peers folded into a coarse bucket) must also have moved. Verdict surfaces via `vadd("agent-state", False, ...)` -- HYGIENE tier. "Resolving" it means rewriting the doc, which the session can always do unilaterally -- the load-bearing property this new check cannot borrow, because "resolving" here would mean committing.
- **`docs_drift`** (`.claude/hooks/stop/wl_checks.py:736-756`) is the one existing detector that already faced this exact tension: it does not demand a commit when the docs were already updated but left uncommitted -- it reads "pending" in that case, distinct from "drifted," and only "drifted" ever surfaces a `vadd`. This is the repo's own prior ruling that a stop-hook check must be satisfiable by facts other than a commit; the new check leans on the same doctrine.
- **No existing per-stop call already answers "is the tree dirty."** `docs_drift` scopes its `git status --porcelain` to one path and only runs it after a drift threshold (rare, cheap); `triage_context`'s own `git status --porcelain` (`.claude/hooks/stop/wl_checks.py:1081`) is unscoped but fires only from the `--triage` CLI verb, not from the Stop battery. Live-timed on this actual tree (204 currently-dirty paths at measurement time): `git status --porcelain` 32ms, `git diff --stat` 37ms, `git rev-parse HEAD` (already paid every stop) 1.2ms. No existing Stop-path call already computes a repo-wide dirty-tree fact, so adding one is a genuinely new ~30ms cost, not a reuse -- bounded by a throttle (Design 4) rather than pretended away.
- **`triage_context`'s own docstring is a live example of the exact misattribution the operator warned about**: it calls raw `git status --porcelain` and hands it to a judge captioned "files this session already has in flight," but the call is completely unscoped by session -- verified live: `git status --porcelain` returned 204 files at a moment this planning session had performed zero writes.
- **`git stash create` is blocked from the session's own Bash tool today.** `.claude/oracles/pre-bash/block-destructive-git-restore.sh`'s `STASH_VERB` regex lists `push|save|pop|apply|drop|clear|branch|create|store` -- `create` is in the list despite `git stash create` not touching the working tree or index at all (unlike `push`/`pop`, it only writes a dangling commit object). Verified live: feeding `git stash create` to the guard produces exit 2, message pointing at "ask the operator to run it with the `!` prefix." Decisive for Design 3: this check must never instruct the session to run `git stash create` as an action item, since it cannot be carried out -- only "tell the operator" is a live option.
- **No existing per-session file-attribution mechanism.** `wl_core.transcript_tail` already parses the transcript's `tool_use` blocks and extracts tool names, but only reads a size-bounded tail and resets on every new user turn, by design -- structurally the wrong shape for "everything this session has touched since it started."
- **`state_doc` is genuinely per-session and safe to extend.** `wl_store.state_path` returns one JSON file per session id, loaded via `S.load_state` at the very top of `run_stop`, written via `S.save_state` (tempfile + `os.replace`, single writer) -- the same store `solo_grind_due` and the submodule pointer's time-boxed latch already use for exactly this kind of bookkeeping.
- **The Stop battery is not run on every literal Stop event.** `poll_fast_path` exits the whole hook silently before `state_doc`/`fold` are even loaded, on a verified no-op inbox poll. A new check placed inside the full battery is never charged on a quiet polling cadence.

## Design

### 1. Attribution: an incremental transcript cursor, not a new hook

A raw `git status --porcelain` count is repo-wide and, as shown live above, would be actively misleading if reported as the current session's own risk. Rejected alternative: a new PostToolUse recorder appending `Edit`/`Write`/`MultiEdit`/`NotebookEdit` file paths to a per-session sidecar -- requires touching `settings.json`'s collapsed table and three files kept in lockstep with it, a lot of new plumbing for a fact the Stop hook can derive more cheaply.

Chosen: an incremental cursor over this session's own transcript, read only by the Stop hook. `event.get("transcript_path")` is already passed to `run_stop` and already read for other facts. Store a byte offset in `state_doc["uc_cursor"]` and, on each full-battery stop, read only the new bytes since that offset, parsing `tool_use` blocks the same way `transcript_tail` already does but keeping `Edit`/`Write`/`MultiEdit`/`NotebookEdit` blocks' `file_path`/`notebook_path`. Union each newly-seen path into `state_doc["uc_files"]` as `{path: first_seen_epoch}` (write-once per path -- a later re-edit must never reset its exposure clock). Bounded catch-up if `uc_cursor` is absent or the transcript is shorter than the recorded offset (a new session id after compaction), capped the same way `transcript_tail` caps its own read.

The intersection, not the touched-set, is what gets reported: `uc_files` intersected with paths currently dirty per `git status` -- a file this session edited and then saw committed (by anyone) drops out of the reported risk the moment `git status` no longer lists it, with zero bookkeeping needed to notice the drop.

### 2. Why this cannot misattribute a peer's work

1. `uc_files` is populated only from blocks inside this session's own transcript file -- the harness never shares one transcript file across two sessions.
2. `state_doc` itself is per-session, the same isolation `solo_grind_due`'s latch and the submodule pointer's window already rely on.
3. The one shared read, `git status --porcelain`, works only as a membership test against paths this session already recorded from its own transcript; it never supplies new paths. A peer's unrelated dirty files can shrink or grow the denominator the advisory optionally mentions for context, but can never enter the numerator this session claims as its own exposure.
4. Nothing here ever reads or writes a peer's `agent/<peer>/` directory or STATE.md section.

### 3. What the advisory says -- and the two candidate actions ruled out

**Auto-commit: ruled out.** It is precisely the action CLAUDE.md Session Default 1 forbids a background process from taking unprompted, and a commit that fires on a timer would inevitably interleave with whatever a concurrent peer is mid-way through editing in the same shared tree.

**`git stash push` (or any mutating stash verb): ruled out**, for the same reason: it resets the working tree to HEAD, which would yank a peer's in-progress edit out from under their own next tool call.

**`git stash create`: named as operator-only information, never a session action.** It genuinely does not touch the working tree or index, so it is the one git-native mechanism that could mint a recoverable snapshot ref without committing or disturbing a peer's live edits. But it is currently blocked from this session's own Bash tool (verified live, exit 2) -- fixing that guard is out of scope for this plan (a separate, narrow finding worth filing on its own). The advisory names `git stash create` only as information for the operator, worded as advisory text, never as an instruction the session attempts.

What the advisory actually recommends, therefore, is awareness alone: it names (capped list, remainder counted, matching `plan_drift_rows`'s no-silent-caps convention) which of this session's own files are still uncommitted, how long the oldest one has sat that way, and states in the same breath that this is informational and that "uncommitted until asked" remains the default.

### 4. Trigger condition and threshold

Two independent triggers, either sufficient:

- **Age**: the oldest `first_seen_epoch` among currently-dirty, this-session-attributed files exceeds `WORKLIST_UNCOMMITTED_AGE_MIN` (proposed default 120 minutes). This check's only available resolution is operator awareness, not a session-executable fix, so nagging on a 15-minute cadence (matching `AGENT_STATE_STALE_MIN`) would be pure noise against a default the operator has explicitly asked to keep -- 120 minutes matches "marathon multi-hour session" as the point past which "still nobody has looked at this" stops being normal.
- **Volume**: the count of currently-dirty, this-session-attributed files exceeds `WORKLIST_UNCOMMITTED_COUNT_MIN` (proposed default 15, roughly matching `SOLO_GRIND_MIN_ITEMS=12`'s order of magnitude) -- catches a large, fast blast-radius change that pure age would miss.

### 5. Cost and firing cadence

- Placement: after `poll_fast_path`'s silent-exit check, so a quiet polling cadence never pays for it at all.
- Throttled `git status --porcelain` call: cache the last dirty-set and the wall-clock time in `state_doc["uc_last_check"]`/`state_doc["uc_dirty_cache"]`, only re-invoke `git status` when `WORKLIST_UNCOMMITTED_CHECK_MIN` (proposed default 10 minutes) has elapsed -- caps the new call to at most 6/hour regardless of stop frequency.
- Transcript-cursor read: bounded to new bytes since the last offset (typically a few KB).
- Tier and rotation: `vadd("uncommitted-risk", False, text)` -- HYGIENE tier, matching `agent-state`, `docs-drift`, `solo-grind`, and the sibling `bg-orphan` design in `PLAN-bgsweep-orphan-shells.md`. No custom latch needed -- the existing rotation and cadence pause already give it the right cadence.

### 6. Safety proof: this check cannot itself cause data loss

- The only git subprocess it ever invokes is `git status --porcelain` (read-only). It never invokes `add`, `commit`, `stash` (any verb), `restore`, `checkout <path>`, `clean`, or `reset`.
- The only files it ever writes are its own per-session `state_doc` -- never a tracked file, never another session's sidecar.
- The only files it ever reads beyond that are `event["transcript_path"]` (this session's own) and the repo's dirty-file listing (read-only `git status`).

## Boxes

- [ ] Add `wl_uncommitted.py` beside `wl_admit.py`/`wl_bgsweep.py`: the transcript-cursor reader (bounded catch-up per section 1), the `uc_files` union (write-once `first_seen_epoch` per path), the throttled `git status --porcelain` intersection (section 5), and the age/volume trigger evaluation (section 4).
- [ ] Add `V_UNCOMMITTED_RISK` to `worklist_messages.py`: names the count and oldest age of this-session's-own still-dirty files (capped list + remainder count), states plainly this is informational and "uncommitted until asked" remains the default, and names `git stash create` as operator-only information per section 3.
- [ ] Wire into `wl_checks.py` (after the `poll_fast_path` exit, alongside the other per-stop fact-gatherers near `docs_drift`'s call site) as `vadd("uncommitted-risk", False, ...)`, wrapped in the same `try/except Exception` every sibling detector uses.
- [ ] New env-tunable constants: `WORKLIST_UNCOMMITTED_AGE_MIN` (120), `WORKLIST_UNCOMMITTED_COUNT_MIN` (15), `WORKLIST_UNCOMMITTED_CHECK_MIN` (10).
- [ ] Test file (`test-uncommitted.py`): synthetic transcript fixtures for the cursor; a fake `git status --porcelain` intersection test proving a peer's dirty file is never reported; the age/volume trigger boundary cases; the throttle (assert via a monkeypatched/counting `subprocess.run`); and a grep-based control asserting the new module's source contains none of `add\b|commit\b|stash\s+(push|pop|apply|...)|restore\b|checkout\s+--|clean\b|reset\b` as a live-executed `git` argument.
- [ ] File, separately and out of this plan's scope, a narrow finding against `.claude/oracles/pre-bash/block-destructive-git-restore.sh`'s `STASH_VERB` regex: `git stash create` does not mutate the working tree or index and arguably should not share a blocklist entry with the mutating stash verbs.
- [ ] Run the new test file plus the full `wl_checks`/`wl_store` suite; confirm no regression.

## Critical files

- `.claude/hooks/stop/wl_checks.py` (wiring point, `vadd`, `poll_fast_path`)
- `.claude/hooks/stop/wl_store.py` (`agent_state_state` as the closest precedent, `state_path`/`load_state`/`save_state`)
- `.claude/hooks/stop/wl_core.py` (`transcript_tail`'s existing transcript-parsing idiom to extend)
- `.claude/hooks/stop/wl_uncommitted.py` (new)
- `.claude/hooks/stop/worklist_messages.py` (new `V_UNCOMMITTED_RISK`)
- `.claude/oracles/pre-bash/block-destructive-git-restore.sh` (why `git stash create` cannot be instructed to the session; separate follow-up finding)
- `.claude/agents/pr-babysitter.md` (why the snapshot mechanism is not reusable)
- `CLAUDE.md` (Session Default 1, the constraint this design is scoped inside)

Design produced by a dispatched Plan agent (2026-09-23), grounded in live experiments on this session's own real tree and the repo's own pre-bash guard rather than hypothetical claims.
