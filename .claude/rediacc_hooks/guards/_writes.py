"""The helpers the shell-write guards had each copied, in one place (PLAN-tooling-code-reduction CR5, D5).

`block_review_file_shell_write`, `block_user_only_command_shell_write`, `block_live_proof_ledger_shell_write` and `block_suppressions_shell_write` were written one from another, and each carried its own copy of the operand filter, the run-directory join, the quoted-literal reader, the "a write through a link the text never spells" reading and the sed and write-call patterns. A fix to one copy reached none of the others. Each guard now binds these names (`_operands = _writes.operands`), so its own call sites and its DEFECT read as before while the code exists once.

Nothing here decides a verdict: every function answers a reading question, and the guard keeps its own path predicate and message.
"""

import os
import re

from rediacc_hooks import shellscan

# The longest path the kernel resolves; a word longer than this names no file a write can open.
PATH_MAX = 4096

# A quoted string literal in program text: single, double or backquoted, unescaped no further.
LITERAL = re.compile(r"'((?:[^'\\\n]|\\.)*)'|\"((?:[^\"\\\n]|\\.)*)\"|`([^`\n]*)`")

# The commands whose own words are the text they write.
WRITERS = ("echo", "printf", "cat")

# A write call in interpreter text, read line by line by the guards that judge a program's CONTENT (the suppression and user-only halves). The review and ledger halves carry wider patterns of their own (`os.open` flags, `unlink`), because they judge where a program writes rather than what.
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|write_text|write_bytes|\.write\(|writeFileSync"
    r"|appendFileSync|os\.replace|os\.rename|shutil\.(copy|move)"
)

# A sed substitution with its pattern and replacement, any delimiter; and an `a`/`i`/`c` text command's text.
SED_SUB = re.compile(
    r"(?:^|[;\s{])s(?P<d>[^\w\s\\])(?P<pat>(?:\\.|(?!(?P=d)).)*)(?P=d)(?P<rep>(?:\\.|(?!(?P=d)).)*)(?P=d)"
)
SED_TEXT = re.compile(r"(?:^|[;\s])(?:\d+|\$|/[^/]*/)?\s*[aic]\\?\s*(?P<text>[^;\n]*)")


def operands(argv):
    """`run.argv` is the ARGUMENTS, without the command name; every word that is not an option, a lone `-` kept."""
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def run_dir(where, cwd):
    """The absolute directory a run in `where` (`shellscan.write_directory`'s answer) executes in, or None when the hook's own directory is not an absolute path."""
    if not cwd or not os.path.isabs(str(cwd)):
        return None
    return os.path.join(str(cwd), str(where)) if where else str(cwd)


def find_starts(run, ops):
    """`ops` with a `{}` read as the starting points of the `find` that launched this run (`shellscan` `Launch.starts`): `find .claude -exec sed -i ... {} +` edits files under `.claude`."""
    if run.launch is None or run.launch.launcher != "find":
        return ops
    out: list[str] = []
    for a in ops:
        out.extend(run.launch.starts if "{}" in a else [a])
    return out


def literals(text):
    """Every quoted string literal in `text` (single, double or backquoted), unescaped no further."""
    for m in LITERAL.finditer(text):
        yield next(g for g in m.groups() if g is not None)


def code_writes_through_disk(code, through_link, write_code, program=None):
    """Whether interpreter `code` writes to a place `through_link` accepts (a literal that reaches the guarded tree only on disk, through a link the text never spells).

    A Python `program` that parses is judged by its write TARGETS through `shellscan.python_writes_to`, so a literal bound to a name on one line and written on another is followed, and a link that is only read is not a write (review f25b1360.1, .2, .3). Other code is read line by line with `write_code`, a name assigned from such a literal standing for it on a later line.
    """
    if program is not None:
        verdict = shellscan.python_writes_to(program, through_link)
        if verdict is not None:
            return verdict
    names = {
        m.group(1)
        for m in re.finditer(r"\b([A-Za-z_$][\w$]*)\s*=\s*([^\n=]*)", code)
        if any(through_link(lit) for lit in literals(m.group(2)))
    }
    for line in code.splitlines():
        if not write_code.search(line):
            continue
        if any(through_link(lit) for lit in literals(line)):
            return True
        if any(re.search(r"(?<![\w$])%s(?![\w$])" % re.escape(n), line) for n in names):
            return True
    return False
