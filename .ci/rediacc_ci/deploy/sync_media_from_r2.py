#!/usr/bin/env python3
"""Port of `.ci/scripts/deploy/sync-media-from-r2.sh`.

The DOWNLOAD direction of the media sync: three `aws s3 sync` calls that pull `tutorials/video/`, `videos/` and `tutorials/audio/` out of the R2 bucket `rediacc-www-media` into `packages/www/public/assets/`. Its upload counterpart is `sync-media-to-r2.sh`, ported beside this file as `rediacc_ci.deploy.sync_media_to_r2`. The two are twins in the campaign's sense and in the tree's:
same bucket, same three prefixes, same flag vocabulary, and the differences between them are exactly the differences between reading a bucket and writing one.

WHY A CHECKOUT NEEDS THIS AT ALL, carried over from the twin's header because it is the reason the audio prefix is here beside two video prefixes. Most `npm run dev` browsing does NOT need any of it: the URL builders read the manifest and point at media.rediacc.com, so the site fetches videos from the CDN exactly as production does. `tutorials/audio/` is different. It is a
build-time TTS cache read off LOCAL DISK by the tutorial-video pipeline, is not exposed on the public CDN at all, and is reachable only through this S3 API path, so restoring it is REQUIRED before re-running `./run.sh www tutorials generate|video` on a fresh checkout.

-----------------------------------------------------------------------------
NOTHING HERE REACHES R2 IN A TEST
-----------------------------------------------------------------------------
`aws` is the one external tool that carries a credential, so the differential (`.ci/rediacc_ci/tests/test_deploy_sync_media_from_r2.py`) puts a RECORDING FAKE `aws` on a scratch PATH that logs its exact argv and answers from the environment. `.ci/shadow/w7p5a-status.json` records this path as blocked only
for the "one real run" clause and says in as many words that the mocked parity
ledger is a SEPARATE, achievable piece of work. This is that piece.

THE CALL LOG IS THE PRIMARY EVIDENCE FOR THIS SCRIPT. Everything it prints is three `Restoring ...` lines plus at most one closing line, none of which is
derived from what actually moved; the entire observable effect is the argv of
the `aws s3 sync` calls, in order, with their filter flags. Two implementations can print identical output while syncing a different prefix, omitting `--dryrun`, or reordering the three legs.

-----------------------------------------------------------------------------
`mkdir` IS CALLED, NOT REIMPLEMENTED
-----------------------------------------------------------------------------
`mkdir -p` is an external binary here (bash has no `mkdir` builtin), so the twin genuinely execs `/usr/bin/mkdir` and, under `set -e`, hands its exit status and its stderr BYTES straight to the caller. Driven 2026-09-13 with a regular file sitting where `tutorials/video/` belongs: the run printed `mkdir: Already exists` and exited 1, before the step line. `os.makedirs` would print
a Python traceback for the same condition, with a different status. Calling the same binary is what keeps those bytes identical, and it is the same ruling `promote_r2_to_stable.py` makes for `find` and `sed`.

-----------------------------------------------------------------------------
THREE FACTS ABOUT THE TWIN THAT LOOK LIKE MISTAKES. ALL THREE ARE REPRODUCED
-----------------------------------------------------------------------------
  1. `require_var` VALIDATES ONLY ITS FIRST ARGUMENT, SO TWO OF THE THREE
     DOCUMENTED-AS-REQUIRED CREDENTIALS ARE NEVER CHECKED. The twin writes
     `require_var CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID
     CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY CLOUDFLARE_R2_MEDIA_ENDPOINT`, and
     `common.sh:131-137` reads `local var_name="$1"` and stops there. Driven
     2026-09-13: `require_var A B C` with only `A` set reaches the next line.
     What catches the other two is not the guard but `set -u`, three lines
     later, and only when they are UNSET.
     `REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT` names it.
  2. AN EMPTY SECRET OR AN EMPTY ENDPOINT IS NOT CAUGHT AT ALL, which is fact 1
     with the one escape `set -u` leaves open. `set -u` fires on UNSET, never on
     SET-BUT-EMPTY, and the twin's own guard would have caught empty (it is a
     `-z` test) if it had looked. Driven 2026-09-13 with
     `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY=` and
     `CLOUDFLARE_R2_MEDIA_ENDPOINT=`: the run passed `--endpoint-url` followed by
     the empty string to `aws`, printed `Restore complete.` and exited 0.
     `AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT` names it.
  3. `--dry-run` STILL CREATES THE LOCAL DIRECTORIES. `mkdir -p "$local_dir"`
     sits above the `aws` call in `restore_dir` and is not conditioned on
     `DRY_RUN`, so the flag that promises to "download nothing" leaves three new
     empty directories in the working copy. Driven 2026-09-13 in a fixture tree:
     `--dry-run` on an empty checkout created
     `packages/www/public/assets/{tutorials/video,videos,tutorials/audio}`.
     Harmless in a git sense (git does not track empty directories) and still a
     write from a flag documented as read-only.
     `DRY_RUN_STILL_CREATES_THE_LOCAL_DIRECTORIES` names it.

None is repaired here. This wave's acceptance rule is agreement with the live
twin; changing what a credential guard accepts is a cutover-box decision rather
than a port's.

-----------------------------------------------------------------------------
THE ONE DIVERGENCE: WHAT `set -u` PRINTS
-----------------------------------------------------------------------------
When `CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY` or `CLOUDFLARE_R2_MEDIA_ENDPOINT` is UNSET, bash's own refusal names the bash FILE and a bash LINE NUMBER:

    .ci/scripts/deploy/sync-media-from-r2.sh: line 90: \
CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY: unbound variable

This port prints the `NAME: unbound variable` half, on the same stream, with the same exit status 1. Identical ruling and identical wording to `deploy/promote_r2_to_stable.py`, `deploy/delete_r2_channel.py` and
`deploy/upload_repos_to_r2.py`, whose `${VAR:?msg}` guards have the same shape.
The differential asserts BOTH directions so nobody "fixes" either side into the other.

THE ORDER OF THE THREE REFUSALS IS PART OF THE CONTRACT and is reproduced exactly: `require_var` on the access key, then `require_cmd aws`, then the secret, then the endpoint. A machine with no `aws` and no credentials at all reports the MISSING BINARY, not the missing key.

K=5 LEDGER: `.ci/shadow/w7p6-sync-media-from-r2.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

# `BUCKET="rediacc-www-media"` (twin :48). Hard-coded there, hard-coded here.
BUCKET = "rediacc-www-media"

# The three legs, in the twin's order (twin :110-120), as (remote_prefix, local_path_relative_to_repo_root). ORDER IS OBSERVABLE: it is the order of the step lines and the order of the `aws` calls, and a reordered tuple is a different program even though the same bytes end up on disk. Every local path keeps its TRAILING SLASH because the twin's does, and `aws` is handed the string
# as written.
TUTORIALS = ("tutorials/video/", "packages/www/public/assets/tutorials/video/")
SOLUTIONS = ("videos/", "packages/www/public/assets/videos/")
AUDIO = ("tutorials/audio/", "packages/www/public/assets/tutorials/audio/")

# The environment names, as literals, for the messages and the registry.
ACCESS_KEY_ENV = "CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"
SIGNING_KEY_ENV = "CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"
ENDPOINT_ENV = "CLOUDFLARE_R2_MEDIA_ENDPOINT"

# `export AWS_DEFAULT_REGION="auto"` (twin :91). R2 has one region and it is
# spelled `auto`; a real region name makes the SigV4 signature wrong.
AWS_DEFAULT_REGION = "auto"

# The three facts in the module docstring, as constants so a test can assert each by name instead of restating the sentence.
REQUIRE_VAR_CHECKS_ONLY_ITS_FIRST_ARGUMENT = True
AN_EMPTY_CREDENTIAL_IS_NOT_CAUGHT = True
DRY_RUN_STILL_CREATES_THE_LOCAL_DIRECTORIES = True


class UnknownArgumentError(Exception):
    """The `*)` arm of the twin's parse loop (twin :78-81). Exit 1."""

    def __init__(self, argument: str) -> None:
        super().__init__("Unknown argument: %s" % argument)
        self.argument = argument
        self.code = 1


class UnboundVariableError(Exception):
    """`set -u` on a variable the twin's own guard never checked.

    See "THE ONE DIVERGENCE" in the module docstring: bash prefixes its message
    with the script name and a line number, this carries the `NAME: unbound
    variable` half, and both exit 1 on stderr.
    """

    def __init__(self, name: str) -> None:
        super().__init__("%s: unbound variable" % name)
        self.name = name
        self.code = 1


class BashExitError(Exception):
    """`set -e` ending the run on an unguarded external command.

    Both `mkdir -p` and `aws s3 sync` are unguarded in `restore_dir`, so the failing program's own stderr is the only explanation the caller gets and its status becomes the script's.
    """

    def __init__(self, code: int) -> None:
        super().__init__("set -e: exit %d" % code)
        self.code = code


class Options:
    """The four parse-loop variables (twin :50-53), as one object.

    Plain attributes rather than a dataclass: the differential compares these against literal booleans, and a dataclass would add a repr nobody reads and an equality nobody wants (two runs with the same flags are not the same run).
    """

    def __init__(
        self,
        *,
        tutorials: bool = True,
        solutions: bool = True,
        audio: bool = True,
        dry_run: bool = False,
    ) -> None:
        self.tutorials = tutorials
        self.solutions = solutions
        self.audio = audio
        self.dry_run = dry_run

    def selected(self) -> list[tuple[str, str]]:
        """The legs this run will restore, in the twin's order."""
        legs = []
        if self.tutorials:
            legs.append(TUTORIALS)
        if self.solutions:
            legs.append(SOLUTIONS)
        if self.audio:
            legs.append(AUDIO)
        return legs


def parse_args(argv: list[str]) -> Options:
    """The `while [[ $# -gt 0 ]]` loop (twin :55-83), verbatim in behaviour.

    EACH `--*-only` FLAG SETS ALL THREE BOOLEANS, so they are not additive and the LAST one wins: `--tutorials-only --audio-only` restores audio alone. A port that OR-ed them would sync two prefixes where the twin syncs one. `--dry-run` is orthogonal and may appear anywhere in the line.

    An EMPTY STRING argument reaches the `*)` arm and is refused as `Unknown argument: ` with a trailing space, exactly as the twin's `log_error "Unknown argument: $1"` renders it.
    """
    opts = Options()
    for argument in argv:
        if argument == "--tutorials-only":
            opts.tutorials, opts.solutions, opts.audio = True, False, False
        elif argument == "--solutions-only":
            opts.tutorials, opts.solutions, opts.audio = False, True, False
        elif argument == "--audio-only":
            opts.tutorials, opts.solutions, opts.audio = False, False, True
        elif argument == "--dry-run":
            opts.dry_run = True
        else:
            raise UnknownArgumentError(argument)
    return opts


def repo_root() -> str:
    """`REPO_ROOT` (twin :47), by location rather than by cwd.

    The twin resolves `.ci/scripts/deploy/../../..` from its own `BASH_SOURCE`;
    this file sits at `.ci/rediacc_ci/deploy/`, three directories under the same root, so the arithmetic is identical and neither side depends on the caller's cwd. `abspath`, NOT `realpath`: bash's `cd` is logical, so a checkout reached through a symlink keeps the symlinked spelling on both sides, and the paths in the step lines therefore match byte for byte.
    """
    here = os.path.dirname(os.path.abspath(__file__))
    return os.path.abspath(os.path.join(here, "..", "..", ".."))


def environment() -> dict[str, str | None]:
    """Every variable this module reads, ONE `os.environ.get` PER NAME.

    NOT `dict(os.environ)`, AND THE DIFFERENCE IS A GATE RATHER THAN A STYLE. `check:ci-python-env-registry` derives a module's declared inputs by walking
    its AST for literal `os.environ` subscripts, `.get` calls and `in` tests; a
    read that goes through a materialised copy or a local alias is INVISIBLE to it, and the module then reports zero inputs while depending on three.

    `None` MEANS UNSET AND `""` MEANS SET-BUT-EMPTY, and the distinction is the whole of fact 2 in the module docstring: `set -u` fires on the first and not on the second, so a helper that folded them together would refuse a run the twin performs.
    """
    return {
        ACCESS_KEY_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID"),
        SIGNING_KEY_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"),
        ENDPOINT_ENV: os.environ.get("CLOUDFLARE_R2_MEDIA_ENDPOINT"),
    }


def require_access_key(env: dict[str, str | None]) -> str:
    """`require_var CLOUDFLARE_R2_MEDIA_ACCESS_KEY_ID ...` (twin :85).

    THE ONLY ONE OF THE THREE THAT IS ACTUALLY GUARDED (fact 1). Unset and empty
    are one outcome here, because `common.sh`'s test is `[[ -z "${!v:-}" ]]`.
    """
    return common.require_var(ACCESS_KEY_ENV, {ACCESS_KEY_ENV: env.get(ACCESS_KEY_ENV) or ""})


def require_secret_key(env: dict[str, str | None]) -> str:
    """`export AWS_SECRET_ACCESS_KEY="$CLOUDFLARE_R2_MEDIA_SECRET_ACCESS_KEY"` (twin :90).

    Not a guard: an expansion that `set -u` happens to police. An empty value is accepted and exported, which is fact 2.
    """
    value = env.get(SIGNING_KEY_ENV)
    if value is None:
        raise UnboundVariableError(SIGNING_KEY_ENV)
    return value


def require_endpoint(env: dict[str, str | None]) -> str:
    """`SYNC_ARGS=(--endpoint-url "$CLOUDFLARE_R2_MEDIA_ENDPOINT" ...)` (twin :93).

    Same shape as the secret, three lines later, which is why an unset secret is reported before an unset endpoint even though both are missing.
    """
    value = env.get(ENDPOINT_ENV)
    if value is None:
        raise UnboundVariableError(ENDPOINT_ENV)
    return value


def sync_args(endpoint: str, *, dry_run: bool) -> list[str]:
    """`SYNC_ARGS` (twin :93-97). ORDER IS OBSERVABLE, so it is pinned.

    `--dryrun` is APPENDED, so it trails `--no-progress` rather than leading the
    list. `aws` does not care; the recorded argv does, and the argv is the
    evidence this port is judged on.
    """
    args = ["--endpoint-url", endpoint, "--no-progress"]
    if dry_run:
        args.append("--dryrun")
    return args


def download_argv(remote_prefix: str, local_dir: str, args: list[str]) -> list[str]:
    """`aws s3 sync "s3://$BUCKET/$remote_prefix" "$local_dir" "${SYNC_ARGS[@]}"` (twin :107)."""
    return ["aws", "s3", "sync", "s3://%s/%s" % (BUCKET, remote_prefix), local_dir, *args]


def _run(argv: list[str], env: dict[str, str]) -> None:
    """One unguarded external command under `set -e`.

    stdout and stderr are INHERITED, not captured: the twin does not capture them either, and `aws --no-progress` still writes a `download: ...` line per object that a caller reads as the record of what moved.
    """
    proc = subprocess.run(argv, env=env, check=False)
    if proc.returncode != 0:
        raise BashExitError(proc.returncode)


def restore_dir(remote_prefix: str, local_dir: str, args: list[str], env: dict[str, str]) -> None:
    """`restore_dir` (twin :100-106).

    `mkdir -p` FIRST AND UNCONDITIONALLY (fact 3), then the step line, then the sync. The order matters to the output: a `mkdir` that fails produces its own stderr and NO step line at all, so a reader sees the failure without ever learning which prefix was being restored.
    """
    _run(["mkdir", "-p", local_dir], env)
    log.step("Restoring s3://%s/%s -> %s" % (BUCKET, remote_prefix, local_dir))
    _run(download_argv(remote_prefix, local_dir, args), env)


def child_env(access_key: str, secret_key: str) -> dict[str, str]:
    """The three `export`s (twin :89-91), as the environment the children get.

    `export` in the twin mutates the whole process; passing an explicit `env=`
    to each child reproduces the only part of that which is observable, and leaves this process's own environment alone so an importing caller does not inherit a credential it never asked for.
    """
    env = dict(os.environ)
    env["AWS_ACCESS_KEY_ID"] = access_key
    env["AWS_SECRET_ACCESS_KEY"] = secret_key
    env["AWS_DEFAULT_REGION"] = AWS_DEFAULT_REGION
    return env


def main(argv: list[str]) -> int:
    try:
        opts = parse_args(argv)
    except UnknownArgumentError as exc:
        log.error(str(exc))
        return exc.code

    env = environment()
    try:
        access_key = require_access_key(env)
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        common.require_cmd("aws")
    except common.RefusalError as exc:
        exc.report()
        return exc.code

    try:
        secret_key = require_secret_key(env)
        endpoint = require_endpoint(env)
    except UnboundVariableError as exc:
        print(str(exc), file=sys.stderr)
        return exc.code

    child = child_env(access_key, secret_key)
    args = sync_args(endpoint, dry_run=opts.dry_run)
    if opts.dry_run:
        log.info("Dry run: nothing will be downloaded.")

    try:
        for remote_prefix, local_relative in opts.selected():
            restore_dir(remote_prefix, os.path.join(repo_root(), local_relative), args, child)
    except BashExitError as exc:
        return exc.code

    if not opts.dry_run:
        log.info("Restore complete.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
