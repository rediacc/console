"""Refuse a Bash command that writes an append-only agent store by hand: `agent/reggate/`, the worklist event log `agent/worklist/*.jsonl`, or a ledger under `agent/ledgers/` other than the live-proof ledger, which has its own guard.

WHY (review finding 896a95d5.3). These stores are event logs their readers fold without asking who wrote a line. `wl_reggate.retire()` checks a `retire` line's `ASKED:` minute against the transcript before it appends, but `paid_sigs` cannot when it reads, so a hand-typed `retire` with a well-formed stamp pays a debt; a hand-typed worklist event ticks an item no verb checked. This is the pre-bash half of the agent store row of `_write_rules.ROWS`; `block_guarded_path_edit` refuses the Edit/Write half from the same row.

THE SANCTIONED WRITERS ARE PROCESSES, so most pass without an exception list: `worklist.py --tick ...`, `python3 -m rediacc_ci.ops.dmarc_reports --log` and the Stop hook write through Python whose command words name no store path, and no reading below takes an interpreter's argv as a write. The one admission is for a hook script run BY PATH (`python3 .claude/hooks/stop/worklist.py`, or the script itself through its shebang): a script the working tree changed is read by `shellscan.interpreter_program`, and the worklist verbs' own source writes these stores, so a run whose script lives under `.claude/hooks/` is not judged by its program text. A redirect, `tee` or copy added to that same command is still refused, because those records are judged whatever the run is.

WHAT COUNTS AS A WRITE, read by the lexer and never by a regex over the raw text, so `cat`, `jq`, `grep`, `wc`, `git diff`, `git add` and `git commit -- <store>` all pass:
  - every record of the chain's one walk (`shellscan.event_write_records`): an output redirect, `tee`, an in-place `sed`/`perl`, a copier (`cp`, `mv`, `install`, `rsync`, `ln`) placed where the tool places it, an output option, an unlisted command's word (`touch`), `truncate`, `rm`, and a string target of a Python program's write call; each judged where it LANDS, symlinks followed and a glob expanded, so `cd agent/reggate && echo x >> main.jsonl` and a link to a store are both the store. A pathspec of a restoring git verb is the restore guards' to judge, not this one's;
  - a word the walk cannot expand (`echo x >> $(echo agent/reggate/main.jsonl)`) whose text names a store directory: refused with the advice to spell the path, since what it lands on cannot be read;
  - interpreter code the walk does not read as Python (node, perl, ruby, a Python program that does not parse): a line naming a store directory beside write code; code this hook cannot read at all is refused when the command names a store.

RESIDUE, stated so nobody reads the green as more than it is: a path assembled from parts in non-Python code (`'agent/' + 'reggate'` in node) is not read, nor a Python write through a name bound in a scope the walk's interpreter reading does not follow, nor a write by a tracked script edited to write a store and then run (that is not a direct write; its commit is reviewed). `rm -rf agent` removes every store and is not this guard's to judge.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`), so it is judged against `test-block_agent_store_shell_write.py` beside it and against its own DEFECT, never against a golden.
"""

import glob
import os
import re

from rediacc_hooks import hookio, shellscan
from rediacc_hooks.guards import _write_rules, tables

__getattr__ = tables("block_agent_store_shell_write", "EDGE_CASES")

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 73

# The landing test is the whole guard: with it gone no record ever lands on a store.
DEFECT = ("    if not path:\n        return False", "    if True:\n        return False")

# The path, the refusal and the sanctioned writers are one row of `_write_rules.ROWS`, shared with the edit half.
RULE = _write_rules.ROWS["agent_store"]
if RULE.path is None:
    raise RuntimeError("the agent_store row of _write_rules.ROWS names no path")
STORE_PATH = RULE.path
MESSAGE = RULE.message[1]

# A store directory named in text (an unexpanded word, a line of code). Looser than STORE_PATH on purpose: the text is not a path yet, so its boundary is any non-path character.
STORE_TEXT = re.compile(r"(?<![\w.-])agent/(?:reggate|worklist|ledgers)(?:/|\b)")
# A hook script run by path: the worklist verbs and the hook processes, whose own source writes the stores.
SANCTIONED_SCRIPT = re.compile(r"(\A|/)\.claude/hooks/[^\0]+\.py\Z")
INTERPRETERS = shellscan.INTERPRETER_NAMES
_PATH_MAX = shellscan.PATH_MAX
_GLOB = frozenset("*?[")
_UNEXPANDED = frozenset("$`")

# Code that opens a file for writing, appends to one, replaces or removes one (the ledger guard's reading).
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|\.open\(\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|O_WRONLY|O_RDWR|O_APPEND|O_CREAT|O_TRUNC"
    r"|write_text|write_bytes|append_lines|os\.replace|os\.rename|shutil\.(copy|move)|unlink|writeFileSync|appendFileSync|createWriteStream|>>"
)

# How each `shellscan.write_records` reading is named in the refusal. "git" (a restoring verb's pathspec) is the restore guards'; "unknown" is judged by its text below.
_HOW = {
    "redirect": "redirect into %(path)s",
    "append": "append into %(path)s",
    "tee": "tee into %(path)s",
    "in-place": "in-place edit of %(path)s",
    "copy": "copy onto %(path)s",
    "option": "a command writing %(path)s through its own output option",
    "unread": "%(name)s naming %(path)s, which this guard does not read as a reader",
    "truncate": "truncate of %(path)s",
    "remove": "%(name)s of %(path)s",
    "interpreter": "%(name)s code writing %(path)s",
}


def _lands_on_store(path):
    """Does `path`, as text or resolved on disk (symlinks followed, a glob expanded), land on a store?"""
    if not path:
        return False
    if len(path) > _PATH_MAX or "\n" in path or "\0" in path:
        return False
    if STORE_PATH.search(os.path.normpath(path.replace("\\", "/"))):
        return True
    try:
        candidates = glob.glob(path) if _GLOB & set(path) else [path]
        landed = [os.path.realpath(c) for c in candidates]
    except (OSError, ValueError, RecursionError):
        return False
    return any(STORE_PATH.search(p.replace("\\", "/")) for p in landed)


def _unexpanded_store(word):
    """A word the walk could not expand whose text still names a store directory."""
    if not word or not (_UNEXPANDED & set(word) or shellscan._UNRESOLVED in word):
        return False
    return bool(STORE_TEXT.search(word))


def _script_of(run, cwd):
    """The absolute path of the script a run executes by path (an interpreter's file operand, or the command itself through its shebang), or ""."""
    name = run.name
    base = name.rsplit("/", 1)[-1]
    if base.startswith(INTERPRETERS):
        kind, value = shellscan.program_parse(base, list(run.argv))
        if kind != "file" or not value:
            return ""
        name = value
    elif "/" not in name:
        return ""
    directory = shellscan.write_directory(run.cwd, cwd) if run.cwd is not None else ""
    return os.path.realpath(os.path.join(cwd, directory, name))


def _sanctioned(run, cwd):
    return bool(SANCTIONED_SCRIPT.search(_script_of(run, cwd)))


def _code_writes_store(code):
    return any(STORE_TEXT.search(line) and WRITE_CODE.search(line) for line in code.splitlines())


def _offending(cmd, cwd, records):
    """A short description of the first hand write to a store in `cmd`, or ""."""
    for write in records:
        if write.how == "interpreter" and _sanctioned(write.run, cwd):
            continue
        name = write.run.name.rsplit("/", 1)[-1] if write.run is not None else "a command"
        if write.how in _HOW and _lands_on_store(write.path):
            return _HOW[write.how] % {"path": write.path, "name": name}
        if (write.how in _HOW or write.how == "unknown") and _unexpanded_store(write.word):
            shown = write.word.replace(shellscan._UNRESOLVED, "?")
            return "%s writing through %s, a word this hook cannot expand; spell the path" % (
                name,
                shown,
            )
    for run in shellscan.every_run(cmd):
        name = run.name.rsplit("/", 1)[-1]
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if not name.startswith(INTERPRETERS) or _sanctioned(run, cwd):
            continue
        text, kind = shellscan.interpreter_program(run, cmd, cwd)
        argv = " ".join(run.argv)
        if kind == "unjudgeable":
            if STORE_TEXT.search(argv) or STORE_TEXT.search(cmd):
                return "%s code this hook cannot read (%s)" % (name, shellscan.UNJUDGEABLE_REASON)
            continue
        # Every language is read by its lines as well: the walk's Python reading follows bindings, this one catches the line that names a store beside write code in node, perl, ruby and Python the walk does not parse.
        code = argv + "\n" + (text or "") if kind in ("stdin", "file") else argv
        if kind == "inline" and text:
            code = text
        if _code_writes_store(code):
            return "%s code writing a store" % name
    return ""


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd:
        return hookio.ALLOW
    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    what = _offending(cmd, cwd, shellscan.event_write_records(ev))
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % what)
    return hookio.DENY
