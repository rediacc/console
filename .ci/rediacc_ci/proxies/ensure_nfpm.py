"""Port of `.ci/scripts/test/proxies/proxy-ensure-nfpm.sh`.

Local proxy for `.ci/scripts/build/ensure-nfpm.sh`, wired as the registered gate `check:ci-proxy-ensure-nfpm` (`package.json:392`, `scripts/ci-runner/manifest.ts:7496-7499`). See the twin's header for what it guards in CI and why it builds a THROWAWAY fixture root instead of running in this checkout: the warm `.ci/cache/bin/nfpm` here would take the early-exit branch and the
download and checksum would never be reached.

The SUBJECT stays bash and is run as bash, exactly as the twin runs it. Only the proxy is ported, same division as `rediacc_ci.proxies.docker_prepull`. A Python port of the subject also exists at `rediacc_ci.build.ensure_nfpm`; this proxy does NOT point at it, because the thing under test is what CI executes.

-----------------------------------------------------------------------------
A REAL DEFECT IN THE TWIN, REPRODUCED RATHER THAN FIXED
-----------------------------------------------------------------------------
`proxy-ensure-nfpm.sh:33` is `set -uo pipefail` -- no `-e`. But `:92-95`, `:133-136` and `:158-160` wrap each subject run in `set +e` / `set -e`, and `set -e` TURNS ERREXIT ON rather than restoring the previous state. Measured directly on this host:

    $ bash -c 'set -uo pipefail; echo "$-"; set +e; :; set -e; echo "$-"'
    huBc
    ehuBc

So from `:95` onward the script runs under errexit it never asked for, and there is exactly one place that matters. `:113` is

    GOT_VERSION="$("$PRINTED_DIR/nfpm" --version 2>&1 | grep -oE '[0-9]+\\.[0-9]+\\.[0-9]+' | head -1)"

and under `pipefail` a `grep` that matches nothing makes the whole pipeline non-zero, which under errexit kills the script. Measured:

    $ bash -c 'set -uo pipefail; set +e; :; set -e;
               X="$(echo hi | grep -oE "[0-9]+" | head -1)"; echo REACHED'
    (no output, exit 1)

BLAST RADIUS: the day `nfpm --version` stops printing an `N.N.N` token -- a banner change, a `--version` that goes to stdout as JSON -- this REGISTERED gate exits 1 having printed four PASS lines, no FAIL line and no explanation. That is indistinguishable from the gate crashing, and it is the version-drift check itself that disappears. It is NOT reachable today (nfpm 2.45.0 prints
`version: 2.45.0`), which is why it is documented and pinned rather than fixed: `_version_or_die` reproduces the abort, and `test_proxies_ensure_nfpm.py::test_a_version_with_no_semver_token_kills_both_ sides` drives it with a shimmed nfpm on both sides.

-----------------------------------------------------------------------------
THE PIN IS READ WITH BOTH STREAMS DISCARDED HERE, unlike in the subject
-----------------------------------------------------------------------------
`:59-63` is `$( source "$ROOT/.ci/config/constants.sh" >/dev/null 2>&1; printf
'%s' "${NFPM_VERSION:-}" )`. A constants.sh that refuses (missing
`.devcontainer/toolchain.env`) therefore says NOTHING here, and the proxy's own "could not read NFPM_VERSION" message is the only diagnostic. The subject inherits both streams instead. Reproduced as written, in both places.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-ensure-nfpm.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import shutil
import subprocess
import sys
import tempfile

from rediacc_ci.core import proxyx

SUBJECT_REL = ".ci/scripts/build/ensure-nfpm.sh"

# `grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1` (:113).
SEMVER_RE = re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")

# The `uname` shim written at `:150-155`, verbatim.
UNAME_SHIM = """#!/bin/bash
for a in "$@"; do [[ "$a" == "-m" ]] && { echo riscv64; exit 0; }; done
exec /usr/bin/uname "$@"
"""


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:35-36).

    The twin resolves it from its own location under `.ci/scripts/test/proxies/`; this module sits at `.ci/rediacc_ci/proxies/`, which is `parents[3]` rather than four `..` from a deeper directory. `rediacc_ci.paths.repo_root()` is not used, for the reason `rediacc_ci.infra.ci_start_elite._console_root` states: it honours $REDIACC_CI_ROOT and the twin has no such override.
    """
    return pathlib.Path(__file__).resolve().parents[3]


def read_pin(constants: pathlib.Path) -> str:
    """`:59-63`. Both streams of the `source` are DISCARDED; "" when unset."""
    body = 'source "$1" >/dev/null 2>&1\nprintf "%s" "${NFPM_VERSION:-}"\n'
    proc = subprocess.run(
        ["bash", "-c", body, "bash", str(constants)],
        stdout=subprocess.PIPE,
        stderr=subprocess.DEVNULL,
        text=True,
        check=False,
    )
    return proc.stdout


def clean_path(path: str) -> str:
    """`:83-87`. Drop the directory holding `nfpm` from PATH, if there is one.

    `tr ':' '\\n' | grep -vxF "$NFPM_HOME" | paste -sd: -` removes EVERY entry equal to that directory, not just the first, and joins the rest with `:`. A PATH with no nfpm on it is returned unchanged, which is the `if` at :84.
    """
    found = shutil.which("nfpm", path=path)
    if found is None:
        return path
    home = os.path.dirname(found)
    return ":".join(entry for entry in path.split(":") if entry != home)


def semver_of(text: str) -> str:
    """`grep -oE '<semver>' | head -1` over the merged streams (:113)."""
    match = SEMVER_RE.search(text)
    return match.group(0) if match else ""


def run() -> int:
    root = _proxy_root()
    subject = root / SUBJECT_REL
    constants = root / ".ci" / "config" / "constants.sh"
    toolchain_env = root / ".devcontainer" / "toolchain.env"

    p = proxyx.Proxy("ensure-nfpm", SUBJECT_REL)
    p.need_exec(str(subject), "the subject script is missing from this checkout")
    p.need_file(str(constants), "the pin site is missing from this checkout")
    p.need_file(str(toolchain_env), "constants.sh sources this; the checkout is incomplete")
    p.need_cmd("curl", "sudo apt-get install -y curl")
    p.need_cmd("sha256sum", "sudo apt-get install -y coreutils")
    p.need_cmd("tar", "sudo apt-get install -y tar")
    p.need_url(
        "https://github.com",
        "the subject fetches the pinned tarball from github releases",
    )
    p.preflight()

    pinned = read_pin(constants)
    if not pinned:
        colour = p._c(proxyx.RED)
        off = p._c(proxyx.OFF)
        print(
            "%sproxy ensure-nfpm: could not read NFPM_VERSION out of "
            ".ci/config/constants.sh%s" % (colour, off),
            file=sys.stderr,
        )
        print(
            "  Every comparison below would then be against an empty string, which matches",
            file=sys.stderr,
        )
        print(
            "  nothing and would report a false failure, or worse a false pass.",
            file=sys.stderr,
        )
        return 1
    p.ok("read the pin from .ci/config/constants.sh: NFPM_VERSION=%s" % pinned)

    fix = pathlib.Path(tempfile.mkdtemp())
    try:
        return _drive(p, root, fix, pinned)
    finally:
        # `trap 'rm -rf "$FIX"' EXIT` (:73).
        shutil.rmtree(fix, ignore_errors=True)


def _version_or_die(binary: pathlib.Path) -> str:
    """`:113`, INCLUDING the errexit abort. See the module docstring.

    The twin runs this line under an errexit it acquired from `set -e` at `:95`, so a `--version` with no `N.N.N` token in it does not yield an empty string: it ENDS THE SCRIPT with exit 1 and nothing more on either stream. Raising SystemExit(1) here is that, not a stylistic choice.
    """
    proc = subprocess.run(
        [str(binary), "--version"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        check=False,
    )
    version = semver_of(proc.stdout)
    if not version:
        raise SystemExit(1)
    return version


def _drive(p: proxyx.Proxy, root: pathlib.Path, fix: pathlib.Path, pinned: str) -> int:
    # `:74-79`. A minimal fixture root with a COLD cache.
    (fix / ".ci" / "scripts" / "build").mkdir(parents=True, exist_ok=True)
    (fix / ".ci" / "config").mkdir(parents=True, exist_ok=True)
    (fix / ".devcontainer").mkdir(parents=True, exist_ok=True)
    fix_subject = fix / SUBJECT_REL
    shutil.copyfile(root / SUBJECT_REL, fix_subject)
    shutil.copytree(root / ".ci" / "scripts" / "lib", fix / ".ci" / "scripts" / "lib")
    shutil.copyfile(
        root / ".ci" / "config" / "constants.sh", fix / ".ci" / "config" / "constants.sh"
    )
    shutil.copyfile(
        root / ".devcontainer" / "toolchain.env", fix / ".devcontainer" / "toolchain.env"
    )
    fix_subject.chmod(0o755)

    path = clean_path(os.environ.get("PATH", ""))

    def _run(extra_path: str | None = None, merge: bool = False):
        env = dict(os.environ)
        env["PATH"] = extra_path + ":" + path if extra_path else path
        return subprocess.run(
            [str(fix_subject)],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT if merge else subprocess.PIPE,
            text=True,
            check=False,
        )

    first = _run()
    # `$(...)` strips ALL trailing newlines.
    printed = first.stdout.rstrip("\n")

    if first.returncode == 0:
        p.ok("cold-cache run exited 0")
    else:
        p.bad("cold-cache run exited %d" % first.returncode)
        print("  --- stderr ---", file=sys.stderr)
        sys.stderr.write(first.stderr)

    if printed and pathlib.Path(printed).is_dir():
        # `${PRINTED_DIR#"$FIX"/}` (:106), a PREFIX strip, not a relative path.
        shown = printed[len(str(fix)) + 1 :] if printed.startswith(str(fix) + "/") else printed
        p.ok("it printed a directory that exists: %s" % shown)
    else:
        p.bad(
            "it printed '%s', which is not a directory; every caller does "
            'PATH="$(ensure-nfpm.sh):$PATH" and would silently get nothing' % printed
        )

    binary = pathlib.Path(printed) / "nfpm"
    if os.access(str(binary), os.X_OK):
        p.ok("the printed directory holds an executable nfpm")
        got = _version_or_die(binary)
        if got == pinned:
            p.ok("the installed nfpm reports %s, exactly the pin" % got)
        else:
            p.bad(
                "the installed nfpm reports '%s' but the pin is '%s'; the download "
                "and the pin site have drifted apart" % (got, pinned)
            )
        if "fetching nfpm" in first.stderr:
            p.ok(
                "the cold-cache run really fetched and verified (its 'fetching nfpm' "
                "line is present), so the checksum branch was exercised, not skipped"
            )
        else:
            p.bad(
                "the run produced a binary without printing its 'fetching nfpm' line; "
                "the fixture cache was not cold and the download plus checksum path "
                "went unexercised"
            )
    else:
        p.bad("no executable nfpm at %s/nfpm" % printed)

    # IDEMPOTENCE (:131-145).
    second = _run()
    second_printed = second.stdout.rstrip("\n")
    if second.returncode == 0 and second_printed == printed:
        if "fetching nfpm" in second.stderr:
            p.bad(
                "the second call downloaded again; the subject claims to be idempotent and is not"
            )
        else:
            p.ok("the second call is idempotent: same directory, no fetch")
    else:
        p.bad(
            "the second call exited %d and printed '%s' (expected 0 and '%s')"
            % (second.returncode, second_printed, printed)
        )

    # THE REFUSAL BRANCH, driven for real with a uname shim (:147-167).
    shim = pathlib.Path(tempfile.mkdtemp())
    try:
        (shim / "uname").write_text(UNAME_SHIM, encoding="utf-8")
        (shim / "uname").chmod(0o755)
        shutil.rmtree(fix / ".ci" / "cache", ignore_errors=True)
        refuse = _run(extra_path=str(shim), merge=True)
    finally:
        shutil.rmtree(shim, ignore_errors=True)
    if refuse.returncode != 0:
        p.ok(
            "an unpinned architecture is refused (exit %d), not downloaded unverified"
            % refuse.returncode
        )
    else:
        p.bad(
            "an unpinned architecture was NOT refused; the subject exited 0 and would "
            "install bytes no checksum covers"
        )
    p.expect_contains(
        refuse.stdout,
        "constants.sh",
        "the refusal names the pin site so the fix is in the message",
    )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
