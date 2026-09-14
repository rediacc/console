#!/usr/bin/env python3
"""Port of `.ci/scripts/release/tag-submodules.sh`.

Tags each release-carrying submodule at the parent repo's release-pointer
commit, so "which renet is in v1.2.3" is answerable from renet's own history.
The twin's header carries the reasoning; what matters for the port is the
behaviour it singles out:

DRIFT IS A HARD FAILURE, NOT A SILENT RETAG. If `v<VERSION>` already exists in
the submodule and points somewhere OTHER than the checked-out HEAD, the release
would be claiming one version maps to two different commits. The twin refuses,
exit 1, and says a human must resolve it. When the tag already points AT HEAD it
is reused and the push is idempotent, so retries are safe. Those three arms --
absent, present-at-HEAD, present-elsewhere -- are the whole program, and
`test_release_tag_submodules.py` drives all three against a real local
submodule with a real bare remote rather than only the happy path.

THIS PUSHES TAGS TO SUBMODULE REMOTES. Both the twin and this port. Neither is
ever pointed at the real `private/renet` remote by any test in this repo: every
case builds a throwaway parent repo whose "submodule" pushes to a bare
repository in the same tmpdir. Read the twin's own NOTE before running either
by hand.

THE SINGLE-ELEMENT LOOP IS DELIBERATE AND PRESERVED, including the twin's
BLOCKER comment on it: `private/renet` is the only submodule whose commits ship
inside a release today, and keeping the loop shape means adding the next one is
a one-word edit. `SUBMODULES` below is that word. THE CWD DANCE IS PRESERVED
WITH IT: the twin `cd`s into the submodule and back to `$WORKSPACE` at the end
of each iteration, so the next iteration's relative path resolves from the
workspace and not from inside the previous submodule. This port really does
`os.chdir`, rather than passing `cwd=` per subprocess, because passing `cwd=`
would quietly make the second iteration work even if the chdir-back were
deleted -- and that is the bug the chdir-back exists to prevent.

FOUR THINGS ROUTED EXACTLY AS THE TWIN ROUTES THEM:

  * `git rev-parse HEAD`: stdout captured, stderr INHERITED. An unborn HEAD
    prints git's own fatal message and the script dies with git's exit code.
  * `git rev-list -n1 v<V>`: stdout captured, stderr to /dev/null, `|| true`.
    A missing tag is DATA (the tag does not exist yet), not a failure.
  * `git config`, `git tag -a`, `git push`: NEITHER stream redirected. `git
    push` writes its `To <remote>` / `* [new tag]` report to stderr, and a port
    that captured it would silently swallow the only evidence a release
    actually published anything.
  * Every `echo` is stdout; there are no `log_*` calls in this script at all,
    so nothing here goes to stderr except what git itself writes.

ONE DOCUMENTED DIVERGENCE, MESSAGE TEXT ONLY. The twin's
`VERSION="${VERSION:?tag-submodules.sh: VERSION must be set}"` produces bash's
own `<script>: line 36: VERSION: tag-submodules.sh: VERSION must be set` and
exit 1. That prefix carries a line number not worth reproducing (the same
ruling as the `${VAR:?msg}` twins in `rediacc_ci.deploy`), so this port prints
`tag-submodules.py: VERSION must be set` to stderr and exits 1. The exit code,
the stream and the substance match; the wrapper's prefix does not. `:?` fires
on set-but-EMPTY as well as unset, and so does this.

K=5 LEDGER: `.ci/shadow/w7p6-tag-submodules.observations.jsonl`.
"""

from __future__ import annotations

import os
import subprocess
import sys

from rediacc_ci import log
from rediacc_ci.core import common

SELF = "tag-submodules.py"

# BLOCKER: the single-element list is deliberate and moved verbatim out of
# cd-v2.yml -- private/renet is the only submodule whose commits ship inside a
# release today, and keeping the loop shape means adding the next one is a
# one-word edit rather than a restructure.
SUBMODULES = ("private/renet",)

BOT_NAME = "github-actions[bot]"
BOT_EMAIL = "github-actions[bot]@users.noreply.github.com"


def is_initialized(sub: str) -> bool:
    """`[[ ! -d "$sub/.git" ]] && [[ ! -f "$sub/.git" ]]`, inverted.

    BOTH SHAPES ARE ACCEPTED and that is not redundancy: a submodule checkout
    has `.git` as a FILE holding a gitdir pointer, while a plain clone has it
    as a directory. Testing only one of the two calls half the real cases
    uninitialized and skips the tag entirely, which would pass silently.
    """
    marker = os.path.join(sub, ".git")
    return os.path.isdir(marker) or os.path.isfile(marker)


def _say(line: str) -> None:
    """stdout, flushed. Flushed because the very next thing is usually a
    subprocess writing to the same fd directly; without it the workflow log
    shows git's output before the notice that explains it."""
    print(line)
    sys.stdout.flush()


def _git_capture(*args: str) -> subprocess.CompletedProcess[str]:
    """stdout captured, stderr INHERITED -- `$(git ...)` with no redirect."""
    sys.stdout.flush()
    return subprocess.run(["git", *args], stdout=subprocess.PIPE, text=True, check=False)


def _git_quiet(*args: str) -> subprocess.CompletedProcess[str]:
    """stdout captured, stderr DISCARDED -- `$(git ... 2>/dev/null || true)`."""
    sys.stdout.flush()
    return subprocess.run(
        ["git", *args], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True, check=False
    )


def _git_passthrough(*args: str) -> int:
    """Neither stream redirected. Returns the exit code."""
    sys.stdout.flush()
    return subprocess.run(["git", *args], check=False).returncode


def tag_one(sub: str, version: str) -> int:
    """One iteration of the twin's loop, cwd already inside `sub`.

    Returns 0 to continue, or the exit code the whole program must die with.
    """
    for key, value in (("user.name", BOT_NAME), ("user.email", BOT_EMAIL)):
        rc = _git_passthrough("config", key, value)
        if rc != 0:
            return rc

    head = _git_capture("rev-parse", "HEAD")
    if head.returncode != 0:
        # `set -e` on a failed command substitution: git has already printed
        # its own fatal message to the inherited stderr.
        return head.returncode
    head_sha = head.stdout.rstrip("\n")

    existing = _git_quiet("rev-list", "-n1", "v%s" % version)
    existing_sha = existing.stdout.rstrip("\n") if existing.returncode == 0 else ""

    if existing_sha:
        if existing_sha != head_sha:
            _say(
                "::error::Submodule %s tag v%s already points to %s but HEAD is %s. "
                "Drift must be resolved manually before this release can proceed."
                % (sub, version, existing_sha, head_sha)
            )
            return 1
        _say(
            "::notice::Submodule %s tag v%s already at HEAD (%s); reusing"
            % (sub, version, head_sha)
        )
    else:
        rc = _git_passthrough("tag", "-a", "v%s" % version, "-m", "v%s" % version)
        if rc != 0:
            return rc

    # Push is idempotent for existing tags pointing at the same SHA.
    return _git_passthrough("push", "origin", "v%s" % version)


def main(argv: list[str]) -> int:
    del argv
    try:
        common.require_cmd("git")
    except common.RefusalError as exc:
        log.error(str(exc))
        return 1

    version = os.environ.get("VERSION", "")
    if not version:
        # See the module docstring: reworded, not byte-identical.
        print("%s: VERSION must be set" % SELF, file=sys.stderr)
        return 1

    workspace = os.environ.get("GITHUB_WORKSPACE") or os.getcwd()

    for sub in SUBMODULES:
        if not is_initialized(sub):
            _say("::notice::Skipping %s (not initialized)" % sub)
            continue
        os.chdir(sub)
        rc = tag_one(sub, version)
        if rc != 0:
            return rc
        os.chdir(workspace)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
