"""Refuse a Bash command that writes a NEW inline lint or type suppression marker into a code file.

The shell half of `block_suppressions.py` (operator ruling 2026-10-08: inline suppressions are banned, by hook and by CI). The edit tools are judged there; the same insertion through the shell is judged here, through the same scanner (`rediacc_ci.quality.inline_suppressions`).

THE SHAPES, read by `shellscan`'s lexer rather than a regex over the text, so `echo "noq[a]"` to the terminal, a commit message heredoc, and `grep -rn noq[a]` all pass:

  1. A REDIRECT or `tee` into a code file (`cat > a.py <<EOF`, `echo ... >> a.sh`, `printf ... | tee a.ts`). The text written (the heredoc bodies and the writer's own arguments) is counted in the target's language and compared with the file on disk: an overwrite must not raise any (kind, code) count above the file's current one, and an append must not carry any marker at all.
  2. `sed -i` / `perl -i` on a code file. A substitution may not put more markers in its REPLACEMENT than its PATTERN removes, and an `a`/`i`/`c` text command may not carry one.
  3. An INTERPRETER program (`python3 -c`, `python3 - <<EOF`, `node -e`, `perl -e`, `ruby -e`, or a script passed BY PATH) that writes files and whose source holds a marker anywhere. Its STRINGS are what it writes, so the source is read RAW, strings included.

A SCRIPT BY PATH IS READ LIKE A HEREDOC (#f3f36655). `python3 scratch/edit.py` wrote a marker unrefused on 2026-10-11 while the same program through `python3 - <<EOF` was refused: the command text named no marker, so the pre-filter allowed it before the lexer started. The script's own text is now its program, with two limits. A script TRACKED in this checkout is not read: its markers are reviewed code the CI gate already judges, and reading them would refuse every run of `worklist.py` (50 markers, 94 write calls). And a script that cannot be read at hook time FAILS OPEN: one written earlier in the same command by a redirect or heredoc is judged by shape 1 as it is written, one that does not exist makes the interpreter fail, and refusing every chained `make && python3 out.py` would teach routing around the guard while `check:ci-inline-suppressions` reads the tree either way.

SHAPE 3 OVER-REFUSES, and says so. A program that REMOVES markers names them too, and a static read cannot tell `s.replace(MARKER, "")` from `s.replace("", MARKER)`. The refusal names the Edit tool, which `block_suppressions.py` judges exactly (the whole file before and after). A removal script that must run in the shell spells the token with a character class (`noq[a]`), the convention both guards' sources use.

EVERY HEREDOC IN THE COMMAND IS READ AS CONTENT for a redirect or `tee`, because the lexer records heredoc bodies without the command that consumes them. A command that writes a code file AND carries an unrelated heredoc naming a marker (a commit message, say) is refused; split it into two commands.

WHAT IT DOES NOT SEE: `cp`/`mv` of a file that already carries markers, `git apply`/`patch`, a script it cannot read at hook time, and code assembled at run time. `check:ci-inline-suppressions` sees all of them, because it reads the tree rather than the command.

THIS GUARD HAS NO BASH TWIN (`OWN_SUITE = True`); it is judged by `test-block_suppressions.py` (the shared harness for both halves) and against its own DEFECT.

IT FAILS OPEN, LOUDLY, as its edit sibling does: a scanner that cannot be imported leaves the command allowed and stderr saying it went UNEXAMINED.
"""

import importlib
import os
import pathlib
import re
import sys

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
INTERPRETERS = ("python", "node", "perl", "ruby", "deno", "bun", "tsx")
INPLACE = ("sed", "gsed", "perl")
WRITERS = ("echo", "printf", "cat")
WRITE_CODE = re.compile(
    r"open\([^)]*,\s*(mode\s*=\s*)?['\"][^'\"]*[wax+]|write_text|write_bytes|\.write\(|writeFileSync"
    r"|appendFileSync|os\.replace|os\.rename|shutil\.(copy|move)"
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
    return ops


# The interpreter options that put the program on the command line, so no operand is a script.
_INLINE = ("-c", "-e", "-E", "-p", "--eval", "--print")
# The largest script read; a bigger file is not a hand-written edit script.
_SCRIPT_MAX = 1 << 20


def _script_text(argv, run_cwd, cwd):
    """The program text of a script an interpreter run executes BY PATH, or None: an inline program (`-c`, `-e`, stdin), a module (`-m`), a file it cannot read, or a file this checkout tracks (see the module docstring)."""
    if any(a in _INLINE or (a[:2] in ("-c", "-e") and len(a) > 2) for a in argv) or "-m" in argv:
        return None
    ops = _operands(argv)
    if not ops or ops[0] == "-":
        return None
    path = pathlib.Path(_abs(ops[0], run_cwd, cwd))
    try:
        if not path.is_file() or path.stat().st_size > _SCRIPT_MAX:
            return None
        tracked = hookio.git_out(
            ["ls-files", "--error-unmatch", "--", path.name], cwd=str(path.parent), want_rc=True
        )
        if tracked is not None:
            return None
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return None


def _scripts(cmd, cwd):
    """The program text of every script an interpreter in `cmd` runs by path (`_script_text`); the lexer runs only when an interpreter is named at all."""
    if not re.search(r"python|node|perl|ruby|deno|bun|tsx", cmd):
        return []
    out = []
    for run in shellscan.every_run(cmd):
        if run.name.rsplit("/", 1)[-1].startswith(INTERPRETERS):
            text = _script_text(list(run.argv), run.cwd, cwd)
            if text is not None:
                out.append(text)
    return out


def _render(engine, grew):
    return ", ".join(engine.render_marker(kind, code) for kind, code, _b, _a in grew)


def _offending(engine, cmd, cwd):
    """A one-line description of the first marker-adding write in `cmd`, or ""."""
    analysis = shellscan._analyse(cmd)
    bodies = [
        cmd[doc.body_start : doc.body_end]
        for doc in analysis.heredocs
        if doc.body_start is not None and doc.body_end is not None
    ]
    appends = {target for op, target in analysis.writes if op in (">>", "&>>")}
    # What a `tee` writes is its UPSTREAM stage's output; read as every writer's arguments in the command, plus the heredocs.
    # THE LAUNCHED COMMANDS TOO (#503f0ba8): a `sed -i` or an interpreter that `find -exec` or `npx -c` starts writes the same files, so the runs are `shellscan.every_run`.
    runs = shellscan.every_run(cmd)
    piped = "\n".join(
        bodies + [a for r in runs if r.name.rsplit("/", 1)[-1] in WRITERS for a in r.argv]
    )
    for run in runs:
        name = run.name.rsplit("/", 1)[-1]
        argv = list(run.argv)
        targets = [(t, "\n".join(bodies + (argv if name in WRITERS else []))) for t in run.writes]
        if name == "tee":
            targets += [(t, piped) for t in _operands(argv)]
        for target, content in targets:
            language = _language(engine, target, content)
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
        in_place = any(a == "-i" or a.startswith(("-i", "--in-place")) for a in argv)
        if (
            name in INPLACE
            and in_place
            and any(engine.language_for(a) for a in _run_operands(run, argv))
        ):
            exprs = [a for a in argv if not a.startswith("-") and not engine.language_for(a)]
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
        if name.startswith(INTERPRETERS):
            ops = _operands(argv)
            code = " ".join(argv)
            if not ops or ops[0] == "-":
                code += "\n" + "\n".join(bodies)
            script = _script_text(argv, run.cwd, cwd)
            if script is not None:
                code += "\n" + script
            if WRITE_CODE.search(code):
                grew = engine.growth(engine.count_any_language(""), engine.count_any_language(code))
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
        for text in _scripts(cmd, ev.default(("cwd",), str(hookio.repo_root())))
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
