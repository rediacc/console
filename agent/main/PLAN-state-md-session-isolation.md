# PLAN: STATE.md session isolation
Status: done
Owner: 99ccf057
Updated: 2026-08-09

## 1. Context: the incident this fixes

`.agent/<branch>/STATE.md` is the compact-recovery document. It is keyed **per
branch**; sessions are **per session**; and this repo routinely runs several
sessions in one shared checkout on `main`. On 2026-08-09 three were live at
once (`99ccf057`, `2fd369e0`, `97604f47`).

What happened:

1. The Stop hook told session `99ccf057` the document was stale ("30 min old,
   limit 15") and demanded a rewrite.
2. `99ccf057` obeyed with `worklist.py --state 99ccf057 <<EOF ... EOF` and
   **destroyed peer `2fd369e0`'s entire state document** -- a live canary
   campaign: attempt 6 in flight, a watch id, five flag flips, a released
   v1.2.24, an operator-owned design question.
3. It was recovered only because the writer read
   `/tmp/claude-worklist/<slug>.agentstate.prev.main.md` before writing again.
   That backup is single-slot per branch: the very next `--state` write
   overwrote it with `99ccf057`'s own first body. A one-write-later recovery
   would have been impossible.
4. The peers had already been maintaining `## SESSION <id>` headings by hand,
   which is what a social workaround for a tool-level collision looks like.

The staleness gate *drives* the collision: it nags every session on the branch,
on a 15-minute clock, to rewrite the one shared file. More sessions, more
overwrites.

This plan makes the document a per-session sectioned artifact with merge
semantics in the write path, per-section staleness, and automatic reaping of
dead sections -- without giving up the single coherent briefing PostCompact
needs.

## 2. Verified current behavior (with the summary's errors corrected)

All line numbers checked against the working tree at the time of writing.

### 2.1 Paths and shape

| Thing | Where |
|---|---|
| document | `wl_store.py:223` `agent_state_path()` -> `<root>/.agent/<branch>/STATE.md` |
| branch dir | `wl_store.py:219` `agent_branch_dir()`; never auto-created (`worklist.py:845-849`) |
| write lock | `wl_store.py:235` `agent_state_lock_path()` -> `<worklist>.agentstate.lock` in TMPDIR |
| backup | `wl_store.py:241` `agent_state_backup_path(worklist, branch)` -> `<worklist>.agentstate.prev.<branch>.md` |
| shape rule | `wl_store.py:1167` `agent_state_shape()`: thin <250, bloated >cap, aimless without `## Next action` |
| next-action regex | `wl_store.py:167` `AGENT_NEXT_RE` |
| staleness | `wl_store.py:1202` `agent_state_state()` |
| constants | `wl_store.py:116-124`: `AGENT_STATE_STALE_MIN=15`, `MIN_CHARS=250`, `MAX_CHARS=4000`; `:162` `AGENT_STATE_ADOPT_MAX_MIN=60` |

### 2.2 Corrections to the briefing I was given

- **The `## SESSION` convention is not purely social -- it is already half in
  the code.** `wl_store.py:139` `AGENT_STATE_SESSION_RE`, `:142`
  `agent_state_blocks()`, `:152` `agent_state_max_chars()` and the mirrored
  arithmetic in `block-agent-state-shape.sh:49-51` make the *character cap*
  scale with the number of `## SESSION` headings. That is the only thing the
  code knows about sections. Nothing parses them, nothing owns them, nothing
  ages them, and the write path is still whole-file last-write-wins. So the
  format already exists and the semantics do not -- which is exactly why the
  collision is invisible to the tool.
- **The comment at `wl_store.py:126-140` already names this failure and its
  incentive**: under a flat cap "the cheapest way to satisfy it is to delete
  the other session's block, which is precisely the loss this document's own
  header warns against and which had already happened twice." The cap was
  scaled; the deletion was not prevented.
- **A second session is not nagged immediately on arrival.** Adopt-on-first-
  sight (`wl_store.py:1244-1247`) makes an unsigned document up to 60 minutes
  old "ok", and `wl_checks.py:1923-1933` banks the signature on an "ok"
  verdict. The nag starts *after* adoption, which is when the collision starts.
- **The backup is already branch-scoped** (fixed 2026-07-31, findings
  3688784930/3688787780). It is still *single-slot per branch*, so the report's
  central point stands unchanged.
- **"30 min old, limit 15" is only half the rule.** Staleness is world-keyed:
  `agent_state_state()` returns `stale` only when the age exceeds 15 minutes
  **and** `cur_sig != saved_sig` (`wl_store.py:1242-1249`), where `cur_sig` is
  `state_world_sig()` (`wl_store.py:1359`, item structure + HEAD + task
  statuses) and `saved_sig` is this session's own `state_sig` in
  `<worklist>.state-<prefix>.json`.

### 2.3 The bug, in two halves, both proven

**Half one, destruction.** `worklist.py:789-889` `--state` reads the whole body
from stdin and `os.replace`s the file (`:869-871`). There are no merge
semantics and the code says so at `:790-796`: "last-write-wins is deliberate,
because a document whose contract is 'rewrite every time' has no merge
semantics." A raw `Write` is the same story: `block-agent-state-shape.sh` denies
`Edit`/`MultiEdit`/`NotebookEdit` (`:31-34`) but *allows* a shape-valid whole-
file `Write` (`:36-60`), which has no merge semantics either.

**Half two, mutual silencing.** Age comes from the file's mtime
(`wl_store.py:1236`), which is per FILE, while `saved_sig` is per SESSION. So a
peer's write resets everyone's clock. Reproduced against the real function
rather than inferred:

```
$ python3 probe.py     # drives wl_store.agent_state_state on a fixture
30-min-old, B's own sig moved ->            ('stale', 30)
after peer A's write, B's sig STILL moved -> ('ok', 0)
```

Session B's obligation vanished because session A wrote. Worse: at that point
`wl_checks.py:1923-1933` banks A's world signature as B's own, so B does not
merely skip one stop -- it adopts a document describing A's world as its own
recovery artifact.

### 2.4 The consumer that constrains the format

`wl_checks.py:1463-1528` `handle_post_compact()` calls
`agent_state_state(root, branch)` with no signature (shape and presence only,
`:1486`), and hands the **entire** document back inside
`CTX_POSTCOMPACT_BRIEFING` (`worklist_messages.py:1226`) alongside RULES.md and
the TRAPS.md titles. When the document is missing it emits
`CTX_POSTCOMPACT_MISSING` (`:1210`) -- and today that path returns **no state
content at all**, so a compacted session on a branch where only a peer has
written gets nothing.

### 2.5 Identity and liveness primitives already in the repo

- `wl_core.py:137` `owned_by_me(owner, session_id)` -- untagged is mine; a tag is
  a prefix of the session id.
- `wl_core.py:147` `same_session(a, b)` -- symmetric prefix match.
- `wl_core.py:199` `resolve_session_id()` -- `WORKLIST_SESSION_ID` then
  `CLAUDE_CODE_SESSION_ID`; `ME_MIN_LEN = 8`.
- `wl_store.py:841` `owner_age_hours(owner, projects_dir)` -- hours since the
  owner's newest transcript write; `None` when no transcript matches; newest
  match wins (conservative).
- `wl_store.py:855` `cleanup_dead_sessions()` -- `WORKLIST_DEAD_HOURS` default
  24, `WORKLIST_ARCHIVE_HOURS` default 168. `projects_dir` is derived at
  `wl_checks.py:1678-1680` from `WORKLIST_PROJECTS_DIR` or the transcript's
  dirname. There is **no** helper that derives it without an event, which the
  CLI write path will need (see 4.2).

Transcript directory convention, verified on this machine:
`~/.claude/projects/<repo-path-with-slashes-as-dashes>/<session-uuid>.jsonl`,
e.g. `/home/muhammed/.claude/projects/-home-muhammed-monorepo-console/`.

### 2.6 Gates that constrain the change

- `.ci/scripts/quality/check-python-lint.sh` -- ruff lint **and** format,
  `select = ["ALL"]` in `ruff.toml`, line length 100, `RUF100` on. `S105` fires
  on any identifier containing "TOKEN".
- `.ci/scripts/quality/check-tracked-sidecars.sh` -- parses the parenthesised
  list in the `wl_store.py` module docstring (`wl_store.py:36-42`) and refuses
  to run if it cannot. **Finding:** that list omits `.agentstate.*`,
  `.events.*`, `.lastevent-*`, `.emails*`, `.emailunconf-*`. Nothing is tracked
  today (only `.py`/`.sh` files are in `git ls-files .claude/hooks/stop`), so
  this is a blind spot rather than a live defect -- but it is one line of
  docstring and this change adds a sidecar to that family anyway, so close it
  here (see 4.1).
- `test-worklist-v5.sh` case 117 (`:2477-2607`) renders every catalogue string
  at its call-site arity **and fails on any unmapped constant**
  (`gap = strs - set(ARITY)`), so every new message needs an ARITY entry.
- `.ci/scripts/test/gates/test-worklist-hooks.sh` runs both stop-hook harnesses
  in CI and fails a harness that ran zero cases.

## 3. Design

### 3.1 Recommendation, in one paragraph

STATE.md becomes a **single file of owned, timestamped sections**. `--state`
takes **one section's body** on stdin and MERGES it into the document under the
existing flock, leaving every other section byte-identical; it reaps sections
whose owner is dead and archives their bodies before dropping them. Staleness
is computed from the **owner's own section heading timestamp**, so no session's
write can silence or nag another. PostCompact renders the same file with the
reader's own section first and peers' sections labelled as not-theirs. Raw
`Write` on STATE.md is denied outright, because a whole-file write is the
defect and only the CLI can merge.

### 3.2 On-disk format

```
## SESSION 2fd369e0 2026-08-09T21:05Z
<body: 250-4000 chars, contains a '## Next action' section>

## SESSION 99ccf057 2026-08-09T18:30Z
<body>
```

- **Heading regex** (new, `wl_store.py`):
  `AGENT_STATE_HEAD_RE = re.compile(r"^##[ \t]+SESSION[ \t]+([A-Za-z0-9_-]{4,32})\b[ \t]*(.*)$", re.M)`
  Case-sensitive on `SESSION` is fine (the writer emits it); the owner group is
  deliberately wider than hex so the `legacy` pseudo-owner (3.7) parses through
  the same path.
- **Timestamp**: the first
  `AGENT_STATE_TS_RE = re.compile(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(?::\d{2})?Z")`
  match **anywhere in the heading tail**. This is not decoration: the headings
  live sessions are writing by hand today
  (`## SESSION 2fd369e0 (Part C: canary attempt 6; 2026-08-09T21:05Z)`) parse
  correctly under this rule on first encounter, with no migration.
- **Body** is everything up to the next heading, stripped. Text **before** the
  first heading is the unowned preamble (3.7).
- **Order on disk is stable**: an existing section is replaced in place, a new
  one is appended. Reordering happens only at render time, so a `diff` between
  two writes shows exactly one section changed.

Rejected delimiters: an HTML comment fence (`<!-- session: x -->`) -- invisible
to the human reading the file, and the file's readability is the property that
made the incident recoverable at all; and YAML front matter per section -- a
second syntax for the same fact.

### 3.3 Write path: `worklist.py --state <me>` (merge)

stdin is **this session's section body only**. The verb:

1. Resolves branch and identity exactly as today (`worklist.py:800-825`),
   including the isatty and empty-stdin refusals -- unchanged.
2. Refuses a body containing a `## SESSION` heading, with a message that names
   the new contract (`CLI_STATE_WHOLE_DOC`). A session pasting the whole
   document is the exact old habit; refusing it is how the contract is taught,
   and the refusal costs nothing because the previous document is untouched.
3. Validates the **submitted body** with `agent_state_shape()`: flat 250-4000
   and a `## Next action`. `agent_state_blocks()` and `agent_state_max_chars()`
   are DELETED. The scaling cap existed only to make a shared budget survivable;
   with a per-section budget it is dead weight, and clean break is the rule
   here (one operator, no external consumers).
4. Takes the existing flock, reads the current document, parses it into
   sections. **A parse that yields nothing but a non-empty file is not an
   error**: the whole file becomes one `legacy` section (3.7). Nothing is ever
   silently discarded.
5. Reaps dead sections (3.6), appending each reaped body to
   `<worklist>.agentstate.reaped.<branch>.md` **before** it is dropped.
6. Replaces or appends this session's section with a freshly stamped heading.
7. Copies the whole outgoing document to the branch-scoped `.prev` backup
   (unchanged code, unchanged semantics), then `tempfile` + `os.replace`.
8. Banks `state_sig` in `.state-<prefix>.json` (unchanged, `worklist.py:882-887`).
9. Prints: chars written, sections kept with owners and ages, sections reaped
   with the archive path, and the backup path. The existing "replacing a
   N-minute-old document" line becomes "replacing your N-minute-old section",
   because after this change replacing the *document* is not a thing that
   happens.

Failure policy: the write path fails **loud and writes nothing** on any refusal
or exception. The previous document surviving intact is always the correct
outcome of a failed write.

### 3.4 Read path: per-session staleness

`agent_state_state(root, branch, session_id, cur_sig=None, saved_sig=None)`
gains `session_id` and judges **only the caller's own section**:

- `no-branch`, `no-dir` -- unchanged.
- `missing` -- no file, OR no section owned by me and no adoptable preamble.
- `thin` / `bloated` / `aimless` -- **my** section fails `agent_state_shape()`.
  A peer's malformed section never blocks me. This is not politeness: blocking
  me on a document I must not edit leaves deletion as the only way to clear the
  gate, which is the incentive that caused the incident.
- `stale` -- my section's heading timestamp is older than `AGENT_STATE_STALE_MIN`
  AND (`saved_sig is None` and past the adopt horizon, OR `cur_sig != saved_sig`).
  The world-keyed rule and the adopt-on-first-sight rule are preserved verbatim;
  only the age source moves from the file's mtime to my heading's stamp.
- `ok` otherwise.

`saved_sig` stays in `.state-<prefix>.json`. It is already per-session, so no
new sidecar is needed for the world half; the **time** half is the part that
had nowhere per-session to live, and it now lives in the heading.

**Named residual (fail-open by at most one peer-write interval):** a section
whose heading carries no parseable timestamp -- only reachable by a raw
`cat > STATE.md` in Bash, since Write and Edit are both denied -- falls back to
the file's mtime for age. mtime is the newest write to the file, so such a
section can read fresher than it is. The alternative (treat it as permanently
stale) nags forever on a document the tool did not write; the fallback is
stated here rather than hidden, and the reap path still bounds it at 24 hours.

### 3.5 PostCompact assembly

`handle_post_compact()` renders from the parsed sections:

- **Own section first**, in the existing `CTX_POSTCOMPACT_BRIEFING` slot, with
  the arity unchanged so the case-117 map does not move for it.
- **Peers after**, in a new `CTX_POSTCOMPACT_PEERS` block appended the way the
  plans and checklist blocks already are (`wl_checks.py:1512-1525`). Each peer
  renders as a labelled fence naming the owner, the age, and that it is not the
  reader's to rewrite or delete.
- **Dead sections are skipped** at render time (they are only physically removed
  by a write).
- **Own section missing**: `CTX_POSTCOMPACT_MISSING` as today, **plus** the
  peers block. Today that path returns no state content whatsoever, which on a
  shared branch is a strictly worse briefing than the file contains.

Appending peers as a separate block rather than widening
`CTX_POSTCOMPACT_BRIEFING` is deliberate: it keeps two message arities frozen,
and it matches the established "each block is built on its own and the hook
emits when either has something to say" structure at `wl_checks.py:1404-1410`.

### 3.6 Reaping dead sections

One liveness notion, the repo's existing one:

```
dead(section) = owner is not me
                AND (owner_age_hours(owner, projects_dir) >= WORKLIST_DEAD_HOURS
                     OR (owner_age_hours(...) is None
                         AND section_age_hours >= WORKLIST_DEAD_HOURS))
```

`WORKLIST_DEAD_HOURS` defaults to 24, shared with `cleanup_dead_sessions()`. The
`None` arm covers the `legacy` pseudo-owner and any owner whose transcripts live
on another machine; falling back to the section's own stamp keeps the horizon
identical instead of inventing a second one.

- Reaping happens **only in the write path**. The Stop check must not rewrite a
  document under a live peer; a read-only hook that mutates shared state is how
  the next clobber gets built. Accumulation is bounded anyway, because
  accumulating requires somebody to be writing.
- Never reap the writer's own section, at any age. A session's own stale
  section is a nag, not garbage.
- Reaped bodies are appended to `<worklist>.agentstate.reaped.<branch>.md`
  before removal. Append-only, in TMPDIR, unbounded but tiny (one append per
  dead session per branch).
- The Stop check reports (never blocks on) the peer sections it sees, including
  which are reap-eligible, via `N_AGENT_PEERS` queued as a class-2 volatile note
  the way `N_AGENT_BLIND` already is (`wl_checks.py:2648-2651`). A session that
  cannot see the peers cannot be expected to respect them.

### 3.7 Legacy and unowned content

A pre-section STATE.md, or any text before the first heading, is **one unowned
section**. On the next `--state` write it is preserved verbatim under a
synthesised heading:

```
## SESSION legacy <file-mtime as ISO8601Z> (adopted from a pre-section document)
```

- It is never deleted by the write that adopts it, so an in-flight peer's
  pre-upgrade document survives the first merge on that branch.
- It ages out through the ordinary reap path (owner `legacy` has no transcript,
  so the section-age arm applies) 24 hours later, archived rather than dropped.
- On the **read** side, a session with no section of its own but an adoptable
  preamble younger than `AGENT_STATE_ADOPT_MAX_MIN` (60) gets `ok`, exactly
  reproducing today's adopt-on-first-sight grace for the single-session case.
  Past that horizon it is `missing`, and writing a section is one command.

This is the only backward-compatibility affordance in the plan, and it is not a
migration path: it is the *read* of a document that already exists on disk in
three checkouts right now.

### 3.8 Write-tool policy

`block-agent-state-shape.sh` changes from "deny Edit, shape-check Write" to
**deny every direct tool write to STATE.md**, naming `--state` as the way. The
cap arithmetic (`:42-55`) is deleted with `agent_state_max_chars()`.

Justification: merge semantics cannot be enforced by a shape-only shell guard,
and a shape-valid whole-file `Write` destroys peers exactly as thoroughly as the
CLI used to. The escape hatches that matter survive: restoring a backup is `cp`
in Bash, and the CLI is a script anyone can run. The residual is a Bash
heredoc straight onto the path, which no PreToolUse hook can see -- handled by
3.4's timestamp fallback and 3.7's unowned-section rule rather than pretended
away.

### 3.9 Backup strategy: decided

**Keep the single-slot branch-scoped `.prev.<branch>.md`, and add an
append-only reap archive.** Reasoning:

- After this change, `--state` cannot destroy another session's content, so the
  loss the `.prev` slot was built for is gone by construction. What remains for
  it to cover is a bug in the merge itself, and one slot covers that: the whole
  outgoing document is copied, and the merge preserves the sections anyway.
- Making it per-session would be backwards. The clobber risk is per-DOCUMENT,
  the document is per-branch, and a per-session slot would hold N copies of the
  same content while still keeping only one generation of each.
- Timestamped generations were rejected as unbounded growth for a hazard that
  the merge removes. The one path that still *deletes* content without anyone
  choosing to is reaping, and that gets a genuinely append-only archive, which
  is the strictly stronger guarantee applied to the strictly narrower case.

### 3.10 Alternatives rejected

1. **One file per session (`.agent/<branch>/STATE-<prefix>.md`).** The strongest
   alternative: collisions become impossible at the filesystem layer, including
   the Bash-heredoc case. Rejected because the shared document is doing real
   work as a shared document -- the live `.agent/main/STATE.md` right now has
   `99ccf057`'s section telling the *reader* which uncommitted files peers
   `2fd369e0` and `97604f47` own and must not be swept by a `git add -A`. That
   cross-session context has no home in a per-session file, and every session
   would have to glob and read N files to get it. It also renames the artifact
   that the README, the PreToolUse guard glob, the hook messages and the
   operator's own habits all name, for a hazard the merge already closes on
   every tool-mediated path.
2. **Keep whole-file writes; refuse a body that drops a peer's heading.** Makes
   the tool refuse the natural action without offering a correct one. The
   session then hand-merges the peer's block into its own body, which is the
   failing social workaround with a gate bolted on.
3. **Per-section timestamps in a sidecar instead of the heading.** A sidecar is
   invisible to a human reading the file, cannot survive a write that does not
   go through the tool, and would need a new entry in the docstring family
   anyway. The heading stamp is self-describing, already half-present in the
   headings live sessions write by hand, and is information the reader wants.
4. **Reap by section age alone.** A live but quiet session (24h on one long
   watch is ordinary here) would lose its section. `owner_age_hours` is the
   repo's liveness notion; a second one would drift from it.
5. **Reap inside the Stop check.** Makes a read-only, every-turn hook a writer
   of the shared document. Fastest route to the next clobber.

## 4. Implementation order

Land as ONE commit. A Stop hook reading sections while the CLI writes whole
documents nags every session on the branch forever, so the halves must not be
separable.

### 4.1 `wl_store.py`

- Module docstring `:36-42`: add `.agentstate.*` to the sidecar list, and while
  there `.events.*`, `.lastevent-*`, `.emails*`, `.emailunconf-*` (finding 2.6).
  Keep the parenthesised shape the gate's parser depends on.
- DELETE `AGENT_STATE_SESSION_RE` (`:139`), `agent_state_blocks()` (`:142`),
  `agent_state_max_chars()` (`:152`) and the cap-scaling comment `:126-140`
  (replace with a pointer to the per-section budget).
- ADD `AGENT_STATE_HEAD_RE`, `AGENT_STATE_TS_RE`, `AGENT_STATE_LEGACY_OWNER = "legacy"`.
- ADD `agent_state_reaped_path(worklist, branch)` beside
  `agent_state_backup_path()`, same branch-sanitising rule.
- ADD `agent_state_parse(text, mtime)` -> ordered list of
  `{"owner", "ts", "heading", "body"}`. Never raises: an unparseable or
  heading-free document yields one `legacy` section carrying the whole text.
- ADD `agent_state_render(sections)` -- the inverse; stable, idempotent
  (`render(parse(x)) == x` for any document this program wrote).
- ADD `agent_state_mine(sections, session_id)` using `C.owned_by_me`.
- ADD `agent_state_dead(sections, session_id, projects_dir, now)` ->
  `(kept, reaped)` per 3.6.
- REWRITE `agent_state_state()` (`:1202`) to take `session_id` and judge the
  caller's own section per 3.4. Keep the docstring's history; extend it.
- ADD `agent_state_briefing(root, branch, session_id, projects_dir)` ->
  `(own_body_or_None, peers_rendered, n_live_peers)` for PostCompact and for
  the Stop-check peer note.
- `agent_state_shape()` (`:1167`): cap becomes flat `AGENT_STATE_MAX_CHARS`.

### 4.2 `wl_core.py`

- ADD `projects_dir(root)`: `WORKLIST_PROJECTS_DIR`, else
  `~/.claude/projects/<abs-root-with-/-as->` if that directory exists, else `""`.
  One definition of "where transcripts live", because the CLI write path has no
  event to derive it from. `wl_checks.py:1678-1680` keeps preferring the
  transcript's dirname (exact) and falls back to this.

### 4.3 `worklist_messages.py`

- REWORD `V_AGENT_STATE` (`:258`) for sections and the merge contract. **Arity
  stays 6** (`branch, state, age-detail, min, max, me`) so case 117 does not
  move.
- REWORD `CLI_STATE_REFUSED` (`:450`) to say "section"; arity unchanged.
- NEW `CLI_STATE_WHOLE_DOC` -- 1 arg (`me`).
- NEW `CTX_POSTCOMPACT_PEERS` -- 1 arg (rendered peer blocks).
- NEW `N_AGENT_PEERS` -- 2 args (branch, rows).
- No em dashes in any new prose (repo convention).

### 4.4 `worklist.py`

- `--state` (`:789-889`) becomes the merge path of 3.3. Keep the isatty guard,
  the empty-stdin diagnosis, the branch/dir refusals and the `state_sig` banking
  exactly as they are; everything new goes between the flock and `os.replace`.
- Module docstring `:17` mentions the document; update the one clause.

### 4.5 `wl_checks.py`

- `:1920-1933`: pass `session_id` (and `projects_dir`) into
  `agent_state_state()`. The adopt-banking block at `:1923-1933` is unchanged in
  logic -- it now banks against the caller's own section.
- `:2620-2652`: the violation is unchanged in structure; add the class-2
  `N_AGENT_PEERS` note beside the existing `N_AGENT_BLIND` queueing.
- `handle_post_compact()` `:1463-1528`: assemble per 3.5.

### 4.6 `.claude/hooks/pre-edit/block-agent-state-shape.sh`

- Deny `Write` as well as the edit tools (3.8); delete the length/cap/Next-action
  arithmetic (`:36-59`) with it; rewrite the header comment to say why the shape
  check moved back to the one writer that can merge.

### 4.7 Docs

- `.agent/README.md` "Enforcement" section: the section format, the one-section-
  per-write contract, per-section staleness, reaping at 24h, and that `Write` is
  now denied. Gitignored, so no gate -- but it is the file every hook message
  points at.

## 5. Test plan

House style: every case must FIRE on a planted defect and stay silent when
clean; `check <label> <expect-decision> <must-contain>`; fixtures isolated via
`TMPDIR`/`CLAUDE_PROJECT_DIR`/`WORKLIST_TASKS_DIR`.

### 5.1 Harness helpers to add (beside `plant_state`, `test-worklist-v5.sh:132`)

```bash
# mk_section <owner> <minutes-ago> <body> -> a full stamped section on stdout
# plant_doc <text>                        -> raw whole-document plant (bypasses --state)
# section_now <owner> <body>              -> mk_section with a now stamp
```
`plant_state` stays (the shape cases still need a raw, unowned plant) but its
comment gains the reason a plant is now specifically a *legacy* document.

### 5.2 Existing cases that must be updated

18, 19, 20, 21, 29, 29b, 29c, 29d, 30, 44, 144, T1 and T7a/T7b all plant or
write whole documents. Most keep working through the legacy-adoption path, which
is itself worth asserting -- but 44 and 144 (staleness) must be re-pointed at a
**stamped own section**, or they would be testing the mtime fallback instead of
the new rule. Re-read each one; do not bulk-edit.

### 5.3 New cases

- **29f. two sessions share one branch and both sections survive.**
  A (`deadbeef`) writes; B (`cafe1234`, via `as_peer`) writes; assert A's
  section body is byte-identical afterwards and A's heading timestamp is
  unchanged. CONTROL: B writing a second time replaces only B's section
  (A untouched, B's stamp advanced). PLANTED DEFECT that must make it fail:
  restore the whole-file `os.replace(body)`.
- **29g. `--state` refuses a body carrying a `## SESSION` heading.**
  FIRE on a pasted whole document; CONTROL: the same body without the heading is
  accepted, and a refusal leaves the document byte-identical (the 29b pattern).
- **29h. a dead peer's section is reaped and archived.**
  `WORKLIST_PROJECTS_DIR` points at a fixture dir; plant a peer section stamped
  30h ago whose owner has no `.jsonl`; write as `deadbeef`; assert the section
  is gone from STATE.md AND its body is present in
  `<wl>.agentstate.reaped.agenttest.md`. CONTROL 1: a peer whose fixture
  transcript was just touched is NOT reaped. CONTROL 2: the writer's own
  30h-old section is NOT reaped.
- **29i. a legacy single-section document is adopted, not destroyed.**
  `plant_doc` a pre-section body; write as `deadbeef`; assert the legacy text is
  still present under a `## SESSION legacy` heading and `deadbeef`'s section
  exists. CONTROL: with the legacy stamp aged past `WORKLIST_DEAD_HOURS`, the
  next write reaps it into the archive (never into nothing).
- **44b. per-session staleness nags the stale session only.**
  Plant A's section stamped now and B's stamped 30 minutes ago; move the world
  (add an item) so `state_sig` differs for both. Run the Stop hook as B ->
  `block` on "STATE.md". Run it as A -> `allow`. ANTI-VACUITY: re-stamp B's
  section fresh and assert B now allows, so the case is not passing because
  everything blocks. This is the case for the incident; a mutation that reverts
  age to `p.stat().st_mtime` must turn it red.
- **21b. PostCompact puts my section first and labels the peer's.**
  Assert the own body's offset in `additionalContext` is lower than the peer
  heading's, and that the not-yours label is present. CONTROL: with no peer
  section, no peers block appears at all.
- **20b. PostCompact with no own section still hands back the peer's.**
  Assert both the own-missing instruction and the peer's body are present.
- **29j. a fail-closed malformed document is never silently replaced.**
  Plant a document that parses to nothing useful (binary bytes / no headings /
  under the thin floor); write as `deadbeef`; assert the original bytes are
  recoverable from either the `.prev` backup or the preserved legacy section.
- **117.** Add `"CLI_STATE_WHOLE_DOC": ("m",)`, `"CTX_POSTCOMPACT_PEERS": ("b",)`,
  `"N_AGENT_PEERS": ("br", "rows")` to the ARITY map.

### 5.4 `test-hooks.sh` (guard suite)

Cases at `:173-175` and `:233` change: the two blocked-Write cases stay exit 2
with a new needle, `:175` (Edit) is unchanged, and `:233`
("well-shaped Write passes") **inverts** to exit 2 with the `--state` pointer.
Keep a passing control on `RULES.md` (`:234`) and a non-agent file (`:235`) so
the guard is still proven not to over-match.

### 5.5 Local run commands

```bash
bash .claude/hooks/stop/test-worklist-v5.sh          # the stop suite (~440 cases)
bash .claude/hooks/test-hooks.sh                     # guards + the stop suite
bash .ci/scripts/test/gates/test-worklist-hooks.sh   # exactly what CI runs
bash .ci/scripts/quality/check-python-lint.sh        # ruff lint AND format
bash .ci/scripts/quality/check-tracked-sidecars.sh   # parses the wl_store docstring
```

Mutation proof before calling any case done: for each new case, plant the defect
it targets (whole-file replace; mtime-based age; reap-without-archive; peers
dropped from PostCompact) and confirm that exact case goes red. A case that
stays green under its own mutation is not a case.

## 6. Risk

**Blast radius is every stop in the repo.** This code gates the end of every
turn for every session in every checkout of this monorepo, and three sessions
are live in this tree right now. A crash in the new parser blocks or wedges all
of them; a wrong staleness verdict either nags every session forever or silently
retires the one artifact that survives compaction.

What makes it safe to land:

- **Read paths cannot raise.** `agent_state_parse()` degrades an unparseable
  document to one `legacy` section and never throws, so the worst read-side
  outcome is today's behavior (one document, one owner). The Stop hook keeps its
  existing "OSError degrades to missing, which BLOCKS" posture.
- **The write path fails loud and writes nothing.** Every refusal leaves the
  previous document byte-identical, which case 29b already pins and the new
  cases extend.
- **No content is ever dropped without a copy.** The merge preserves peers by
  construction, the `.prev` backup keeps the whole outgoing document, and the
  one deleting path (reap) appends to an append-only archive first.
- **The format degrades gracefully under a revert.** A sectioned document read
  by the pre-change code is just a long single document, and the pre-change cap
  scaled with `## SESSION` headings -- so it fits. Rollback is `git revert` of
  the one commit with no on-disk cleanup, which is why no dual code path or
  feature flag is warranted (and the repo forbids them anyway).
- **The suite runs in CI.** `.ci/scripts/test/gates/test-worklist-hooks.sh`
  already fails on a harness that ran zero cases, so a suite silently reduced to
  nothing cannot pass.

What stays risky, stated rather than hidden:

- A Bash heredoc writing STATE.md directly bypasses every guard. Mitigated, not
  closed, by the timestamp fallback (3.4) and unowned-section handling (3.7).
- Sessions running the pre-change instructions will keep piping whole documents
  into `--state`. They get `CLI_STATE_WHOLE_DOC` rather than a clobber, which is
  the correct trade, but it is a refusal an in-flight session will meet
  mid-task. The message must therefore state the new contract in full, not just
  say no.
- The implementing session must not test against the live store or hand-edit
  `.agent/main/STATE.md`; the suite is TMPDIR-isolated and that isolation is the
  only thing keeping this work off three peers' recovery documents.

## Status

**IMPLEMENTED, uncommitted, 2026-08-09.** Every section of this plan landed as
written except the four deviations named below. Verification, all run against
the working tree:

| Gate | Result |
|---|---|
| `.claude/hooks/stop/test-worklist-v5.sh` | `passed=657 failed=0` (baseline before this change: `passed=634 failed=0`) |
| `.ci/scripts/test/gates/test-worklist-hooks.sh` | `PASS: all 2 stop-hook harnesses green` (657 + 118) |
| `.claude/hooks/test-hooks.sh` | `PASS=740 FAIL=0` |
| `.ci/scripts/quality/check-python-lint.sh` | 28 files pass ruff lint AND format |
| `.ci/scripts/quality/check-tracked-sidecars.sh` | pass, now deriving 22 patterns (was 13) |

### Mutation proof

Eight defects were planted in a COPY of the hook directory and the whole suite
re-run against each. A no-op control run in the same copied setup fails exactly
one case (191, which asserts on the hook file's own repo root and so cannot
pass from `/tmp`); every other failure below is attributable to its mutation.

| Mutation | Cases that went red |
|---|---|
| `f.write(merged)` -> `f.write(body)` (whole-file replace) | 29f (both assertions + control), 29h, 29i, 29j, 20b, 21b, 44, 44b, 144, 154b, 160e -- 25 in total |
| section stamp -> `p.stat().st_mtime` for age | 44 and **44b FIRE**, 144, 154b, 160e |
| reap without archiving | **29h** archive assertion, 29i CONTROL |
| peers block dropped from PostCompact | **21b**, **20b** |
| `## SESSION` heading refusal removed | **29g** (both assertions) |
| preamble discarded by the parser | **29i**, **29j**, plus 19/29/30/T7a/T7b (the legacy read path) |
| `session_id=""` into `agent_state_state` | **44b FIRE**, and 121 cases in total, because a blind read makes every session's own section unfindable |
| future heading stamps trusted | **44c FIRE** |

### Live proof, not fixtures

Two real `--state` writes on a mktemp fixture, stdout and stderr read
separately:

- **post-fix:** A writes, B writes, `grep -c` for A's distinctive line in the
  merged document returns **1**; B's success line reads
  `sections kept: aaaa1111 (0 min old), bbbb2222 <- you (0 min old)`.
- **pre-fix (same fixture, `git show HEAD:` copies of the hook):** the same two
  writes leave A's text at `grep -c` = **0**. The incident reproduces exactly.
- **per-session staleness, probed directly on both versions of the function:**
  post-fix `('ok', 0)` for A and `('stale', 30)` for B; pre-fix `('ok', 0)` for
  both, because the old signature has no `session_id` at all and reads the
  file's mtime, which A's write had just reset.

### Deviations from the plan, with reasons

1. **`agent_state_mine` uses `C.same_session`, not `C.owned_by_me`** (4.1).
   Symmetric matching, because the CLI passes a short prefix while the Stop
   event carries the full uuid and either side can be either. `owned_by_me` is
   one-directional, so a session that once wrote a longer tag than the prefix
   it later passes would grow a second section for itself. Both are prefix
   matches, so neither is looser about claiming a peer's section.
2. **`missing` is not the verdict for an aged legacy document** (3.7). It stays
   `stale`, which is what the pre-change code returned and what cases T7a/T7b
   pin, including T7b's anti-vacuity property that it must block twice on an
   unchanged world. Downgrading it to `missing` would have retired a proven
   control for no gain, since both verdicts block.
3. **The backup path is announced whenever a previous document existed**, not
   only when the writer replaced its own section (3.3 step 9). Since the merge,
   a write that merely APPENDS a section still rewrites the file, so the copy
   is real either way. The phantom-file findings the old condition guarded
   against are still covered: nothing is announced on a first write, and a
   failed copy is confessed.
4. **A failed reap archive ABORTS the reap** rather than proceeding (3.6). The
   plan said "archive before drop"; making the drop conditional on the archive
   is the same rule with the failure case decided. Keeping a dead section
   forever is untidy; losing it is the failure this file exists to prevent.

### Findings fixed along the way, not asked for

- **The sidecar docstring list was blind to ELEVEN suffixes, not the five 2.6
  named.** Checked against the code instead of memory: `.ciqueue-*`,
  `.waiternudge-*`, `.failwarned` and `.reaped-*` were missing too. All added;
  the gate now derives 22 patterns.
- **`state_as` in the suite swallowed stderr in its first draft**, and a peer
  body two characters under the 250-char floor was silently refused. Three
  cases then asserted the absence of a section that had never been written, and
  two would have passed for the wrong reason. The helper now fails loudly.
- **`test-hooks.sh` had no way to assert what a guard SAID.** Added `check_out`,
  because the STATE.md guard's entire product is now the redirect to `--state`
  and an exit code cannot tell that from a bare refusal.

### One more finding, from driving the LIVE document

Parsing the real `.agent/main/STATE.md` (read-only) as the last check found a
hole in this plan's own timestamp model, which no fixture would have shown.
Peer `2fd369e0`'s hand-written heading was stamped **101 minutes in the
future** -- almost certainly local time written with a `Z`. A trusted future
stamp makes a section PERMANENTLY fresh, which is strictly worse than the
unstamped fallback 3.4 already accepts as a residual, because the whole point
of per-section staleness is that a section cannot dodge its own clock.

Fixed here rather than filed: a stamp more than `AGENT_STATE_FUTURE_SKEW_SEC`
(300) ahead is treated exactly like an unparseable one, falling back to the
file's mtime with `stamped=False`. Case 44c pins it with two controls (a stamp
inside the skew is still trusted; the fallback really is the mtime rather than
a hardcoded stale verdict), and mutation M8 turns it red.

Live document after the fix, all three real sections: `2fd369e0` now reads
`stamped=False, 48 min` instead of permanently fresh, `render(parse(x)) == x`
still holds byte for byte, and nothing is reap-eligible.

### One behaviour worth knowing before this lands

A session on a branch whose STATE.md has an unowned preamble but no section of
its own is judged on that preamble (3.7). On the live document that means
`97604f47`, which has never written a section, reads `thin` off a 108-character
leftover scrap rather than `missing`. Both verdicts block and both point at the
same fix -- write your own section, one command -- and keeping the preamble
judgeable is what preserves the proven shape cases (19, 29, 30, T7a, T7b). It
is named here rather than smoothed over because the word in the message will be
`thin` when the truer word is `yours does not exist yet`.
