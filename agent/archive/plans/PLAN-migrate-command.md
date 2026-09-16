# PLAN: /migrate and a git-tracked worklist store

Status: draft
Owner: d1589e0b
Updated: 2026-09-04

Scope: move the worklist event log into git under `agent/worklist/` so open work travels with push/pull; add `/migrate`, a user-invocable skill that lists candidate sessions, asks WHICH to continue (multi-select, never assumed), and re-tags their remaining items to the current session; and teach the Stop hook to surface a dead-or-remote predecessor's open items on every stop, in the PostCompact briefing and at SessionStart so a compaction summary carries them. Every load-bearing claim below carries a `file:line` that was read, and section 0 was measured on this machine rather than recalled.

The operator's four decisions (store into git; re-tag with the old items ticked "migrated to"; automatic Stop-hook fold-in; scope = `[ ]`, `[>]` with leases reset, `[?]` with windows preserved, STATE.md Next action, predecessor brief marked handed off; NOT requests or round logs) are taken as given and are not re-argued here.

## 0. What is actually there (measured 2026-09-04)

**Where the store lives and how big it is.** `worklist.py --path` prints `/tmp/claude-worklist/home_developer_console.md` (`wl_core.worklist_for`, `.claude/hooks/stop/wl_core.py:482-495`: TMPDIR + a slug of the repo root). That `.md` inbox file **does not exist** on this machine; the store is entirely `home_developer_console.events.jsonl`: **501,266 bytes, 776 events**, first stamp `2026-08-31T12:55:45Z`, kinds `state 274, add 216, update 150, lease 99, tomb 32, triage 3, lineage 1, md 1`, writers `74de73ca 331, a276391d 241, f88f9be7 187, judge 5, 472cf53d 5, d1589e0b 5`. The five largest events are `state` ticks of ~3 KB (evidence prose). The directory holds ~90 sidecars totalling 1.7 MB. The fold gives **184 live items, 181 done**; the only open work is `472cf53d` 1x`[>]` and `d1589e0b` 2x`[>]`. One lineage edge exists (`a276391d -> 74de73ca` via `continued-in`). The CLAUDE.md "~550 KB" figure (`CLAUDE.md:110`) is accurate to within 10%.

**What `compact()` keeps.** `wl_store.compact` (`.claude/hooks/stop/wl_store.py:1449-1592`) re-emits exactly four kinds: one `md` event with every md-origin item (1505-1510), every `lineage` edge verbatim (1520-1534), one `add` per CLI item carrying `bt/ln/upd/tr/ju` (1556-1575), and a `lease` where `until`/`worker` are set (1576-1586). It **drops** `state`, `update`, `unlease`, `reassign`, `triage` and `tomb` records; their effect survives only through the folded fields (`s`, `o`, `t`, `ln`). The pr-epics warning ("folds the log to md/add/lease, a novel event kind is destroyed", `.claude/skills/pr-epics/SKILL.md:35-37`) is correct except that `lineage` has been carried since 2026-09-03. Consequence for this plan: **any new linkage must ride the `add` event as a field compact carries, never as a novel event kind.**

**How the Stop hook derives "others".** `wl_store.classify_items` (`wl_store.py:1302-1331`) buckets every not-mine `[ ]` and `[>]` item into `others[owner]`; `[?]` items of other owners are dropped entirely (1314 requires `mine`). `run_stop` renders them through `other_sessions_note()` (`wl_checks.py:2901-2906`) and queues that text as the `others-items` allow-report section only when nothing of mine is open (`wl_checks.py:5966-5976`). Block-path verdicts are composed purely from `violations` (`wl_checks.py:5256-5262`, `5386`). So today a dead predecessor's work is a priority-2 note that appears only on clean stops and never mentions `[?]` items.

**Is `agent/` tracked?** Fully: no ignore rule exists on purpose (`.gitignore:150-157`), STATE.md files are committed per session (`646298a95 state(d1589e0b): ...`), CI cost is a zero-job module (`.ci/scripts/ci/scope-map.cjs:47-60,193`). Two things a new tracked directory would trip: `wl_store.agent_session_dirs` counts **every** non-reserved directory under `agent/` as a session (`wl_store.py:281`, `371-386`), and the sidecar gate parses `wl_store.py`'s docstring list (`wl_store.py:36-60`, `.ci/scripts/quality/check-tracked-sidecars.sh:44-60`) but scopes `git ls-files` to `.claude/hooks/stop` only (`HOOK_DIR`, line 33), so a tracked file under `agent/` is outside its view. The plan gates glob `agent/PLAN-*.md` only (`check-plan-housekeeping.sh:142`, `check_plan_boxes.py`).

**Liveness artifacts that exist today.** `.lastevent-<sid8>.json` is written at exactly one place per full stop (`wl_checks.py:3050-3054`); `phantom_identities` reads its absence as "never stopped" (2221-2227) and declares itself blind when none exist (2248-2254). `.sessions` briefs age against `SESSION_BRIEF_STALE_MIN=90` (`wl_store.py:110`, `sole_live_session` 1659-1672). Transcript mtime via `owner_age_hours` (1337-1348) returns `None` for an owner with no local transcript, which `cleanup_dead_sessions` treats as "never tombstone" (1372). STATE.md sections carry a heading stamp (`agent_state_parse` 1811-1854) and `agent_state_dead` already names "a session whose transcripts live on another machine" as the case that falls back to the section's own stamp (1885-1908). `--reassign` refuses any prefix with a `.lastevent` (`worklist.py:858-859`) and one younger than `PHANTOM_MIN` (885-886). `--adopt` is evidence-gated with no `--force` (`worklist.py:750-819`, `wl_lineage.py:27-35`).

**The case this plan exists for is live in the tree.** `agent/d1589e0b/STATE.md` says: "continuation of 472cf53d after a harness restart ... #6f84d8d8 is the pre-restart twin, tagged 472cf53d, adopt refused". A restart leaves no `compact_boundary`, so `--adopt` correctly cannot prove it, and today the only door is the operator typing `WORKLIST_SESSION_ID`.

**AskUserQuestion contract.** No repo skill uses it; the in-repo command `.claude/commands/ask.md:51-63` batches at most 4 per call and puts the recommended option first. The installed plugin reference (`~/.claude/plugins/marketplaces/claude-plugins-official/plugins/plugin-dev/skills/command-development/references/interactive-commands.md:34-66`) gives the shape: `questions[]` of `{question, header (<=12 chars), multiSelect, options[{label, description}]}`, 2-4 options per question, 1-4 questions per call, "Other" always offered. The repo's PreToolUse guard for AskUserQuestion (`.claude/hooks/pre-ask/block-settled-questions.sh`) reads only `question` and `header` text (jq at lines 68-73) and refuses a permission-shaped phrase combined with a git-object word (`PERMISSION`/`OBJECT` regexes, lines 76-77). Option descriptions are not examined.

**Skill file shape.** Frontmatter `name`, `description`, `user-invocable`, `self-improving` (`.claude/skills/ci-watch/SKILL.md:1-6`). Every existing repo skill is `user-invocable: false`; `/migrate` will be the first `true`.

**Identity.** Every `<me>`-taking verb passes `_identity_or_die` (`worklist.py:235-256`, `wl_core.check_me` 293-349); `18-identity.sh` derives the verb table from the dispatcher and reds on an uncovered verb (`worklist-cases/18-identity.sh:322-348`, exemptions 462-500). Stamps are `%Y-%m-%dT%H:%M:%SZ` (`wl_core.py:89-90`), so lexical order is chronological. The fold is a single chronological pass, later wins (`wl_store.py:863-874`); unknown event kinds fall through untouched (no arm matches, 1032 is inside the last `elif`).

## 1. The tracked store

### 1.1 Layout

    agent/worklist/
      README.md                 ten lines: what this is, never hand-edit, how to resolve a conflict
      <writer8>.jsonl           ONE append-only file per WRITER identity (agent_session_slug, wl_store.py:284-294)
      _shared.jsonl             events with no resolvable session identity (md sync, a judge write with no session in scope)
      _import-<hosthash>.jsonl  the one-shot snapshot of this host's TMPDIR log (section 1.6)

Per-writer files, not one file, and not `agent/<session>/`. One file conflicts on every concurrent append from two branches (both sides append at EOF); per-writer files never conflict because a session id exists in exactly one harness process, so each file has exactly one appender. `agent/<session>/worklist.jsonl` was rejected because (a) the session directory is deliberately never auto-created (`worklist.py:1062-1069`) while the store must accept a `--add` before any STATE.md exists, and (b) `agent/README.md` says finished session directories are moved into `archive/<label>/`, which `agent_session_dirs` excludes (`wl_store.py:281`), so archiving a session would silently drop its items from the fold.

`worklist` is added to `AGENT_RESERVED_DIRS` (`wl_store.py:281`) so it is never listed as a peer session. The directory is created by the tool (`mkdir -p`), which does not contradict the never-auto-create decision: that decision is about a session's notes, and this is a machine artifact directory with a reserved name.

### 1.2 What changes in `wl_store`, and what does not

`worklist_for()` and the TMPDIR handle are **unchanged**. About forty sidecars derive from it by `with_suffix` (`.state-*`, `.lastevent-*`, `.reggate-*`, `.sessions`, `.requests`, judge caches, `.agentstate.*`; docstring `wl_store.py:36-45`), and all of them are per-machine runtime state that must stay out of git. Only the event LOG moves.

- `store_dir()` = `$WORKLIST_STORE_DIR` or `<project_root>/agent/worklist`. Root comes from `C.project_root(C.project_start())` (`wl_core.py:437-479`), the same ladder the CLI and the hook already share; test fixtures pin `CLAUDE_PROJECT_DIR`, so their store lands under `$BASE/proj/agent/worklist`.
- `writer_path(writer)` = `store_dir()/<agent_session_slug(writer)>.jsonl`.
- `append_events(worklist, payloads, writer=None)`: writer = the explicit argument, else the first payload's `by` when it matches `PREFIX_RE` and is not in `{"compact","unknown","md","judge","import"}`, else `C.resolve_session_id()[:8]`, else `_shared`. The lock is unchanged: the TMPDIR `.events.lock` (`wl_store.py:256`, `_append_lines` 737-750). One machine, N sessions, one flock. The md-sync raw write inside `load()` (1133-1140) routes through the same function under the already-held lock (same reason as the comment at 1131-1132). The judge's reopen write (`wl_checks.py:5758-5762`, `by="judge"`) passes `writer=me8` explicitly so it lands in the stopping session's file rather than `_shared`.
- `_read_events(worklist)`: read every `*.jsonl` in `store_dir()` in name order, PLUS the legacy TMPDIR `events_path(worklist)` while it still exists (section 1.6), concatenate, **stable-sort by `at`** (missing `at` sorts first), then fold. The sort is what makes a union of two files, or a conflict resolved by keeping both sides, a valid store: a snapshot `add` stamped with the item's `first` always precedes the ticks that follow it. Torn or garbage lines are skipped as today (759-775).
- `append_events` stamps two fields on every payload that lacks them: `h` = sha1(hostname)[:8] (this host: `29c1bbae`) and `br` = `C.git_branch(root)` (`wl_core.py:520-562`, cached once per process because it is a subprocess). The fold records `rec["host"]`, `rec["branch"]` from `add` and `rec["last_host"]` from the newest event; `compact` carries `br`/`h` on the `add`. Hostnames are hashed, not stored, because the file is tracked.
- Every hook and CLI consumer already goes through `load()`/`_read_events`/`append_events`, so `wl_checks`, `wl_report`, `wl_wait`, `wl_requests`, `wl_epic` need no edit for the move. Two direct readers of the file must change: `wl_checks.phantom_identities` reads `S.events_path(worklist)` bytes (`wl_checks.py:2258`) and becomes `S._read_events`; `worklist.py:876` already uses `_read_events`.
- The `wl_store` docstring sidecar list (36-45) is amended to say the LOG is tracked at `agent/worklist/` while `.events.lock` stays; the parenthesised shape the gate parses is preserved (comment at 57-58).

### 1.3 Concurrency

- Same machine, same checkout, N sessions: one appender per file, one flock, lock-free readers, torn tail tolerated. Identical to today.
- Two worktrees of one repo on one machine: the store is per CHECKOUT (it lives in the tree), exactly as the TMPDIR slug made it per root path before (`wl_core.py:493-494`). Work crosses worktrees only through git, which is the operator's stated intent.
- Two machines: disjoint writer files; git merges add/add of different paths cleanly. The shared-write paths are exactly two, `_shared.jsonl` (rare by construction) and compaction (gated below), and the resolution rule for any conflict in `agent/worklist/*.jsonl` is **keep both sides, delete the markers**: the sorted fold makes the union correct. `worklist.py --doctor` (section 1.5) makes leftover markers loud, because `_read_events` would otherwise skip them silently (772).
- Clock skew between machines only matters when two writers touch one item, which after this plan is `migrate`, `tomb` and `reassign`. A migration's `state x` sorted before a straggling `update` from a revived predecessor stays `x` (an `update` never changes state, `wl_store.py:983-989`); a straggling `lease` would flip it to `[>]` (991) and the liveness ladder would then report it. Named, not fixed.

### 1.4 Compaction, size and history

`--compact` keeps the md tombstone half unchanged (1460-1487) and rewrites per-writer files under one rule: **you may rewrite only what nobody else can still append to** -- the caller's own file, and files whose writer is not live (section 3's `session_liveness`, verdict `idle` or `remote` with newest event older than `WORKLIST_DEAD_HOURS`, 24h, `wl_store.py:1356`). A live peer's file is never touched, and the command prints per file `rewritten` or `skipped: live (brief 12m old)`. Rewritten files get the same minimal set as today (1505-1586) plus `mg`, `br`, `h`, and `[x]` items whose `upd` is older than `WORKLIST_ARCHIVE_HOURS` (168h, 1357) are **dropped** from the rewrite unless `--keep-done` is passed. This is a behaviour change: today compact keeps done items forever. Git history is the archive; the commit diff shows exactly what left.

Size: measured 125 KB/day across six sessions. Git stores deltas and packs them, so the working file's size, not the history, is what a fresh clone pays on every read; compaction of dead writers bounds it. With 181 of 184 items done here, a compaction would shrink this store by roughly the accumulated tick prose (the 3 KB `state` notes are the dominant bytes).

### 1.5 New identity-free verbs

- `--store`: self-contained twin of `--path` (same reason `_local_worklist_path` exists, `worklist.py:206-220`): prints `store_dir()` with every sibling broken.
- `--import-tmp`: section 1.6.
- `--doctor`: parses every store file, reports unparseable lines, `<<<<<<<`/`=======`/`>>>>>>>` markers with `file:line`, duplicate `add` ids across files (allowed, but named), and secret-shaped strings (section 7); exit 1 on any finding. Also run as a CI gate over `agent/worklist/` (task list), registered per the `testing` skill's conventions.
- All three go into `NO_ME` in `18-identity.sh` (462-500) with the same one-line justification shape as `--path`/`--compact`.

### 1.6 Migration path from the TMPDIR store

Gap-free by construction: **the reader unions the legacy TMPDIR log while it exists; the writer never appends to it again.** From the first run of the new code every open item in `/tmp/claude-worklist/home_developer_console.events.jsonl` still blocks, and every new event lands in `agent/worklist/<me8>.jsonl`.

`worklist.py --import-tmp` (identity-free, operator- or session-run once per host): fold the legacy log with `sync=False` (the same self-deadlock reason as `compact`, 1495-1501), write the minimal set as `agent/worklist/_import-<hosthash>.jsonl` with `by="import"` (lineage edges included, 1520-1534), rename the legacy file to `.events.jsonl.imported-<stamp>` so the union stops reading it, print `imported N item(s), M lineage edge(s) from <path>; commit agent/worklist/_import-<hosthash>.jsonl`. Refuses when the snapshot for this host already exists (idempotent; `--again` overrides and names the existing file). A second machine with its own TMPDIR log produces `_import-<otherhash>.jsonl`; the two cannot collide. After import, TMPDIR holds only locks, sidecars and the md inbox; the events file is retired, not a cache.

`load()` prints one stderr line while a legacy file is still being unioned (`legacy TMPDIR log still read; run worklist.py --import-tmp`) so the state cannot persist unnoticed.

### 1.7 Commit discipline for the store

Each session commits its own `agent/worklist/<me8>.jsonl` with its STATE.md commit (the `state(<me>): ...` shape already in use). A new advisory `N_STORE_UNCOMMITTED` (priority 2, `outq_add` with `refresh_min=60`, `wl_checks.py:1705-1707`) fires when the session's own writer file differs from HEAD and its newest event is older than 60 minutes: the machine-switch case is lost entirely if the file is never pushed, and the docs-drift "pending" note (`wl_checks.py:2064-2069`) is the precedent for saying so. Never `git add -A` (blocked already); name the path.

## 2. Liveness, defined from artifacts

`wl_store.session_liveness(worklist, prefix, projects_dir, events)` returns `(verdict, evidence)`, one definition shared by `/migrate`'s refusal, the Stop fold-in and `--compact`:

- `live` when ANY local artifact is fresh: `.lastevent-<p>.json` mtime younger than `LIVE_MIN` (default `PHANTOM_MIN`, 30, `wl_checks.py:2204`); a `.sessions` brief younger than `SESSION_BRIEF_STALE_MIN` (the existing oracle, `wl_store.py:1659-1672`); a transcript newer than `LIVE_MIN` (`owner_age_hours`, 1337-1348); or the newest store event by `p` younger than `LIVE_MIN` with `h` equal to this host. Evidence names the artifact and its age (`.lastevent-472cf53d.json written 4 min ago`).
- `idle`: local artifacts exist, all older than `LIVE_MIN`.
- `remote`: no local artifact for `p` at all and the newest event carries a foreign `h`. Cannot be verified from here, and the plan does not pretend otherwise: a remote session is migratable, the AskUserQuestion is the safeguard, and the option text says `last seen 2m ago on another host; may still be running`.
- `unknown`: no events by `p` anywhere; nothing to migrate.

Same-session and lineage aliases (`fold.aliases_of`, `wl_store.py:1049-1073`) are excluded before liveness is asked: they are already mine and `--adopt` is the verb that proved it. Heuristics (same cwd, same branch, adjacency) rank the candidate list in section 4; they never move an item, which is the line `wl_lineage.py:27-35` draws.

## 3. `--migrate` and the re-tag event shape

### 3.1 The verb

    worklist.py --migrate <me> --candidates [--json] [--all]
    worklist.py --migrate <me> <prev> [<prev>...]

`<me>` passes `_identity_or_die` like every other verb and additionally REQUIRES a resolvable identity (`C.resolve_session_id()` non-empty): re-tagging work onto an unverifiable `<me>` would manufacture a phantom, which is the incident `check_me` exists for (`wl_core.py:293-306`).

`--candidates`: every owner in the fold (plus its lineage aliases) with at least one un-migrated `[ ]`, `[>]` or `[?]` item, excluding me and my aliases, excluding `live` verdicts, excluding owners already marked handed off (below) unless `--all`. Per row: prefix, verdict + evidence, counts `{open, inflight, deferred}`, newest-event age, branch (`br` of the newest event), host hash with `this machine`/`another host`, a one-line brief (newest tracked `brief` event by that owner, else the first step under `## Next action` in `agent/<p>/STATE.md` via `agent_next_lead`, `wl_store.py:1756-1771`, else `(no brief)`), and `requests: N open (not moved)`. Ranked: same branch as mine first, then this host, then newest. `--json` prints the same rows as one JSON array for the skill.

`--migrate <me> <prev>` refuses (exit 2, nothing written) when: `prev` is me or an alias ("already yours; --adopt proved it"); `session_liveness` is `live` (the message names the artifact and its age, then says how the same rule can be re-checked, the way `CLI_REASSIGN_ALIVE` does, `worklist_messages.py:753-759`); no events by `prev` exist; or `<me>` is unverifiable. Otherwise it moves, per item, in one `append_events` batch:

    add    {ev:"add", id:<new>, at:<now>, by:<me>, s:" " or "?", o:<me>,
            t:<old text, full accumulation>, bt:<old basetext>,
            ln:"migrated from #<old> (<prev>)" + optional ": <old lastnote>"[:200],
            ju:<old just>, tr:<old triage>,            # when present, as compact carries them
            upd:<old upd>,                             # ONLY for [?]: the DEFAULT window is preserved
            mg:{from:<old id>, o:<prev>, first:<old first>, was:<old state>,
                worker:<old worker or "">, until:<old until or "">},
            br, h}
    state  {ev:"state", id:<old>, at:<now>, by:<me>, s:"x",
            note:"migrated to #<new> (<me>) by /migrate", mg:{to:<new>}}

- `[>]` becomes `[ ]` with the worker and lease recorded in `mg` and named in the note ("lease on worker:<w> reset by migration; the worker lived in session <prev>"). Never re-leased: decision 4 says the worker is dead.
- `[?]` keeps `s:"?"`, its `DEFAULT:`/`WHY:`/`HOW:` tokens (they are in `t`, which is what the audit re-parses, `deferral_justification` 1275-1284) and its `upd`, so `guided_slice`'s window arithmetic (`wl_checks.py:1968-1983`) reads the same minutes-left as before.
- Items owned by an alias of `prev` (proven lineage) migrate with it.
- The `state x` on a peer-owned item is written by the store function, not the CLI tick path, so the tick evidence gate (`worklist.py:518-527`) and the ownership refusal (510-514) are bypassed on purpose, with the liveness gate and the operator's selection as the substitute. `wl_reggate.mine_tick_ids` counts `[x]` lines owned by ME (`wl_reggate.py:113-119`); the old item stays owned by `prev`, so a migration never reads as a fix I must prove.
- One more event: `{ev:"brief", by:<me>, about:<prev>, at, t:"handed off to <me>"}`. `brief` is a new kind, ignored by the fold (unknown kinds fall through) and read by `--candidates` and the Stop fold-in as the handed-off mark. `compact` carries the newest `brief` per `(by, about)`. `--brief` (self-contained, `worklist.py:1513-1563`) gains a best-effort raw append of the same kind with `about` empty, after the `.sessions` write, so a fresh machine has one-line briefs at all; it never fails the brief channel.
- After writing, the verb prints: what moved (`#old -> #new` per line with state), what it refused (`[?]` without DEFAULT: still moved but flagged, requests not moved with the count), and `HANDED OFF NEXT ACTION from <prev> (agent/<prev>/STATE.md, stamped <ts>)` followed by that section's text capped at 1500 chars. The predecessor's STATE.md is **not** edited: `agent/README.md` makes a peer's document read-only by construction and the PreToolUse guard denies direct writes anyway; the handed-off mark lives in the store.
- Idempotent: the un-migrated set is computed from `mg.from` over live items (an old item is migrated iff some live item's `mg.from` equals its id), never from note text. A second run prints `nothing left to migrate from <prev> (3 already: #a->#b, ...)`, exit 0, appends nothing.

### 3.2 Fold and display

- `_fold_events` reads `mg` from `add` into `rec["mg"]` and `mg.to` from `state` into `rec["migrated_to"]`; `compact` carries both on the `add` (`mg`, `mt`).
- `--list --open` / the guided slice need no renderer change: `brief_text` already shows `LATEST: migrated from #old (prev)` (`wl_store.py:827-847`). The full `--list` bracket (`worklist.py:473-482`) gains `from:#old` / `to:#new`.
- The Remaining check is unaffected: new items are mine and enter `remaining_lines` as ordinary `[ ]`/`[?]` (`wl_checks.py:3094-3099`); old items are `[x]` and vanish from `classify_items`. Nothing about migrated items is exempted, which is the point of re-tagging rather than aliasing.

## 4. The Stop-hook fold-in

Where: `run_stop`, immediately after `classify_items` (`wl_checks.py:2878-2880`), a new `handoff_candidates(worklist, fold, session_id, projects_dir)` that walks `fold.items` for not-mine `[ ]`/`[>]`/`[?]` (so it sees the `[?]` that `others` drops, 1314), groups by owner, applies `session_liveness`, drops `live` owners (they stay in the existing `others-items` note), drops handed-off owners, and ranks same-branch, same-host, newest. It returns at most 6 owners with at most 3 brief lines each.

What it emits, verbatim shape (new `M.N_HANDOFF_CANDIDATES` in `worklist_messages.py`):

    HANDOFF CANDIDATES (not yours, never blocking): 1 session with open work and no live process here
      472cf53d  1 item ([>] 1)  last seen 41m ago on this machine  branch 0903-1
          - [>] #6f84d8d8 pr-babysit 0903-1 ...  LATEST: ...
      To continue one or more of them: /migrate  (it lists them and asks which; nothing is moved unasked)
      Until then list them under '## Remaining' as "inherited from <prefix>, unclaimed" so a compaction summary carries them.

Where it lands, three seams:
1. Allow path: `outq_add(key="handoff", prio=1, refresh_min=60, on_change=True)` beside `others-items` (`wl_checks.py:5966-5976`), so an unchanged candidate set is absorbed and a changed one re-fires. It is emitted whether or not I have open items of my own (the current note fires only when I have none).
2. PostCompact: appended to the briefing in `handle_post_compact` after the plans block (`wl_checks.py:2164-2175` pattern). This is the strongest carrier: the compacted session reads it as `additionalContext`.
3. SessionStart with `source != compact`: a fourth independent block in `handle_session_start` (`wl_checks.py:2073-2084` pattern). This is the fresh-machine moment.

`CLAUDE.md:160-167` gains admissible shape (e): "inherited from `<prefix>`, unclaimed; `/migrate` to continue". The Remaining scan demands state words only for task ids (`wl_checks.py:4808-4820`) and `no-remaining` keys on my own `remaining_lines` (5029-5040), so an inherited line is never demanded and never mis-scored.

How it avoids claiming a live peer: it never writes; a `live` verdict removes the owner from the block entirely; and the only path that moves an item is the operator's selection in `/migrate`. The ranking heuristics choose display order, nothing else.

## 5. The `/migrate` skill

`.claude/skills/migrate/SKILL.md`, frontmatter `name: migrate`, `user-invocable: true`, `self-improving: false`, `description: Continue another session's remaining worklist items in this session: lists candidate sessions with open work, asks WHICH to continue (multi-select), re-tags their open/in-flight/deferred items to this session and hands you the predecessor's next action. Use after a harness restart, a machine switch, or when the Stop hook prints HANDOFF CANDIDATES.`

Steps the skill body prescribes, in order, with the exact commands:

1. `ME="${CLAUDE_CODE_SESSION_ID:0:8}"; python3 .claude/hooks/stop/worklist.py --migrate "$ME" --candidates --json`. If the array is empty, say `No session has un-migrated open work that is not demonstrably live here.` and stop; the guarded case is that this is a valid, common outcome (`ask.md:48-49`). If a legacy TMPDIR log is still unioned, run `--import-tmp` first and say so.
2. One `AskUserQuestion` call. `header: "Continue"`, `multiSelect: true`, question text exactly: `Which sessions should this session (<me>) continue? Their open, in-flight and deferred items will be re-tagged to <me>; the originals are ticked "migrated to", nothing is deleted, and requests are not moved.` One option per candidate, at most 4 per question and 4 questions per call (16 candidates; more than that pages by newest first and says how many remain). Label `<prefix> (<branch>) <n> open`; description carries the consequence: verdict + evidence, age, host, brief, counts. No option is pre-selected or recommended, because "never assumes" is the operator's requirement. The question text contains no `should I / do you want / want me to` shape, so the pre-ask guard (`block-settled-questions.sh:76-77`) cannot match even though descriptions mention branches; the control in section 6 pins that. An "Other" answer is parsed as prefixes and re-validated against the listed candidates; anything not listed is refused with the reason (live, self, unknown).
3. For each selected prefix, in the order given: `python3 .claude/hooks/stop/worklist.py --migrate "$ME" <prefix>`. Print each verb's output unedited: it is the "what moved and what it refused" report.
4. Fold the printed `HANDED OFF NEXT ACTION` into this session's own STATE.md body under `## Next action` (first step must be work, not a wait: `agent_state_shape`, `wl_store.py:1740-1753`) and write it with `worklist.py --state "$ME"` on stdin. Then `worklist.py --list --open "$ME"` and continue the work; the Stop hook now blocks on it.
5. Commit `agent/worklist/<me8>.jsonl` and `agent/<me8>/STATE.md` by name, so the migration travels.

Safety properties stated in the skill: safe to run twice (idempotent verb); never migrates a locally live session (verb refuses); works on a fresh machine with only git content (the candidate list needs only the store; the phantom check's blindness message is expected there and harmless).

## 6. Controls

New case file `worklist-cases/26-migrate.sh`, registered in `CASE_FILES` (`test-worklist-v5.sh`, the runner reds on an unlisted file). Each control names its planted defect and reds against it; each has a control-on-the-control where the pass could otherwise be vacuous (the lesson recorded in `PLAN-worklist-ownership-continuity.md:200-204`).

1. **Store split.** `--add` lands in `$BASE/proj/agent/worklist/deadbeef.jsonl` and `$WL.events.jsonl` is not created. Planted: append target left at TMPDIR.
2. **Per-writer isolation.** `as_peer cafe1234 --add` writes `cafe1234.jsonl`; `deadbeef.jsonl` is byte-identical before and after. Planted: writer derived from the process id instead of `by`.
3. **Union + sort.** Two files whose name order is the reverse of their time order (`zz.jsonl` holds the `add` at T1, `aa.jsonl` the `state x` at T2): the fold must read `[x]`. Planted: concatenation without the stable sort reads `[ ]`.
4. **Gap-free legacy union.** Tracked store empty, `$WL.events.jsonl` holds an open item: the Stop BLOCKS; after `--import-tmp` the snapshot `_import-*.jsonl` exists, the legacy file is renamed, the Stop still blocks, a second `--import-tmp` refuses. Planted: reader ignores the legacy file, so the pre-import stop allows.
5. **Compaction never rewrites a live peer.** `brief_other cafe1234` (fresh) plus events by cafe1234; `--compact` leaves `cafe1234.jsonl` byte-identical and prints `skipped: live`; a writer whose newest `at` is 25h old (`WORKLIST_DEAD_HOURS` fixture) is rewritten and its 8-day-old `[x]` items are gone; `mg`, `ju`, `tr`, `br`, `h` and the lineage edge survive. Planted: the liveness gate removed; the `mg` carry removed (an item migrated then compacted loses `from:`).
6. **`--migrate` FIRE.** Predecessor `mig-prev` (dead: no artifacts, events aged 2h) owns `[ ]`, `[>]` (fresh lease, `worker:x`) and `[?]` with DEFAULT/WHY/HOW and `upd` 100 min ago. After: three items owned by deadbeef; the `[>]` is `[ ]` with no worker and the reset note; the `[?]` keeps its tokens and `--list --open deadbeef` shows `DEFAULT executes in 20m`, not 120; the originals are `[x]` with `migrated to #`; a Stop as deadbeef BLOCKS on them; `--candidates` no longer lists `mig-prev`. Planted: `upd` not carried (window reads 120m); the `[?]` written as `[ ]`.
7. **Idempotent by `mg.from`.** Second run: `nothing left`, exit 0, writer file line count unchanged; after `--update` on the new item (lastnote changes) a third run still migrates nothing. Planted: dedup keyed on the note text.
8. **Refuse local liveness, and the control on the control.** `.lastevent-migprev.json` written now: exit 2 naming the file and its age; backdated 40 min: succeeds. Same pair for a fresh vs stale `.sessions` brief and for a transcript mtime under `WORKLIST_PROJECTS_DIR`. Planted: liveness reads `.lastevent` presence instead of age (refuses forever, which is also what would refuse everything on a warm machine).
9. **Refuse self and alias.** `--migrate deadbeef deadbeef` exit 2; `plant_chain` + `--adopt` then `--migrate` the adopted prev: exit 2 "already yours". Planted: alias check dropped (the ancestor's items are re-added as duplicates).
10. **Candidates counts and exclusions.** `--candidates --json` reports `{open:1, inflight:1, deferred:1}`, `branch: agenttest`, the host hash, the brief; excludes a live peer; excludes a handed-off prev unless `--all`. Planted: counts derived from `classify_items` `others` strings (deferred reads 0).
11. **Fresh machine.** New TMPDIR, empty `WORKLIST_PROJECTS_DIR`, only `agent/worklist/*.jsonl` present: `--candidates` lists prev as `remote`, `--migrate` succeeds, and the existing blindness line (`N_PHANTOM_BLIND`) still prints unchanged. Planted: "no artifacts" treated as `live`.
12. **Stop fold-in.** As deadbeef with no own items and prev's open item: the allow report contains `HANDOFF CANDIDATES`, `/migrate` and the item text; with prev LIVE (fresh brief) the block is absent and `others-items` prints instead; two consecutive stops -> the second is absorbed; a new `--add` by prev -> it re-fires. A `[?]` owned by prev appears in the block (the `others` path would drop it). Planted: gate inverted; `[?]` filtered.
13. **PostCompact and SessionStart carry it.** `--post-compact` `additionalContext` contains the block; `--session-start` with `source=startup` contains it; `source=compact` stays silent (the rule at `wl_checks.py:2034-2035`). Planted: block appended only to the allow path.
14. **Identity table.** `18-identity.sh` gains `"--migrate|--migrate @ME@ mig-prev|migrated"` (FIRE refuses a foreign `<me>`, CONTROL A moves against the planted dead prev, CONTROL B blind) and `--store`, `--import-tmp`, `--doctor` in `NO_ME`; the existing derivation reds if any is missing.
15. **Doctor.** Planted `<<<<<<<` lines in a store file: `--doctor` exit 1 with `file:line`; the Stop report carries `store: 3 unparseable line(s) in <file>`; a clean store exits 0 and the report is silent. Planted: the warning removed (the fold skips markers silently, 772).
16. **Uncommitted store advisory.** Own writer file dirty with newest event 90 min old (`git init` fixture as in `reg_repo`): advisory present; committed: silent; dirty but newest event 5 min old: silent. Planted: age gate dropped (fires on every stop).
17. **Skill shape** in `test-hooks.sh` beside the WIRING section: `.claude/skills/migrate/SKILL.md` exists, has `user-invocable: true`, names `--candidates`, `AskUserQuestion` and `multiSelect: true`; the skill's question text extracted from the file is piped through `block-settled-questions.sh` as an AskUserQuestion payload and must exit 0; the planted `Do you want to continue the branch 0903-1 session?` must exit 2. Planted: question reworded to a permission shape.
18. **Secrets refused at the door.** `--add`/`--tick`/`--update`/`--defer` text carrying `-----BEGIN PGP PRIVATE KEY BLOCK-----`, `ghp_` + 36 alnum, or `AKIA` + 16 uppercase: exit 1, nothing appended; a plain `https://` URL passes. The `--doctor`/CI gate reds on the same shapes in a fixture store. Planted: the refusal removed (the tracked file now contains the token).

## 7. Risks, stated plainly

- **Secrets in a tracked store.** Tick evidence and notes are free text, and `agent/d1589e0b/STATE.md` records an armored private key reaching a transcript this week. Mitigation: shape refusal at every text-taking verb, `--doctor` and a CI gate over `agent/worklist/`, and the history-rewrite path already designed in `agent/PLAN-git-history-media-rewrite.md` as the last resort. Residual: a secret that matches no shape.
- **Merge conflicts.** Per-writer files make them structurally rare; the two shared-write paths (`_shared.jsonl`, compaction) are bounded and gated; the resolution rule is union and the fold is built to accept a union. Residual: a revived dead session appending to a file compaction rewrote -> modify/modify, resolved by union.
- **Two machines editing the same item.** Only `migrate`/`tomb`/`reassign` cross writers; clock skew can reorder them; the outcomes are enumerated in 1.3 and none loses an item.
- **Size and history growth.** 125 KB/day measured; compaction of dead writers drops old `[x]` items and their prose; git delta-packs the rest. Residual: history is permanent; that is the operator's chosen trade for portability.
- **An always-dirty tree.** The writer file changes on every verb, so `git status` is never clean in a working session; the repo already forbids blanket adds and demands named paths (`agent/RULES.md`). The uncommitted-store advisory turns "forgot to push before switching machines" into a printed line.
- **Suite fallout.** Cases that plant or read `$WL.events.jsonl` directly (`_harness.sh:339 phantom_store`, case 78 in `05-requests.sh:274-315`) must be repointed at the writer file; the runner's fixture root grows an `agent/worklist/` that the tool creates. Any case that asserts `agent/` contains only session directories will see `worklist` and must use `agent_session_dirs`.
- **Hook budget.** Reading ~15 small files and sorting ~800 events per stop is negligible; `git_branch` is one subprocess per process, cached.
- **Remote sessions cannot be proven live.** The plan says so in the option text and makes the operator the oracle; a `LIVE_MIN` wait was rejected because the operator's stated use is an immediate machine switch.
- **Privacy.** Branch names and a hostname hash enter a tracked file; item text already carries repo paths. Raw hostnames and cwd are deliberately not stored.
- **Plan-fidelity nag.** This plan carries `Owner: d1589e0b` and open boxes, so the plan-fidelity check will demand they be tracked; that is intended and the implementing session claims them with `--add`.

## Tasks

- [ ] `wl_store`: add `store_dir()`, `writer_path()`, per-writer `append_events(writer=)` with `h`/`br` stamping, the union-and-sort `_read_events` that also reads the legacy TMPDIR log, `worklist` in `AGENT_RESERVED_DIRS`, and the amended sidecar docstring (keep the parenthesised shape the gate parses)
- [ ] `wl_store`: fold arms for `mg` on `add` and `mg.to` on `state`; carry `mg`/`mt`/`br`/`h` and the newest `brief` per `(by, about)` through `compact()`; compaction limited to own + dead writers with `[x]` older than `WORKLIST_ARCHIVE_HOURS` dropped unless `--keep-done`, printing per-file `rewritten`/`skipped: live (<evidence>)`
- [ ] `wl_store.session_liveness()` (live/idle/remote/unknown with evidence) reusing `.lastevent` age, `.sessions` age, `owner_age_hours` and newest same-host event; alias exclusion via `fold.aliases_of`
- [ ] `wl_checks`: `phantom_identities` via `_read_events`; judge reopen passes `writer=me8`; `handoff_candidates()` + `N_HANDOFF_CANDIDATES` on the allow path (`outq` key `handoff`, prio 1, refresh 60), in `handle_post_compact` and in `handle_session_start` (non-compact only); `N_STORE_UNCOMMITTED` advisory; `N_STORE_DOCTOR` line for unparseable store lines
- [ ] `worklist.py`: `--store` (self-contained), `--import-tmp`, `--doctor`, `--migrate <me> --candidates [--json] [--all]`, `--migrate <me> <prev>...` with the refusals and the printed report, secret-shape refusal in every text-taking verb, `--brief` tracked twin, USAGE line and `CLI_MIGRATE_*` messages in `worklist_messages.py`
- [ ] `.claude/skills/migrate/SKILL.md` per section 5 (first `user-invocable: true` skill in the repo)
- [ ] `worklist-cases/26-migrate.sh` with controls 1-16, registered in `CASE_FILES`; repoint `phantom_store` and case 78 at the writer file; `--migrate` row and the three `NO_ME` entries in `18-identity.sh`
- [ ] `test-hooks.sh`: control 17 (skill shape and the pre-ask guard round trip) and control 18 (secret refusal) wiring; CI gate `check-worklist-store.sh` over `agent/worklist/` registered per the `testing` skill
- [ ] Docs: `CLAUDE.md:91-140` (per-checkout tracked store, commit your writer file with STATE.md, `/migrate`, admissible Remaining shape (e)); `agent/README.md` layout entry for `agent/worklist/`; `agent/worklist/README.md`; TRAPS entry "a store file conflict is resolved by union, never by picking a side"
- [ ] Run `worklist.py --import-tmp` on this host, commit `agent/worklist/_import-29c1bbae.jsonl` and `agent/worklist/d1589e0b.jsonl` by name, run `bash .claude/hooks/test-hooks.sh` to green (890+ cases plus the new file)
- [ ] First real exercise: `/migrate` in this session with `472cf53d` offered as a candidate, operator selects, `#6f84d8d8` re-tags to `d1589e0b`; record the outcome in this plan's Status

## Controls

Listed in section 6; each names its planted defect. The five that must red before anything else is trusted: 3 (union without sort), 4 (legacy union dropped -> stop allows), 5 (compact rewrites a live peer's file), 8 (liveness read as presence rather than age), 12 (fold-in claims a live peer or drops `[?]`).

