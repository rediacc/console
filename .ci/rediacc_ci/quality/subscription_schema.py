"""The subscription schema must stay in step between TypeScript and Go.

Ported from `.ci/scripts/quality/check-subscription-schema.sh`, which is NOT
deleted; see `rediacc_ci.quality.__init__`.

-----------------------------------------------------------------------------
THE TWIN'S HEADER AND ITS THREE PHASES, CARRIED ACROSS.
-----------------------------------------------------------------------------

Check that subscription schema is up-to-date between TypeScript and Go.

  Exit codes:
    0 - Schema is up-to-date
    1 - Stale schema detected

GENERATE OUT OF TREE. Phase 1 used to regenerate `$SCHEMA_FILE` in place and
then `biome format --write` it, which made this gate a WRITER of a tracked file
while the ~8.7x-parallel pool read the same tree -- the hazard class in
scripts/ci-runner/manifest.ts:346-365, observed live with this exact file
stamped mid-battery. The check only ever needed something to DIFF against, so
it writes to $TEMP_DIR and the tracked file is never touched.

Formatting goes through STDIN rather than `--write`, so biome still resolves
this repo's config for the file's real path without that path being written.
Formatting is cosmetic here; an unformatted comparison is still a valid
staleness check, and failing the gate on a formatter hiccup would be worse, so
a biome failure falls back to the unformatted text.

THIS COMPARISON IS THE GATE, so it EXITS rather than warning. It used to warn,
which was survivable only because phase 1 regenerated `$SCHEMA_FILE` in place
and phase 3's `git diff` against HEAD then failed on the difference. Generating
out of tree removed that side effect and, with it, the only path that could fail
a stale schema: phase 3 now diffs an untouched file and is clean no matter how
stale the committed output is. A gate whose green no longer depends on the thing
it checks is worse than no gate.

Phase 3 compares against git HEAD, so it stays red in a working tree that has
legitimately-regenerated output but is not committed yet. Phase 1 verified the
content is CURRENT but does NOT write this file, so anything phase 3 reports is
the author's own edit.

-----------------------------------------------------------------------------
PORT NOTES.
-----------------------------------------------------------------------------

`set -euo pipefail` IS INHERITED FROM `common.sh`, NOT WRITTEN IN THE GATE, and
that is load-bearing for the port. Every external command in the twin is
therefore an implicit `|| exit $?`: a missing `npx`, a failed generator, a
`mktemp` that cannot write all abort the script with the child's status and no
message of the gate's own. Python has no such default, so each subprocess call
below returns its status explicitly and the module returns it. Anywhere the twin
would have aborted, this returns the same number.

The exceptions are the three places the twin guards explicitly, and they are the
interesting ones: `npx biome ... || cp` (a formatter hiccup must not fail the
gate), `diff -u | head -40 || true` (a diff that exits 1 is the normal case, and
`head` closing the pipe early is a SIGPIPE the twin does not want to see), and
`require_submodule ... || exit 0` (absent locally is a skip, absent in CI is a
hard failure).

`diff` AND `head` ARE THE REAL BINARIES, deliberately. `difflib.unified_diff`
produces a different header format, a different hunk-count spelling and a
different treatment of a missing final newline, and this gate PRINTS its diff
for a human to act on. Reproducing the bytes matters more than avoiding a
subprocess, and the subprocess is what the twin runs anyway.

`require_submodule` IS RE-IMPLEMENTED HERE rather than imported, because it
lives in `common.sh` and the whole point of the port is not to source that file.
Its contract, from the twin's own comment: "Returns 0 when the submodule is
present. When it is absent: in CI -> hard failure, because a gate that silently
skips is worse than no gate at all. check:ci-renet rides on this, and it carries
govulncheck (Go CVE scanning), deadcode and golangci-lint -- all three would
report success while checking nothing. locally -> warn and return 1, so a fresh
clone without --recursive is still workable."

`[[ -e "$marker" ]]` IS `-e`, NOT `-d`, so a submodule checked out as a FILE
gitlink (`.git` file rather than directory) still counts. `os.path.exists`
follows symlinks the same way `-e` does. A broken symlink is absent to both.

THE ORDER OF THE `cd`s IS BEHAVIOUR. The twin `cd`s to the repo root, then into
the submodule for `go test`, then back to the root for phase 3. Nothing here
changes process-global state; each subprocess is given its own `cwd`, which is
the same fact expressed without the hazard of leaving the interpreter somewhere
unexpected if a phase returns early.

STREAMS. `log_step`, `log_info`, `log_warn` and `log_error` are all stderr in
`common.sh`, and `rediacc_ci.log` matches them byte for byte. The generator's
stdout is discarded (`>/dev/null`) and its stderr is INHERITED, so a real
failure still explains itself; `go test -v` inherits both, because its output is
the evidence a reader needs.
"""

import os
import pathlib
import subprocess
import sys
import tempfile

from rediacc_ci import log, paths
from rediacc_ci.controls import Controls

# The committed artifact this gate rules on, and the submodule that must agree
# with it. Root-relative, joined at call time so REDIACC_CI_ROOT reaches them.
SCHEMA_REL = "packages/shared/src/subscription/schema.generated.json"
RENET_REL = "private/renet"

# The generator, named identically in the three places the twin names it: the invocation, the MISSING hint and the STALE hint. One constant, because a reader copies whichever of the three they happen to be looking at.
GENERATOR = "packages/shared/scripts/generate-subscription-schema.ts"

# The five Go tests that assert the two languages agree. A single `-run` alternation, exactly as the twin passes it.
GO_TEST_RUN = (
    "TestGoTypesMatchTypeScriptSchema|TestGoConstantsMatchTypeScriptSchema|"
    "TestSchemaVersion|TestPlanResourcesConsistency|TestPlanFeaturesConsistency"
)

# The label `require_submodule` prints. Quoted whole because it appears in the warning a developer reads on a fresh clone.
RENET_LABEL = "Renet submodule (Go schema validation)"

# The status a POSIX shell reports for a command it could not find. Named because Python raises where bash returns, and every subprocess in this module has to translate one into the other.
NOT_FOUND = 127


def require_submodule(marker: pathlib.Path, label: str, env: dict[str, str] | None = None) -> bool:
    """`common.sh`'s `require_submodule`, re-implemented. True when present.

    Returns False for "absent, and that is survivable here"; raises SystemExit(1)
    for "absent in CI", which is the twin's `exit 1` and not a value a caller can
    accidentally ignore. See the module docstring for why the two cases differ.
    """
    if marker.exists():
        return True
    environ = os.environ if env is None else env
    if environ.get("CI", "false") == "true":
        log.error("%s is required in CI but missing: %s" % (label, marker))
        log.error("  A gate skipped here would report success while checking nothing.")
        log.error("  Fix the workflow checkout (submodules: true, or git submodule update --init).")
        raise SystemExit(1)
    log.warn("%s not available, skipping (this is a hard failure in CI)" % label)
    return False


def generate(root: pathlib.Path, out: pathlib.Path) -> int:
    """Phase 1's generator, writing OUT OF TREE. Returns its exit status.

    stdout is discarded exactly as the twin's `>/dev/null` discards it; stderr is
    inherited, so the reason a generator failed is not swallowed. That asymmetry
    is the twin's and it is the right one: the schema itself is not wanted on a
    terminal, and the failure text is.
    """
    env = dict(os.environ)
    env["SUBSCRIPTION_SCHEMA_OUT"] = str(out)
    try:
        proc = subprocess.run(
            ["npx", "tsx", GENERATOR],
            cwd=str(root),
            env=env,
            stdout=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        # COMMAND NOT FOUND IS 127, NOT AN EXCEPTION, and getting this wrong is the single easiest way for a shell port to diverge. bash prints
        # `npx: command not found` and exits 127; Python raises FileNotFoundError
        # and, if nothing catches it, produces a traceback and exit 1. The twin cannot be traced back to, so neither is this.
        return NOT_FOUND
    return proc.returncode


def format_through_stdin(root: pathlib.Path, fresh: pathlib.Path, formatted: pathlib.Path) -> None:
    """biome, through STDIN so nothing tracked is written. Never fatal.

    A formatter hiccup falls back to copying the unformatted text, which is what
    the twin does and for the reason it states: "an unformatted comparison is
    still a valid staleness check, and failing the gate on a formatter hiccup
    would be worse."
    """
    status = NOT_FOUND
    try:
        with fresh.open("rb") as stdin, formatted.open("wb") as stdout:
            status = subprocess.run(
                ["npx", "biome", "format", "--stdin-file-path=%s" % SCHEMA_REL],
                cwd=str(root),
                stdin=stdin,
                stdout=stdout,
                stderr=subprocess.DEVNULL,
                check=False,
            ).returncode
    except OSError:
        # `if ! npx biome ...` in bash catches a missing binary as 127 and takes the fallback branch. See `generate` for the same point at more length.
        status = NOT_FOUND
    if status != 0:
        formatted.write_bytes(fresh.read_bytes())


def files_differ(a: pathlib.Path, b: pathlib.Path) -> bool:
    """`diff -q a b >/dev/null 2>&1` -- true when they are not identical.

    Shelled out rather than compared in Python because `diff`'s notion of
    identical is what the twin rules on, and because a missing file makes `diff`
    exit 2, which the twin treats as "differ" through its `if !`. Reproducing
    that with a byte comparison would need the same three-way branch written out
    by hand and would drift from it.
    """
    try:
        proc = subprocess.run(
            ["diff", "-q", str(a), str(b)],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            check=False,
        )
    except OSError:
        # An ABSENT `diff` is 127 in a shell, which the twin's `if !` reads as "they differ". Erring toward STALE rather than toward clean is the
        # right direction and it is the twin's; a port that raised here would
        # turn a missing tool into a traceback.
        return True
    return proc.returncode != 0


def print_diff(a: pathlib.Path, b: pathlib.Path) -> None:
    """`diff -u a b | head -40 || true`, on STDOUT, with the pipe reproduced.

    The `|| true` matters: `diff` exits 1 whenever there IS a difference, which
    is exactly when this runs, and under the twin's inherited `set -e` an
    unguarded call would abort the gate before it printed its advice.
    """
    # BUILT AS TWO PROCESSES, NOT AS A SHELL STRING. `shell=True` would be the
    # literal transliteration and it is refused by this repo's own ruff rule (S602), correctly: a path interpolated into a shell string is an injection the day a path contains a quote. Two Popens joined by a pipe are what the shell would have built anyway, and they preserve the two behaviours that matter: `head` closing the pipe early sends `diff` a SIGPIPE, and neither exit status
    # is allowed to propagate (the `|| true`).
    try:
        diff_proc = subprocess.Popen(["diff", "-u", str(a), str(b)], stdout=subprocess.PIPE)
        head_proc = subprocess.Popen(["head", "-40"], stdin=diff_proc.stdout)
    except OSError:
        # `|| true` swallows a missing binary in the twin, and this is advisory output printed under a verdict that has already been reached.
        return
    if diff_proc.stdout is not None:
        # Closed in THIS process so `diff` sees the pipe close when `head` exits;
        # leaving it open here is how a pipeline hangs on a large diff.
        diff_proc.stdout.close()
    head_proc.wait()
    diff_proc.wait()


def main(argv: list[str] | None = None) -> int:
    """Run the three phases. Exit 0 up-to-date, 1 stale or out of sync."""
    args = list(argv or [])
    if args and args[0] == "--selftest":
        return selftest()

    root = paths.repo_root()
    schema_file = root / SCHEMA_REL
    renet_dir = root / RENET_REL

    # ---- Phase 1: generate a fresh schema and compare -------------------
    log.step("Generating fresh subscription schema...")
    with tempfile.TemporaryDirectory() as temp:
        temp_dir = pathlib.Path(temp)
        fresh = temp_dir / "schema.fresh.json"
        formatted = temp_dir / "schema.formatted.json"

        status = generate(root, fresh)
        if status != 0:
            # The twin has no branch here at all: `set -e` aborts with this status and no message. Returning it reproduces both the code and the silence, and the generator's own stderr has already been seen.
            return status

        format_through_stdin(root, fresh, formatted)

        if not schema_file.is_file():
            log.error("Subscription schema is MISSING at %s" % schema_file)
            log.error("  regenerate with: npx tsx %s" % GENERATOR)
            return 1

        if files_differ(schema_file, formatted):
            log.error("Subscription schema is STALE: the committed file does not match what the")
            log.error("TypeScript source generates today.")
            log.error("")
            print_diff(schema_file, formatted)
            log.error("")
            log.error("  regenerate and commit: npx tsx %s" % GENERATOR)
            return 1

    log.info("Subscription schema is up-to-date")

    # ---- Phase 2: the Go side must agree --------------------------------
    if not require_submodule(renet_dir, RENET_LABEL):
        # `require_submodule ... || exit 0`. A fresh clone without --recursive is
        # still workable; CI never reaches here because the helper exits 1 there.
        return 0

    log.step("Running Go schema validation tests...")
    proc = subprocess.run(
        ["go", "test", "./pkg/subscription/...", "-run", GO_TEST_RUN, "-v"],
        cwd=str(renet_dir),
        check=False,
    )
    if proc.returncode != 0:
        log.error("Go types do not match TypeScript schema!")
        log.error("")
        log.error("This means the subscription types are out of sync between TypeScript and Go.")
        log.error("To fix:")
        log.error(
            "  1. Update Go types in private/renet/pkg/subscription/types.go to match TypeScript"
        )
        log.error("  2. Run: npx tsx %s" % GENERATOR)
        log.error(
            "  3. Run: cd private/renet && go test ./pkg/subscription/... "
            "-run TestGoTypesMatchTypeScriptSchema -v"
        )
        return 1

    log.info("Go types match TypeScript schema")

    # ---- Phase 3: the schema must be committed ---------------------------
    dirty = subprocess.run(
        ["git", "diff", "--quiet", str(schema_file)],
        cwd=str(root),
        stderr=subprocess.DEVNULL,
        check=False,
    )
    if dirty.returncode != 0:
        log.error("Schema file has uncommitted changes")
        log.error("")
        log.error("Phase 1 verified the content is CURRENT but does NOT write this file,")
        log.error("so these are your own edits: review the diff and commit it.")
        log.error("  git diff %s" % schema_file)
        log.error("")
        log.error("This compares against git HEAD, so it stays red in a working tree that")
        log.error("has legitimately-regenerated output but is not committed yet.")
        return 1

    return 0


def selftest() -> int:
    """Both directions, against fixtures the gate's own subprocesses can reach.

    THE SUBJECT IS A PIPELINE OF FOUR EXTERNAL TOOLS -- npx tsx, npx biome, diff,
    go -- so the controls here drive the DECISIONS around them (present/absent,
    identical/different, CI/local) rather than the tools themselves. The tools
    are covered by the committed shadow ledger, which runs the whole gate.
    """
    ctl = Controls("subscription-schema", floor=13, verbose=True)

    with tempfile.TemporaryDirectory() as tmp:
        root = pathlib.Path(tmp)
        a = root / "a.json"
        b = root / "b.json"
        a.write_text('{"x":1}\n', encoding="utf-8")
        b.write_text('{"x":1}\n', encoding="utf-8")

        # -- files_differ, both directions ---------------------------------
        ctl.falsy("CONTROL: identical files do not differ", files_differ(a, b))
        b.write_text('{"x":2}\n', encoding="utf-8")
        ctl.truthy("PLANT: a changed value makes them differ", files_differ(a, b))
        b.write_text('{"x":1}', encoding="utf-8")
        ctl.truthy(
            "PLANT: a missing final newline is a difference, as diff sees it",
            files_differ(a, b),
        )
        ctl.truthy(
            "VACUITY: a file that is not there reads as different, never as identical",
            files_differ(a, root / "gone.json"),
        )

        # -- require_submodule, all three outcomes -------------------------
        present = root / "sub"
        present.mkdir()
        ctl.truthy(
            "CONTROL: a present submodule directory satisfies the requirement",
            require_submodule(present, "L", env={}),
        )
        gitlink = root / "sub-file"
        gitlink.write_text("gitdir: ../.git/modules/sub\n", encoding="utf-8")
        ctl.truthy(
            "CONTROL: a FILE gitlink also satisfies it (-e, not -d)",
            require_submodule(gitlink, "L", env={}),
        )
        ctl.falsy(
            "MIRROR: absent LOCALLY is a warn-and-skip, not a failure",
            require_submodule(root / "nope", "L", env={"CI": "false"}),
        )
        ctl.falsy(
            "MIRROR: absent with CI unset is also a warn-and-skip",
            require_submodule(root / "nope", "L", env={}),
        )
        ctl.raises(
            "PLANT: absent in CI is a HARD failure, because a silent skip is worse than no gate",
            SystemExit,
            require_submodule,
            root / "nope",
            "L",
            {"CI": "true"},
        )
        broken = root / "broken-link"
        broken.symlink_to(root / "does-not-exist")
        ctl.falsy(
            "MIRROR: a broken symlink is ABSENT to -e, not present",
            require_submodule(broken, "L", env={}),
        )

        # -- the formatter fallback ---------------------------------------- A biome that cannot run must leave a usable comparison behind rather than an empty file, which would make every schema read as STALE.
        fresh = root / "fresh.json"
        formatted = root / "formatted.json"
        fresh.write_text('{"generated":true}\n', encoding="utf-8")
        saved_path = os.environ.get("PATH", "")
        try:
            # An empty PATH is the cheapest honest way to make `npx` unavailable.
            os.environ["PATH"] = str(root / "no-such-bin")
            format_through_stdin(root, fresh, formatted)
        finally:
            os.environ["PATH"] = saved_path
        ctl.check(
            "CONTROL: a formatter that cannot run falls back to the unformatted text",
            formatted.read_text(encoding="utf-8"),
            '{"generated":true}\n',
        )
        ctl.falsy(
            "CONTROL: and the fallback text is therefore comparable, not empty",
            files_differ(fresh, formatted),
        )

        # -- the generator's status is returned, not swallowed --------------
        saved_path = os.environ.get("PATH", "")
        try:
            os.environ["PATH"] = str(root / "no-such-bin")
            ctl.check(
                "VACUITY: an absent generator is 127, never a clean schema",
                generate(root, root / "out.json"),
                NOT_FOUND,
            )
        finally:
            os.environ["PATH"] = saved_path

    return 0 if ctl.report() else 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
