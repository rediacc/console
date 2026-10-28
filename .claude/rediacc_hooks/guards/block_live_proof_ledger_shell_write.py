"""Refuse a Bash command that writes the live-proof ledger, `agent/ledgers/live-proof.jsonl`, by any route but the recorder.

WHY. The pre-bash half of `block_live_proof_ledger_write` (agent/plans/PLAN-tested-on-bench.md box V10): the Edit/Write tools are refused there, so the same hand write through the shell is refused here. The one sanctioned writer is `python3 -m rediacc_ci.ops.live_proof record --write`, a module run whose words name no ledger path, so it passes without an exception list; a redirect
added to that same command is still refused.

WHAT COUNTS AS A WRITE, read by the lexer (`shellscan`) and never by a regex over the raw text, so `cat`, `jq`, `grep`, `git diff`, `git add` and a commit message naming the ledger all pass:
  - an output redirection (`>`, `>>`, `>|`) whose target lands on the ledger, as typed and as bash expands it;
  - `tee`, an in-place `sed`/`perl`, `truncate`, `dd of=` or `rm` naming it, and a copier (`cp`, `mv`, `install`, `rsync`, `ln`) whose destination lands on it (`shellscan.copy_landings`, so a copy into `agent/ledgers/` of a file named `live-proof.jsonl` counts);
  - any other command's output word (`shellscan.output_landings`): an output option of a listed reader (`sort -o`), or any word of a command that table does not list as a reader (`touch`, `rm`);
  - interpreter code: a Python program whose write targets, or whose appending calls (`append_lines`, `.write`, `json.dump`), name the ledger, a call of `ledger_path`, or the `LEDGER` constant; other interpreters, and Python that does not parse, by a line that names the ledger beside write code. A program that imports the recorder and passes `write=True`,
    or calls its `_judge_and_write`, is refused too: an in-process `record(..., world=World(run=<fake>))` would append a VERIFIED row for steps that never ran.

WHERE A WORD LANDS is read on disk as well as in text: each word is joined to the directory its run executes in (`shellscan.write_directory`) and resolved through symlinks, and a word with a glob is expanded there, so `cd agent/ledgers && echo x >> live-proof.jsonl`, `echo x >> agent/ledgers/live-pr*.jsonl` and a link to the ledger are each the ledger.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_live_proof_ledger_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import ast
import glob
import os
import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import block_live_proof_ledger_write as EDIT

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 65

# The landing test is the whole guard: with it gone no word is ever the ledger.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

LEDGER_REL = EDIT.LEDGER_REL
LEDGER_PATH = EDIT.LEDGER_PATH
LEDGER_NAME = "live-proof.jsonl"
INTERPRETERS = shellscan.INTERPRETER_NAMES
_PATH_MAX = 4096
_GLOB = frozenset("*?[")

# Code that opens a file for writing, appends to one, replaces or removes one (the review-file guard's reading plus the append verbs this ledger is written with).
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC"
    r"|write_text|write_bytes|append_lines|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync|>>"
)
# A Python call whose name says it writes; one whose argument holds the ledger is a write to it.
_WRITE_CALL = re.compile(
    r"(?i)(write|append|dump|save|copy|move|replace|rename|unlink|remove|truncate)"
)
_PATH_KEYWORDS = frozenset(("path", "file", "dst", "dest", "target", "filename"))
# Driving the recorder in-process with its write switch on, or its writing step directly.
RECORDER_MODULE = re.compile(r"\blive_proof\b")
RECORDER_WRITE = re.compile(r"\bwrite\s*=\s*True\b|_judge_and_write|\bjsonl_append\b")

MESSAGE = (
    "BLOCKED: this command writes the live-proof ledger by hand (%s).\n"
    "\n"
    "CI trusts agent/ledgers/live-proof.jsonl without re-running anything, so a row is written\n"
    "only by the recorder, after the live run it describes; a hand-written row with a recomputed\n"
    "id is the forgery this guard exists to stop.\n"
    "\n"
    "  record a receipt:  " + EDIT.RECORDER + "\n"
    "  judge the ledger:  PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof verify\n"
)

EDGE_CASES = [
    ("append a row", "echo '{}' >> " + LEDGER_REL),
    ("the recorder", "PYTHONPATH=.ci python3 -m rediacc_ci.ops.live_proof record --write"),
    ("read the ledger", "jq . " + LEDGER_REL),
    ("tee the ledger", "printf x | tee -a " + LEDGER_REL),
    ("stage the ledger", "git add -- " + LEDGER_REL),
]


def _base(where, cwd):
    """The absolute directory a run in `where` (`shellscan.write_directory`'s answer) executes in, or None when the hook's own directory is not an absolute path."""
    if not cwd or not os.path.isabs(str(cwd)):
        return None
    return os.path.join(str(cwd), str(where)) if where else str(cwd)


def _is_ledger(word, base=None):
    """Does `word`, as text or resolved on disk from the absolute directory `base` (symlinks followed, a glob expanded), land on the live-proof ledger?"""
    if not word:
        return False
    if len(word) > _PATH_MAX or "\n" in word or "\0" in word:
        return False
    if LEDGER_PATH.search(word.replace("\\", "/")):
        return True
    if not base:
        return False
    joined = os.path.join(base, word)
    try:
        candidates = glob.glob(joined) if _GLOB & set(word) else [joined]
        landed = [os.path.realpath(c) for c in candidates]
    except (OSError, ValueError, RecursionError):
        return False
    return any(LEDGER_PATH.search(p.replace("\\", "/")) for p in landed)


def _operands(argv):
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _operand_write(run, name, argv, base):
    """A description of the ledger write `run` makes through one of its own operands (tee, sed/perl -i, truncate, dd of=, rm), or ""."""
    operands = shellscan.xargs_fed_operands(run, _operands(argv))
    if name == "tee" and any(_is_ledger(a, base) for a in operands):
        return "tee into the ledger"
    edit = shellscan.in_place_edit(run)
    if edit is not None and any(_is_ledger(f, base) for f in [*edit[1], *operands]):
        return "%s -i on the ledger" % name
    if name == "truncate" and any(_is_ledger(a, base) for a in operands):
        return "truncate of the ledger"
    if name == "dd" and any(a.startswith("of=") and _is_ledger(a[3:], base) for a in argv):
        return "dd of= the ledger"
    if name in ("rm", "unlink", "shred") and any(_is_ledger(a, base) for a in operands):
        return "%s of the ledger" % name
    return ""


def _holds_ledger(expr, names):
    """Whether a Python expression carries the ledger: a string naming it (or its file name), a name bound to one, a `ledger_path(...)` call, or the `LEDGER` constant."""
    for n in ast.walk(expr):
        constant = (
            isinstance(n, ast.Constant)
            and isinstance(n.value, str)
            and n.value.rstrip("/").endswith(LEDGER_NAME)
        )
        name = isinstance(n, ast.Name) and (n.id in names or n.id == "LEDGER")
        attribute = isinstance(n, ast.Attribute) and n.attr in ("LEDGER", "ledger_path")
        if constant or name or attribute:
            return True
    return False


def _call_name(func):
    if isinstance(func, ast.Attribute):
        return func.attr
    if isinstance(func, ast.Name):
        return func.id
    return ""


def _python_writes_ledger(program):
    """True or False for a Python program that parses; None when it does not, so the line reading answers."""
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    bound = shellscan.python_bindings(tree)
    names: set = set()
    changed = True
    while changed:
        changed = False
        for name, values in bound.items():
            if name not in names and any(_holds_ledger(v, names) for v in values):
                names.add(name)
                changed = True
    imports = shellscan.python_imports(tree)
    if any(_holds_ledger(t, names) for t in shellscan.python_write_targets(tree, imports)):
        return True
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call) or not _WRITE_CALL.search(_call_name(node.func)):
            continue
        # Where the call writes, not what. A METHOD on an object writes into its receiver, so only the receiver is judged: `fh.write(row)` with `fh` the ledger is a write, and `bad.append(Finding(..., rel))` with `rel` the ledger's name is a list growing (V6 writer, 2026-10-28: `check_plan_live_proof.py --selftest` was refused for exactly that). A FUNCTION, bare or a module's
        # (`append_lines(path, ...)`, `jsonl_append.append_lines(...)`), takes its destination first, so its first argument and a path-named keyword are judged. Written CONTENT that names the ledger is data either way.
        func = node.func
        on_module = (
            isinstance(func, ast.Attribute)
            and isinstance(func.value, ast.Name)
            and func.value.id in imports
        )
        if isinstance(func, ast.Attribute) and not on_module:
            parts = [func.value]
        else:
            parts = [*node.args[:1], *(k.value for k in node.keywords if k.arg in _PATH_KEYWORDS)]
        if any(_holds_ledger(p, names) for p in parts):
            return True
    return False


_RECORDER_MODULE = "rediacc_ci.ops.live_proof"


def _python_drives_recorder(program):
    """True or False for a Python program that parses: does it import the recorder and call something with `write=True`, or call its `_judge_and_write`? None when it does not parse.

    Read from the tree, not the text, so a program that only QUOTES such a line (this guard's own test, a plan being written) is not refused for it.
    """
    try:
        tree = ast.parse(program)
    except (SyntaxError, ValueError, RecursionError, MemoryError):
        return None
    imports = shellscan.python_imports(tree)
    if not any(
        v == _RECORDER_MODULE or v.startswith(_RECORDER_MODULE + ".") for v in imports.values()
    ):
        return False
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        if _call_name(node.func) == "_judge_and_write":
            return True
        for kw in node.keywords:
            if kw.arg == "write" and isinstance(kw.value, ast.Constant) and kw.value.value is True:
                return True
    return False


def _code_writes_ledger(code, program):
    """Interpreter code that writes the ledger: the recorder driven in-process with its write on, a Python program by its targets, else a line naming the ledger beside write code."""
    drives = _python_drives_recorder(program) if program is not None else None
    if drives is None:
        drives = any(
            RECORDER_MODULE.search(line) and RECORDER_WRITE.search(line)
            for line in code.splitlines()
        )
    if drives:
        return "code that drives the recorder in-process with its write on"
    if LEDGER_NAME not in code and "ledger_path" not in code and "LEDGER" not in code:
        return ""
    verdict = _python_writes_ledger(program) if program is not None else None
    if verdict is None:
        verdict = any(
            (LEDGER_NAME in line or "ledger_path" in line) and WRITE_CODE.search(line)
            for line in code.splitlines()
        )
    return "code that writes the ledger" if verdict else ""


def _offending(cmd, cwd):
    """A short description of the first hand write to the ledger in `cmd`, or ""."""
    root = _base(None, cwd)
    hits = [t for t in shellscan.write_targets(cmd) if _is_ledger(t, root)]
    if hits:
        return "redirect into %s" % hits[0]
    for run in shellscan.every_run(cmd):
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        base = _base(shellscan.write_directory(run.cwd, cwd), cwd)
        for target in shellscan.redirect_targets(run):
            if _is_ledger(target, base):
                return "redirect into %s" % target
        variants = [argv]
        if run.xargv is not None and list(run.xargv) != argv:
            variants.append(list(run.xargv))
        for words in variants:
            what = _operand_write(run, name, words, base)
            if what:
                return what
            if any(
                _is_ledger(p, "/") for p, _into in shellscan.copy_landings(run, cwd, argv=words)
            ):
                return "%s onto the ledger" % name
            for word, how in shellscan.output_landings(run, words, cwd):
                if _is_ledger(word, base):
                    return (
                        "%s writing %s through its own output option" % (name, word)
                        if how == "option"
                        else "%s naming %s, and %s is not a command this guard reads as a reader"
                        % (name, word, name)
                    )
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if not name.startswith(INTERPRETERS):
            continue
        text, kind = shellscan.interpreter_program(run, cmd, cwd)
        if kind == "unjudgeable":
            body = " ".join(argv)
            if LEDGER_NAME in body or "ledger" in cmd:
                return "%s code this hook cannot read (%s)" % (name, shellscan.UNJUDGEABLE_REASON)
            continue
        code = " ".join(argv)
        if kind in ("stdin", "file"):
            code += "\n" + (text or "")
        program = text if kind is not None and re.match(r"^python[0-9.]*$", name) else None
        what = _code_writes_ledger(code, program)
        if what:
            return "%s %s" % (name, what)
    return ""


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd:
        return hookio.ALLOW
    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    what = _offending(cmd, cwd)
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
