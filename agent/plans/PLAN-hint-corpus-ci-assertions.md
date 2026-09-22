# PLAN: check_hint_corpus.py, the control-first liveness gate for the behavioral-hint corpus
Status: draft
Owner: d778be9d
Updated: 2026-09-22

## 0. Scope

`PLAN-stop-hook-behavioral-hints.md` landed its core implementation across three commits already on `0914-1` (`004b5dba1` feat, `1581e5334` test, `8a607c960` docs) and has two open boxes left:

- Write `.ci/scripts/quality/check_hint_corpus.py` with assertions H1-H7 from that plan's section 6.3, control-first.
- Wire `check:ci-hint-corpus` at the three registration points and confirm `scripts/gates/check-ci-parity.ts` is green.

This plan designs both.
It does not touch `wl_hints.py`, `HINTS.md`, or the stop-hook wiring, all of which are already landed and verified by `.claude/rediacc_hooks/tests/test_wl_hints.py` (311 lines, already in the tree, `test_load_corpus_reads_the_real_twelve_entries_clean` confirms the live corpus parses to exactly 12 entries with unique ids, non-empty sources and `Status: active`).

**Branch.** This rides the current branch, `0914-1`.
`git log --oneline -5` shows the three landing commits as the branch tip; `gh pr list --head 0914-1 --state all` shows only `#589`, already `MERGED`, and `git status --porcelain` shows no open PR state, only the session's own worklist bookkeeping files modified (`agent/d778be9d/STATE.md`, `agent/ledgers/census-claim-check.jsonl`, `agent/worklist/d778be9d.jsonl`).
Nothing about starting a fresh PR is needed; this is a continuation of the same branch's own unfinished checklist, and the new gate's commits belong in the same lineage as the feature they gate.

## 1. What already exists and must be read, not re-derived

`.claude/hooks/stop/wl_hints.py` (already landed, no changes needed here):

- `HINTS_REL = "docs/agent-reference/HINTS.md"` at `wl_hints.py:27`
- `TRAILER_KEYS = ("Hint-Id:", "Source:", "Status:")` at `wl_hints.py:32`
- `hints_path(root)` at `wl_hints.py:38`
- `load_corpus(path) -> (entries, errors)`, never raises, at `wl_hints.py:46`. **Load-bearing detail the gate must not re-derive:** the validation loop at the tail of `load_corpus` (roughly `wl_hints.py:88-104`) already reports an empty heading, a missing `Hint-Id`, a missing `Source`, and a **duplicate `Hint-Id`** as entries in the returned `errors` list -- but it does **not** remove the offending row from the returned `entries` list, it only skips adding it to the internal `seen_ids` set. So a corpus with a duplicate id returns both the error string and two rows carrying the same id. The gate must surface `load_corpus`'s own `errors` as findings directly rather than re-implementing duplicate detection, and must build the H1/H5/H6 "active" set from `entries` filtered by `status == "active"` exactly as `hint_pick` does.
- `hint_pick(entries, ledger, rng=None) -> (entry, index, total) | None` at `wl_hints.py:105`
- `render(entry, index, total)` at `wl_hints.py:129`

`docs/agent-reference/HINTS.md`: 12 `## ` entries, all `Status: active`, confirmed clean against the schema at `HINTS.md:10-21`.
The longest heading (`investigate-with-fan-out`) is **exactly 160 characters** -- this is a live boundary case in the real corpus today, not a hypothetical one, and it means an off-by-one in H4's length comparison (`< 160` instead of `<= 160`) will red the real corpus immediately.
Verified: `grep "^## "` over the file, longest line is 160 chars, matching the schema's own `<= 160 chars` at `HINTS.md:12`. No heading in the real corpus contains a first- or second-person pronoun (checked with a case-insensitive word-boundary grep over all 12 headings, zero hits).

`.claude/hooks/stop/wl_planrec.py`:

- `RESOLVE_KINDS = ("blob", "tree", "commit", "ancestor", "fileline", "gate", "plan", "trap")` at `wl_planrec.py:303`
- `resolve(root, kind, token) -> (ok, detail)` at `wl_planrec.py:323`. For this gate's purposes: `kind="fileline"` defers to `wl_checks.citation_state` (`wl_planrec.py:371-374`), which needs the token as a bare `<path>:<line>` -- e.g. `CLAUDE.md:53`, not `file:CLAUDE.md:53`; `kind="trap"` checks membership in `Trap-Id:` lines of `TRAPS.md` (`wl_planrec.py:393-397`); `kind="gate"` checks `package.json`'s `scripts` block (`wl_planrec.py:375-379`); `kind="plan"` checks `agent/PLAN-*.md` across four folders (`wl_planrec.py:380-392`).

**The schema's `file:`/`gate:`/`trap:`/`plan:` prefixes are not `resolve`'s own vocabulary; they are `HINTS.md`'s own grammar layered on top.** No existing module splits a `Source:` value like `"file:CLAUDE.md:53, file:CLAUDE.md:59"` into `[("fileline", "CLAUDE.md:53"), ("fileline", "CLAUDE.md:59")]`.
`check_decision_ids.py:188` calls `R.resolve(root, "fileline", src)` directly because its `Source` column is bare `file:line` with no kind prefix at all; `check_plan_citations.py`'s `citations()` (`check_plan_citations.py:335-372`) extracts kind-tagged tokens by regex over free prose, which is the wrong shape for a structured, comma-separated trailer field.
So H3 needs a small, local, honest split -- comma-separate, then split each pointer on its first `:` into a prefix and a remainder, map `{"file": "fileline", "gate": "gate", "trap": "trap", "plan": "plan"}`, and call `R.resolve(REPO_ROOT, kind, remainder)`.
This is four lines of string handling, not a second resolver, and it is the one piece of this gate with no existing precedent to model directly -- everything else is a direct copy of `check_agent_hint_liveness.py`'s shape.

Verified all nine `CLAUDE.md` line citations the real corpus carries still land on the sentence they were written for: lines 44, 53, 55, 59, 87, 119, 126, 133, 135, 161 all read as the plan's own table describes.
Verified all four `trap:` ids the real corpus cites exist in `TRAPS.md`: `check-cannot-fail` (`TRAPS.md:49`), `ruling-from-an-artifact-is-a-hypothesis` (`TRAPS.md:67`), `read-stdout-and-stderr-separately` (`TRAPS.md:531`), `read-the-history-before-you-guess` (`TRAPS.md:1028`).

`worklist_messages.py:1366` -- `N_BEHAVIOR_HINT = "TIP (hint %d of %d, rotating): %s [%s -- %s]"`, confirming `render`'s five-argument shape; not touched by this gate but useful for a reader checking the gate against the live rendering.

Env seam already registered (task already ticked in the parent plan, re-verified here): `WORKLIST_HINTS_FILE` appears in `.ci/policy/worklist-env-registry.json:298` and `.ci/config/env-manifest.json:860`.
This gate does not need it -- `load_corpus(path)` takes an explicit path argument, so fixtures are driven the same way `check_agent_hint_liveness.py` drives `wl_agents.load_corpus(tmp)`, by passing a fixture path directly rather than setting the env var.

## 2. The model, traced precisely

`.ci/scripts/quality/check_agent_hint_liveness.py` (529 lines) is the named model. Its shape, mapped onto the new gate:

| Model | Role | New gate |
|---|---|---|
| `die()` (`:80-82`) | loud single-exit failure | copy verbatim |
| `agent_names()` (`:85-86`) | universe of real inputs | N/A -- hints have no filesystem universe outside the one corpus file |
| `load_matcher()` (`:89-113`) | import the module under test through `paths.on_sys_path`, with a frozen-contract `hasattr` check per function | `load_hints()`, same shape, checking `hints_path`, `load_corpus`, `hint_pick`, `render` exist on `wl_hints` |
| `resolve_thresholds()` (`:116-131`) | pull numeric knobs from the module rather than re-declaring them | N/A -- `hint_pick` has no threshold, only `MIN_HINTS` which the gate itself declares (the plan text names it as this gate's own floor, not an imported hook constant) |
| `evaluate()` (`:140-211`) | per-entry findings over the real corpus | `judge_corpus()`, covering H1-H4 |
| `controls_fired()` (`:222-284`) | plant defects, judge a synthetic fixture, collect what the evaluator MISSED | `controls_fired()`, six plants (one per H1-H4 plus two for H5/H6) plus a `CONTROL 0` healthy pass, same "return the list of what was missed" contract |
| `main()` (`:312-524`) | vacuity guard, then `controls_fired()` before any real verdict, then the real verdict, then a success line naming the shape | same order, same refusal-before-verdict structure |

The one place the new gate cannot copy the model verbatim is `evaluate()`'s SPECIMENS table, because hint liveness is not a per-entry relevance question (H5/H6 test the whole corpus's rotation as one property, not each entry individually). H5/H6 get their own driver function, `cycle_findings()`, described in section 3.

## 3. The gate: `.ci/scripts/quality/check_hint_corpus.py`

### 3.1 Header

```python
#!/usr/bin/env python3
"""check:ci-hint-corpus -- the behavioral-hint corpus is well-formed and its rotation actually rotates.

WHY THIS EXISTS. `docs/agent-reference/HINTS.md` is hand-curated prose read by
`wl_hints.hint_pick` on every allow-path stop; nothing about its shape is enforced except
by this gate. Same governing principle as `check_agent_hint_liveness.py`, its named model:
"A healthy matcher on a quiet stop emits nothing, exactly like a broken one. Counting hints
cannot separate them." A rotation that always emits the SAME hint, or that silently drops
one from the cycle, looks identical from the stop report's own output to a healthy one --
the report shows one line either way. So this gate drives `hint_pick` directly, over the
whole cycle, and asserts every active entry is actually reachable and the cycle actually
repeats.

CONTROL-FIRST, same shape as the model. Before the real corpus is judged at all, every
assertion below is driven against a synthetic fixture carrying one planted defect apiece --
a corpus under the population floor, a duplicate id, a malformed id, an oversized or
first-person heading, a Source pointing at a file that does not exist, and a hint_pick
stubbed to return a constant -- plus one healthy fixture that must stay silent under all
six. If any plant is not caught, this gate declares itself broken and exits non-zero WITHOUT
judging the real corpus.

Design: agent/plans/PLAN-stop-hook-behavioral-hints.md section 6.3;
agent/plans/PLAN-hint-corpus-ci-assertions.md (this gate's own design).

---- gate ----
step: Behavioral hints can actually fire
needs: none
selftest: true
lane: quality-content
---- end gate ----
"""
```

`selftest: true` on a `.py` leaf is inert for `gate-bind`'s binding purposes (`scripts/gate-bind.ts:1001-1002` states plainly that the flag only changes the derived `run:` command for `.ts` files), but it is kept because the model gate carries it too and the field documents intent even where the binder does not act on it -- consistent, not misleading, since nothing here claims a separate `--selftest` invocation exists.

### 3.2 Constants

```python
REPO_ROOT = <same os.path.abspath(...) pattern as the model, :35>
HOOK_DIR = os.path.join(REPO_ROOT, ".claude", "hooks", "stop")
HINTS_FILE = os.path.join(REPO_ROOT, "docs", "agent-reference", "HINTS.md")

MIN_HINTS = 8          # H1, the number section 6.3 names literally
ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{2,48}$")   # H2
HEADING_MAX = 160       # H4, matches HINTS.md's own schema line at HINTS.md:12
PRONOUN_RE = re.compile(
    r"(?<![\w'-])(i|i'm|i've|i'd|i'll|me|my|mine|myself|you|you're|you've|you'll|"
    r"your|yours|yourself|we|we're|we've|us|our|ours)(?![\w'-])",
    re.IGNORECASE,
)
POINTER_KIND = {"file": "fileline", "gate": "gate", "trap": "trap", "plan": "plan"}
```

### 3.3 `load_hints()`

Same shape as `load_matcher()` (`check_agent_hint_liveness.py:89-113`): guard `HOOK_DIR` exists, guard `wl_hints.py` exists with a named `die()` message, `paths.on_sys_path(HOOK_DIR)`, import `wl_hints` inside a `try/except ImportError`, then `hasattr` over `("hints_path", "load_corpus", "hint_pick", "render")` -- the frozen contract this gate depends on, so a rename reds here with a clear message rather than an `AttributeError` traceback three functions later.
Also import `wl_planrec as R` the same way `check_decision_ids.py:79` and `check_plan_citations.py:96` do, guarded the same way.

### 3.4 `source_pointers(value)`

```python
def source_pointers(value):
    """[(kind, token), ...] for one Source: field, or [(None, ptr)] for an unrecognised prefix."""
    out = []
    for raw in (value or "").split(","):
        ptr = raw.strip()
        if not ptr:
            continue
        prefix, sep, rest = ptr.partition(":")
        kind = POINTER_KIND.get(prefix)
        out.append((kind, rest.strip() if sep and kind else ptr))
    return out
```

### 3.5 `judge_corpus(entries, parse_errors)` -- H1 through H4

```python
def judge_corpus(hints_mod, entries, parse_errors):
    out = list(parse_errors)   # load_corpus's own errors: empty heading/id/source, duplicate id -- half of H2
    active = [e for e in entries if e.get("status") == "active"]

    # H1 population floor
    if len(active) < MIN_HINTS:
        out.append(
            "POPULATION FLOOR: %d active entries, under MIN_HINTS=%d. An emptied, "
            "truncated or relocated corpus reds instead of passing vacuously."
            % (len(active), MIN_HINTS)
        )

    for e in entries:
        eid = e.get("id") or ""
        heading = e.get("heading") or ""
        # H2 identity: format, over and above load_corpus's own duplicate/empty checks
        if eid and not ID_RE.match(eid):
            out.append("MALFORMED ID: %r does not match ^[a-z0-9][a-z0-9-]{2,48}$" % eid)
        # H3 grounding
        if eid and e.get("source"):
            for kind, token in source_pointers(e["source"]):
                if kind is None:
                    out.append("%s: Source pointer %r carries no recognised kind prefix" % (eid, token))
                    continue
                ok, why = hints_mod is None and (False, "") or R.resolve(REPO_ROOT, kind, token)
                if not ok:
                    out.append("%s: Source %s:%s does not resolve -- %s" % (eid, kind, token, why))
        # H4 shape
        if heading:
            if len(heading) > HEADING_MAX:
                out.append("%s: heading is %d chars, over %d" % (eid or "?", len(heading), HEADING_MAX))
            m = PRONOUN_RE.search(heading)
            if m:
                out.append("%s: heading carries the pronoun %r" % (eid or "?", m.group(0)))
    return out
```

(The `hints_mod is None and ...` guard above is pseudocode noise; the real implementation just calls `R.resolve` directly -- shown fully here so the branch reads correctly, but the actual gate does not need the ternary at all since `R` is always imported before this function runs.)

### 3.6 `cycle_findings(pick_fn, entries)` -- H5 and H6

```python
def cycle_findings(pick_fn, entries):
    """Findings from driving pick_fn(entries, ledger) for one full cycle plus one more pick.

    pick_fn defaults to wl_hints.hint_pick; a control passes a stub instead, so this same
    function is both the real gate's H5/H6 judge and the thing CONTROL 5 proves can fail.
    """
    active = [e for e in entries if e.get("status") == "active"]
    if not active:
        return []  # H1 already reports an empty/under-floor corpus; this function does not pile on
    ledger = {}
    picks = []
    for _ in range(len(active)):
        got = pick_fn(entries, ledger)
        if got is None:
            return [
                "H5: hint_pick returned None before a full cycle of %d active entries "
                "completed (picked %d)" % (len(active), len(picks))
            ]
        entry, _index, _total = got
        picks.append(entry["id"])
    out = []
    if len(set(picks)) != len(picks):
        out.append("H5: hint_pick repeated an id inside one cycle: %r" % picks)
    active_ids = {e["id"] for e in active}
    if set(picks) != active_ids:
        out.append(
            "H5: hint_pick never surfaced %s over one full cycle" % sorted(active_ids - set(picks))
        )
    extra = pick_fn(entries, ledger)
    if extra is None:
        out.append("H6: hint_pick returned None immediately after a full cycle; the rotation must repeat forever")
    elif extra[0]["id"] == picks[-1]:
        out.append(
            "H6: the pick right after a cycle boundary repeated the hint that just closed "
            "the cycle (%s), which a back-to-back repeat must never do" % picks[-1]
        )
    return out
```

This is order-invariant by construction -- it asserts a SET equals a SET, not a sequence -- so it needs no seeded `random.Random` and cannot be flaky in CI. `pick_fn` defaults to `hints_mod.hint_pick` (unseeded module `random`) in the real-corpus run, and to a constant stub in CONTROL 5.

### 3.7 `controls_fired(hints_mod)` -- H7

Same contract as the model's `controls_fired()` (`check_agent_hint_liveness.py:222-284`): builds one healthy fixture and six planted-defect fixtures, judges each with the SAME `judge_corpus`/`cycle_findings` functions the real corpus will be judged with, and returns the list of plants that were **not** caught. `main()` refuses to judge the real corpus if this list is non-empty.

A helper writes one `HINTS.md`-shaped fixture to a temp path and returns `(entries, parse_errors)` via `hints_mod.load_corpus(path)`, exactly mirroring the model's `judge()` closure at `check_agent_hint_liveness.py:238-248`.

**The healthy fixture** (used for CONTROL 0 and as the base every plant mutates one property of): 9 entries (one above `MIN_HINTS`, so a plant that trims one entry to breach the floor is a single deletion, not a full rewrite), unique kebab-case ids, headings between 40 and 150 characters with no pronoun, and `Source:` pointers built only from things already true of this repository so they resolve without needing a second fixture tree -- `file:CLAUDE.md:1` (line 1 of `CLAUDE.md` will exist as long as the file is non-empty, which `check:ci-plan-*`-class gates already assume elsewhere) and `trap:check-cannot-fail` (stable, cited by the real corpus itself).
`R.resolve`'s `root` argument is always `REPO_ROOT`, the real checkout, never the fixture's own temp directory -- fixtures replace only the `HINTS.md` file being parsed, not the file tree the pointers are checked against.

**CONTROL 0 -- the healthy fixture must be silent.** `judge_corpus(entries, errors) == []` and `cycle_findings(hints_mod.hint_pick, entries) == []`. If not, `die()` immediately, naming the findings, before any plant is trusted (identical reasoning to the model's own CONTROL 0 at `check_agent_hint_liveness.py:250-256`: "every planted-defect result below is meaningless" otherwise).

**CONTROL 1 (H1).** The healthy fixture with entries trimmed to 3. Must produce a finding starting with `"POPULATION FLOOR"`. Everything else about the 3 remaining entries stays valid (unique ids, resolving sources, in-bounds headings), so a miss here can only mean the floor check itself is broken, not a knock-on from some other rule.

**CONTROL 2 (H2a, duplicate).** The healthy fixture with entry 2's `Hint-Id:` rewritten to equal entry 1's. Must produce a finding from `load_corpus`'s own `errors` list containing the word `"duplicate"` (verifying the gate actually surfaces what `load_corpus` already reports, rather than silently discarding it).

**CONTROL 3 (H2b, malformed id).** The healthy fixture with one `Hint-Id:` changed to `Record_The_Order` (uppercase, underscore -- both outside `[a-z0-9-]`). Must produce a finding starting with `"MALFORMED ID"`.

**CONTROL 4 (H3).** The healthy fixture with one `Source:` changed to `file:docs/agent-reference/DOES-NOT-EXIST-PLANTED.md:1`. Must produce a finding containing `"does not resolve"`.

**CONTROL 5 (H4).** The healthy fixture with one heading rewritten to `"Should remember to check the artifact"` (a second-person pronoun) AND, as a second plant sharing the control, one heading padded to 161 characters. Both must fire, independently checked so a fix for one cannot mask a miss on the other.

**CONTROL 6 (H5/H6, the stubbed matcher).** Not a corpus mutation -- an instrument substitution, matching the plan's own phrase "a `hint_pick` stubbed to return a constant" verbatim. `pick_fn = lambda entries, ledger: (active[0], 1, len(active))`, ignoring `ledger` entirely. Fed into `cycle_findings(pick_fn, entries)` against the healthy 9-entry fixture.
Must produce **both** an H5 finding (`"never surfaced"`, since only entry 1 is ever returned) and, since the stub also never advances past the constant, no separate H6 finding is guaranteed by this plant alone -- so a second stub variant is also run: `pick_fn` that returns each of the 9 entries once in order then, on the 10th call (the post-cycle pick), returns entry 9 again (the same id that just closed the cycle).
This must produce the H6 finding (`"repeated the hint that just closed the cycle"`). Two stubs, one for each half of the H5/H6 pair, both proven to be catchable before the real `hint_pick` is trusted to avoid them.

If `controls_fired` returns anything, `main()` prints it under a `"CONTROLS DID NOT FIRE"` header (same wording as the model, `check_agent_hint_liveness.py:356-361`) and exits 1 **without** loading or judging the real corpus.

### 3.8 `main()`

1. Vacuity guard: `HINTS_FILE` must exist (`os.path.isfile`), else `"VACUOUS INPUT"` and exit 1, same shape as the model's `AGENTS_DIR` guard (`check_agent_hint_liveness.py:314-321`) -- a missing corpus here is a real defect (unlike inside `wl_hints.load_corpus`, where a missing path is deliberately silent-not-an-error for the hook's own fail-open contract; this gate is not the hook, and a missing `HINTS.md` in CI means the feature shipped with nothing to show).
2. `hints_mod = load_hints()`.
3. `missed = controls_fired(hints_mod)`; if non-empty, report and exit 1.
4. `entries, parse_errors = hints_mod.load_corpus(HINTS_FILE)`.
5. `findings = judge_corpus(hints_mod, entries, parse_errors) + cycle_findings(hints_mod.hint_pick, entries)`.
6. If `findings`, print each, exit 1.
7. Else print a success line naming the shape -- entry count, active count, and "N planted defects were caught first, so this green means the check can fail" (matching the model's closing line at `check_agent_hint_liveness.py:523`) -- and exit 0.

## 4. H1-H7 summary table

| # | Assertion | Planted-defect fixture | Must red with | Clean fixture stays green because |
|---|---|---|---|---|
| H1 | Population floor, `MIN_HINTS=8` | 3 valid, resolving, uniquely-id'd entries | `"POPULATION FLOOR"` | Healthy fixture carries 9 |
| H2 | Identity: id regex + uniqueness | (a) two entries share one `Hint-Id`; (b) one id is `Record_The_Order` | (a) `load_corpus`'s own `"duplicate"` error; (b) `"MALFORMED ID"` | Healthy fixture's 9 ids are distinct and kebab-case |
| H3 | Grounding: every `Source:` pointer resolves via `wl_planrec.resolve` | one `Source:` rewritten to a nonexistent path | `"does not resolve"` | Healthy fixture cites only `CLAUDE.md:1` and `trap:check-cannot-fail`, both real |
| H4 | Shape: heading `<=160` chars, no first/second-person pronoun | one heading at 161 chars; one heading with second-person pronoun | length finding; pronoun finding | Healthy fixture's headings are 40-150 chars, pronoun-free (matching the real corpus, whose longest heading is exactly 160) |
| H5 | Fires: one full cycle covers every active id exactly once | `hint_pick` stubbed to always return entry 1 | `"never surfaced"` | Real `hint_pick`'s round-robin exhausts `shown` before repeating, proven directly against the healthy fixture in CONTROL 0 |
| H6 | Cycle repeats without a back-to-back duplicate | stub returns the 9 entries in order, then repeats entry 9 on pick 10 | `"repeated the hint that just closed the cycle"` | Real `hint_pick` resets `shown` and excludes `last` at the cycle boundary (`wl_hints.py:118-123`) |
| H7 | Control-first ordering | any of the above escapes detection | `"CONTROLS DID NOT FIRE"`, exit 1, real corpus never loaded | N/A -- H7 is the ordering guarantee itself, proven by construction: `main()` calls `controls_fired()` before `load_corpus(HINTS_FILE)` |

## 5. Three-point wiring

Traced against `check:ci-agent-hint-liveness`, the sibling gate in the same lane, as the worked example the plan asked for:

1. **`package.json`.** `check:ci-agent-hint-liveness` sits at `package.json:221` as `"check:ci-agent-hint-liveness": ".ci/scripts/quality/check_agent_hint_liveness.py"` -- the bare path, no `python3` prefix (`scripts/lib/gate-header.ts:331-334`'s docstring: a `python3` prefix makes `check:ci-parity` resolve the leaf to `[python3]` and fail).
   Add, immediately beside it or wherever alphabetical grouping in that block prefers:
   ```
   "check:ci-hint-corpus": ".ci/scripts/quality/check_hint_corpus.py",
   ```
   The new file needs `chmod +x` and a `#!/usr/bin/env python3` shebang -- both `check_agent_hint_liveness.py` and `check_decision_ids.py` are `-rwxr-xr-x` on disk; a non-executable leaf run as a bare path fails immediately.

2. **`scripts/ci-runner/manifest.ts`.** The sibling's entry spans `manifest.ts:2380-2391`:
   ```
   {
     id: 'check:ci-hint-corpus',
     run: 'npm run check:ci-hint-corpus',
     gate: true,
     leaves: ['.ci/scripts/quality/check_hint_corpus.py'],
     ci: {
       kind: 'step',
       workflow: '.github/workflows/ci-quality.yml',
       job: 'quality-content',
       step: 'Behavioral hints can actually fire',
     },
   },
   ```
   Add a byte-for-byte parallel entry for `check:ci-hint-corpus`, `step: 'Behavioral hints can actually fire'` (matching the header's `step:` line exactly -- `scripts/lib/gate-header.ts`'s binder requires this).
   **`npx tsx scripts/gen/gen-manifest.ts --write` will not create this entry from nothing**: its own guard at `gen-manifest.ts:210-215` refuses to run at all when the span count in the file and the entry count in the imported `GATES` array disagree, so a brand-new gate must be hand-added to the array first.
   Once it is, `--write` wraps it in the `// >>> gen-manifest: region N` / `// <<< gen-manifest: region N` markers if (and only if) the hand-written text is byte-identical to what the header would generate -- run it once after hand-adding, and read its `console.log` line ("N generated, M hand") to confirm the new entry did not drop into the "hand" bucket for a reason worth knowing (a stray `//` comment inside the span is the most common one, per `gen-manifest.ts:33-38`).

3. **The workflow step.** `.github/workflows/ci-quality.yml:1353-1355`, inside the `quality-content` job:
   ```
   - name: Agent hints can actually fire
     if: ${{ !cancelled() && steps.setup.outcome == 'success' }}
     run: .ci/scripts/quality/check_agent_hint_liveness.py
   ```
   Add the parallel step, `name: Behavioral hints can actually fire`, same `if:` guard, `run: .ci/scripts/quality/check_hint_corpus.py`.
   This is the one artifact `npm run gate:bind -- --write` (`package.json:240`) can emit directly from the header once the `manifest.ts` entry exists and matches -- run it after step 2, and confirm its own report says a region was rewritten rather than "already matches" with the new step absent, which would mean the header's `step:` text and the manifest's `ci.step` text disagree by a character.

   Steps within the header block, package.json and manifest.ts constitute the "three-point wiring" the plan's task list names; the workflow YAML step is the fourth artifact that `check:ci-parity` (`scripts/gates/check-ci-parity.ts`) actually reads to settle R2/R3 (`check-ci-parity.ts:8-9`: `W -> C` and `C -> W`), and it is generated from the header/manifest pair rather than hand-maintained, which is why `.claude/agents/gate-author.md`'s own "three places" section folds it into "the workflow file" as the third hand-verified location even though a tool writes it.
   Both framings describe the same four files; the plan's checklist wording and the agent doc's wording are not in tension, they are counting header+package.json+manifest as the three EDITED by hand and the workflow step as the one PROVEN to match by `gate-bind`.

4. **Confirm.** `npm run check:ci-parity` and `npm run check:ci-gate-reachability-coverage` (`package.json:159`), both named by `gate-author.md`'s wiring section as the two meta-gates that catch a half-wired gate. `check:ci-parity`'s own header (`check-ci-parity.ts:44-52`) already carries `scripts.ci`-parsing and `Quality / Branch` job-name literal parity guards this new gate must not trip -- since `check:ci-hint-corpus` is a plain `lane: quality-content` entry with no `paths:`, no `blocker:`, and one leaf, it should register cleanly.

## 6. Task checklist

- [ ] Write `.ci/scripts/quality/check_hint_corpus.py`: header (section 3.1), constants (3.2), `load_hints()` (3.3), `source_pointers()` (3.4), `judge_corpus()` (3.5), `cycle_findings()` (3.6), `controls_fired()` with CONTROL 0 through CONTROL 6 (3.7), `main()` (3.8). `chmod +x`.
- [ ] Run the new gate standalone (`.ci/scripts/quality/check_hint_corpus.py`) against the real tree and confirm the success line prints "9 planted defects caught" (7 control fixtures, two of which -- H4 and H6 -- carry two independent plants apiece) and the real corpus's 12/12 active entries.
- [ ] Break each of the 7 control fixtures ONE AT A TIME by temporarily disabling its matching assertion in a scratch copy, and confirm `controls_fired` reports it missed and the gate exits 1 without reaching the real corpus -- the proof that H7 itself is not vacuous, run once by hand rather than left as a claim.
- [ ] Add `"check:ci-hint-corpus": ".ci/scripts/quality/check_hint_corpus.py"` to `package.json` beside `check:ci-agent-hint-liveness` (`package.json:221`).
- [ ] Hand-add the `manifest.ts` entry parallel to `manifest.ts:2380-2391`, `step: 'Behavioral hints can actually fire'`.
- [ ] Run `npx tsx scripts/gen/gen-manifest.ts --write`; confirm its report counts the new entry as generated (or investigate why it landed in "hand" if it does not).
- [ ] Run `npm run gate:bind -- --write`; confirm it adds the `Behavioral hints can actually fire` step to `.github/workflows/ci-quality.yml`'s `quality-content` job, placed after `Agent hints can actually fire` in the region gate-bind already owns there.
- [ ] Run `npm run check:ci-parity` and `npm run check:ci-gate-reachability-coverage`; both must be green.
- [ ] Tick the two open boxes in `agent/plans/PLAN-stop-hook-behavioral-hints.md`'s task list (the "Write `.ci/scripts/quality/check_hint_corpus.py`..." and "Wire `check:ci-hint-corpus`..." lines) with evidence pointing at this plan and the commit that lands it.
- [ ] Register this plan file itself in `.ci/config/plan-boxes.json`, or run `python3 .ci/scripts/quality/check_plan_boxes.py --update`, so `check:ci-plan-boxes` G-A0 (`check_plan_boxes.py:28,236`) does not red on a tracked plan carrying open boxes with no ledger row.
- [ ] Run `python3 .ci/scripts/quality/check_prose_style.py reflow --write` then `check` on this plan file before it is committed, matching the parent plan's own closing convention (`PLAN-stop-hook-behavioral-hints.md`'s task list, last-but-one box).

## 7. Acceptance criteria

- `check:ci-hint-corpus` is green against the real 12-entry corpus.
- Each of H1 through H6 has been observed to RED against its own planted-defect fixture, and the healthy fixture (CONTROL 0) stays silent under all six -- both directions proven in the same run, per this repo's own control-first convention.
- `controls_fired` runs, and can be shown to fail closed (exit 1, no real-corpus verdict issued), before the real corpus is ever loaded.
- `check:ci-parity` and `check:ci-gate-reachability-coverage` are both green with the new gate registered.
- No change to `wl_hints.py`, `HINTS.md`, or the stop-hook wiring; this plan is additive, one new file plus three registration edits.

### Critical Files for Implementation

- `.ci/scripts/quality/check_agent_hint_liveness.py` -- the control-first liveness gate this design copies function-for-function (`die`, `load_matcher`/`load_hints`, `evaluate`/`judge_corpus`, `controls_fired`, `main`'s ordering)
- `.claude/hooks/stop/wl_hints.py` -- `load_corpus:46` (whose own error/entry contract H2 depends on), `hint_pick:105` (what H5/H6 drive directly)
- `.claude/hooks/stop/wl_planrec.py` -- `resolve:323`, the only oracle H3 may call
- `docs/agent-reference/HINTS.md` -- the corpus H1-H4 judge, including its own 160-char boundary case already living in the real data
- `scripts/ci-runner/manifest.ts:2380-2391` and `package.json:221` -- the byte-for-byte pattern the new gate's three-point wiring must match
