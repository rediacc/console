#!/usr/bin/env python3
"""check:ci-policy-inventory -- the `.ci/policy/` contract, in four directions plus the prose.

THE DRIFT THIS EXISTS FOR ALREADY HAPPENED, one day after the move that created the directory. `.language-policy-allowlist` landed on 2026-09-07 with `check:ci-language-policy`: sixteen dotfiles were on disk, `POLICY_FILES` in `scripts/lib/policy-paths.ts` held fifteen names, and the new gate reached its allowlist through a hardcoded `ROOT / ".ci" / "policy" / ...` join that
bypassed the seam entirely. Nothing was red for a day. Every gate that touched a policy file kept working, because a reader that hardcodes the path does not need the list to know about it -- which is exactly why the list going stale is invisible without this gate.

THE CONTROL THAT PROVES IT IS THE GATE FOR THAT DEFECT was run at authoring time against the tree where it happened, worktree-free:

    GIT_INDEX_FILE=/tmp/hist.idx git read-tree 19c45c78e
    GIT_INDEX_FILE=/tmp/hist.idx git checkout-index -a --prefix="$scratch/"
    cp .ci/rediacc_ci/policy_paths.py "$scratch/.ci/rediacc_ci/"

`git archive` CANNOT be used for this, which is worth recording because it is the obvious first try: `.gitattributes:55` sets `* export-ignore` with a single `LICENSE -export-ignore` beneath it, so an archive of any commit in this repository contains exactly one file. A detached `GIT_INDEX_FILE` plus `checkout-index --prefix` writes the whole tree without touching the worktree or
the real index, which is what the two lines above do.
    POLICY_INVENTORY_ROOT="$scratch" .ci/scripts/quality/check_policy_inventory.py

and it reported exit 1 naming exactly one policy file, `.language-policy-allowlist`, in the inventory directions. The Python twin is COPIED IN because it is the instrument being added, not part of the tree under judgement; the inventory question it answers there is about the directory and the TypeScript list, which are the two things that had actually drifted.

WHY THE SAME CONTROL IS NOT BAKED INTO `selftest()`. It would need `git archive <sha>`, and CI clones this repository shallow everywhere except the `quality-i18n` lane (see the manifest note on `check:ci-plan-housekeeping`). A control that cannot run in CI is a control that reports nothing there, so the baked-in version below reconstructs the same SHAPE from a synthetic fixture --
one more file on disk than the TypeScript list knows about -- and the historical run stays here in prose, with its command, as the evidence that the shape is the real one.

THE FOUR DIRECTIONS, and each is a different failure:

  1. A file in `.ci/policy/` that is in NO list. The 2026-09-07 case. Its
     suppressions are live and unaccounted for.
  2. A name in a list with no file in `.ci/policy/`. Worse than it sounds: every
     mechanism in this repo reads a missing policy file as ZERO ENTRIES, which
     is indistinguishable from "nothing is suppressed". A deleted list is a
     silently emptied one.
  3. The Python list against the TypeScript list, plus `POLICY_DIR` against
     `POLICY_DIR`. Two seams that disagree are two live locations, which is the
     thing rule 3 of both modules refuses.
  4. A literal policy-path join outside the two seams. A reader that hardcodes
     the path is a reader the next move will leave behind, and it is invisible
     to directions 1-3 because it needs no list entry to work.

PLUS THE PROSE, which is direction 4 pointed at comments rather than code (W4 P4c). Two rules, and the first one was written because a comment in `scripts/gates/check-suppression-liveness.ts` still said "Today POLICY_DIR is '' and this is a provable no-op" for two days after `b80552370` made POLICY_DIR `.ci/policy`. A comment that states a value is a claim a reader will act on:

  5. No comment may assert a POLICY_DIR value differing from the one in
     `scripts/lib/policy-paths.ts`, which is the ORACLE here and is read out of
     that file rather than typed into this one.
  6. No comment may cite a policy file by a path whose directory is not the
     policy directory. `.ci/policy/.audit-allowlist` and the bare name
     `.audit-allowlist` are both fine; `$ROOT/<name>` is a citation of a location
     that has not existed since the move. The example is written with a
     placeholder rather than a real name BECAUSE THIS GATE JUDGES ITS OWN
     DOCSTRING: the first draft of this paragraph spelled the name out and the
     gate reported itself, correctly.

PAST TENSE IS NOT AN ASSERTION, and rule 5 has to know the difference or it becomes a machine for deleting the repository's own record of what went wrong. `.claude/hooks/pre-bash/block-pathspecless-git-commit.sh:27` says HEAD "still
read `const POLICY_DIR = '';`" while describing the half-landed state of
2026-09-06. That sentence is true, is load-bearing history, and must not be a finding; `_PAST_MARKERS` is what keeps it out, and the control below drives that exact line.

ANTI-VACUITY, REFUSED PER CORPUS. Four separate refusals, not one: an empty directory listing, an empty TypeScript list, an empty Python list and an empty file corpus each exit 1 with their own message. A populated half does not excuse an empty half -- the whole point of a three-way equality is that any two of them agreeing proves nothing about the third. The success line prints
every count, so a collapse is visible rather than silent.

Exit 1 on any finding or refusal, 2 on a failed control.

---- gate ---- step: Policy inventory needs: none lane: quality-static selftest: true why: the `.ci/policy/` directory, the TypeScript POLICY_FILES and the Python
     POLICY_FILES must be one set; a file in the directory that is in neither
     list is a live suppression nobody is counting, and a name with no file
     reads to every consumer as "nothing is suppressed"
---- end gate ----
"""

from __future__ import annotations

import ast
import io
import os
import pathlib
import re
import subprocess
import sys
import tempfile
import tokenize

import _cipath  # noqa: F401
from rediacc_ci.controls import Controls, plant
from rediacc_ci.policy_paths import policy_path

RED = "\033[0;31m"
GREEN = "\033[0;32m"
YELLOW = "\033[0;33m"
NC = "\033[0m"

ROOT_ENV = "POLICY_INVENTORY_ROOT"

# The two files that are ALLOWED to know where a policy file lives. Everything
# else asks one of them.
TS_SEAM = "scripts/lib/policy-paths.ts"
PY_SEAM = ".ci/rediacc_ci/policy_paths.py"
SEAMS = (TS_SEAM, PY_SEAM)

# The one non-dotfile in `.ci/policy/`. Exempt BY NAME with its reason, and counted in the success line, because a silent exemption is how a directory listing quietly stops meaning what the gate says it means.
DIRECTORY_EXEMPT = {"README.md": "the directory's own predicate and move record, not policy"}

# Exempt BY NAME, printed on every run with the offending lines. `paths:` in the manifest is a repo-RELATIVE change-selector consumed by `--changed`, not a read: `policyPath()` answers an ABSOLUTE path, so routing this through the seam would break gate selection rather than harden it.
NAMED_EXEMPT = {
    "scripts/ci-runner/manifest.ts": (
        "a `paths:` change-selector, repo-relative by contract; the seam answers "
        "absolute paths and would break `--changed`"
    )
}

# ---- direction 7: the refusal W4 P5 recorded ---------------------------------
#
# `.ci/policy/README.md` section 6 REFUSES `.ci/config/bws-secret-map.json` entry to this directory, on three of the four section 1 clauses. A refusal that lives only in prose is a refusal nobody re-derives, so the three clauses are asserted here every run. Each one is mechanical, and each one can flip:
#
# 1. the file EXISTS. A refusal about a file that is gone is a stale paragraph, not a decision, and it must stop being asserted rather than pass vacuously. 2. it is NOT here. Not under POLICY_DIR, and its name is in neither seam. 3. it carries ZERO `BLOCKER:` lines. This is the live one: writing reasons into it is exactly what would make clause 2 of the section 1 predicate stop
# failing, at which point the refusal is no longer complete and a human has to re-run the predicate.
#
# The fix for a red here is never to widen this gate. It is to re-run section 1 against the file and rewrite section 6 with whatever the new answer is.
REFUSED_FILE = ".ci/config/bws-secret-map.json"
REFUSED_RECORD = ".ci/policy/README.md section 6"

CODE_EXTS = (".py", ".ts", ".js", ".cjs", ".mjs")
SHELL_EXTS = (".sh",)
SCANNED_EXTS = CODE_EXTS + SHELL_EXTS

# Directories a walk must not descend into. Only reached when `git ls-files` is unavailable (a scratch tree extracted with `git archive`).
WALK_SKIP = {".git", "node_modules", "private", "dist", "build", "__pycache__", "cache"}

# Present-tense assertions of a value. `was`, `went from` and `still read` are reports of history and are not findings; see the module docstring.
_POLICY_DIR_CLAIM = re.compile(
    r"POLICY_DIR\s+(?:is|remains|stays)\s+[\"'`]([^\"'`]*)[\"'`]"
    r"|POLICY_DIR\s*(?:=|:)\s*[\"'`]([^\"'`]*)[\"'`]"
)
_PAST_MARKERS = (
    "still read",
    "used to",
    "went from",
    " was ",
    " were ",
    "had been",
    "before the move",
    "no longer",
    "until the move",
)


class RefusalError(Exception):
    """The gate cannot see its subject, so no verdict it printed would mean anything."""


def repo_root() -> pathlib.Path:
    """The tree under judgement. Resolved at CALL time so a control can point it elsewhere.

    A module-level constant would make every refusal below untestable, which is the shape this repo keeps getting caught by: an anti-vacuity arm nothing can reach is an arm nobody has seen fail.
    """
    override = os.environ.get(ROOT_ENV)
    if override:
        return pathlib.Path(override)
    return pathlib.Path(__file__).resolve().parents[3]


# ---- the three name sets ----------------------------------------------------


def ts_policy_dir(root: pathlib.Path) -> str:
    """POLICY_DIR out of the TypeScript seam. THE ORACLE for rule 5."""
    text = _read(root / TS_SEAM)
    m = re.search(r"const\s+POLICY_DIR\s*=\s*'([^']*)'", text)
    if m is None:
        raise RefusalError("no `const POLICY_DIR = '...'` in %s" % TS_SEAM)
    return m.group(1)


def ts_names(root: pathlib.Path) -> list[str]:
    """POLICY_FILES out of the TypeScript seam, comment lines skipped."""
    text = _read(root / TS_SEAM)
    m = re.search(r"const\s+POLICY_FILES\s*=\s*Object\.freeze\(\[(.*?)\]", text, re.DOTALL)
    if m is None:
        raise RefusalError("no `const POLICY_FILES = Object.freeze([...])` in %s" % TS_SEAM)
    out = []
    for line in m.group(1).splitlines():
        stripped = line.strip()
        if stripped.startswith("//"):
            continue
        out.extend(re.findall(r"'([^']+)'", stripped))
    return sorted(out)


def py_policy_dir(root: pathlib.Path) -> str:
    """POLICY_DIR out of the Python seam, parsed rather than imported.

    PARSED ON PURPOSE. Importing would answer for the instrument's own copy, and the question is about the tree being judged -- which for a fixture, or for a historical tree, is a different file.
    """
    value = _py_constant(root, "POLICY_DIR")
    if not isinstance(value, str):
        raise RefusalError("POLICY_DIR in %s is not a string" % PY_SEAM)
    return value


def py_names(root: pathlib.Path) -> list[str]:
    """POLICY_FILES out of the Python seam, parsed rather than imported."""
    value = _py_constant(root, "POLICY_FILES")
    if not isinstance(value, (tuple, list)):
        raise RefusalError("POLICY_FILES in %s is not a tuple" % PY_SEAM)
    return sorted(str(v) for v in value)


def _py_constant(root: pathlib.Path, name: str) -> object:
    tree = ast.parse(_read(root / PY_SEAM))
    for node in tree.body:
        targets = []
        if isinstance(node, ast.Assign):
            targets = [t.id for t in node.targets if isinstance(t, ast.Name)]
            value = node.value
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            targets = [node.target.id]
            value = node.value
        else:
            continue
        if name in targets and value is not None:
            return ast.literal_eval(value)
    raise RefusalError("no module-level `%s` in %s" % (name, PY_SEAM))


def directory_names(root: pathlib.Path, policy_dir: str) -> list[str]:
    """Everything in the policy directory that is not exempt by name."""
    d = root / policy_dir
    if not d.is_dir():
        raise RefusalError("%s is not a directory in the tree under judgement" % policy_dir)
    return sorted(p.name for p in d.iterdir() if p.name not in DIRECTORY_EXEMPT)


def _read(path: pathlib.Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except OSError as exc:
        raise RefusalError("cannot read %s: %s" % (path, exc)) from exc


# ---- the corpus -------------------------------------------------------------


def source_files(root: pathlib.Path) -> tuple[list[str], str]:
    """(repo-relative paths, how they were enumerated).

    `git ls-files` when the root is a checkout, a filtered walk otherwise. The enumerator is RETURNED rather than hidden because a silent fallback that changes the corpus is the same class of defect as a silent exemption; the success line prints which one ran.

    UNTRACKED FILES ARE IN SCOPE, and in this repository that is not a detail. The house rule is that work stays UNCOMMITTED until the operator asks, so a new gate and its readers live untracked for days. A tracked-only corpus cannot see them, which means the one moment a hardcoded join is easiest to fix -- while its author is still holding it -- is exactly the moment this gate
    would have been blind. Measured while writing this gate: its own file was invisible to it, and the two findings it should have reported against its own docstring only appeared when the corpus was widened.
    """
    try:
        seen: set[str] = set()
        ok = False
        for extra in ([], ["--others", "--exclude-standard"]):
            proc = subprocess.run(
                ["git", "-C", str(root), "ls-files", "-z", *extra],
                capture_output=True,
                check=False,
                text=True,
            )
            if proc.returncode != 0:
                ok = False
                break
            ok = True
            seen.update(n for n in proc.stdout.split("\0") if n.endswith(SCANNED_EXTS))
        if ok and seen:
            return sorted(seen), "git ls-files (tracked + untracked)"
    except OSError:
        pass
    out = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in WALK_SKIP]
        out.extend(
            os.path.relpath(os.path.join(dirpath, f), str(root))
            for f in filenames
            if f.endswith(SCANNED_EXTS)
        )
    return sorted(out), "filesystem walk"


# ---- direction 4: literal joins ---------------------------------------------


def mentions_policy(source: str, names: frozenset[str], policy_dir: str) -> bool:
    """Could this file hold a finding at all?

    EXACT, NOT A HEURISTIC, and that distinction is the whole licence for it. Every predicate in this gate needs one of three literals present in the text before it can match anything: a policy NAME (both join shapes and the citation rule), the string `POLICY_DIR` (the claim rule), or the policy DIRECTORY. A file containing none of them cannot produce a finding, so skipping it
    changes no verdict -- it only stops the gate from AST-parsing and tokenising 2300 files to prove they say nothing.

    Measured on this tree 2026-09-08: 2381 files enumerated, 77 candidates, 13.9s -> 2.0s. The count of candidates is PRINTED, because a pre-filter that silently matched nothing would make every direction below vacuous, which is why `scan()` refuses on zero rather than reporting agreement.
    """
    if "POLICY_DIR" in source or policy_dir in source:
        return True
    return any(name in source for name in names)


def _is_test_path(rel: str) -> bool:
    base = os.path.basename(rel)
    return (
        "/tests/" in rel
        or "/__tests__/" in rel
        or rel.startswith(".ci/scripts/test/")
        or base.startswith(("test_", "test-"))
    )


def python_join_sites(source: str, names: frozenset[str], policy_dir: str) -> list[tuple[int, str]]:
    """(line, name) for every literal policy-path join in Python source.

    TWO SHAPES, and both are joins rather than prose:
      * a string constant that IS `<policy_dir>/<name>` and nothing else, and
      * a string constant that IS a bare policy NAME and is an operand of a `/`
        path expression or an argument to `os.path.join` / `Path`.

    A bare name on its own is NOT a finding, and that is the important exclusion: `policy_path(".audit-allowlist")` is a name handed TO the seam, which is the shape this gate wants everywhere. A name embedded in a longer sentence is not a finding either -- `"... held in .ci/policy/.audit-allowlist"` is a message printed at a human, and rewriting it through the seam would change
    what the reader is told, not where the file is read from.
    """
    tree = ast.parse(source)
    docstrings = set()
    for node in ast.walk(tree):
        body = getattr(node, "body", None)
        if (
            isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
            and body
            and isinstance(body[0], ast.Expr)
            and isinstance(body[0].value, ast.Constant)
            and isinstance(body[0].value.value, str)
        ):
            docstrings.add(id(body[0].value))
    for node in ast.walk(tree):
        for child in ast.iter_child_nodes(node):
            child.parent = node  # type: ignore[attr-defined]

    joiners = {"os.path.join", "posixpath.join", "pathlib.Path", "Path"}
    out = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        value = node.value
        for name in names:
            if value == "%s/%s" % (policy_dir, name):
                out.append((node.lineno, name))
                break
            if value != name:
                continue
            parent = getattr(node, "parent", None)
            joined = isinstance(parent, ast.BinOp) and isinstance(parent.op, ast.Div)
            called = isinstance(parent, ast.Call) and ast.unparse(parent.func) in joiners
            if joined or called:
                out.append((node.lineno, name))
            break
    return out


def _opens_a_comment(rel: str, line: str, i: int) -> bool:
    """Does a comment start at `line[i]`? Shell `#`, or C-style `//`.

    Named rather than written as two `elif` arms so the shell and C-style cases stay legible; ruff's SIM114 is right that they share a body, and an `or` of two four-term conditions inline is not the way to say it.
    """
    if rel.endswith(SHELL_EXTS):
        return line[i] == "#" and (i == 0 or line[i - 1].isspace())
    return line.startswith("//", i)


def _strip_comment(rel: str, line: str) -> str:
    """The CODE half of one line: everything before an out-of-string comment marker.

    THE JOIN SCAN MUST NOT RULE ON PROSE, and a shell comment reading `# see .ci/policy/.audit-allowlist` is a bare word that looks exactly like a path in argument position. Quote state is tracked rather than assumed because `"http://x"` is not a comment and `# "` does not open a string.
    """
    stripped = line.lstrip()
    # No shell arm here: a `#` at column 0 or after whitespace is already caught by the loop below, and a mutant that deleted an early return for it changed nothing measurable, so the line is not carried. The C-style arm IS needed: a jsdoc continuation ` * text` carries no `//` for the loop to find.
    if not rel.endswith(SHELL_EXTS) and stripped.startswith(("//", "/*", "*")):
        return ""
    quote = ""
    i = 0
    while i < len(line):
        ch = line[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = ""
        elif ch in "\"'`":
            quote = ch
        elif _opens_a_comment(rel, line, i):
            return line[:i]
        i += 1
    return line


def _quoted_spans(text: str):
    """(first line, content, is_quoted) for every quoted string and every gap between them.

    OVER THE WHOLE FILE, NOT LINE BY LINE, and that is not a refinement. The first version worked a line at a time, so a line INSIDE a multi-line template literal carried no quote character of its own and was read as bare code: the help text in `scripts/gates/check-actions.ts:382` and `scripts/gates/check-deps.ts:678` ("Actions can be blocklisted in
    .ci/policy/.actions-upgrade-blocklist to prevent...") became two joins that are not joins. A span that spans lines contains whitespace, which is exactly what the caller uses to tell a path from a sentence, so tracking the state across lines is what makes the discriminator mean what it says.

    Comments are already gone by the time this runs, which matters: an apostrophe in `# the gate's own list` would otherwise open a string that never closes and swallow the rest of the file.
    """
    out = []
    quote = ""
    buf: list[str] = []
    line = 1
    start = 1
    for ch in text:
        if quote:
            if ch == quote:
                out.append((start, "".join(buf), True))
                buf = []
                quote = ""
                start = line
            else:
                buf.append(ch)
        elif ch in "\"'`":
            if buf:
                out.append((start, "".join(buf), False))
                buf = []
            quote = ch
            start = line
        else:
            buf.append(ch)
        if ch == "\n":
            line += 1
    if buf:
        out.append((start, "".join(buf), quote != ""))
    return out


def _is_path_token(token: str, names: frozenset[str], policy_dir: str) -> str | None:
    """The policy name this token builds a path to, or None.

    A token is a JOIN when, after an optional `${VAR:-` wrapper and an optional
    directory prefix, it IS `<policy_dir>/<name>` and nothing else. Everything that survives to here has already been proven free of whitespace, which is what separates a path from a sentence that happens to contain one.
    """
    t = token.strip().strip(",;)]}")
    t = re.sub(r"^\$\{[A-Za-z_][A-Za-z0-9_]*(?::?[-=])", "", t)
    t = t.rstrip("}")
    for name in names:
        tail = "%s/%s" % (policy_dir, name)
        if t == tail or t.endswith("/" + tail):
            return name
    return None


def text_join_sites(
    rel: str, source: str, names: frozenset[str], policy_dir: str
) -> list[tuple[int, str]]:
    """(line, name) for every literal policy-path join in TypeScript, JS or shell.

    THE DISCRIMINATOR IS WHITESPACE INSIDE THE QUOTES, and it is the whole predicate. A quoted string whose content is a bare path is a JOIN; a quoted string containing a sentence is a MESSAGE printed at a human, and there are nineteen of those in `audit.sh` alone plus two multi-line help texts under `scripts/`. Flagging them would train the next reader to route human-readable text
    through a path helper, which helps nobody and buries the real joins in noise. Outside quotes the same rule applies word by word, which is what catches `[[ -f .ci/policy/.x ]]`.

    Comments are stripped first: prose is directions 5 and 6's subject, judged by a different predicate that knows about tense.
    """
    stripped = "\n".join(_strip_comment(rel, line) for line in source.splitlines())
    if policy_dir not in stripped:
        return []
    out = []
    for start, content, quoted in _quoted_spans(stripped):
        if quoted:
            body = content.strip()
            if not body or re.search(r"\s", body):
                continue
            name = _is_path_token(body, names, policy_dir)
            if name:
                out.append((start, name))
            continue
        for offset, line in enumerate(content.split("\n")):
            for word in line.split():
                name = _is_path_token(word, names, policy_dir)
                if name:
                    out.append((start + offset, name))
    return out


# ---- directions 5 and 6: the prose ------------------------------------------


def _strip_marker(text: str) -> str:
    """One comment line with its `#`, `//` or ` * ` removed.

    THE MARKER IS PUNCTUATION, NOT PROSE, and leaving it in breaks the one predicate that reads across a line break: a block joined verbatim reads "still # read", so the past-tense lookbehind for "still read" misses, and the gate reports a sentence that is plainly in the past tense. Found by this gate against its own docstring.
    """
    return re.sub(r"^\s*(?:#+|//+|/\*+|\*+)\s?", "", text)


def comment_blocks(rel: str, source: str) -> list[tuple[int, str, int]]:
    """(first line, text, line count) for every CONTIGUOUS run of comment lines.

    BLOCKS, NOT LINES, and this is the correction that a real run forced. The first version of this gate yielded one line at a time, so the tense marker in `.claude/hooks/pre-bash/block-pathspecless-git-commit.sh` -- "policy-paths.ts still read" -- sat on the line ABOVE the value it qualifies, out of the lookbehind window, and the gate reported the repository's own historical
    record as a stale claim. The unit-level control passed throughout, because it handed the predicate both lines as one string, which is the shape a per-line extractor never produces. Prose is a paragraph; judging it a line at a time asks a question no author was answering.

    Python is TOKENIZED rather than pattern-matched, because a `#` inside a string is not a comment and this gate must not rule on one. Docstrings are comments here: they are the prose that carries most of this repository's reasoning, and the stale claim this rule exists for lived in one.
    """
    out: list[tuple[int, str, int]] = []
    if rel.endswith(".py"):
        run: list[tuple[int, str]] = []
        try:
            for tok in tokenize.generate_tokens(io.StringIO(source).readline):
                if tok.type == tokenize.COMMENT:
                    if run and tok.start[0] != run[-1][0] + 1:
                        out.append(
                            (run[0][0], "\n".join(_strip_marker(t) for _, t in run), len(run))
                        )
                        run = []
                    run.append((tok.start[0], tok.string))
        except (tokenize.TokenError, IndentationError, SyntaxError):
            pass
        if run:
            out.append((run[0][0], "\n".join(_strip_marker(t) for _, t in run), len(run)))
        try:
            tree = ast.parse(source)
        except SyntaxError:
            return out
        for node in ast.walk(tree):
            body = getattr(node, "body", None)
            if (
                isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
                and body
                and isinstance(body[0], ast.Expr)
                and isinstance(body[0].value, ast.Constant)
                and isinstance(body[0].value.value, str)
            ):
                text = body[0].value.value
                out.append((body[0].value.lineno, text, len(text.splitlines()) or 1))
        return out

    run_lines: list[tuple[int, str]] = []
    for i, line in enumerate(source.splitlines(), 1):
        stripped = line.strip()
        text = None
        if stripped.startswith(("//", "/*", "*", "#")):
            text = stripped
        elif "//" in line and not rel.endswith(SHELL_EXTS):
            text = line[line.index("//") :]
        elif rel.endswith(SHELL_EXTS) and " #" in line:
            code = _strip_comment(rel, line)
            if len(code) < len(line):
                text = line[len(code) :]
        if text is None:
            if run_lines:
                out.append(
                    (
                        run_lines[0][0],
                        "\n".join(_strip_marker(t) for _, t in run_lines),
                        len(run_lines),
                    )
                )
                run_lines = []
            continue
        if run_lines and i != run_lines[-1][0] + 1:
            out.append(
                (run_lines[0][0], "\n".join(_strip_marker(t) for _, t in run_lines), len(run_lines))
            )
            run_lines = []
        run_lines.append((i, text))
    if run_lines:
        out.append(
            (run_lines[0][0], "\n".join(_strip_marker(t) for _, t in run_lines), len(run_lines))
        )
    return out


def policy_dir_claims(text: str) -> list[tuple[int, str]]:
    """(line offset within the block, value) for every PRESENT-TENSE POLICY_DIR claim."""
    lowered = text.lower()
    out = []
    for m in _POLICY_DIR_CLAIM.finditer(text):
        # WHITESPACE-NORMALISED, because prose WRAPS. This gate's own docstring quotes the hook sentence as "still\nread", and an unnormalised window does not contain "still read" at all -- so the gate reported itself for explaining the exemption it was implementing.
        prefix = re.sub(r"\s+", " ", lowered[max(0, m.start() - 160) : m.start()])
        if any(marker in prefix for marker in _PAST_MARKERS):
            continue
        out.append(
            (text[: m.start()].count("\n"), m.group(1) if m.group(1) is not None else m.group(2))
        )
    return out


def root_path_citations(text: str, names: frozenset[str], policy_dir: str) -> list[tuple[int, str]]:
    """(line offset within the block, citation) for every policy file cited by a wrong path."""
    alt = "|".join(re.escape(n) for n in sorted(names))
    leaf = os.path.basename(policy_dir)
    out = []
    for m in re.finditer(r"([A-Za-z0-9_.${}<>~-]*)/(" + alt + r")\b", text):
        parent = m.group(1)
        if parent.endswith(leaf):
            continue
        out.append((text[: m.start()].count("\n"), "%s/%s" % (parent, m.group(2))))
    return out


def prose_findings(
    rel: str, source: str, names: frozenset[str], policy_dir: str
) -> tuple[list[str], int]:
    """(findings, comment lines swept) for one file. THE COMPOSITION THE CONTROLS DRIVE.

    Controls call this rather than the three helpers above, deliberately. The false positive that shipped in the first draft was invisible to helper-level controls: every helper was correct, and the DEFECT WAS IN THE COMPOSITION -- a per-line extractor feeding a predicate that needs a paragraph. A control that never runs the composition cannot see that class at all.
    """
    findings: list[str] = []
    swept = 0
    for start, text, count in comment_blocks(rel, source):
        swept += count
        for offset, claimed in policy_dir_claims(text):
            if claimed != policy_dir:
                findings.append(
                    "%s:%d asserts POLICY_DIR is %r; it is %r (%s). Say what is true today, "
                    "or write the sentence in the past tense if it is history."
                    % (rel, start + offset, claimed, policy_dir, TS_SEAM)
                )
        for offset, cited in root_path_citations(text, names, policy_dir):
            findings.append(
                "%s:%d cites a policy file as %s; it lives in %s/ and has since b80552370"
                % (rel, start + offset, cited, policy_dir)
            )
    return findings, swept


def refusal_findings(
    root: pathlib.Path,
    policy_dir: str,
    seam_names: frozenset[str],
) -> tuple[list[str], int]:
    """The three clauses `REFUSED_RECORD` fails on, re-derived. Returns (findings, blockers).

    The count comes back so the success line can print it. A zero that is never printed is indistinguishable from a check that did not run.
    """
    findings: list[str] = []
    target = root / REFUSED_FILE
    name = REFUSED_FILE.rsplit("/", 1)[-1]

    if not target.is_file():
        findings.append(
            "%s is GONE, so %s refuses a file that no longer exists. Delete the section "
            "or point it at whatever replaced the map; do not leave the assertion passing "
            "over nothing." % (REFUSED_FILE, REFUSED_RECORD)
        )
        return findings, -1

    # TWO WAYS THE "not here" CLAUSE CAN STOP HOLDING, and both are reachable, which is why neither is written as a comparison against a literal. A COPY landing in the directory is the likely one (somebody tidies, the original stays where its readers expect it, and two files disagree). POLICY_DIR moving on top of the config directory is the other, and it is what makes `startswith`
    # here a real test rather than a restatement of the constant above.
    if (root / policy_dir / name).is_file() or REFUSED_FILE.startswith(policy_dir + "/"):
        findings.append(
            "%s is now reachable under %s/, which is the move %s refuses. Re-run the "
            "section 1 predicate before keeping it there."
            % (REFUSED_FILE, policy_dir, REFUSED_RECORD)
        )
    if name in seam_names:
        findings.append(
            "%s is in POLICY_FILES, and %s says it does not belong there. One of the two "
            "is wrong and it is not the gate's job to pick." % (name, REFUSED_RECORD)
        )

    try:
        text = target.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError) as exc:
        findings.append(
            "%s cannot be read (%s), so the BLOCKER clause of %s was NOT checked. Unknown "
            "is a failure here, not a pass." % (REFUSED_FILE, exc, REFUSED_RECORD)
        )
        return findings, -1

    blockers = sum(1 for line in text.split("\n") if "BLOCKER:" in line)
    if blockers:
        findings.append(
            "%s now carries %d BLOCKER: line(s). That is clause 2 of the section 1 "
            "predicate no longer failing, so the refusal in %s is no longer complete. "
            "Re-run the predicate and rewrite the section; do not delete this check."
            % (REFUSED_FILE, blockers, REFUSED_RECORD)
        )
    return findings, blockers


# ---- the scan ---------------------------------------------------------------


class Report:
    """Everything one run measured. Counts as well as findings, so the shape prints."""

    def __init__(self) -> None:
        self.inventory: list[str] = []
        self.joins: list[str] = []
        self.prose: list[str] = []
        self.refusal: list[str] = []
        self.refused_blockers = 0
        self.named: list[str] = []
        self.dir_count = 0
        self.ts_count = 0
        self.py_count = 0
        self.files = 0
        self.candidates = 0
        self.comment_lines = 0
        self.exempt_test_sites = 0
        self.shell_sites: list[str] = []
        self.enumerator = ""
        self.policy_dir = ""

    @property
    def findings(self) -> list[str]:
        return self.inventory + self.joins + self.prose + self.refusal

    def named_policy_files(self) -> set[str]:
        """Every policy FILE NAME the inventory directions named. The control reads this."""
        out = set()
        for f in self.inventory:
            for tok in re.findall(r"\.[a-z0-9-]+(?:-allowlist|-blocklist|-exempt)", f):
                out.add(tok)
        return out


def scan(root: pathlib.Path) -> Report:
    """Every direction, against one root. Raises RefusalError when a corpus is empty."""
    r = Report()
    r.policy_dir = ts_policy_dir(root)
    ts = ts_names(root)
    py = py_names(root)
    disk = directory_names(root, r.policy_dir)
    r.ts_count, r.py_count, r.dir_count = len(ts), len(py), len(disk)

    if not ts:
        raise RefusalError("POLICY_FILES in %s parsed to ZERO names" % TS_SEAM)
    if not py:
        raise RefusalError("POLICY_FILES in %s parsed to ZERO names" % PY_SEAM)
    if not disk:
        raise RefusalError("%s holds no policy file at all" % r.policy_dir)

    ts_set, py_set, disk_set = set(ts), set(py), set(disk)
    for name in sorted(disk_set - ts_set):
        r.inventory.append(
            "%s/%s is on disk but absent from POLICY_FILES in %s -- a live suppression "
            "no list accounts for" % (r.policy_dir, name, TS_SEAM)
        )
    for name in sorted(ts_set - disk_set):
        r.inventory.append(
            "%s is in POLICY_FILES (%s) with no file in %s -- every consumer reads a "
            "missing policy file as ZERO entries, which is indistinguishable from "
            '"nothing is suppressed"' % (name, TS_SEAM, r.policy_dir)
        )
    for name in sorted(py_set - ts_set):
        r.inventory.append(
            "%s is in POLICY_FILES (%s) but not in %s -- the two seams disagree, which "
            "is two live locations" % (name, PY_SEAM, TS_SEAM)
        )
    for name in sorted(ts_set - py_set):
        r.inventory.append(
            "%s is in POLICY_FILES (%s) but not in %s -- the two seams disagree, which "
            "is two live locations" % (name, TS_SEAM, PY_SEAM)
        )
    py_dir = py_policy_dir(root)
    if py_dir != r.policy_dir:
        r.inventory.append(
            "POLICY_DIR is %r in %s and %r in %s -- one location at a time, or the move "
            "half-lands" % (r.policy_dir, TS_SEAM, py_dir, PY_SEAM)
        )

    r.refusal, r.refused_blockers = refusal_findings(root, r.policy_dir, frozenset(ts_set | py_set))

    names = frozenset(ts_set | py_set | disk_set)
    files, r.enumerator = source_files(root)
    r.files = len(files)
    if not files:
        raise RefusalError(
            "the corpus is EMPTY: no %s file found under %s" % (" / ".join(SCANNED_EXTS), root)
        )

    oracle = r.policy_dir
    for rel in files:
        try:
            source = (root / rel).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        if not mentions_policy(source, names, oracle):
            continue
        r.candidates += 1
        if rel.endswith(SHELL_EXTS):
            sites = text_join_sites(rel, source, names, oracle)
            if sites and not _is_test_path(rel):
                r.shell_sites.extend("%s:%d (%s)" % (rel, ln, nm) for ln, nm in sites)
        elif rel not in SEAMS:
            if rel.endswith(".py"):
                try:
                    sites = python_join_sites(source, names, oracle)
                except SyntaxError:
                    sites = []
            else:
                sites = text_join_sites(rel, source, names, oracle)
            if _is_test_path(rel):
                r.exempt_test_sites += len(sites)
            elif rel in NAMED_EXEMPT:
                r.named.extend("%s:%d joins %s" % (rel, ln, nm) for ln, nm in sites)
            else:
                r.joins.extend(
                    "%s:%d builds the path to %s by hand; call policy_path()/policyPath() "
                    "so the directory is written down once" % (rel, ln, nm)
                    for ln, nm in sites
                )

        prose, swept = prose_findings(rel, source, names, oracle)
        r.prose.extend(prose)
        r.comment_lines += swept

    # NO `candidates == 0` REFUSAL, and the absence is deliberate. Both seams are
    # in the corpus by construction (scan() has already read them) and both mention policy names, so the arm could never fire -- an unreachable refusal is a line that looks like a guarantee and is not one. The count is PRINTED instead, and the comment-line refusal below is the reachable arm: a corpus the pre-filter emptied has no comments in it either.
    if r.comment_lines == 0:
        raise RefusalError(
            "ZERO comment lines swept across %d file(s); the prose rules asserted nothing" % r.files
        )
    return r


# ---- controls ---------------------------------------------------------------
#
# EVERY PREDICATE IS DRIVEN IN BOTH DIRECTIONS, and the fixtures below are real lines from this tree rather than invented ones, because the two defects this gate's own first run produced were both cases where an invented fixture had a shape the tree does not have:
#
# * `_HISTORY_BLOCK` is `.claude/hooks/pre-bash/block-pathspecless-git-commit.sh:26-27`. The first draft handed the predicate both lines glued into one string, the extractor handed it one line at a time, and the gate reported the repository's own record of the 2026-09-06 half-landed move as a stale claim. The control passed the whole time. * `_SH_TRAILING_SENTENCE` is
# `audit.sh:256`, and `_SH_WRAPPED_JOIN` is `check-plan-housekeeping.sh:87`. The first tokenizer anchored on end of line, so it called the first a join (it is a message) and missed the second (it is a join). Both errors are invisible to a fixture that ends the line right after the path.

_PY_WHOLE_JOIN = """
X = ".ci/policy/.audit-allowlist"
"""
_PY_SEGMENT_JOIN = """
X = ROOT / ".ci" / "policy" / ".audit-allowlist"
"""
_PY_THROUGH_SEAM = """
X = policy_path(".audit-allowlist", ROOT)
"""
_PY_MESSAGE = """
print("held in .ci/policy/.audit-allowlist, with a BLOCKER reason")
"""
_PY_DOCSTRING = '''
"""Reads .ci/policy/.audit-allowlist, through the seam."""
X = 1
'''

_SH_ASSIGNMENT_JOIN = 'BLOCKLIST_FILE="$REPO_ROOT/.ci/policy/.audit-allowlist"\n'
_SH_WRAPPED_JOIN = 'ALLOWLIST="${PLAN_HK_ALLOWLIST:-$ROOT_DIR/.ci/policy/.audit-allowlist}"\n'
# `check-profiler-coverage.sh:91`: a `${VAR:-<relative path>}` default with NO
# directory prefix. This is the shape the `${VAR:-` strip in `_is_path_token`
# exists for; `_SH_WRAPPED_JOIN` above cannot prove it, because its `$ROOT_DIR/` makes the tail match on its own.
_SH_BARE_DEFAULT_JOIN = 'ALLOWLIST="${PROFILER_COVERAGE_ALLOWLIST:-.ci/policy/.audit-allowlist}"\n'
_SH_ARGUMENT_JOIN = 'parse_blockered_list ".ci/policy/.audit-allowlist" ALLOWED_DEV BLOCKER_DEV\n'
_SH_TEST_OPERAND_JOIN = '    [[ -n "$pkg" && -f .ci/policy/.audit-allowlist ]] || return 1\n'
_SH_TRAILING_SENTENCE = 'DEFER_REASON="fix requires ${p}, held in .ci/policy/.audit-allowlist"\n'
_SH_PARENTHESISED_SENTENCE = (
    'ci_warn "Allowed production vulnerabilities: $n (see .ci/policy/.audit-allowlist)"\n'
)
_SH_COMMENT = "# the entries live in .ci/policy/.audit-allowlist, one per line\n"
# A SENTENCE ENDING IN A SLASH-PREFIXED PATH. The pair below differs from `_SH_ASSIGNMENT_JOIN` only by the words around an identical tail, which is the one shape where dropping the "no whitespace inside the quotes" requirement still reds: `t.endswith("/" + tail)` matches the last word of the sentence. Written because a mutant that deleted that requirement survived every other
# control on this tree.
_SH_SENTENCE_ENDING_IN_PATH = (
    'ci_warn "add a BLOCKER above the entry in $REPO_ROOT/.ci/policy/.audit-allowlist"\n'
)

_TS_WHOLE_JOIN = "const F = '.ci/policy/.audit-allowlist';\n"
_TS_SENTENCE = "  `remove line ${l} from .ci/policy/.audit-allowlist, then: npm run x`\n"
_TS_COMMENT = "// Actions can be blocklisted in .ci/policy/.audit-allowlist to prevent\n"
# `scripts/gates/check-actions.ts:378-384`, trimmed: help text inside a template literal that OPENS on an earlier line. A per-line tokenizer sees no quote character on the offending line and reads the prose as bare code.
_TS_MULTILINE_HELP = """const usage = `
DESCRIPTION
  Checks for outdated GitHub Actions in workflow files and fails if any
  are found. Actions can be blocklisted in .ci/policy/.audit-allowlist to
  prevent upgrade enforcement (e.g., actions requiring workflow changes).
`;
"""
_TS_MULTILINE_JOIN = """const f = `.ci/policy/.audit-allowlist`;
"""
# A JSDOC CONTINUATION LINE, which carries no `//` of its own. This is the shape that needs the ` * ` arm of `_strip_comment`: without it the line reads as bare code and its prose becomes a join.
_TS_JSDOC = """/**
 * Eleven of the fifteen are read here, .ci/policy/.audit-allowlist among them.
 */
"""

# `.ci/scripts/test/gates/test-policy-path.sh:21`, verbatim: the CURRENT value, in backticks, in a comment that must stay clean.
_CURRENT_CLAIM = (
    "# THE MOVE LANDED 2026-09-06 at b80552370: POLICY_DIR is `.ci/policy` and all\n"
    "# fifteen are there. `.ci-trigger` stayed at root with its own recorded reason.\n"
)
# `scripts/gates/check-suppression-liveness.ts:61-63`, verbatim: the finding this box exists to absorb.
_STALE_BLOCK = (
    " * Today POLICY_DIR is '' and this is a provable no-op: the paths it returns are\n"
    " * byte-identical to the joins it replaced, which is what keeps the seam\n"
    " * verifiable before the move rather than only after it.\n"
)
# `.claude/hooks/pre-bash/block-pathspecless-git-commit.sh:26-27`, verbatim.
_HISTORY_BLOCK = (
    "#     files at their new paths while scripts/lib/policy-paths.ts still read\n"
    "#     `const POLICY_DIR = '';` -- the exact half-landed state that seam exists\n"
)
_ROOT_CITATION = "# reads $ROOT_DIR/.audit-allowlist on every run\n"
# THE SAME PAST-TENSE EXEMPTION WITH THE MARKER WRAPPED across a line break, which is what prose does. This gate's own docstring is written this way, and an unnormalised lookbehind reported it.
_WRAPPED_HISTORY = (
    "# the sentence in the hook says the seam still\n"
    "# read `const POLICY_DIR = '';` while HEAD held the new paths\n"
)
_BARE_NAME = "# reads .audit-allowlist, resolved through policyPath()\n"
_POLICY_CITATION = "# reads .ci/policy/.audit-allowlist, resolved through policyPath()\n"
_STRING_NOT_COMMENT = "X = \"# POLICY_DIR is ''\"\n"

_NAMES = frozenset({".audit-allowlist", ".deps-upgrade-blocklist", ".ci-parity-exempt"})


def _fixture_tree(tmp: pathlib.Path, ts_list: list[str], py_list: list[str], disk: list[str]):
    """A minimal tree with both seams and a policy directory. Returns the root."""
    (tmp / "scripts" / "lib").mkdir(parents=True)
    (tmp / ".ci" / "rediacc_ci").mkdir(parents=True)
    (tmp / "scripts" / "lib" / "policy-paths.ts").write_text(
        "const POLICY_DIR = '.ci/policy';\nconst POLICY_FILES = Object.freeze([\n"
        + "".join("  '%s',\n" % n for n in ts_list)
        + "] as const);\n",
        encoding="utf-8",
    )
    (tmp / ".ci" / "rediacc_ci" / "policy_paths.py").write_text(
        'POLICY_DIR = ".ci/policy"\nPOLICY_FILES = (\n'
        + "".join('    "%s",\n' % n for n in py_list)
        + ")\n# a comment so the prose corpus is never empty\n",
        encoding="utf-8",
    )
    for name in disk:
        # THROUGH THE SEAM, in the gate's own fixtures: if `policy_path` and this gate ever disagree about where a policy file goes, every fixture below is built in the wrong place and the controls say so.
        p = policy_path(name, tmp)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text("# BLOCKER: fixture\n", encoding="utf-8")
    # Direction 7's subject. Present and clean in every fixture, so a fixture-based control that DOES flip a clause is measuring the flip and not the fixture.
    refused = tmp / REFUSED_FILE
    refused.parent.mkdir(parents=True, exist_ok=True)
    refused.write_text(
        '{"refreshed_at": "2026-01-01T00:00:00Z", "secrets": {}}\n', encoding="utf-8"
    )
    return tmp


def _scan_or_refusal(root: pathlib.Path) -> Report | str:
    try:
        return scan(root)
    except RefusalError as exc:
        return "REFUSED: %s" % exc


def _prose(rel: str, source: str) -> list[str]:
    return prose_findings(rel, source, _NAMES, ".ci/policy")[0]


def selftest(verbose: bool = False) -> int:
    c = Controls("check_policy_inventory", floor=65, verbose=verbose)

    # -- direction 4, Python.
    c.check(
        "a whole-string .ci/policy join is a finding",
        python_join_sites(_PY_WHOLE_JOIN, _NAMES, ".ci/policy"),
        [(2, ".audit-allowlist")],
    )
    c.check(
        "a segmented ROOT / '.ci' / 'policy' / name join is a finding",
        python_join_sites(_PY_SEGMENT_JOIN, _NAMES, ".ci/policy"),
        [(2, ".audit-allowlist")],
    )
    c.check(
        "ANTI-SILENCER: a name handed TO the seam is not a finding",
        python_join_sites(_PY_THROUGH_SEAM, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: the same path inside a sentence is a message, not a join",
        python_join_sites(_PY_MESSAGE, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a docstring is prose",
        python_join_sites(_PY_DOCSTRING, _NAMES, ".ci/policy"),
        [],
    )

    # -- direction 4, shell. The bash twins have no seam, so this arm only DISCLOSES -- but a disclosure built on a broken predicate is a number nobody can read, so it is asserted in both directions like the rest.
    c.check(
        "a shell assignment join is a finding",
        text_join_sites("x.sh", _SH_ASSIGNMENT_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "a ${VAR:-$ROOT/...} wrapped join is a finding (check-plan-housekeeping.sh:87)",
        text_join_sites("x.sh", _SH_WRAPPED_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "a ${VAR:-<relative>} default with no prefix is a finding (check-profiler-coverage.sh:91)",
        text_join_sites("x.sh", _SH_BARE_DEFAULT_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "a quoted ARGUMENT with more arguments after it is a finding (audit.sh:337)",
        text_join_sites("x.sh", _SH_ARGUMENT_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "an UNQUOTED operand inside [[ ... ]] is a finding (audit.sh:220)",
        text_join_sites("x.sh", _SH_TEST_OPERAND_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "ANTI-SILENCER: a sentence ENDING in the path is a message (audit.sh:256)",
        text_join_sites("x.sh", _SH_TRAILING_SENTENCE, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a parenthesised '(see <path>)' is a message (audit.sh:457)",
        text_join_sites("x.sh", _SH_PARENTHESISED_SENTENCE, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a shell COMMENT naming the path is prose, not a join",
        text_join_sites("x.sh", _SH_COMMENT, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a sentence whose LAST WORD is $ROOT/<path> is still a message",
        text_join_sites("x.sh", _SH_SENTENCE_ENDING_IN_PATH, _NAMES, ".ci/policy"),
        [],
    )

    # -- direction 4, TypeScript.
    c.check(
        "a TypeScript whole-string join is a finding",
        text_join_sites("x.ts", _TS_WHOLE_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )
    c.check(
        "ANTI-SILENCER: a template-literal sentence is not a join",
        text_join_sites("x.ts", _TS_SENTENCE, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a `//` comment naming the path is not a join",
        text_join_sites("x.ts", _TS_COMMENT, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: a JSDOC continuation line is prose, not a join",
        text_join_sites("x.ts", _TS_JSDOC, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "ANTI-SILENCER: help text inside a MULTI-LINE template literal is prose "
        "(scripts/gates/check-actions.ts:382)",
        text_join_sites("x.ts", _TS_MULTILINE_HELP, _NAMES, ".ci/policy"),
        [],
    )
    c.check(
        "MIRROR: a template literal holding ONLY the path is still a join",
        text_join_sites("x.ts", _TS_MULTILINE_JOIN, _NAMES, ".ci/policy"),
        [(1, ".audit-allowlist")],
    )

    # -- directions 5 and 6, driven through prose_findings() -- the COMPOSITION, not the helpers. The helpers were all correct when the composition was
    #    wrong; see this section's header.
    # ONE call, and no indexing into a list a mutation can empty. A control that raises IndexError takes every control after it down with it, which turns one visible regression into a suite that stopped running.
    stale = _prose("x.ts", _STALE_BLOCK)
    c.check("the stale claim in check-suppression-liveness.ts is caught", len(stale), 1)
    c.truthy(
        "...and it names both the claimed value and the real one",
        stale and "asserts POLICY_DIR is ''" in stale[0] and "'.ci/policy'" in stale[0],
    )
    c.check(
        "ANTI-SILENCER: the CURRENT value in backticks is clean (test-policy-path.sh:21)",
        _prose("x.sh", _CURRENT_CLAIM),
        [],
    )
    c.check(
        "ANTI-SILENCER: the PAST-TENSE history block, whose tense marker is on the "
        "PREVIOUS line, must not fire (block-pathspecless-git-commit.sh:26-27)",
        _prose("x.sh", _HISTORY_BLOCK),
        [],
    )
    c.check(
        "MIRROR: the same two lines with the tense marker removed DO fire",
        len(_prose("x.sh", plant(_HISTORY_BLOCK, "still read", "reads"))),
        1,
    )
    c.check(
        "ANTI-SILENCER: a past-tense marker WRAPPED across a line break still exempts",
        _prose("x.py", _WRAPPED_HISTORY),
        [],
    )
    c.check("a root-path citation is caught", len(_prose("x.py", _ROOT_CITATION)), 1)
    c.check(
        "ANTI-SILENCER: a BARE name is the documented way to cite one",
        _prose("x.py", _BARE_NAME),
        [],
    )
    c.check(
        "ANTI-SILENCER: the correct .ci/policy/ path is clean",
        _prose("x.py", _POLICY_CITATION),
        [],
    )
    c.check(
        "ANTI-SILENCER: a `#` inside a Python STRING is not a comment",
        prose_findings("x.py", _STRING_NOT_COMMENT, _NAMES, ".ci/policy"),
        ([], 0),
    )
    c.check(
        "MIRROR: the same text as a real comment IS swept",
        prose_findings("x.py", "# POLICY_DIR is ''\n", _NAMES, ".ci/policy")[1],
        1,
    )
    c.truthy(
        "a Python DOCSTRING is swept as prose",
        prose_findings("x.py", '"""POLICY_DIR is \'\' here."""\n', _NAMES, ".ci/policy")[0],
    )

    # -- the four directions and the five refusals, against real trees.
    with tempfile.TemporaryDirectory() as td:
        base = [".audit-allowlist", ".ci-parity-exempt"]
        drifted = [*base, ".deps-upgrade-blocklist"]

        # THE HISTORICAL SHAPE, reconstructed: one more file on disk than the TypeScript list knows about, reached by a hardcoded join. This is 19c45c78e in miniature; the real tree was driven by hand at authoring time, see the module docstring.
        drift = pathlib.Path(td) / "drift"
        drift.mkdir()
        _fixture_tree(drift, base, drifted, drifted)
        rep = _scan_or_refusal(drift)
        c.check(
            "the 2026-09-07 shape reds naming EXACTLY the one drifted file",
            rep.named_policy_files() if isinstance(rep, Report) else rep,
            {".deps-upgrade-blocklist"},
        )
        # THE TWO DIRECTIONS ARE ASSERTED SEPARATELY, not counted. Deleting either one leaves a length-based control passing at the wrong number only by luck, and passing for the wrong reason is the class this whole gate is about; each arm is named by the text only it produces.
        inv = rep.inventory if isinstance(rep, Report) else [str(rep)]
        c.check(
            "...the DISK-vs-TypeScript arm fires",
            [f for f in inv if "is on disk but absent" in f] != [],
            True,
        )
        c.check(
            "...the Python-vs-TypeScript arm fires, and is a different arm",
            [f for f in inv if "the two seams disagree" in f] != [],
            True,
        )
        c.check("...and nothing else does", len(inv), 2)

        clean = pathlib.Path(td) / "clean"
        clean.mkdir()
        _fixture_tree(clean, base, base, base)
        (clean / ".ci" / "policy" / "README.md").write_text("# the predicate\n", "utf-8")
        rep = _scan_or_refusal(clean)
        c.check(
            "ANTI-SILENCER: README.md in the policy directory is exempt by name",
            rep.dir_count if isinstance(rep, Report) else rep,
            2,
        )
        c.check(
            "ANTI-SILENCER: an agreeing tree has no inventory finding",
            rep.inventory if isinstance(rep, Report) else rep,
            [],
        )
        c.check("...and no join finding", rep.joins if isinstance(rep, Report) else rep, [])
        c.check("...and no prose finding", rep.prose if isinstance(rep, Report) else rep, [])
        c.check(
            "...and it counted the tree it saw rather than reporting on nothing",
            (rep.dir_count, rep.ts_count, rep.py_count) if isinstance(rep, Report) else rep,
            (2, 2, 2),
        )

        missing = pathlib.Path(td) / "missing"
        missing.mkdir()
        _fixture_tree(missing, base, base, base[:1])
        rep = _scan_or_refusal(missing)
        c.check(
            "a name with no file on disk is a finding, not silence",
            len(rep.inventory) if isinstance(rep, Report) else rep,
            1,
        )
        c.truthy(
            "...and it says a missing file reads as zero entries",
            isinstance(rep, Report) and any("ZERO entries" in f for f in rep.inventory),
        )

        # -- direction 7, all four arms plus the anti-silencer. Fixture-based and end to end, because the unit these arms compose over is a whole tree: one of them reads the seams, one reads the policy directory and two read the refused file itself.
        keep = pathlib.Path(td) / "refusal-holds"
        keep.mkdir()
        _fixture_tree(keep, base, base, base)
        rep = _scan_or_refusal(keep)
        c.check(
            "ANTI-SILENCER: a present, BLOCKER-free, elsewhere-living map is NOT a finding",
            (rep.refusal, rep.refused_blockers) if isinstance(rep, Report) else rep,
            ([], 0),
        )

        gone = pathlib.Path(td) / "refusal-gone"
        gone.mkdir()
        _fixture_tree(gone, base, base, base)
        (gone / REFUSED_FILE).unlink()
        rep = _scan_or_refusal(gone)
        c.truthy(
            "a REFUSED file that no longer exists is a finding, never a vacuous pass",
            isinstance(rep, Report) and any("is GONE" in f for f in rep.refusal),
        )

        reasoned = pathlib.Path(td) / "refusal-reasoned"
        reasoned.mkdir()
        _fixture_tree(reasoned, base, base, base)
        (reasoned / REFUSED_FILE).write_text(
            '{\n  "_comment": "BLOCKER: somebody wrote a reason",\n  "secrets": {}\n}\n',
            encoding="utf-8",
        )
        rep = _scan_or_refusal(reasoned)
        c.truthy(
            "a BLOCKER: line appearing in the refused map reopens the decision",
            isinstance(rep, Report)
            and any("no longer failing" in f for f in rep.refusal)
            and rep.refused_blockers == 1,
        )

        copied = pathlib.Path(td) / "refusal-copied"
        copied.mkdir()
        _fixture_tree(copied, base, base, base)
        (copied / ".ci" / "policy" / REFUSED_FILE.rsplit("/", 1)[-1]).write_text(
            "{}\n", encoding="utf-8"
        )
        rep = _scan_or_refusal(copied)
        c.truthy(
            "a COPY of the refused map landing in the policy directory is a finding",
            isinstance(rep, Report) and any("reachable under" in f for f in rep.refusal),
        )

        seamed = pathlib.Path(td) / "refusal-seamed"
        seamed.mkdir()
        # The name goes in BOTH seams and NOT on disk: `policy_path` refuses to build a path for a name it does not know, so the fixture writer cannot place it, and placing it is not what this arm is about. The inventory direction also reds here, which is correct and is why this control reads `rep.refusal`.
        _fixture_tree(seamed, [*base, "bws-secret-map.json"], [*base, "bws-secret-map.json"], base)
        rep = _scan_or_refusal(seamed)
        c.truthy(
            "the refused name added to POLICY_FILES is a finding",
            isinstance(rep, Report)
            and any("says it does not belong there" in f for f in rep.refusal),
        )

        # THE REFUSALS, each reached on its own so that deleting any one arm fails a control no other arm answers.
        empty_dir = pathlib.Path(td) / "emptydir"
        empty_dir.mkdir()
        _fixture_tree(empty_dir, base, base, [])
        (empty_dir / ".ci" / "policy").mkdir(parents=True, exist_ok=True)
        c.check(
            "an EMPTY policy directory is refused",
            _scan_or_refusal(empty_dir),
            "REFUSED: .ci/policy holds no policy file at all",
        )

        no_ts = pathlib.Path(td) / "nots"
        no_ts.mkdir()
        _fixture_tree(no_ts, base, base, base)
        (no_ts / "scripts" / "lib" / "policy-paths.ts").write_text(
            "const POLICY_DIR = '.ci/policy';\nconst POLICY_FILES = Object.freeze([\n] as const);\n",
            encoding="utf-8",
        )
        c.check(
            "an EMPTY TypeScript list is refused, not folded into agreement",
            _scan_or_refusal(no_ts),
            "REFUSED: POLICY_FILES in %s parsed to ZERO names" % TS_SEAM,
        )

        no_py = pathlib.Path(td) / "nopy"
        no_py.mkdir()
        _fixture_tree(no_py, base, base, base)
        (no_py / ".ci" / "rediacc_ci" / "policy_paths.py").write_text(
            'POLICY_DIR = ".ci/policy"\nPOLICY_FILES = ()\n# comment\n', encoding="utf-8"
        )
        c.check(
            "an EMPTY Python list is refused SEPARATELY from the TypeScript one",
            _scan_or_refusal(no_py),
            "REFUSED: POLICY_FILES in %s parsed to ZERO names" % PY_SEAM,
        )

        no_seam = pathlib.Path(td) / "noseam"
        no_seam.mkdir()
        _fixture_tree(no_seam, base, base, base)
        (no_seam / ".ci" / "rediacc_ci" / "policy_paths.py").unlink()
        c.truthy(
            "a MISSING Python seam is refused rather than skipped",
            str(_scan_or_refusal(no_seam)).startswith("REFUSED: cannot read"),
        )

        no_dir = pathlib.Path(td) / "nodir"
        no_dir.mkdir()
        _fixture_tree(no_dir, base, base, base)
        for f in (no_dir / ".ci" / "policy").iterdir():
            f.unlink()
        (no_dir / ".ci" / "policy").rmdir()
        c.check(
            "a MISSING policy directory is refused",
            _scan_or_refusal(no_dir),
            "REFUSED: .ci/policy is not a directory in the tree under judgement",
        )

        two_dirs = pathlib.Path(td) / "twodirs"
        two_dirs.mkdir()
        _fixture_tree(two_dirs, base, base, base)
        (two_dirs / ".ci" / "rediacc_ci" / "policy_paths.py").write_text(
            'POLICY_DIR = ".ci/policies"\nPOLICY_FILES = (\n'
            + "".join('    "%s",\n' % n for n in base)
            + ")\n# comment\n",
            encoding="utf-8",
        )
        rep = _scan_or_refusal(two_dirs)
        c.truthy(
            "two seams with DIFFERENT POLICY_DIR values is a finding",
            isinstance(rep, Report) and any("one location at a time" in f for f in rep.inventory),
        )

        joiner = pathlib.Path(td) / "joiner"
        joiner.mkdir()
        _fixture_tree(joiner, base, base, base)
        (joiner / "gate.py").write_text(_PY_WHOLE_JOIN, encoding="utf-8")
        rep = _scan_or_refusal(joiner)
        c.check(
            "a hardcoded join in a NON-seam file is a finding",
            len(rep.joins) if isinstance(rep, Report) else rep,
            1,
        )
        c.check(
            "...and the corpus was enumerated by a walk, the fixture being no checkout",
            rep.enumerator if isinstance(rep, Report) else rep,
            "filesystem walk",
        )
        c.truthy(
            "...and the file corpus is counted, so an empty one could not pass",
            isinstance(rep, Report) and rep.files >= 3,
        )
        c.check(
            "the pre-filter admits a file that mentions a policy name",
            mentions_policy(_PY_WHOLE_JOIN, _NAMES, ".ci/policy"),
            True,
        )
        c.check(
            "...and one that mentions POLICY_DIR",
            mentions_policy("# POLICY_DIR moved\n", _NAMES, ".ci/policy"),
            True,
        )
        c.check(
            "MIRROR: and skips a file that mentions none of the three literals, "
            "which is exact rather than a heuristic",
            mentions_policy("x = 1\n# nothing to see\n", _NAMES, ".ci/policy"),
            False,
        )
        c.truthy(
            "...and the candidate count is non-zero on a real fixture, so the "
            "pre-filter cannot have emptied the corpus unnoticed",
            isinstance(rep, Report) and rep.candidates >= 1,
        )
        c.truthy(
            "...and the comment corpus is counted too",
            isinstance(rep, Report) and rep.comment_lines >= 1,
        )

        # THE GIT ENUMERATOR, which every fixture above bypasses. Without this the `git ls-files` branch is a live line no control reaches: a mutant that made it return nothing passed the whole suite, because the walk fallback quietly answered instead.
        tracked = pathlib.Path(td) / "tracked"
        tracked.mkdir()
        _fixture_tree(tracked, base, base, base)
        init = subprocess.run(
            ["git", "-C", str(tracked), "init", "-q"], capture_output=True, check=False
        )
        subprocess.run(["git", "-C", str(tracked), "add", "-A"], capture_output=True, check=False)
        (tracked / "untracked_gate.py").write_text(_PY_WHOLE_JOIN, encoding="utf-8")
        rep = _scan_or_refusal(tracked)
        c.check(
            "a checkout is enumerated with git ls-files, not walked",
            (rep.enumerator if isinstance(rep, Report) else rep) if init.returncode == 0 else "",
            "git ls-files (tracked + untracked)" if init.returncode == 0 else "",
        )
        c.check(
            "...and an UNTRACKED file IS judged, because in this tree work stays "
            "uncommitted for days and a tracked-only corpus would not see a new reader",
            (len(rep.joins) if isinstance(rep, Report) else rep) if init.returncode == 0 else 1,
            1,
        )

        # THE PROSE CORPUS REFUSAL, reached by removing the one comment `_fixture_tree` writes. Without a case here the arm is a claim nobody has watched fail.
        no_prose = pathlib.Path(td) / "noprose"
        no_prose.mkdir()
        _fixture_tree(no_prose, base, base, base)
        seam_py = no_prose / PY_SEAM
        # plant(), not str.replace: the first draft of this line targeted a comma the fixture does not write, replaced nothing, and the control passed against the CLEAN fixture. plant() raises on a needle it cannot find, which is the entire reason it exists.
        seam_py.write_text(
            plant(
                seam_py.read_text(encoding="utf-8"),
                "# a comment so the prose corpus is never empty\n",
                "",
            ),
            encoding="utf-8",
        )
        c.truthy(
            "a corpus with NO comment in it is refused, not swept vacuously",
            str(_scan_or_refusal(no_prose)).startswith("REFUSED: ZERO comment lines"),
        )

        seam_itself = pathlib.Path(td) / "seamitself"
        seam_itself.mkdir()
        _fixture_tree(seam_itself, base, base, base)
        seam = seam_itself / PY_SEAM
        seam.write_text(seam.read_text(encoding="utf-8") + _PY_WHOLE_JOIN, encoding="utf-8")
        rep = _scan_or_refusal(seam_itself)
        c.check(
            "ANTI-SILENCER: the SEAM itself may hold the join, that being its job",
            rep.joins if isinstance(rep, Report) else rep,
            [],
        )

        tested = pathlib.Path(td) / "tested"
        tested.mkdir()
        _fixture_tree(tested, base, base, base)
        (tested / "test_gate.py").write_text(_PY_WHOLE_JOIN, encoding="utf-8")
        rep = _scan_or_refusal(tested)
        c.check(
            "the same join in a TEST file is exempt BY RULE, and counted",
            (rep.joins, rep.exempt_test_sites) if isinstance(rep, Report) else rep,
            ([], 1),
        )

        lines = pathlib.Path(td) / "lines"
        lines.mkdir()
        _fixture_tree(lines, base, base, base)
        # TWO SEPARATE comment runs. If contiguous runs are not broken into blocks, the whole file reads as one block and every finding is reported at the FIRST comment's line, which sends the reader to the wrong place with total confidence.
        (lines / "gate.py").write_text(
            "# an unrelated note\nX = 1\nY = 2\n# Today POLICY_DIR is '' so nothing moved\nZ = 3\n",
            "utf-8",
        )
        rep = _scan_or_refusal(lines)
        c.truthy(
            "a finding names the line the claim is ON, not the top of the file",
            isinstance(rep, Report) and any("gate.py:4 asserts" in f for f in rep.prose),
        )

        prose = pathlib.Path(td) / "prose"
        prose.mkdir()
        _fixture_tree(prose, base, base, base)
        (prose / "gate.py").write_text(
            "# Today POLICY_DIR is '' so nothing moved\nX = 1\n", "utf-8"
        )
        rep = _scan_or_refusal(prose)
        c.check(
            "a stale POLICY_DIR claim in a comment is a finding, end to end",
            len(rep.prose) if isinstance(rep, Report) else rep,
            1,
        )

        cite = pathlib.Path(td) / "cite"
        cite.mkdir()
        _fixture_tree(cite, base, base, base)
        (cite / "gate.py").write_text("# reads $ROOT/.audit-allowlist every run\nX = 1\n", "utf-8")
        rep = _scan_or_refusal(cite)
        c.truthy(
            "a root-path citation in a comment is a finding, end to end",
            isinstance(rep, Report) and any("cites a policy file" in f for f in rep.prose),
        )

    return 0 if c.report() else 2


def main(argv: list[str]) -> int:
    verbose = "--verbose" in argv
    # CONTROLS FIRST, ALWAYS, not only under --selftest: a gate whose controls run only when asked is a gate whose controls do not run in CI.
    rc = selftest(verbose)
    if rc != 0:
        print(
            "✗ instrument control failed; every verdict below would be meaningless",
            file=sys.stderr,
        )
        return rc
    if "--selftest" in argv:
        return 0

    root = repo_root()
    try:
        r = scan(root)
    except RefusalError as exc:
        print(
            "%s✗%s the gate cannot see its subject: %s\n"
            "  A green here would mean nothing, so this is a failure and not a note."
            % (RED, NC, exc),
            file=sys.stderr,
        )
        return 1

    for line in r.named:
        print(
            "%s!%s EXEMPT BY NAME  %s\n      %s"
            % (YELLOW, NC, line, NAMED_EXEMPT[line.split(":")[0]])
        )
    if r.shell_sites:
        print(
            "%s!%s %d shell join(s) remain and are NOT gated: bash has no policy seam, and "
            "the bash twins are frozen until W7 P5 deletes them. Listed so the debt is "
            "visible rather than forgotten:" % (YELLOW, NC, len(r.shell_sites))
        )
        for line in r.shell_sites:
            print("      %s" % line)

    if r.findings:
        print(
            "%s✗%s %d policy-inventory finding(s):" % (RED, NC, len(r.findings)),
            file=sys.stderr,
        )
        for f in r.findings:
            print("    %s" % f, file=sys.stderr)
        print(
            "\n  Fix the value, do not widen the list to match: a name added to POLICY_FILES "
            "for a file nobody reads is a suppression with no reader, and a file deleted "
            "from %s while its name stays is a reader with no suppressions." % r.policy_dir,
            file=sys.stderr,
        )
        return 1

    print(
        "%s✓%s policy inventory: %d file(s) in %s/ == %d name(s) in POLICY_FILES (%s) "
        "== %d name(s) in POLICY_FILES (%s); %d exempt by name in the directory; %s still "
        "refused entry with %d BLOCKER: line(s) (%s); 0 literal "
        "join(s) outside the two seams across %d file(s) via %s, %d of which mention a "
        "policy name or POLICY_DIR (%d exempt in test corpora, %d exempt by name); %d "
        "comment line(s) swept for stale POLICY_DIR claims and root-path citations"
        % (
            GREEN,
            NC,
            r.dir_count,
            r.policy_dir,
            r.ts_count,
            TS_SEAM,
            r.py_count,
            PY_SEAM,
            len(DIRECTORY_EXEMPT),
            REFUSED_FILE,
            r.refused_blockers,
            REFUSED_RECORD,
            r.files,
            r.enumerator,
            r.candidates,
            r.exempt_test_sites,
            len(r.named),
            r.comment_lines,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
