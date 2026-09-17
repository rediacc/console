#!/usr/bin/env python3
"""Port of `.ci/scripts/security/actionlint.sh`.

W7P6 wave 28. The bash twin stays the LIVE registered gate ("Workflow lint (actionlint)", lane quality-code); this module is its VERIFIED-EQUIVALENT ALTERNATIVE, proved byte-for-byte on both streams by
`.ci/rediacc_ci/tests/test_security_actionlint.py` and by the K=5 shadow ledger
`.ci/shadow/w7p6-actionlint.observations.jsonl`. Nothing is repointed at this file. Cutover is a separate, later, driver-only step.

WHAT IT DOES. Acquires actionlint at the pin (a PATH binary at the exact pinned version wins; otherwise a checksum-verified release tarball is fetched into a cache directory whose rungs are NOT the ones the twin's line reads as; see `cache_dir`), enumerates every workflow file under `.github/workflows/` PLUS the vendorable templates under `.ci/*/workflow/`, refuses an empty corpus,
and runs `actionlint -no-color` over the lot.

REAL RUNS OR STUBS: BOTH, SPLIT THE SAME WAY WAVE 27's dependency-inventory PORT
SPLIT THEM.

  * The HAPPY PATHS run the REAL actionlint against this repository's REAL 29
    workflow files. actionlint is a pure READER: it opens YAML, parses it, and
    writes findings to stdout. It creates nothing, and the differential hashes
    every one of the 29 inputs before and after each real-run case and refuses a
    byte of drift, so "read-only" is asserted rather than assumed. No fixture
    reproduces 29 real workflows with their real `${{ }}` expression graph, and
    that graph is the only thing this gate exists to check.
  * The FAILURE PATHS (a corpus of zero, a checksum mismatch, an unfetchable
    URL, an unsupported architecture, actionlint itself reporting findings) run
    against a RECORDING FAKE `actionlint` and a RECORDING FAKE `curl` on a
    scratch PATH, because there is no way to make the real tool fail on demand
    without editing a real workflow file. Every fake appends its exact argv to
    `$FAKE_LOG` and the differential compares the two call logs as well as the
    two streams: a port that produced identical bytes by asking a DIFFERENT
    question would pass a stdout comparison and fail the call-log one.

PORT NOTES. Unless an item says otherwise the behaviour is REPRODUCED, not repaired.

  1. `tr -d 'v'` DELETES EVERY `v`, NOT A LEADING ONE. The PATH-version probe is
     `actionlint --version | head -1 | tr -d 'v'`, so a hypothetical version
     string containing a `v` anywhere loses it. Reproduced with
     `line.replace("v", "")` rather than `lstrip`/`removeprefix`, because the
     two disagree and the twin's answer is the one that decides whether a
     developer's own install is honoured.

  2. A `--version` THAT PRINTS NOTHING BUT SUCCEEDS leaves `have` empty and the
     twin logs "actionlint  is on PATH but this gate pins ..." with a DOUBLE
     SPACE where the version would be. Reproduced verbatim; it is the twin's
     message and a reader seeing the double space is being told something true.

  3. **THE EXIT-3 ANTI-VACUITY REFUSAL IS UNREACHABLE, AND AN EMPTY CORPUS EXITS
     1 IN COMPLETE SILENCE.** This is the defect this wave found, reproduced
     here and NOT fixed. `collect_targets`'s last statement is

         for f in "$REPO_ROOT"/.ci/*/workflow/*.yml; do
             [[ -f "$f" ]] && echo "$f"
         done

     so the function's return status is the status of the LAST `[[ -f ]]` test.
     When that glob matches nothing bash leaves the literal pattern in `$f`, the
     test is false, the function returns 1, and `targets="$(collect_targets)"`
     under `set -e` KILLS THE SCRIPT THERE -- before `count` is computed, before
     the `-eq 0` test, with no message on either stream. Measured 2026-09-14 in a
     scratch tree:

         no .github/workflows/*.yml, no .ci/*/workflow/*.yml -> rc 1, 0 bytes out
         no .github/workflows/*.yml, one template present    -> rc 0, lints 1 file
         two workflows, no template                          -> rc 1, 0 bytes out

     Two consequences, and the second is worse than the first. The refusal the
     header describes ("a lint run over zero files reports success while
     checking nothing") can NEVER fire. And the silent status is 1, which is the
     SAME code the gate uses for "actionlint reported findings", so a CI reader
     sees a red workflow-lint step with an empty log and goes looking for a
     `${{ }}` error that does not exist. Reproduced exactly by
     `collect_targets_status` below.

  4. THE GLOB ORDER IS bash's, WHICH IS LC_COLLATE's. `*.yml` expands sorted by
     the collation of the ambient locale, so `ci-build-cli.yml` sorts BEFORE
     `ci.yml` under `LC_ALL=C` and AFTER it under `en_US.UTF-8` (glibc ignores
     punctuation at the first collation level). This port sorts by BYTES, which
     is the C answer. Every differential case and the shadow ledger pin
     `LC_ALL=C` on both sides, and this is stated here rather than discovered
     later: under a UTF-8 locale the two sides would hand actionlint the same 29
     files in a different ORDER, which is invisible on a clean tree and visible
     in the order of the findings on a dirty one.

  5. THE FOUR `.yml` / `.yaml` / TEMPLATE GLOBS ARE THREE SEPARATE PASSES, in the
     twin's order: `.github/workflows/*.yml`, then `.github/workflows/*.yaml`,
     then `.ci/*/workflow/*.yml`. Concatenated, NOT re-sorted across passes. A
     single `sorted()` over the union would put a `.yaml` file before a later
     `.yml` file and change the argv.

  6. curl's OWN STDERR IS NOT CAPTURED. `-fsSL` includes `-S`, which makes curl
     print `curl: (22) ...` to stderr on a failure, and the twin does not
     redirect it. This port therefore inherits curl's stderr instead of
     capturing it. (`rediacc_ci.core.toolchain._curl`, the wave-6 port of the
     sibling acquisition helpers, DOES capture it; that divergence is reported
     by this wave, not fixed here.)

  7. THE LOGGER IS `rediacc_ci.log`, because the twin sources `common.sh` and
     the house logger is that logger's differential-checked port. It carries one
     inherited, already-pinned divergence: under `CI=true` with stderr on a tty,
     `common.sh` still emits colour and `rediacc_ci.log` does not
     (`tests/test_log.py::test_ci_true_is_the_one_deliberate_divergence`).
     `test_security_actionlint.py` asserts BOTH sides of that combination so the
     divergence stays a pinned decision rather than a surprise.

  8. `require_cmd` IS NOT CALLED HERE, so the multi-argument `require_cmd` defect
     (`common.sh:141-148` binds `local cmd="$1"` and ignores the rest) does not
     apply to this script. Checked, and recorded so the next reader does not have
     to check again.

  9. `$CI_TEMP` IS DEAD TEXT IN THE CACHE PATH, because `common.sh` overwrites it
     at source time. The full measurement is in `cache_dir`'s docstring; it is
     the second of the three defects this wave found in this twin.

 10. **A `--version` THAT EXITS NON-ZERO KILLS THE GATE SILENTLY WITH THAT CODE.**
     The third defect. `have="$(actionlint --version 2>/dev/null | head -1 |
     tr -d 'v')"` runs under `set -euo pipefail`, so `pipefail` hands the
     substitution actionlint's own exit status and `set -e` acts on the
     assignment. Measured 2026-09-14 with a PATH binary whose `--version` exits
     3: the gate exits 3 with ZERO bytes on both streams -- and 3 is this gate's
     DOCUMENTED code for "nothing to check (vacuous)", so a broken shim on PATH
     is reported as an empty corpus. Together with note 3 that is two distinct
     silent failures wearing two of the gate's three documented exit codes.
     Reproduced by `path_version` returning its status and `ensure_actionlint`
     raising `SystemExit(status)` on it.

ONE NAMED DIVERGENCE THIS PORT ADDS: `paths.repo_root()` honours `$REDIACC_CI_ROOT` and the twin's `SCRIPT_DIR/../../..` does not.
"""

from __future__ import annotations

import hashlib
import os
import pathlib
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile

from rediacc_ci import log, paths

# `readonly NAME="value"`, as `.ci/config/constants.sh` writes it. Anchored and
# quote-aware for the same reason `core.toolchain.CONSTANTS_ASSIGN_RE` is: a commented-out line or a `readonly` inside a heredoc must not contribute a hash.
CONSTANTS_ASSIGN = r'^readonly\s+([A-Z][A-Z0-9_]*)="([^"]*)"\s*$'

# `KEY=value` in `.devcontainer/toolchain.env`. ACTIONLINT_VERSION lives there
# (constants.sh:234 re-exports it with `:?`), because the image build reads the same number.
PINS_RELPATH = (".devcontainer", "toolchain.env")

# uname -m to the arch spelling actionlint uses in its asset names, paired with the constants.sh key holding that asset's sha256.
ARCH_TABLE = {
    "x86_64": ("amd64", "ACTIONLINT_SHA256_LINUX_AMD64"),
    "amd64": ("amd64", "ACTIONLINT_SHA256_LINUX_AMD64"),
    "aarch64": ("arm64", "ACTIONLINT_SHA256_LINUX_ARM64"),
    "arm64": ("arm64", "ACTIONLINT_SHA256_LINUX_ARM64"),
}

# `curl -fsSL --max-time 180 --retry 3 --retry-delay 5`. `-S` is what makes curl speak on failure; see port note 6.
CURL_ARGS = ("-fsSL", "--max-time", "180", "--retry", "3", "--retry-delay", "5")


# --------------------------------------------------------------------------- Pins ---------------------------------------------------------------------------


def _assignments(text: str, pattern: str) -> dict[str, str]:
    """Every `NAME=value` the pattern matches, later lines winning."""
    return dict(re.findall(pattern, text, re.MULTILINE))


def actionlint_version(root: pathlib.Path | None = None) -> str:
    """`$ACTIONLINT_VERSION`, from `.devcontainer/toolchain.env`.

    Read from the pins file rather than from constants.sh because constants.sh
    only re-exports it: `readonly ACTIONLINT_VERSION="${ACTIONLINT_VERSION:?...}"`
    resolves to whatever the `set -a` source of toolchain.env put in scope.
    """
    base = paths.repo_root() if root is None else root
    path = base.joinpath(*PINS_RELPATH)
    if not path.is_file():
        return ""
    pairs = _assignments(
        path.read_text(encoding="utf-8", errors="replace"), r"^([A-Z][A-Z0-9_]*)=(.*)$"
    )
    return pairs.get("ACTIONLINT_VERSION", "")


def actionlint_checksums(root: pathlib.Path | None = None) -> dict[str, str]:
    """The two `ACTIONLINT_SHA256_LINUX_*` pins from `.ci/config/constants.sh`."""
    base = paths.repo_root() if root is None else root
    path = base / ".ci" / "config" / "constants.sh"
    if not path.is_file():
        return {}
    found = _assignments(path.read_text(encoding="utf-8", errors="replace"), CONSTANTS_ASSIGN)
    return {k: v for k, v in found.items() if k.startswith("ACTIONLINT_SHA256_")}


def cache_dir(version: str) -> pathlib.Path:
    """Where the pinned binary is cached. NOT what the twin's line says it is.

    THE SECOND DEFECT THIS WAVE FOUND. The twin writes

        CACHE_DIR="${CI_TEMP:-${RUNNER_TEMP:-/tmp}}/actionlint-${ACTIONLINT_VERSION}"

    two lines after `source common.sh`, and `common.sh:509-514` does this at source time, unconditionally:

        CI_TEMP="$(get_temp_dir)"   # RUNNER_TEMP, else TMPDIR, else /tmp
        export CI_OS CI_ARCH CI_TEMP

    So by the time that line runs, `$CI_TEMP` is ALWAYS non-empty and always common.sh's own answer. Two consequences, both measured 2026-09-14:

        CI_TEMP=/CALLER_SET                 -> CI_TEMP is /tmp    (caller ignored)
        CI_TEMP=/CALLER_SET TMPDIR=/TMPD    -> CI_TEMP is /TMPD   (caller ignored)

    A caller that exports `CI_TEMP` to steer this gate's cache is SILENTLY OVERRULED, and the `:-` fallbacks in the twin's own line are dead text: the effective rung order is `RUNNER_TEMP`, then `TMPDIR`, then `/tmp`, which is not the order the line reads as. Note that this makes the gate DISAGREE with `toolchain.sh:toolchain_cache_dir`, whose order really is `CI_TEMP`,
    `RUNNER_TEMP`, `TMPDIR` -- so on a host with `CI_TEMP` set, actionlint and shfmt cache in two different places for reasons nobody wrote down.

    Reproduced, not repaired: this function reads the rungs that actually decide, and deliberately does NOT read `CI_TEMP`.
    """
    base = os.environ.get("RUNNER_TEMP", "") or os.environ.get("TMPDIR", "") or "/tmp"
    return pathlib.Path(base) / ("actionlint-%s" % version)


# --------------------------------------------------------------------------- Acquisition ---------------------------------------------------------------------------


def path_version(binary: str) -> tuple[str, int]:
    """`actionlint --version 2>/dev/null | head -1 | tr -d 'v'`, AND ITS STATUS.

    THE STATUS IS RETURNED BECAUSE IT IS FATAL. Port notes 1 and 10: the twin
    runs this as `have="$(...)"` under `set -euo pipefail`, so a `--version`
    that exits non-zero takes the pipeline's status through the command substitution and kills the gate on the spot, silently, with THAT code.

    `126` for a binary that cannot be executed, which is bash's own status for the same condition. `command -v` has already said the path is executable by the time this runs, so it is the OSError-on-fork case rather than a routine one.
    """
    try:
        proc = subprocess.run(
            [binary, "--version"],
            capture_output=True,
            text=True,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return "", 126
    first = proc.stdout.split("\n", 1)[0] if proc.stdout else ""
    return first.replace("v", ""), proc.returncode


def sha256_of(path: pathlib.Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def ensure_actionlint(version: str, checksums: dict[str, str]) -> str:
    """The binary to run. Exits 2 the way `ensure_actionlint` (:57-115) does."""
    cache = cache_dir(version)
    binary = cache / "actionlint"

    on_path = shutil.which("actionlint")
    if on_path is not None:
        have, status = path_version(on_path)
        # `set -e` + `pipefail` on `have="$(...)"`. Port note 10: this is a
        # SILENT exit carrying the probe's own code, before any comparison.
        if status != 0:
            raise SystemExit(status)
        if have == version:
            return on_path
        log.info(
            "actionlint %s is on PATH but this gate pins %s; fetching the pinned build"
            % (have, version)
        )

    if os.access(str(binary), os.X_OK):
        return str(binary)

    machine = platform.machine()
    entry = ARCH_TABLE.get(machine)
    if entry is None:
        log.error("no pinned actionlint checksum for architecture '%s'" % machine)
        log.error("add one to .ci/config/constants.sh rather than downloading unverified")
        raise SystemExit(2)
    arch, sha_key = entry
    sha = checksums.get(sha_key, "")

    url = (
        "https://github.com/rhysd/actionlint/releases/download/v%s/"
        "actionlint_%s_linux_%s.tar.gz" % (version, version, arch)
    )
    cache.mkdir(parents=True, exist_ok=True)
    # PRIVATE STAGING DIR, mirroring `mktemp -d "$CACHE_DIR/al.XXXXXXXX"` in the twin. The cache lives under a temp root a CI runner shares across every concurrent invocation, so the fixed `cache / "actionlint.tar.gz"` both sides used was one inode they all downloaded into at once; the winner's unlink then deleted it out from under the losers mid-verify. The twin carries the
    # measurement (8 racers on a cold cache, 7 exited 2, all with a false "checksum MISMATCH"). Extraction is staged too, so a half-written binary can never sit at the final path.
    stage = pathlib.Path(tempfile.mkdtemp(prefix="al.", dir=str(cache)))
    tmp = stage / "actionlint.tar.gz"

    log.info("fetching actionlint %s (%s)" % (version, arch))
    # stderr INHERITED, not captured: `-fsSL` includes `-S`. See port note 6.
    proc = subprocess.run(
        ["curl", *CURL_ARGS, "-o", str(tmp), url],
        check=False,
    )
    if proc.returncode != 0:
        log.error("could not download actionlint from %s" % url)
        shutil.rmtree(stage, ignore_errors=True)
        raise SystemExit(2)

    actual = sha256_of(tmp) if tmp.is_file() else ""
    if actual != sha or not sha:
        log.error("actionlint checksum MISMATCH -- refusing to extract")
        log.error("  expected: %s" % sha)
        log.error("  actual:   %s" % actual)
        log.error(
            "if the release was legitimately re-cut, update the pin in .ci/config/constants.sh"
        )
        shutil.rmtree(stage, ignore_errors=True)
        raise SystemExit(2)

    with tarfile.open(str(tmp), "r:gz") as archive:
        member = archive.getmember("actionlint")
        archive.extract(member, str(stage), filter="data")
    staged = stage / "actionlint"
    # chmod the STAGED binary and move it in already executable, so there is no window in which the final path exists but cannot be run.
    staged.chmod(0o755)
    staged.replace(binary)
    shutil.rmtree(stage, ignore_errors=True)
    return str(binary)


# --------------------------------------------------------------------------- The corpus ---------------------------------------------------------------------------


def collect_targets(root: pathlib.Path | None = None) -> list[str]:
    """The absolute paths the twin's three glob passes yield, in its order.

    THREE PASSES, CONCATENATED, NOT RE-SORTED. See port note 5. Each pass is
    sorted by bytes, which is bash's answer under `LC_COLLATE=C`; see note 4.
    """
    base = paths.repo_root() if root is None else root
    out: list[str] = []
    for pattern in ("*.yml", "*.yaml"):
        out.extend(
            str(p) for p in sorted((base / ".github" / "workflows").glob(pattern)) if p.is_file()
        )
    # Workflow TEMPLATES outside .github/, invisible to every other workflow gate. `.ci/*/workflow/*.yml` is a two-level glob: bash expands the `*` directory component sorted too.
    templates: list[str] = []
    ci_dir = base / ".ci"
    if ci_dir.is_dir():
        for child in sorted(ci_dir.iterdir()):
            workflow_dir = child / "workflow"
            if not workflow_dir.is_dir():
                continue
            templates.extend(str(p) for p in sorted(workflow_dir.glob("*.yml")) if p.is_file())
    out.extend(templates)
    return out


def template_glob_expansion(root: pathlib.Path | None = None) -> list[str]:
    """What bash's `"$REPO_ROOT"/.ci/*/workflow/*.yml` expands to, LITERAL included.

    A glob that matches nothing is left as its own text by bash (no `nullglob` here), and that literal is what the twin's final `[[ -f "$f" ]]` tests. The literal is returned rather than an empty list precisely so the caller can reproduce the test on it.
    """
    base = paths.repo_root() if root is None else root
    pattern = str(base / ".ci" / "*" / "workflow" / "*.yml")
    matches: list[str] = []
    ci_dir = base / ".ci"
    if ci_dir.is_dir():
        for child in sorted(ci_dir.iterdir()):
            workflow_dir = child / "workflow"
            if workflow_dir.is_dir():
                matches.extend(str(p) for p in sorted(workflow_dir.glob("*.yml")))
    return matches or [pattern]


def collect_targets_status(root: pathlib.Path | None = None) -> int:
    """`collect_targets`'s RETURN STATUS, which is what `set -e` acts on.

    The status of the last `[[ -f "$f" ]]` in the last loop. See port note 3: this is the whole reason an empty corpus exits 1 in silence instead of reaching the exit-3 refusal.
    """
    last = template_glob_expansion(root)[-1]
    return 0 if pathlib.Path(last).is_file() else 1


# --------------------------------------------------------------------------- main ---------------------------------------------------------------------------


def main(argv: list[str]) -> int:
    """`main` (:118-157). argv is accepted and ignored, as `main "$@"` does."""
    del argv
    root = paths.repo_root()
    version = actionlint_version(root)
    binary = ensure_actionlint(version, actionlint_checksums(root))

    targets = collect_targets(root)
    count = len(targets)

    # `targets="$(collect_targets)"` UNDER `set -e`. When the last template glob
    # matched nothing the substitution's status is 1 and bash exits RIGHT HERE, silently. Port note 3; this is a reproduced defect, not a design.
    if collect_targets_status(root) != 0:
        return 1

    # ANTI-VACUITY. A linter with no input exits 0 and looks like a pass. UNREACHABLE in practice; see port note 3. Kept because the twin keeps it.
    if count == 0:
        log.error("no workflow files found under .github/workflows/ or .ci/*/workflow/")
        log.error("a lint run over zero files reports success while checking nothing")
        return 3

    log.step("Running actionlint over %d workflow file(s)" % count)

    # Streams INHERITED. The twin runs actionlint with its stdout and stderr attached to the gate's own, so a finding lands on the caller's stdout unbuffered and interleaved with nothing.
    sys.stdout.flush()
    sys.stderr.flush()
    proc = subprocess.run([binary, "-no-color", *targets], check=False)

    if proc.returncode != 0:
        log.error("actionlint reported findings in the workflow files above")
        log.error("these are parse/expression/context errors or ShellCheck findings in")
        log.error("an inline run: block. A bad ${{ }} expression makes a run start with")
        log.error("ZERO jobs and no error message anywhere.")
        return 1

    log.info("actionlint clean across %d workflow file(s)" % count)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
