"""A script that INSTALLS a Go tool must be able to FIND it.

Ported from `.ci/scripts/quality/check-go-tool-path.sh`, which is NOT deleted;
see `rediacc_ci.quality.__init__` for why both copies live side by side until a
committed differential ledger says otherwise.

WHY THE TWIN EXISTS, carried over from its header because the archaeology is the
half of a gate that cannot be recovered from the code:

  `go install` writes to $(go env GOPATH)/bin, and nothing puts that directory on
  PATH. A script that installs a tool and then invokes it by bare name therefore
  reports a successful install and dies on the very next line with
  `command not found`, exit 127, taking its whole stage with it.

  Measured 2026-08-27 in private/renet: FOUR scripts did exactly this --
  quality/format.sh (goimports), quality/lint.sh (golangci-lint),
  quality/deadcode.sh (deadcode) and test/run-tests.sh (gotestsum). Patching the
  first only moved the failure to the second. `npm run check:ci-renet` exited 127
  about a second in, which also made its "fast" tier a measurement of crashing
  early rather than of running.

  AND IT IS INVISIBLE WHERE IT IS TESTED. CI never hits it, because
  actions/setup-go puts $(go env GOPATH)/bin on PATH itself. So the family is
  green in the one place nobody debugs and fatal in the one place people do,
  which is why it survived long enough to be four instances.

  THE SANCTIONED SHAPE, already used by this repo. .ci/scripts/lib/toolchain.sh
  installs with GOBIN pointed at a cache dir and then invokes the tool by
  ABSOLUTE path. That needs no PATH at all and is why check:ci-shell-format
  passes on a host with no shfmt anywhere on PATH. Any of these satisfy the gate:

      GOBIN="$dir" go install ...   then run "$dir/tool"     (preferred)
      PATH="$(go env GOPATH)/bin:$PATH"  before the invocation
      invoke via an absolute or $-prefixed path rather than a bare name

  SCOPE. Tracked shell scripts under .ci/ and scripts/. The submodule has its own
  CI and its own copy of this problem, already fixed at its root in
  .ci/scripts/lib/common.sh; this gate keeps console from growing a fifth.

The twin's gate header also records why it is registered with `emit: false`, and
that reason is about WIRING rather than about go tools, so it stays with the bash
file: the step "runs before this lane's `- id: setup` step, so its hand-written
step carries no `steps.setup.outcome` guard. Emitting it into the region would
move it below that guard and skip it whenever setup fails." A port inherits no
registration, so nothing here re-states that as a live suppression.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE PATHSPEC IS `.ci/*.sh`, NOT `.ci/**/*.sh`, AND THAT IS LOAD-BEARING. The
twin says so in six lines and they are carried here because the wrong spelling
is the one a reader would "correct" to: git's default (non-`:(glob)`) wildmatch
lets `*` cross `/`, so `.ci/*.sh` already reaches every depth, while
`.ci/**/*.sh` demands a literal slash after `.ci/` and therefore MISSES every
script sitting directly under `.ci/`. Measured 2026-09-06 when .ci/bootstrap.sh
became the first file in that class: the two spellings return the same 453
tracked files, and only the second one drops bootstrap.sh.

THE FLOOR IS 50 AND IT IS COUNTED FROM THE TRACKED LIST, not from the
filesystem, so a stray untracked file cannot prop the number up. Below it the
gate FAILS rather than passing quietly: a glob that silently matches nothing
would make it green forever while checking not one line.

`grep -n` NUMBERS THE FILTERED STREAM, NOT THE FILE, and the port reproduces
that faithfully. The twin pipes the body through `grep -vE '^[[:space:]]*#'`
BEFORE `grep -nE`, so every comment line is removed and the numbers that reach
the operator count only the surviving lines. In a file with a 40-line header the
reported number is off by 40. That is a real defect in the twin -- the numbers
look like file line numbers and are not -- and it is REPORTED rather than
repaired here, because repairing it would change the finding text and the port's
job is to keep the verdict.

THE COLOUR IS UNCONDITIONAL IN THE TWIN, unlike every sibling gate. `pass` and
`fail` here `printf` raw `\033[0;31m` and `\033[0;32m` with no `[ -t 1 ]` test,
no `NO_COLOR` test and no `CI` test, so this gate writes escape sequences into
every CI log and every pipe. check-git-op-conditionals.sh and
check-host-toolchain-coverage.sh, written by the same hand, both gate their
colour on `[ -t 1 ] && [ -z "${NO_COLOR:-}" ]`. Carried unchanged and reported;
`scripts/lib/shadow-gate.ts` strips ANSI before comparing, so this costs the
differential nothing and costs a human reading a log a little.

FINDINGS GO TO STDOUT IN THE TWIN. `fail()` has no `>&2`, so every finding, the
floor refusal and the final `N finding(s).` line all land on stdout. That is the
opposite of `rediacc_ci.log`'s rule (messages on stderr, stdout is data), so the
port uses `print()` for exactly these lines and says so at each call site rather
than silently moving a stream. A stream swap is precisely the 2026-09-06
emit-advisory incident, and moving one during a port is how it would happen
again.

`[[:space:]]` IS NOT `\\s`. POSIX space is exactly [ \\t\\n\\v\\f\\r]; Python's
`\\s` on a str pattern additionally matches U+00A0 and friends, so a line
indented with a non-breaking space would be seen by the port and not by grep.
The class is written out rather than abbreviated. grep also works line by line,
so the `\\n` member can never participate in a match -- stated because its
presence in the class otherwise looks like a bug when read next to `re.MULTILINE`.

WHAT THIS GATE STILL CANNOT SEE, unchanged by the port and worth knowing before
anyone trusts a green: the analysis is per-FILE, so a GOBIN mention anywhere in
a file clears every bare invocation in it, including ones on a code path the
GOBIN line never runs on. That is the twin's deliberate trade -- the install and
the invocation are usually several lines apart, and a PATH fix anywhere above the
call site is what actually makes it work -- and widening it would flag correct
code, which is how a gate gets suppressed.
"""

import os
import pathlib
import re
import subprocess
import sys
import tempfile

from rediacc_ci import paths
from rediacc_ci.controls import Controls

# POSIX [[:space:]], written out. See the port notes for why `\s` is wrong here.
SPACE = r"[ \t\n\v\f\r]"

# Tools commonly provisioned with `go install`. A bare invocation of one of these
# in a script that also installs it is the defect. The alternation is carried in
# the twin's order, which is not alphabetical and does not need to be.
GO_TOOLS = "goimports|golangci-lint|govulncheck|gotestsum|deadcode|staticcheck|shfmt|gopls|mockgen"

# The pathspecs the twin hands to `git ls-files`. See the port notes: the single
# `*` is deliberate and the `**` spelling is a bug, not a tidy-up.
PATHSPECS = (".ci/*.sh", "scripts/*.sh")

# ANTI-VACUITY FLOOR. Fewer tracked shell files than this and the gate refuses.
MIN_FILES = 50

# The twin's colour, emitted unconditionally. See the port notes.
RED = "\033[0;31m"
GREEN = "\033[0;32m"
NC = "\033[0m"

# Does the file provision a go tool at all? `(^|[[:space:];&|])` in the twin.
_INSTALLS = re.compile(r"(^|[ \t;&|])go[ \t]+install[ \t]")

# An explicit GOBIN, or a PATH that includes GOPATH/bin, is the fix. Either
# anywhere in the file clears it; see the per-FILE note in the module docstring.
_FIXED = re.compile(r"GOBIN=|go env GOPATH.*bin|GOPATH_BIN|_go_bin")

# A comment line, dropped before the numbering grep. This is the filter that
# makes the reported numbers count the surviving lines rather than the file's.
_COMMENT = re.compile(r"^[ \t]*#")

# Is a go tool invoked by BARE name? The three openers are: line start, one of
# the shell separators, or the literal `$(`. The trailing space class is what
# stops a bare mention at end-of-line from counting.
_BARE = re.compile(r"(^|[ \t;&|(]|\$\()[ \t]*(%s)[ \t]" % GO_TOOLS)

# A path-qualified call ($x/tool, ./tool, /usr/bin/tool, "$VAR") already resolves
# without PATH, and a mention inside a string is not an invocation. `grep -vE`
# in the twin, so a line matching this is DROPPED however else it looked.
_QUALIFIED = re.compile(r"[/\"'$](%s)" % GO_TOOLS)


def installs_go_tool(body: str) -> bool:
    """`grep -qE '(^|[[:space:];&|])go[[:space:]]+install[[:space:]]'`.

    Exported so a test can drive it without a file on disk. Line-oriented,
    because grep is: a match must sit entirely inside one physical line.
    """
    return any(_INSTALLS.search(line) for line in body.split("\n"))


def has_path_fix(body: str) -> bool:
    """`grep -qE 'GOBIN=|go env GOPATH.*bin|GOPATH_BIN|_go_bin'`. Any line clears the file."""
    return any(_FIXED.search(line) for line in body.split("\n"))


def bare_invocations(body: str) -> list[str]:
    """The twin's `hits`: `<n>:<line>` for each bare invocation, numbers and all.

    THE NUMBERS COUNT THE FILTERED STREAM. Comment lines are removed first and
    the numbering starts after that, so these are NOT file line numbers. See the
    port notes; this is a defect being preserved, not introduced.

    `printf '%s' "$body"` in the twin drops the trailing newline, so a file
    ending in `\\n` does not contribute a final empty line. `split("\\n")` would
    produce one, and an empty string matches neither pattern, so the two agree
    without a guard -- stated because the absence of one looks like an oversight.
    """
    out: list[str] = []
    number = 0
    for line in body.split("\n"):
        if _COMMENT.match(line):
            continue
        number += 1
        if _BARE.search(line) and not _QUALIFIED.search(line):
            out.append("%d:%s" % (number, line))
    return out


def scan_file(path: pathlib.Path, label: str) -> list[str]:
    """The twin's `scan_file`, as the lines it would print. Empty means clean.

    Returned rather than printed so `main` owns every stream decision in one
    place and a test can assert on the decision without capturing anything. The
    first line is the finding header; the rest are its continuation, which is
    what `scripts/lib/shadow-gate.ts` folds into the same finding.

    An unreadable file is NOT a finding. The twin's `cat "$f" 2>/dev/null ||
    return 0` swallows it, and a port that turned it into an error would report
    findings the twin never reports -- on this repo's own tree, where a path in
    the index but deleted from disk is an ordinary state.
    """
    try:
        body = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if not installs_go_tool(body):
        return []
    if has_path_fix(body):
        return []

    hits = bare_invocations(body)
    if not hits:
        return []

    lines = [
        "%s installs a go tool and then invokes one by bare name, "
        "with no GOBIN and no GOPATH/bin on PATH:" % label
    ]
    # `head -3`: only the first three hits are shown, so a file with thirty bad
    # lines prints three. The count is not printed either, which means the
    # operator cannot tell three from thirty. Carried; reported.
    lines.extend("         " + hit for hit in hits[:3])
    lines.append(
        '         FIX: GOBIN="$dir" go install ... then run "$dir/tool", '
        "the shape .ci/scripts/lib/toolchain.sh uses."
    )
    return lines


def tracked_shell_files(root: pathlib.Path) -> list[str]:
    """`git ls-files '.ci/*.sh' 'scripts/*.sh'`, in git's order.

    NOT `rediacc_ci.gitx.ls_files`, which sorts and de-duplicates. The twin
    prints findings in git's own order and the differential compares a multiset,
    so the order costs nothing -- but the COUNT would differ if two pathspecs
    ever overlapped, and the floor is computed from that count. Same command,
    same number.

    A git failure yields an empty list, which the floor then refuses. That is the
    right direction: "git said nothing" and "the tree has no shell scripts" are
    both states in which this gate has verified nothing.
    """
    proc = subprocess.run(
        ["git", "ls-files", *PATHSPECS],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        return []
    return [line for line in proc.stdout.split("\n") if line]


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 clean, 1 violation.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no arguments
    at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    failures = 0

    # STDOUT, deliberately, for every line below. The twin's `fail()` carries no
    # `>&2`; see the port notes. `log.error` would be the house style and would
    # be a stream swap.
    def fail(message: str) -> None:
        nonlocal failures
        print("%s✗%s   %s" % (RED, NC, message))
        failures += 1

    def ok(message: str) -> None:
        print("ok   %s" % message)

    files = tracked_shell_files(root)
    count = len(files)

    # THE FLOOR, AND IT IS A FAILURE RATHER THAN AN ABSTENTION. A green from a
    # gate that saw four files is a statement about four files wearing the
    # sentence "every script that installs a go tool can find it".
    if count < MIN_FILES:
        fail(
            "only %d shell file(s) in scope -- the scan is not reaching the tree, "
            "so a green here would mean nothing" % count
        )
    else:
        ok("scope: %d tracked shell file(s) under .ci/ and scripts/" % count)

    for rel in files:
        for line in scan_file(root / rel, rel):
            if line.startswith("  "):
                print(line)
            else:
                fail(line)

    # --- controls: the gate must be able to FIRE, and must not fire on the fix -
    #
    # Run against fixtures in a scratch dir, because the live tree is expected to
    # be clean and a gate proven only on a clean tree has proven nothing. These
    # are the twin's four fixtures verbatim, kept INLINE (not moved behind
    # `--selftest`) because the twin runs them on every invocation and a port
    # that moved them would change what a plain run proves.
    with tempfile.TemporaryDirectory() as ctl_dir:
        ctl_root = pathlib.Path(ctl_dir)
        for name, text in _CONTROL_FIXTURES.items():
            (ctl_root / name).write_text(text, encoding="utf-8")

        for name, want, label in _CONTROL_CASES:
            fired = bool(scan_file(ctl_root / name, name))
            if want == "fire" and not fired:
                fail(
                    "CONTROL FAILED: %s -- the gate could not fire, so its green means nothing"
                    % label
                )
            elif want == "silent" and fired:
                fail("CONTROL FAILED: %s -- the gate fires on the CORRECT shape" % label)
            else:
                ok("control: %s" % label)

    if failures == 0:
        print("%s✓%s go tool PATH: every script that installs a go tool can find it." % (GREEN, NC))
        return 0
    print("%s✗%s %d finding(s)." % (RED, NC, failures))
    return 1


# The twin's four control fixtures, byte for byte. `bad.sh` is the defect the
# 2026-08-27 renet incident wore four times; the three `good`/`unrelated` files
# are the mirrors that stop this gate from flagging the correct shape.
_CONTROL_FIXTURES = {
    "bad.sh": (
        "#!/usr/bin/env bash\n"
        "go install golang.org/x/tools/cmd/goimports@latest\n"
        "unformatted=$(goimports -l .)\n"
    ),
    "good-gobin.sh": (
        "#!/usr/bin/env bash\n"
        'GOBIN="$cache" go install golang.org/x/tools/cmd/goimports@latest\n'
        'unformatted=$("$cache/goimports" -l .)\n'
    ),
    "good-path.sh": (
        "#!/usr/bin/env bash\n"
        'PATH="$(go env GOPATH)/bin:$PATH"\n'
        "go install golang.org/x/tools/cmd/goimports@latest\n"
        "unformatted=$(goimports -l .)\n"
    ),
    "unrelated.sh": (
        '#!/usr/bin/env bash\necho "this script mentions goimports in prose and installs nothing"\n'
    ),
}

_CONTROL_CASES = (
    ("bad.sh", "fire", "install-then-bare-invoke is detected"),
    ("good-gobin.sh", "silent", "GOBIN plus an absolute path is not flagged"),
    ("good-path.sh", "silent", "extending PATH with GOPATH/bin is not flagged"),
    ("unrelated.sh", "silent", "a script that only MENTIONS a tool is not flagged"),
)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    BOTH DIRECTIONS FOR EVERY CONTROL. A gate with only positive plants will
    happily flag a correct tree, and the mirrors below are the half that proves
    it does not. The whole-gate cases build a REAL git repository, because the
    floor is computed from `git ls-files` and a fixture that skipped git would
    exercise a code path no caller ever takes.
    """
    ctl = Controls("go-tool-path", floor=24, verbose=True)

    bad = _CONTROL_FIXTURES["bad.sh"]

    # -- the three decision helpers, driven directly -------------------------
    ctl.check("installs: a bare `go install` line is seen", installs_go_tool(bad), True)
    ctl.check(
        "installs: `go install` after a semicolon is seen",
        installs_go_tool("cd x; go install foo@latest\n"),
        True,
    )
    # MIRROR: `cargo install` is not `go install`, and neither is a word ending
    # in "go". The opener class is what carries this.
    ctl.check(
        "installs: MIRROR cargo install is not go install",
        installs_go_tool("cargo install x\n"),
        False,
    )
    ctl.check(
        "installs: MIRROR a word ending in go is not go",
        installs_go_tool("django install x\n"),
        False,
    )
    ctl.check(
        "installs: MIRROR `go installer` is not `go install `",
        installs_go_tool("go installer x\n"),
        False,
    )

    ctl.check("fix: GOBIN= clears the file", has_path_fix('GOBIN="$d" go install x\n'), True)
    ctl.check(
        "fix: go env GOPATH ... bin clears it",
        has_path_fix('PATH="$(go env GOPATH)/bin:$PATH"\n'),
        True,
    )
    ctl.check("fix: MIRROR an unrelated file has no fix", has_path_fix(bad), False)

    ctl.check("bare: a bare goimports call is a hit", len(bare_invocations(bad)), 1)
    ctl.check(
        "bare: MIRROR a $-qualified call is not a hit",
        bare_invocations('unformatted=$("$cache/goimports" -l .)\n'),
        [],
    )
    ctl.check(
        "bare: MIRROR a tool at end of line is not a hit",
        bare_invocations("goimports\n"),
        [],
    )
    ctl.check(
        "bare: MIRROR a comment line is skipped",
        bare_invocations("# goimports -l .\n"),
        [],
    )
    # THE NUMBERING DEFECT, PINNED. Two comment lines above the hit and the
    # reported number is 1, not 3. If someone "fixes" the twin, this control
    # fails and points at the sentence in the port notes that explains why.
    ctl.check(
        "bare: the number counts the FILTERED stream, not the file",
        bare_invocations("# a\n# b\ngoimports -l .\n"),
        ["1:goimports -l ."],
    )

    # -- scan_file, over the twin's own four fixtures ------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        for name, text in _CONTROL_FIXTURES.items():
            (root / name).write_text(text, encoding="utf-8")
        ctl.check("scan: bad.sh fires", bool(scan_file(root / "bad.sh", "bad.sh")), True)
        ctl.check("scan: good-gobin.sh is silent", scan_file(root / "good-gobin.sh", "g"), [])
        ctl.check("scan: good-path.sh is silent", scan_file(root / "good-path.sh", "g"), [])
        ctl.check("scan: unrelated.sh is silent", scan_file(root / "unrelated.sh", "u"), [])
        # An absent file is not a finding; see scan_file's docstring.
        ctl.check("scan: an unreadable path is not a finding", scan_file(root / "nope.sh", "n"), [])
        # The header names the file, and the FIX line is present. Both are the
        # output contract: a finding a reader cannot act on is a count.
        header = scan_file(root / "bad.sh", "bad.sh")
        ctl.check("scan: the header names the file", header[0].startswith("bad.sh installs"), True)
        ctl.check("scan: the FIX line is the last line", "FIX: GOBIN=" in header[-1], True)

    # -- the whole gate, over real git repositories --------------------------
    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        _git_init(root)
        (root / ".ci").mkdir()
        # THE VACUITY CASE FIRST. A repository with no shell files at all must be
        # a refusal, never a clean verdict.
        ctl.check("VACUITY: an empty tree is refused", _run(root), 1)

        # Fill to the floor with harmless scripts, then assert the floor is the
        # thing that flipped rather than anything about their contents.
        for i in range(MIN_FILES):
            (root / ".ci" / ("filler%02d.sh" % i)).write_text(
                "#!/bin/bash\necho hi\n", encoding="utf-8"
            )
        _git_add(root)
        ctl.check("CONTROL: %d harmless scripts pass" % MIN_FILES, _run(root), 0)

        # ONE SHORT OF THE FLOOR IS STILL A REFUSAL. Off-by-one on a floor is how
        # a floor stops being one.
        (root / ".ci" / "filler00.sh").unlink()
        _git_add(root)
        ctl.check("VACUITY: %d files is one short and is refused" % (MIN_FILES - 1), _run(root), 1)

        (root / ".ci" / "filler00.sh").write_text("#!/bin/bash\necho hi\n", encoding="utf-8")
        (root / ".ci" / "plant.sh").write_text(bad, encoding="utf-8")
        _git_add(root)
        ctl.check("PLANT: one bad script reds the whole gate", _run(root), 1)

        # ITS MIRROR: the sanctioned shape in the same position passes.
        (root / ".ci" / "plant.sh").write_text(_CONTROL_FIXTURES["good-gobin.sh"], encoding="utf-8")
        _git_add(root)
        ctl.check("MIRROR: the GOBIN shape in the same slot passes", _run(root), 0)

        # UNTRACKED IS INVISIBLE, on purpose: the scan reads `git ls-files`. A
        # port that quietly added --others would find things CI never sees.
        (root / ".ci" / "untracked-plant.sh").write_text(bad, encoding="utf-8")
        ctl.check("SCOPE: an UNTRACKED bad script is not seen", _run(root), 0)

    return 0 if ctl.report() else 1


def _git_init(root: pathlib.Path) -> None:
    """A real repository, because the scan is `git ls-files` and nothing else.

    `-c` rather than a written config: the identity is needed only for the commit
    this never makes, and `init` alone leaves an index `ls-files` can read.
    """
    subprocess.run(["git", "init", "-q", str(root)], check=True, capture_output=True)


def _git_add(root: pathlib.Path) -> None:
    subprocess.run(["git", "add", "-A"], cwd=str(root), check=True, capture_output=True)


def _run(root: pathlib.Path) -> int:
    """Drive `main` against a fixture root through the package-wide override.

    REDIACC_CI_ROOT is the one name for the whole program (see
    `rediacc_ci.paths`), set through the mapping the module reads rather than
    through a private seam invented for the test.
    """
    saved = os.environ.get(paths.ROOT_ENV)
    os.environ[paths.ROOT_ENV] = str(root)
    try:
        return main([])
    finally:
        if saved is None:
            del os.environ[paths.ROOT_ENV]
        else:
            os.environ[paths.ROOT_ENV] = saved


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
