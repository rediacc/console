r"""Every shell script INVOKED as `./path.sh` must be committed executable.

Ported from `.ci/scripts/quality/check-script-exec-bit.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live side by side.

WHY THIS EXISTS, in the twin's own words, because the incident is the design:

    A script invoked as `./x.sh` without mode 100755 does not fail like a bug. It
    fails with exit 126 and one line on stderr, before any of its own output
    exists. A driver loop that prints a header per iteration and then counts
    headers therefore reports a full, healthy run: N iterations attempted, N
    headers printed, zero work done. That is not hypothetical -- it happened in
    this repo on 2026-08-20, where 36 pipeline combinations "ran" in under a
    second and the header count read exactly like success.

    The lesson generalises past the missing mode bit: an instrument that counts
    ATTEMPTS cannot distinguish them from COMPLETIONS. This gate closes the cheap
    half of that (the mode bit is mechanically checkable); the expensive half is
    a discipline, which is why the failure above is quoted here rather than
    summarised.

    It reads the GIT INDEX mode, not the filesystem, because the index is what CI
    checks out. A locally chmod'ed file that was committed 100644 is still broken
    for everybody else, and a filesystem check would call it clean.

    CONTROL-FIRST: the detector is run against a planted non-executable script
    BEFORE the real scan. If the control cannot fire, the gate refuses (exit 2)
    rather than reporting a clean tree it never actually inspected.

THE THREE THINGS THE EXTRACTION GETS RIGHT, each paid for, carried verbatim:

    ANCHORED with a negative lookbehind, which is why this is -P and not -E. An
    unanchored `\./` also matches the SECOND dot of a `../` reference:
    `../scripts/lib/foo.sh` yields `./scripts/lib/foo.sh`, a DIFFERENT file.

    NOT -h: the referencing FILE is load-bearing. `./sibling.sh` means a sibling
    of the file that says it, not of the repo root. Resolving everything against
    the root skipped every nested invocation -- which is the pattern used
    throughout .ci/scripts/, i.e. exactly the class this gate exists for. It
    checked 9 repo-root scripts and silently passed on the rest. Caught in review
    on this PR; the earlier two controls both used repo-root references, so they
    proved detection while overstating coverage.

    Whole LINES, not just the match, so comment lines can be dropped. A `./x.sh`
    inside `# Usage: ./x.sh` or `# shellcheck source=./lib/x.sh` is documentation,
    not an invocation, and both produced false positives the moment the path
    resolution above started working: one file the Dockerfile chmods itself, one
    that is SOURCED and therefore needs no exec bit at all.

THE PARENT-REFERENCE CONTROL IS THE INTERESTING ONE, and the twin records why its first version could not fail:

    This control is built so the two behaviours produce DIFFERENT path sets, which
    the first version of it did not: it planted `../victim.sh` in the SAME
    directory as an existing `./victim.sh` reference, so both the correct and the
    broken behaviour deduped to {victim.sh} and the assertion could not fail.
    Caught in review.

    Here the decoy lives in a SUBDIRECTORY and is referenced as `../decoy.sh` from
    a file in that same subdirectory. Correct: the reference is skipped and decoy
    is never reported. Broken (unanchored): `./decoy.sh` is extracted and resolved
    against the subdirectory, naming sub/decoy.sh, which IS tracked and IS
    non-executable, so it is reported. The sets differ by exactly one entry.

That is a control about the CONTROL, and it is the reason this port keeps the decoy in a subdirectory rather than "simplifying" it back into the root: a plant that fires under both the right and the wrong implementation is not a plant.

THE NEGATIVE CONTROL IS NOT OPTIONAL, and the twin says why in one sentence: "A second control: the SAME fixture, made executable, must go quiet. Without this, a detector that flags every script would also 'pass' the check above."

THE SINGLE-QUOTE DETAIL IN THE REFUSAL MESSAGES, which shfmt caught:

    Single quotes on the lines carrying ../x.sh: backticks inside a double-quoted
    echo are COMMAND SUBSTITUTION, so the error path would try to execute the very
    script it is complaining about.

Python has no such hazard, so the note survives here as archaeology rather than as a constraint on this file: it explains why the twin's message block is quoted inconsistently, which otherwise reads as sloppiness and invites a "tidy".

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

COLOUR IS UNCONDITIONAL IN THIS GATE, and that is carried rather than corrected.
The twin assigns `RED=$'\033[31m'` and friends with NO tty test and NO `NO_COLOR`
test, unlike `.ci/scripts/lib/common.sh:18`, which it never sources. So this gate writes escapes into a CI log and into a pipe, always. `rediacc_ci.log` decides colour by `isatty`, so using it here would change the bytes on every non-tty run and the differential would score a mismatch on every tree. The port therefore prints raw, with the twin's exact sequences: `31m`/`32m`/`33m`,
NOT the `0;31m` form `common.sh` uses. Reported as an inconsistency in the twin rather than fixed here.

EVERYTHING GOES TO STDOUT, INCLUDING THE FAILURES. The twin's `echo` calls carry no `>&2`, so a caller redirecting stdout to a file sees nothing on the terminal even when the gate fails. Carried, and reported.

THE ENUMERATION IS `git ls-files` PLUS A PYTHON REGEX, NOT `git grep -nP`. Shelling out to `git grep` would make the port trivially equivalent and would also make it a wrapper rather than a port; the risk of reimplementing is that git's pathspec and binary handling differ from Python's. Both are pinned here: the pathspecs are passed to `git ls-files` UNCHANGED, so git still decides
which files are in scope (a bare `*.sh` pathspec matches at any depth, because git does not set FNM_PATHNAME), and a file containing a NUL byte is skipped, which is what `git grep` does when it reports `Binary file X matches` instead of lines. `git grep` is git's own matcher and is NOT affected by which `grep` is on PATH, which is worth stating because an interactive Claude Code
shell replaces `grep` with a FUNCTION wrapping a bundled ugrep and a script sees GNU grep 3.12; that substitution produced two wrong port notes elsewhere in this wave and cannot reach this gate.

MEASURED END TO END ON THE REAL TREE, 2026-09-06: `git grep -nP` returns 830 hit lines, the twin's shell pipeline resolves them to 102 distinct paths, and the port's own enumeration returns the SAME 102, compared as sorted files. That is the check worth repeating after any change here, because a green run on a clean tree proves only that both sides found nothing.

`\w` IS SPELLED OUT AS `[A-Za-z0-9_]`. PCRE's `\w` without the UTF mode is ASCII;
Python's is unicode-aware and would admit an accented letter in a path, which would change which references are extracted. This is the class of difference that does not show up in any fixture and shows up once, on a real path, years later.

EXIT 2 IS THE REFUSAL AND IS PRESERVED EXACTLY. It is not exit 1: the twin distinguishes "the control could not fire" from "the tree has offenders", and a port that collapsed them would make an unrunnable gate look like a failing tree.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci.controls import Controls

# The twin's escape sequences, verbatim and unconditional. See the port notes for why these are not `rediacc_ci.log`'s.
RED = "\033[31m"
GREEN = "\033[32m"
YEL = "\033[33m"
OFF = "\033[0m"

# The pathspecs `git grep` is given, in the twin's order. Passed through to `git ls-files` unchanged so git, not this file, decides what is in scope.
PATHSPECS = ("*.sh", "*.yml", "*.yaml", "*.json", "*.md", "*.ts")

# `(?<![\w./-])\./[\w./-]+\.sh` with `\w` spelled out. The lookbehind is the whole accuracy of the gate: without it, `../x.sh` yields `./x.sh`, a different file.
WORD = r"A-Za-z0-9_"
REF_RE = re.compile(r"(?<![%s./-])\./[%s./-]+\.sh" % (WORD, WORD))

# A matched LINE whose content is a comment. Three lead-ins, matching the twin's `case` arms: shell, C-style, and a block-comment continuation.
COMMENT_LEADS = ("#", "//", "*")

# The mode a tracked, invoked script must carry.
EXECUTABLE_MODE = "100755"

# The twin's own refusal status. Not 1: see the port notes.
EXIT_REFUSE = 2


def _git(root: str, *args: str) -> subprocess.CompletedProcess:
    """`git -C <root> ...`, never interactive, output captured.

    A missing `git` is a LOUD failure with the fix in the message rather than a traceback that reads as flake; see `refuse_missing_git`.
    """
    return subprocess.run(
        ["git", "-C", root, *args],
        capture_output=True,
        text=True,
        check=False,
    )


def is_comment_line(text: str) -> bool:
    """Does this line's CONTENT read as documentation rather than an invocation?

    The twin strips leading whitespace and then matches `'#'* | '//'* | '*'*`. Both false-positive cases it was written for are real: a Dockerfile that chmods its own subject, and a file that is SOURCED and needs no exec bit.
    """
    lead = text.lstrip()
    return lead.startswith(COMMENT_LEADS)


def first_ref(text: str) -> str | None:
    """The FIRST `./...sh` reference on a line, or None.

    `head -1` in the twin. A line naming two scripts contributes only the first, which is a known imprecision carried unchanged: narrowing it would change which paths are judged, and that is a behaviour change disguised as a fix.
    """
    match = REF_RE.search(text)
    if match is None:
        return None
    return match.group(0)


def resolve(src: str, ref: str) -> str:
    """Resolve `ref` against the DIRECTORY OF THE FILE THAT SAYS IT.

    `"$(dirname "$src")/${ref#./}"` then `${f#./}`. A file at the repo root gives
    dirname `.`, so the join produces `./x.sh` and the second strip removes the prefix. Deliberately NOT `os.path.normpath`: the twin does no normalisation, so a `sub/../x.sh` would be judged under that spelling on both sides, and normalising here would silently start judging a different path than the twin.
    """
    # `dirname` on a bare filename is `.` in the shell and `""` in Python. That one-character difference produced `/victim.sh` for every root-level reference, which is an absolute path and matches nothing in the index, so the gate would have reported a clean tree for exactly the files the 2026-08-20 incident was about. Caught by this file's own control.
    joined = "%s/%s" % (os.path.dirname(src) or ".", ref.removeprefix("./"))
    return joined.removeprefix("./")


def enumerate_hits(root: str) -> list[tuple[str, int, str]]:
    """`git grep -nP <ref> -- <pathspecs>` as (path, lineno, text) triples.

    THE FILE LIST COMES FROM GIT, THE MATCHING FROM PYTHON. See the port notes: git keeps ownership of the pathspec semantics, which is the part that would diverge invisibly if it were reimplemented.
    """
    listed = _git(root, "ls-files", "-z", "--", *PATHSPECS)
    if listed.returncode != 0:
        return []
    hits: list[tuple[str, int, str]] = []
    for name in listed.stdout.split("\0"):
        if not name:
            continue
        try:
            data = (pathlib.Path(root) / name).read_bytes()
        except OSError:
            # Tracked but absent from the working tree, or unreadable. `git grep` skips it too; a deletion that is real on disk and not in the index is a different gate's subject.
            continue
        if b"\0" in data:
            # `git grep` reports `Binary file X matches` instead of lines, which carries no line number and therefore contributes no reference.
            continue
        for number, line in enumerate(data.decode("utf-8", "replace").split("\n"), start=1):
            if REF_RE.search(line):
                hits.append((name, number, line))
    return hits


def referenced_paths(hits: list[tuple[str, int, str]]) -> list[str]:
    """Every path a hit resolves to, sorted and deduplicated.

    A PURE FUNCTION over the grep output on purpose, so the selftest can drive the parent-reference control without building a git repository. `sort -u` in the
    twin; `sorted(set(...))` here, and both run under `LC_ALL=C`, which
    `scripts/lib/shadow-gate.ts:buildEnv` pins for both sides.
    """
    out: set[str] = set()
    for src, _number, text in hits:
        if is_comment_line(text):
            continue
        ref = first_ref(text)
        if ref is None:
            continue
        out.add(resolve(src, ref))
    return sorted(out)


def scan_repo(root: str) -> list[str]:
    """Offenders under `root`, one `"<path> (mode <mode>)"` string per line.

    ONLY TRACKED PATHS ARE JUDGED, and the twin says why: "a `./x.sh` inside a heredoc meant for another checkout is not ours." An untracked path yields no mode and is skipped rather than reported.
    """
    offenders: list[str] = []
    for path in referenced_paths(enumerate_hits(root)):
        staged = _git(root, "ls-files", "-s", "--", path)
        mode = "\n".join(line.split()[0] for line in staged.stdout.splitlines() if line.split())
        if not mode:
            continue
        if mode == EXECUTABLE_MODE:
            continue
        offenders.append("%s (mode %s)" % (path, mode))
    return offenders


def build_control(directory: str) -> None:
    """The twin's control fixture, planted exactly as it plants it.

    TWO PLANTS AND A DECOY, and the decoy's PLACEMENT is the load-bearing part: `sub/decoy.sh` referenced as `../decoy.sh` from `sub/parentref.yml`. See the module docstring for the version of this control that could not fail.
    """
    root = pathlib.Path(directory)
    _git(directory, "init", "-q", ".")
    (root / "victim.sh").write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
    (root / "victim.sh").chmod(0o644)
    (root / "caller.yml").write_text("run: ./victim.sh\n", encoding="utf-8")
    (root / "sub").mkdir()
    (root / "sub" / "decoy.sh").write_text("#!/bin/bash\necho decoy\n", encoding="utf-8")
    (root / "sub" / "decoy.sh").chmod(0o644)
    (root / "sub" / "parentref.yml").write_text("run: ../decoy.sh\n", encoding="utf-8")
    _git(directory, "add", "-A")


def refuse(lines: list[str]) -> int:
    """Print a REFUSE block and return 2. Never 1, never 0."""
    print("%sREFUSE%s  %s" % (RED, OFF, lines[0]))
    for extra in lines[1:]:
        print("        %s" % extra)
    return EXIT_REFUSE


def main(argv: list[str] | None = None) -> int:
    """Run the gate. 0 clean, 1 offenders, 2 the controls could not fire.

    `--selftest` is intercepted BEFORE the control fixture is built, let alone the real scan. The twin takes no arguments and ignores any it is given.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    toplevel = subprocess.run(
        ["git", "rev-parse", "--show-toplevel"],
        capture_output=True,
        text=True,
        check=False,
    )

    with tempfile.TemporaryDirectory() as control_dir:
        try:
            build_control(control_dir)
        except OSError:
            return refuse(["could not build the control fixture"])

        # A parent-relative reference must NOT be mistaken for one relative to the referencing file. Counted with the twin's own anchor, `^sub/decoy.sh`.
        found = scan_repo(control_dir)
        parent_hits = sum(1 for line in found if line.startswith("sub/decoy.sh"))
        if parent_hits != 0:
            return refuse(
                [
                    "a ../decoy.sh reference was resolved as if it were",
                    "./decoy.sh relative to the referencing file. Those name DIFFERENT",
                    "files. The extraction regex has lost its anchor; see the comment",
                    "above this control.",
                ]
            )

        if len(found) < 1:
            return refuse(
                [
                    "the control did not fire: a planted non-executable",
                    "./victim.sh referenced from caller.yml was NOT reported.",
                    "A clean result from this gate would be meaningless, so it",
                    "refuses instead of printing one.",
                ]
            )

        # THE NEGATIVE CONTROL. The same fixture, made executable, must go quiet.
        (pathlib.Path(control_dir) / "victim.sh").chmod(0o755)
        _git(control_dir, "add", "-A")
        if len(scan_repo(control_dir)) != 0:
            return refuse(
                [
                    "the negative control fired: an EXECUTABLE script was",
                    "still reported. The detector flags everything, so a hit means",
                    "nothing.",
                ]
            )

    # ---- the real scan -----------------------------------------------------
    offenders = scan_repo(toplevel.stdout.strip())

    if offenders:
        print(
            "%s✗%s %d script(s) are invoked as ./path.sh but committed NON-executable:"
            % (RED, OFF, len(offenders))
        )
        print()
        for line in offenders:
            print("    %s" % line)
        print()
        print("  These fail at runtime with exit 126 BEFORE producing any output, so a")
        print("  caller that counts output lines sees a healthy run that did nothing.")
        print()
        print("  Fix:  git update-index --chmod=+x <path>")
        return 1

    print(
        "%s✓%s every ./path.sh reference resolves to a committed-executable script" % (GREEN, OFF)
    )
    print("  %scontrols:%s a planted non-executable script IS reported, and the same" % (YEL, OFF))
    print("  script made executable is NOT, so this green distinguishes the two.")
    return 0


def selftest() -> int:
    """Both directions on the extraction, the resolution and the comment filter.

    THE PLANT AND ITS MIRROR FOR EVERY RULE. A gate that only ever fires flags the whole tree; a gate that never fires reports every tree clean. So each rule below carries a case it must catch and a case it must ignore, and the floor is DERIVED from the corpus rather than typed, so a case that stops running turns the suite red instead of quietly shortening it.
    """
    # (label, source path, line text, expected resolved path or None)
    extraction = [
        ("a root-level invocation", "caller.yml", "run: ./victim.sh", "victim.sh"),
        (
            "a sibling invocation resolves against the REFERRER, not the root",
            ".ci/scripts/quality/x.sh",
            'bash ./helper.sh "$@"',
            ".ci/scripts/quality/helper.sh",
        ),
        # THE ANCHOR. Without the lookbehind this yields `./decoy.sh` and resolves to sub/decoy.sh, which is a DIFFERENT FILE.
        (
            "a parent reference is NOT a local reference",
            "sub/parentref.yml",
            "run: ../decoy.sh",
            None,
        ),
        ("a nested parent reference is skipped too", "a/b/c.sh", "source ../../x.sh", None),
        ("a path-like word with no ./ prefix is ignored", "a.sh", "bash scripts/x.sh", None),
        ("a .sh-less reference is ignored", "a.sh", "bash ./x.py", None),
    ]
    comments = [
        ("a shell comment is documentation", "# Usage: ./x.sh", True),
        ("a shellcheck directive is documentation", "# shellcheck source=./lib/x.sh", True),
        ("a C-style comment is documentation", "// see ./x.sh", True),
        ("a block-comment continuation is documentation", " * ./x.sh does the thing", True),
        ("an indented invocation is NOT documentation", "    bash ./x.sh", False),
        ("a bare invocation is NOT documentation", "./x.sh", False),
    ]

    floor = len(extraction) + len(comments) + 4
    ctl = Controls("script-exec-bit", floor=floor)

    for label, src, text, want in extraction:
        ref = first_ref(text)
        got = None if ref is None else resolve(src, ref)
        ctl.check("extract: %s" % label, got, want)
    for label, text, want in comments:
        ctl.check("comment: %s" % label, is_comment_line(text), want)

    # THE PARENT-REFERENCE CONTROL, as a SET comparison rather than a boolean, because that is the shape whose first version could not fail: the correct and the broken behaviour must produce DIFFERENT sets, so both are named.
    hits = [
        ("caller.yml", 1, "run: ./victim.sh"),
        ("sub/parentref.yml", 1, "run: ../decoy.sh"),
    ]
    ctl.check(
        "parent-ref control: only the local reference resolves",
        referenced_paths(hits),
        ["victim.sh"],
    )
    ctl.check(
        "parent-ref control: sub/decoy.sh is NOT in the set",
        "sub/decoy.sh" in referenced_paths(hits),
        False,
    )

    # THE REFUSAL IS 2, NOT 1. A port that collapsed them would make an unrunnable gate read as a failing tree.
    ctl.check("refuse() returns the twin's status", EXIT_REFUSE, 2)
    ctl.check("the executable mode is the git one", EXECUTABLE_MODE, "100755")

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
