"""The renet-generated TypeScript types are up to date.

Ported from `.ci/scripts/quality/check-renet-types.sh`, which is not deleted;
see `rediacc_ci.quality.__init__` for why both copies live.

WHAT THE TWIN DOES. It builds `renet` from the `private/renet` submodule,
regenerates the contract into a temporary directory, and compares each
generated file against the committed copy in
`packages/shared/src/renet-contract/data`, IGNORING the version line. A
difference means the committed contract is stale: the CLI would then be typed
against a renet that no longer exists.

THE LIST IS THE GATE, and the twin's own comment says why in the one place it
was learned the hard way: "Adding a generated file to the generator is NOT
enough: this list is what the gate actually compares. license-tiers.generated.ts
was generated into TEMP_DIR and silently ignored until it was added here, which
would have let it go stale forever while the gate reported 'up-to-date'." A
seventh generated file added tomorrow is invisible to this gate until someone
edits `FILES`, and that is a real blind spot which is preserved rather than
quietly widened, because widening it would change the verdict.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

THE SUBMODULE GUARD IS A THREE-WAY BRANCH, NOT A TWO-WAY ONE, and collapsing it
is how a gate becomes vacuous. `require_submodule` in `.ci/scripts/lib/common.sh`
answers:

    marker present          -> run
    marker absent, CI=true  -> HARD FAILURE, exit 1, three lines that name the
                               fix ("Fix the workflow checkout (submodules:
                               true, or git submodule update --init)")
    marker absent, locally  -> warn and return 1, and the caller's `|| exit 0`
                               turns that into a skip

The middle rung is the one that matters. common.sh states it: "a gate that
silently skips is worse than no gate at all. check:ci-renet rides on this, and
it carries govulncheck (Go CVE scanning), deadcode and golangci-lint -- all
three would report success while checking nothing." The port carries all three
rungs, including the local skip, because a port that hardened the skip into a
failure would break a fresh clone without `--recursive`, and a port that dropped
the CI rung would make the gate vacuous in the one place it must not be.

THE MARKER IS `go.mod`, NOT THE DIRECTORY. An uninitialised submodule leaves an
EMPTY directory behind, which satisfies a directory test while proving nothing
about content.

`grep -v` ON A MISSING FILE LEAKS ITS ERROR, and the port leaks the same bytes.
`compare_ignoring_version` runs both greps inside process substitutions, and the
`2>/dev/null` on the enclosing `diff` does NOT cover them: measured, a missing
committed file prints `grep: <path>: No such file or directory` on the gate's
own stderr and the comparison then reports "differ", so the file lands in the
STALE list. The port emits the identical line. It is a twin defect -- the
message reads as a crash when it means "this generated file has never been
committed" -- and it is reported rather than repaired, because repairing it
would change what the gate prints.

A FILE THE GENERATOR DID NOT PRODUCE IS SKIPPED ENTIRELY. `if [[ -f
"$TEMP_DIR/$file" ]] && ...` means a generator that stopped emitting one of the
six is NOT reported as stale; the file simply drops out of the comparison. That
is the second blind spot in the same loop and it is likewise preserved.

`go` MISSING IS THE ONE DELIBERATE DIVERGENCE IN WORDING. Under `set -e` the
twin dies with bash's own `go: command not found` and exit 127, a message the
gate never wrote. The port cannot produce that string without pretending to be
a shell, so it prints its own line naming the same fix and returns the same 127.
The exit code is what any caller reads; the text differs and is stated here so
nobody reports it as a regression.
"""

import os
import pathlib
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# Where the submodule and the committed contract live, relative to the root.
RENET_REL = "private/renet"
OUTPUT_REL = "packages/shared/src/renet-contract/data"

# The marker whose presence means the submodule is really checked out.
MARKER = "go.mod"

# The generated files this gate compares. THE LIST IS THE GATE; see the module
# docstring for the file that went stale for months because it was missing here.
FILES = (
    "functions.generated.ts",
    "functions.schema.ts",
    "vault.generated.ts",
    "vault.schema.ts",
    "list-types.generated.ts",
    "license-tiers.generated.ts",
)

# The substring whose lines are excluded from the comparison. NOT anchored, and
# the trailing space is part of it: `grep -v '_VERSION = '` drops any line
# containing that exact text anywhere.
VERSION_MARKER = "_VERSION = "


def strip_version_lines(path: pathlib.Path) -> tuple[list[str], str | None]:
    """The file's lines minus the version lines, plus grep's error if it failed.

    A MISSING FILE IS AN EMPTY STREAM, NOT A FAILURE, and getting that wrong is
    a divergence this port shipped in a draft. `grep -v PAT missing` writes its
    diagnostic to stderr and produces NO output, and the process substitution
    around it still presents a readable, empty file to `diff`. So two missing
    files compare EQUAL: `diff -q` sees two empty streams and exits 0. The draft
    returned a sentinel and treated either side's absence as "differ", which
    disagreed with the twin on exactly that case; the pytest differential caught
    it on the both-missing row of its table.

    Returns the error TEXT rather than raising, because the twin does not raise:
    it lets grep write to stderr and lets the comparison fall out of the byte
    content. The caller reproduces both halves of that.
    """
    try:
        text = path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        # GNU grep's wording under LC_ALL=C, which is what the differential pins.
        return [], "grep: %s: No such file or directory" % path
    lines = text.split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return [line for line in lines if VERSION_MARKER not in line], None


def compare_ignoring_version(committed: pathlib.Path, generated: pathlib.Path) -> bool:
    """True when the two files agree once their version lines are removed.

    `diff -q <(grep -v ...) <(grep -v ...) >/dev/null 2>&1` -- a boolean, with
    the DIFFERENCE itself thrown away. That is why the gate's failure message
    can only name the file and not say what changed, and it is carried as is.
    """
    left, left_err = strip_version_lines(committed)
    right, right_err = strip_version_lines(generated)
    for err in (left_err, right_err):
        if err is not None:
            # THE LEAK, REPRODUCED. See the port notes: the enclosing `2>/dev/null` does not reach into a process substitution.
            print(err, file=sys.stderr)
    # NO SHORT-CIRCUIT ON THE ERROR. A missing file contributes an EMPTY line list and the comparison proceeds, which is what `diff` does with the empty stream a failed `grep` leaves behind. See `strip_version_lines`.
    return left == right


def _require_submodule(marker: pathlib.Path, label: str) -> bool:
    """`require_submodule` from `.ci/scripts/lib/common.sh`. True to proceed.

    Raises SystemExit(1) on the CI rung, exactly as the bash function's `exit 1`
    does: it is not a return value there, and a port that returned False would
    let a caller ignore it.
    """
    if marker.exists():
        return True
    if os.environ.get("CI", "false") == "true":
        log.error("%s is required in CI but missing: %s" % (label, marker))
        log.error("  A gate skipped here would report success while checking nothing.")
        log.error("  Fix the workflow checkout (submodules: true, or git submodule update --init).")
        raise SystemExit(1)
    log.warn("%s not available, skipping (this is a hard failure in CI)" % label)
    return False


def _describe(root: pathlib.Path) -> str:
    """`git describe --tags --always`, falling back to the literal "dev"."""
    proc = subprocess.run(
        ["git", "describe", "--tags", "--always"],
        cwd=str(root),
        capture_output=True,
        text=True,
        check=False,
    )
    out = proc.stdout.strip()
    return out if proc.returncode == 0 and out else "dev"


def main(argv: list[str] | None = None) -> int:
    """Run the gate. Exit 0 fresh, 1 stale, 0 when the submodule is absent locally.

    `--selftest` is intercepted BEFORE any real scan. The twin takes no
    arguments at all, so no caller can be passing this string today.
    """
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    renet_dir = root / RENET_REL
    output_dir = root / OUTPUT_REL

    if not _require_submodule(renet_dir / MARKER, "Renet submodule"):
        # The caller's `|| exit 0`. A skip, loud on stderr, and never a claim that anything was checked.
        return 0

    log.step("Building renet...")
    try:
        built = subprocess.run(
            ["go", "build", "-o", "bin/renet", "./cmd/renet"],
            cwd=str(renet_dir),
            check=False,
        )
    except FileNotFoundError:
        # The one deliberate wording divergence; see the port notes.
        log.error("go is not installed, so renet cannot be built and NOTHING was verified.")
        log.error("  Install the Go toolchain, or run this gate where one exists.")
        return 127
    if built.returncode != 0:
        # `set -e`: the twin dies here with go's own diagnostics already on stderr and go's exit code. Nothing is added, because anything added would be a line the twin does not print.
        return built.returncode

    log.step("Checking types freshness...")
    temp_dir = pathlib.Path(tempfile.mkdtemp())
    try:
        version = _describe(root)
        generated = subprocess.run(
            [
                str(renet_dir / "bin" / "renet"),
                "functions",
                "generate-types",
                "--output",
                str(temp_dir),
                "--version",
                version,
            ],
            check=False,
        )
        if generated.returncode != 0:
            # `set -e` again: the generator's own output is already on the streams and its exit code is the gate's.
            return generated.returncode

        # A FILE THE GENERATOR DID NOT PRODUCE IS SKIPPED, not reported. See
        # the port notes; this is the twin's second blind spot, and the `-f`
        # guard below is where it lives.
        stale: list[str] = [
            name
            for name in FILES
            if (temp_dir / name).is_file()
            and not compare_ignoring_version(output_dir / name, temp_dir / name)
        ]

        if not stale:
            log.info("Renet types are up-to-date")
            return 0

        log.error("Stale types detected: %s" % " ".join(stale))
        log.error("Regenerate:")
        log.error("  cd private/renet && go build -o bin/renet ./cmd/renet")
        log.error("  private/renet/bin/renet functions generate-types \\")
        log.error("    --output packages/shared/src/renet-contract/data --version dev")
        return 1
    finally:
        # `trap 'rm -rf "$TEMP_DIR"' EXIT`.
        shutil.rmtree(temp_dir, ignore_errors=True)


def selftest() -> int:
    """Plant each violation, prove it reds; remove it, prove it greens.

    THE PURE HALF ONLY, AND THAT IS A DECISION. The end-to-end path builds a Go
    binary, which needs a toolchain and tens of seconds, and a selftest that
    silently degrades when `go` is missing would be the vacuity this package
    exists to refuse. The comparison logic -- the part that decides the verdict
    -- is pure, so it is driven directly here, and the whole gate is proven
    end to end by the committed shadow ledger
    `.ci/shadow/w7p2-renet-types.observations.jsonl` over five distinct trees.
    """
    ctl = Controls("renet-types", floor=18, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        a = root / "a.ts"
        b = root / "b.ts"

        def cmp_files(left: str, right: str) -> bool:
            a.write_text(left, encoding="utf-8")
            b.write_text(right, encoding="utf-8")
            return compare_ignoring_version(a, b)

        ctl.check("CONTROL: identical files agree", cmp_files("x\ny\n", "x\ny\n"), True)
        ctl.check("PLANT: a changed line is caught", cmp_files("x\ny\n", "x\nz\n"), False)
        ctl.check("PLANT: an ADDED line is caught", cmp_files("x\n", "x\ny\n"), False)
        ctl.check("PLANT: a REMOVED line is caught", cmp_files("x\ny\n", "x\n"), False)

        # THE VERSION EXCLUSION, in both directions. This is the whole reason the comparison is not `diff`, and a port that dropped it would report the contract stale on every commit.
        ctl.check(
            "MIRROR: a differing _VERSION line does not count",
            cmp_files(
                'export const RENET_VERSION = "v1";\nx\n', 'export const RENET_VERSION = "v2";\nx\n'
            ),
            True,
        )
        ctl.check(
            "MIRROR: the marker is a SUBSTRING, not an anchor",
            cmp_files("  const X_VERSION = 1;\ny\n", "  const X_VERSION = 2;\ny\n"),
            True,
        )
        ctl.check(
            "PLANT: `_VERSION=` with no spaces is NOT excluded",
            cmp_files("const A_VERSION=1;\n", "const A_VERSION=2;\n"),
            False,
        )
        ctl.check(
            "PLANT: a real change beside a version line is still caught",
            cmp_files('A_VERSION = "v1";\nx\n', 'A_VERSION = "v2";\nz\n'),
            False,
        )
        ctl.check(
            "MIRROR: a trailing newline is not a difference",
            cmp_files("x\ny\n", "x\ny"),
            True,
        )
        ctl.check("MIRROR: two empty files agree", cmp_files("", ""), True)

        # THE MISSING-FILE PATH. A committed file that does not exist is reported as differing, which is what puts it on the STALE list.
        missing = root / "gone.ts"
        b.write_text("x\n", encoding="utf-8")
        ctl.check(
            "VACUITY: a missing committed file counts as DIFFERING, never as equal",
            compare_ignoring_version(missing, b),
            False,
        )
        ctl.check(
            "VACUITY: a missing GENERATED file also counts as differing",
            compare_ignoring_version(b, missing),
            False,
        )
        # AND THE CASE THAT IS NOT A REFUSAL, which is the one a draft got wrong: BOTH files missing are two empty streams, and `diff` calls those identical. It cannot arise in the gate's own loop -- the generated side is guarded by `-f` -- and it is pinned anyway, because the port had already disagreed with the twin about it once.
        gone = root / "also-gone.ts"
        ctl.check(
            "MIRROR: TWO missing files are two EMPTY streams, which diff calls equal",
            compare_ignoring_version(missing, gone),
            True,
        )

        # THE STRIPPER ITSELF.
        kept, err = strip_version_lines(b)
        ctl.check("strip_version_lines: a readable file has no error", err, None)
        ctl.check("strip_version_lines: and returns its records", kept, ["x"])
        kept, err = strip_version_lines(missing)
        ctl.check("strip_version_lines: a missing file returns NO lines, not a sentinel", kept, [])
        ctl.check(
            "strip_version_lines: and grep's exact wording",
            err,
            "grep: %s: No such file or directory" % missing,
        )

    # THE LIST IS THE GATE. Asserted so a port that lost an entry is caught here rather than by a contract going stale for months.
    ctl.check("the compared file list still holds six entries", len(FILES), 6)
    ctl.check("and license-tiers is one of them", "license-tiers.generated.ts" in FILES, True)

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
