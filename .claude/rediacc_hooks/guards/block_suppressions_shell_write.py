"""Refuse a Bash command that writes a NEW inline lint or type suppression marker into a code file.

The shell half of `block_suppressions.py` (operator ruling 2026-10-08: inline suppressions are banned, by hook and by CI). The edit tools are judged there; the same insertion through the shell is judged here, through the same scanner (`rediacc_ci.quality.inline_suppressions`).

THE SHAPES, read by `shellscan`'s lexer rather than a regex over the text, so `echo "noq[a]"` to the terminal, a commit message heredoc, and `grep -rn noq[a]` all pass:

  1. A REDIRECT or `tee` into a code file (`cat > a.py <<EOF`, `echo ... >> a.sh`, `printf ... | tee a.ts`). The text written (the heredoc bodies and the writer's own arguments) is counted in the target's language and compared with the file on disk: an overwrite must not raise any (kind, code) count above the file's current one, and an append must not carry any marker at all.
  2. `sed -i` / `perl -i` on a code file. A substitution may not put more markers in its REPLACEMENT than its PATTERN removes, and an `a`/`i`/`c` text command may not carry one.
  3. An INTERPRETER program (`python3 -c`, `python3 - <<EOF`, `node -e`, `perl -e`, `ruby -e`, or a script passed BY PATH) that writes files and whose source holds a marker anywhere. Its STRINGS are what it writes, so the source is read RAW, strings included.

A SCRIPT BY PATH IS READ LIKE A HEREDOC (#f3f36655). `python3 scratch/edit.py` wrote a marker unrefused on 2026-10-11 while the same program through `python3 - <<EOF` was refused: the command text named no marker, so the pre-filter allowed it before the lexer started. The script's own text is now its program, with two limits. A script TRACKED in this checkout is not read: its markers are reviewed code the CI gate already judges, and reading them would refuse every run of `worklist.py` (50 markers, 94 write calls). And a script that cannot be read at hook time FAILS OPEN: one written earlier in the same command by a redirect or heredoc is judged by shape 1 as it is written, one that does not exist makes the interpreter fail, and refusing every chained `make && python3 out.py` would teach routing around the guard while `check:ci-inline-suppressions` reads the tree either way.

SHAPE 3 OVER-REFUSES, and says so. A program that REMOVES markers names them too, and a static read cannot tell `s.replace(MARKER, "")` from `s.replace("", MARKER)`. The refusal names the Edit tool, which `block_suppressions.py` judges exactly (the whole file before and after). A removal script that must run in the shell spells the token with a character class (`noq[a]`), the convention both guards' sources use.

A WRITER'S OWN TEXT IS ITS CONTENT (review fc3f376a.2): `echo`, `printf`, `tee` and a file-less `cat` write their words as bash expands them plus their own heredoc, here-string or piped words (`shellscan.writer_text`), and a text the walk cannot expand is an unknown write, refused. Any other redirect into a code file is read with EVERY heredoc in the command, because its content is not on the command line; a command that writes a code file that way AND carries an unrelated heredoc naming a marker (a commit message, say) is refused, so split it into two commands.

WHAT IT DOES NOT SEE: `cp`/`mv` of a file that already carries markers, `git apply`/`patch`, a script it cannot read at hook time, and code assembled at run time. `check:ci-inline-suppressions` sees all of them, because it reads the tree rather than the command.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`); it is judged by `test-block_suppressions.py` (the shared harness for both halves) and against its own DEFECT.

IT FAILS OPEN, LOUDLY, as its edit sibling does: a scanner that cannot be imported leaves the command allowed and stderr saying it went UNEXAMINED.
"""

import importlib
import io
import os
import pathlib
import re
import sys
import tokenize

from rediacc_hooks import hookio, shellscan, syspath

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 58

# Planting `False` here drops shape 1, the redirect: `cat > a.py <<EOF` with a marker in the body goes through, and the redirect cases flip.
DEFECT = ("if language is not None:", "if False:")

# The cheap pre-filter: a command that names none of these cannot write a marker, and most commands do not, so the lexer is never started for them. Character classes keep the literal tokens out of this file.
_PREFILTER = re.compile(
    r"noq[a]|type\s*:\s*ignor[e]|pyright|pylint|mypy\s*:|@ts-|eslint-disabl[e]|biome-ignor[e]"
    r"|nolin[t]|lint:ignor[e]|shellcheck|hadolint",
    re.IGNORECASE,
)
INTERPRETERS = shellscan.INTERPRETER_NAMES
WRITERS = ("echo", "printf", "cat")
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|write_text|write_bytes|\.write\(|writeFileSync"
    r"|appendFileSync|os\.replace|os\.rename|shutil\.(copy|move)"
)
# A program that RUNS text it was handed (review 13505e0b.2): for one of these the stdin is program text as well as data.
# THE RULE (648366c8.1): stdin is program text unless the source can be classified as not evaluating it. In Python, Perl and Ruby an evaluator is ordinarily reached by a NAME, so a source naming none of `_RUNS_TEXT` is classified. That is a reading of the plain spelling, not a proof: a name assembled at run time (`getattr(__builtins__, 'ex' + 'ec')`) is not seen, and such a program's stdin is read as data. JavaScript has plain spellings that name nothing a list can hold (a bare `Function(...)` call, `import('data:...')`, `x.constructor.constructor(...)`), beside the ones the list does hold (`new Function`), so no JavaScript program is classified and every one of `_UNCLASSIFIED` that is fed anything is read as running it.
_UNCLASSIFIED = ("node", "deno", "bun", "tsx")
_RUNS_TEXT = re.compile(
    r"\b(?:exec|eval|execfile|compile|instance_eval|class_eval|module_eval)\b|new\s+Function\b"
    r"|\brunIn(?:This|New)?Context\b|\brunpy\b|\bcode\.interact|\bInteractiveConsole\b"
)
_SED_SUB = re.compile(
    r"(?:^|[;\s{])s(?P<d>[^\w\s\\])(?P<pat>(?:\\.|(?!(?P=d)).)*)(?P=d)(?P<rep>(?:\\.|(?!(?P=d)).)*)(?P=d)"
)
_SED_TEXT = re.compile(r"(?:^|[;\s])(?:\d+|\$|/[^/]*/)?\s*[aic]\\?\s*(?P<text>[^;\n]*)")

UNEXAMINED = (
    "block-suppressions-shell-write: the inline-suppression scanner could not be loaded (%s); "
    "this command passed UNEXAMINED. CI (check:ci-inline-suppressions) still judges the tree."
)

MESSAGE = """BLOCKED: this command writes a NEW inline lint/type suppression marker (%s).
Inline suppressions are banned (operator ruling 2026-10-08).

  %s

Instead:
  * Fix the code the linter is pointing at.
  * For a deliberate, project-wide exception, add a per-file entry to the linter's own
    config (pyproject.toml per-file-ignores, biome.json overrides, .golangci.yml) with a
    BLOCKER: reason, per docs/agent-reference/suppressions.md.
  * To edit a file that already carries markers, use the Edit tool: it compares the whole
    file before and after, so keeping or removing an existing marker passes. A shell
    program cannot be read that precisely, which is why one that merely NAMES a marker
    is refused here.
"""

_NQ = "# noq" + "a"
_TSI = "@ts-ignor" + "e"
_SC = "# shellcheck disabl" + "e"

EDGE_CASES = [
    (
        "a heredoc writing a python file with a marker",
        "cat > /r/x.py <<'EOF'\nimport os  %s: F401\nEOF" % _NQ,
    ),
    ("an append to a shell script", "echo '%s=SC2086' >> scripts/x.sh" % _SC),
    ("tee into a TS file", "printf '// %s\\n' | tee src/a.ts" % _TSI),
    ("sed -i adding a marker", "sed -i 's/x = 1/x = 1  %s: B010/' a.py" % _NQ),
    ("sed -i appending a marker line", "sed -i '/^import/a %s: E402' a.py" % _NQ),
    (
        "python -c writing a marker",
        "python3 -c \"open('a.py','a').write('x = 1  %s: B010')\"" % _NQ,
    ),
    (
        "python heredoc writing a marker",
        "python3 - <<'EOF'\nimport pathlib\npathlib.Path('a.py').write_text('x = 1  %s: B010\\n')\nEOF"
        % _NQ,
    ),
    ("inside sh -c", "sh -c \"echo 'x = 1  %s: B010' >> a.py\"" % _NQ),
    # CONTROLS.
    ("sed -i removing a marker", "sed -i 's/  %s: B010//' a.py" % _NQ),
    ("echo to the terminal", "echo 'never write %s: B010'" % _NQ),
    (
        "a commit message heredoc naming the marker",
        "git commit -F - <<'EOF'\nfix: drop the %s: B010 swaps\nEOF" % _NQ,
    ),
    (
        "a heredoc into a Markdown file",
        "cat > docs/x.md <<'EOF'\nNever write `%s: B010`.\nEOF" % _NQ,
    ),
    ("grep for markers", "grep -rnP '%s' .ci" % _NQ),
    (
        "a python program that only reads",
        "python3 -c \"print(open('a.py').read().count('%s'))\"" % _NQ,
    ),
    ("an unrelated redirect", "echo hello > /tmp/out.txt"),
    ("a heredoc python file with no marker", "cat > /r/x.py <<'EOF'\nimport os\nEOF"),
    # #503f0ba8: a command `npx` or `find -exec` LAUNCHES is judged as a run of its own.
    (
        "sed -i launched by find -exec on the *.py it names",
        "find . -name '*.py' -exec sed -i 's/$/  %s: E501/' {} +" % _NQ,
    ),
    ("a launched grep only reads", "find . -name '*.py' -exec grep -n '%s' {} +" % _NQ),
]


def _engine():
    root = hookio.repo_root()
    cipath = str(pathlib.Path(root) / ".ci")
    inserted = syspath.on_sys_path(cipath)
    try:
        module = importlib.import_module("rediacc_ci.quality.inline_suppressions")
    finally:
        if inserted and cipath in sys.path:
            sys.path.remove(cipath)
    return root, module


def _language(engine, target, content):
    head = content.lstrip("\n").split("\n", 1)[0]
    return engine.language_for(target, head)


def _abs(target, run_cwd, cwd):
    # A kept `<name>/..` pair is read where the disk resolves it (review 2925782e.1), so the baseline counted is the file the write replaces.
    run_cwd = shellscan.write_directory(run_cwd, cwd)
    base = (
        cwd
        if run_cwd is None
        else (run_cwd if os.path.isabs(run_cwd) else os.path.join(cwd, run_cwd))
    )
    return target if os.path.isabs(target) else os.path.normpath(os.path.join(base, target))


def _disk_counts(engine, path, language):
    try:
        with open(path, encoding="utf-8", errors="surrogateescape") as handle:
            return engine.count_markers(handle.read(), language)
    except OSError:
        return engine.count_markers("", language)


def _operands(argv):
    """`run.argv` is the ARGUMENTS, without the command name."""
    return [a for a in argv if not (a.startswith("-") and len(a) > 1)]


def _run_operands(run, argv):
    """`_operands`, with a `find -exec` run's `{}` read as what the find names (#503f0ba8): `find . -name '*.py' -exec sed -i ... {} +` edits the `*.py` files, so the find's own words (`run.feed`) stand in for `{}`. Every word counts, which over-reads, never under-reads, the files touched."""
    ops = _operands(argv)
    if (
        run.launch is not None
        and run.launch.launcher == "find"
        and run.feed
        and any("{}" in a for a in ops)
    ):
        ops = [a for a in ops if "{}" not in a] + run.feed.split()
    else:
        # What xargs reads becomes this command's words, appended or put where its marker stands, whatever the marker is (`shellscan.xargs_fed_operands`): `echo a.py | xargs sed -i ...` named no file among sed's own words and was allowed.
        ops = shellscan.xargs_fed_operands(run, ops)
    return ops


def _python_strings(source):
    """The text of every string literal in a python source, f-string parts included, or None when it does not tokenize (then the whole source is read, the safe direction)."""
    middle = getattr(tokenize, "FSTRING_MIDDLE", None)
    try:
        out = [
            tok.string
            for tok in tokenize.generate_tokens(io.StringIO(source).readline)
            if tok.type == tokenize.STRING or (middle is not None and tok.type == middle)
        ]
    except (tokenize.TokenError, SyntaxError, IndentationError):
        return None
    return "\n".join(out)


def _render(engine, grew):
    return ", ".join(engine.render_marker(kind, code) for kind, code, _b, _a in grew)


_redirects = shellscan.analysis_redirects


def _offending(engine, cmd, cwd):
    """A one-line description of the first marker-adding write in `cmd`, or ""."""
    analysis = shellscan._analyse(cmd)
    # A nested heredoc's offsets index its payload, not `cmd` (#78afdc0b): the body is read from its own text.
    bodies = shellscan.heredoc_bodies(cmd)
    appends = {target for op, target in _redirects(analysis) if op in (">>", "&>>")}
    # What a `tee` writes is its UPSTREAM stage's output; read as every writer's arguments in the command, plus the heredocs.
    # THE LAUNCHED COMMANDS TOO (#503f0ba8): a `sed -i` or an interpreter that `find -exec` or `npx -c` starts writes the same files, so the runs are `shellscan.every_run`.
    runs = shellscan.every_run(cmd)
    for run in runs:
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        # A writer's text as bash hands it over (`shellscan.writer_text`, review fc3f376a.2): `F='... marker'; echo "$F" >> a.py` wrote the marker while its argv read `"$F"`. A pure writer whose text is unexpanded (`$(...)`, an unset variable, an unquoted heredoc's `$`) is an unknown write. `cat other.py > a.py` copies, which this guard does not see (module docstring). Of WRITERS, `echo` and `printf` are always pure and `cat` is pure with no file operand; a `cat` WITH one is read with every heredoc in the command, and loses only its file NAMES from the content, which it never writes (review 094dea3b.3).
        pure = name in ("echo", "printf", "tee") or (
            name == "cat" and not any(not a.startswith("-") for a in argv)
        )
        written = shellscan.writer_text(run, cmd) if pure else ""
        # A pure writer's text carries its own heredoc or feed; any other redirect (`python3 gen.py > a.py`) is read with every heredoc in the command, as before.
        content = (written or "") if pure else "\n".join(bodies)
        targets = shellscan.redirect_targets(run) + (_operands(argv) if name == "tee" else [])
        for target in targets:
            language = _language(engine, target, content)
            if language is not None and pure and written is None:
                return "a write of text this hook cannot read into %s (%s)" % (
                    target,
                    shellscan.UNJUDGEABLE_REASON,
                )
            if language is not None:
                new = engine.count_markers(content, language)
                appending = target in appends or (name == "tee" and "-a" in argv)
                old = (
                    engine.count_markers("", language)
                    if appending
                    else _disk_counts(engine, _abs(target, run.cwd, cwd), language)
                )
                grew = engine.growth(old, new)
                if grew:
                    return "%s into %s" % (_render(engine, grew), target)
        # In place is sed's or perl's own option parse (review 3f53e99e.2 sweep): `sed -Ei` and `perl -pi -e` are in place.
        edit = shellscan.in_place_edit(run)
        if edit is not None and any(engine.language_for(a) for a in _run_operands(run, argv)):
            exprs = edit[0] + [
                a for a in argv if not a.startswith("-") and not engine.language_for(a)
            ]
            for expr in exprs:
                pattern = "\n".join(m.group("pat") for m in _SED_SUB.finditer(expr))
                added = "\n".join(m.group("rep") for m in _SED_SUB.finditer(expr))
                if not _SED_SUB.search(expr):
                    added = "\n".join(m.group("text") for m in _SED_TEXT.finditer(expr))
                grew = engine.growth(
                    engine.count_any_language(pattern), engine.count_any_language(added)
                )
                if grew:
                    return "%s -i adding %s" % (name, _render(engine, grew))
        # A script run DIRECTLY by its shebang is the interpreter it names (#7ab88f34, as in block_review_file_shell_write): no interpreter word stands in the command, and the program would otherwise run unread.
        shebang = shellscan.shebang_interpreter(run, cwd)
        if shebang and shebang.startswith(INTERPRETERS) and not name.startswith(INTERPRETERS):
            name = shebang
        if name.startswith(INTERPRETERS):
            # A script by path is read like the heredoc above, under `shellscan.interpreter_program`'s rules (tracked exempt, unreadable fails open).
            script, kind = shellscan.interpreter_program(run, cmd, cwd)
            code = " ".join(argv)
            # Whether the program arrives on stdin is the interpreter's own option parse (#a2599946). This guard asked it of the first word not starting with `-`, so an option's value hid the `-`: `python3 -W ignore - <<EOF` and `deno run - <<EOF` with a marker in the body were allowed (rc 0, 2026-10-15 at 2f3430b60).
            if kind == "stdin":
                code += "\n" + script
            # A program this hook cannot read (review b922f15c.1, .4) is refused rather than run unread; the pre-filter already matched.
            if kind == "unjudgeable":
                return "a %s program this hook cannot read (%s)" % (
                    name,
                    shellscan.UNJUDGEABLE_REASON,
                )
            # A script read by PATH is judged by what it can write, not by its own comments (coordinator 2026-10-11: an edited tracked test whose source carries a lint marker comment, writing fixture files, was refused): a python script's markers count only inside its string literals; its write calls are still read from the whole source.
            marked = code
            if kind == "file":
                code += "\n" + script
                literals = _python_strings(script) if name.startswith("python") else None
                marked = code if literals is None else " ".join(argv) + "\n" + literals
            # What arrives on the program's stdin is text it can write out too (review 094dea3b.2: `python3 copy_stdin.py <<EOF` with a marker in the heredoc was not judged). It is DATA, so it is read for markers and never for write calls (7837d22e.2: a stdin line holding `open(` made a script that writes nothing a writer), and it is read as bash hands it over (7837d22e.1: `M='<marker>'; python3 gen.py <<EOF` with a body line `$M`); a part the walk cannot expand makes it unknown, which is refused. A program read FROM stdin has no other stdin, and its heredoc is already in `code`.
            # STDIN IS NOT ONLY DATA for a program that runs text it is handed (`exec(sys.stdin.read())`, 13505e0b.2) and for every JavaScript program, which is never classified (`_UNCLASSIFIED`, 648366c8.1): its stdin is then read for write calls as well, and stdin the walk cannot expand is a program this hook cannot read.
            fed: str | None = ""
            program = code
            if kind in ("file", "inline") and run.feed:
                fed = shellscan.stdin_text(run, cmd)
                if name.startswith(_UNCLASSIFIED) or _RUNS_TEXT.search(code):
                    if fed is None:
                        return (
                            "a %s program that runs its stdin, fed text this hook cannot read (%s)"
                            % (
                                name,
                                shellscan.UNJUDGEABLE_REASON,
                            )
                        )
                    program += "\n" + fed
            if WRITE_CODE.search(program):
                if fed is None:
                    return "a %s program that writes files, fed text this hook cannot read (%s)" % (
                        name,
                        shellscan.UNJUDGEABLE_REASON,
                    )
                marked += "\n" + fed
                grew = engine.growth(
                    engine.count_any_language(""), engine.count_any_language(marked)
                )
                if grew:
                    return "a %s program that writes files and names %s" % (
                        name,
                        _render(engine, grew),
                    )
    return ""


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd:
        return hookio.ALLOW
    # A script run by path names no marker in the command text (#f3f36655), so such a command is let through only when a script it runs names one; the scanner is loaded for nothing else.
    if not _PREFILTER.search(cmd) and not any(
        _PREFILTER.search(text)
        for text in shellscan.interpreter_scripts(
            cmd, ev.default(("cwd",), str(hookio.repo_root()))
        )
    ):
        return hookio.ALLOW
    try:
        root, engine = _engine()
    except (ImportError, OSError, RuntimeError, SyntaxError) as exc:
        ev.warn(UNEXAMINED % exc)
        return hookio.ALLOW
    what = _offending(engine, cmd, ev.default(("cwd",), str(root)))
    if not what:
        return hookio.ALLOW
    ev.warn_raw(MESSAGE % (what, cmd.split("\n", 1)[0][:160]))
    return hookio.DENY
