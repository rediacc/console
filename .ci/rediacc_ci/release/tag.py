#!/usr/bin/env python3
"""Create and push the release tag `v<VERSION>` on a given commit.

Lifted from the inline bash of the `Create version tag` step in `.github/workflows/cd-v2.yml`. The behaviour it keeps:

  * The remote is asked first, through `git ls-remote --exit-code`, never a local guess. rc 0 means the tag exists, rc 2 means it is absent, and any other rc is UNKNOWN and refused.
  * A tag that exists on the same commit is success (a retry only proves it). A tag on another commit is refused: one version never maps to two commits. `--retry` accepts an existing tag wherever it points, and refuses when the remote has no such tag.
  * Otherwise the tag is created (annotated by default, `--lightweight` for a plain one) on the commit and pushed.

`--dry-run` runs every check and prints what it would create, writing nothing.
"""

from __future__ import annotations

import argparse
import subprocess
import sys

DEFAULT_REMOTE = "origin"


class TagError(Exception):
    """The tag cannot be created or confirmed; the message says why."""


def _git(
    args: list[str], cwd: str | None, env_cfg: list[str] | None = None
) -> subprocess.CompletedProcess[str]:
    cmd = ["git", *(env_cfg or []), *args]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, check=False)


def remote_tag_commit(version: str, remote: str, cwd: str | None) -> str | None:
    """Commit the remote tag points at, or None when absent. Raises on an unknown result."""
    ref = f"refs/tags/v{version}"
    res = _git(["ls-remote", "--exit-code", remote, ref, f"{ref}^{{}}"], cwd)
    if res.returncode == 2:
        return None
    if res.returncode != 0:
        raise TagError(
            f"git ls-remote {remote} failed (rc={res.returncode}), so whether v{version} exists is UNKNOWN. "
            f"Refusing to guess: {res.stderr.strip()}"
        )
    lines = [ln for ln in res.stdout.splitlines() if ln.strip()]
    if not lines:
        raise TagError(
            f"git ls-remote {remote} returned rc=0 with no refs for v{version}: UNKNOWN, refusing"
        )
    # The peeled `^{}` line comes last for an annotated tag, so the last line is the commit.
    return lines[-1].split("\t")[0]


def ensure_tag(
    version: str,
    sha: str,
    *,
    remote: str = DEFAULT_REMOTE,
    cwd: str | None = None,
    retry: bool = False,
    lightweight: bool = False,
    dry_run: bool = False,
    bot_name: str = "",
    bot_email: str = "",
) -> str:
    """Make `v<version>` exist on `sha` at the remote. Returns a one-line outcome, raises TagError."""
    if not version or not sha:
        raise TagError("version and sha are both required")
    tag = f"v{version}"
    full = _git(["rev-parse", "--verify", f"{sha}^{{commit}}"], cwd)
    if full.returncode != 0:
        raise TagError(f"{sha} is not a commit in this repository: {full.stderr.strip()}")
    sha = full.stdout.strip()

    at = remote_tag_commit(version, remote, cwd)
    if at is not None:
        if at == sha or retry:
            return f"Tag {tag} already exists at {at} (retry={retry}); nothing to create."
        raise TagError(
            f"Tag {tag} already exists at {at}, not at {sha}. Refusing to release one version from two commits."
        )
    if retry:
        raise TagError(
            f"Retry of {tag}, but {remote} has no such tag. Re-dispatch as a new release."
        )

    if dry_run:
        return f"DRY RUN: would create {'lightweight ' if lightweight else ''}tag {tag} at {sha} and push it to {remote}."

    local = _git(["rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"], cwd)
    if local.returncode == 0:
        if local.stdout.strip() != sha:
            raise TagError(
                f"Local tag {tag} points at {local.stdout.strip()}, not at {sha}. Resolve it by hand."
            )
    else:
        cfg: list[str] = []
        if bot_name:
            cfg += ["-c", f"user.name={bot_name}"]
        if bot_email:
            cfg += ["-c", f"user.email={bot_email}"]
        args = ["tag", tag, sha] if lightweight else ["tag", "-a", tag, "-m", tag, sha]
        made = _git(args, cwd, cfg)
        if made.returncode != 0:
            raise TagError(f"git tag {tag} failed (rc={made.returncode}): {made.stderr.strip()}")
    pushed = _git(["push", remote, tag], cwd)
    if pushed.returncode != 0:
        raise TagError(
            f"git push {remote} {tag} failed (rc={pushed.returncode}): {pushed.stderr.strip()}"
        )
    return f"Created tag {tag} at {sha}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="version without the leading v")
    ap.add_argument("--sha", required=True, help="commit to tag")
    ap.add_argument("--remote", default=DEFAULT_REMOTE)
    ap.add_argument(
        "--retry", action="store_true", help="accept an existing tag wherever it points"
    )
    ap.add_argument("--lightweight", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bot-name", default="")
    ap.add_argument("--bot-email", default="")
    ns = ap.parse_args(argv)
    try:
        msg = ensure_tag(
            ns.version,
            ns.sha,
            remote=ns.remote,
            retry=ns.retry,
            lightweight=ns.lightweight,
            dry_run=ns.dry_run,
            bot_name=ns.bot_name,
            bot_email=ns.bot_email,
        )
    except TagError as exc:
        print(f"rediacc_ci.release.tag: {exc}", file=sys.stderr)
        return 1
    print(msg)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
