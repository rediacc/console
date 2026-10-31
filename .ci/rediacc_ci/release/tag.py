#!/usr/bin/env python3
"""Create and push the release tag `v<VERSION>` on a given commit.

Lifted from the inline bash of the `Create version tag` step in `.github/workflows/cd-v2.yml`. The behaviour it keeps:

  * The remote is asked first, through `git ls-remote --exit-code`, never a local guess. rc 0 means the tag exists, rc 2 means it is absent, and any other rc is UNKNOWN and refused.
  * A tag that exists on the same commit is success (a retry only proves it). A tag on another commit is refused: one version never maps to two commits. `--retry` accepts an existing tag wherever it points, and refuses when the remote has no such tag.
  * Otherwise the tag is created (annotated by default, `--lightweight` for a plain one) on the commit and pushed.

THREE ENTRY POINTS. `ensure_tag` (the CLI default) creates and pushes in one call. A local release (`rediacc_ci.release.local`) needs the tag OBJECT id between the two, because the git-level pre-push hook admits its push only by the exact oid its release-run record lists, and an annotated tag's object id does not exist until the tag is made. So `create_tag` (`--create-only`) makes the local tag and prints that oid as its only stdout line, the entry adds it to the record, and `push_tag` (`--push-oid <oid>`) pushes `refs/tags/v<V>` only when it is still that oid.

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


def remote_tag(version: str, remote: str, cwd: str | None) -> tuple[str, str] | None:
    """(ref oid, commit) of the remote tag, or None when absent. Raises on an unknown result.

    The ref oid is the tag OBJECT for an annotated tag and the commit for a lightweight one: it is what a push of the tag sends, and what the release-run record must list.
    """
    ref = f"refs/tags/v{version}"
    res = _git(["ls-remote", "--exit-code", remote, ref, f"{ref}^{{}}"], cwd)
    if res.returncode == 2:
        return None
    if res.returncode != 0:
        raise TagError(
            f"git ls-remote {remote} failed (rc={res.returncode}), so whether v{version} exists is UNKNOWN. "
            f"Refusing to guess: {res.stderr.strip()}"
        )
    rows = [ln.split("\t") for ln in res.stdout.splitlines() if ln.strip()]
    rows = [r for r in rows if len(r) == 2]
    oid = next((r[0] for r in rows if r[1] == ref), "")
    if not oid:
        raise TagError(
            f"git ls-remote {remote} returned rc=0 with no {ref} line for v{version}: UNKNOWN, refusing"
        )
    # The peeled `^{}` line exists only for an annotated tag; without it the ref is the commit.
    peeled = next((r[0] for r in rows if r[1] == f"{ref}^{{}}"), oid)
    return oid, peeled


def remote_tag_commit(version: str, remote: str, cwd: str | None) -> str | None:
    """Commit the remote tag points at, or None when absent. Raises on an unknown result."""
    found = remote_tag(version, remote, cwd)
    return None if found is None else found[1]


def _commit(sha: str, cwd: str | None) -> str:
    if not sha:
        raise TagError("version and sha are both required")
    full = _git(["rev-parse", "--verify", f"{sha}^{{commit}}"], cwd)
    if full.returncode != 0:
        raise TagError(f"{sha} is not a commit in this repository: {full.stderr.strip()}")
    return full.stdout.strip()


def _local_tag(tag: str, cwd: str | None) -> tuple[str, str] | None:
    """(ref oid, commit) of the local tag, or None when there is none."""
    ref = _git(["rev-parse", "--verify", "-q", f"refs/tags/{tag}"], cwd)
    if ref.returncode != 0:
        return None
    peeled = _git(["rev-parse", "--verify", "-q", f"refs/tags/{tag}^{{commit}}"], cwd)
    return ref.stdout.strip(), peeled.stdout.strip()


def create_tag(
    version: str,
    sha: str,
    *,
    remote: str = DEFAULT_REMOTE,
    cwd: str | None = None,
    retry: bool = False,
    lightweight: bool = False,
    bot_name: str = "",
    bot_email: str = "",
) -> str:
    """Make the LOCAL tag `v<version>` on `sha`, push nothing, and return the oid a push sends (`refs/tags/v<version>`).

    When the remote already holds the tag on `sha` (or anywhere, under `retry`), nothing is created and the remote's ref oid comes back: pushing it again is a no-op `push_tag` reports. A tag on another commit, a retry with no remote tag, an unknown `ls-remote` and a local tag on another commit all raise TagError.
    """
    if not version:
        raise TagError("version and sha are both required")
    tag = f"v{version}"
    sha = _commit(sha, cwd)
    at = remote_tag(version, remote, cwd)
    if at is not None:
        if at[1] == sha or retry:
            return at[0]
        raise TagError(
            f"Tag {tag} already exists at {at[1]}, not at {sha}. Refusing to release one version from two commits."
        )
    if retry:
        raise TagError(
            f"Retry of {tag}, but {remote} has no such tag. Re-dispatch as a new release."
        )
    local = _local_tag(tag, cwd)
    if local is not None:
        if local[1] != sha:
            raise TagError(
                f"Local tag {tag} points at {local[1]}, not at {sha}. Resolve it by hand."
            )
        return local[0]
    cfg: list[str] = []
    if bot_name:
        cfg += ["-c", f"user.name={bot_name}"]
    if bot_email:
        cfg += ["-c", f"user.email={bot_email}"]
    args = ["tag", tag, sha] if lightweight else ["tag", "-a", tag, "-m", tag, sha]
    made = _git(args, cwd, cfg)
    if made.returncode != 0:
        raise TagError(f"git tag {tag} failed (rc={made.returncode}): {made.stderr.strip()}")
    local = _local_tag(tag, cwd)
    if local is None or local[1] != sha:
        raise TagError(f"git tag {tag} exited 0 but refs/tags/{tag} does not resolve to {sha}")
    return local[0]


def push_tag(
    version: str, oid: str, *, remote: str = DEFAULT_REMOTE, cwd: str | None = None
) -> str:
    """Push the local `refs/tags/v<version>`, which must be exactly `oid` (the value `create_tag` returned and the release-run record lists). Returns a one-line outcome, raises TagError.

    A remote that already holds `oid` is success with nothing pushed; a remote holding another object is refused, as is a local tag that is not `oid`: the record admits that one object id and no other.
    """
    if not version or not oid:
        raise TagError("version and oid are both required")
    tag = f"v{version}"
    at = remote_tag(version, remote, cwd)
    if at is not None:
        if at[0] == oid:
            return f"Tag {tag} already exists on {remote} as {oid}; nothing to push."
        raise TagError(
            f"Tag {tag} on {remote} is {at[0]}, not {oid}. Refusing to move a released tag."
        )
    local = _local_tag(tag, cwd)
    if local is None or local[0] != oid:
        raise TagError(
            f"Local refs/tags/{tag} is {local[0] if local else 'absent'}, not {oid}; the push would send another object."
        )
    pushed = _git(["push", remote, f"refs/tags/{tag}:refs/tags/{tag}"], cwd)
    if pushed.returncode != 0:
        raise TagError(
            f"git push {remote} {tag} failed (rc={pushed.returncode}): {pushed.stderr.strip()}"
        )
    return f"Created tag {tag} at {local[1]} ({oid})"


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
    """Make `v<version>` exist on `sha` at the remote: `create_tag`, then `push_tag`. Returns a one-line outcome, raises TagError."""
    if not version or not sha:
        raise TagError("version and sha are both required")
    tag = f"v{version}"
    full = _commit(sha, cwd)
    at = remote_tag(version, remote, cwd)
    if at is not None:
        if at[1] == full or retry:
            return f"Tag {tag} already exists at {at[1]} (retry={retry}); nothing to create."
        raise TagError(
            f"Tag {tag} already exists at {at[1]}, not at {full}. Refusing to release one version from two commits."
        )
    if retry:
        raise TagError(
            f"Retry of {tag}, but {remote} has no such tag. Re-dispatch as a new release."
        )
    # The local-tag check `create_tag` makes, run here first so `--dry-run` refuses exactly what a real run refuses.
    local = _local_tag(tag, cwd)
    if local is not None and local[1] != full:
        raise TagError(f"Local tag {tag} points at {local[1]}, not at {full}. Resolve it by hand.")
    if dry_run:
        return f"DRY RUN: would create {'lightweight ' if lightweight else ''}tag {tag} at {full} and push it to {remote}."
    oid = create_tag(
        version,
        full,
        remote=remote,
        cwd=cwd,
        lightweight=lightweight,
        bot_name=bot_name,
        bot_email=bot_email,
    )
    push_tag(version, oid, remote=remote, cwd=cwd)
    return f"Created tag {tag} at {full}"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--version", required=True, help="version without the leading v")
    ap.add_argument("--sha", default="", help="commit to tag (not with --push-oid)")
    ap.add_argument("--remote", default=DEFAULT_REMOTE)
    ap.add_argument(
        "--retry", action="store_true", help="accept an existing tag wherever it points"
    )
    ap.add_argument("--lightweight", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--bot-name", default="")
    ap.add_argument("--bot-email", default="")
    mode = ap.add_mutually_exclusive_group()
    mode.add_argument(
        "--create-only",
        action="store_true",
        help="create the local tag, push nothing, print the oid a push sends",
    )
    mode.add_argument(
        "--push-oid", default="", help="push the local tag, which must be exactly this oid"
    )
    ns = ap.parse_args(argv)
    if not ns.push_oid and not ns.sha:
        ap.error("--sha is required unless --push-oid is given")
    if ns.push_oid and (ns.sha or ns.retry or ns.lightweight or ns.dry_run):
        ap.error("--push-oid takes only --version and --remote")
    if ns.create_only and ns.dry_run:
        ap.error("--create-only writes a local tag; --dry-run writes nothing")
    try:
        if ns.push_oid:
            msg = push_tag(ns.version, ns.push_oid, remote=ns.remote)
        elif ns.create_only:
            msg = create_tag(
                ns.version,
                ns.sha,
                remote=ns.remote,
                retry=ns.retry,
                lightweight=ns.lightweight,
                bot_name=ns.bot_name,
                bot_email=ns.bot_email,
            )
        else:
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
