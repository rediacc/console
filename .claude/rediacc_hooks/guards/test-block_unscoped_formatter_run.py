#!/usr/bin/env python3
"""Control harness for block_unscoped_formatter_run.

Both directions, because a one-sided control is satisfiable by a broken guard: one that always refuses passes every refusal case, one that never refuses passes every control. The last section plants the module's own DEFECT (the empty-set predicate answers "never empty") in-process and requires the 2026-10-07 command, and every other empty-set case, to stop being refused, so this harness can tell a working guard from a constant.
"""

import ast
import importlib.util
import json
import pathlib
import subprocess
import sys
import typing

HERE = pathlib.Path(__file__).resolve()
DISPATCH = str(HERE.parents[1] / "dispatch.py")
STEM = "block_unscoped_formatter_run"
GUARD_ARGV = [sys.executable, DISPATCH, STEM]

_SYSPATH = importlib.util.spec_from_file_location(
    "rediacc_hooks_syspath", HERE.parents[1] / "syspath.py"
)
_syspath = importlib.util.module_from_spec(_SYSPATH)  # type: ignore[arg-type]
_SYSPATH.loader.exec_module(_syspath)  # type: ignore[union-attr]
_syspath.on_sys_path(str(HERE.parents[2]))
from rediacc_hooks import hookio  # noqa: E402
from rediacc_hooks.guards import block_unscoped_formatter_run as guard  # noqa: E402

ROOT = hookio.repo_root()

# Which kind of refusal each blocked case must name: the planted DEFECT may only flip the EMPTY ones.
EMPTY, ROOTED = "EMPTY", "WHOLE TREE"

CASES = [
    # (name, command, expect: None = allowed, else the refusal kind)
    ("the 2026-10-07 command, verbatim shape", guard.INCIDENT, EMPTY),
    ("ruff format, no path", "ruff format", EMPTY),
    ("ruff check --fix, no path", "ruff check --fix", EMPTY),
    ("ruff check --fix-only, no path", "ruff check --fix-only --select I", EMPTY),
    ("only $(...)", "ruff format $(git diff --name-only -- '*.py')", EMPTY),
    ("-- before an empty $(...)", "ruff format -- $(git diff --name-only)", EMPTY),
    ("only a backtick span", "black `git ls-files '*.py'`", EMPTY),
    ("only an unquoted variable", "f=$(git diff --name-only); prettier --write $f", EMPTY),
    ("${var} braces", "eslint --fix ${files}", EMPTY),
    ('"$@" vanishes quoted', 'eslint --fix "$@"', EMPTY),
    ('"${arr[@]}" vanishes quoted', 'shfmt -w "${arr[@]}"', EMPTY),
    ("a test with || does not guard", '[ -n "$f" ] || ruff format $f', EMPTY),
    ("xargs without -r", "git diff --name-only | xargs npx prettier --write", EMPTY),
    ("gofmt -w, no path", "gofmt -w", EMPTY),
    ("goimports -w, no path", "goimports -w -local example.com", EMPTY),
    ("shfmt -w, no path", "shfmt -w -i 2", EMPTY),
    ("golangci-lint run --fix, no path", "golangci-lint run --fix", EMPTY),
    ("biome check --write, no path", "npx @biomejs/biome check --write", EMPTY),
    ("npm exec launcher", "npm exec -- prettier --write $(git ls-files '*.md')", EMPTY),
    ("uv run launcher", "uv run --frozen ruff format", EMPTY),
    ("uvx launcher", "uvx ruff check --fix", EMPTY),
    ("python -m launcher", "python3 -m black --line-length 100", EMPTY),
    ("inside bash -c", "bash -c 'ruff format'", EMPTY),
    ("behind timeout and env", "timeout 60 env X=1 ruff format", EMPTY),
    ("dot at the repo root", "ruff format .", ROOTED),
    ("dot-slash at the repo root", "npx eslint --fix ./", ROOTED),
    ("the absolute root", "ruff format %s" % ROOT, ROOTED),
    ("up to the root from a child", "cd packages && ruff format ..", ROOTED),
    ("a ** glob at the root", 'npx prettier --write "**/*.md"', ROOTED),
    ("go fmt ./... at the root", "go fmt ./...", ROOTED),
    ("a variable assigned the root", "F=.; ruff format $F", ROOTED),
    ("dot beside a real file", "ruff format a.py .", ROOTED),
    # --- controls: each must be allowed ---
    ("explicit paths after --", "ruff format -- a.py b.py", None),
    ("explicit paths, no --", "black a.py b.py", None),
    ("ruff format --check, no path", "ruff format --check", None),
    ("ruff format --diff, no path", "ruff format --diff", None),
    ("ruff check, no --fix", "ruff check", None),
    ("ruff check --fix --no-fix", "ruff check --fix --no-fix", None),
    ("black --check", "black --check", None),
    ("prettier --check", "npx prettier --check", None),
    ("eslint without --fix", "npx eslint", None),
    ("eslint --fix-dry-run", "npx eslint --fix-dry-run", None),
    ("gofmt -l", "gofmt -l", None),
    ("shfmt -d", "shfmt -d", None),
    ("golangci-lint run, no --fix", "golangci-lint run", None),
    ("go fmt -n", "go fmt -n ./...", None),
    (
        "a guarded variable with &&",
        'f=$(git diff --name-only); [ -n "$f" ] && ruff format -- $f',
        None,
    ),
    ("a guarded variable in if", 'if [ -n "$f" ]; then ruff format -- $f; fi', None),
    ("${x:?} aborts on empty", "ruff format ${files:?no files}", None),
    ('a quoted "$f"', 'ruff format "$f"', None),
    ("a quoted substitution", 'ruff format "$(git diff --name-only | head -1)"', None),
    ("a literal beside a substitution", "ruff format a.py $(git diff --name-only)", None),
    ("prefix text in the word", "ruff format src/$name.py", None),
    ("a literal list in a variable", 'F="a.py b.py"; ruff format $F', None),
    ("a for-loop variable", "for f in a.py b.py; do black $f; done", None),
    ("xargs -r", "git diff --name-only | xargs -r npx prettier --write", None),
    ("xargs -0r", "git ls-files -z | xargs -0r ruff format", None),
    ("xargs --no-run-if-empty", "git ls-files | xargs --no-run-if-empty gofmt -w", None),
    ("a subdirectory dot", "cd packages/cli && npx eslint --fix .", None),
    ("a subdirectory by name", "ruff format .claude/rediacc_hooks", None),
    ("a scoped ** glob", 'npx prettier --write "docs/**/*.md"', None),
    ("a top-level glob only", "ruff format *.py", None),
    ("stdin with -", "ruff format - < a.py", None),
    ("stdin with --stdin-filename", "ruff format --stdin-filename a.py < a.py", None),
    ("biome over staged files", "npx biome check --write --staged", None),
    ("an option value is not a path", "ruff format --config pyproject.toml a.py", None),
    ("a computed cd skips the root test", 'cd "$D" && ruff format .', None),
    ("prose is not a run", "echo 'ruff format'", None),
    ("a commit message is not a run", 'git commit -m "ruff format ." -- a.py', None),
    ("a remote operand is not this tree", "ssh host 'ruff format'", None),
    ("a different tool named ruff-ish", "ruffle format", None),
]


def answer(cmd):
    p = subprocess.run(
        GUARD_ARGV,
        input=json.dumps({"tool_input": {"command": cmd}, "cwd": str(ROOT)}),
        capture_output=True,
        text=True,
        check=False,
        cwd=str(ROOT),
    )
    return p.returncode, p.stderr


fails = 0
blocked = allowed = 0
for name, cmd, want in CASES:
    rc, err = answer(cmd)
    got = None
    if rc == 2:
        got = EMPTY if "EMPTY" in err else ROOTED if "WHOLE TREE" in err else "?"
    ok = got == want and rc in (0, 2)
    blocked += want is not None
    allowed += want is None
    fails += not ok
    print(
        "%-42s want=%-10s got=%-14s %s"
        % (
            name,
            want or "allowed",
            got or ("allowed" if rc == 0 else "rc=%d" % rc),
            "ok" if ok else "*** FAIL ***",
        )
    )

# The refusal must carry the safe form, and must say `--` alone is not it.
rc, err = answer(guard.INCIDENT)
safe = (
    "ruff format -- <path>" in err
    and '[ -n "$files" ] && ruff format -- $files' in err
    and "xargs -r ruff format" in err
    and "`--` alone does not help" in err
)
fails += not safe
print("%-42s %s" % ("message carries the safe forms", "ok" if safe else "*** FAIL ***\n" + err))

# MUTATION: the module's own DEFECT, planted in a copy of its source. Every EMPTY case must stop being refused (the green above depends on that branch), and every WHOLE TREE case must still be refused (the defect is the empty-set predicate, nothing wider).
old, new = guard.DEFECT
source = pathlib.Path(guard.__file__).read_text(encoding="utf-8")
# The declaration itself spells `old`, so it is cut by AST before the search, or the search could never fail.
decl = next(
    n
    for n in ast.parse(source).body
    if isinstance(n, ast.Assign) and any(getattr(t, "id", "") == "DEFECT" for t in n.targets)
)
lines = source.split("\n")
body = "\n".join(lines[: decl.lineno - 1] + lines[decl.end_lineno :])
if old not in body:
    fails += 1
    print("*** FAIL *** DEFECT no longer applies outside its own declaration: %r" % old)
namespace: dict[str, typing.Any] = {"__name__": "broken_" + STEM, "__file__": guard.__file__}
head, tail = "\n".join(lines[: decl.end_lineno]), "\n".join(lines[decl.end_lineno :])
mutant = head + "\n" + tail.replace(old, new)
if mutant == source:
    fails += 1
    print("*** FAIL *** planting the DEFECT changed nothing, so the mutation below proves nothing")
exec(compile(mutant, guard.__file__, "exec"), namespace)  # noqa: S102
flipped = still = 0
for _name, cmd, want in CASES:
    if want is None:
        continue
    event = hookio.Event(
        json.dumps({"tool_input": {"command": cmd}, "cwd": str(ROOT)}), cwd=str(ROOT)
    )
    rc = namespace["run"](event)
    if want == EMPTY:
        flipped += rc == hookio.ALLOW
        if rc != hookio.ALLOW:
            fails += 1
            print("%-42s *** FAIL *** mutant still refuses %r" % ("mutation", cmd))
    else:
        still += rc == hookio.DENY
empties = sum(1 for _, _, w in CASES if w == EMPTY)
rooted = sum(1 for _, _, w in CASES if w == ROOTED)
red = flipped == empties and still == rooted
fails += not red
print(
    "%-42s %s (%d/%d EMPTY cases go red, %d/%d WHOLE TREE cases unaffected)"
    % ("mutation: DEFECT planted", "ok" if red else "*** FAIL ***", flipped, empties, still, rooted)
)

# Zero cases would be a green that verified nothing.
if blocked == 0 or allowed == 0:
    fails += 1
    print("*** FAIL *** a direction has no cases: %d blocked, %d allowed" % (blocked, allowed))

print()
print("%d case(s): %d must be refused, %d must be allowed" % (len(CASES), blocked, allowed))
print("FAILURES: %d" % fails)
sys.exit(1 if fails else 0)
