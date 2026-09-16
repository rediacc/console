"""`.ci/media/verify.sh`, ported: the post-cutover ownership proof and the module sandbox.

WHAT THE BASH ORIGINAL PROVES, restated because it is the whole reason a media
gate test is not just a behaviour test. Phase 1 of the media split copied 35
functions out of run.sh and three out of media.sh into seven modules WITHOUT
deleting the originals, so for one phase both copies existed and the entire risk
was silent drift between them. Phase 2 deleted the originals. There is no second
copy left to drift from, so the question changed from "did the copy drift" to
"does the delegation still reach the function that used to be here", and it is
answered two ways: STRUCTURE (exactly one file defines the name, it is the module
under test, the origins no longer define it, and sourcing media-entry.sh resolves
the name to THIS module's body) and BEHAVIOUR (what the module does when its
dependencies are missing, which is the only part CI can drive).

WHAT IS PORTED AND WHAT IS NOT. The two `fidelity_assert_*` byte-identity helpers
are already GONE from the bash file, deleted in phase 2 rather than left pointing
at an absent function, and nothing here recreates them. The chain probe
(`media_chain_probe` / `media_chain_mutate` / `media_chain_run`) is not ported
either, because no subject in this batch drives a verb chain; `media_chain_sandbox`
IS ported, because `media_assert_ownership_control` needs a real writable repo.
When a later batch ports a chain test it adds those three here rather than
building a second sandbox.

THE VACUITY TRAP IS THE SAME ONE, so it is guarded the same way. Extraction still
fails loudly on a name it cannot find, every comparison is preceded by a floor on
its size, and each module's gate test plants a mutation and requires the assertion
to fire, because a comparison that has never been seen to fail is a comparison
nobody has checked.

TWO THINGS ARE RESOLVED AT IMPORT TIME, NOT AT CALL TIME, and both for the reason
the bash file records. Callers invoke these from inside `fake_bin`, where PATH
holds ONLY what the test named, so a lookup deferred to call time fails with
"command not found" reported as the module's exit code. `_BASH` is the absolute
interpreter path (`"$BASH"` in the original, for exactly this reason) and
`MEDIA_DIR` is resolved from this package's own location rather than from cwd.
"""

import os
import pathlib
import re
import shutil

from rediacc_ci import paths
from rediacc_ci.tests.gates import harness

MEDIA_ROOT = paths.repo_root()
MEDIA_DIR = MEDIA_ROOT / ".ci" / "media"

# See the docstring: resolved now, while the caller's real PATH is still in effect.
_BASH = shutil.which("bash") or "/bin/bash"

# ONE LIST, BECAUSE FOUR HAND-MAINTAINED COPIES IS WHAT WENT WRONG. The 2026-09-06
# router split moved every verb body out of run.sh into .ci/legacy/run-legacy.sh,
# which made that file a third origin overnight; four separate absence assertions
# had to be widened by hand to notice, and missing one of them would not have
# shown up as a failure.
MEDIA_ORIGIN_RELPATHS = ("run.sh", "media.sh", ".ci/legacy/run-legacy.sh")


class ExtractionError(Exception):
    """`fidelity_extract` exiting 1 with a reason on stderr."""


def fidelity_extract(path: pathlib.Path, name: str) -> str:
    """The function's body: the `name() {` line through the closing `}` in COLUMN 0.

    Column 0 is what makes this unambiguous: every nested block in these files
    closes indented, and shfmt (`-i 4 -ci`, enforced by check:ci-shell-format over
    `.ci/**`) is what keeps that true. The bash original is an awk program doing
    exactly this scan; the two agree because both test for the literal opening
    line and the literal single-character closing line, with no regex involved on
    either side.
    """
    if not path.is_file():
        raise ExtractionError("fidelity_extract: no such file: %s" % path)
    lines = path.read_text(encoding="utf-8").splitlines()
    opening = "%s() {" % name
    start = None
    for index, line in enumerate(lines):
        if line == opening:
            start = index
            break
    if start is None:
        raise ExtractionError("fidelity_extract: %s() not defined in %s" % (name, path))
    for index in range(start + 1, len(lines)):
        if lines[index] == "}":
            return "\n".join(lines[start : index + 1])
    raise ExtractionError("fidelity_extract: %s() in %s never closes at column 0" % (name, path))


def fidelity_extract_any(path: pathlib.Path, name: str) -> str:
    """`fidelity_extract`, widened to the ONE-LINE form `name() { ...; }`.

    media.sh wrote `die` that way before the cutover, and a block-only extractor
    reported it MISSING, which under a naive comparison read as "both sides
    empty, therefore equal". media.sh no longer defines anything, so the form
    survives only in prose today; the widening stays because `media_defines` uses
    this to ask WHETHER A FILE STILL DEFINES A NAME, and a one-line definition
    would otherwise be invisible to exactly the check that must not miss it.
    """
    if not path.is_file():
        raise ExtractionError("fidelity_extract: no such file: %s" % path)
    one_line = re.compile(r"^%s\(\) \{.*\}$" % re.escape(name), re.MULTILINE)
    match = one_line.search(path.read_text(encoding="utf-8"))
    if match:
        return match.group(0)
    return fidelity_extract(path, name)


def media_defines(path: pathlib.Path, name: str) -> bool:
    """True when `path` carries a definition of `name` at column 0, either form."""
    if not path.is_file():
        return False
    try:
        fidelity_extract_any(path, name)
    except ExtractionError:
        return False
    return True


def media_origins(root: pathlib.Path) -> tuple[list[pathlib.Path], list[str]]:
    """(existing origin paths, complaints about missing ones).

    IT REFUSES A MISSING ORIGIN RATHER THAN SKIPPING IT, which is the whole point
    of the function. An absence assertion over a file that is not there passes for
    FREE: `media_defines` returns False on a missing file, and `grep -q pat a b`
    with b absent exits 2 while writing to stderr. Both read as "the name is not
    there" when what happened is "nobody looked". Measured 2026-09-06 in a
    sandbox: deleting run-legacy.sh left the sole-owner assertion green with its
    legacy arm doing nothing at all.

    The caller decides what a missing origin means, which is why this returns the
    complaints rather than raising.
    """
    found: list[pathlib.Path] = []
    missing: list[str] = []
    for rel in MEDIA_ORIGIN_RELPATHS:
        candidate = root / rel
        if candidate.is_file():
            found.append(candidate)
        else:
            missing.append(
                "media_origins: %s does not exist -- an absence assertion over a file "
                "nobody read is not absence, so this is a finding rather than a skip" % candidate
            )
    return found, missing


def _coverage_prelude() -> str:
    """The xtrace seam, spliced into the code STRING rather than the environment.

    SHELLOPTS is readonly in a running bash, so the option can only be inherited
    from an environment, and inheriting it is precisely what perturbs: forcing
    xtrace into every child makes eight of the ten media gate tests FAIL, because
    `media_run_module` captures MERGED stdout and stderr and the behaviour cases
    assert on that text. Scoped here, the trace goes to its own descriptor and the
    captured output is byte-identical with the probe on and off.

    `${BASH_SOURCE:-}` and NOT `${BASH_SOURCE}`: common.sh sets `set -u`, and at
    the top level of a `bash -c` string BASH_SOURCE is unset, so the bare form
    makes the FIRST traced command die with "BASH_SOURCE: unbound variable".
    """
    target = os.environ.get("MEDIA_COVERAGE_FILE")
    if not target:
        return ""
    return "exec 9>>'%s'; BASH_XTRACEFD=9; PS4='+|${BASH_SOURCE:-}|${LINENO}|'; set -x;" % target


def media_run_module(
    root_dir: os.PathLike[str] | str,
    modules: str,
    code: str,
    *,
    module_dir: pathlib.Path | None = None,
) -> harness.RunResult:
    """Run `code` against the named `.ci/media` modules in a FRESH bash.

    A FRESH SHELL RATHER THAN A SUBSHELL, for two reasons that both bit while the
    bash original was being written: the functions under test call `exit`, which
    in a plain subshell ends the enclosing test rather than the code under test;
    and common.sh sets `set -euo pipefail`, which is what run.sh does too, so a
    fresh shell is also the HONEST environment rather than a convenient one.

    It inherits PATH, so a caller inside `fake_bin` gets the emptied PATH here
    too, which is the entire point. `modules` is a space-separated list of file
    names relative to `.ci/media`, sourced in the order given, so a test states
    its own dependency edges instead of pulling the whole folder in.

    `module_dir` IS THE MUTATION SEAM (`$MEDIA_MODULE_DIR` in bash). A test writes
    one altered module into a temp directory, points this at it, re-runs the same
    probe and requires the result to CHANGE. Without it a behaviour case could
    only ever run the module that is already green, and "this assertion would fail
    if the code were wrong" would be an assumption rather than something the test
    file has watched happen.

    portable.sh IS ALWAYS SOURCED, and always from the REAL folder rather than
    from `module_dir`. It is the seam layer, not a subject: every module is
    entitled to `media_mtime` and `${MEDIA_SHA256[@]}` being in scope exactly as
    media-entry.sh guarantees, and a test naming its module without naming the
    seams would fail with "command not found" for a reason unrelated to what it
    asserts. From the real folder because `module_dir` points at a mutant
    directory holding one altered module and nothing else.

    ONE COMMAND IS ALWAYS REQUIRED of the caller: common.sh runs
    `CI_OS="$(detect_os)"` at source time, and `detect_os` shells out to `uname`.
    A caller inside `fake_bin` must admit `+uname`, or every run carries a stray
    "uname: command not found" on stderr.
    """
    directory = MEDIA_DIR if module_dir is None else module_dir
    sources = ["source '%s/portable.sh';" % MEDIA_DIR]
    sources += ["source '%s/%s';" % (directory, name) for name in modules.split()]
    script = "\n".join(
        [
            "ROOT_DIR='%s'" % root_dir,
            "source '%s/.ci/scripts/lib/common.sh'" % MEDIA_ROOT,
            _coverage_prelude(),
            " ".join(sources),
            code,
        ]
    )
    return harness.run([_BASH, "-c", script])


def media_assert_sole_owner(root: pathlib.Path, module: str, name: str) -> str | None:
    """None when all four hold, else the ONE that did not, as a message.

      1. `module` defines the function. Checked FIRST and loudly, because every
         check below is about UNIQUENESS and "nobody defines it" satisfies
         uniqueness vacuously. That is the trap the deleted byte-identity helper
         was built around: two extractions that both found nothing compared equal.
      2. No OTHER file in `.ci/media` defines it. Two modules defining one name
         means the winner is decided by media-entry.sh's source order, which is
         not a contract anybody wrote down.
      3. The origins do not define it. This is the cutover itself, stated as an
         invariant rather than as a one-time event: re-add a copy to run.sh, which
         is exactly what a future session merging a conflict would do, and this
         fires.
      4. Sourcing media-entry.sh puts THIS module's body in scope under that name.
         Steps 1 to 3 are about FILES; this one is about what the interpreter
         actually ends up with, so a module that exists but is never sourced, or a
         name shadowed by a later source, is caught. `declare -f` is bash's own
         canonical form, so the comparison is indifferent to formatting and to
         nothing else.

    `root` is a PARAMETER rather than a constant so a control can point it at a
    sandbox where the invariant has been deliberately broken. That is the only way
    this assertion is ever watched failing.
    """
    module_path = root / ".ci" / "media" / module

    if not media_defines(module_path, name):
        return (
            "media_assert_sole_owner: %s() is not defined in %s -- nothing here is "
            "uniquely owned, so uniqueness proves nothing" % (name, module_path)
        )

    for other in sorted((root / ".ci" / "media").glob("*.sh")):
        if other == module_path:
            continue
        if media_defines(other, name):
            return (
                "media_assert_sole_owner: %s() is defined in BOTH %s and %s -- source "
                "order in media-entry.sh would silently pick the winner"
                % (name, module, other.name)
            )

    origins, missing = media_origins(root)
    if missing:
        return missing[0]
    for origin in origins:
        if media_defines(origin, name):
            return (
                "media_assert_sole_owner: %s() is defined again in %s -- the cutover has "
                "been undone for this function" % (name, origin.name)
            )

    via_entry = harness.run(
        [
            _BASH,
            "-c",
            "source '%s/.ci/media/media-entry.sh' >/dev/null 2>&1; declare -f '%s'" % (root, name),
        ]
    )
    via_module = harness.run(
        [
            _BASH,
            "-c",
            "ROOT_DIR='%s'; source '%s' >/dev/null 2>&1; declare -f '%s'"
            % (root, module_path, name),
        ]
    )
    entry_body = via_entry.out if via_entry.rc == 0 else ""
    module_body = via_module.out if via_module.rc == 0 else ""
    if not entry_body or not module_body:
        return (
            "media_assert_sole_owner: %s() would not parse out of media-entry.sh or %s -- "
            "refusing to compare nothing" % (name, module)
        )
    if entry_body != module_body:
        return (
            "media_assert_sole_owner: media-entry.sh resolves %s() to something other "
            "than %s's definition" % (name, module)
        )
    return None


def media_assert_module_owns(gate, module: str, *names: str) -> None:
    """`media_assert_module_owns`. One `log_pass` for the whole set, as in bash."""
    for name in names:
        problem = media_assert_sole_owner(MEDIA_ROOT, module, name)
        if problem:
            gate.log_fail(
                "%s() is not solely owned by %s, or media-entry.sh does not resolve to "
                "it: %s" % (name, module, problem)
            )
        gate.assertions += 1
    if len(names) == 1:
        gate.log_pass(
            "%s holds the only definition of %s, and media-entry.sh resolves the name to it"
            % (module, names[0])
        )
    else:
        gate.log_pass(
            "%s holds the only definition of all %d moved functions, and media-entry.sh "
            "resolves each to it" % (module, len(names))
        )


def media_chain_sandbox(directory: pathlib.Path) -> pathlib.Path:
    """A REAL, RUNNABLE repo at `<directory>/repo`.

    Everything at the repo root is a SYMLINK to the real checkout except run.sh,
    media.sh, `.ci/media` and `.ci/legacy`, which are COPIES. Those are the only
    paths an ownership control needs to ALTER, and the last of them joined the
    list on 2026-09-06 when the router split made run-legacy.sh a third origin.
    `.ci` itself is rebuilt as a directory of symlinks for the same reason.

    Symlinks rather than copies because the whole tree is needed (run.sh sources
    .ci/config, .ci/scripts/lib, .ci/lib and reads .devcontainer/toolchain.env at
    startup) and copying it per test would be slow enough to matter.

    `.ci/legacy` IS REBUILT AS A REAL DIRECTORY OF COPIES, and that is a
    CORRECTNESS requirement rather than a preference: the ownership control plants
    a duplicate definition into each origin, and through a symlinked directory
    that append lands in the REAL checkout, corrupting a 1,300-line file owned by
    another workstream while the sandbox proves nothing. Verified 2026-09-06 in
    the bash original: before that change the sandbox path resolved straight back
    to the live tree.

    `.git` is skipped outright: nothing on the path to a marker runs git, and a
    symlink into the real object store is not worth the one accident.
    """
    repo = directory / "repo"
    (repo / ".ci").mkdir(parents=True, exist_ok=True)
    for entry in sorted(MEDIA_ROOT.iterdir()):
        if entry.name in {".ci", "run.sh", "media.sh", ".git"}:
            continue
        link = repo / entry.name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(entry)
    for entry in sorted((MEDIA_ROOT / ".ci").iterdir()):
        if entry.name == "media":
            continue
        if entry.name == "legacy":
            (repo / ".ci" / "legacy").mkdir(parents=True, exist_ok=True)
            for item in sorted(entry.iterdir()):
                if item.is_file():
                    shutil.copy2(item, repo / ".ci" / "legacy" / item.name)
            continue
        link = repo / ".ci" / entry.name
        if link.is_symlink() or link.exists():
            link.unlink()
        link.symlink_to(entry)
    (repo / ".ci" / "media").mkdir(parents=True, exist_ok=True)
    for item in sorted(MEDIA_DIR.glob("*.sh")):
        shutil.copy2(item, repo / ".ci" / "media" / item.name)
    for item in ("run.sh", "media.sh"):
        shutil.copy2(MEDIA_ROOT / item, repo / item)
    for item in (repo / "run.sh", repo / "media.sh", repo / ".ci" / "media" / "media-entry.sh"):
        item.chmod(item.stat().st_mode | 0o111)
    return repo


def media_assert_ownership_control(gate, directory: pathlib.Path, module: str, name: str) -> None:
    """THE CONTROL, in the four ways the ownership assertion could go quiet.

    An assertion nobody has watched fail is an assertion nobody has checked, and
    this one has a specific vacuity in its history: the byte-identity helper it
    replaced compared two extractions that had both found nothing and called them
    equal.

      1. A second definition put back into EVERY origin, one at a time: run.sh,
         `.ci/legacy/run-legacy.sh` (where the router split moved every verb body,
         so it is where a re-planted media function would actually land today, and
         it was invisible here until 2026-09-06) and media.sh.
      2. In media.sh the plant uses the ONE-LINE `name() { ...; }` spelling,
         because that is how media.sh actually wrote `die`, and a block-only
         search reports a one-line re-plant as ABSENT and passes.
         `fidelity_extract_any` exists for exactly that, and this is the arm that
         proves it is wired in.
      3. A name nothing defines anywhere. "Nobody defines it, so nobody else does
         either" must NOT read as unique ownership.
      4. AN ORIGIN FILE THAT IS NOT THERE. This is the arm that would otherwise be
         missing, and it is the one that matters most for arms 1 and 2: an absence
         check over a missing file passes for free, so renaming run-legacy.sh
         would silently retire a third of this proof while every gate stayed
         green.

    Each arm RESTORES the origin it damaged before the next one runs, so the arms
    are independent rather than cumulative and a failure names one cause.
    """
    repo = media_chain_sandbox(directory)

    # REFUSE TO PROCEED THROUGH A SYMLINK. Every arm below WRITES to an origin
    # inside the sandbox, and if the sandbox ever goes back to symlinking
    # .ci/legacy those writes land in the real checkout. A guard rather than a
    # comment, because the damage is silent and lands in another workstream's
    # 1,300-line file.
    if (repo / ".ci" / "legacy").is_symlink():
        gate.log_fail(
            "the sandbox symlinked .ci/legacy -- planting an origin here would write "
            "into the real checkout"
        )

    for rel in MEDIA_ORIGIN_RELPATHS:
        target = repo / rel
        original = target.read_text(encoding="utf-8")
        if rel == "media.sh":
            plant = '\n%s() { printf "%%s\\n" "$*" >&2; exit 1; }\n' % name
        else:
            plant = "\n%s() {\n    :\n}\n" % name
        target.write_text(original + plant, encoding="utf-8")
        gate.assertions += 1
        if media_assert_sole_owner(repo, module, name) is None:
            gate.log_fail(
                "the ownership assertion passed with %s defining %s() again, so it "
                "proves nothing" % (rel, name)
            )
        shutil.copy2(MEDIA_ROOT / rel, target)

    gate.assertions += 1
    if media_assert_sole_owner(MEDIA_ROOT, module, "zzz_no_such_function") is None:
        gate.log_fail(
            "the ownership assertion passed for a function nothing defines -- absence is "
            "not ownership"
        )

    # PARKED AT THE SANDBOX ROOT, not beside the file it came from. A name under
    # .ci/legacy/ would read as a claim that such a path exists, and the folder's
    # documentation gate checks every .ci/ path a media file names.
    legacy = repo / ".ci" / "legacy" / "run-legacy.sh"
    parked = repo / "absent-origin"
    legacy.rename(parked)
    gate.assertions += 1
    if media_assert_sole_owner(repo, module, name) is None:
        gate.log_fail(
            "the ownership assertion passed with an origin file absent -- a file nobody "
            "read cannot testify that the name is not in it"
        )
    parked.rename(legacy)

    gate.log_pass(
        "the ownership assertion fires on %s() re-planted in each of the %d origins "
        "(one-line form in media.sh), on a name nothing defines, and on an origin that "
        "is missing" % (name, len(MEDIA_ORIGIN_RELPATHS))
    )


def media_assert_mutation_swapped(gate, observed: str, original: str, planted: str, subject: str):
    """The two-line pair that closes every "the mutation is visible" control.

    BOTH HALVES ARE LOAD-BEARING and the first is the one people forget: asserting
    only that the planted text appears would still pass if the run were reading
    the UNMUTATED module and the marker happened to be a substring of something
    else.
    """
    gate.assert_not_contains(
        observed,
        original,
        "the original %s must be GONE, or the cases are not reading the module under test"
        % subject,
    )
    gate.assert_contains(observed, planted, "the planted %s is what the run reports" % subject)
