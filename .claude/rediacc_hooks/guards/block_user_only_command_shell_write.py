"""Refuse a Bash command that puts `disable-model-invocation` into a slash command or skill file.

The shell half of `block_user_only_command` (operator ruling 2026-10-09: "no command or skill in this repo is user-only. Every slash command and skill must be invocable by the AI. This is enforced twice: a hook refuses the flag at write time, and a CI gate fails on it."). What counts as a command or skill file and as the key is `rediacc_hooks/model_invocation.py`, shared with the edit half and with `check:ci-model-invocable-commands`.

THE SHAPES, read by `shellscan`'s lexer rather than a regex over the text, so `echo` of the key to the terminal, `grep -rn` for it, and a commit message heredoc naming it all pass:

  1. A REDIRECT or `tee` into a command or skill file or directory. The text written (every heredoc body in the command and every `echo`/`printf`/`cat` argument) must not carry the key followed by a value.
  2. `sed -i` / `perl -i` on such a file. A substitution's REPLACEMENT and an `a`/`i`/`c` text command must not carry the key with a value; its PATTERN is what the edit removes, so `sed -i '/^disable-model-invocation:/d'` and `sed -i 's/^disable-model-invocation: true$//'` pass.
  3. `cp`/`mv`/`install`/`rsync`/`ln` ONTO such a path. The SOURCE is read from disk (a directory is walked for `.md` files) and judged by the shared frontmatter predicate exactly as the edit half judges a Write; a source the same command writes first is caught by shape 1's text.
  4. An INTERPRETER program (`python3 -c`, `python3 - <<EOF`, `node -e`, `perl -e`, `ruby -e`) that writes files, names a command or skill directory (or runs inside one), and whose source carries the key with a value.

SHAPES 1 AND 4 OVER-REFUSE, and say so. A heredoc or program that REMOVES the key names it too (`s.replace('disable-model-invocation: true\\n', '')`), and a static read cannot tell removal from insertion. The refusal points at the Edit tool, which `block_user_only_command` judges exactly (the whole resulting file), and at `sed -i '/^disable-model-invocation:/d'`, which passes here.

WHAT IT DOES NOT SEE: `git apply`/`patch`, a checkout of an old revision, a `sed -i` on a file that ALREADY carries the key (it judges what a command puts in, not what it leaves), and a key assembled at run time. `check:ci-model-invocable-commands` sees all of them, because it reads the tree rather than the command.

THE EXCEPTION LIST, from the operator's amendment of 2026-10-09, verbatim:

    it seems that we need an exceptionlist. I forgot about handoff command. let's include it into the exception list for CI & hook(s)

Read through `model_invocation.exceptions_for`, the one loader the edit half and the gate share. A LISTED file may carry the key exactly as listed: an overwrite of it (`>`, `tee`, a copy) is judged by `model_invocation.verdict` on the text written, while an append or interpreter write carrying the key is refused as for any other file, and an in-place `sed -i`/`perl -i` whose script names the key on a listed file is refused because the flag stays as the list says. ANY write to the list itself (a redirect, `tee`, `sed -i`, `truncate`, `dd of=`, a copy onto it, an interpreter program naming it) is refused: adding an exception is an operator decision, made with `!`. The list holds operator rulings only, never a BLOCKER entry.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`); it is judged by `test-block_user_only_command.py` (the shared harness for both halves) and against its own DEFECT.
"""

import os
import re

from rediacc_hooks import hookio, model_invocation, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 61

# The target test every shape goes through. With it answering no, every redirect, tee, sed -i, copy and interpreter write into a command directory passes.
DEFECT = ("    if not word:\n        return False", "    if True:\n        return False")

# A command naming neither the key nor a command or skill directory cannot write the key into one; most commands name neither, so the lexer is never started for them.
_PREFILTER = re.compile(
    r"%s|commands|skills|model-invocation-exceptions" % model_invocation.KEY_WORDS, re.IGNORECASE
)
WRITERS = ("echo", "printf", "cat")
INTERPRETERS = ("python", "node", "perl", "ruby", "deno", "bun", "tsx")
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|write_text|write_bytes|\.write\(|writeFileSync"
    r"|appendFileSync|os\.replace|os\.rename|shutil\.(copy|move)"
)
# The first command or skill path an interpreter program names, for the message.
# A match starts only at a word boundary: without the lookbehind every position of a long word was a start and the search was quadratic (2 MiB of `#` in a script read by path pinned the hook at 100% CPU, measured 3 s at 20,000 characters).
_NAMED_PATH = re.compile(
    r"(?<![^\s'\"])[^\s'\"]*\.claude/(?:commands|skills)[^\s'\"]*", re.IGNORECASE
)
_SED_SUB = re.compile(
    r"(?:^|[;\s{])s(?P<d>[^\w\s\\])(?P<pat>(?:\\.|(?!(?P=d)).)*)(?P=d)(?P<rep>(?:\\.|(?!(?P=d)).)*)(?P=d)"
)
_SED_TEXT = re.compile(r"(?:^|[;\s])(?:\d+|\$|/[^/]*/)?\s*[aic]\\?\s*(?P<text>[^;\n]*)")

MESSAGE = (
    "BLOCKED: this command breaks the model-invocation rule for a slash command or skill file (%s).\n"
    "\n"
    "The ruling: %s\n"
    "%s\n"
    "\n"
    "To REMOVE the key, use the Edit tool (block_user_only_command judges the whole resulting file),\n"
    "or `sed -i '/^disable-model-invocation:/d' <file>`. A shell program that merely names the key\n"
    "with a value is refused here, because a static read cannot tell removal from insertion.\n"
)

LIST_MESSAGE = (
    "BLOCKED: this command edits the model-invocation exception list (%s).\n"
    "\n"
    "Every entry is an operator ruling that lets one command or skill stay user-only.\n"
    "The ruling: %s\n"
    "%s\n"
)

_K = "disable-model-invocation"
_C = ".claude/commands/x.md"

EDGE_CASES = [
    ("a heredoc writing the key", "cat > %s <<'EOF'\n---\n%s: true\n---\nEOF" % (_C, _K)),
    ("an append of another spelling", "echo 'Disable_Model_Invocation: yes' >> %s" % _C),
    (
        "tee into a skill",
        "printf -- '---\\n%s: false\\n---\\n' | tee .claude/skills/s/SKILL.md" % _K,
    ),
    ("sed -i adding the key", "sed -i 's/^description:/%s: true\\ndescription:/' %s" % (_K, _C)),
    ("sed -i appending the key", "sed -i '1a %s: true' %s" % (_K, _C)),
    # #5077391c: xargs appends its feed, so under `-t` a fed word is a SOURCE (the commands directory once read as the source here, and a flagged command copied into a skill passed).
    (
        "xargs feeds a flagged command to cp -t a skill",
        "echo .claude/commands/handoff.md | xargs cp -t .claude/skills/demo",
    ),
    (
        "xargs feeds a flagged command to cp -t elsewhere",
        "echo .claude/commands/handoff.md | xargs cp -t /tmp",
    ),
    (
        "xargs feeds the exception list to cp -t elsewhere",
        "echo .ci/config/model-invocation-exceptions.json | xargs cp -t /tmp",
    ),
    (
        "xargs feeds cp the exception list as its destination",
        "echo /tmp/x.json .ci/config/model-invocation-exceptions.json | xargs cp",
    ),
    (
        "python writing the key",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('%s').write_text('---\\n%s: true\\n---\\n')\nEOF"
        % (_C, _K),
    ),
    ("after cd", "cd .claude/commands && echo '%s: on' >> x.md" % _K),
    ("inside sh -c", "sh -c \"echo '%s: 1' >> %s\"" % (_K, _C)),
    ("cp -t names where the copy lands", "cp -t .claude/skills .claude/commands/handoff.md"),
    # CONTROLS.
    ("sed -i deleting the key line", "sed -i '/^%s:/d' %s" % (_K, _C)),
    ("sed -i substituting the key away", "sed -i 's/^%s: true$//' %s" % (_K, _C)),
    ("echo to the terminal", "echo '%s: true is banned'" % _K),
    ("grep for the key", "grep -rn '%s' .claude/commands" % _K),
    ("a heredoc into a doc", "cat > docs/x.md <<'EOF'\n%s: true\nEOF" % _K),
    (
        "a commit message heredoc naming the key",
        "git commit -F - <<'EOF'\nfix: drop %s: true\nEOF" % _K,
    ),
    ("a command file without the key", "printf -- '---\\ndescription: x\\n---\\n' > %s" % _C),
    ("an unrelated redirect", "echo hello > /tmp/out.txt"),
    ("cp -t copies a command out", "cp -t /tmp .claude/commands/handoff.md"),
    # The exception list itself.
    (
        "a redirect into the exception list",
        "echo '{}' > .ci/config/model-invocation-exceptions.json",
    ),
    ("reading the exception list", "cat .ci/config/model-invocation-exceptions.json"),
]


def _is_target(word, cwd=None):
    if not word:
        return False
    if model_invocation.names_scope_dir(word):
        return True
    if cwd and not os.path.isabs(word):
        return model_invocation.names_scope_dir(str(cwd).rstrip("/") + "/" + word)
    return False


def _operands(argv):
    """`run.argv` is the ARGUMENTS, without the command name."""
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _run_operands(run, argv):
    """`_operands`, with a `find -exec` run's `{}` read as what the find walks (#503f0ba8)."""
    ops = _operands(argv)
    if run.launch is None or run.launch.launcher != "find":
        return ops
    out: list[str] = []
    for a in ops:
        out.extend(run.launch.starts if "{}" in a else [a])
    return out


def _lands(source, dest, into):
    """Where `source` lands under `dest`: inside it when the copy names a directory, else `dest` itself (a directory on disk is `_landing`'s to tell)."""
    return (
        dest.rstrip("/") + "/" + os.path.basename(source.rstrip("/"))
        if into or dest.endswith("/")
        else dest
    )


def _abs(path, run_cwd, cwd):
    base = cwd if run_cwd is None else os.path.join(cwd, run_cwd)
    return path if os.path.isabs(path) else os.path.normpath(os.path.join(base, path))


def _landing(source, dest_abs, dest_word, into=False):
    """Where a copied source file lands: inside `dest` when it is a directory (or written as one, or named by a target-directory option), else `dest` itself."""
    if into or os.path.isdir(dest_abs) or dest_word.endswith("/"):
        return os.path.join(dest_abs, os.path.basename(source.rstrip("/")))
    return dest_abs


def _copy_problems(source_abs, landing):
    """(landing path, refusals) for each `.md` a copy would put into a command or skill directory, judged by the shared `verdict` exactly as the edit half judges a Write."""
    pairs = [(source_abs, landing)]
    if os.path.isdir(source_abs):
        pairs = [
            (
                os.path.join(d, f),
                os.path.join(landing, os.path.relpath(os.path.join(d, f), source_abs)),
            )
            for d, _dirs, files in os.walk(source_abs)
            for f in files
            if f.lower().endswith(".md")
        ]
    for src, dst in pairs:
        if not model_invocation.in_scope(dst):
            continue
        try:
            with open(src, encoding="utf-8", errors="replace") as handle:
                text = handle.read()
        except OSError:
            continue
        rel, exceptions = model_invocation.exceptions_for(dst)
        problems = model_invocation.verdict(rel, text, exceptions)
        if problems:
            return dst, problems
    return None, []


def _listed(target_abs):
    """(rel, list) when `target_abs` is a file on the operator's exception list, else None."""
    if not model_invocation.in_scope(target_abs):
        return None
    rel, exceptions = model_invocation.exceptions_for(target_abs)
    return (rel, exceptions) if rel in exceptions.entries else None


def _list_write(runs, analysis, cmd, cwd):
    """A short description of the first write to the exception list itself, or ""."""
    for _op, target in analysis.writes:
        if model_invocation.is_exception_list(target):
            return "a redirect into %s" % target
    for run in runs:
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        operands = _run_operands(run, argv)
        prefix = str(run.cwd).rstrip("/") + "/" if run.cwd else ""
        on_list = [
            a
            for a in operands
            if model_invocation.is_exception_list(a)
            or model_invocation.is_exception_list(prefix + a)
        ]
        for target in run.writes:
            if model_invocation.is_exception_list(target) or (
                run.cwd
                and model_invocation.is_exception_list(str(run.cwd).rstrip("/") + "/" + target)
            ):
                return "a redirect into %s" % target
        # In place is sed's or perl's own option parse (review 3f53e99e.2): `sed -Ei`, `sed -ni` and `perl -pi -e` are in place.
        in_place = shellscan.in_place_edit(run) is not None
        if on_list and (name in ("tee", "truncate") or in_place):
            return "%s on %s" % (name, on_list[0])
        copies = shellscan.run_copies(run, None, cwd)
        if copies is not None:
            sources, dests, into = copies
            for dest in dests:
                for landed in [dest] + [_lands(src, dest, into) for src in sources]:
                    if any(
                        model_invocation.is_exception_list(p) for p in (landed, prefix + landed)
                    ):
                        return "%s onto %s" % (name, landed)
        if name == "dd" and any(
            a.startswith("of=") and model_invocation.is_exception_list(a[3:]) for a in argv
        ):
            return "dd of= the exception list"
        # A script run DIRECTLY by its shebang is the interpreter it names (#7ab88f34, as in block_review_file_shell_write): no interpreter word stands in the command, and the program would otherwise run unread.
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if name.startswith(INTERPRETERS):
            code, verdict, _kind = _program(run, cmd, cwd, _names_list)
            writes = WRITE_CODE.search(code) if verdict is None else verdict
            if "model-invocation-exceptions" in code and writes:
                return "a %s program writing the exception list" % name
    return ""


# A PYTHON PROGRAM IS JUDGED BY WHERE IT WRITES (coordinator finding 2026-10-11): `shellscan.python_writes_to` reads its write targets, so a program that reads the exception list, or names it beside a write to a scratch file, is not writing it. Node, perl, ruby and Python that does not parse keep the text reading, and so does a program run INSIDE a command directory, which writes there by any relative path.
def _names_list(value):
    return "model-invocation-exceptions" in value


def _names_dir(value):
    return model_invocation.names_scope_dir(value)


def _program(run, cmd, cwd, holds):
    """`(code, verdict)` for an interpreter run. `code` is its argv joined plus the program `shellscan.interpreter_program` reads from stdin or from a script passed BY PATH (#c4542b69: a script by path was not read at all, so one writing the key or the list passed where the same heredoc was refused); `verdict` is `shellscan.python_writes_to` over a python program, None for any other interpreter or a program that does not parse."""
    text, kind = shellscan.interpreter_program(run, cmd, cwd)
    code = " ".join(run.argv)
    if kind in ("stdin", "file"):
        code += "\n" + text
    if kind not in ("inline", "stdin", "file") or not re.match(
        r"^python[0-9.]*$", run.name.rsplit("/", 1)[-1]
    ):
        return code, None, kind
    return code, shellscan.python_writes_to(text, holds), kind


def _offending(cmd, cwd):
    """(kind, description) of the first refused write, kind "list" or "flag", or None."""
    analysis = shellscan._analyse(cmd)
    # A nested heredoc's offsets index its payload, not `cmd` (#78afdc0b): the body is read from its own text.
    bodies = shellscan.heredoc_bodies(cmd)
    runs = shellscan.every_run(cmd)
    listed_write = _list_write(runs, analysis, cmd, cwd)
    if listed_write:
        return "list", listed_write
    written = "\n".join(
        bodies + [a for r in runs if r.name.rsplit("/", 1)[-1] in WRITERS for a in r.argv]
    )
    flagged = model_invocation.flag_in_text(written)
    appends = {target for op, target in analysis.writes if op in (">>", "&>>")}

    def redirect_refusal(target, run_cwd, appending):
        """A refusal for a write of `written` into `target`, or "". A LISTED file overwritten whole is judged by `verdict` on the text written; any other write carrying the key is refused."""
        if not _is_target(target, run_cwd):
            return ""
        listed = None if appending else _listed(_abs(target, run_cwd, cwd))
        if listed is not None:
            problems = model_invocation.verdict(listed[0], written, listed[1])
            return "a write of %s: %s" % (target, "; ".join(problems)) if problems else ""
        return "a write of the key into %s" % target if flagged else ""

    for run in runs:
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        operands = _run_operands(run, argv)
        for target in run.writes:
            why = redirect_refusal(target, run.cwd, target in appends)
            if why:
                return "flag", why
        if name == "tee":
            appending = "-a" in argv or "--append" in argv
            for target in operands:
                why = redirect_refusal(target, run.cwd, appending)
                if why:
                    return "flag", why
        # In place is sed's or perl's own option parse (review 3f53e99e.2): `sed -Ei`, `sed -ni` and `perl -pi -e` rewrote the key into a command file unrefused. Its scripts join the non-option words, so the scripts read can only grow.
        edit = shellscan.in_place_edit(run)
        hits = [a for a in operands if _is_target(a, run.cwd)]
        if edit is not None and hits:
            exprs = edit[0] + [
                a for a in argv if not a.startswith("-") and not _is_target(a, run.cwd)
            ]
            for expr in exprs:
                added = "\n".join(m.group("rep") for m in _SED_SUB.finditer(expr))
                if not _SED_SUB.search(expr):
                    added = "\n".join(m.group("text") for m in _SED_TEXT.finditer(expr))
                if model_invocation.flag_in_text(added):
                    return "flag", "%s -i adding the key to %s" % (name, hits[0])
            # A listed file keeps its key exactly as the list says, so an in-place edit whose script names the key is refused on it: that is a removal or a rewrite of the flag.
            listed = [h for h in hits if _listed(_abs(h, run.cwd, cwd)) is not None]
            if listed and any(model_invocation.MENTION.search(e) for e in exprs):
                return (
                    "flag",
                    "%s -i rewriting the key of %s, which the exception list says stays"
                    % (
                        name,
                        listed[0],
                    ),
                )
        # `cwd` places a relative fed glob in the run's own directory (#e5b0540a).
        copies = shellscan.run_copies(run, None, cwd)
        for dest in copies[1] if copies is not None else []:
            if not _is_target(dest, run.cwd):
                continue
            dest_abs = _abs(dest, run.cwd, cwd)
            for source in copies[0]:
                source_abs = _abs(source, run.cwd, cwd)
                landing, problems = _copy_problems(
                    source_abs, _landing(source_abs, dest_abs, dest, copies[2])
                )
                if problems:
                    return "flag", "%s of %s onto %s: %s" % (
                        name,
                        source,
                        landing,
                        "; ".join(problems),
                    )
        # A script run DIRECTLY by its shebang is the interpreter it names (#7ab88f34, as in block_review_file_shell_write): no interpreter word stands in the command, and the program would otherwise run unread.
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if name.startswith(INTERPRETERS):
            in_dir = _is_target(".", run.cwd)
            code, verdict, kind = _program(run, cmd, cwd, _names_dir)
            # A program this hook cannot read (review b922f15c.1, .4): the same command wrote the script from an unknown source, or it is too large to read. The pre-filter already matched, so it is refused rather than run unread.
            if kind == "unjudgeable":
                return "flag", "a %s program this hook cannot read (%s)" % (
                    name,
                    shellscan.UNJUDGEABLE_REASON,
                )
            if in_dir:
                verdict = None
            if verdict is None:
                names_dir = _NAMED_PATH.search(code) is not None or in_dir
                verdict = bool(names_dir and WRITE_CODE.search(code))
            if verdict and model_invocation.flag_in_text(code):
                named = _NAMED_PATH.search(code)
                return "flag", "a %s program writing the key into %s" % (
                    name,
                    named.group(0) if named else "a file under %s" % run.cwd,
                )
    return None


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd:
        return hookio.ALLOW
    try:
        cwd = ev.default(("cwd",), str(hookio.repo_root()))
    except RuntimeError:
        cwd = ev.cwd
    # A script run by path names the key or the directory in its own text, not the command's (#c4542b69), so the pre-filter reads those scripts too; the lexer starts only when an interpreter is named.
    if not _PREFILTER.search(cmd) and not any(
        _PREFILTER.search(text) for text in shellscan.interpreter_scripts(cmd, cwd)
    ):
        return hookio.ALLOW
    found = _offending(cmd, cwd)
    if found is None:
        return hookio.ALLOW
    kind, what = found
    template = LIST_MESSAGE if kind == "list" else MESSAGE
    ev.warn_raw(template % (what, model_invocation.RULING, model_invocation.OPERATOR_LINE))
    return hookio.DENY
