#!/usr/bin/env python3
"""Port of `.ci/scripts/build/pack-cli-npm.sh`.

Produces the CLI npm tarball plus the stable `rediacc-cli-latest.tgz` alias.
Driven by `.github/workflows/ci-build-docker.yml:91` ("Create CLI npm package")
with `VERSION: ${{ inputs.next_version || '0.0.0-dev' }}`, and the artifact
upload immediately after it takes the whole of `/tmp/cli-npm/`.

WHY THE VERSION IS INJECTED BEFORE `npm pack`, kept from the twin's own header:
npm names the tarball from `package.json`'s version, so the version has to be in
the file before pack runs. The `0.0.0-dev` placeholder is deliberately left
alone, because that is the value the repository carries in git and a dev build
should not masquerade as a release.

WHY IT LOCATES ITSELF instead of trusting the caller's directory, also from the
twin's header and worth carrying because it is an incident rather than a
preference: the workflow step used to set `working-directory: packages/cli` AND
address the script by a repo-root-relative path, so the two combined into
`packages/cli/.ci/scripts/build/pack-cli-npm.sh`, which does not exist, and CI
died with exit 127. The script therefore derives the repository root from its
own location and `cd`s to `packages/cli` itself.

-----------------------------------------------------------------------------
WHAT IS SHELLED OUT TO, AND WHAT IS NOT
-----------------------------------------------------------------------------
SHELLED OUT, because these are the twin's own tools and the differential fakes
them on a scratch PATH:

  * `jq --arg v <version> '.version = $v' package.json`. NOT reimplemented with
    `json.load`/`json.dump`. jq's serialisation is the thing whose BYTES land in
    a published `package.json`: its two-space indent, its key order, its
    handling of non-ASCII and of numbers that do not round-trip through a float.
    A Python rewrite would be a second opinion about all of that, and the first
    time the two disagreed the difference would appear in a tarball rather than
    in a test. `require_cmd jq` in the twin is what makes jq's presence the
    caller's problem, and this port keeps that check as its first act.
  * `npm pack --pack-destination <dir>`, with the streams inherited so npm's own
    progress and its tarball-name line reach the caller unchanged.

NOT SHELLED OUT: `mkdir -p`, `cd`, `cp`, and the `ls | head -1` selection. Those
are filesystem operations with exact Python equivalents, and spawning coreutils
for them from a program whose whole purpose is to stop spawning shells would be
theatre. The two places where that choice has an OBSERVABLE consequence are
named below rather than left to be discovered.

-----------------------------------------------------------------------------
DEFECT 1, REPRODUCED AND NOT FIXED: THE `log_error` BRANCH IS DEAD CODE
-----------------------------------------------------------------------------
The twin ends:

    CLI_PKG="$(ls rediacc-cli-*.tgz 2>/dev/null | head -1)"
    if [[ -n "$CLI_PKG" ]]; then
        ...
    else
        log_error "npm pack produced no rediacc-cli-*.tgz in $OUT_DIR"
        exit 1
    fi

That `else` arm can never run. The script is `set -euo pipefail`; when the glob
matches nothing, bash passes the unexpanded pattern to `ls`, which exits 2, and
`head` exits 0, so `pipefail` gives the pipeline status 2. The pipeline is the
only command substitution in an assignment-only simple command, so the
assignment itself carries status 2, `set -e` fires, and the script dies BEFORE
the `if` is ever reached. Driven on bash 5.3.9:

    $ cat t.sh
    set -euo pipefail
    cd /tmp
    P="$(ls zzz-no-such-*.tgz 2>/dev/null | head -1)"
    echo "reached, P=[$P]"
    $ bash t.sh; echo "rc=$?"
    rc=2

Nothing is printed on either stream. So the one failure mode the author wrote a
message for -- "npm pack produced no tarball" -- is exactly the one that reports
NOTHING and exits 2, and the exit code differs from the intended 1. This port
reproduces that behaviour byte for byte and status for status, because a port
that started printing the message would fail differently from the script it
claims to be equivalent to. Reported to the driver; the repair is a cutover-box
decision, and it is two characters (`|| true`) plus the exit code.

-----------------------------------------------------------------------------
DEFECT 2, REPRODUCED AND NOT FIXED: THE TARBALL IS CHOSEN LEXICALLY
-----------------------------------------------------------------------------
`ls rediacc-cli-*.tgz | head -1` takes the FIRST name in collation order, not
the tarball this run just produced, and `OUT_DIR` defaults to `/tmp/cli-npm`,
which nothing cleans between runs. Two consequences on any machine that runs
this twice:

  * `rediacc-cli-0.10.0.tgz` sorts BEFORE `rediacc-cli-0.9.0.tgz` (`1` < `9`),
    so a 0.9.0 build after a 0.10.0 build copies the 0.10.0 tarball to
    `rediacc-cli-latest.tgz` and reports `Packed rediacc-cli-0.10.0.tgz`.
  * `rediacc-cli-latest.tgz` ITSELF matches the glob. It normally sorts last
    (digits before letters), but when it is the only match -- a leftover alias
    beside a pack that produced a differently-named tarball -- the script runs
    `cp rediacc-cli-latest.tgz rediacc-cli-latest.tgz`, which GNU cp refuses
    with "are the same file" and exit 1.

CI is unaffected today because a GitHub runner's `/tmp/cli-npm` is empty, which
is precisely why this has never been noticed. Both behaviours are reproduced;
`select_tarball` is exported so the ordering rule can be read and tested
directly rather than inferred from a build log.

-----------------------------------------------------------------------------
DEFECT 3, REPRODUCED AND NOT FIXED, AND THE WORST OF THE THREE:
A FAILING `jq` IS REPORTED AS A SUCCESSFUL INJECTION
-----------------------------------------------------------------------------
    if [[ "$VERSION" != "0.0.0-dev" ]]; then
        jq --arg v "$VERSION" '.version = $v' package.json >package.json.tmp &&
            mv package.json.tmp package.json
        log_info "Injected version $VERSION into package.json"
    fi

`set -e` DOES NOT FIRE when jq fails. A failing member of an AND-OR list is
exempt from errexit, and bash does not re-apply errexit to the LIST's own
status; execution simply continues with the next command. Driven on bash 5.3.9
with a `jq` stub that exits 4:

    fake jq failing
    LOG: Injected version 9.9.9 into package.json
    still running, about to pack
    rc=0
    --- package.json:
    {"version":"0.0.0-dev"}
    --- tmp exists: -rw-r--r-- ... 0 ... package.json.tmp

So the run reports `✓ Injected version 9.9.9 into package.json`, `npm pack`
then builds the tarball from the UNINJECTED manifest, and the whole step exits
0. On the release path -- `ci-build-docker.yml` passes `inputs.next_version` --
that publishes a `rediacc-cli-0.0.0-dev.tgz` under a green check, and the only
trace is jq's own stderr line scrolled past in a build log. This is the
"a check that could not run reported as a check that passed" shape, in the one
place where the artifact is what ships.

It is REPRODUCED here, not repaired: `inject_version`'s status is returned and
deliberately discarded by its caller, and the success line prints regardless.
`test_a_failing_jq_is_announced_as_a_success_in_both` pins both halves. The fix
is one `||` arm plus an `exit`, and it is a cutover-box decision.

THIS DEFECT WAS FOUND BY THE DIFFERENTIAL, not by reading. The first draft of
this port returned jq's code and exited on it -- which is what the `&&` LOOKS
like it does -- and `test_port_and_twin_agree[jq-fails-manifest-untouched]`
reported `exit diverged: twin 0, port 4`.

-----------------------------------------------------------------------------
TWO DELIBERATE, DOCUMENTED DIVERGENCES, BOTH IN DIAGNOSTIC TEXT ONLY
-----------------------------------------------------------------------------
1. A FAILING `cd`. bash prints `<script path>: line <n>: cd: <dir>: No such
   file or directory` and exits 1. This port prints the same shape naming ITS
   own path and ITS own line, because that is the faithful analogue: the message
   identifies the program that could not proceed. The differential masks the
   `<path>: line <n>: ` prefix and compares the rest.

2. A FAILING `mkdir -p "$OUT_DIR"`. That diagnostic belongs to coreutils, not to
   the script, and its exact wording varies by implementation (this host's
   `mkdir -p` prints `mkdir: Permission denied` where GNU coreutils documents
   `mkdir: cannot create directory 'X': Permission denied`). The port emits the
   GNU shape and the EXIT CODE agrees; the text is pinned as divergent by
   `test_a_failing_mkdir_agrees_on_the_status_and_not_on_the_text` rather than
   quietly asserted equal.

-----------------------------------------------------------------------------
ENVIRONMENT IS READ AT THE CALL SITE, ONE NAME AT A TIME
-----------------------------------------------------------------------------
`os.environ.get("VERSION", "")` and `os.environ.get("OUT_DIR", "")`, each where
it is used. No `env = dict(os.environ)` alias anywhere: the env-manifest reader
parses direct `os.environ` reads and an alias makes both names invisible to it.

Both use `or <default>` rather than a `get` default, because the twin spells
them `${VERSION:-0.0.0-dev}` and `${OUT_DIR:-/tmp/cli-npm}`. `:-` substitutes on
UNSET **or EMPTY**, so `VERSION= ` exported as the empty string must take the
default; `get(name, default)` would return the empty string and the script would
try to inject a version of `""`.
"""

from __future__ import annotations

import glob
import os
import pathlib
import shutil
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core.common import RefusalError, require_cmd

# The version the repository carries in git. Injecting it would be a no-op, and
# the twin skips the jq call entirely rather than rewriting the file with
# identical content, which also keeps a dev build from dirtying the tree.
PLACEHOLDER_VERSION = "0.0.0-dev"

# `${OUT_DIR:-/tmp/cli-npm}`. The workflow's upload-artifact step names the same
# literal, so this default is a contract with the workflow, not a scratch path.
DEFAULT_OUT_DIR = "/tmp/cli-npm"

# The glob the twin hands to `ls`, and the alias every downstream install step
# fetches. The alias matches the glob; see DEFECT 2 above.
TARBALL_GLOB = "rediacc-cli-*.tgz"
ALIAS = "rediacc-cli-latest.tgz"

# `jq`'s output is redirected here and only then moved over `package.json`, so a
# jq that dies half-way cannot leave a truncated manifest behind. The temporary
# file IS left on disk in that case, exactly as the twin leaves it.
TMP_MANIFEST = "package.json.tmp"


def console_root() -> pathlib.Path:
    """The repository root, derived from this file's own location.

    The twin gets it from `get_repo_root` (`common.sh:205-210`), which is
    `cd "$script_dir/../../.." && pwd` off `common.sh`'s own directory.
    `rediacc_ci.paths.repo_root()` is deliberately NOT used, on the
    `infra/build_renet.py` precedent: that resolver honours `$REDIACC_CI_ROOT`
    and the twin has no such override, so a differential pointing one at a
    fixture and not the other would diverge for a reason that has nothing to do
    with the port.
    """
    # This file: <root>/.ci/rediacc_ci/build/pack_cli_npm.py
    return pathlib.Path(__file__).resolve().parents[3]


def select_tarball(names: list[str]) -> str | None:
    """`ls rediacc-cli-*.tgz 2>/dev/null | head -1`, as a pure function.

    Returns the first name in ascending byte order, or None when the list is
    empty. Exported so DEFECT 2's ordering rule can be asserted directly.

    ORDER IS BYTE ORDER, WHICH IS `ls` UNDER `LC_ALL=C` AND NOT NECESSARILY
    `ls` ELSEWHERE. GNU `ls` sorts by `LC_COLLATE`, and a locale that ignores
    punctuation would order `rediacc-cli-0.9.0.tgz` and `rediacc-cli-09.0.tgz`
    differently from this. Every name the glob can match is ASCII digits, dots,
    hyphens and lowercase letters, where the common locales agree; the case
    where they would not is named here rather than assumed away, and the
    differential pins `LC_ALL=C` on both sides so the comparison measures the
    port and not the harness's locale.
    """
    # `min` rather than `sorted(...)[0]`: same answer, one pass, and it is
    # what ruff's FURB192 asks for. The empty case is the `ls` failure that
    # DEFECT 1 describes, and it is the caller's to handle.
    return min(names) if names else None


def inject_version(version: str) -> int:
    """`jq --arg v "$V" '.version = $v' package.json >tmp && mv tmp package.json`.

    Returns jq's exit status, WHICH THE CALLER DELIBERATELY IGNORES -- see
    DEFECT 3 in the module docstring. It is returned rather than swallowed here
    so a future cutover has the number to act on without re-deriving it.

    The redirection TRUNCATES the temporary file before jq runs and the `mv`
    only happens on success, so a failing jq leaves `package.json` untouched and
    an EMPTY `package.json.tmp` behind. Both are reproduced: the leftover file is
    what a developer sees after a failure, and a port that tidied up would be
    describing a different script.
    """
    tmp = pathlib.Path(TMP_MANIFEST)
    with tmp.open("wb") as handle:
        completed = subprocess.run(
            ["jq", "--arg", "v", version, ".version = $v", "package.json"],
            stdout=handle,
            check=False,
        )
    if completed.returncode != 0:
        return completed.returncode
    # `mv` within one directory is a rename, and `os.replace` is atomic where
    # the platform allows it. Same observable, minus a process.
    os.replace(TMP_MANIFEST, "package.json")
    return 0


def _bash_style_error(message: str, line: int) -> None:
    """`<this file>: line <n>: <message>`, the shape bash uses for `cd` failures.

    Divergence 1 in the module docstring. The path names THIS program because
    that is the program that could not proceed; the differential masks the
    prefix and compares the rest.
    """
    print("%s: line %d: %s" % (__file__, line, message), file=sys.stderr, flush=True)


def main() -> int:
    # STEP 1: refuse early, in the twin's order -- jq first, then npm. The order
    # is observable: on a host missing both, the message names jq.
    try:
        require_cmd("jq")
        require_cmd("npm")
    except RefusalError as refusal:
        refusal.report()
        return refusal.code

    # STEP 2: locate ourselves. `cd "$(get_repo_root)/packages/cli"`.
    cli_dir = console_root() / "packages" / "cli"
    try:
        os.chdir(cli_dir)
    except OSError as exc:
        _bash_style_error(
            "cd: %s: %s" % (cli_dir, exc.strerror or "No such file or directory"),
            sys._getframe().f_lineno,
        )
        return 1

    version = os.environ.get("VERSION", "") or PLACEHOLDER_VERSION
    out_dir = os.environ.get("OUT_DIR", "") or DEFAULT_OUT_DIR

    # STEP 3: inject, unless this is the placeholder. See the module docstring
    # for why the placeholder is skipped rather than written back.
    if version != PLACEHOLDER_VERSION:
        # DEFECT 3, REPRODUCED AND NOT FIXED. jq's status is thrown away and the
        # success line prints unconditionally. Written as a bare call with the
        # return value discarded, so the discard is visible rather than implied.
        inject_version(version)
        log.info("Injected version %s into package.json" % version)

    # STEP 4: `mkdir -p "$OUT_DIR"`. Divergence 2: the status agrees, the
    # coreutils diagnostic does not.
    try:
        os.makedirs(out_dir, exist_ok=True)
    except OSError as exc:
        print(
            "mkdir: cannot create directory '%s': %s" % (out_dir, exc.strerror),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # STEP 5: pack. Streams inherited, so npm's tarball-name line stays on the
    # caller's stdout where the workflow's log shows it. Flushed first because
    # this process has already written to stderr through `log` and a buffered
    # parent interleaving with an unbuffered child is a difference the port
    # would be introducing all by itself.
    sys.stdout.flush()
    sys.stderr.flush()
    try:
        completed = subprocess.run(
            ["npm", "pack", "--pack-destination", out_dir],
            check=False,
        )
    except PermissionError:
        return 126  # bash's "cannot execute"
    except OSError:
        return 127  # bash's "command not found"
    if completed.returncode != 0:
        # `set -e` on a plain command: the twin dies with npm's own status and
        # prints nothing of its own.
        return completed.returncode

    # STEP 6: `cd "$OUT_DIR"`, then choose the tarball.
    try:
        os.chdir(out_dir)
    except OSError as exc:
        _bash_style_error(
            "cd: %s: %s" % (out_dir, exc.strerror or "No such file or directory"),
            sys._getframe().f_lineno,
        )
        return 1

    package = select_tarball(sorted(glob.glob(TARBALL_GLOB)))
    if package is None:
        # DEFECT 1. The twin's `log_error "npm pack produced no ..."` never runs:
        # the assignment carries `ls`'s exit 2 through `pipefail` and errexit
        # kills the script here, silently. Reproduced exactly -- no message, and
        # status 2 rather than the 1 the unreachable branch intended.
        return 2

    # DEFECT 2's second face: when the alias is the only match, `cp x x` is what
    # the twin runs and GNU cp refuses it. `os.path.samefile` is the same test cp
    # makes (device plus inode), so a hardlinked alias is caught too, and the
    # message is cp's own C-locale wording with the operands as GIVEN.
    try:
        same = os.path.exists(ALIAS) and os.path.samefile(package, ALIAS)
    except OSError:
        same = False
    if same:
        print(
            "cp: '%s' and '%s' are the same file" % (package, ALIAS),
            file=sys.stderr,
            flush=True,
        )
        return 1

    # `cp src dst` overwrites dst in place and does not carry the source's mode
    # onto an existing destination, which is `shutil.copyfile`, not `copy2`.
    shutil.copyfile(package, ALIAS)
    log.info("Packed %s (+ %s alias)" % (package, ALIAS))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
