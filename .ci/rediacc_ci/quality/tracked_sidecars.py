"""No stop-hook RUNTIME sidecar may be tracked by git.

Ported from `.ci/scripts/quality/check-tracked-sidecars.sh`, retired in W7 P5; see `rediacc_ci.quality.__init__`; the committed differential ledger under `.ci/shadow/` is what licensed the retirement.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS. Every date and every named file below is the original's, not a paraphrase of it.
-----------------------------------------------------------------------------

WHY THIS EXISTS. On 2026-08-05 a `git add -A` swept two runtime files into a commit: `.claude/hooks/stop/.sessions` and `.claude/hooks/stop/.waiter-aaaaaaaa`. They were removed by hand and added to .gitignore, and nothing whatsoever prevented their return -- every existing gate was blind to them by construction. These files have no static markers in source; they exist only
while a session runs, so no linter, type-check or dead-code scan can see them.
The only observable that distinguishes the defect is `git ls-files`.

WHY A TRACKED SIDECAR IS WORSE THAN UNTIDY. The PostToolUse nudge reads a `.waiter-<prefix>` heartbeat to decide whether a session is listening for peer messages. A committed heartbeat tells every fresh clone that a waiter is already running when none is, so the nudge goes quiet and the session is silently deaf -- the exact failure the waiter was built to remove. A committed
`.sessions` brief describes a session that no longer exists, and a committed `.requests` would replay other sessions' questions into a clone as if new.

THE PATTERN LIST IS DERIVED, NOT COPIED. wl_store.py's module docstring is the single source for the sidecar family. Hard-coding the list here would let the two drift, and a gate that checks a stale list is the vacuity this repo keeps paying for. If that docstring is reworded so the list cannot be parsed, this gate FAILS rather than silently checking nothing.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE TWIN SHELLS OUT TO PYTHON ALREADY, and that is the single most important fact about this port. Its pattern parser is a `python3 - "$STORE" <<'PY'` heredoc running a `re.search(r"The sidecars \\((.*?)\\)", src, re.S)` and a `re.split(r"[,\\s]+", ...)`. Those two expressions are carried here VERBATIM, because rewriting them into "cleaner" Python would change which tokens the gate
derives and therefore which paths it globs. The non-greedy `(.*?)` stopping at the FIRST closing paren is behaviour, not an accident: the docstring's list ends
with `.resprofile.*)` and any later paren in the file must not be reached.

`re.S` (DOTALL) is what lets the list span five physical lines. Without it the match would stop at the first newline and the gate would derive four patterns instead of twenty-one, which is the collapsed-corpus failure this gate is supposed to be immune to.

THE CONTROL IS A GLOB SELF-MATCH, and it looks tautological because in bash it very nearly is. The twin builds `$HOOK_DIR/$pat` and tests it against the
UNQUOTED right-hand side of `[[ ... == ... ]]`, which is pattern matching: a
pattern is asked whether it matches the literal text it was built from. What it actually proves is that the pattern survived word splitting and carries no character the matcher chokes on -- a pattern list mangled into `.reggate-` and `*` as two tokens, or a `[` with no `]`, fails it. `fnmatch.fnmatchcase` is the closest Python equivalent: same `*`/`?`/`[...]` grammar, no case
folding, no special treatment of a leading dot or of `/`. `pathlib.PurePath.match` would have been wrong here, because it anchors on path components and would not compare the whole string.

THE EXIT STATUS OF `git ls-files` IS LOAD-BEARING, and the twin says so at length: `2>/dev/null || true` there would make a FAILED enumeration -- no repo, a broken index, a bad pathspec -- read exactly like "no sidecars are tracked", so the gate would report a clean tree precisely when it could not look. The twin captures `2>&1` into the same variable and prints it back with `git
said: ...`, so stderr is DATA on this path rather than a stream to
discard. `subprocess.run(..., stderr=STDOUT)` reproduces that exactly.

STREAMS, AND WHY `log.error` IS THE WRONG TOOL HERE. This gate is the one in the batch that sources NO logger at all: every line it emits is a bare `echo ... >&2`, with the `✗` TYPED INTO the first string of each block and the continuation lines carrying no glyph, plus deliberate blank `echo >&2` lines between the header, the path list and the advice. Routing those through
`log.error` would prefix a `✗` onto lines the twin leaves bare and would drop the blanks, which changes the shape a reader sees and, more sharply, changes which lines `scripts/lib/shadow-gate.ts` counts as findings: a blank line ends a continuation block, and an unmarked indented line after one is chatter. A port that "improved" the streams here would be non-equivalent to its twin
while
looking tidier. So every message goes through `print(..., file=sys.stderr)` and
the blanks are preserved exactly.

The final success line is a bare `echo` on STDOUT in the twin, printing the derived pattern COUNT. It is data a reader is meant to see collapse, so it stays on stdout through `print()`.

WHAT THIS GATE STILL CANNOT SEE, unchanged by the port: it globs only under `.claude/hooks/stop`. A sidecar written anywhere else, or one whose name does not appear in wl_store.py's docstring, is invisible. Widening it would change the verdict, so it is preserved and stated instead.
"""

import fnmatch
import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The directory the sidecars live in, relative to the repository root. The twin `cd`s to the root and uses this bare relative string as the pathspec prefix, which is the same fact with the cd removed.
HOOK_DIR = ".claude/hooks/stop"

# The single source for the family. The twin reads it as an absolute path built
# from its own location; here it is root-relative and joined at call time so the
# REDIACC_CI_ROOT override reaches it.
STORE_REL = (".claude", "hooks", "stop", "wl_store.py")

# The two expressions the twin's heredoc uses, carried verbatim. `re.S` is required (spelled `re.DOTALL`, which is the same flag the twin's `re.S` names): the list spans five physical lines in wl_store.py today.
SIDECAR_LIST_RE = re.compile(r"The sidecars \((.*?)\)", re.DOTALL)
TOKEN_SPLIT_RE = re.compile(r"[,\s]+")


def parse_patterns(source: str) -> list[str]:
    """The sidecar globs named in wl_store.py's docstring, in document order.

    Returns [] both when the "The sidecars (" phrase is absent and when the parenthesised list contains no token starting with a dot. The twin collapses those two cases too -- its heredoc `sys.exit(0)`s on no match and prints nothing, and the caller tests only for an empty string -- so they are one outcome here as well rather than two, and the caller reports the same refusal for
    both.
    """
    match = SIDECAR_LIST_RE.search(source)
    if not match:
        return []
    out: list[str] = []
    for raw in TOKEN_SPLIT_RE.split(match.group(1)):
        token = raw.strip()
        # Only tokens that are globs. The list is prose as well as data: it contains the words "keep their v5-v9 formats" further down, and the leading-dot test is what separates the two.
        if token.startswith("."):
            out.append(token)
    return out


def control_fires(patterns: list[str]) -> bool:
    """Prove the matcher can FIRE before trusting it to pass.

    A gate whose matcher is broken reports a clean tree exactly like a clean tree does, which is how a check that cannot fail survives for months. Feed it a synthetic path built from its own pattern list and require a match.

    The twin sets `control_hit=1` if ANY pattern self-matches, not all of them,
    so an OR is the faithful reading. Stated because an AND looks stronger and would be a different gate: one pattern carrying an unbalanced `[` would then fail the whole control rather than being the single dud it is.
    """
    for pattern in patterns:
        if not pattern:
            continue
        subject = "%s/%s" % (HOOK_DIR, pattern)
        if fnmatch.fnmatchcase(subject, subject):
            return True
    return False


def ls_files(pathspec: str, root) -> tuple[int, str]:
    """`git ls-files -- <pathspec>` with stderr FOLDED INTO the output.

    Returns (exit status, combined text). The fold is the twin's `2>&1`: on the failure path the text is printed back to the reader as `git said: ...`, so it is data, not a stream to be discarded. Keeping the status is the whole point of the function; see the module docstring.
    """
    proc = subprocess.run(
        ["git", "ls-files", "--", pathspec],
        cwd=str(root),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    return proc.returncode, proc.stdout


def err(message: str) -> None:
    """One line on stderr, with NO glyph and no colour.

    Named rather than inlined so the deviation from `rediacc_ci.log` is visible at every call site: this gate's twin sources no logger, and matching its bytes matters more than matching the package's house style. See the module docstring, "STREAMS, AND WHY `log.error` IS THE WRONG TOOL HERE".
    """
    print(message, file=sys.stderr)


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation or refusal.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments at all and would ignore the string; no caller passes it, and the differential never passes it to the old side.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    store = root.joinpath(*STORE_REL)

    # THE ABSENT SOURCE IS A FAILURE, NOT AN ABSTENTION, and the twin spells out why in the message itself: without wl_store.py there is no pattern list, so the gate "would be checking nothing. That is a failure, not a pass."
    if not store.is_file():
        err("\u2717 %s not found -- cannot derive the sidecar list, so this gate" % store)
        err("  would be checking nothing. That is a failure, not a pass.")
        return 1

    patterns = parse_patterns(store.read_text(encoding="utf-8", errors="replace"))
    if not patterns:
        err("\u2717 could not parse the sidecar list out of wl_store.py's docstring.")
        err("  The list is the single source for this gate; if it was reworded,")
        err("  re-point this parser rather than deleting the check.")
        return 1

    count = len(patterns)

    if not control_fires(patterns):
        err("\u2717 CONTROL FAILED: the matcher did not match a path built from its own")
        err("  pattern list. The detector is broken; a clean result would be a lie.")
        return 1

    tracked: list[str] = []
    for pattern in patterns:
        if not pattern:
            continue
        status, text = ls_files("%s/%s" % (HOOK_DIR, pattern), root)
        if status != 0:
            err("\u2717 git ls-files failed for pattern '%s', so this gate cannot" % pattern)
            err("  tell a clean tree from an unreadable one. Refusing to pass.")
            err("  git said: %s" % text)
            return 1
        tracked.extend(line for line in text.split("\n") if line != "")

    if tracked:
        # THE BLANK LINES ARE PART OF THE OUTPUT, not spacing that can be tidied away: the twin writes `echo >&2` between the header, the path list and the advice, and a blank line is what separates a finding from the prose about it. Reproduced literally.
        err("\u2717 RUNTIME SIDECAR(S) ARE TRACKED BY GIT:")
        err("")
        for path in tracked:
            err("    %s" % path)
        err("")
        err("  These are per-session runtime state, not source. A tracked")
        err("  .waiter-* heartbeat tells a fresh clone a waiter is running when")
        err("  none is, so its session goes silently deaf to peer messages.")
        err("")
        err("  Fix: git rm --cached <path>, and add the pattern to .gitignore.")
        err("  Do not just delete the file -- it will be recreated on the next run.")
        return 1

    print("✓ no runtime sidecars tracked (%d pattern(s) derived from wl_store.py)" % count)
    return 0


# A docstring shaped exactly like wl_store.py's, small enough to read. The selftest mutates copies of this rather than the real file, because a control built by substituting into real source silently stops controlling anything the day that source is reworded (see check-control-vacuity.sh).
_STORE_DOC = '''"""The worklist store.

The sidecars (.requests, .sessions, .loop, .reggate-*,
.waiter-*, .events.*)
keep their v5-v9 formats and names.
"""
'''


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will happily flag a correct tree, so every plant below has a mirror that must stay GREEN, and the parser is exercised on the shapes that would silently shrink the pattern list rather than break it.
    """
    ctl = Controls("tracked-sidecars", floor=16, verbose=True)

    # -- the parser, driven directly ---------------------------------------
    ctl.check(
        "CONTROL: the real-shaped docstring yields its six patterns",
        parse_patterns(_STORE_DOC),
        [".requests", ".sessions", ".loop", ".reggate-*", ".waiter-*", ".events.*"],
    )
    # VACUITY: a reworded docstring yields nothing, and nothing is a refusal.
    ctl.check(
        "VACUITY: a docstring with no 'The sidecars (' phrase parses to nothing",
        parse_patterns('"""The worklist store. It has some files."""'),
        [],
    )
    ctl.check("VACUITY: an empty source parses to nothing", parse_patterns(""), [])
    # THE DOTALL CASE. Without re.S the list would stop at the first newline and the gate would derive a SHORTER list, which is the silent-shrink failure rather than a loud one. Assert the multi-line list survives.
    ctl.check(
        "CONTROL: the list spans lines, so DOTALL is required",
        len(parse_patterns("The sidecars (.a,\n.b,\n.c)")),
        3,
    )
    # THE NON-GREEDY CASE. `(.*?)` must stop at the FIRST paren; a greedy match would swallow the rest of the file and admit tokens from elsewhere.
    ctl.check(
        "CONTROL: the match stops at the first closing paren",
        parse_patterns("The sidecars (.a) and later (.b)"),
        [".a"],
    )
    # MIRROR: a token that is not a glob is prose, not a pattern.
    ctl.check(
        "MIRROR: non-dotted tokens in the list are prose, not patterns",
        parse_patterns("The sidecars (.a, and, .b)"),
        [".a", ".b"],
    )

    # -- the control's own control -----------------------------------------
    ctl.truthy("CONTROL: the matcher self-matches a real pattern set", control_fires([".waiter-*"]))
    ctl.falsy("MIRROR: an empty pattern set cannot self-match", control_fires([]))
    ctl.falsy("MIRROR: a list of empty strings cannot self-match", control_fires(["", ""]))

    # -- the enumerator, over throwaway git repos ---------------------------
    def build(tmp: str, *, store: str | None, tracked: tuple[str, ...] = ()) -> pathlib.Path:
        """A throwaway repo with an optional wl_store.py and optional sidecars."""
        root = pathlib.Path(tmp)
        hooks = root / HOOK_DIR
        hooks.mkdir(parents=True, exist_ok=True)
        if store is not None:
            (hooks / "wl_store.py").write_text(store, encoding="utf-8")
        subprocess.run(["git", "init", "-q"], cwd=str(root), check=True)
        subprocess.run(
            ["git", "config", "user.email", "selftest@example.invalid"],
            cwd=str(root),
            check=True,
        )
        subprocess.run(["git", "config", "user.name", "selftest"], cwd=str(root), check=True)
        for name in tracked:
            (hooks / name).write_text("runtime\n", encoding="utf-8")
            subprocess.run(
                ["git", "add", "-f", "%s/%s" % (HOOK_DIR, name)], cwd=str(root), check=True
            )
        # A commit is not required: `git ls-files` reads the INDEX, and adding is what puts a path there. Stated because "tracked" and "committed" are different claims and this gate is about the first one.
        return root

    def run(root: pathlib.Path) -> int:
        saved = os.environ.get(paths.ROOT_ENV)
        os.environ[paths.ROOT_ENV] = str(root)
        try:
            return main([])
        finally:
            if saved is None:
                del os.environ[paths.ROOT_ENV]
            else:
                os.environ[paths.ROOT_ENV] = saved

    with tempfile.TemporaryDirectory() as tmp:
        ctl.check("CONTROL: a clean tree passes", run(build(tmp, store=_STORE_DOC)), 0)
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "VACUITY: a missing wl_store.py is refused, not passed",
            run(build(tmp, store=None)),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "VACUITY: an unparseable docstring is refused",
            run(build(tmp, store='"""nothing to see here."""')),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "PLANT: a tracked .sessions is caught (the 2026-08-05 defect)",
            run(build(tmp, store=_STORE_DOC, tracked=(".sessions",))),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        ctl.check(
            "PLANT: a tracked .waiter-<prefix> is caught, through its glob",
            run(build(tmp, store=_STORE_DOC, tracked=(".waiter-aaaaaaaa",))),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        # The `.events.*` token carries a dot INSIDE the glob, which is the shape a naive `startswith(".")`-then-`split(".")` parser mangles.
        ctl.check(
            "PLANT: a tracked .events.<n> is caught through a dotted glob",
            run(build(tmp, store=_STORE_DOC, tracked=(".events.3",))),
            1,
        )
    with tempfile.TemporaryDirectory() as tmp:
        # MIRROR: a file under the hook dir that is NOT a sidecar is source and must stay tracked. A gate that flagged this would be unusable.
        ctl.check(
            "MIRROR: an ordinary tracked file in the hook dir is not a sidecar",
            run(build(tmp, store=_STORE_DOC, tracked=("worklist.py",))),
            0,
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
