"""block_unscoped_formatter_run: refuse a writing formatter or fixer whose path set may be empty or is the whole tree.

THE MISTAKE, 2026-10-07 (worklist #ab17ccc1). The lead ran

    R=ruff; $R format $( $R format --check <6 files> 2>&1 | grep 'Would reformat' | sed 's/Would reformat: //')

The grep matched nothing, the substitution was empty, and `ruff format` ran with NO path, which ruff reads as "the current directory". It reformatted 28 files across the whole repo, 26 of them markdown docs whose code blocks ruff rewrapped, all outside the work, and the session repaired it by writing HEAD content back.
Nothing in the command was wrong on its face: the path list was a pipeline that happened to print nothing. That is the shape this guard refuses, BEFORE the run, because afterwards the only repair is a revert that a shared tree makes dangerous (CLAUDE.md rule 1 forbids `git checkout/restore` here).

THE RULE. A run of a formatter in WRITE mode must name at least one path that cannot vanish, and no path it names may be a repository root.

  * NO PATH AT ALL is refused. `ruff format`, `ruff check --fix`, `eslint --fix` (v9), `biome format --write` and `golangci-lint run --fix` all read "no path" as the current directory. black, prettier, gofmt and shfmt instead error or read stdin; the rule is applied uniformly anyway, because which tools treat "nothing" as "everything" changes between versions and a guard that tracked it per tool would be wrong the day a tool changed its mind.
  * A PATH THAT MAY VANISH is an UNQUOTED expansion with nothing literal beside it: `$(...)`, a backtick span, `$list`, `${list}`, and `"$@"` / `"${arr[@]}"` even quoted. Word splitting turns an empty result into zero words, so `ruff format $(cmd)` IS `ruff format` whenever cmd prints nothing. A QUOTED scalar expansion (`"$f"`, `"$(cmd)"`) is always exactly one word; empty, it is a path the tool refuses (`ruff format ""` exits 2, measured 2026-10-07, ruff 0.16.1), never an empty set.
  * `--` DOES NOT HELP, and the refusal message says so: `ruff format -- $(cmd)` with an empty substitution is `ruff format --`, which is still the whole tree. The safe forms are explicit paths, or a variable tested non-empty before use (`[ -n "$files" ] && ruff format -- $files`), or `${files:?}`, which makes bash abort on an empty value. Those last two are recognised here; so is a `for f in ...` loop variable, which word splitting never leaves empty.
  * `xargs` WITHOUT `-r` runs its command ONCE WITH NO ARGUMENTS on empty input (GNU behaviour, the one this repo runs), so `... | xargs ruff format` is the same accident. shellscan strips `xargs` as a prefix, so the `-r` / `--no-run-if-empty` flag is read from the raw text in front of the tool's name.

A BARE `.` AT THE REPOSITORY ROOT IS REFUSED TOO, deliberately. The task that produced this guard asked for the decision to be made out loud, so here it is: the damage on 2026-10-07 came from a whole-repo rewrite, and the empty substitution was only the route there. `ruff format .` at the root is that same rewrite typed on purpose, and it is still 26 markdown files outside the work.
An agent session never needs it: it formats the files it touched, by name. So a path resolving to a repository root (`.`, `./`, `..` from a direct child, the absolute root, a `**` glob or `./...` package pattern anchored there, or a submodule's own root) counts as the whole tree. A SUBDIRECTORY is allowed (`cd packages/cli && eslint --fix .`), because naming a package is a deliberate, bounded scope, and `block_unproven_bulk_transform` still demands proof at commit time if that scope turns out large.
A genuine whole-tree format is an operator decision, run with the `!` prefix, which no pre-bash guard sees.

WHAT IS JUDGED, AND WHAT IS LEFT OPEN.
    tools     ruff (format; check --fix/--fix-only), black, prettier --write, eslint --fix, biome (format/check/lint with --write/--fix/--apply), gofmt -w, goimports -w, gofumpt -w, shfmt -w, golangci-lint run --fix, go fmt
    launchers npx, npm exec, uvx, uv run, uv tool run, pipx run, python -m, plus whatever shellscan already strips (env, timeout, xargs, command, ...), `bash -c`, `eval`
    names     a command named by a variable (`$R format`) is resolved through a literal `R=...` assignment in the same command, which is exactly the incident's spelling
Read-only modes (`--check`, `--diff`, `-l`, no `--fix`), stdin modes (`-`, `--stdin-filename` and its spellings) and biome's VCS scopes (`--staged`, `--changed`) are allowed.
It FAILS OPEN where it cannot judge: a command name that is a variable with no literal assignment, a `cd` into a computed directory (the root test only), and an option this table does not know takes a value (its value is then read as a path, which can only make the guard more permissive).

OWN_SUITE = True: this guard was never bash, so there is no golden to freeze; `test-block_unscoped_formatter_run.py` is its suite, both directions plus the planted DEFECT.
"""

import pathlib
import re

from rediacc_hooks import hookio, shellscan

CHAIN = "pre-bash"
OWN_SUITE = True
ORDER = 55

# The decision the incident needed: "every path may vanish" is the empty-set case. Planting `return False` lets `ruff format $(empty)` and a bare `ruff format` through, which is the 2026-10-07 rewrite; the whole-tree arm is untouched, so the mutant is a targeted one.
DEFECT = (
    "    return not paths or all(p.vanishes for p in paths)",
    "    return False",
)

INCIDENT = (
    "R=ruff; $R format $( $R format --check a.py b.py 2>&1 | grep 'Would reformat'"
    " | sed 's/Would reformat: //')"
)

EDGE_CASES = [
    ("the 2026-10-07 command", INCIDENT),
    ("ruff format with no path", "ruff format"),
    ("ruff check --fix with no path", "ruff check --fix"),
    ("only a command substitution", "ruff format $(git diff --name-only -- '*.py')"),
    ("-- does not save an empty substitution", "ruff format -- $(git diff --name-only)"),
    ("only a backtick span", "black `git ls-files '*.py'`"),
    ("only an unquoted variable", "files=$(git diff --name-only); prettier --write $files"),
    ('"$@" vanishes even quoted', 'eslint --fix "$@"'),
    ("xargs without -r", "git diff --name-only | xargs npx prettier --write"),
    ("dot at the repo root", "ruff format ."),
    ("biome write with no path", "npx @biomejs/biome check --write"),
    ("gofmt -w with no path", "gofmt -w"),
    ("shfmt -w with no path", "shfmt -w"),
    ("inside bash -c", "bash -c 'ruff format'"),
    ("python -m black with no path", "python3 -m black"),
    ("go fmt over the whole module", "go fmt ./..."),
    # CONTROLS: every one of these must pass.
    ("explicit paths after --", "ruff format -- a.py b.py"),
    ("a check is read-only", "ruff format --check"),
    ("ruff check without --fix", "ruff check"),
    (
        "a guarded variable",
        'files=$(git diff --name-only); [ -n "$files" ] && ruff format -- $files',
    ),
    ("${x:?} aborts on empty", "ruff format ${files:?no files}"),
    ("a quoted substitution is one word", 'ruff format "$(git diff --name-only | head -1)"'),
    ("a literal beside a substitution", "ruff format a.py $(git diff --name-only)"),
    ("xargs -r skips empty input", "git diff --name-only | xargs -r npx prettier --write"),
    ("a for-loop variable", "for f in a.py b.py; do black $f; done"),
    ("a subdirectory dot", "cd packages/cli && npx eslint --fix ."),
    ("stdin mode", "ruff format - < a.py"),
    ("biome over staged files", "npx biome check --write --staged"),
    ("prose is not a run", "echo 'ruff format'"),
    ("a commit message is not a run", 'git commit -m "ruff format" -- a.py'),
]

# --------------------------------------------------------------------------- the tool table ---------------------------------------------------------------------------

# Options that take a VALUE, per tool, so the word after them is not a path. A missing entry fails open (see the module docstring); `--opt=value` is always one word.
VALUE_OPTS = {
    "ruff": frozenset(
        (
            "--config",
            "--target-version",
            "--line-length",
            "--exclude",
            "--extend-exclude",
            "--stdin-filename",
            "--cache-dir",
            "--range",
            "--select",
            "--ignore",
            "--extend-select",
            "--extend-ignore",
            "--per-file-ignores",
            "--extend-per-file-ignores",
            "--fixable",
            "--unfixable",
            "--extend-fixable",
            "--output-format",
            "-o",
            "--output-file",
            "--dummy-variable-rgx",
            "--extension",
            "--color",
            "--add-noqa",
        )
    ),
    "black": frozenset(
        (
            "-l",
            "--line-length",
            "-t",
            "--target-version",
            "--include",
            "--exclude",
            "--extend-exclude",
            "--force-exclude",
            "--stdin-filename",
            "--config",
            "-W",
            "--workers",
            "--required-version",
            "--python-cell-magics",
            "--enable-unstable-feature",
            "--line-ranges",
        )
    ),
    "prettier": frozenset(
        (
            "--config",
            "--ignore-path",
            "--plugin",
            "--parser",
            "--print-width",
            "--tab-width",
            "--trailing-comma",
            "--end-of-line",
            "--log-level",
            "--cache-location",
            "--cache-strategy",
            "--stdin-filepath",
            "--config-precedence",
            "--arrow-parens",
            "--prose-wrap",
            "--quote-props",
            "--html-whitespace-sensitivity",
            "--embedded-language-formatting",
            "--object-wrap",
            "--experimental-operator-position",
        )
    ),
    "eslint": frozenset(
        (
            "-c",
            "--config",
            "--ext",
            "--parser",
            "--parser-options",
            "--resolve-plugins-relative-to",
            "--rulesdir",
            "--plugin",
            "--rule",
            "--global",
            "--env",
            "--ignore-path",
            "--ignore-pattern",
            "-f",
            "--format",
            "-o",
            "--output-file",
            "--max-warnings",
            "--cache-location",
            "--cache-strategy",
            "--stdin-filename",
            "--report-unused-disable-directives-severity",
            "--fix-type",
            "--flag",
            "--concurrency",
        )
    ),
    "biome": frozenset(
        (
            "--config-path",
            "--max-diagnostics",
            "--diagnostic-level",
            "--log-level",
            "--log-kind",
            "--log-path",
            "--colors",
            "--stdin-file-path",
            "--reporter",
            "--since",
            "--only",
            "--skip",
            "--vcs-root",
            "--threads",
        )
    ),
    "gofmt": frozenset(("-r", "-cpuprofile")),
    "goimports": frozenset(("-local", "-srcdir", "-cpuprofile")),
    "gofumpt": frozenset(("-lang", "-modpath", "-r", "-cpuprofile")),
    "shfmt": frozenset(
        ("-i", "--indent", "-ln", "--language-dialect", "-filename", "--filename", "--to-json")
    ),
    "golangci-lint": frozenset(
        (
            "-c",
            "--config",
            "--timeout",
            "--out-format",
            "-E",
            "--enable",
            "-D",
            "--disable",
            "--build-tags",
            "--new-from-rev",
            "--new-from-patch",
            "-j",
            "--concurrency",
            "--path-prefix",
            "--max-issues-per-linter",
            "--max-same-issues",
            "-p",
            "--presets",
            "--modules-download-mode",
            "--go",
        )
    ),
    "go": frozenset(("-mod", "-modfile", "-C")),
}

STDIN_OPTS = frozenset(
    ("--stdin-filename", "--stdin-filepath", "--stdin-file-path", "-filename", "--filename")
)
BIOME_SUBS = frozenset(("format", "check", "lint"))
BIOME_WRITE = frozenset(("--write", "--fix", "--apply", "--apply-unsafe"))
BIOME_SCOPED = frozenset(("--staged", "--changed"))
# Launchers whose own options take a value, so their value is not the tool.
NPX_VALUE = frozenset(("-p", "--package", "--cache", "--userconfig", "-w", "--workspace"))
UV_VALUE = frozenset(
    (
        "--with",
        "--with-requirements",
        "--with-editable",
        "--python",
        "-p",
        "--project",
        "--directory",
        "--group",
        "--extra",
        "--package",
        "--from",
        "--env-file",
        "--index",
        "--default-index",
        "--index-url",
        "--extra-index-url",
    )
)
PY_VALUE = frozenset(("-W", "-X", "-c"))
LAUNCHER_STOP = frozenset(("-c", "--call"))

TOOL_WORD = re.compile(
    r"(^|[^A-Za-z0-9_-])(ruff|black|prettier|eslint|biome|gofmt|goimports|gofumpt|shfmt"
    r"|golangci-lint|go)([^A-Za-z0-9_-]|$)"
)
ASSIGN = re.compile(
    r"(?:^|[\s;&|(])([A-Za-z_][A-Za-z0-9_]*)=(\"[^\"$`]*\"|'[^']*'|[A-Za-z0-9_./@+:,-]+)(?=[\s;&|)]|$)"
)
FOR_VAR = re.compile(r"(?:^|[\s;&|(])for\s+([A-Za-z_][A-Za-z0-9_]*)\s+in\s")
# An expansion bash can expand to ZERO words even inside double quotes.
LIST_EXPANSION = re.compile(r"^\$(?:@|\{[A-Za-z_][A-Za-z0-9_]*\[[@*]\]\})$")
# `${x:?msg}` / `${x?}`: bash aborts the command when x is empty or unset.
ABORTS_EMPTY = re.compile(r"^\$\{[A-Za-z_][A-Za-z0-9_]*:?\?[^}]*\}$")
SIMPLE_VAR = re.compile(r"^\$(?:\{([A-Za-z_][A-Za-z0-9_]*)\}|([A-Za-z_][A-Za-z0-9_]*))$")
XARGS_SAFE = r"xargs(?:\s+(?:-[A-Za-z0-9]+|--[a-z-]+(?:=\S+)?|\S+))*?\s+(?:-[A-Za-z0-9]*r[A-Za-z0-9]*|--no-run-if-empty)\b[^|;&]*?\b%s\b"
XARGS_ANY = r"xargs\b[^|;&]*?\b%s\b"

MESSAGE = """BLOCKED: `%(shown)s` runs %(tool)s in write mode, and its path set %(why)s.

On 2026-10-07 `ruff format $( ... | grep 'Would reformat' | sed ...)` ran with an
empty substitution, so ruff got NO path, formatted the current directory, and
rewrote 28 files across the whole repo, 26 of them docs outside the work.

Name the files, explicitly:
    %(tool)s %(safe)s -- <path> [<path>...]
or capture the list and refuse an empty one before the run:
    files=$(git diff --name-only -- '*.py'); [ -n "$files" ] && %(tool)s %(safe)s -- $files
(`${files:?no files}` also works: bash aborts on an empty value.) With xargs, add -r:
    ... | xargs -r %(tool)s %(safe)s
`--` alone does not help: `%(tool)s %(safe)s -- $(empty)` is still a run with no path.
A whole-tree format is an operator decision, run with the `!` prefix.
"""

# The pseudo-path standing for what xargs appends; never root-tested.
XARGS_INPUT = "(xargs input)"

WHY_NONE = (
    "is EMPTY: no path at all, which ruff, eslint, biome and golangci-lint read as the\n"
    "current directory"
)
WHY_VANISH = (
    "may be EMPTY: every path is an expansion that can become zero words\n"
    "(%s), and then the run has no path at all"
)
WHY_XARGS = "may be EMPTY: xargs without -r runs it once with no path when its input is empty"
WHY_ROOT = "is the WHOLE TREE: %r resolves to the repository root %s"


class _Path:
    __slots__ = ("text", "vanishes")

    def __init__(self, text, vanishes):
        self.text = text
        self.vanishes = vanishes


def _may_be_empty(paths):
    """THE INCIDENT'S PREDICATE: no path survives word splitting for certain."""
    return not paths or all(p.vanishes for p in paths)


# --------------------------------------------------------------------------- reading a run ---------------------------------------------------------------------------


def _strip_expansions(word):
    """`word` with every `$(...)`, backtick span, `${...}` and `$name` removed; "" means the word is expansions and nothing else."""
    out = []
    i = 0
    n = len(word)
    while i < n:
        ch = word[i]
        if ch == "`":
            j = word.find("`", i + 1)
            i = n if j < 0 else j + 1
            continue
        if ch == "$" and i + 1 < n:
            nxt = word[i + 1]
            if nxt in "({":
                close = ")" if nxt == "(" else "}"
                depth = 0
                j = i + 1
                while j < n:
                    if word[j] == nxt:
                        depth += 1
                    elif word[j] == close:
                        depth -= 1
                        if depth == 0:
                            break
                    j += 1
                i = j + 1
                continue
            m = re.match(r"[A-Za-z_][A-Za-z0-9_]*|[0-9@*#?$!-]", word[i + 1 :])
            if m:
                i += 1 + m.end()
                continue
        out.append(ch)
        i += 1
    return "".join(out)


def _dynamic(word):
    return "$" in word or "`" in word


def _resolve_name(name, assigns):
    m = SIMPLE_VAR.match(name)
    if not m:
        return name
    return assigns.get(m.group(1) or m.group(2), name)


def _tool_argv(name, argv, assigns):
    """(tool, argv after the tool) for a formatter run, or None. Unwraps the launchers the module docstring names."""
    base = shellscan._base(_resolve_name(name, assigns))
    for _ in range(4):
        if base in VALUE_OPTS:
            return base, argv
        if base == "npx" or (base == "npm" and argv[:1] == ["exec"]):
            rest = argv[1:] if base == "npm" else argv
            found = _skip_launcher_opts(rest, NPX_VALUE)
        elif base == "uvx" or (base == "pipx" and argv[:1] == ["run"]):
            rest = argv[1:] if base == "pipx" else argv
            found = _skip_launcher_opts(rest, UV_VALUE)
        elif base == "uv" and argv[:1] == ["run"]:
            found = _skip_launcher_opts(argv[1:], UV_VALUE)
        elif base == "uv" and argv[:2] == ["tool", "run"]:
            found = _skip_launcher_opts(argv[2:], UV_VALUE)
        elif re.match(r"^python[0-9.]*$", base):
            found = _python_module(argv)
        else:
            return None
        if found is None:
            return None
        tool, argv = found
        base = _package_bin(tool)
    return None


def _skip_launcher_opts(argv, value_opts):
    i = 0
    while i < len(argv):
        word = argv[i]
        if word == "--":
            i += 1
            break
        if word in LAUNCHER_STOP:
            return None
        if word.startswith("-") and word != "-":
            i += 2 if word in value_opts else 1
            continue
        break
    if i >= len(argv):
        return None
    return argv[i], argv[i + 1 :]


def _python_module(argv):
    i = 0
    while i < len(argv):
        word = argv[i]
        if word == "-m":
            return (argv[i + 1], argv[i + 2 :]) if i + 1 < len(argv) else None
        if word.startswith("-m") and len(word) > 2:
            return word[2:], argv[i + 1 :]
        if word.startswith("-") and word != "-":
            i += 2 if word in PY_VALUE else 1
            continue
        return None
    return None


def _package_bin(spec):
    """`prettier@3` -> prettier, `@biomejs/biome@2` -> biome, `mvdan.cc/sh/v3/cmd/shfmt` -> shfmt."""
    spec = spec.removeprefix("@").split("@", 1)[0]
    return spec.rsplit("/", 1)[-1]


def _split(tool, argv):
    """(subcommand words, flags, path words, stdin) for one tool's argv."""
    values = VALUE_OPTS[tool]
    flags = set()
    words = []
    stdin = False
    i = 0
    while i < len(argv):
        word = argv[i]
        if word == "--":
            words.extend(argv[i + 1 :])
            break
        if word == "-":
            stdin = True
        elif word.startswith("-"):
            flag, eq, _ = word.partition("=")
            flags.add(flag)
            if flag in STDIN_OPTS:
                stdin = True
            if not eq and flag in values:
                i += 1
        else:
            words.append(word)
        i += 1
    return flags, words, stdin


def _writes(tool, flags, words):
    """(writes, path words) once the subcommand is taken off, or (False, ...) for a read-only run."""
    if tool == "ruff":
        if not words or words[0] not in ("format", "check"):
            return False, words
        sub, rest = words[0], words[1:]
        if sub == "format":
            return not flags & {"--check", "--diff"}, rest
        fix = bool(flags & {"--fix", "--fix-only"}) and "--no-fix" not in flags
        return fix and "--diff" not in flags and "--watch" not in flags, rest
    if tool == "black":
        return not flags & {"--check", "--diff", "-c", "--code"}, words
    if tool == "prettier":
        return bool(flags & {"--write", "-w"}), words
    if tool == "eslint":
        return "--fix" in flags, words
    if tool == "biome":
        if not words or words[0] not in BIOME_SUBS:
            return False, words
        return bool(flags & BIOME_WRITE) and not flags & BIOME_SCOPED, words[1:]
    if tool in ("gofmt", "goimports", "gofumpt"):
        return "-w" in flags, words
    if tool == "shfmt":
        return bool(flags & {"-w", "--write"}), words
    if tool == "golangci-lint":
        return bool(words) and words[0] == "run" and "--fix" in flags, words[1:]
    if tool == "go":
        return bool(words) and words[0] == "fmt" and "-n" not in flags, words[1:]
    return False, words


def _guarded(var, cmd):
    """Is `$var` tested non-empty with `&&` or `then` before it can reach the run?"""
    name = re.escape(var)
    test = (
        r"(?:\[\[?|\btest)\s+-n\s+\"?\$\{?%s\}?\"?\s*(?:\]\]?)?\s*(?:&&|;?\s*then\b|\n\s*then\b)"
        % name
    )
    return re.search(test, cmd) is not None


def _classify(word, canonical, cmd, assigns, loop_vars):
    """One path word as a `_Path`, with any literal assignment substituted for the root test."""
    if not _dynamic(word):
        return [_Path(word, False)]
    if LIST_EXPANSION.match(word):
        return [_Path(word, True)]
    if _strip_expansions(word) != "":
        return [_Path(word, False)]
    # shellscan drops every QUOTED span from `canonical`, so a value missing from it was quoted: one word, never zero (module docstring).
    if word not in canonical:
        return [_Path(word, False)]
    if ABORTS_EMPTY.match(word):
        return [_Path(word, False)]
    m = SIMPLE_VAR.match(word)
    if m:
        var = m.group(1) or m.group(2)
        if var in loop_vars or _guarded(var, cmd):
            return [_Path(word, False)]
        value = assigns.get(var)
        if value is not None and value.strip() and not _dynamic(value):
            return [_Path(v, False) for v in value.split()]
    return [_Path(word, True)]


def _assignments(cmd):
    found = {}
    for m in ASSIGN.finditer(cmd):
        value = m.group(2)
        if value[:1] in ("'", '"'):
            value = value[1:-1]
        found[m.group(1)] = value
    return found


# --------------------------------------------------------------------------- the root test ---------------------------------------------------------------------------


def _base_dir(ev, run):
    base = pathlib.Path(ev.field("cwd") or ev.cwd)
    if run.cwd is None:
        return base
    if _dynamic(run.cwd) or run.cwd in ("-", "~") or run.cwd.startswith("~"):
        return None
    return base / run.cwd


def _scope_dir(word):
    """The directory a path word recurses from, or None when it names files rather than a tree."""
    if word.endswith("/..."):
        return word[: -len("/...")] or "/"
    if "*" in word or "?" in word or "[" in word:
        head: list[str] = []
        for part in word.split("/"):
            if any(ch in part for ch in "*?["):
                return ("/".join(head) or ".") if part.startswith("**") else None
            head.append(part)
        return None
    return word


def _toplevel(directory):
    out = hookio.git_out(["-C", str(directory), "rev-parse", "--show-toplevel"])
    return pathlib.Path(out.strip()).resolve() if out and out.strip() else None


def _root_hit(word, base):
    """The repository root `word` resolves to, or None."""
    if base is None or _dynamic(word):
        return None
    scope = _scope_dir(word)
    if scope is None:
        return None
    try:
        target = (base / scope).resolve()
    except (OSError, RuntimeError):
        return None
    if not target.is_dir():
        return None
    top = _toplevel(target)
    if top is not None and top == target:
        return top
    here = _toplevel(base)
    if here is not None and target in here.parents:
        return here
    return None


# --------------------------------------------------------------------------- the guard ---------------------------------------------------------------------------


def _xargs_fed(tool, cmd):
    """(fed by xargs, xargs has -r) for a run of `tool`, read from the raw text."""
    name = re.escape(tool)
    if re.search(XARGS_ANY % name, cmd) is None:
        return False, False
    return True, re.search(XARGS_SAFE % name, cmd) is not None


def _verdict(ev, cmd, run, assigns, loop_vars):
    found = _tool_argv(run.name, run.argv, assigns)
    if found is None:
        return None
    tool, argv = found
    flags, words, stdin = _split(tool, argv)
    writes, path_words = _writes(tool, flags, words)
    if not writes or stdin:
        return None
    paths = []
    for word in path_words:
        paths.extend(_classify(word, run.canonical, cmd, assigns, loop_vars))
    shown = run.canonical if len(run.canonical) <= 160 else run.canonical[:157] + "..."
    safe = _safe_verb(tool, words, flags)
    # xargs appends its input as paths, so that input is one more path word: one that vanishes on empty input unless `-r` stops the run. Routed through the same predicate as every other path, so the DEFECT judges it too.
    fed, safe_x = _xargs_fed(tool, cmd)
    if fed:
        paths.append(_Path(XARGS_INPUT, not safe_x))
    if _may_be_empty(paths):
        if not paths:
            return tool, shown, safe, WHY_NONE
        if fed:
            return tool, shown, safe, WHY_XARGS
        return tool, shown, safe, WHY_VANISH % ", ".join(p.text for p in paths)
    base = _base_dir(ev, run)
    for p in paths:
        root = None if p.vanishes or p.text == XARGS_INPUT else _root_hit(p.text, base)
        if root is not None:
            return tool, shown, safe, WHY_ROOT % (p.text, root)
    return None


def _safe_verb(tool, words, flags):
    """The subcommand and write flag the refusal's suggested form repeats, so it can be pasted."""
    keep = {
        "ruff": ["--fix"] if "--fix" in flags else [],
        "prettier": ["--write"],
        "eslint": ["--fix"],
        "biome": sorted(flags & BIOME_WRITE)[:1],
        "gofmt": ["-w"],
        "goimports": ["-w"],
        "gofumpt": ["-w"],
        "shfmt": ["-w"],
        "golangci-lint": ["--fix"],
    }.get(tool, [])
    sub = words[:1] if tool in ("ruff", "biome", "golangci-lint", "go") else []
    return " ".join([*sub, *keep])


def run(ev):
    cmd = ev.field("tool_input", "command")
    if not cmd or TOOL_WORD.search(cmd) is None:
        return hookio.ALLOW
    assigns = _assignments(cmd)
    loop_vars = set(FOR_VAR.findall(cmd))
    for item in shellscan._analyse(cmd).runs:
        verdict = _verdict(ev, cmd, item, assigns, loop_vars)
        if verdict is None:
            continue
        tool, shown, safe, why = verdict
        ev.warn(MESSAGE % {"shown": shown, "tool": tool, "why": why, "safe": safe})
        return hookio.DENY
    return hookio.ALLOW
