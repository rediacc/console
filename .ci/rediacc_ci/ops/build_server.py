"""Port of `scripts/ops/build-server.sh` (118 lines).

Builds the consolidated rediacc server image locally for testing. It stages a build context under the console root (renet binaries, the marketing site, the account portal SPA, a CLI npm tarball) and then runs `docker buildx build --target onprem`, tagging the result `rediacc-server-onprem:dev`. The tag is local-only: it carries no `ghcr.io/` prefix and so cannot be confused
with, or pushed to, the production registry path.

WHO CALLS IT: nobody. It is an operator entry point, invoked by hand, and the only references to it in the tree are the two comments at `Dockerfile:12,32` that describe how the context gets staged. Those two comments were also the only thing keeping the bash twin out of `check-dead-bash`'s findings (`scripts/data/domains.json:131`), and they now name this module instead.

    PYTHONPATH=.ci python3 -m rediacc_ci.ops.build_server onprem

PREREQUISITES ARE THE TWIN'S, unchanged: npm dependencies installed, both cross-compiled renet binaries present under `private/renet/bin/`, and either `ACCOUNT_ED25519_PUBLIC_KEY` in the environment or an `ACCOUNT_ED25519_PUBLIC_KEY=` line in `private/account/.env`.

PORT NOTES, each driven before it was written down.

THE FIVE SHELL-OUTS THAT STAY SHELL-OUTS, and why each one is not a stdlib call. `cp -r packages/www/dist/. www-assets/` MERGES a directory's contents into an existing destination, and neither `shutil.copytree` (which wants to create the destination, or needs `dirs_exist_ok` plus a different symlink policy) nor `shutil.copy2` reproduces the trailing-`/.` form. `sort -V` is a
version sort whose tie-breaking on `rediacc-cli-0.8.10.tgz` against `rediacc-cli-0.8.9.tgz` a `str.sort` gets backwards. `npm`, `npx` and `docker` were always subprocesses. Reimplementing any of the three in Python would put a second implementation of the staging contract in the tree, which is the thing the differential exists to prevent.

`mkdir -p` AND `rm -rf` DO NOT STAY SHELL-OUTS, because `Path.mkdir(parents=True, exist_ok=True)` and `shutil.rmtree(ignore_errors=True)` are the same operations with the same failure behaviour, and spawning a process to make a directory would add two entries to the differential's call log that say nothing about the staging.

`$0` IS REPRODUCED, NOT FORGED. The usage line is `usage: $0 <onprem>`, and a bash child and a Python child never agree on that token: one prints the path it was invoked by, the other the module file. The port prints `sys.argv[0]`, the differential masks the token on both sides, and a control asserts both sides printed a well-formed usage line so the mask cannot hide its absence.

`set -e` IS REPRODUCED AS AN EXIT STATUS, NOT AS AN EXCEPTION. Every command the twin runs is unguarded, so the first failure ends the script with THAT command's status: npm's 1, docker's 125, cp's 1. `_run` returns the status and every call site returns it upward unchanged. A port that flattened them to 1 would be right-looking and wrong on the case an operator actually hits,
which is a docker daemon that is not running.

THE `sed` THAT READS THE ACCOUNT KEY PRINTS EVERY MATCHING LINE, not the first. `sed -n 's/^ACCOUNT_ED25519_PUBLIC_KEY=//p' | tr -d '\\r'` over a file carrying the name twice yields two lines joined by a newline, and the command substitution then strips the trailing newlines. A `.env` with a duplicate key is malformed, but the twin has a defined answer for it and so does this.

THE VARIANT SWITCH READS `$1` ALONE. Extra arguments are ignored rather than rejected, which is the twin's behaviour and not an oversight worth repairing in a port.

Exit: 0 on a completed build; 2 on a missing or unknown variant; 1 when a renet binary is absent or `npm pack` produced no tarball; otherwise the failing command's own status.
"""

from __future__ import annotations

import os
import pathlib
import shutil
import subprocess
import sys

# `scripts/ops/build-server.sh` derived the console root from `BASH_SOURCE[0]`; this derives it from `__file__` at the same relative depth, so a copy of this file in a throwaway tree resolves against that tree.
ROOT_DIR = pathlib.Path(__file__).resolve().parent.parent.parent.parent

ACCOUNT_ENV = "private/account/.env"
ACCOUNT_KEY_PREFIX = "ACCOUNT_ED25519_PUBLIC_KEY="
RENET_ARCHES = ("amd64", "arm64")
RENET_BIN_DIR = "private/renet/bin"
CLI_TARBALL_GLOB = "rediacc-cli-*.tgz"
CLI_TARBALL_LATEST = "rediacc-cli-latest.tgz"

VARIANTS = {"onprem": ("on-premise", "rediacc-server-onprem:dev")}


def _run(
    argv: list[str],
    *,
    cwd: str | None = None,
    quiet: bool = False,
) -> int:
    """One subprocess, its status returned rather than raised.

    `cwd` is a path RELATIVE to the console root, spelled the way the twin spells it inside `(cd <dir> && ...)`, because a failing `cd` is a defined outcome: bash prints `cd: <dir>: No such file or directory` naming the directory as written, the subshell exits 1, and `set -e` ends the script there. Reproduced with the same sentence and the same status.

    `quiet` is the twin's `>/dev/null` on `npm pack`: stdout is discarded, stderr is not.
    """
    where = ROOT_DIR if cwd is None else ROOT_DIR / cwd
    if not where.is_dir():
        print("cd: %s: No such file or directory" % cwd, file=sys.stderr, flush=True)
        return 1
    try:
        proc = subprocess.run(
            argv,
            cwd=str(where),
            stdout=subprocess.DEVNULL if quiet else None,
            check=False,
        )
    except FileNotFoundError:
        # bash prints `<script>: line N: <name>: command not found` and exits 127. The port prints the sentence without the location, because a hard-coded line number in a port goes stale the first time the twin gains a comment.
        print("%s: command not found" % argv[0], file=sys.stderr, flush=True)
        return 127
    return proc.returncode


def account_key() -> str:
    """`ACCOUNT_ED25519_PUBLIC_KEY`, from the environment or from `private/account/.env`."""
    from_env = os.environ.get("ACCOUNT_ED25519_PUBLIC_KEY", "")
    if from_env:
        return from_env
    env_file = ROOT_DIR / ACCOUNT_ENV
    if not env_file.is_file():
        return ""
    matched = [
        line[len(ACCOUNT_KEY_PREFIX) :]
        for line in env_file.read_text(encoding="utf-8", errors="surrogateescape").split("\n")
        if line.startswith(ACCOUNT_KEY_PREFIX)
    ]
    return "\n".join(matched).replace("\r", "").rstrip("\n")


def missing_renet(arch: str) -> int:
    """The twin's five stderr lines for an absent cross-compiled binary.

    The `$(git branch --show-current)` inside them is ESCAPED in the twin and therefore literal: the operator is meant to read the command, not to have it run.
    """
    print("error: missing %s/renet-linux-%s" % (RENET_BIN_DIR, arch), file=sys.stderr)
    print(file=sys.stderr)
    print("Run ./rdc.sh once to trigger the cross-compile, or download from a", file=sys.stderr)
    print("recent CI run:", file=sys.stderr)
    print(
        "  gh run list --workflow ci.yml --branch $(git branch --show-current) --limit 5",
        file=sys.stderr,
    )
    print("  gh run download <run-id> --name renet-binaries-<sha>", file=sys.stderr, flush=True)
    return 1


def stage_assets(source_dir: str, staged_dir: str, build_label: str, build_argv: list[str]) -> int:
    """Build `source_dir` if it is absent, then merge it into a fresh `staged_dir`."""
    if not (ROOT_DIR / source_dir).is_dir():
        print("==> Building %s..." % build_label, flush=True)
        rc = _run(build_argv, cwd=build_label)
        if rc != 0:
            return rc
    shutil.rmtree(ROOT_DIR / staged_dir, ignore_errors=True)
    (ROOT_DIR / staged_dir).mkdir(parents=True, exist_ok=True)
    return _run(["cp", "-r", "%s/." % source_dir, "%s/" % staged_dir])


def pack_cli() -> int:
    """`npm pack` into `cli-npm/`, then copy the highest version to a stable name."""
    print("==> Packing CLI tarball...", flush=True)
    cli_npm = ROOT_DIR / "cli-npm"
    shutil.rmtree(cli_npm, ignore_errors=True)
    cli_npm.mkdir(parents=True, exist_ok=True)
    rc = _run(
        ["npm", "pack", "--pack-destination", str(cli_npm)],
        cwd="packages/cli",
        quiet=True,
    )
    if rc != 0:
        return rc
    # The twin's `shopt -s nullglob` plus `sort -V | tail -n 1`: npm pack always produces exactly one tarball matching the glob, and the version sort is what decides when a stale one is lying beside it.
    names = sorted(p.name for p in cli_npm.glob(CLI_TARBALL_GLOB))
    if not names:
        print("error: npm pack produced no %s" % CLI_TARBALL_GLOB, file=sys.stderr, flush=True)
        return 1
    sort = subprocess.run(
        ["sort", "-V"],
        input="".join("%s\n" % name for name in names),
        capture_output=True,
        text=True,
        check=False,
    )
    newest = sort.stdout.splitlines()[-1]
    return _run(["cp", newest, CLI_TARBALL_LATEST], cwd="cli-npm")


def main(argv: list[str]) -> int:
    variant = argv[0] if argv else ""
    if not variant:
        print("usage: %s <onprem>" % sys.argv[0], file=sys.stderr, flush=True)
        return 2
    if variant not in VARIANTS:
        print("unknown variant: %s (expected onprem)" % variant, file=sys.stderr, flush=True)
        return 2
    account_entry, local_tag = VARIANTS[variant]

    key = account_key()

    for arch in RENET_ARCHES:
        if not (ROOT_DIR / RENET_BIN_DIR / ("renet-linux-%s" % arch)).is_file():
            return missing_renet(arch)

    print("==> Staging build context...", flush=True)

    (ROOT_DIR / "binaries").mkdir(parents=True, exist_ok=True)
    for arch in RENET_ARCHES:
        rc = _run(
            [
                "cp",
                "%s/renet-linux-%s" % (RENET_BIN_DIR, arch),
                "binaries/renet-linux-%s" % arch,
            ]
        )
        if rc != 0:
            return rc

    rc = stage_assets("packages/www/dist", "www-assets", "packages/www", ["npm", "run", "build"])
    if rc != 0:
        return rc
    rc = stage_assets(
        "private/account/web/dist",
        "account-web-assets",
        "private/account/web",
        ["npx", "vite", "build", "--outDir", "dist"],
    )
    if rc != 0:
        return rc

    rc = pack_cli()
    if rc != 0:
        return rc

    print("==> Building %s (--target %s)..." % (local_tag, variant), flush=True)
    rc = _run(
        [
            "docker",
            "buildx",
            "build",
            "--file",
            "Dockerfile",
            "--target",
            variant,
            "--build-arg",
            "ACCOUNT_ENTRY=%s" % account_entry,
            "--build-arg",
            "ACCOUNT_ED25519_PUBLIC_KEY=%s" % key,
            "--build-arg",
            "VITE_APP_VERSION=dev",
            "--tag",
            local_tag,
            "--load",
            ".",
        ]
    )
    if rc != 0:
        return rc

    print(flush=True)
    print("Built: %s" % local_tag, flush=True)
    print(flush=True)
    print("Run with:", flush=True)
    print("  docker run --rm -p 8080:80 %s" % local_tag, flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
