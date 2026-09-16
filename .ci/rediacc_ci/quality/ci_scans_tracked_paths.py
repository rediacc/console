"""CI CANNOT EXECUTE WHAT GIT DOES NOT TRACK.

Ported from `.ci/scripts/quality/check-ci-scans-tracked-paths.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__` for why both copies live.

The twin's header, carried whole because the incident and the false-positive
argument are both load-bearing:

    A GitHub runner checks out tracked files only. So a workflow step or a CI
    shell script that RUNS something under a gitignored path invokes a file that
    is not there: it errors, or worse, exits 0 having done nothing and reports
    coverage that cannot exist.

    This is not hypothetical. Over five stops on 2026-08-28 a stop-hook judge
    repeatedly instructed this session to wire
    `private/growth/.ci/checks/check-no-direct-query.sh` into `ci-quality.yml`.
    `private/growth` is a SEPARATE repository, ignored at `.gitignore:69`, with
    zero tracked files in console. Each time, the reason it could not work had to
    be re-derived by hand.

    `scripts/gates/check-gate-manifest.ts` closed one door: a manifest LEAF git does
    not track is now refused. This closes the other: a workflow `run:` line, or a
    `.ci/scripts` command, that reaches into an ignored path.

    PROSE IS NOT EXECUTION, and that distinction is the whole difficulty.
    Comments and error messages naming `private/growth` are CORRECT and common:
    `check-translation-hashes.ts` tells a human which pipeline regenerates a
    file, `ci-quality.yml` explains why a provenance file is committed. Flagging
    those would make the gate noise, it would be silenced, and it would then
    guard nothing. Only command positions are examined.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE IGNORED ROOTS ARE ASKED OF GIT, NEVER HARDCODED, and the twin says why in
one line kept at the function: "a new ignored directory is covered the day it
appears, and a path that stops being ignored stops being flagged." The globs are
`*/` and `*/*/`, which is bash's own behaviour and therefore EXCLUDES dotted
directories: `.git`, `.github` and `.ci` are never candidates. That is not an
oversight to be tidied; widening it would put `.git` itself in the alternation.

TWO CONDITIONS, AND DROPPING EITHER MAKES THIS GATE NOISE. The twin's words,
carried at the two tests they describe:

    Without the command-position test, a YAML artifact `path:` list entry like
    `private/bin/renet-linux-*` reads as an executable. Without the executable
    test, a tracked script writing its OUTPUT to `./private/bin` reads as running
    from it.

    THE EXECUTABLE, not the line. `ci-build-renet.yml:199` runs a TRACKED script
    and merely writes its output to `./private/bin`, which is ignored; flagging
    that would be noise, and a noisy gate gets silenced. Only the thing being RUN
    matters, so strip the command keyword and test the token immediately after it.

`return "$hits"` IS FORBIDDEN AND THE REASON IS CARRIED. The twin: "A shell
return is taken mod 256, so exactly 256 findings would return 0 and read as a
clean scan. Only the STATUS is made boolean here; the count itself is still
printed with the findings." This port returns the findings themselves and lets
the caller test emptiness, which cannot wrap at all, and the comment stays
because it explains why an obvious refactor is wrong.

ONE PASS, NOT ONE PER ROOT. The twin: "ONE grep over each surface, not one pass
per ignored root. The nested form was O(roots x files x lines) in pure bash and
did not finish in two minutes on this repo." Measured while porting on the real
checkout: `node_modules/*` alone contributes several hundred ignored roots, so
the alternation is enormous and the nested form would be hopeless. The port
compiles the same alternation once.

THE ESCAPING IS `sed 's/[].[^$*\\/]/\\\\&/g'`, a seven-character class:
`]`, `.`, `[`, `^`, `$`, `*`, `/`. `]` first in a bracket expression is literal
and `^` not first is literal, which is why that spelling is not a typo. Every one
of those escapes is also valid in Python's `re`, so the pattern string crosses
languages unchanged rather than being rebuilt.

THE SORT IS BYTEWISE. The twin pipes grep's output through `sort` under the
comparator's `LC_ALL=C`, so the port sorts the same `path:line:text` strings by
their bytes. Sorting the parsed tuples instead would order 9 before 10 and
disagree with the twin on any file with more than nine hits.

A TREE WITH NO IGNORED DIRECTORIES PASSES, AND THAT IS A TWIN DEFECT CARRIED
RATHER THAN FIXED. `[ -z "$roots" ] && return 0` means a checkout whose
`.gitignore` vanished reports "Nothing CI executes reaches into a gitignored
path" while having examined nothing. It is reproduced because changing it would
change the verdict, and it is named here so it is a known hole rather than a
surprise.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# The gate's own filename, skipped by BASENAME so the examples inside it are not
# read as findings. The twin spells this `SELF`; the value has to stay the bash
# file's name, because that is the file whose examples would otherwise match.
SELF = "check-ci-scans-tracked-paths.sh"

# The two surfaces scanned, and the two extensions. Anything a runner executes
# lives in one of these; a third surface is a deliberate widening, not a typo.
SURFACES = ((".github", "workflows"), (".ci", "scripts"))
# `.py` ALONGSIDE `.sh`, and the twin at .ci/scripts/quality/check-ci-scans-tracked-paths.sh:85
# carries the same widening, because the two must agree or the shadow differential
# disagrees on the corpus rather than on the verdict. SURFACES above already puts
# `.ci/scripts` in scope, so only the extension filter was keeping the ported gates
# out. Measured 2026-09-08: 45 quality gates exist ONLY as `check_*.py`, with no
# `.sh` twin left to cover them by accident, so a ported gate that invokes a
# gitignored path was judged by nothing.
INCLUDES = (".yml", ".sh", ".py")

# The command-position prefixes. A line whose whitespace-stripped form does not
# start with one of these is not running anything, whatever else it names.
COMMAND_PREFIXES = (
    "run:",
    "- run:",
    "bash ",
    "sh ",
    "./",
    "source ",
    ". ",
    "npm ",
    "npx ",
    "node ",
    "python3 ",
    "tsx ",
)

# Interpreters whose FIRST argument is the thing being run.
INTERPRETERS = ("bash ", "sh ", "source ", "node ", "python3 ", "tsx ")

# The seven characters the twin's sed escapes. Written as a set rather than as a
# copy of the bracket expression, because the bracket expression's ordering rules
# (`]` first, `^` not first) are what make it readable as a class at all.
SED_SPECIALS = "].[^$*/"


def escape_for_ere(name: str) -> str:
    """`sed 's/[].[^$*\\/]/\\\\&/g'` over one directory name."""
    return "".join("\\" + ch if ch in SED_SPECIALS else ch for ch in name)


def ignored_roots(root: pathlib.Path) -> list[str]:
    """The one- and two-level directories git ignores, repo-relative.

    The globs are bash's `*/` and `*/*/`, so a dotted directory is never a
    candidate and the order is the shell's sorted order: every first-level entry
    before every second-level one.
    """
    candidates: list[str] = []
    for depth in (1, 2):
        candidates.extend(sorted(_glob_dirs(root, depth)))
    if not candidates:
        return []
    # ONE `git check-ignore` call, not one per directory. `--stdin` answers the
    # same question for the whole list; the twin pays a process per directory and
    # that is the only place this port is deliberately faster rather than
    # identical, because the ANSWER is the same set.
    proc = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--stdin"],
        input="\n".join(candidates).encode("utf-8"),
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    ignored = {line for line in proc.stdout.decode("utf-8", "replace").split("\n") if line}
    return [c for c in candidates if c in ignored]


def _glob_dirs(root: pathlib.Path, depth: int) -> list[str]:
    """Directories exactly `depth` levels down, skipping dotted names.

    Bash's `*` does not match a leading dot, which is what keeps `.git` out of
    the alternation. Reproduced explicitly rather than relying on a library
    glob's defaults.
    """
    if depth == 1:
        return [child for child in _listdir(root) if (root / child).is_dir()]
    return [
        "%s/%s" % (parent, child)
        for parent in _listdir(root)
        if (root / parent).is_dir()
        for child in _listdir(root / parent)
        if (root / parent / child).is_dir()
    ]


def _listdir(where: pathlib.Path) -> list[str]:
    try:
        return [n for n in os.listdir(where) if not n.startswith(".")]
    except OSError:
        return []


def roots_pattern(roots: list[str]) -> str:
    """The alternation `paste -sd'|'` builds from the escaped names."""
    return "|".join(escape_for_ere(r) for r in roots)


def grep_lines(root: pathlib.Path, pattern: str) -> list[str]:
    """`grep -rnE <pat> <surfaces> --include='*.yml' --include='*.sh' | sort`.

    Returns `path:line:text` strings, sorted BYTEWISE, with the paths spelled the
    way grep spells them: the surface directory it was given, then the relative
    tail.
    """
    compiled = re.compile(pattern)
    hits: list[str] = []
    for surface in SURFACES:
        base = root.joinpath(*surface)
        if not base.is_dir():
            continue
        for dirpath, _dirs, files in paths.walk_tree(base):
            for name in sorted(files):
                if not name.endswith(INCLUDES):
                    continue
                path = pathlib.Path(dirpath) / name
                try:
                    text = path.read_text(encoding="utf-8", errors="replace")
                except OSError:
                    continue
                for number, line in enumerate(text.split("\n"), start=1):
                    if compiled.search(line):
                        hits.append("%s:%d:%s" % (path, number, line))
    return sorted(hits, key=lambda s: s.encode("utf-8", "surrogateescape"))


def executable_token(stripped: str) -> str | None:
    """The thing being RUN on this line, or None when the line runs nothing.

    Both of the twin's conditions live here: the command-position test decides
    whether the line is a command at all, and the keyword stripping decides which
    token is the executable. `npm` returns None on purpose, because an npm key is
    resolved by package.json and is not a path.
    """
    if not stripped.startswith(COMMAND_PREFIXES):
        return None

    # `${exe#- }` then `${exe#run: }`, in that order and unconditionally, which
    # is what lets `- run: x` lose both prefixes in one pass.
    exe = stripped.removeprefix("- ").removeprefix("run: ")

    if exe.startswith("npm "):
        return None
    if exe.startswith("npx "):
        # `npx <pkg> <arg>`: the twin drops `npx `, then drops the next word, so
        # the token tested is the ARGUMENT to the tool rather than the tool.
        exe = exe[4:]
        exe = exe.split(" ", 1)[1] if " " in exe else exe
    elif exe.startswith(INTERPRETERS):
        exe = exe.split(" ", 1)[1] if " " in exe else exe

    return exe.split(" ", 1)[0]


def scan(root: pathlib.Path) -> list[str]:
    """Every finding, as the two printed lines per hit, in grep order.

    NOT A COUNT AND NOT AN EXIT STATUS. See the port notes: a shell `return` is
    taken mod 256, so exactly 256 findings would read as a clean scan.
    """
    roots = ignored_roots(root)
    if not roots:
        # A TWIN DEFECT, carried. See the port notes: no ignored directories
        # means this gate examined nothing and still reports clean.
        return []
    pattern = roots_pattern(roots)
    exe_pattern = re.compile(r"^\.?/?(%s)/" % pattern)

    out: list[str] = []
    for hit in grep_lines(root, pattern):
        try:
            path, number, line = hit.split(":", 2)
        except ValueError:
            continue
        if path == "":
            continue
        if os.path.basename(path) == SELF:
            continue
        stripped = line.lstrip(" \t")
        if stripped.startswith("#"):
            continue
        exe = executable_token(stripped)
        if exe is None:
            continue
        if not exe_pattern.search(exe):
            continue
        relative = path[len(str(root)) + 1 :] if path.startswith(str(root) + "/") else path
        out.append("  %s:%s executes a gitignored path" % (relative, number))
        out.append("    %s" % stripped)
    return out


# ---------------------------------------------------------------------------
# The control tree, built by CONSTRUCTION.
# ---------------------------------------------------------------------------

CONTROL_WORKFLOW = (
    "jobs:\n"
    "  x:\n"
    "    steps:\n"
    "      # ignoredir/thing.sh is explained here, which is PROSE\n"
    "      - run: bash ignoredir/thing.sh\n"
)

CONTROL_SCRIPT = "#!/usr/bin/env bash\n# see ignoredir/thing.sh for why\nbash ignoredir/thing.sh\n"


def build_control_tree(where: pathlib.Path) -> pathlib.Path:
    """The twin's $CTL fixture: one ignored dir, one offender per surface, one comment."""
    (where / ".github" / "workflows").mkdir(parents=True, exist_ok=True)
    (where / ".ci" / "scripts").mkdir(parents=True, exist_ok=True)
    (where / "ignoredir").mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ["git", "-C", str(where), "init", "-q"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    (where / ".gitignore").write_text("ignoredir/\n", encoding="utf-8")
    (where / "ignoredir" / "thing.sh").write_text("", encoding="utf-8")
    (where / ".github" / "workflows" / "w.yml").write_text(CONTROL_WORKFLOW, encoding="utf-8")
    (where / ".ci" / "scripts" / "s.sh").write_text(CONTROL_SCRIPT, encoding="utf-8")
    return where


def run_controls(where: pathlib.Path) -> str | None:
    """Run the two controls. None means both fired; a string is the failure text.

    A gate nobody has watched fail is not a gate, so this runs BEFORE the real
    tree is touched and its failure is fatal rather than advisory.
    """
    build_control_tree(where)
    found = scan(where)
    if not found:
        return "CONTROL FAILED: an executed ignored path was NOT reported."
    hits = [line for line in found if "executes a gitignored path" in line]
    if len(hits) != 2:
        return "CONTROL FAILED: expected exactly 2 findings (one per surface), got:\n" + "\n".join(
            found
        )
    if any("# " in line for line in found):
        return "CONTROL FAILED: a COMMENT was reported as execution."
    return None


# The closing advice, kept as one block because the twin writes it with a single
# quoted heredoc and its paragraph breaks are part of the message.
ADVICE = """
A runner checks out tracked files only, so that step runs against a file that is not
there. Move the check into the repo that owns the code and run it from that repo's own
hooks, the way private/growth/.ci/checks/ does, or vendor the file into console.

Naming such a path in a COMMENT or an error message is fine and this gate ignores it."""


def main(argv: list[str] | None = None) -> int:
    """Run the controls, then the real tree. 0 clean, 1 on a finding or a dead control."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    with tempfile.TemporaryDirectory() as tmp:
        problem = run_controls(pathlib.Path(tmp))
    if problem is not None:
        print(problem, file=sys.stderr)
        return 1
    print("  PASS  control: an executed ignored path is reported, on both surfaces")
    print("  PASS  control: a comment naming the same path is NOT reported")

    root = paths.repo_root()
    found = scan(root)
    if not found:
        print("\u2713 Nothing CI executes reaches into a gitignored path.")
        return 0
    print("\u2717 CI would execute a path git does not track:", file=sys.stderr)
    for line in found:
        print(line, file=sys.stderr)
    print(ADVICE, file=sys.stderr)
    return 1


# ---------------------------------------------------------------------------
# Selftest
# ---------------------------------------------------------------------------


def selftest() -> int:
    """Both directions for the command-position test, the executable test and the scan.

    The over-broad direction is the one that matters most here: a gate that
    flagged an artifact path list or a script writing its OUTPUT into an ignored
    directory would be noise, would be silenced, and would then guard nothing.
    """
    ctl = Controls("ci-scans-tracked-paths", floor=24, verbose=True)

    # -- escaping and the alternation ---------------------------------------
    ctl.check("a dot is escaped", escape_for_ere("a.b"), "a\\.b")
    ctl.check("a slash is escaped", escape_for_ere("a/b"), "a\\/b")
    ctl.check("an ordinary name is untouched", escape_for_ere("private"), "private")
    ctl.check(
        "the alternation joins with a pipe",
        roots_pattern(["private/bin", "node_modules"]),
        "private\\/bin|node_modules",
    )

    # -- executable_token, both directions ----------------------------------
    ctl.check(
        "a workflow run: step yields its script", executable_token("- run: bash x/y.sh"), "x/y.sh"
    )
    ctl.check("a bare run: yields its script", executable_token("run: bash x/y.sh"), "x/y.sh")
    ctl.check("a direct bash call yields its script", executable_token("bash x/y.sh"), "x/y.sh")
    ctl.check("a ./ invocation is itself", executable_token("./x/y.sh --flag"), "./x/y.sh")
    ctl.check("source yields its argument", executable_token("source x/y.sh"), "x/y.sh")
    # TWIN BLIND SPOT, found by planting it and reported rather than repaired.
    # `. ` is in the command-position list but NOT in the interpreter-strip list
    # (`check-ci-scans-tracked-paths.sh:58` admits it, `:71` does not strip it),
    # so a dot-sourced script resolves to the single token `.`, which can never
    # match `^\.?/?(<roots>)/`. A `. private/growth/x.sh` line is therefore
    # invisible to both implementations. Pinned here so a reader meets it as a
    # known hole instead of assuming coverage.
    ctl.check(
        "TWIN BLIND SPOT: the dot-source form resolves to '.' and can never match",
        executable_token(". x/y.sh"),
        ".",
    )
    ctl.check(
        "npx drops the tool AND takes its argument", executable_token("npx tsx x/y.ts"), "x/y.ts"
    )
    ctl.check("npm is a package.json key, never a path", executable_token("npm run build"), None)
    ctl.check(
        "MIRROR: an artifact path list is not a command",
        executable_token("path: private/bin/renet-linux-*"),
        None,
    )
    ctl.check(
        "MIRROR: prose naming a path is not a command",
        executable_token("see private/growth/.ci/checks for why"),
        None,
    )
    ctl.check(
        "MIRROR: an env assignment is not a command",
        executable_token("OUT=private/bin"),
        None,
    )

    with tempfile.TemporaryDirectory() as tmp:
        base = pathlib.Path(tmp)

        # -- the twin's own control tree -----------------------------------
        control = build_control_tree(base / "control")
        ctl.check(
            "CONTROL: the control tree ignores exactly one root",
            ignored_roots(control),
            ["ignoredir"],
        )
        found = scan(control)
        ctl.check(
            "PLANT: both surfaces report, and nothing else does",
            [line for line in found if "executes a gitignored path" in line],
            [
                "  .ci/scripts/s.sh:3 executes a gitignored path",
                "  .github/workflows/w.yml:5 executes a gitignored path",
            ],
        )
        ctl.falsy(
            "MIRROR: the comment naming the same path is NOT reported",
            any("# " in line for line in found),
        )
        ctl.check("CONTROL: run_controls reports both fired", run_controls(base / "control2"), None)

        # -- a tree that WRITES into an ignored path is not running from it --
        writer = build_control_tree(base / "writer")
        (writer / ".github" / "workflows" / "w.yml").write_text(
            "jobs:\n  x:\n    steps:\n      - run: bash tracked.sh --out ignoredir/bin\n",
            encoding="utf-8",
        )
        (writer / ".ci" / "scripts" / "s.sh").write_text(
            "#!/usr/bin/env bash\nOUT=ignoredir/bin\n", encoding="utf-8"
        )
        ctl.check(
            "MIRROR: writing OUTPUT into an ignored path is not execution",
            scan(writer),
            [],
        )

        # -- a tree with NO ignored directories ------------------------------
        # The twin returns clean here having examined nothing. Pinned as a
        # DEFECT so the next reader meets it as a decision.
        bare = base / "bare"
        (bare / ".github" / "workflows").mkdir(parents=True)
        subprocess.run(
            ["git", "-C", str(bare), "init", "-q"],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
        (bare / ".github" / "workflows" / "w.yml").write_text(
            "jobs:\n  x:\n    steps:\n      - run: bash anything/thing.sh\n", encoding="utf-8"
        )
        ctl.check("TWIN DEFECT: no ignored roots means an empty scan", scan(bare), [])

        # -- the gate itself is skipped by basename --------------------------
        selfnamed = build_control_tree(base / "selfnamed")
        (selfnamed / ".ci" / "scripts" / SELF).write_text(
            "#!/usr/bin/env bash\nbash ignoredir/thing.sh\n", encoding="utf-8"
        )
        ctl.check(
            "MIRROR: the gate's own file is skipped, so its examples do not self-report",
            len([line for line in scan(selfnamed) if "executes a gitignored path" in line]),
            2,
        )

        # -- the whole gate, both directions ---------------------------------
        def run(root: pathlib.Path) -> int:
            saved = os.environ.get(paths.ROOT_ENV)
            os.environ[paths.ROOT_ENV] = str(root)
            try:
                return main([])
            finally:
                if saved is None:
                    os.environ.pop(paths.ROOT_ENV, None)
                else:
                    os.environ[paths.ROOT_ENV] = saved

        ctl.check("PLANT: an offending tree reds", run(control), 1)
        ctl.check("MIRROR: a tree that only writes into an ignored path passes", run(writer), 0)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
