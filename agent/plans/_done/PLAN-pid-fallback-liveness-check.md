# PLAN: block_unsatisfiable_pid_wait.py -- a /proc/$(cat X || echo <always-alive-PID>) liveness-check guard
Status: done
First-Seen: 2026-09-22
Owner: d778be9d
Updated: 2026-09-22

## Finding statement

A background wait loop's third liveness clause,

```
! [ -e /proc/$(cat <out>.pid 2>/dev/null || echo 1) ]
```

is unsatisfiable by construction: `<out>.pid` is never written, so `cat` always fails, `||` always falls through to the literal `echo 1`, and `/proc/1` (init) is alive on every live Linux system. `! [ -e /proc/1 ]` is therefore permanently false, and the whole `until`/`while` condition stays false forever.

Task `b9fd3td29` wedged on exactly this shape for over 24 hours; it was found by the agent that wrote it, during a Writer-F autopilot-removal batch, 2026-09-21/22. From the outside, the loop is indistinguishable from a patient one: its OS process is genuinely alive and running, and the Stop hook's liveness check reports it that way correctly -- only the exit condition tells the two
apart, and nothing was checking that.

This is the same trap family as `block_self_matching_pgrep.py` (an unsatisfiable, invisible-from-outside wait-loop exit condition) but a different mechanism: that guard tests a regex self-match; this one tests whether a `$(cat X || echo <literal>)` fallback used inside a `/proc/<pid>` existence test resolves to a PID that is provably always alive.

## Root-cause explanation

`$(cat <path> 2>/dev/null || echo <N>)` is a common "read a value from a file, or use a default" idiom, and it is completely safe for ordinary defaults (config paths, counters, feature flags). It becomes a specific, different bug only when: (a) it sits inside a `/proc/<pid>` existence test (`-e`/`-d`), (b) that test sits inside a `while`/`until` loop's own exit condition, and (c)
`<N>` is a PID that is provably alive for the entire lifetime the loop could run -- true for exactly two literals: `1` (init, essentially always alive on a live Linux system, per the incident) and `$$` (the waiting shell's own PID, alive for the loop's own lifetime by definition).

Any other literal (`0`, `54321`, ...) is not provably alive-by-construction and must not be treated as the same defect -- `0` is in fact provably never alive (`/proc/0` never exists), which makes that shape safe, not dangerous.

## Detection approach: regex over the loop condition span, not a full AST

This is a new guard with no bash twin, so there is nothing to port and no differential oracle -- it is judged the way `.claude/rediacc_hooks/guards/block_prose_style_edit.py` (`TWIN = None`, confirmed at `.claude/rediacc_hooks/guards/block_prose_style_edit.py:55`) is judged: a dedicated `test-<stem>.py`, plus a planted `DEFECT`.

A full shell AST is not warranted any more than it was for `block_self_matching_pgrep.py`, which also uses anchored regex plus a small amount of Python string surgery over `hookio` primitives (verified: `CHAIN = "pre-bash"` at line 26, `TWIN = "pre-bash/block-self-matching-pgrep.sh"` at line 27, `ORDER = 15` at line 28, `LOOP_WITH_PGREP` regex at line 38). This design follows that
precedent: regex to find the loop condition and the `-e`/`-d /proc/$(` anchor, then a small hand-written balanced-paren scanner (regex cannot do nested parens reliably) to pull out the substitution body, then a `||`-aware split (quote-respecting) of that body into the `cat` half and the `echo` half.

### Verified precedents this borrows from

- `.claude/rediacc_hooks/guards/block_self_matching_pgrep.py:39-41` -- the loop-condition anchor `(^|[;&|(]|&&|\|\|)[{S}]*(until|while)[^;]*...`, and its own comment: "A loop condition runs from the keyword to the `; do` that closes it, so that is the span to search."
- `block_self_matching_pgrep.py` -- "THE TEST IS THE BUG ITSELF" framing, and the "an unparseable regex is not a verdict" convention (fail open on anything the guard cannot statically resolve).
- `.claude/rediacc_hooks/guards/block_prose_style_edit.py:55` -- the `TWIN = None` header template for a guard with no bash original.
- `.claude/rediacc_hooks/hookio.py` -- verified primitives: `ALLOW = 0` (line 64), `DENY = 2` (line 65), `def rx(pattern)` (line 73), `class Event` (line 102) with `def raw(self, *path)` (line 134) and `def warn_raw(self, text)` (line 207), `def grep_q(...)` (line 279), `def grep_o(...)` (line 295), and the `{S}`/`{B}` placeholder convention (`_RX_CLASSES`, referencing `SPACE`).

### Exact pattern (v1 scope: `/proc/` only, `-e`/`-d` only -- see "Scope and named gaps" below)

```python
CHAIN = "pre-bash"
TWIN = None
ORDER = 45  # append; see "Wiring" below for why this beats a mid-chain insert

LOOP_HEAD = hookio.rx(r"(^|[;&|(]|&&|\|\|)[{S}]*(until|while)\b")
DO_CLOSE = hookio.rx(r";[{S}]*do\b")

# -e or -d immediately (optionally through one straight quote) in front of
# /proc/$( -- NOT a bare "-e $(...)" (an ordinary default-value idiom used
# everywhere, explicitly out of scope), and NOT a mention of /proc/$( outside
# a -e/-d test.
PROC_TEST_OPEN = hookio.rx(r"-[ed][{S}]+\"?/proc/\$\(")

# The LEFT half of a top-level `||` inside the substitution must be EXACTLY
# a `cat` of one path token (no pipe, no further command), with an optional
# `2>/dev/null`. A pipeline, a `;`, or an `&&` is a DIFFERENT idiom.
LEFT_IS_BARE_CAT = hookio.rx(
    r"^[{S}]*cat[{S}]+[^|;&{S}]+([{S}]*2>[{S}]*/dev/null)?[{S}]*$"
)
RIGHT_IS_ECHO = hookio.rx(r"^[{S}]*echo[{S}]+(-[A-Za-z]+[{S}]+)?(\S+)[{S}]*$")

# THE TEST IS THE BUG ITSELF: only a fallback provably alive for the whole
# time the loop could run counts. "1" (init) is the incident's own literal;
# "$$" (the waiting shell's own PID) is the same defect and, per this
# design's own reasoning, arguably the single most common way this actually
# gets written by an agent -- both caught in v1. Any OTHER literal integer,
# INCLUDING 0, is NOT provably always-alive by construction (0 is provably
# NEVER alive, which is why it is the safe control) and is deliberately left
# unblocked -- see the adversarial case list and "Scope and named gaps".
def _is_provably_always_alive(token):
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in ("'", '"'):
        token = token[1:-1]
    return token in ("$$", "1")


def _extract_subst(text, open_paren_idx):
    """Balanced $( ... ) scan from the '(' at open_paren_idx. None if
    unbalanced -- an unparseable substitution is not a verdict, same
    convention as block_self_matching_pgrep's unparseable-regex handling:
    fail toward allow."""
    depth = 0
    in_sq = in_dq = False
    for i in range(open_paren_idx, len(text)):
        ch = text[i]
        if in_sq:
            in_sq = ch != "'"
            continue
        if in_dq:
            if ch == '"' and text[i - 1] != "\\":
                in_dq = False
            continue
        if ch == "'":
            in_sq = True
        elif ch == '"':
            in_dq = True
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return text[open_paren_idx + 1 : i]
    return None


def _split_top_level_or(body):
    """First `||` outside quotes, or None. `;`- and `&&`-joined fallbacks are
    a DIFFERENT idiom (only a fallback that ACTUALLY substitutes on cat
    failure matters) and correctly never split here."""
    in_sq = in_dq = False
    i = 0
    while i < len(body) - 1:
        ch = body[i]
        if in_sq:
            in_sq = ch != "'"
        elif in_dq:
            if ch == '"' and body[i - 1] != "\\":
                in_dq = False
        elif ch == "'":
            in_sq = True
        elif ch == '"':
            in_dq = True
        elif ch == "|" and body[i + 1] == "|":
            return body[:i], body[i + 2 :]
        i += 1
    return None


def run(ev):
    cmd = ev.raw("tool_input", "command")
    if cmd == "" or "/proc/" not in cmd or "$(" not in cmd:
        return hookio.ALLOW

    for head in re.finditer(LOOP_HEAD, cmd):
        close = re.search(DO_CLOSE, cmd[head.end() :])
        cond_end = head.end() + close.start() if close else len(cmd)
        condition = cmd[head.end() : cond_end]  # SCOPE: loops only

        for anchor in re.finditer(PROC_TEST_OPEN, condition):
            open_idx = anchor.end() - 1  # index of the '(' in "$("
            body = _extract_subst(condition, open_idx)
            if body is None:
                continue  # unbalanced: not a verdict, keep scanning

            split = _split_top_level_or(body)
            if split is None:
                continue  # no top-level `||`: `;`/`&&`/no-fallback, not this bug
            left, right = split

            if not re.match(LEFT_IS_BARE_CAT, left):
                continue  # not a bare `cat <path>`: a pipeline etc, not this bug
            m = re.match(RIGHT_IS_ECHO, right)
            if not m:
                continue  # not `echo <literal>`

            fallback = m.group(2)
            if _is_provably_always_alive(fallback):
                ev.warn_raw(MESSAGE % (anchor.group(0) + body + ")", fallback))
                return hookio.DENY

    return hookio.ALLOW
```

`DEFECT = ("if _is_provably_always_alive(fallback):", "if False:")` -- the single substitution that must exist verbatim in the file and that the planted-defect control nullifies; nullifying it turns the incident's own fire-case into a silent allow, the same shape every other guard's `DEFECT` proves.

## Adversarial case list, with expected verdicts

| # | Case | Verdict | Why |
|---|---|---|---|
| 1 | The incident's own shape (`until ... ! [ -e /proc/$(cat out.log.pid 2>/dev/null \|\| echo 1) ]; do sleep 5; done`) | BLOCK | exact `b9fd3td29` shape, fallback `1` |
| 2 | Minimal fire, unnegated (`until [ -e /proc/$(cat x.pid 2>/dev/null \|\| echo 1) ]; do sleep 5; done`) | BLOCK | polarity-agnostic by design -- the clause is a manufactured constant either way |
| 3 | `$$` fallback | BLOCK | the shell's own PID, alive for the loop's whole life -- v1 explicitly catches this |
| 4 | Quoted path form (`"/proc/$(...)"`) | BLOCK | `-e "?/proc/\$\(` anchor allows the leading quote |
| 5 | `-d` instead of `-e` | BLOCK | both `-e`/`-d` covered |
| 6 | CONTROL -- safe literal `0` | ALLOW | `/proc/0` never exists; `0` is not in `{"1", "$$"}` |
| 7 | CONTROL -- arbitrary other literal PID (`echo 54321`) | ALLOW (documented gap) | not provably always-alive by construction |
| 8 | CONTROL -- pidfile genuinely written first by an earlier `&&`-chained command | BLOCK | the guard cannot verify write ordering/reliability and does not try to; blocking is still correct because the shape is unsatisfiable in exactly the moment it matters |
| 9 | CONTROL -- unexaminable variable fallback (`echo "$FALLBACK_PID"`) | ALLOW | cannot be resolved statically, reads as unexaminable, matching this repo's "fail toward allowing when a claim cannot be resolved statically" convention |
| 10 | CONTROL -- one-shot, not a loop (`if [ -e /proc/$(...) ]; then ...; fi`) | ALLOW (out of scope) | no `until`/`while` anchor -- SCOPE: loops only, identical carve-out to `block_self_matching_pgrep.py` |
| 11 | `;`-joined is NOT the bug (`cat x.pid 2>/dev/null; echo 1`) | ALLOW | no top-level `\|\|`; `echo 1` always runs regardless of whether `cat` succeeded -- a different defect this guard does not claim to cover |
| 12 | `&&`-joined is NOT the bug (`cat x.pid 2>/dev/null && echo 1`) | ALLOW | `echo 1` only runs when `cat` SUCCEEDS -- not a fallback at all |
| 13 | Correct remedy #1 -- pidfile written first, no fallback (`cat out.pid`, no `\|\|`) | ALLOW | does not match the shape, passes by construction |
| 14 | Correct remedy #2 -- missing pidfile means "not started, keep waiting" (`[ ! -s out.pid ] \|\| ! [ -e /proc/$(cat out.pid) ]`) | ALLOW | same reason as #13 |
| 15 | `kill -0` form | ALLOW in v1 (explicit gap) | same mechanism, different string; v1 is scoped to `/proc/` only |
| 16 | Non-`/proc/` default-value idiom (`-e $(cat config_path.txt \|\| echo default.conf)`) | ALLOW | anchor requires the literal string `/proc/`; this is the ordinary "read a path or use a default" idiom |
| 17 | Prose mention, not a real loop (`echo "never write /proc/$(cat x.pid \|\| echo 1) into a wait loop"`) | ALLOW | no real `until`/`while` keyword at command position |
| 18 | Unbalanced/unparseable substitution | ALLOW | `_extract_subst` returns `None`; an unparseable construct is not a verdict |
| 19 | A pipeline on the left, not a bare `cat` (`cat x.pid \| grep -q 1 \|\| echo 1`) | ALLOW | `LEFT_IS_BARE_CAT` requires no `\|` inside the left half |
| 20 | `while` form fires the same as `until` | BLOCK | `LOOP_HEAD` matches both keywords |

## Files to create / edit

New:
- `.claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py` -- the guard itself.
  Docstring sections: WHY A HOOK AND NOT A DOCUMENT (cite `b9fd3td29`); THIS GUARD HAS NO BASH TWIN (modeled on `.claude/rediacc_hooks/guards/block_prose_style_edit.py:55`); THE TEST IS THE BUG ITSELF; SCOPE (`/proc/` only, `-e`/`-d` only, loops only, `{1, $$}` only); ADVERSARIAL RISKS DESIGNED AGAINST (the `0`/variable/arbitrary-literal/one-shot/prose cases above).
- `.claude/rediacc_hooks/guards/test-block_unsatisfiable_pid_wait.py` -- standalone control script, house shape matching `.claude/rediacc_hooks/guards/test-block_push_to_protected_branch.py` (confirmed shape: `CASES = [(name, command, cwd, expect_blocked), ...]` -- the `cwd` slot can be `None` for every case here, since none of these commands are branch-dependent the way a push guard's are; drives the live guard through `dispatch.py` via `GUARD_ARGV`, an anti-vacuity check that not all cases answer the same way, ends `sys.exit(1 if fails else 0)`), transcribing the 20-case table above.

Edit:
- `docs/agent-reference/TRAPS.md` -- insert the new entry immediately after the existing pgrep entry (confirmed: that entry starts at line 708, the next heading `## A \`cp -rs\` mirror...` starts at line 729), so the insertion point is between those two, unchanged from the design.

Not edited (verified, self-registering):
- `.claude/settings.json` -- routes `pre-bash` to `dispatch.py --chain pre-bash` as one command; a new `block_*.py` with `CHAIN = "pre-bash"` is picked up with no edit here (`.claude/rediacc_hooks/guards/__init__.py:38`, confirmed: "A guard added here is registered by EXISTING").
- `.claude/rediacc_hooks/tests/test_hooks_delegates.py` -- `TAILED`'s runtime glob discovery (since 2026-09-22, commit `4e5781b7b`'s neighbor) auto-picks up `test-block_unsatisfiable_pid_wait.py` from `.claude/rediacc_hooks/guards/`, one of `_TAILED_ROOTS`. No manual wiring needed, confirmed by design and by how `test-block_push_to_protected_branch.py` itself got picked up.
- `test_guards_differential.py` -- `test_every_port_has_a_present_twin` only requires the `test-<stem>.py` file to exist at the conventional name for a `TWIN = None` guard; `EDGE_CASES` on the module (if added) is auto-consumed into `NATIVE_CASES`.

## Wiring: CHAIN, ORDER, and the placement decision

`CHAIN = "pre-bash"`, `TWIN = None`.

Verified: every `pre-bash` guard's `ORDER` is densely contiguous 3 through 44 (42 guards, no gaps, no duplicates -- confirmed by direct scan of the tree, matching `.claude/rediacc_hooks/tests/test_dispatch.py:166-167`'s own assertion: `declared == list(range(declared[0], declared[0] + len(declared)))`).

Two valid placements, both verified against real precedent (commit `36dd93635`, confirmed in git log, which inserted `block_push_to_protected_branch.py` at `ORDER = 39` and re-keyed 5 sibling files with `# Re-keyed from X to X+1 on 2026-09-22 by the insertion of block_push_to_protected_branch.py at 39.` comments -- confirmed present verbatim in
`.claude/rediacc_hooks/guards/block_pathspecless_git_commit.py:45`, `.claude/rediacc_hooks/guards/block_prose_style_commit.py:49`, `.claude/rediacc_hooks/guards/block_unproven_bulk_transform.py:30`, `.claude/rediacc_hooks/guards/warn_staged_shape_duplication.py:55`, `.claude/rediacc_hooks/guards/block_unverified_push.py:36`):

- Recommended: append, `ORDER = 45`. Zero other files touched. There is no correctness dependency between this guard and any neighbor -- each `pre-bash` guard matches a disjoint command shape and the chain stops at first refusal, so relative order among independent guards is inert. Lowest-risk choice.
- Alternative (documented, not taken): insert at `ORDER = 16`, immediately after `block_self_matching_pgrep.py` (15, the closest sibling in the wait-loop-liveness family), re-keying 29 files. Rejected for this implementation: no correctness benefit over appending, and 29 touched files is a much larger surface for a change with zero behavioral dependency on ordering.

## Fix classification: own guard file, confirmed

`block_shell_background_waiter.py` is scoped, by its own docstring, to exactly one named instrument (`wl_wait.py` launched with a shell `&`) -- a different failure mode (untracked backgrounding) unrelated to exit-condition satisfiability.

`block_self_matching_pgrep.py` is scoped to one specific mechanism (a `pgrep -f` pattern self-matching its own command line via text/regex). Extending it to also parse `/proc/$(cat X || echo N)` would give it two unrelated `DEFECT`s, two unrelated anchor regexes, and two unrelated `EDGE_CASES` families under one name -- exactly the shape both guards' own narrow-scope sections argue
against. A new, narrowly-scoped file matching that same discipline is the correct call.

## TRAPS.md entry (insert after line 727, before line 729)

```markdown
## A `/proc/$(cat <pidfile> || echo <literal>)` liveness check with an always-alive fallback PID waits forever
Trap-Id: proc-pid-fallback-always-alive
Enforced-By: file:.claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py
Residue: v1 covers `/proc/<pid>` existence tests (`-e`/`-d`) only, and only the two fallbacks that are provably always alive by construction (`1`, init; `$$`, the waiting shell's own PID). The identical bug spelled as `kill -0 $(cat X || echo N)` is not covered and is a named gap. A fallback to any OTHER literal PID is also not covered, because the guard cannot prove it stays alive; only a hand read of the specific PID tells you.

A background wait loop's liveness check used this shape (task `b9fd3td29`, found by the agent that wrote it, wedged over 24 hours, during a Writer-F autopilot-removal batch on 2026-09-21/22):

    until grep -q "ci-dead-bash" <out> && [ "$(tail -c 200 <out> | wc -c)" -gt 0 ] \
          && ! [ -e /proc/$(cat <out>.pid 2>/dev/null || echo 1) ]; do sleep 5; done

The third clause is unsatisfiable by construction. `<out>.pid` was never written, so `cat <out>.pid 2>/dev/null` fails every time, `||` falls back to the literal `echo 1`, and `/proc/1` (init) exists on every live Linux system. `! [ -e /proc/1 ]` is therefore permanently false, so the loop can never exit, no matter what the first two clauses do.

Nothing looked wrong from outside. The waiting shell's own OS process is genuinely alive and genuinely sleeping in a loop, so a liveness check on the PROCESS reports it as healthy -- correctly. Only the exit CONDITION distinguishes a wedged loop from a patient one, and this condition contained a sub-clause that was a disguised constant: `$(cat X || echo N)` reads as "the real PID, or a sensible fallback", but when `N` is a PID that is itself always alive (`1`, or `$$` -- the waiting shell's own PID, trivially alive for the whole time the loop could possibly run), the fallback branch is not a fallback at all. It is the answer, always, and the "real PID" branch never gets a chance to matter.

This is the same class of trap as "a `pgrep -f <pattern>` guard inside a shell whose own command line contains that pattern waits forever" (above), and a different mechanism: that one is a pure text/regex self-reference; this one is a numeric/semantic question -- does a hardcoded fallback resolve to a PID that happens to be alive for the loop's entire possible lifetime. `echo 0` is the corresponding SAFE case and proves the difference: `/proc/0` never exists, so `cat X || echo 0` is an honest "assume not-yet-started" default, not a disguised constant.

Two rules. First, never give a `$(cat <pidfile> || echo <N>)` substitution inside a `/proc/<pid>` or `kill -0` liveness test a fallback `N` that could itself be alive for as long as the loop can run -- `1` and `$$` both qualify and both must be treated as banned literals in this exact position, not just `1`. Second, write the wait correctly instead of defending the fallback: either write the pidfile BEFORE the loop starts and drop the `||` entirely (a missing pidfile is a hard error, not a value to guess), or treat a missing pidfile as "not started yet, keep waiting" (`[ ! -s <out>.pid ] || ! [ -e /proc/$(cat <out>.pid) ]`) rather than substituting a literal PID for it.
```

## Tasks

- [x] Write `.claude/rediacc_hooks/guards/block_unsatisfiable_pid_wait.py` per the design above.
- [x] Write `.claude/rediacc_hooks/guards/test-block_unsatisfiable_pid_wait.py`, transcribing all 20 adversarial cases, modeled on `test-block_push_to_protected_branch.py`.
- [x] Insert the TRAPS.md entry between lines 727 and 729.
- [x] Run the new standalone test directly (`python3 .claude/rediacc_hooks/guards/test-block_unsatisfiable_pid_wait.py`), confirm 20/20 with a non-trivial block/allow split.
- [x] Run `.claude/rediacc_hooks/tests/test_hooks_delegates.py` and `.claude/rediacc_hooks/tests/test_dispatch.py` (ORDER contiguity) and `.claude/rediacc_hooks/tests/test_guards_differential.py` (TWIN=None coverage), confirm all green with no manual wiring needed.
- [x] Confirm the new test file is auto-discovered by `test_hooks_delegates.py`'s TAILED glob (case count should increase by one, matching the pattern already proven for `test-block_push_to_protected_branch.py`).

## Acceptance criteria

- `test-block_unsatisfiable_pid_wait.py` passes all 20 cases standalone, with a genuine block/allow split (not all one verdict).
- The planted `DEFECT` substitution flips at least one case's verdict when nullified (proves the test is not vacuous).
- `check:ci-pytest`-equivalent local run (`test_hooks_delegates.py`, `.claude/rediacc_hooks/tests/test_dispatch.py`, `test_guards_differential.py`) green with zero manual registration.
- The TRAPS.md entry reads correctly in place, matching the document's existing entry format.
