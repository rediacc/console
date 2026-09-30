"""Whether the green nightly that triggered `promote-stable.yml` actually tested the edge release it would promote.

Operator ruling 2026-09-30: a green scheduled `Console CI` run also releases edge to stable, alongside the 7-day soak. The nightly vouches only for the commit it ran on (`github.event.workflow_run.head_sha`), so the soak is waived only when the edge version's own tagged commit is that commit or one of its ancestors: `git merge-base --is-ancestor <edge commit> <head_sha>`.
An edge built from anything the nightly did not contain (a later push, a hotfix branch) is not vouched for.

"COULD NOT TELL" IS NEVER A YES. A tag that does not resolve, a malformed SHA, a SHA the checkout does not hold, or any git error returns `False` with the reason, and the caller falls back to the ordinary soak rule. The waiver exists only where the ancestry was positively proven. The checkout must hold full history and tags (`fetch-depth: 0`) for the proof to be possible at all.
"""

from __future__ import annotations

import re
import subprocess
from collections.abc import Callable, Sequence

SHA_RE = re.compile(r"^[0-9a-f]{40}$")
VERSION_RE = re.compile(r"^v?[0-9]+\.[0-9]+\.[0-9]+([-+][0-9A-Za-z.-]+)?$")

Runner = Callable[[Sequence[str]], "subprocess.CompletedProcess[str]"]


def _git(args: Sequence[str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(["git", *args], capture_output=True, text=True, check=False)


def edge_tested_by_nightly(version: str, head_sha: str, run: Runner = _git) -> tuple[bool, str]:
    """Return (proven, reason). `proven` is True only when the edge tag's commit is `head_sha` or an ancestor of it."""
    version = version.strip()
    head_sha = head_sha.strip().lower()
    if not VERSION_RE.match(version):
        return False, f"edge version {version!r} is not a release version"
    if not SHA_RE.match(head_sha):
        return False, f"nightly head_sha {head_sha!r} is not a full commit SHA"
    tag = version if version.startswith("v") else f"v{version}"

    resolved = run(["rev-parse", "--verify", "--quiet", f"refs/tags/{tag}^{{commit}}"])
    edge_commit = resolved.stdout.strip()
    if resolved.returncode != 0 or not SHA_RE.match(edge_commit):
        return False, f"tag {tag} does not resolve to a commit in this checkout"

    present = run(["cat-file", "-e", f"{head_sha}^{{commit}}"])
    if present.returncode != 0:
        return False, f"nightly head {head_sha} is not in this checkout"

    ancestry = run(["merge-base", "--is-ancestor", edge_commit, head_sha])
    if ancestry.returncode == 0:
        return (
            True,
            f"edge {tag} ({edge_commit[:12]}) is contained in the green nightly head {head_sha[:12]}",
        )
    if ancestry.returncode == 1:
        return (
            False,
            f"edge {tag} ({edge_commit[:12]}) is NOT contained in the green nightly head {head_sha[:12]}",
        )
    return False, f"git merge-base failed (exit {ancestry.returncode}): {ancestry.stderr.strip()}"
