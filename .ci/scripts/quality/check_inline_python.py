#!/usr/bin/env python3
"""Refuse Python source embedded inside JavaScript/TypeScript.

WHY THIS EXISTS. A ruff gate landed on 2026-08-06 that lints every TRACKED .py
file. Python living inside a JS/TS string literal is invisible to it: never
linted, never formatted, never type-checked by anything at all. That blind spot
was not hypothetical -- packages/cli/src/remote/vscode/bootstrap.ts held a
130-line, 4871-character Python program in a template literal, and four of the
six values interpolated into it went in unescaped. Python's own parser confirms
the consequence: a universalUser of `'; import os; os.system('id'); x='` parses
cleanly and turns the middle into executable Python, which then runs on a remote
host under `sudo -u`. Nothing in the repo could have seen it, because no tool
looks inside a template literal.

THE RULE, and why it is drawn this way. "Mentions Python" is far too wide: of
999 tracked JS/TS files, four match /python3?/ and THREE of those are innocent
(an interpreter binary name in a config default, the word "python" inside a word
list, and the string "check:ci-python-lint"). A rule that flagged those would be
turned off within a week. So a file is flagged only when a string in it looks
like Python SOURCE -- two or more distinct statement-shaped signals, each at the
start of a line, inside one quoted region. Naming the interpreter is not a
finding; shipping a program is.

THIS IS A DETECTOR, NOT A PARSER, and the difference is stated rather than
hidden: it reads quoted regions with a small scanner instead of a JS grammar. It
can therefore be fooled by source that assembles Python from fragments, and it
is not asked to catch that. What it does catch is the shape the incident
actually took -- a readable program pasted into a template literal -- and it
catches it before review rather than after.

Run modes:
    check_inline_python.py            scan every tracked JS/TS file (the gate)
    check_inline_python.py --file P   judge ONE file, for the pre-edit hook
    check_inline_python.py --selftest controls only, no repo scan
"""

import argparse
import pathlib
import re
import subprocess
import sys

# Statement shapes that only appear in real Python. Each must match at the START
# of a line inside a quoted region, which is what keeps prose and identifiers
# from scoring: a JS file may well contain the word "import", but not at the
# head of a line inside a string, followed by a stdlib module name.
_SIGNALS = (
    re.compile(
        r"^\s*import\s+(os|sys|json|re|pathlib|subprocess|shutil|pwd|grp|time)\b", re.MULTILINE
    ),
    re.compile(r"^\s*from\s+[A-Za-z_][\w.]*\s+import\s+\w", re.MULTILINE),
    re.compile(r"^\s*def\s+[A-Za-z_]\w*\s*\(", re.MULTILINE),
    re.compile(r"^\s*class\s+[A-Za-z_]\w*\s*[(:]", re.MULTILINE),
    re.compile(r"^\s*if\s+__name__\s*==", re.MULTILINE),
    re.compile(r"^\s*(?:el)?if\s+.+:\s*$", re.MULTILINE),
    re.compile(r"^\s*(?:try|except|finally|else)\s*(?:\w[\w.]*\s*)?:\s*$", re.MULTILINE),
    re.compile(r"^\s*print\s*\(", re.MULTILINE),
)

# `python -c` / `python3 -c` given anything other than a trivial literal. The
# interpreter NAME on its own is deliberately not a signal (that is the
# generate-tutorial-audio.ts false positive), so this needs the -c flag.
_DASH_C = re.compile(r"python3?\s+-c\b")

# Quoted regions: template literals, single and double quotes. Backslash escapes
# are honoured so an escaped quote does not end a region early.
_REGION = re.compile(
    r"`(?:[^`\\]|\\.)*`" r"|'(?:[^'\\\n]|\\.)*'" r'|"(?:[^"\\\n]|\\.)*"',
    re.DOTALL,
)

MIN_SIGNALS = 2


def findings(text):
    """[(line_number, why)] for one file's source. Empty means clean."""
    out = []
    for m in _REGION.finditer(text):
        region = m.group(0)
        if "\n" not in region:
            continue  # a one-line string cannot hold a program worth linting
        hits = sorted({p.pattern for p in _SIGNALS if p.search(region)})
        if len(hits) >= MIN_SIGNALS:
            out.append(
                (
                    text.count("\n", 0, m.start()) + 1,
                    "a %d-line quoted region matches %d Python statement shapes"
                    % (region.count("\n") + 1, len(hits)),
                )
            )
    for m in _DASH_C.finditer(text):
        line_start = text.rfind("\n", 0, m.start()) + 1
        line = text[line_start : text.find("\n", m.start())]
        # `python3 -c` naming a module path or a short fixed probe is fine; what
        # is not fine is handing it source assembled in this file.
        if "${" in line or "+" in line.split("-c", 1)[1]:
            out.append(
                (
                    text.count("\n", 0, m.start()) + 1,
                    "python -c is handed source built in this file",
                )
            )
    return out


# ---- controls ---------------------------------------------------------------
# A detector that cannot fire would report a clean tree forever. Both directions
# are proven before any real file is read: it must FLAG a planted program, and
# it must CLEAR the three real, benign shapes that exist in this repo today.
_MUST_FLAG = [
    (
        "a program in a template literal",
        "const s = `\nimport os\nimport pathlib\n\ndef go():\n    print(os.getcwd())\n`;\n",
    ),
    ("python -c handed an interpolation", "const c = `python3 -c '${script}'`;\n"),
]
_MUST_CLEAR = [
    ("naming the interpreter binary", "const pythonBin = process.env.BIN || 'python3';\n"),
    ("the word python in a list", "const words = ['bash', 'git', 'npm', 'node', 'python'];\n"),
    ("a gate id that contains python", "{ id: 'check:ci-python-lint', gate: true }\n"),
    (
        "prose mentioning def and import",
        "// we import os-level defaults here\nconst x = 'import the config, then define it';\n",
    ),
]


def selftest():
    bad = 0
    for name, src in _MUST_FLAG:
        if not findings(src):
            print("CONTROL FAILED (should flag): %s" % name, file=sys.stderr)
            bad += 1
    for name, src in _MUST_CLEAR:
        got = findings(src)
        if got:
            print("CONTROL FAILED (should clear): %s -> %r" % (name, got), file=sys.stderr)
            bad += 1
    return bad


MIN_FILES = 200  # the tree holds ~999; a collapsed glob must not read as clean


def tracked_files(root):
    out = subprocess.run(
        ["git", "-C", str(root), "ls-files", "--", "*.ts", "*.js", "*.cjs", "*.mjs"],
        capture_output=True,
        text=True,
        check=False,
    )
    if out.returncode != 0:
        return None
    return [f for f in out.stdout.split() if not f.startswith("private/")]


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--file", help="judge a single file (used by the pre-edit hook)")
    ap.add_argument("--selftest", action="store_true", help="run controls only")
    args = ap.parse_args(argv)

    root = pathlib.Path(__file__).resolve().parents[3]

    if selftest():
        print(
            "refusing to report a verdict: the detector's own controls do not hold",
            file=sys.stderr,
        )
        return 1
    if args.selftest:
        print("controls hold: %d flag-cases, %d clear-cases" % (len(_MUST_FLAG), len(_MUST_CLEAR)))
        return 0

    if args.file:
        p = pathlib.Path(args.file)
        try:
            text = p.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            print("cannot read %s: %s" % (p, exc), file=sys.stderr)
            return 1
        hits = findings(text)
        for line, why in hits:
            print("%s:%d: inline Python -- %s" % (p, line, why), file=sys.stderr)
        return 1 if hits else 0

    files = tracked_files(root)
    if files is None:
        print("VACUOUS INPUT: %s is not a git work tree" % root, file=sys.stderr)
        return 1
    if len(files) < MIN_FILES:
        print(
            "VACUOUS INPUT: only %d JS/TS file(s) found, expected at least %d"
            % (len(files), MIN_FILES),
            file=sys.stderr,
        )
        return 1

    total = 0
    for rel in files:
        try:
            text = (root / rel).read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line, why in findings(text):
            print("%s:%d: inline Python -- %s" % (rel, line, why), file=sys.stderr)
            total += 1
    if total:
        print(file=sys.stderr)
        print(
            "%d embedded Python program(s) in JS/TS. Move the source into a real .py\n"
            "file so ruff can see it; a string literal is not a place a program can be\n"
            "linted, formatted or reviewed." % total,
            file=sys.stderr,
        )
        return 1
    print("no inline Python in %d tracked JS/TS file(s)" % len(files))
    return 0


if __name__ == "__main__":
    sys.exit(main())
