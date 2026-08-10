# PLAN: Unify the trap corpus
Status: superseded
Owner: 99ccf057
Updated: 2026-08-09
Superseded-by: docs/agent/main/PLAN-trap-enforcement.md

SUPERSEDED 2026-08-09. This plan solved the corpus split (two TRAPS.md files,
each blind to the other) and it solved it correctly, but it left the operator's
actual objection untouched: a session can skip reading either file, so one
unified document is still not a control. PLAN-trap-enforcement.md absorbs it and
keeps its decisions, listed in that plan's section 9: the canonical path, the
two-tuple return, one renderer, the blocking violation, the anti-resplit gate,
the merge arithmetic, and all three rejected alternatives including the tested
finding that un-ignoring .agent/TRAPS.md silently tracks nothing. Read it for
that reasoning; execute the other plan.

One trap corpus, at `docs/agent/TRAPS.md`, read by the Stop hook and pointed at by
`CLAUDE.md`, with a gate that reds if a second one ever appears.

---

## 1. Context: the finding, corrected

The repo keeps two trap documents and each half is blind to the other. The brief's
version of this is accurate in every load-bearing claim; the corrections below are
additions and one sharpening, not refutations.

**Confirmed as stated:**

- `.agent/TRAPS.md` is gitignored (`.gitignore:149` is a bare `.agent/`) and carries
  **15** `## ` headings. It is the only file the Stop hook reads
  (`wl_store.py:231-232`, `agent_traps_path` → `agent_root(root) / "TRAPS.md"`).
- `docs/agent/TRAPS.md` is tracked and carries **9** `## ` headings. It is the only
  one `CLAUDE.md:593-596` points sessions at.
- No CI gate reads either file. `grep -rn TRAPS` over `.ci/scripts` and
  `.github/workflows` returns exactly one hit, a prose comment at
  `.ci/scripts/quality/check-probe-parity.sh:16`.
- On a missing file `trap_headings` returns `[]` (`wl_store.py:274-277`, bare
  `except OSError`) and both consumers render the placeholder `"  (none recorded)"`
  (`wl_checks.py:1481`, `wl_judge.py:323`). The brief's belief was right.
- The cap is 40 (`wl_store.py:282`).

**Corrections and additions:**

1. **The overlap is one entry, not zero — and it is byte-identical.** After the
   brief's append, `` `git diff <branch>` reads as DELETED for a file the worktree
   never tracked `` exists in both files with identical bodies (measured by splitting
   both files on `^## ` and comparing entry text). So the union is **23**, not 24:
   15 + 9 − 1. Every count in §5 is built on that number.

2. **`"(none recorded)"` is worse than silence: it is an affirmative falsehood.**
   The judge prompt introduces the block as "Hard-won facts about THIS repository …
   each cost a real CI round or a wasted session to learn"
   (`worklist_messages.py:1409-1414`). Rendering `(none recorded)` there tells the
   judge this repository has *recorded no traps*, which is the opposite of true and
   is exactly the input that makes a blocker sound credible for lack of a
   contradicting line. Same string reaches a freshly-compacted session at
   `wl_checks.py:1481`. Absence is being reported as a finding.

3. **The unreadable case is the same silent path as the missing case.** `except
   OSError` at `wl_store.py:276` swallows permission errors, a dangling symlink, and
   a directory-in-place-of-file identically. Any design that only handles "missing"
   leaves two thirds of the class silent.

4. **The 40-heading cap is silent AND positionally backwards.** `trap_headings`
   breaks out of the loop at 40 in *file order* (`wl_store.py:279-283`), and both
   corpora order newest-last (`.agent/TRAPS.md:11`, "Newest at the bottom"). So once
   the file passes 40 entries, the oldest 40 win and **every newly-added trap is
   invisible to the judge, silently, forever**. The merge takes the count to 23,
   consuming 58% of the ceiling in one step, so this stops being theoretical
   immediately. Headings are also truncated to 120 chars (`:281`) without a marker.

5. **There are three heading consumers, not two**, plus five prose references:
   the judge (`wl_checks.py:3269` → `wl_judge.py:305,323` →
   `worklist_messages.py:1414`), and *two* PostCompact arms —
   `CTX_POSTCOMPACT_BRIEFING` (`wl_checks.py:1502-1508`) and
   `CTX_POSTCOMPACT_NO_BRANCH` (`:1484`). A third PostCompact arm,
   `CTX_POSTCOMPACT_MISSING` (`worklist_messages.py:1228-1235`), names the path in
   prose and gets no headings at all.

6. **The two files have incompatible charters, so the merge is not mechanical.**
   `docs/agent/TRAPS.md:7-10` says in as many words: *"Mechanics of a specific
   subsystem do not belong here. CI behaviour (watchdog semantics, job-roster
   growth, run-selection, gate quick-fixes) lives in ci-gates.md … This file is about
   judgement."* At least five incoming entries are precisely that — the review
   tooling coming from `main`, `.ci/breakpoint/` vendoring, matrix fail-fast, the
   status-function skip, the cache-key closure. Concatenating them silently violates
   the destination's own stated scope. The charter paragraph has to be rewritten as
   part of the merge (§5.3); this is the one piece of the work that is editorial
   rather than mechanical.

7. **The repo has already written down the rule this violates.** `wl_checks.py:735-740`:
   *"A plan is the DURABLE design record: committed with its branch, so it survives
   compaction and a lost machine. That is what distinguishes it from the gitignored
   `.agent/<branch>/` tree, whose STATE.md is the volatile cursor."* And
   `.agent/README.md` splits its own tree **by lifetime**, with a table whose rows are
   Minutes → `STATE.md`, The branch → `RULES.md`, Forever → `TRAPS.md`, History →
   `archive/`. TRAPS is the only *Forever* artifact in a directory whose README opens
   with "Gitignored on purpose … must never land in a PR diff, never be policed by the
   CI gates". The corpus is not merely duplicated; by the repo's own durable/volatile
   rule it is **filed in the wrong tree**, and that misfiling is what produced the
   duplicate.

**Adjacent finding, reported not fixed here (out of this plan's scope):**
`V_AGENT_BOOTSTRAP` (`worklist_messages.py:271-279`) ends with "See
`.agent/README.md`", and `.agent/README.md` is itself gitignored. On a fresh clone
that pointer resolves to nothing, so the whole `.agent/` convention bootstraps from a
file that does not exist. Same class as this finding (durable instructions living in a
volatile tree), different file. Worth its own worklist item.

---

## 2. Verified current behavior

| What | Where | Behavior |
|---|---|---|
| Path resolution | `wl_store.py:231-232` | `agent_root(root) / "TRAPS.md"` = `<root>/.agent/TRAPS.md`. No env override. |
| Parsing | `wl_store.py:265-284` | `## ` lines only, never `### `, never bodies; `[:120]` per title; hard `break` at 40. |
| Missing / unreadable | `wl_store.py:274-277` | `except OSError: return []`. Never raises, never reports. |
| Judge | `wl_checks.py:3269` → `wl_judge.py:305,323` | Receives the **list**, joins it itself, falls back to `"  (none recorded)"`. Rendering happens inside `run_judge`. |
| PostCompact | `wl_checks.py:1480-1508` | Renders its own copy of the same join+fallback at `:1481`; feeds `CTX_POSTCOMPACT_BRIEFING` (with the **path** as its 4th arg, `:1506`) or `CTX_POSTCOMPACT_NO_BRANCH`. |
| Suite coverage | `test-worklist-v5.sh:520-535` (case 20), `:4175-4207` (case 153d) | Both plant `$BASE/proj/.agent/TRAPS.md`. 153d asserts titles-only, no bodies, no `###`, and `absent-file → []`. |

**What each consumer actually needs:** titles only, plus a path a human can open. The
economy is deliberate and documented twice (`wl_store.py:268-273`,
`wl_checks.py:1473-1476`): the file is designed to grow forever, so feeding bodies to
a per-stop model call would turn growth into a cost multiplier. Nothing needs body
text. But `CTX_POSTCOMPACT_BRIEFING` hands the session the **path** and tells it to
"read the full entry for any that looks relevant" — so the canonical location must be a
path that exists in the reader's checkout, which a gitignored file is not.

**Two renderings of the same block exist in two files** (`wl_checks.py:1481`,
`wl_judge.py:323`). That duplication is why the placeholder can be fixed in one place
and stay wrong in the other; §4 collapses it to one renderer.

---

## 3. Recommended design

**Make the committed `docs/agent/TRAPS.md` canonical. Repoint the hook at it. Delete
nothing from `.gitignore`. Move the local `.agent/TRAPS.md` aside. Gate against a
second corpus ever appearing.**

Five parts:

1. **Canonical path** — `wl_store.traps_path(root)` returns
   `<root>/docs/agent/TRAPS.md`, with a `WORKLIST_TRAPS_PATH` env override (precedent:
   `WORKLIST_DESIGN_DOCS` at `wl_checks.py:59`, `WORKLIST_AGENT_BRANCH`). The override
   is an unwedging tool, not a fallback: it never points anywhere by default, and the
   gate reads the default with the env unset (§6 assertion E) so it cannot mask a
   wrong default.

2. **Missing is loud, by construction** — `trap_headings` returns a **two-tuple**
   `(headings, problem)`. Callers cannot get the headings without also receiving the
   problem, so a future consumer physically cannot re-introduce a silent `[]`. That is
   the "loud or impossible" constraint satisfied by shape rather than by care.

3. **One renderer** — `wl_checks.traps_block(root) -> (text, problem)` becomes the
   only place a traps block is turned into prose. It emits either the bullet list or
   `M.TRAPS_ALARM % (path, problem)`. `run_judge` takes the rendered string instead of
   a list, so the second fallback at `wl_judge.py:323` disappears rather than being
   fixed twice.

4. **A missing corpus blocks the stop** — `vadd("traps-missing", True, M.V_TRAPS_MISSING
   % (path, problem, repair))`. `always=True` is the documented tier for "hook-integrity
   failures" (`wl_checks.py:2185-2190`), so focus rotation cannot swallow it. Blocking
   is safe here in a way it would not normally be: the hook is registered per-project
   with `$CLAUDE_PROJECT_DIR` (`.claude/settings.json:141,152,170`), the file is tracked,
   so every console checkout and every worktree has it; a miss means someone deleted a
   tracked file, and the message carries the one-line repair.

5. **An anti-resplit gate** — `check:ci-trap-corpus`, five assertions, control-first,
   reachable from `npm run ci` (§6).

### Why this one

- The hook gets a path it can **always** read, guaranteed by git rather than by a
  machine's history. That is the only option where the missing-file path is rare enough
  that blocking on it is reasonable.
- A trap added in a session becomes part of a diff and gets reviewed. Today a trap is
  either invisible to review (`.agent/`) or invisible to tooling (`docs/agent/`).
- `CLAUDE.md:588-596` keeps its shelf of three lookup files under `docs/agent/`
  (`ci-gates.md`, `suppressions.md`, `TRAPS.md`) unchanged — no pointer moves.
- It restores the repo's own durable/volatile rule (`wl_checks.py:735-740`): durable
  goes in git, volatile stays gitignored. `.agent/` keeps exactly the artifacts its
  README's premise actually describes.
- Cost, stated plainly: `docs/agent/TRAPS.md` now appears in PR diffs, and two sessions
  appending on one branch can conflict. Both are trivial (append-only, newest-last) and
  both are the price of reviewability. It picks up **no** new CI policing:
  `check-content-quality.sh:30-33` scans only `packages/www/src/content/{docs,blog}`, so
  the AI-slop patterns never touch it.

### Rejected: (b) keep `.agent/TRAPS.md` canonical and un-ignore it

Possible, but wrong, and its first step is a trap in itself.

- **The obvious implementation is inert.** `.gitignore:149` ignores a *directory*, and
  git will not descend into an excluded directory to re-include a file. Verified in a
  scratch repo: with `.agent/` + `!.agent/TRAPS.md`, `git add -A` then `git ls-files`
  lists **only `.gitignore`**; changing the ignore to `.agent/*` + `!.agent/TRAPS.md`
  lists `.agent/TRAPS.md`. So the natural edit silently tracks nothing, and the author
  finds out when the file is missing on another machine — the exact failure being fixed.
- **It ends the `.agent/` invariant.** `.agent/README.md:3-6` promises the tree never
  lands in a PR diff and is never policed by CI. After (b), one member is tracked and
  the rest are not, and every session has to remember which is which.
- **It strands `CLAUDE.md:593`.** Either the operator's `docs/agent/` shelf loses its
  third entry, or a stub stays behind — two files again, which is the defect.

### Rejected: (c) canonical committed file plus a generated or symlinked local view

- The symlink lives under `.agent/`, so it is itself gitignored: **nothing creates it on
  a fresh clone**, and the hook reads a missing path exactly as it does today. The
  degradation this plan exists to remove is reproduced by the mitigation.
- A dangling symlink after any `docs/` move raises `OSError` → the same silent `[]`.
- A generator script makes the corpus a build artifact with two writable faces, so the
  re-split the gate is meant to prevent becomes the design.

### Rejected: (d) status quo with the pointer moved (hook stays on `.agent/`, `CLAUDE.md` repointed)

The corpus dies with the machine, never appears in review, and `CLAUDE.md` — a committed
file — would point outside the repo's tracked content. It also leaves the fresh-clone
hole open permanently.

### Clean break

No dual read, no fallback to `.agent/TRAPS.md`, no migration shim. A fallback would keep
two live paths, which is what the gate exists to forbid; a gate whose invariant the code
deliberately violates is worse than no gate.

**What a session with a stale local `.agent/TRAPS.md` experiences, first time:**
nothing breaks and nothing warns *during the turn*. The hook reads
`docs/agent/TRAPS.md`, which is present because it is tracked; the stale file is inert.
The loud moment is the next `npm run ci` (or a targeted
`bash .ci/scripts/quality/check-trap-corpus.sh`), where assertion C reds with
"`.agent/TRAPS.md` still exists — the corpus moved to docs/agent/TRAPS.md; run
`mv .agent/TRAPS.md .agent/archive/TRAPS.pre-unify.md`". Until that run, a trap appended
to the stale file reaches nobody. That window is the reason assertion C exists and the
reason it must run locally, not only in CI where `.agent/` never exists at all.

---

## 4. Implementation order

Content first, then the pointer, then the gate. At no point does the hook point at a
file that lacks entries.

1. **`docs/agent/TRAPS.md`** — perform the merge in §5. Verify 23 headings before
   touching any code.

2. **`.claude/hooks/stop/wl_store.py`**
   - Delete `agent_traps_path` (`:231-232`); add `traps_path(root)` returning
     `pathlib.Path(os.environ["WORKLIST_TRAPS_PATH"])` when set, else
     `pathlib.Path(root) / "docs" / "agent" / "TRAPS.md"`. **Rename, do not keep the
     old name** — a function called `agent_traps_path` that no longer resolves under
     `agent_root` is the "wrong comment" trap from the corpus itself.
   - `trap_headings(root)` → `(list, problem)`. `problem` is `None`, or
     `"missing"`, or `"unreadable: %s" % exc`. Distinguish them: `Path.exists()` before
     the read, `except OSError as exc` after.
   - Raise the cap to `TRAP_HEADING_CAP = 120` and make overflow visible: when the file
     holds more `## ` lines than the cap, append a final synthetic entry
     `"(+%d more traps not shown; read %s)"`. Keep file order. *(This sub-item is
     separable — it can be dropped without affecting anything else in the plan — but it
     closes finding 4, and the merge alone eats 58% of the old ceiling.)*
   - Update the block comment at `:102-107` ("TRAPS.md is shared, append-only, and feeds
     the judge headings") to name the new location.

3. **`.claude/hooks/stop/wl_checks.py`**
   - Add `traps_block(root) -> (text, problem)`; single renderer.
   - `handle_post_compact` (`:1480-1508`): replace the local join at `:1481`; both the
     `no-branch` arm (`:1484`) and the briefing arm (`:1502-1508`) consume it. The path
     argument at `:1506` becomes `S.traps_path(root)` and needs no other change.
   - Judge call site (`:3269`): pass the rendered text. Update the adjacent comment
     (`:3266-3268`, "~145 tokens today") — it will be ~220 at 23 entries.
   - New violation next to the `docs-drift` one (`:2718-2720`), using `always=True`.

4. **`.claude/hooks/stop/wl_judge.py`** — `run_judge(..., traps=None)` now takes the
   rendered string; delete the join and the `"  (none recorded)"` fallback at `:323`
   (keep a `traps or "  (none recorded)"` guard **only** if a direct caller with no
   root exists; the suite's synthetic prompt build in case 153d is the one such caller
   and §6 rewrites it, so prefer deleting the fallback outright).

5. **`.claude/hooks/stop/worklist_messages.py`**
   - Add `TRAPS_ALARM` and `V_TRAPS_MISSING`. `V_TRAPS_MISSING` must carry the exact
     repair command (`git checkout -- docs/agent/TRAPS.md`) and say why it blocks.
   - Repoint prose: `:265` (`V_AGENT_STATE`), `:1230` (`CTX_POSTCOMPACT_MISSING`),
     `:1241` (`CTX_POSTCOMPACT_NO_BRANCH`), `:1253` (`CTX_POSTCOMPACT_BRIEFING`),
     `:1410` (`JUDGE_PROMPT`) — every literal `.agent/TRAPS.md` becomes
     `docs/agent/TRAPS.md`. Assertion D in §6 fails while any remains.

6. **`.claude/hooks/stop/test-worklist-v5.sh`** — §7.

7. **`.ci/scripts/quality/check-trap-corpus.sh`** (new) — §6.

8. **`package.json`** — `"check:ci-trap-corpus": ".ci/scripts/quality/check-trap-corpus.sh"`,
   placed beside `check:ci-probe-parity` (`:62`).

9. **`scripts/ci-runner/manifest.ts`** — two entries, matching the shapes at `:118` and
   `:388`:
   - `{ id: 'check:ci-trap-corpus', run: 'npm run check:ci-trap-corpus', gate: true, leaves: ['.ci/scripts/quality/check-trap-corpus.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-static', step: 'Trap corpus is single and canonical' } }`
   - `{ id: 'gate-test:trap-corpus', run: '.ci/scripts/test/gates/test-trap-corpus.sh', gate: true, qualityGateTest: true, leaves: ['.ci/scripts/test/gates/test-trap-corpus.sh'], ci: { kind: 'step', workflow: '.github/workflows/ci-quality.yml', job: 'quality-security', step: 'Quality-gate unit tests' } }`
   - The `gate-test:` prefix on the second is mandatory: `check-gate-id-convention.sh`
     reds on a manifest entry whose `run` resolves to a `gates/` script under any other
     id, and on a redundant npm alias for it.

10. **`.github/workflows/ci-quality.yml`** — add the step named exactly
    `Trap corpus is single and canonical` to the `quality-static` job (model it on
    "Capability-probe parity", `:285`). The gate test `test-trap-corpus.sh` needs no
    step; `run-all.sh` globs `test-*.sh`.

11. **`.ci/scripts/test/gates/test-trap-corpus.sh`** (new) — §7.

12. **`CLAUDE.md:593-596`** — extend the TRAPS bullet: it is also the corpus the Stop
    hook feeds to the judge and to the PostCompact briefing, so appending here is how a
    trap reaches the tooling, and a `## ` heading must be a self-contained claim because
    the headings are read by machine.

13. **Comment-only path fixes** — `.claude/hooks/pre-edit/block-agent-state-shape.sh:20-21`
    and `:53`, `.ci/scripts/quality/check-probe-parity.sh:16`. Assertion D reds while
    these hold the old literal.

14. **`.agent/README.md`** (gitignored, local-only) — the lifetime table's *Forever* row
    points at `docs/agent/TRAPS.md`, and the "Why TRAPS.md is the exception" section says
    it now lives in git *because* it is the exception. Note in the commit message that
    this edit cannot ship, which is itself the argument for the move.

15. **`mv .agent/TRAPS.md .agent/archive/TRAPS.pre-unify.md`** — last, and only after
    step 1 is verified at 23 headings. **Move, never delete**: the file is gitignored, so
    there is no copy anywhere and no `git checkout` that brings it back. The archive
    location satisfies assertion C (which checks `.agent/TRAPS.md` exactly) while keeping
    the bytes.

---

## 5. Merge plan

### 5.1 Arithmetic

15 (`.agent`) + 9 (`docs`) − 1 shared = **23 headings** in the merged file. The shared
entry's bodies are byte-identical, so nothing is chosen or lost on it.

### 5.2 Order and conflict rule

**`.agent/TRAPS.md` wins on any conflict of content**, because it is the file the tooling
has actually been reading and the one whose entries carry run ids. There is exactly one
conflict candidate and it is identical text, so the rule costs nothing today; it exists
so a future re-merge has an answer.

Layout of the merged file:

1. `# Traps` + rewritten charter (§5.3).
2. The **8 non-shared `docs/` entries**, in their current order, `A wrong comment is
   more dangerous…` through `A cancelled run is not a passed run…`.
3. The **15 `.agent/` entries**, in their current file order, `The review tooling comes
   from main` through `` `git diff <branch>` reads as DELETED… ``.

8 + 15 = 23. The shared entry is dropped from the `docs/` block and kept in the `.agent/`
block, where it already sits last. That preserves both files' internal orders *and*
lands the newest entry (2026-08-09) at the bottom, honouring "Newest at the bottom"
(`.agent/TRAPS.md:11`) without reordering anything else.

### 5.3 The charter rewrite (the one editorial step)

Replace `docs/agent/TRAPS.md:3-10`. The new preamble must:

- keep the *fooled* vs *blocked* framing from `:3-5` — it is the sharpest line either
  file has, and `CLAUDE.md:593` quotes it;
- **drop the "mechanics of a specific subsystem do not belong here" exclusion**, which
  five incoming entries violate. Replace it with the durable version of the same idea:
  *reference* material (how a gate works, what a suppression means) stays in
  `ci-gates.md` / `suppressions.md`; an entry here records **a belief that turned out
  false and what it cost**. Every one of the 23 fits that;
- carry the append-only rule verbatim from `.agent/TRAPS.md:3-11`, including "Newest at
  the bottom" and "a trap without a run id or a `file:line` is a rumour";
- state the new machine-read constraint: the `## ` titles are read by the Stop hook and
  handed to the judge and to compacted sessions, so a heading must be a self-contained
  claim. "Another CI gotcha" is now a defect, not a style opinion.

### 5.4 Near-duplicates: four pairs, all kept

None of the 23 is redundant. Four pairs share a family and must both survive; merge the
prose and you delete a citation, and a citation is what separates a trap from a rumour
(`.agent/README.md`). Add a one-line cross-reference to each side instead:

| Pair | Why both stay |
|---|---|
| `A gate can pass on the exact body it was written to reject` ↔ `A check that cannot fail is not evidence` | Same vacuity family, opposite ends: one is a concrete grep that accepts `{"e2e":{"keys":[]}}`, the other is the general control-first rule with three independent instances. |
| `A watch verdict is not evidence` ↔ `A cancelled run is not a passed run` | One carries the drop-rate data (4 of 4) and the 42→48 job growth; the other carries the run-vs-job `--jq` fix and the three-rounds-measured-nothing cost. Different remedies. |
| `A failed existence check with the WRONG PATH proves nothing` ↔ `` `git diff <branch>` reads as DELETED… `` | The second already ends "Same class as a failed existence check with the wrong path" — a cross-reference that, until the merge, pointed at an entry in the other file. Resolving it is the clearest single proof the split was costing something. |
| `A ruling from an artifact is a hypothesis` ↔ `A watch verdict is not evidence` | General (any artifact, any author) vs specific (the CI watch). The general one is where a session looks when the artifact is not a watch. |

### 5.5 Verification after merge (run it, do not eyeball it)

```bash
grep -c '^## ' docs/agent/TRAPS.md      # must print 23

python3 - <<'EOF'
import re, pathlib
def titles(p):
    return {b.split('\n',1)[0].strip()
            for b in re.split(r'(?m)^## ', pathlib.Path(p).read_text())[1:]}
old = titles('.agent/archive/TRAPS.pre-unify.md') | titles('docs/agent/TRAPS.md')
new = titles('docs/agent/TRAPS.md')
print('lost:', sorted(old - new))          # must be []
print('count:', len(new))                  # must be 23
EOF
```

Run the second block **before** step 15's move against `.agent/TRAPS.md`, and again
after against the archived path. "lost: []" with a count of 23 is the whole acceptance
criterion for §5.

---

## 6. The anti-resplit gate

`.ci/scripts/quality/check-trap-corpus.sh`, wired at `check:ci-trap-corpus`.

**Seam:** the gate accepts `--root <dir>` (default: the repo root). This exists so the
gate's own control can run against a `mktemp` fixture and **never writes into the real
tree** — the hazard `run-all.sh:16-30` documents for the two existing writer tests.

**Assertions:**

- **A — CANONICAL PRESENT.** `docs/agent/TRAPS.md` is tracked
  (`git ls-files --error-unmatch`) and holds at least `TRAP_FLOOR=23` `## ` headings.
  Append-only means the count can only rise, so the floor doubles as "no trap was
  deleted". Also closes the vacuity hole: an emptied file cannot pass.
- **B — EXACTLY ONE TRACKED CORPUS.** `git ls-files` yields exactly one path matching
  `(^|/)TRAPS\.md$`, and it is the canonical one.
- **C — NO UNTRACKED LOCAL CORPUS.** `.agent/TRAPS.md` must not exist on disk. Fires
  locally (where the stale copy lives); vacuous in CI, which is why D exists.
- **D — NO STALE REFERENCES.** `git grep -n -- '\.agent/TRAPS\.md'` returns nothing.
  The gate script itself is the single permitted exception and must be excluded by an
  exact-path match, never a pattern — a pattern is how an exception list starts. This is
  the assertion with teeth in CI: it catches a hook, a message, a doc, or a comment
  repointed at the old path.
- **E — HOOK AGREEMENT.** With `WORKLIST_TRAPS_PATH` **unset**, import `wl_store` and
  require `traps_path(root)` to equal the canonical path, and `trap_headings(root)` to
  return `problem is None` with a heading count equal to the file's own
  `grep -c '^## '` (capped at `TRAP_HEADING_CAP`). Without E the gate polices a file the
  hook might not read — a check that cannot fail on the defect that matters most.

**Self-control (runs first; if the plant passes, the gate exits non-zero without judging
the real tree):** copy the four inputs into a `mktemp -d` fixture, plant a second
`TRAPS.md`, and require a red. The control targets B specifically because a second
corpus appearing is the failure this gate is named for.

**Exact mutations that must turn it red** (each verified by running the gate, not by
reading it):

| Mutation | Assertion |
|---|---|
| `cp docs/agent/TRAPS.md .agent/TRAPS.md` | C |
| `git add` a second `TRAPS.md` anywhere (e.g. `docs/foo/TRAPS.md`) | B |
| Revert `wl_store.traps_path` to `agent_root(root) / "TRAPS.md"` | E (and D, once the literal returns) |
| Re-add the string `.agent/TRAPS.md` to any tracked file | D |
| Delete two entries from the canonical file | A (count below floor) |
| `rm docs/agent/TRAPS.md` | A |

**House rules the script must obey** (all are entries in the corpus it guards): no
`2>/dev/null`; no `|| true` around a grep whose emptiness is the verdict — use an
explicit `if ! out=$(...)` so `check-silent-failure-patterns.sh` and
`check-swallowed-failures.sh` stay quiet on it; helpers defined at the top; formatted
with `shfmt -i 4 -ci`.

---

## 7. Test plan

House style: every case plants the defect, asserts the FIRE, then re-runs clean and
asserts SILENCE.

### `.claude/hooks/stop/test-worklist-v5.sh`

**Fixture moves.** Cases 20 (`:526`) and 153d (`:4176`) currently write
`$BASE/proj/.agent/TRAPS.md`. Both become `mkdir -p "$BASE/proj/docs/agent"` +
`$BASE/proj/docs/agent/TRAPS.md`. `setup` (`:82-83`) already `rm -rf "$BASE"`, so no
cleanup changes.

**Amended cases:**

- **20 — PostCompact still carries headings.** Keep every existing assertion (title
  present, `body detail here` absent) against the new path; this is the brief's "the
  PostCompact briefing still carries headings" requirement. **Add the control**: with no
  corpus file at all, the briefing must contain the alarm text *and must not contain*
  `(none recorded)`.
- **153d — titles-only.** Unpack the two-tuple. Keep titles-only / no-body / no-`###`.
  Replace `absent-file-empty-list` with `absent-file-problem-set`
  (`heads == [] and problem is not None`). Build the judge prompt through the single
  renderer, not by hand, so the case cannot pass while the real call site is wrong.

**New cases:**

- **A missing corpus BLOCKS and names the repair.** No `docs/agent/TRAPS.md`; `run`;
  expect a block containing the path and `git checkout --`. *Control:* write a file with
  one heading, re-run, assert that violation is absent.
- **The judge never hears `(none recorded)` about a missing corpus.** Render through
  `traps_block` with the file absent: alarm present, literal `(none recorded)` absent.
  *Control:* with a populated file the alarm is absent and the titles are present.
- **Overflow is visible.** Plant `TRAP_HEADING_CAP + 3` headings: the list is capped and
  its last element is the `(+3 more …)` marker. *Control:* at `CAP - 1` headings no
  marker appears. (Skip this case if the cap sub-item in §4.2 is dropped.)
- **ARITY, case 117.** Add to the map at `:2489-2588`:
  `"V_TRAPS_MISSING": ("p", "e", "c")` and `"TRAPS_ALARM": ("p", "e")`, matching the
  actual call sites. The gap check at `:2601` fails on any unregistered constant, so
  omitting these is a designed suite failure, not an oversight.

### `.ci/scripts/test/gates/test-trap-corpus.sh`

One case per row of the §6 mutation table, each against a `mktemp` fixture, plus a
clean-tree case asserting exit 0 and a vacuity case asserting that an **empty** fixture
reds rather than passing. Summary line must end `passed=<n> failed=<m>` —
`test-worklist-hooks.sh:68` and `run-all.sh` both parse that shape, and a harness that
changes it reads as broken rather than green.

### Local run commands

```bash
bash .claude/hooks/stop/test-worklist-v5.sh 2>&1 | tail -5
bash .ci/scripts/test/gates/test-worklist-hooks.sh
bash .ci/scripts/quality/check-trap-corpus.sh
bash .ci/scripts/test/gates/test-trap-corpus.sh
bash .ci/scripts/quality/check-python-lint.sh          # ruff lint AND format
npm run check:ci-shell-format                          # shfmt -i 4 -ci
npm run check:ci-gate-id-convention
npm run check:ci-gate-reachability-coverage
npm run check:ci-dead-bash
bash .ci/scripts/test/gates/test-ci-parity.sh          # manifest ↔ workflow step names
```

Read stdout and stderr separately on the two harnesses — `test-worklist-v5.sh` has
shipped a `253 passed, 0 failed` while three assertions wrote `pass: command not found`
to stderr (it is an entry in the corpus being merged).

---

## 8. Risk

**Blast radius: every stop in the repo.** Three consumers, all read-only over one text
file; nothing writes it. Ranked by what can actually go wrong:

1. **A wrong `traps_path` wedges every session** (new, and the only genuinely dangerous
   part). The violation blocks, so a path typo would block every stop until someone
   reads the message. Three mitigations, in order of who hits them first:
   `WORKLIST_TRAPS_PATH=<any readable file>` unwedges a session in one command; the
   violation text carries the exact repair; and assertion E turns a wrong default red in
   `npm run ci` rather than in a live session. If the reviewer wants belt and braces,
   downgrade the violation to advisory for one wave — but then the fresh-clone hole is
   only half closed, and the CI gate is doing all the work.
2. **The judge losing its traps block** degrades one section of a prompt that also
   carries remaining items, leases, citations and the session's message. It cannot flip
   a verdict to `stop` on its own; it makes the judge slightly worse at telling a real
   constraint from an excuse. Failure here is a quality loss, not an outage.
3. **PostCompact** emits `additionalContext` only (`wl_checks.py:1527-1530`). A defect
   there degrades a briefing; it never blocks a stop.
4. **Merge loss** is the irreversible one, because `.agent/TRAPS.md` is gitignored and
   has no second copy. Handled by the move-don't-delete rule (§4.15) and the
   `lost: []` check (§5.5), which must pass before the move.

**What makes it safe to land:** the change is inert until step 4.2 flips the path, and
every earlier step is additive. The two harnesses cover all three consumers today
(cases 20 and 153d), so a regression in the rendering is caught by tests that already
exist rather than by tests written alongside the change. The new gate has a self-control
that runs before it judges anything, so it cannot go quietly green.

**Two things the implementer will meet that this plan does not cause:**

- `docs_drift` (`wl_checks.py:710-732`) counts commits touching `.ci .github .claude`
  (`PROGRAM_SURFACE`, `:63`) since `docs/ci-overhaul` last moved (`DESIGN_DOCS`, `:59`),
  and blocks over 10. This change touches two of those three trees.
- `check_scope_completeness.py` refuses a verdict when a declared submodule is missing
  from disk, so the quality lane needs the submodules checked out to run clean locally.
