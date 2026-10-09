"""Refuse a Bash command that writes a per-commit review record under `agent/reviews/` by hand.

WHY. The pre-bash half of `block_review_file_edit` (agent/plans/PLAN-per-commit-review.md section 6): the Edit/Write tools are refused there, so the same hand edit through the shell is refused here. The shapes are the ones a session reaches for: an output redirection (`>`, `>>`, `>|`), `tee`, `sed -i`/`perl -i`, `cp`/`mv`/`install`/`rsync`/`ln` onto the directory, `truncate`, `dd of=`, and an
interpreter one-liner or heredoc (`python3 -c`, `python3 - <<EOF`, `node -e`) whose code names the directory and opens something for writing.

READ BY THE LEXER, NOT BY A REGEX OVER THE TEXT. `shellscan` already knows where bash really redirects and which words are a command's operands, so `echo "agent/reviews"`, `cat agent/reviews/b/x.md`, `grep -rn x agent/reviews/` and a commit message naming the path all pass. The two sanctioned writers are named and pass too: the reviewer (`wl_review.py`) and the worklist verbs that
call it (`worklist.py --review-mark`, `--review-commit`, `--review-run`).

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_review_file_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import ast
import re
import shlex

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 53

# The path test every shell shape goes through. With it answering no, every redirect, tee, sed -i and copy onto a review file passes.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

REVIEW_TEXT = "agent/reviews/"
# A string literal that IS a review path (relative or absolute), as opposed to prose that mentions one: the quote is followed by path characters only. A URL (`https://.../agent/reviews/...`) names a web page, not a file on disk, so a literal opening with a scheme is not one.
REVIEW_LITERAL = re.compile(r"['\"](?![A-Za-z][A-Za-z0-9+.-]*://)(?:[^'\"\s]*/)?agent/reviews/")
REVIEW_WORD = re.compile(r"(\A|/)agent/reviews(/|\Z)")
SANCTIONED = ("wl_review.py", "worklist.py")
COPIERS = ("cp", "mv", "install", "rsync", "ln")
INPLACE = ("sed", "perl", "gsed")
INTERPRETERS = ("python", "python3", "node", "perl", "ruby")
# Code that opens a file for writing, replaces or removes one. `.open('w')` is pathlib's spelling, whose mode is the FIRST argument (e30f1ad1.1).
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC|write_text|write_bytes|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync"
)
# Code that hands a string to a shell or starts a program (e30f1ad1.2): its string literals are commands, judged by this guard's own shell reading rather than by the line-scoped write test, which a redirect inside `os.system('echo x > ...')` never meets.
SHELL_CALL = re.compile(
    r"\b(system|popen|exec(Sync|File|FileSync)?|spawn(Sync)?|subprocess|check_output|check_call|getoutput|getstatusoutput|qx|Popen3?|Open3)\b|`"
)
_LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`([^`\n]*)`")
# How deep a command handed to a shell from inside a program is followed; a program that runs a program that runs a shell is two.
MAX_DEPTH = 4

MESSAGE = (
    "BLOCKED: this command writes a per-commit review record by hand (%s).\n"
    "\n"
    "Review files are written by the reviewer and closed only through the verb, which checks\n"
    "the fix before it records it. A hand edit is how a high finding disappears without a fix.\n"
    "\n"
    "  close a finding:  .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> fixed <sha>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> not-a-bug <evidence path:line>\n"
    "                    .claude/hooks/stop/worklist.py --review-mark <me> <finding-id> deferred #<item>\n"
    "  re-review:        python3 .claude/hooks/stop/wl_review.py --run <sha> --branch <branch>\n"
    "  record them:      .claude/hooks/stop/worklist.py --review-commit <me>\n"
)

R = "agent/reviews/0930-1/" + "a" * 40 + ".md"

EDGE_CASES = [
    ("a redirect", "printf 'Resolution: fixed' > %s" % R),
    ("an append", "echo x >> %s" % R),
    ("an append to the clean ledger", "echo '{}' >> agent/reviews/0930-1/clean.jsonl"),
    ("a cat heredoc", "cat > %s <<'EOF'\n# Review\nEOF" % R),
    ("tee", "echo x | tee %s" % R),
    ("tee -a", "echo x | tee -a %s >/dev/null" % R),
    ("sed -i", "sed -i 's/\\[high\\]/[low]/' %s" % R),
    ("cp onto the directory", "cp /tmp/x.md agent/reviews/0930-1/"),
    ("mv onto a review file", "mv /tmp/x.md %s" % R),
    ("truncate", "truncate -s 0 %s" % R),
    ("python -c open for write", "python3 -c \"open('%s','w').write('x')\"" % R),
    (
        "python heredoc write_text",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('x')\nEOF" % R,
    ),
    ("after cd", "cd agent/reviews/0930-1 && echo x > a.md"),
    ("inside sh -c", "sh -c 'echo x > %s'" % R),
    # allowed
    ("reading one", "cat %s" % R),
    ("grep over the directory", "grep -rn high agent/reviews/"),
    ("echo naming the path", "echo 'see agent/reviews/0930-1/'"),
    ("a commit that carries them", "git commit -F /tmp/m.txt -- agent/reviews/0930-1/"),
    ("git add", "git add -- agent/reviews/0930-1/%s.md" % ("a" * 40)),
    (
        "the mark verb",
        ".claude/hooks/stop/worklist.py --review-mark abcd1234 aaaaaaaa.1 fixed %s" % ("b" * 40),
    ),
    ("the reviewer", "python3 .claude/hooks/stop/wl_review.py --run abc --branch 0930-1"),
    ("a copy OUT of the directory", "cp %s /tmp/x.md" % R),
    ("a python read", "python3 -c \"print(open('%s').read())\"" % R),
    (
        "python heredoc rewriting a URL that names the directory",
        (
            "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('t.py')\n"
            "p.write_text(p.read_text().replace('\"https://github.com/o/r/blob/h/agent/reviews/b/x.md\"', 'U'))\nEOF"
        ),
    ),
    ("an unrelated redirect", "echo x > /tmp/out.txt"),
    ("a sibling directory", "echo x > agent/reviews-old/x.md"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "sed -i launched by find under the directory",
        "find agent/reviews -name '*.md' -exec sed -i s/high/low/ {} +",
    ),
    (
        "a launched cp onto what find names",
        r"find agent/reviews -name '*.md' -exec cp /tmp/x.md {} \;",
    ),
    (
        "a launched copy OUT of the directory",
        r"find agent/reviews -name '*.md' -exec cp {} /tmp/ \;",
    ),
    # A Python program is judged by its write TARGETS: a review path in written content is data.
    (
        "a review path only in written content",
        "python3 - <<'EOF'\nimport pathlib\np = pathlib.Path('/tmp/s/f.py')\ns = p.read_text().replace('X', 'agent/reviews/feat/%02d.md')\np.write_text(s)\nEOF",
    ),
    (
        "a target built from a review path",
        "python3 - <<'EOF'\nimport pathlib\nT = 'agent/reviews/feat/%02d.md'\npathlib.Path(T % 1).write_text('x')\nEOF",
    ),
    # e30f1ad1.1: pathlib's `.open` takes its mode first, `os.open` takes flags.
    ("Path.open for write", "python3 -c \"import pathlib; pathlib.Path('%s').open('w')\"" % R),
    ("Path.open for read", "python3 -c \"import pathlib; pathlib.Path('%s').open().read()\"" % R),
    ("os.open for write", "python3 -c \"import os; os.open('%s', os.O_WRONLY)\"" % R),
    # e30f1ad1.2: a command a program hands to a shell is judged as the shell line it is.
    ("os.system redirect", "python3 -c \"import os; os.system('echo x > %s')\"" % R),
    ("subprocess argv tee", "python3 -c \"import subprocess; subprocess.run(['tee', '%s'])\"" % R),
    ("node execSync redirect", "node -e \"require('child_process').execSync('echo x > %s')\"" % R),
    (
        "os.system reading the directory",
        "python3 -c \"import os; os.system('cat %s > /tmp/x')\"" % R,
    ),
]


def _is_review(word, cwd=None):
    if not word:
        return False
    if REVIEW_WORD.search(word):
        return True
    return bool(cwd and REVIEW_WORD.search(str(cwd).rstrip("/") + "/" + word))


def _operands(argv):
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _run_operands(run, argv):
    """`_operands`, with a `find -exec` run's `{}` read as what the find walks (#503f0ba8): `find agent/reviews -exec sed -i ... {} +` edits files under `agent/reviews`, so the find's starting points (`shellscan.Launch.starts`) stand in for `{}`, in place. A `{}` that is a copy's SOURCE is still not its last operand, so `-exec cp {} /tmp/ ';'` stays a copy out."""
    ops = _operands(argv)
    if run.launch is None or run.launch.launcher != "find":
        return ops
    out: list[str] = []
    for a in ops:
        out.extend(run.launch.starts if "{}" in a else [a])
    return out


def _offending(cmd, depth=0):
    """A short description of the first hand write to a review file in `cmd`, or "". `depth` counts the programs a shell command was handed down through (`os.system`, `subprocess.run`, `execSync`), so a command quoting itself cannot recurse forever.

    PAST THE CAP IT REFUSES. A command is only handed down when it names the review directory, so one nested deeper than MAX_DEPTH is a review path this guard stopped reading, and allowing it would let depth alone carry a write past the guard.
    """
    if depth > MAX_DEPTH:
        return (
            "a command nested more than %d programs deep that names the review directory"
            % MAX_DEPTH
        )
    hits = [t for t in shellscan.write_targets(cmd) if _is_review(t)]
    if hits:
        return "redirect into %s" % hits[0]
    analysis = shellscan._analyse(cmd)
    # THE LAUNCHED COMMANDS TOO (#503f0ba8): a `sed -i`, `cp` or interpreter that `find -exec` or `npx -c` starts writes the same review file, so the runs are `shellscan.every_run`.
    for run in shellscan.every_run(cmd):
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        if any(a.rsplit("/", 1)[-1] in SANCTIONED for a in [run.name, *argv[:2]]):
            continue
        for target in run.writes:
            if _is_review(target, run.cwd):
                return "redirect into %s" % target
        operands = _run_operands(run, argv)
        if name == "tee" and any(_is_review(a, run.cwd) for a in operands):
            return "tee into the review directory"
        in_place = any(a == "-i" or a.startswith(("-i", "--in-place")) for a in argv)
        if name in INPLACE and in_place and any(_is_review(a, run.cwd) for a in operands):
            return "%s -i on a review file" % name
        if name in COPIERS and operands and _is_review(operands[-1], run.cwd):
            return "%s onto the review directory" % name
        if name == "truncate" and any(_is_review(a, run.cwd) for a in operands):
            return "truncate of a review file"
        if name == "dd" and any(a.startswith("of=") and _is_review(a[3:], run.cwd) for a in argv):
            return "dd of= a review file"
        if name.startswith(INTERPRETERS):
            # A heredoc is this interpreter's code only when it reads its program from stdin (`python3 -`, a bare `python3`); a `cat > x.py <<EOF` earlier in the line is a file being written, not code being run.
            reads_stdin = not operands or operands[0] == "-"
            code = " ".join(argv)
            if reads_stdin:
                code += "\n" + "\n".join(_heredoc_bodies(cmd, analysis))
            program = _python_program(name, argv, reads_stdin, cmd, analysis)
            verdict = _python_writes_review(program, depth) if program is not None else None
            if verdict is None:
                verdict = _code_writes_review(code, depth)
            if verdict:
                return "%s code that writes into the review directory" % name
    return ""


def _code_writes_review(code, depth=0):
    """Interpreter code that writes a review path: a write on a line naming the directory, or through a name bound to such a path, or a shell command on a line that hands one to a shell.

    LINE-SCOPED, measured on its first live run: a python heredoc that patched an unrelated module, whose replacement text merely MENTIONED the directory in a comment, was refused when any write anywhere plus any mention anywhere was enough. A write and a path LITERAL (a quote followed by path characters, not prose) have to meet on one line, or through a variable assigned from such a literal.
    A SHELL CALL IS A THIRD WAY (e30f1ad1.2): on a line that hands a string to a shell (`system(...)`, `execSync(...)`, backticks), each string literal is read as a command by `_offending`, so `system("echo x > agent/reviews/a.md")` is the redirect it spells, while a literal that only names the directory is a command that writes nothing.
    """
    if REVIEW_TEXT not in code:
        return False
    for line in code.splitlines():
        if REVIEW_TEXT in line and SHELL_CALL.search(line):
            for m in _LITERAL.finditer(line):
                text = next(g for g in m.groups() if g is not None)
                if REVIEW_TEXT in text and _offending(text, depth + 1):
                    return True
    names = {
        m.group(1)
        for m in re.finditer(r"\b([A-Za-z_]\w*)\s*=\s*([^\n=]*)", code)
        if REVIEW_LITERAL.search(m.group(2))
    }
    for line in code.splitlines():
        if REVIEW_LITERAL.search(line) and WRITE_CODE.search(line):
            return True
        for name in names:
            if re.search(r"\b%s\b" % re.escape(name), line) and WRITE_CODE.search(line):
                return True
    return False


# PYTHON IS JUDGED BY ITS WRITE TARGETS (2026-10-09). The line-scoped reading below refused a heredoc that wrote only a scratchpad file, because a review path TEMPLATE flowed into the written content (`s = s.replace(..., 'agent/reviews/feat/%02d.md')` then `p.write_text(s)`): the name `s` was bound to a review literal, and a write named it. The content of a write is not where it lands.
# So a Python program that parses is read with `ast`: each write call's TARGET expression (the path `open` opens for writing, the receiver of `write_text`/`write_bytes`/`unlink`/`touch`, the destination of `os.replace`/`os.rename`/`shutil.copy*`/`shutil.move`, the path `os.remove` deletes) is refused when it holds a review path string or a name bound to one, transitively. Strings anywhere else are data. Node, perl, ruby and Python that does not parse keep the line-scoped regex.
_WRITE_MODE = re.compile(r"[wax+]")
_RECEIVER_WRITES = frozenset(
    ("write_text", "write_bytes", "unlink", "touch", "rmdir", "symlink_to", "hardlink_to")
)
_RECEIVER_MOVES = frozenset(("rename", "replace"))
_DEST_CALLS = frozenset(
    ("replace", "rename", "move", "copy", "copy2", "copyfile", "copytree", "link", "symlink")
)
_REMOVE_CALLS = frozenset(("remove", "unlink", "rmtree", "truncate"))
_URL = re.compile(r"\A[A-Za-z][A-Za-z0-9+.-]*://")


def _python_program(name, argv, reads_stdin, cmd, analysis):
    """The Python program text a python run executes (`-c` value, or its stdin heredocs), or None for anything else."""
    if not re.match(r"^python[0-9.]*$", name):
        return None
    for k, a in enumerate(argv):
        if a == "-c":
            return argv[k + 1] if k + 1 < len(argv) else None
        if a.startswith("-c") and len(a) > 2:
            return a[2:]
    return "\n".join(_heredoc_bodies(cmd, analysis)) if reads_stdin else None


def _is_review_string(value):
    return (
        isinstance(value, str) and not _URL.match(value) and REVIEW_WORD.search(value) is not None
    )


def _imports(tree):
    """Each imported local name -> what it names: `import subprocess as sp` gives `sp -> subprocess`, `from os import system` gives `system -> os.system`."""
    names: dict[str, str] = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for a in node.names:
                if a.asname:
                    names[a.asname] = a.name
                else:
                    head = a.name.split(".")[0]
                    names[head] = head
        elif isinstance(node, ast.ImportFrom) and node.module:
            for a in node.names:
                names[a.asname or a.name] = "%s.%s" % (node.module, a.name)
    return names


def _qualified(func, imports):
    """The dotted name a call's function spells after resolving import aliases (`sp.run` -> `subprocess.run`), or ""."""
    parts = []
    while isinstance(func, ast.Attribute):
        parts.append(func.attr)
        func = func.value
    if not isinstance(func, ast.Name):
        return ""
    parts.append(imports.get(func.id, func.id))
    return ".".join(reversed(parts))


# `os.open`'s flags: anything but these read-only bits (a write flag, a variable, a number with a write bit) can write.
_READ_FLAGS = frozenset(
    (
        "os",
        "O_RDONLY",
        "O_CLOEXEC",
        "O_NOFOLLOW",
        "O_DIRECTORY",
        "O_NONBLOCK",
        "O_NOCTTY",
        "O_BINARY",
        "O_PATH",
        "O_NOATIME",
        "O_LARGEFILE",
    )
)


def _flags_can_write(expr):
    for n in ast.walk(expr):
        if isinstance(n, ast.Name) and n.id not in _READ_FLAGS:
            return True
        if isinstance(n, ast.Attribute) and n.attr not in _READ_FLAGS:
            return True
        if isinstance(n, ast.Constant) and isinstance(n.value, int) and n.value & 0o3:
            return True
    return False


def _mode_can_write(mode):
    """An `open` mode argument: absent is a read, a constant is read by its letters, and anything else (a variable, `*args`) is assumed to write."""
    if mode is None:
        return False
    if isinstance(mode, ast.Constant):
        return isinstance(mode.value, str) and _WRITE_MODE.search(mode.value) is not None
    return True


def _keyword(node, name):
    return next((k.value for k in node.keywords if k.arg == name), None)


def _write_targets(tree, imports=None):
    """The target expressions of every write call in a Python tree.

    `open` has three shapes (e30f1ad1.1): the builtin and a module function (`io.open`, `codecs.open`, `gzip.open`) take the path first and the mode second; `os.open` takes FLAGS second; and a method on a path object (`Path(p).open('w')`) takes the mode FIRST, the receiver being the target.
    """
    imports = _imports(tree) if imports is None else imports
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        attr = (
            func.attr
            if isinstance(func, ast.Attribute)
            else func.id
            if isinstance(func, ast.Name)
            else ""
        )
        if attr == "open":
            qualified = _qualified(func, imports)
            on_module = isinstance(func, ast.Name) or (
                isinstance(func, ast.Attribute)
                and isinstance(func.value, ast.Name)
                and func.value.id in imports
            )
            if qualified == "os.open":
                flags = node.args[1] if len(node.args) > 1 else _keyword(node, "flags")
                path = node.args[0] if node.args else _keyword(node, "path")
                if flags is not None and path is not None and _flags_can_write(flags):
                    yield path
            elif on_module:
                mode = node.args[1] if len(node.args) > 1 else _keyword(node, "mode")
                path = node.args[0] if node.args else _keyword(node, "file")
                if path is not None and _mode_can_write(mode):
                    yield path
            elif isinstance(func, ast.Attribute):
                mode = node.args[0] if node.args else _keyword(node, "mode")
                if _mode_can_write(mode):
                    yield func.value
            continue
        # `os.replace(a, b)` and `str.replace(old, new)` share a name: a module call counts only when `os` or `shutil` qualifies it, and the receiver form only with Path's single argument.
        module = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in ("os", "shutil")
        )
        receiver_write = attr in _RECEIVER_WRITES or (
            attr in _RECEIVER_MOVES and len(node.args) == 1
        )
        if isinstance(func, ast.Attribute) and not module and receiver_write:
            yield func.value
            yield from node.args[:1] if attr in _RECEIVER_MOVES else ()
        if module and attr in _DEST_CALLS and len(node.args) > 1:
            if attr in ("replace", "rename", "move"):
                yield node.args[0]
            yield node.args[1]
        if module and attr in _REMOVE_CALLS and node.args:
            yield node.args[0]


# Calls that hand a command to a shell or start a program (e30f1ad1.2), by qualified name: the first argument (or `args=`/`cmd=`) is the command, a string for a shell and a list for an argv.
_SHELL_CALLS = frozenset(
    (
        "os.system",
        "os.popen",
        "subprocess.run",
        "subprocess.call",
        "subprocess.check_call",
        "subprocess.check_output",
        "subprocess.Popen",
        "subprocess.getoutput",
        "subprocess.getstatusoutput",
    )
)
# Text standing in for a piece of a command the ast cannot spell: a name bound to a review path renders as one, anything else as an unknown path segment.
# The unknown ends in `/` so text glued after it still starts a segment: `f"{root}agent/reviews/a.md"` renders `_/agent/reviews/a.md`, which REVIEW_WORD matches. A bare `_` made it `_agent/reviews/a.md`, which it did not (review 071b7987.1).
_UNKNOWN = "_/"
_UNKNOWN_REVIEW = "agent/reviews/_"
# A printf-style conversion in a `%` template: `%s`, `%-10r`, `%(name)s`, `%%` (a literal percent).
_PERCENT_SPEC = re.compile(r"%(\([^)]*\))?[-#0 +]*(\*|\d+)?(\.(\*|\d+))?[a-zA-Z%]")
# A replacement field in a `str.format` template: `{}`, `{0}`, `{name!r:>10}`; `{{`/`}}` are literal braces.
_FORMAT_FIELD = re.compile(r"\{\{|\}\}|\{[^{}]*\}")
_PATH_CTORS = frozenset(("Path", "PurePath", "PosixPath", "PurePosixPath"))


def _is_path_join(func):
    """`os.path.join` or `posixpath.join`, spelled as the call names it."""
    if not (isinstance(func, ast.Attribute) and func.attr == "join"):
        return False
    owner = func.value
    if isinstance(owner, ast.Name):
        return owner.id == "posixpath"
    return (
        isinstance(owner, ast.Attribute)
        and owner.attr == "path"
        and isinstance(owner.value, ast.Name)
        and owner.value.id == "os"
    )


def _is_path_ctor(func):
    """`Path(...)` and its siblings, bare or as `pathlib.Path`."""
    if isinstance(func, ast.Name):
        return func.id in _PATH_CTORS
    return isinstance(func, ast.Attribute) and func.attr in _PATH_CTORS


def _render(expr, bound, review_names, seen=frozenset()):
    """The text a string expression evaluates to, as near as the ast spells it: constants, f-strings, `+`, `%` and `str.format`, `os.path.join`, `Path(...)` and `/`, and names bound once to such an expression."""

    def sub(node):
        return _render(node, bound, review_names, seen)

    if isinstance(expr, ast.Constant):
        return expr.value if isinstance(expr.value, str) else str(expr.value)
    if isinstance(expr, ast.JoinedStr):
        return "".join(sub(v) for v in expr.values)
    if isinstance(expr, ast.FormattedValue):
        return sub(expr.value)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Add):
        return sub(expr.left) + sub(expr.right)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Div):
        return sub(expr.left).rstrip("/") + "/" + sub(expr.right)
    if isinstance(expr, ast.BinOp) and isinstance(expr.op, ast.Mod):
        # Each conversion takes the next argument (or the mapping's value, unknown); `%%` stays a percent (review 071b7987.1 sibling).
        args = iter(
            [sub(e) for e in expr.right.elts]
            if isinstance(expr.right, ast.Tuple)
            else [sub(expr.right)]
        )
        return _PERCENT_SPEC.sub(
            lambda m: "%" if m.group(0) == "%%" else next(args, _UNKNOWN), sub(expr.left)
        )
    if isinstance(expr, ast.Call):
        func = expr.func
        if (
            isinstance(func, ast.Attribute)
            and func.attr == "format"
            and isinstance(func.value, ast.Constant)
            and isinstance(func.value.value, str)
        ):
            args = iter([sub(a) for a in expr.args])
            return _FORMAT_FIELD.sub(
                lambda m: m.group(0)[0] if m.group(0) in ("{{", "}}") else next(args, _UNKNOWN),
                func.value.value,
            )
        if _is_path_join(func) or _is_path_ctor(func):
            return "/".join(sub(a).rstrip("/") for a in expr.args) if expr.args else _UNKNOWN
        if (
            isinstance(func, ast.Name)
            and func.id in ("str", "os.fspath", "fspath")
            and len(expr.args) == 1
        ):
            return sub(expr.args[0])
        if isinstance(func, ast.Attribute) and func.attr == "fspath" and len(expr.args) == 1:
            return sub(expr.args[0])
    if isinstance(expr, ast.Name):
        values = bound.get(expr.id, [])
        if len(values) == 1 and expr.id not in seen:
            return _render(values[0], bound, review_names, seen | {expr.id})
        return _UNKNOWN_REVIEW if expr.id in review_names else _UNKNOWN
    return _UNKNOWN


def _shell_commands(tree, imports, bound, review_names):
    """Every command a Python tree hands to a shell or starts, rendered as one shell line."""
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _qualified(node.func, imports) not in _SHELL_CALLS:
            continue
        arg = node.args[0] if node.args else _keyword(node, "args") or _keyword(node, "cmd")
        if arg is None:
            continue
        if isinstance(arg, (ast.List, ast.Tuple)):
            yield shlex.join(_render(e, bound, review_names) for e in arg.elts)
        else:
            yield _render(arg, bound, review_names)


def _python_writes_review(program, depth=0):
    """True or False for a Python program that parses, by its write targets and the shell commands it runs; None when it does not parse, so the regex reading answers instead.

    THE SHELL COMMANDS ARE ADDITIVE (e30f1ad1.2): a program whose only write is `os.system('echo x > agent/reviews/a.md')` names no write target, so each command it hands to a shell is rendered and judged by `_offending` as the shell line it is. A review path in written CONTENT is still data: only a string that reaches a shell is read as a command.
    """
    if REVIEW_TEXT.rstrip("/") not in program:
        return False
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    bound: dict[str, list[ast.AST]] = {}
    for node in ast.walk(tree):
        if isinstance(node, (ast.Assign, ast.AnnAssign, ast.AugAssign)) and node.value is not None:
            targets = node.targets if isinstance(node, ast.Assign) else [node.target]
            for t in targets:
                for n in ast.walk(t):
                    if isinstance(n, ast.Name):
                        bound.setdefault(n.id, []).append(node.value)
        elif isinstance(node, ast.NamedExpr):
            bound.setdefault(node.target.id, []).append(node.value)
    review_names: set[str] = set()

    def holds_review(expr):
        for n in ast.walk(expr):
            if isinstance(n, ast.Constant) and _is_review_string(n.value):
                return True
            if isinstance(n, ast.Name) and n.id in review_names:
                return True
        return False

    changed = True
    while changed:
        changed = False
        for name, values in bound.items():
            if name not in review_names and any(holds_review(v) for v in values):
                review_names.add(name)
                changed = True
    imports = _imports(tree)
    if any(holds_review(t) for t in _write_targets(tree, imports)):
        return True
    return any(
        REVIEW_TEXT.rstrip("/") in c and _offending(c, depth + 1)
        for c in _shell_commands(tree, imports, bound, review_names)
    )


def _heredoc_bodies(cmd, analysis):
    """The text of every heredoc the lexer read; a body fed to an interpreter is code."""
    return [
        cmd[doc.body_start : doc.body_end]
        for doc in analysis.heredocs
        if doc.body_start is not None and doc.body_end is not None
    ]


def run(ev):
    cmd = ev.field("tool_input", "command")
    if "reviews" not in cmd:
        return hookio.ALLOW
    what = _offending(cmd)
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
