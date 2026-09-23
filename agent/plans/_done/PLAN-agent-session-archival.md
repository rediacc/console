# PLAN: Agent session archival: a deliberate verb, and a gate that only reds when someone is responsible
Status: done -- all S1-S6 boxes ticked, gate green on the real tree (1 session dir, 0 abandoned), check:ci-parity and check:ci-gate-reachability-coverage both green, 18 backlog sessions archived. Spot-checked 2026-09-22.
Owner: d778be9d
First-Seen: 2026-09-22
Updated: 2026-09-22

## Why

`agent/<session-prefix>/` holds one session's `STATE.md` (`agent/README.md:14`).
The Stop hook already computes which peer directories are ABANDONED, every stop, for free: `.claude/hooks/stop/wl_checks.py:3526-3527` calls `S.agent_peer_sections(root, session_id)` then `S.agent_state_dead(_all, session_id, projects_dir)`, and the row-rendering comment at `.claude/hooks/stop/wl_checks.py:3535` says outright: "NOT 'reap-eligible' any more: nothing prunes another session's directory, so a label promising that would be a check that cannot fire." It only labels; nothing moves anything.
`agent/README.md:72` describes the manual step ("Move the finished session directories into `archive/<label>/`... Before archiving, promote anything in RULES.md that turned out to be true of the REPO into TRAPS.md") and nobody runs it.

Measured on this tree, with the already-landed `agent_peer_sections` dedup fix in place (`.claude/rediacc_hooks/tests/test_wl_state_document.py::test_29k_a_peer_directory_carrying_two_sections_for_one_owner_is_reported_once`): 19 peer directories, 18 ABANDONED, 1 live (the current session). The 18 range from 7.2 days idle (`f4da5c2e`) to 43.9 days idle (`2fd369e0`).
`agent/archive/` last received a real entry (`0815-1`) roughly five weeks ago. The gap this plan closes is the one `agent/archive/2026-09-22-backfill/97604f47/STATE.md:49` already flagged and left unanswered: "Unanswered peer question: move `agent/2fd369e0/`, `agent/99ccf057/`, `agent/legacy/` under `agent/archive/`? Operator's call."

## The oracle: reused, not reinvented

`wl_store.agent_state_dead(sections, session_id, projects_dir, now=None)` (`.claude/hooks/stop/wl_store.py:2299`) is the ONE liveness judge in this repo. The gate calls it exactly as written, with two decisions on the two arguments a CI gate cannot fill from live event context the way the Stop hook does:

- **session_id**: pass empty string. `wl_core.same_session(a, b)` returns `bool(a) and bool(b) and (...)`, so an empty caller id can never match any real owner.
  Every section in the tree is judged uniformly, none exempted as "the caller's own."
- **projects_dir**: pass empty string, always, never `C.projects_dir(root)`. A CI runner's home directory has no `~/.claude/projects/<repo-slug>/`, so `owner_age_hours` returns None and `agent_state_dead` falls back to the section's own `ts` (the heading stamp in `STATE.md`, on disk, tracked, reproducible).
  Deterministic across a laptop session and a GitHub Actions runner, and also the correct question for archival: has anyone touched this session's own directory recently, independent of whether a transcript exists on this particular disk.

Both are pure-input decisions at the gate's own call site; `wl_store.agent_state_dead` itself is untouched.

## The oracle's import path: mirror check_tree_shape.py, not wl_planrec

`.ci/rediacc_ci/quality/tree_shape.py` already needed `wl_store` and the entry point derives it rather than copying it (`.ci/scripts/quality/check_tree_shape.py:338-353`, `_reserved()`): `paths.hooks_stop_dir(root)` then `paths.on_sys_path(hooks)` then `import wl_store`, wrapped so a missing `.claude/` is `CannotRunError` -- a loud refusal, not a silent skip.
This plan's gate does the identical hop to reach `wl_store.agent_peer_sections` and `wl_store.agent_state_dead`. No second implementation of either function is written anywhere under `.ci/`.

## The move

`agent/<session>/` -> `agent/archive/<label>/<session>/`, a whole-directory `git mv` (rename detected, full history preserved).
Confirmed against the one precedent already in the tree: `agent/archive/0815-1/97604f47/`, `agent/archive/main/97604f47/` and `agent/archive/backup-storage/97604f47/` each hold a nested `<session>/STATE.md` -- the exact shape a `git mv agent/<session> agent/archive/<label>/<session>` produces.
Going forward there is only ever ONE current directory per session, so `--move` produces exactly one archive copy.

**Label.** README (`agent/README.md:72`) gives latitude ("whatever names that work best -- historically a branch name, and branch names are still fine HERE"). Default: the branch checked out at move time (`wl_core.git_branch(root)`).
`--label <name>` overrides it, since the one-time bulk migration of the 18 pre-existing backlog directories spans branches and five weeks; that bulk pass uses an explicit synthetic label, `2026-09-22-backfill`.

**Does the old path need a stub?** Measured: grepped the tree for every `agent/[0-9a-f]{7,8}/...` reference. Result: zero citations anywhere in the tracked tree carry the `<path>:<line>` shape `check_plan_citations.py`'s `CITE_RE` or `wl_planrec.resolve`'s `RESOLVE_KINDS` (no `session` kind exists at all) would ever mechanically check.
The handful of real references found (`agent/RULES.md:53`, `agent/archive/2026-09-22-backfill/e580532b/NOTE-to-9d92d9b6.md:18`, `.ci/scripts/quality/check_guard_feature_completeness.py:11`, six `agent/8f55d4f0/W7P3-batch5-brief.md` mentions, `docs/ci-overhaul/06-progress.md:3492`) are all bare paths with no line number, so `CITE_RE` never matches them -- `check:ci-plan-citations` is structurally blind to all of them, today and after any move.
This is the opposite of the `plans/` case, where `plan:<slug>` is resolved by name and genuinely forces a stub.

More importantly, a same-named stub would be actively wrong. `wl_store.agent_peer_sections` reads `d / "STATE.md"` literally and `agent_state_parse` "NEVER RAISES, and never discards": any `STATE.md`-named file with no `## SESSION` heading is adopted as a `legacy` section stamped at the file's own `mtime`.
A three-line "Status: moved / Moved-To:" stub left at `agent/<session>/STATE.md` would therefore be read, the moment it is written, as a brand-new, zero-minutes-old legacy peer -- resurrecting the archived session back into the Stop hook's peer roster and back into this gate's own ABANDONED count, on a clock that restarts every time someone re-derives the stub.
That is a strictly worse bug than the one this plan fixes.
**Decision: leave nothing at the old path.** A plain `git mv` of the whole directory is sufficient.

## RULES.md-promotion: flagged, never gated

`agent/README.md:72`'s promotion step is about `agent/RULES.md`, a single document every session reads and sharpens in place. It is not a property of the directory being archived, and nothing can verify mechanically whether a given RULES.md line "turned out to be true of the REPO."
**Decision: `--move` prints a fixed one-line reminder to stdout before it runs** and does nothing further. Out of gate scope, in-scope as an advisory nudge, matching how `--sweep` already prints without enforcing in `check_plan_folders.py`.

## What makes the gate RED, and why it is not "any ABANDONED dir reds"

A naive "red if any ABANDONED peer directory is unarchived" reds on 18/18 directories today, on every unrelated PR, blaming whoever's branch happens to run CI next for 18 other sessions going idle -- a fact about the passage of time, not about that PR's diff.
The fix mirrors how `check_plan_folders.py`'s F1 was actually staged: spend one stage as an advisory only because a gate cannot red on arrival over an uncleared backlog, migrate the backlog to zero as this plan's own implementation step, then land the gate already fatal -- never advisory-then-flip.

Two things keep it from reproducing the 18-red-forever problem afterward:

1. **A grace period past the 24h ABANDONED threshold, not the threshold itself.** A third retention clock, `grace_days` (default 14), read from `.ci/config/agent-session-archival.json`.
   A directory is a fatal finding only once it has been ABANDONED (24h, `WORKLIST_DEAD_HOURS`) and an additional `grace_days` have passed (~15 days idle total). Long enough that ordinary session cadence (a paused session over a long weekend, a weekly `/pr-babysit` wave) clears the debt before the clock fires; short enough that it still creates real pressure.
2. **The fix is a single cheap, always-safe CLI verb**, not debt needing per-file judgment -- so this plan does NOT add a shrink-only baseline file on top of the grace period. Archiving one directory is one `git mv`; there is no partial-progress state worth tracking.

One finding, S1: "agent/<session>/ has been idle N days (last touch <timestamp>); archive it: `.ci/scripts/quality/check_agent_session_archival.py --move <session>`." Not diff-scoped, because whether a directory is overdue is a property of the tree, not of any one PR's diff.

Anti-vacuity: zero session directories enumerated at all is CANNOT RUN, not a green -- a tree that thin has no `.claude/hooks/stop` either. `agent/archive/` missing entirely is also CANNOT RUN, mirroring `check_tree_shape.py`'s refusal shape for a missing `.claude/`.

## --move's own safety rail (defending the one hard constraint)

The one hard constraint: a hook must never auto-move a peer's directory as a stop-hook side effect, because the per-directory `STATE.md` split exists precisely so no session can destroy another's document by naming its path. This plan's gate (`--check`, the default verb) is read-only -- it only calls `agent_peer_sections`/`agent_state_dead` and prints findings.
It is wired into `.ci/` only, never registered anywhere under `.claude/hooks/`, and `--check` never calls `--move` itself. `--move` is a verb a human or a session runs explicitly, by name, from a shell.

`--move`'s own guard: it refuses a target whose oracle verdict is "kept" (still live) unless `--force` is passed -- protecting the routine case while leaving the README's own same-day self-archival path open via explicit `--force`. Reserved names (`AGENT_RESERVED_DIRS`) are refused outright.

## Migration of the current 18: in this plan, not handed off

Per the F1 precedent, the backlog is cleared as this plan's own implementation step, in the same wave that lands the gate.
S4 below runs `--move --label 2026-09-22-backfill` once per directory over the measured 18 (`2fd369e0`, `99ccf057`, `97604f47`, `3fe0b2ed`, `e6500e92`, `0ad063bf`, `b7baf3ee`, `854ac1c6`, `e580532b`, `9d92d9b6`, `88e2bb0c`, `f88f9be7`, `a276391d`, `472cf53d`, `74de73ca`, `d1589e0b`, `8f55d4f0`, `f4da5c2e`), needs a quiet tree (no peer session mid-write in one of those directories), and is one commit.

## Wiring: three points, mirroring 7dd14f98f

1. `package.json`: `"check:ci-agent-session-archival": ".ci/scripts/quality/check_agent_session_archival.py"`, beside `"check:ci-plan-folders"` (`package.json:182`).
2. `scripts/ci-runner/manifest.ts`: one `GateSpec` entry, `id: 'check:ci-agent-session-archival'`, `gate: true`, `leaves: ['.ci/scripts/quality/check_agent_session_archival.py']`.
   `ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-branch', step: 'Agent session archival' }`, placed immediately after the `check:ci-plan-folders` entry (`scripts/ci-runner/manifest.ts:1962-1981`).
3. `.github/workflows/ci-quality.yml`: a step named `Agent session archival` in the `quality-branch` job, immediately after "Plan folders and retention" (`.github/workflows/ci-quality.yml:583-585`).

Run `npm run check:ci-parity` and `npm run check:ci-gate-reachability-coverage` after wiring.

## Tests

**Control-first gate selftest** (`--selftest`, mirroring `.ci/scripts/quality/check_plan_folders.py:123-249` and `check_hint_corpus.py`): pure fixtures, no git repo per control.
S1 fires on a section timestamped past `WORKLIST_DEAD_HOURS + grace_days`; does NOT fire on a section within the grace window (both boundary directions); does NOT fire on a live section; a directory already moved (absent from enumeration) produces no finding; vacuity floor for an empty session list.

**Pure-library pytest** (`.ci/rediacc_ci/tests/test_quality_agent_session_archival.py`, mirroring `test_quality_plan_lifecycle.py`): `classify_due(...)`, `label_for(branch)`, pure judgment split from impure gather, exactly as `check_tree_shape.py`'s `_reserved()` split.

**Regression proof of the resurrection bug this plan's design found and rejected**, using `wlfix`/`test_wl_state_document.py`'s style: `wl.brief_other("cafe1234")`, `wl.state_as("cafe1234", ...)`, `wl.age_state("cafe1234", ...)` past `WORKLIST_DEAD_HOURS`, delete `wl.owner_state_file("cafe1234")` (simulating the archival move, no stub), then `wl.run()` and assert `"cafe1234"` no longer appears in the `agent-peers` report row at all.
This is the one control this plan cannot skip: it is the exact failure mode a same-named stub would have reintroduced.

**--move's own tests** (bash, modelled on `check_plan_folders.py`'s `move()` coverage): refuses a reserved name; refuses a live target without `--force`; moves a genuinely ABANDONED target and leaves nothing at the old path; refuses on a dirty/mid-write tree.

## Tasks

- [x] S1 `.ci/rediacc_ci/quality/agent_session_archival.py`: pure `findings()`/`classify_due()`/`label_for()`, taking already-gathered session records as data. `.ci/config/agent-session-archival.json` with `grace_days: 14`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] S2 `.ci/scripts/quality/check_agent_session_archival.py`: `_gather()` via `paths.hooks_stop_dir` + `paths.on_sys_path` + `import wl_store`, calling `agent_peer_sections(root, "")` / `agent_state_dead(sections, "", "")`; verbs `--check` (default), `--status`, `--move <session> [--label L] [--force]`, `--selftest`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] S3 Wire the three points, run `check:ci-parity` and `check:ci-gate-reachability-coverage`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] S4 Run `--move --label 2026-09-22-backfill` once per directory over the 18 measured backlog sessions, on a quiet tree, one commit. Confirm the gate is green afterward at `grace_days=14`.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] S5 Regression test proving no STATE.md resurrection, landed alongside S4.
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites
- [x] S6 `--move` bash coverage (refuse reserved / refuse live without `--force` / move-and-leaves-nothing / refuse dirty tree).
    (ticked) 2026-09-23T11:19:16Z by d778be9d: retroactive record: closed by f5007b649 (2026-09-23) fix(ci): 6 independent ci:quick reds surfaced this session -- trail backfilled under PLAN-fix-plan-implementation-check-regression, which explains why this line post-dates the commit it cites

## Risks

1. **Grace period miscalibration.** 14 days is a judgment call. If routine housekeeping runs less often than every two weeks in practice, the gate reds on unrelated PRs again. `grace_days` lives in one config file so it can be retuned without touching code.
2. **A session that legitimately pauses longer than 14 days** gets archived by the gate's pressure even though its work is not done.
   Archiving is not destructive -- full history survives the `git mv`, nothing prevents un-archiving.
3. **S4 touching 18 directories in one commit** risks colliding with a peer session mid-write in one of them. `--move` must check the tree is quiet for that directory before moving, and refuse rather than silently racing a concurrent writer.

## Acceptance criteria

- `npm run check:ci-agent-session-archival` exists, is wired at all three points, and `check:ci-parity` / `check:ci-gate-reachability-coverage` are green.
- The gate's `--selftest` proves S1 fires and does not fire on both sides of the grace-period boundary and on a live section, using planted fixtures.
- After S4, `agent/` holds zero session directories idle past `grace_days`, and the gate is green on the real tree.
- `agent/archive/2026-09-22-backfill/<session>/` exists for all 18 measured directories, each holding the full moved content, with nothing left at the old `agent/<session>/` path.
- The Stop hook's `agent-peers` report row no longer lists any of the 18 archived sessions on the next stop (proven by the regression test in S5, not merely asserted).
- `--move` refuses a reserved name and a live (unforced) target; `--check` never writes anything, under any argument.

### Critical Files for Implementation

- `.claude/hooks/stop/wl_store.py` (the oracle: `agent_state_dead` at line 2299, `agent_peer_sections` at line 307, `AGENT_RESERVED_DIRS` at line 173, `agent_session_dirs` at line 328)
- `.claude/hooks/stop/wl_checks.py` (lines 3496-3536, the existing peer-abandonment report this plan reuses and never duplicates)
- `.ci/scripts/quality/check_plan_folders.py` (the direct structural model: gate shape, verbs, control-first selftest, `move()`)
- `.ci/scripts/quality/check_tree_shape.py` (lines 330-353, the precedent for importing `wl_store` from `.ci/` via `paths.hooks_stop_dir`/`paths.on_sys_path`)
- `agent/README.md` (lines 28-34, 72, the layout and archival contract this plan implements)
- `.claude/rediacc_hooks/tests/wlfix.py` and `.claude/rediacc_hooks/tests/test_wl_state_document.py` (the fixture harness for the resurrection-prevention regression test)
