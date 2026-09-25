# PLAN: A permanent shape for agent/ and the repo root, kept true by Python
Status: mostly-done -- 6 of 7 boxes verified done 2026-09-22 (commits 1ea0c7340, fce51e202). S6 (sweeper's first run + shadow-ledger drop) correctly stays open: time-gated (40/90-day clock, move was 2026-09-21) and dependent on PLAN-tooling-transformation.md's W1P6, which is itself unticked.
Depends-On: PLAN-tooling-transformation.md#W1P6 -- the one open box S6 waits on the umbrella's terminal box W1P6, as this plan's Status line states
First-Seen: 2026-09-21
Owner: d778be9d

## Why
The tooling transformation wants a clean tree. Two defects showed that cleanliness held only by luck. Debris files (`aa.jsonl`, `zz.jsonl`, `.events.jsonl`, `.lastevent-*.json`, `.requests`, `.local/`, `claude/`) sat untracked at the repo root, written by the old bash worklist suites, and a second reggate ledger appeared under `.claude/hooks/stop/agent/` because
`wl_reggate.debt_dir()` fell back to a cwd-relative root (fixed in c33203f5a). Separately `agent/` holds 102 `PLAN-*.md` at its root with no rule about where a plan lives or when it goes. The operator's ruling of 2026-09-21: fix the CLASS, in Python, so it stays true.

## Operator rulings (2026-09-21)
- Plans live in `agent/plans/` (active and backlog). A plan moves exactly once, at close, to `agent/plans/_done/` or `agent/plans/_removed/`, and leaves a one-line stub at its old path.
- A sweeper deletes `_done/` and `_removed/` entries 40 days after the move, and not-started backlog plans 90 days after their last touch. Expiry deletes the file and keeps a tombstone row (title, dates, git blob id of the full text) in `agent/INDEX.md`.
- The structure is enforced by Python for the class (a lifecycle module and a gate with a planted control per finding), not fixed for today's instances.

## Settled by the session, all reversible (defaults, veto welcome)
- A `parked` record stays in `agent/plans/` (active), because plan compaction keeps it on the clock.
- A tombstone is revivable: `--plan-revive` restores the file from the blob into `agent/plans/`.
- `_removed/` uses the same 40 days as `_done/`.
- The tree-shape gate lands blocking with a shrink-only baseline, never advisory.
- `agent/REPORT-*.md` is an archive-class file and moves under `agent/archive/`.
- Citations are NOT re-pointed. A stub at the old path keeps every `agent/PLAN-*.md` citation resolving (523 references in 130 files), which is the mechanism plan compaction already relies on.

## Design (from two independent Plan agents, claims spot-checked before use)

### A. Plan lifecycle
Reuse, do not duplicate:
- `.ci/scripts/quality/check_plan_boxes.py` with the ledger `.ci/config/plan-boxes.json` and the never-delete rule.
- `.ci/config/plan-lifecycle.json` (`archive_dir`, `warn_days`, `delete_days`, read by three gates).
- `.ci/rediacc_ci/quality/plan_housekeeping.py:571`, the `git log -1 --format=%cI` clock.
- `agent/INDEX.md` with `check_plan_record.py` (record table and blob ids), `.claude/hooks/stop/wl_planrec.py` and `check_plan_citations.py`.

Design:
- States: `active` and `backlog` in `agent/plans/`, decided by the `Status:` header (the FINISHED and NOT_STARTED sets in `wl_planfile.py`) and the ledger box counts; `done` in `_done/`; `removed` in `_removed/`, declared only explicitly by `Status: removed` plus a `Removed-Why:` line; `expired` means no file and a tombstone row.
- Data model: two keys added to each `plan-boxes.json` row, `folder` and `moved_at`; no second ledger.
- Clocks: the 40-day clock reads `moved_at`, cross-checked against `git log` of the new path (a mismatch over one day is a finding, so it cannot be back-dated). The 90-day clock reads the older of `First-Seen:` (carried from the pre-move `%cI`) and `%cI`, because `git log` does not follow renames and a move must not buy freshness.
- Modules: `.ci/rediacc_ci/quality/plan_lifecycle.py` (state_of, folder_for, retention_days, last_touch shared with plan_housekeeping, stub grammar, tombstone rows) and the gate `.ci/scripts/quality/check_plan_folders.py` (id `check:ci-plan-folders`) with the verbs `--status`, `--move`, `--sweep` (refuses without `--write`), `--check` and `--update`.
- Findings, each with a `plant()` control (part 1): F1 plan outside `agent/plans/**`; F2 folder disagrees with `Status:`; F3 terminal plan past 40 days; F4 backlog plan past 90 days.
- Findings, part 2: F5 stub pointing at a stub; F6 `moved_at` disagrees with git; F7 citation resolving to neither a file nor a tombstone (including inside `plan-boxes.json` and `INDEX.md`); F8 tombstone blob does not resolve; F9 vacuity floor.

### B. Tree shape
- Policy as data: `.ci/policy/tree-shape.json`, a permitted-class table (root fixed names, plan, agent-doc, session-note `agent/<8hex>/STATE.md`, the ledger classes, pr-snapshot, agent-archive, policy, baseline, hook-sidecar, and a `dead-amnesty` class to delete). Register it in both `POLICY_FILES` lists (`.ci/rediacc_ci/policy_paths.py` and `scripts/lib/policy-paths.ts`).
- Logic in `.ci/rediacc_ci/quality/tree_shape.py`, entry `.ci/scripts/quality/check_tree_shape.py`, key `check:ci-tree-shape`. It enumerates `git ls-files` plus `git ls-files --others --exclude-standard` and keeps the exit status, since a swallowed enumeration must not read as clean.
- It derives `AGENT_RESERVED_DIRS` from `.claude/hooks/stop/wl_store.py:170` instead of copying it (that set is already stale: `pr` and `legacy` are missing).
- The baseline is `.ci/config/tree-shape-baseline.json`, shrink-only, reusing the decision in `.ci/scripts/quality/check_language_policy.py:365-400`, with a `plant()` control per finding class.
- Runtime guard: a session-scoped autouse fixture in the root `conftest.py` (the only conftest all three testpaths see) that snapshots untracked files before and after the session and fails naming the last test. A gate assertion also forbids any module under `.claude/hooks/` or `.ci/rediacc_ci/` from building a repo path out of a bare relative string.
- Known cwd-relative sites to fix: `.ci/rediacc_ci/review/standing_orders_brief.py:271,273,321,329`, `.ci/rediacc_ci/private/run_account.py:154`, `.claude/hooks/stop/wl_ci.py:1074-1102` (selftest only) and `.claude/hooks/stop/wl_reggate.py:192` (a read-only git call).
- Ledgers: move only `agent/census-plan-record.jsonl` to `agent/ledgers/`. That touches `.ci/scripts/quality/check_plan_record.py:162` with its glob base and the two citations in `PLAN-tooling-transformation.md` and `PLAN-migrate-plan-doc-discovery.md`, in the same commit. `agent/worklist/` and `agent/reggate/` stay: their paths are the hook's contract.
- The 291 `.ci/shadow/*.observations.jsonl` are read by `.ci/rediacc_ci/quality/dead_python.py:93-94,270-290`. A ledger whose twin is deleted is already inert, so drop by whole file only after W1P6 deletes the twins (dead_python refuses ledgers that parse to zero records, so never truncate).
- Delete the dead `.gitignore` amnesties left by the removed bash suites (`.claude/hooks/stop/.events.jsonl`, `capfix-at/`, `capfix-over/`) and their on-disk leftovers.

## Steps
Each step is one commit, and none may land while another writer edits the same files.
- [x] S1 Lifecycle library and gate, registered, reading BOTH `agent/PLAN-*.md` and `agent/plans/**` (the old location is legal); `terminal_days: 40` and `backlog_days: 90` in `plan-lifecycle.json`; `"plans"`, `"pr"` and `"legacy"` in `AGENT_RESERVED_DIRS`. Green on today's tree.
    (ticked) 2026-09-22T19:53:54Z by d778be9d: commit 1ea0c7340: plan_lifecycle.py + check_plan_folders.py landed. plan-lifecycle.json: terminal_days=40, backlog_days=90. AGENT_RESERVED_DIRS at .claude/hooks/stop/wl_store.py:173-175 includes plans/pr/legacy
- [x] S2 Every reader dual-path: `.claude/hooks/stop/wl_store.py:210 agent_plan_dir` (the choke point), `.claude/hooks/stop/wl_checks.py:801`, `.claude/hooks/stop/wl_planindex.py:86`, `.ci/scripts/quality/check_plan_boxes.py:109,379,384`, `plan_housekeeping.py`, `PLAN_REF_RE` in `.claude/hooks/stop/wl_planrec.py:206`, the `check-plan-housekeeping` twin, `skip-plan-reconcile.cjs`, `agent/README.md` and `CLAUDE.md`.
    (ticked) 2026-09-22T19:53:54Z by d778be9d: .claude/hooks/stop/wl_store.py:236 agent_plan_dirs + AGENT_PLAN_SUBDIRS; .claude/hooks/stop/wl_planindex.py:91-96; .ci/scripts/quality/check_plan_boxes.py:112,213,397 is_plan_path; plan_housekeeping.py reads plan_globs; .claude/hooks/stop/wl_planrec.py:206 PLAN_REF_RE; agent/README.md:31 and CLAUDE.md:37 both canonical
- [x] S2b A move without the glob change trips the `MIN_PLAN_FILES` vacuity floor, so the migration cannot fail green.
    (ticked) 2026-09-22T19:53:55Z by d778be9d: MIN_PLAN_FILES floor=20 in .ci/scripts/quality/check_plan_boxes.py:112 and .ci/rediacc_ci/quality/plan_lifecycle.py:92; F9 planted-control test at .ci/rediacc_ci/tests/test_quality_plan_lifecycle.py:298-312 and .ci/scripts/quality/check_plan_folders.py:272-288
- [x] S3 Tree-shape policy, module, gate and baseline over today's tree; the root conftest fixture; the cwd-relative fixes; the dead amnesties removed.
    (ticked) 2026-09-22T19:53:55Z by d778be9d: commit 1ea0c7340: tree-shape.json, tree_shape.py, check_tree_shape.py landed. conftest.py:124-137 autouse fixture; .ci/rediacc_ci/review/standing_orders_brief.py:127-135 cwd-relative fix
- [x] S4 The move: 102 `git mv` plus stubs plus `First-Seen:` headers, then one `check:ci-plan-boxes --update` and one `check:ci-plan-record --update`. Confirm the archive append-only rule does not claim the rename, that `_archived()` does not start matching by basename across trees, and that the floors count the recursive corpus. Needs a quiet tree.
    (ticked) 2026-09-22T19:53:55Z by d778be9d: commit fce51e202: 103 plans moved into agent/plans/, census ledger and reports follow. agent/plans/ now holds 114 files, 0 flat agent/PLAN-*.md remain at commit time
- [x] S5 Flip the gate so the old location is fatal; move `census-plan-record.jsonl` to `agent/ledgers/`; move `agent/REPORT-*.md` under `agent/archive/`; regenerate.
    (ticked) 2026-09-22T19:53:55Z by d778be9d: .ci/scripts/quality/check_plan_folders.py:20 confirms F1 fatal since migration landed; agent/ledgers/census-plan-record.jsonl exists; agent/archive/REPORT-licensing-bigbang-2026-08-04.md exists, 0 agent/REPORT-*.md remain at root
- [ ] S6 The sweeper's first run (`--sweep --write`) once a plan has aged, and the shadow-ledger drops after W1P6.

## Risks and first tests
1. The move resets every `%cI` clock (git log does not follow renames), silently disarming plan-housekeeping for 33 days and the 90-day sweeper for 90. Test first; the mitigation is `First-Seen:` and reading the older date.
2. Stop-hook cost: `wl_planindex` exists because opening 83 plans was slow, so the recursive glob over four folders must keep the stat-only fast path.
3. `_done/` plans leave the box corpus, so the `MIN_PLAN_FILES` and `MIN_OPEN_BOXES` floors must count the recursive corpus.
