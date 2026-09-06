r"""Every gate-tool version is defined ONCE, and nothing acquires unpinned.

Ported from `.ci/scripts/quality/check-toolchain-pins.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER, CARRIED ACROSS.
-----------------------------------------------------------------------------

Why this exists. Measured 2026-08-25, before .devcontainer/toolchain.env: ruff
was pinned in two places, PyYAML in four, and shfmt and shellcheck in none at
all -- so the same gate reached different verdicts in different lanes. The host
had shellcheck 0.9.0, the image had none, and CI used whatever the runner
shipped. shfmt agreed across lanes only by luck.

  A1  a pin's value appears in exactly one place
  A2  nothing acquires a gate tool unpinned (@latest / releases/latest)
  A3  the pins file itself is well-formed and non-trivial
  A6  a gate that runs a pinned tool acquires it, rather than trusting PATH
  A8  a WORKFLOW must not invoke a pinned tool directly
  A9  a pin must RESOLVE, not merely exist
  A10 all THREE readers must still READ the pins

Controls are built by CONSTRUCTION -- fixtures written literally into a temp
dir, never by substituting into real source -- so rewording a real file cannot
silently void them (see .ci/scripts/quality/check-control-vacuity.sh).

-----------------------------------------------------------------------------
THE PER-ASSERTION ARCHAEOLOGY, all of it the twin's.
-----------------------------------------------------------------------------

A1'S PATHSPEC IS `.ci/*.sh`, NOT `.ci/**/*.sh`. Git's default (non-`:(glob)`)
wildmatch lets `*` cross `/`, so `.ci/*.sh` already reaches every depth, while
`.ci/**/*.sh` demands a literal slash after `.ci/` and therefore MISSES every
script sitting directly under `.ci/`. Measured 2026-09-06 when .ci/bootstrap.sh
became the first file in that class: the two spellings return the same 453
tracked files, and only the second one drops bootstrap.sh. A scanner that
silently skips a file is the vacuity this gate exists to prevent, so the
narrower spelling is a bug.

A1 EXEMPTS NODE_VERSION AND GO_VERSION, because both are also expressed as bare
majors by third-party actions (actions/setup-node) and by go.mod, which are not
ours to unify. `check-toolchain-env-dockerfile-sync.sh` is the narrower check
that exemption made necessary.

COMMENTS ARE NOT DEFINITIONS. An earlier draft of A1 flagged this gate's own
measurement notes and a checksum URL containing the version -- prose ABOUT a
pin, not a second copy of it. Flagging prose would push someone to delete the
evidence for a rule in order to satisfy the rule, so comment lines are stripped
before the comparison. A line that names the KEY is reading the pin, not
restating it.

A2 COVERS ONLY THE TOOLS A GATE DEPENDS ON. Editor tooling (gopls, dlv,
staticcheck, golangci-lint, goimports) stays out of THIS assertion, but the
reason changed on 2026-09-06 and the old one is worth not re-deriving: it used
to be "nothing gates on its output, so pinning would buy churn". Those five are
now pinned as ARG <NAME>_VERSION lines in .devcontainer/Dockerfile, and three of
them are watched by check-devcontainer-pin-freshness. They remain outside A2
because A2 asks a different question: does a SHELL SCRIPT acquire a gate tool
without a version. A Dockerfile ARG is not that shape, and the freshness gate
already owns it. The control therefore still earns its place: it proves this
regex does not reach past the gate tools, using a synthetic fixture rather than
the real Dockerfile, which no longer contains a version-less install to sample.

A8 CATCHES UNPINNED USE, where A2 catches unpinned ACQUISITION. A workflow step
that runs `shfmt -d .` itself, instead of running the gate script that resolves
the tool at the pin, would silently lint with whatever the runner image happens
to ship. Nothing does that today; this exists so nothing starts. NOTE ON SHAPE,
because it is the opposite of what it may look like: a workflow invoking a gate
SCRIPT directly (`run: .ci/scripts/security/shfmt.sh`) is the REQUIRED pattern
here -- scripts/check-ci-parity.ts enforces three-point wiring in which the
workflow step names the script. It is invoking the TOOL that is forbidden, not
invoking the script.

THE A8 CONTROLS `mkdir` FIRST. The shared fixture dir is created in the controls
section further down, and writing before it exists made these silently write
nothing -- the control then reported DID NOT FIRE, which is the correct
direction for that mistake to fail in.

A6 IS DISCOVERED, NOT HARDCODED. It named shfmt.sh and shellcheck.sh literally,
so a THIRD gate invoking a pinned tool escaped the rule entirely -- the
assertion kept passing while the invariant rotted. Tracked AND untracked,
because `git ls-files` alone is blind to a gate not yet committed: proven by
planting one, which A6 then said nothing about. Same blind spot
.ci/scripts/security/shellcheck.sh:68 documents for its own enumerator.

PROSE IS NOT AN INVOCATION, and an echoed string is prose too. Measured
2026-08-26 (run 32907xxx, Quality / Code): A6 flagged check-shell-size.sh, whose
only two matches were

    echo "         # shellcheck extended-analysis=false"
    echo '# shellcheck extended-analysis=false'

i.e. the directive it TELLS you to add. It never runs shellcheck at all, so
demanding it acquire shellcheck at the pin was incoherent. Only a line whose
FIRST word is echo/printf and that carries no command separator is dropped:
`echo x; shfmt y` still gets scrutinised, so this narrows the false-positive
without opening a bypass.

DATA IS NOT AN INVOCATION EITHER, the same reasoning one step over. A
`NAME=(a b c)` array literal naming a gated tool as one of its elements is being
DEFINED, not run -- check-host-toolchain-coverage.sh's own NPX_TOOLS/BARE_TOOLS
fixtures tripped this before the exemption existed (measured 2026-08-28, run
98854256844, Quality / Code), because the tool name sits after `(` and before a
space, which the invocation regex cannot distinguish from a bare command word.
Only a line matching `NAME=(...)` in full (the assignment is complete on one
line, no command separator) is dropped, same narrowing discipline as the
echo/printf case.

A6 DEMANDS RESOLVING AT A PIN, not merely NAMING one. The first version accepted
any `*_VERSION` mention, and check-python-lint.sh passed it while still taking
an unversioned `command -v ruff` from PATH -- the assertion was satisfied by a
variable that the acquisition path never consulted.

A9 EXECUTES THE PIN. A1-A8 are source scans, and every one of them was green
while this was broken: toolchain_pin_for printed "" AND RETURNED 0 whenever the
pins had not been loaded, because sourcing toolchain.sh does not populate them.
The empty value then travelled into a download URL. Measured 2026-08-26 in a
fresh shell:

  .../releases/download/v/shellcheck-v.linux.aarch64.tar.xz  -> curl 404

The 404 names GitHub, so the symptom points away from the cause. No textual
assertion could have caught this: the source looked correct and the defect lived
in what the function RETURNED. So A9 executes it, in a subshell that sources
nothing but the library -- which is exactly the caller that broke.

THE A9 CONTROL IS A COPY PLUS AN APPENDED NO-OP OVERRIDE of toolchain_load.
Appending cannot silently fail to apply the way a pattern substitution can when
the targeted line is later reworded.

A10 ASSERTS THE UNIT, not the parts. A3 proves the file is PARSEABLE by three
readers. Nothing proved they still read it. Delete the `. toolchain.env` from
constants.sh, or the COPY from the Dockerfile, or the --env step from the
workflow, and every assertion above stays green while the pins go back to being
decorative -- which is the exact state this whole file exists to end. The
three-point wiring is the invariant; asserting the parts individually never
asserted the unit. Each reader is checked for the mechanism it actually uses,
not for the string "toolchain.env": a COMMENT mentioning the file would
otherwise satisfy the rule, and every one of these three files has several such
comments. The Actions reader is checked via `--env`, never a bare `cat`:
$GITHUB_ENV accepts only KEY=value and would choke on the comments, which is why
the emitter exists at all.

THE BLIND SPOT, stated so a green is not read as more than it is: A1 is a
LITERAL scan, so a pin written 0.16 against a value of 0.16.1 escapes it.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`set -uo pipefail` WITHOUT `-e` is the twin's mode, so a failing grep is a
verdict rather than an abort. Every probe below therefore returns a value and
nothing raises; the one place that would have raised in Python (a missing file)
is guarded, because "unreadable" and "clean" have to stay distinguishable.

`grep -F "$value" file | grep -vE '^\s*#' | grep -qvF "$key"` IS A THREE-STAGE
PIPELINE AND IS REPRODUCED STAGE BY STAGE. Read it as: the lines containing the
VALUE, minus the comment lines, minus the lines that also name the KEY; if
anything survives, that file restates the pin. Collapsing it into one pass over
the file would be equivalent only by accident, because the second stage drops
comment lines by their own shape rather than by the match's position.

THE A9 SUBSHELL IS STILL A SUBSHELL. `bash -c "source toolchain.sh;
toolchain_pin_for shfmt"` is what A9 exists to run, and re-reading
`toolchain.env` in Python would test this module's idea of the loader rather
than the loader. The twin swallows both a crash and an empty pin into the same
"bad" answer, and says so in a `swallowed-failure-ok` waiver: "either a crash or
a genuinely empty pin makes t bad on the next line, so the cause does not change
the outcome".

`git ls-files` PATHSPECS ARE PASSED TO GIT UNCHANGED, including the deliberate
`.ci/*.sh` spelling. Re-implementing the walk in Python would silently re-decide
the `*`-crosses-`/` question that paragraph is about.

STREAMS. `fail()` is `✗ <msg>` on STDERR and `pass()` is `ok   <msg>` on STDOUT,
neither through a logger. The A1/A2/A8 detail lists follow their `✗` on STDERR;
the A10 detail list goes to STDOUT with a nine-space indent, which is an
inconsistency in the twin and is preserved because moving it would change which
stream a reader greps.
"""

import fnmatch
import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

_ANSI = {"RED": "\033[0;31m", "GREEN": "\033[0;32m", "NC": "\033[0m"}

PINS_REL = ".devcontainer/toolchain.env"

# The tools a GATE depends on. Editor tooling is deliberately outside; see the
# header for the reason, which CHANGED on 2026-09-06 without changing the list.
GATED_TOOLS = "shfmt|shellcheck|ruff|actionlint"

# The pathspecs A1 and A2 scan. `.ci/*.sh` is the deliberate spelling.
CORPUS_PATHSPECS = (".github/workflows/*.yml", ".devcontainer/*", ".ci/*.sh", "run.sh")

# The pathspecs A6 scans, tracked AND untracked.
GATE_PATHSPECS = (".ci/scripts/quality/*.sh", ".ci/scripts/security/*.sh")

# Files that may legitimately restate a pin: the pins file itself, and anything
# whose job is to talk ABOUT pins (this gate, its test, the resolver).
EXEMPT_EXACT = (
    ".devcontainer/toolchain.env",
    ".ci/scripts/quality/check-toolchain-pins.sh",
    ".ci/scripts/lib/toolchain.sh",
)
EXEMPT_GLOBS = (".ci/scripts/test/gates/test-toolchain*.sh",)

# A3's floor. A pins file that shrank below this is a collapsed corpus, not a
# clean tree.
MIN_KEYS = 5

PIN_LINE_RE = re.compile(r"^[A-Z][A-Z0-9_]*=")
# A pin value containing a quote, a space or a `$`. The Dockerfile and
# $GITHUB_ENV readers cannot parse that.
UNPARSEABLE_PIN_RE = re.compile(r"^[A-Z][A-Z0-9_]*=.*[ \"'$]")

# A9's subjects, in the twin's order.
A9_TOOLS = ("shfmt", "shellcheck", "ruff", "actionlint", "go", "node")


def colours(stream=None, env=None) -> dict[str, str]:
    """`[ -t 1 ] && [ -z "${NO_COLOR:-}" ]`."""
    environ = os.environ if env is None else env
    target = sys.stdout if stream is None else stream
    if environ.get("NO_COLOR"):
        return {"RED": "", "GREEN": "", "NC": ""}
    try:
        tty = bool(target.isatty())
    except (AttributeError, ValueError):
        tty = False
    return dict(_ANSI) if tty else {"RED": "", "GREEN": "", "NC": ""}


class Report:
    """The `fails` counter with its two printers."""

    def __init__(self, colour: dict[str, str] | None = None) -> None:
        self.colour = colours() if colour is None else colour
        self.fails = 0

    def fail(self, message: str) -> None:
        print("%s✗%s %s" % (self.colour["RED"], self.colour["NC"], message), file=sys.stderr)
        self.fails += 1

    def ok(self, message: str) -> None:
        print("%sok%s   %s" % (self.colour["GREEN"], self.colour["NC"], message))


def is_exempt(rel: str) -> bool:
    """May this file legitimately restate a pin?"""
    if rel in EXEMPT_EXACT:
        return True
    return any(fnmatch.fnmatchcase(rel, pattern) for pattern in EXEMPT_GLOBS)


def git_lines(root: pathlib.Path, args: list[str]) -> list[str]:
    """`git -C root <args>` split into lines, or [] on any failure.

    A failed git is [] here exactly as the twin's `2>/dev/null` makes it empty,
    and the A1 vacuity branch is what stops that from reading as a clean tree.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(root), *args],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return []
    if proc.returncode != 0:
        return [line for line in proc.stdout.split("\n") if line != ""]
    return [line for line in proc.stdout.split("\n") if line != ""]


def scan_corpus(root: pathlib.Path) -> list[str]:
    """A1/A2's corpus. The pathspecs are handed to git unchanged."""
    return git_lines(root, ["ls-files", *CORPUS_PATHSPECS])


def read_lines(path: pathlib.Path) -> list[str]:
    """A file's lines, or [] when it cannot be read."""
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def restates(path: pathlib.Path, key: str, value: str) -> bool:
    """`grep -F value | grep -vE '^\\s*#' | grep -qvF key`, stage by stage."""
    hits = [line for line in read_lines(path) if value in line]
    hits = [line for line in hits if not re.match(r"^[ \t]*#", line)]
    return any(key not in line for line in hits)


def check_a3(report: Report, pins: pathlib.Path) -> int:
    """A3 first: a malformed or tiny pins file makes everything else vacuous.

    Returns the key count, which is 0 when the file is unusable.
    """
    if not os.access(pins, os.R_OK) or not pins.is_file():
        report.fail("A3. pins file missing: %s" % pins)
        return 0
    lines = read_lines(pins)
    n_keys = sum(1 for line in lines if PIN_LINE_RE.match(line))
    if n_keys < MIN_KEYS:
        report.fail(
            "A3. pins file defines only %d key(s) -- a shrinking file must not read as "
            "a clean tree" % n_keys
        )
    elif any(UNPARSEABLE_PIN_RE.match(line) for line in lines):
        report.fail(
            "A3. a pin value contains a quote, space or $ -- the Dockerfile and "
            "$GITHUB_ENV readers cannot parse that"
        )
    else:
        report.ok("A3. pins file defines %d keys, all plain KEY=value" % n_keys)
    return n_keys


def pin_entries(pins: pathlib.Path) -> list[tuple[str, str]]:
    """Every `KEY=value` in the pins file, with `IFS='='` semantics.

    `read -r key value` under `IFS='='` puts everything after the FIRST `=` into
    `value`, separators included, so `K=a=b` is ("K", "a=b").
    """
    out: list[tuple[str, str]] = []
    for line in read_lines(pins):
        if not PIN_LINE_RE.match(line):
            continue
        key, _, value = line.partition("=")
        if key and value:
            out.append((key, value))
    return out


def check_a1(report: Report, root: pathlib.Path, pins: pathlib.Path) -> int:
    """A1: one definition per pin. Returns the number of files scanned."""
    corpus = scan_corpus(root)
    dupes: list[str] = []
    for key, value in pin_entries(pins):
        # NODE_VERSION/GO_VERSION are also expressed as bare majors by
        # third-party actions and by go.mod, which are not ours to unify.
        if key in ("NODE_VERSION", "GO_VERSION"):
            continue
        for rel in corpus:
            if rel == "" or is_exempt(rel):
                continue
            target = root / rel
            if not target.is_file():
                continue
            if restates(target, key, value):
                dupes.append("%s restates %s=%s" % (rel, key, value))

    scanned = len(corpus)
    if scanned == 0:
        report.fail(
            "A1. scanned ZERO files -- the glob matched nothing, so this assertion is vacuous"
        )
    elif not dupes:
        report.ok("A1. no pin value is restated across %d file(s)" % scanned)
    else:
        report.fail("A1. a pin is defined in more than one place:")
        for entry in dupes:
            print("     %s" % entry, file=sys.stderr)
    return scanned


UNPINNED_RE = re.compile(
    r"(%s)[^ ]*@latest|releases/latest/download[^ ]*(%s)" % (GATED_TOOLS, GATED_TOOLS)
)


def check_a2(report: Report, root: pathlib.Path) -> None:
    """A2: nothing acquires a gate tool unpinned."""
    unpinned: list[str] = []
    for rel in scan_corpus(root):
        if rel == "" or is_exempt(rel):
            continue
        target = root / rel
        if not target.is_file():
            continue
        for line in read_lines(target):
            if not UNPINNED_RE.search(line):
                continue
            # `case "$line" in \#*)` skips only a line whose FIRST character is
            # `#`, so an indented comment still counts. That is the twin's.
            if line.startswith("#"):
                continue
            unpinned.append("%s: %s" % (rel, line.lstrip(" \t")))
    if not unpinned:
        report.ok("A2. no gate tool is acquired unpinned")
    else:
        report.fail("A2. a gate tool is acquired without a version:")
        for entry in unpinned:
            print("     %s" % entry, file=sys.stderr)


A8_HIT_RE = re.compile(r"^[ \t]*(run:|-)?[ \t]*[^#]*(^|[;&|\s])(%s)[ \t]+-" % GATED_TOOLS)
A8_DROP_RE = re.compile(r"\.sh|install|--version|uvx|name:|#")


def check_a8(report: Report, root: pathlib.Path) -> None:
    """A8: a WORKFLOW must not invoke a pinned tool directly."""
    hits: list[str] = []
    workflows = sorted((root / ".github" / "workflows").glob("*.yml"))
    for path in workflows:
        for number, line in enumerate(read_lines(path), start=1):
            if A8_HIT_RE.search(line) and not A8_DROP_RE.search(line):
                hits.append("%s:%d:%s" % (path, number, line))
    if not hits:
        report.ok("A8. no workflow invokes a pinned tool directly")
    else:
        report.fail("A8. a workflow runs a pinned tool itself instead of via its gate script:")
        for entry in hits:
            print("     %s" % entry, file=sys.stderr)


# A6's three drop filters and its invocation matcher, in the twin's order.
A6_COMMENT_RE = re.compile(r"^[ \t]*#")
A6_PROSE_RE = re.compile(r"^[ \t]*(echo|printf)[ \t][^;&|]*$")
A6_ARRAY_RE = re.compile(r"^[ \t]*[A-Za-z_][A-Za-z0-9_]*=\([^)]*\)[ \t]*$")
A6_INVOKE_RE = re.compile(r"(^|[;&|(]|[ \t])(%s)[ \t]" % GATED_TOOLS)
A6_ACQUIRE_RE = re.compile(r"toolchain_acquire|toolchain_check|ensure_actionlint")


def invokes_gated_tool(lines: list[str]) -> bool:
    """Does this file RUN a gated tool, as opposed to naming one?

    Three drops, then the invocation match. Each drop is a separate `grep -v` in
    the twin and each has its own incident behind it; see the header.
    """
    kept = [line for line in lines if not A6_COMMENT_RE.match(line)]
    kept = [line for line in kept if not A6_PROSE_RE.match(line)]
    kept = [line for line in kept if not A6_ARRAY_RE.match(line)]
    return any(A6_INVOKE_RE.search(line) for line in kept)


def check_a6(report: Report, root: pathlib.Path) -> None:
    """A6: a gate that runs a pinned tool acquires it at the pin."""
    missing: list[str] = []
    corpus = git_lines(root, ["ls-files", *GATE_PATHSPECS])
    corpus += git_lines(root, ["ls-files", "--others", "--exclude-standard", *GATE_PATHSPECS])
    for rel in corpus:
        if rel == "":
            continue
        target = root / rel
        if not target.is_file() or is_exempt(rel):
            continue
        lines = read_lines(target)
        if not invokes_gated_tool(lines):
            continue
        if not any(A6_ACQUIRE_RE.search(line) for line in lines):
            missing.append(rel)
    if not missing:
        report.ok("A6. each pinned-tool gate acquires its tool at the pin")
    else:
        report.fail("A6. these trust PATH instead of acquiring at the pin: %s" % " ".join(missing))


def pin_from_bare_source(library: pathlib.Path, tool: str) -> str:
    """`bash -c "source <lib>; toolchain_pin_for <tool>"`. Never raises.

    swallowed-failure-ok in the twin, and the reason is quoted there: "either a
    crash or a genuinely empty pin makes t bad on the next line, so the cause
    does not change the outcome".
    """
    try:
        proc = subprocess.run(
            ["bash", "-c", "source '%s'; toolchain_pin_for %s" % (library, tool)],
            stdout=subprocess.PIPE,
            stderr=subprocess.DEVNULL,
            text=True,
            check=False,
        )
    except OSError:
        return ""
    return proc.stdout


def check_a9(report: Report, root: pathlib.Path) -> None:
    """A9: every pin resolves to a non-empty value from a bare source."""
    library = root / ".ci" / "scripts" / "lib" / "toolchain.sh"
    bad = [tool for tool in A9_TOOLS if pin_from_bare_source(library, tool) == ""]
    if not bad:
        report.ok("A9. every pin resolves to a non-empty value from a bare source")
    else:
        report.fail("A9. these pins resolve EMPTY (did toolchain_load run?): %s" % " ".join(bad))


# A10's three mechanisms, each checked for what it actually DOES.
A10_SOURCE_RE = re.compile(r"(\.|source)[ \t]+\"?\$\{?_REDIACC_TOOLCHAIN_ENV")
A10_COPY_RE = re.compile(r"^[ \t]*COPY[ \t]+toolchain\.env")
A10_ENV_RE = re.compile(r"toolchain\.sh[ \t]+--env[ \t]*>>[ \t]*\"?\$\{?GITHUB_ENV")


def check_a10(report: Report, root: pathlib.Path) -> None:
    """A10: all THREE readers (bash, Docker, Actions) still read the pins."""
    bad: list[str] = []
    consts = root / ".ci" / "config" / "constants.sh"
    dockerfile = root / ".devcontainer" / "Dockerfile"

    # bash: constants.sh must SOURCE it, not merely name it.
    if not consts.is_file():
        bad.append("constants.sh is missing entirely")
    else:
        lines = [line for line in read_lines(consts) if not A6_COMMENT_RE.match(line)]
        if not any(A10_SOURCE_RE.search(line) for line in lines):
            bad.append("constants.sh no longer sources the pins file")

    # Docker: the image must COPY it in, or the container's tools are unpinned.
    if not dockerfile.is_file():
        bad.append("Dockerfile is missing entirely")
    else:
        lines = [line for line in read_lines(dockerfile) if not A6_COMMENT_RE.match(line)]
        if not any(A10_COPY_RE.search(line) for line in lines):
            bad.append("Dockerfile no longer COPYs toolchain.env into the image")

    # Actions: some workflow must feed the pins into $GITHUB_ENV, via --env.
    found = False
    workflows = root / ".github" / "workflows"
    if workflows.is_dir():
        for dirpath, _dirnames, filenames in os.walk(workflows):
            for name in filenames:
                path = pathlib.Path(dirpath) / name
                if any(A10_ENV_RE.search(line) for line in read_lines(path)):
                    found = True
                    break
            if found:
                break
    if not found:
        bad.append("no workflow feeds the pins into $GITHUB_ENV via toolchain.sh --env")

    if not bad:
        report.ok("A10. all three readers (bash, Docker, Actions) still read the pins")
    else:
        report.fail("A10. a pin reader went dark, so the pins are decorative for that lane:")
        # STDOUT, with a nine-space indent. An inconsistency in the twin; see
        # the port notes on streams.
        for entry in bad:
            print("         %s" % entry)


def run_controls(report: Report, root: pathlib.Path, tmp: pathlib.Path) -> None:
    """Every control, by CONSTRUCTION. Fixtures written literally, never sampled.

    A control built by substituting into real source stops controlling anything
    the day that source is reworded, which is what
    `check-control-vacuity.sh` exists to catch.
    """
    control_dir = tmp / "c"
    control_dir.mkdir(parents=True, exist_ok=True)

    # -- A8 controls -------------------------------------------------------
    wf_direct = control_dir / "wf-direct.yml"
    wf_direct.write_text("        run: shfmt -d .\n", encoding="utf-8")
    if any(
        re.search(r"(^|[;&|\s])(%s)[ \t]+-" % GATED_TOOLS, line) for line in read_lines(wf_direct)
    ):
        report.ok("A8 control: a workflow running the tool directly is detected")
    else:
        report.fail("A8 CONTROL DID NOT FIRE: a direct tool invocation went undetected")

    wf_script = control_dir / "wf-script.yml"
    wf_script.write_text("        run: .ci/scripts/security/shfmt.sh\n", encoding="utf-8")
    matched = [
        line
        for line in read_lines(wf_script)
        if re.search(r"(^|[;&|\s])(%s)[ \t]+-" % GATED_TOOLS, line)
    ]
    if any(not re.search(r"\.sh|install|--version|uvx", line) for line in matched):
        report.fail(
            "A8 IS OVER-BROAD: running the gate SCRIPT was flagged, and that is the "
            "required pattern"
        )
    else:
        report.ok("A8 control: invoking the gate script is not flagged")

    # -- A9 control, by construction: a copy plus an APPENDED no-op override --
    a9_dir = tmp / "a9"
    a9_dir.mkdir(parents=True, exist_ok=True)
    library = root / ".ci" / "scripts" / "lib" / "toolchain.sh"
    mutant = a9_dir / "toolchain.sh"
    try:
        shutil.copyfile(library, mutant)
    except OSError:
        mutant.write_text("", encoding="utf-8")
    with mutant.open("a", encoding="utf-8") as handle:
        handle.write("\ntoolchain_load() { return 0; }\n")
    if any("toolchain_load() { return 0; }" in line for line in read_lines(mutant)):
        # This IS the control: empty is the tested-for outcome (the mutant skips
        # the load), and the next branch treats non-empty as the failure.
        ctl = pin_from_bare_source(mutant, "shellcheck")
        if ctl == "":
            report.ok("A9 control: a library that skips the load is detectable")
        else:
            report.fail("A9 CONTROL DID NOT FIRE: the mutant still resolved a pin ('%s')" % ctl)
    else:
        report.fail("A9 CONTROL WAS NOT PLANTED: the mutant library is unmodified")

    # -- A1 controls -------------------------------------------------------
    (control_dir / "pins.env").write_text("RUFF_VERSION=9.9.9\n", encoding="utf-8")
    restates_yml = control_dir / "restates.yml"
    restates_yml.write_text('run: pip install "ruff==9.9.9"\n', encoding="utf-8")
    if restates(restates_yml, "RUFF_VERSION", "9.9.9"):
        report.ok("control: a restated pin value is detectable")
    else:
        report.fail("A1 CONTROL DID NOT FIRE: a restated value went undetected")

    reads_yml = control_dir / "reads.yml"
    reads_yml.write_text('run: pip install "ruff==${RUFF_VERSION}"\n', encoding="utf-8")
    if restates(reads_yml, "RUFF_VERSION", "9.9.9"):
        report.fail("A1 IS OVER-BROAD: a line READING the pin was flagged as restating it")
    else:
        report.ok("control: a line reading the pin is not flagged")

    # -- A2 control --------------------------------------------------------
    unpinned_sh = control_dir / "unpinned.sh"
    unpinned_sh.write_text("go install mvdan.cc/sh/v3/cmd/shfmt@latest\n", encoding="utf-8")
    if any(re.search(r"(%s)[^ ]*@latest" % GATED_TOOLS, line) for line in read_lines(unpinned_sh)):
        report.ok("control: an unpinned gate-tool install is detectable")
    else:
        report.fail("A2 CONTROL DID NOT FIRE: @latest went undetected")

    # -- A6 controls -------------------------------------------------------
    unpinned_gate = control_dir / "unpinned-gate.sh"
    unpinned_gate.write_text(
        "#!/usr/bin/env bash\nshellcheck -S warning foo.sh\n", encoding="utf-8"
    )
    lines = read_lines(unpinned_gate)
    kept = [line for line in lines if not A6_COMMENT_RE.match(line)]
    if any(A6_INVOKE_RE.search(line) for line in kept) and not any(
        re.search(r"toolchain_acquire|toolchain_check|[A-Z]+_VERSION", line) for line in lines
    ):
        report.ok("A6 control: a gate invoking a tool with no pin is detected")
    else:
        report.fail("A6 CONTROL DID NOT FIRE: an unpinned tool invocation went undetected")

    # A6 SELF-PROSE CONTROL. A6 flagged check-shell-size.sh for two `echo` lines
    # PRINTING the shellcheck directive it tells you to add; the gate invoked
    # nothing. A detector that matches its own documentation cannot be satisfied
    # except by deleting the explanation, so prove it does not.
    prose_gate = control_dir / "prose-gate.sh"
    prose_gate.write_text(
        "#!/usr/bin/env bash\n"
        "# this gate never runs shellcheck itself, it only greps for it\n"
        'echo "  # shellcheck extended-analysis=false"\n',
        encoding="utf-8",
    )
    if invokes_gated_tool(read_lines(prose_gate)):
        report.fail("A6 IS OVER-BROAD: a comment and an echoed string read as an invocation")
    else:
        report.ok("A6 control: naming a tool in prose or an echo is not invoking it")

    # A6 ARRAY-LITERAL CONTROL. A `NAME=(...)` definition naming a gated tool is
    # DATA, not an invocation.
    array_gate = control_dir / "array-literal-gate.sh"
    array_gate.write_text(
        "#!/usr/bin/env bash\n"
        "# this gate only reads NPX_TOOLS from another file, it never runs any of them\n"
        "NPX_TOOLS=(ruff go shfmt shellcheck actionlint)\n",
        encoding="utf-8",
    )
    if invokes_gated_tool(read_lines(array_gate)):
        report.fail("A6 IS OVER-BROAD: an array literal defining tool names reads as an invocation")
    else:
        report.ok("A6 control: naming a tool inside an array literal is not invoking it")

    pinned_gate = control_dir / "pinned-gate.sh"
    pinned_gate.write_text(
        '#!/usr/bin/env bash\nBIN="$(toolchain_acquire shellcheck)"\n', encoding="utf-8"
    )
    if any(
        re.search(r"toolchain_acquire|toolchain_check|[A-Z]+_VERSION", line)
        for line in read_lines(pinned_gate)
    ):
        report.ok("A6 control: a gate that resolves at the pin is not flagged")
    else:
        report.fail("A6 IS OVER-BROAD: a correctly pinned gate was flagged")

    # -- A10 controls ------------------------------------------------------
    a10_dir = tmp / "a10"
    a10_dir.mkdir(parents=True, exist_ok=True)
    fake_consts = a10_dir / "fake-consts.sh"
    fake_consts.write_text(
        "# we load .devcontainer/toolchain.env somewhere else\necho hi\n", encoding="utf-8"
    )
    if any(
        A10_SOURCE_RE.search(line)
        for line in read_lines(fake_consts)
        if not A6_COMMENT_RE.match(line)
    ):
        report.fail(
            "A10 CONTROL DID NOT FIRE: a comment mentioning the pins file counted as reading it"
        )
    else:
        report.ok("A10 control: a comment mentioning the pins file does not count as reading it")

    real_consts = a10_dir / "real-consts.sh"
    real_consts.write_text('# real\n. "${_REDIACC_TOOLCHAIN_ENV}"\n', encoding="utf-8")
    if any(
        A10_SOURCE_RE.search(line)
        for line in read_lines(real_consts)
        if not A6_COMMENT_RE.match(line)
    ):
        report.ok("A10 control: a genuine source line is recognised")
    else:
        report.fail("A10 IS OVER-BROAD: a real source of the pins file was not recognised")

    fake_dockerfile = a10_dir / "Dockerfile"
    fake_dockerfile.write_text(
        "# COPY toolchain.env -- described, not done\nRUN true\n", encoding="utf-8"
    )
    if any(
        A10_COPY_RE.search(line)
        for line in read_lines(fake_dockerfile)
        if not A6_COMMENT_RE.match(line)
    ):
        report.fail("A10 CONTROL DID NOT FIRE: a commented-out COPY counted as copying")
    else:
        report.ok("A10 control: a commented-out COPY does not count")

    # -- A2 over-breadth ---------------------------------------------------
    editor_sh = control_dir / "editor.sh"
    editor_sh.write_text("go install golang.org/x/tools/gopls@latest\n", encoding="utf-8")
    if any(re.search(r"(%s)[^ ]*@latest" % GATED_TOOLS, line) for line in read_lines(editor_sh)):
        report.fail("A2 IS OVER-BROAD: editor tooling was flagged as a gate tool")
    else:
        report.ok("control: editor tooling at @latest is not flagged")


def main(argv: list[str] | None = None) -> int:
    """Run A3, A1, A2, A8, A6, A9, A10 and the controls. 0 clean, 1 failure."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    pins = root / PINS_REL
    report = Report()

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)
        # A3 FIRST: a malformed or tiny pins file makes everything else vacuous.
        check_a3(report, pins)
        scanned = check_a1(report, root, pins)
        check_a2(report, root)
        check_a8(report, root)
        # The A8 controls sit here in the twin, between A8 and A6, because the
        # shared fixture dir is created in the controls section further down and
        # writing before it exists made them silently write nothing.
        check_a6(report, root)
        check_a9(report, root)
        check_a10(report, root)
        run_controls(report, root, tmpdir)

    print()
    if report.fails == 0:
        print(
            "%s✓%s toolchain pins: single-sourced across %d file(s)."
            % (report.colour["GREEN"], report.colour["NC"], scanned)
        )
        print("  Blind spot, stated so a green is not read as more than it is: A1 is a")
        print("  LITERAL scan, so a pin written 0.16 against a value of 0.16.1 escapes it.")
        return 0
    print(
        "%s✗%s toolchain pins: %d failure(s)."
        % (report.colour["RED"], report.colour["NC"], report.fails)
    )
    return 1


def selftest() -> int:
    """Both directions on every matcher. The twin's own controls run inline."""
    ctl = Controls("toolchain-pins", floor=31, verbose=True)
    plain = {"RED": "", "GREEN": "", "NC": ""}

    with tempfile.TemporaryDirectory() as tmp:
        tmpdir = pathlib.Path(tmp)

        # -- is_exempt ------------------------------------------------------
        ctl.truthy(
            "CONTROL: the pins file itself may restate a pin",
            is_exempt(".devcontainer/toolchain.env"),
        )
        ctl.truthy(
            "CONTROL: this gate may restate a pin",
            is_exempt(".ci/scripts/quality/check-toolchain-pins.sh"),
        )
        ctl.truthy(
            "CONTROL: the gate test glob is exempt",
            is_exempt(".ci/scripts/test/gates/test-toolchain-pins.sh"),
        )
        ctl.falsy(
            "MIRROR: an ordinary workflow is not exempt", is_exempt(".github/workflows/ci.yml")
        )
        ctl.falsy(
            "MIRROR: a NEIGHBOURING gate is not exempt just because the name is close",
            is_exempt(".ci/scripts/quality/check-toolchain-env-dockerfile-sync.sh"),
        )

        # -- restates, the three-stage pipeline ----------------------------
        target = tmpdir / "t.yml"
        target.write_text('run: pip install "ruff==9.9.9"\n', encoding="utf-8")
        ctl.truthy(
            "PLANT: a literal copy of the value is a restatement",
            restates(target, "RUFF_VERSION", "9.9.9"),
        )
        target.write_text('run: pip install "ruff==${RUFF_VERSION}"\n', encoding="utf-8")
        ctl.falsy(
            "MIRROR: a line READING the pin is not a restatement",
            restates(target, "RUFF_VERSION", "9.9.9"),
        )
        target.write_text("# we bumped ruff to 9.9.9 last week\n", encoding="utf-8")
        ctl.falsy(
            "MIRROR: a COMMENT naming the value is prose, not a definition",
            restates(target, "RUFF_VERSION", "9.9.9"),
        )
        target.write_text("    # indented prose about 9.9.9\n", encoding="utf-8")
        ctl.falsy(
            "MIRROR: an INDENTED comment is still a comment",
            restates(target, "RUFF_VERSION", "9.9.9"),
        )
        target.write_text("nothing to see\n", encoding="utf-8")
        ctl.falsy(
            "MIRROR: a file that never names the value is clean",
            restates(target, "RUFF_VERSION", "9.9.9"),
        )

        # -- A3's two failure shapes ---------------------------------------
        pins = tmpdir / "toolchain.env"
        report = Report(colour=plain)
        pins.write_text("A=1\nB=2\nC=3\nD=4\nE=5\n", encoding="utf-8")
        ctl.check("CONTROL: five plain keys satisfy A3", check_a3(report, pins), 5)
        ctl.check("CONTROL: and nothing failed", report.fails, 0)
        report = Report(colour=plain)
        pins.write_text("A=1\nB=2\n", encoding="utf-8")
        check_a3(report, pins)
        ctl.check("PLANT: a SHRINKING pins file is a failure, not a clean tree", report.fails, 1)
        report = Report(colour=plain)
        pins.write_text("A=1\nB=2\nC=3\nD=4\nE=has a space\n", encoding="utf-8")
        check_a3(report, pins)
        ctl.check("PLANT: a value with a space is unparseable by the two readers", report.fails, 1)
        report = Report(colour=plain)
        check_a3(report, tmpdir / "gone.env")
        ctl.check("VACUITY: an absent pins file is a FAILURE", report.fails, 1)

        # -- pin_entries ----------------------------------------------------
        pins.write_text("A=1\n# comment\nlowercase=2\nB=a=b\n\n", encoding="utf-8")
        ctl.check(
            "CONTROL: only uppercase KEY=value lines are pins, and IFS='=' keeps the rest",
            pin_entries(pins),
            [("A", "1"), ("B", "a=b")],
        )

        # -- A6's invocation matcher, all four directions -------------------
        ctl.truthy(
            "PLANT: a bare `shellcheck -S warning f.sh` is an invocation",
            invokes_gated_tool(["shellcheck -S warning foo.sh"]),
        )
        ctl.falsy(
            "MIRROR: a comment naming the tool is not",
            invokes_gated_tool(["# run shellcheck here"]),
        )
        ctl.falsy(
            "MIRROR: an echoed string naming the tool is not (2026-08-26)",
            invokes_gated_tool(['echo "# shellcheck extended-analysis=false"']),
        )
        ctl.falsy(
            "MIRROR: an array literal naming the tool is DATA (2026-08-28)",
            invokes_gated_tool(["NPX_TOOLS=(ruff go shfmt shellcheck actionlint)"]),
        )
        ctl.truthy(
            "PLANT: `echo x; shfmt y` is still scrutinised, so the echo drop is not a bypass",
            invokes_gated_tool(["echo x; shfmt -d ."]),
        )

        # -- A8's matcher ---------------------------------------------------
        ctl.truthy(
            "PLANT: a workflow running the tool directly matches",
            bool(A8_HIT_RE.search("        run: shfmt -d .")),
        )
        ctl.truthy(
            "MIRROR: invoking the gate SCRIPT is dropped by the second filter",
            bool(A8_DROP_RE.search("        run: .ci/scripts/security/shfmt.sh")),
        )

        # -- A2's matcher ---------------------------------------------------
        ctl.truthy(
            "PLANT: an @latest gate-tool install matches",
            bool(UNPINNED_RE.search("go install mvdan.cc/sh/v3/cmd/shfmt@latest")),
        )
        ctl.falsy(
            "MIRROR: editor tooling at @latest does not",
            bool(UNPINNED_RE.search("go install golang.org/x/tools/gopls@latest")),
        )
        ctl.truthy(
            "PLANT: a releases/latest download of a gate tool matches",
            bool(UNPINNED_RE.search("curl -L https://x/releases/latest/download/shellcheck.tar")),
        )

        # -- A10's three mechanisms -----------------------------------------
        ctl.truthy(
            "CONTROL: a genuine source line is recognised",
            bool(A10_SOURCE_RE.search('. "${_REDIACC_TOOLCHAIN_ENV}"')),
        )
        ctl.falsy(
            "MIRROR: naming the pins file in prose is not sourcing it",
            bool(A10_SOURCE_RE.search("# we load .devcontainer/toolchain.env somewhere else")),
        )
        ctl.truthy(
            "CONTROL: a real COPY line is recognised",
            bool(A10_COPY_RE.search("COPY toolchain.env /tmp/")),
        )
        ctl.truthy(
            "CONTROL: the --env emitter into $GITHUB_ENV is recognised",
            bool(A10_ENV_RE.search('  .ci/scripts/lib/toolchain.sh --env >> "$GITHUB_ENV"')),
        )
        ctl.falsy(
            "MIRROR: a bare `cat toolchain.env >> $GITHUB_ENV` is NOT the emitter",
            bool(A10_ENV_RE.search('cat toolchain.env >> "$GITHUB_ENV"')),
        )

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
