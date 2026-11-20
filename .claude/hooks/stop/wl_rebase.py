"""Whether a lease has fallen behind its base (PLAN-two-track-merge-dev RB1).

A lease is cut at the live branch's tip. While the PR that branch carries is open, the base is that branch; once it merges, the base is origin/main. The question is asked of the remote, never of a local ref: the reader fetches the base branch into its remote-tracking ref first, because a stale local ref reads every lease as current (the RB1 mutant).

Verdicts, per lease tree:
  skipped   the lease holds no commit of its own; nothing to rebase.
  clean     the base tip is an ancestor of the lease head.
  absorbed  the base holds commits the lease lacks, and every one is patch-equivalent to a lease commit (`git cherry` marks it `-`): a rebase-merged parent, whose copies on main carry new shas.
  behind    at least one base commit has no patch-equivalent in the lease (`git cherry` marks it `+`).
  note      the base could not be read (a failed fetch, a missing ref): the reader allows, with one NOTE line, because a network blip must not block a stop.
"""

from __future__ import annotations

import dataclasses
import subprocess

GIT_TIMEOUT_S = 60
REMOTE = "origin"


@dataclasses.dataclass(frozen=True)
class Verdict:
    state: str
    behind: int = 0
    absorbed: int = 0
    tip: str = ""
    note: str = ""


def _git(cwd, *args) -> tuple[int, str, str]:
    try:
        r = subprocess.run(
            ["git", "-C", str(cwd), *args],
            capture_output=True,
            text=True,
            timeout=GIT_TIMEOUT_S,
            check=False,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return 1, "", str(exc)
    return r.returncode, r.stdout.strip(), r.stderr.strip()


def _fetch(tree, remote: str, branch: str, ref: str) -> tuple[int, str]:
    rc, _out, err = _git(
        tree, "fetch", "--quiet", "--no-tags", remote, "+refs/heads/%s:%s" % (branch, ref)
    )
    return rc, err


def base_branch(pr_open: bool, live_branch: str) -> str:
    """The branch a lease is judged against: the live branch while its PR is open, main after the merge."""
    return live_branch if pr_open else "main"


def behind_base(tree, head: str, cut_at: str, branch: str, remote: str = REMOTE) -> Verdict:
    """The verdict for one lease tree whose head is `head`, cut at `cut_at`, judged against `remote`/`branch`."""
    rc, own, err = _git(tree, "rev-list", "--count", "%s..%s" % (cut_at, head))
    if rc != 0:
        return Verdict(
            "note",
            note="NOTE: the lease's own commits could not be counted (%s)"
            % (err[-160:] or "git failed"),
        )
    if int(own or 0) == 0:
        return Verdict("skipped")
    ref = "refs/remotes/%s/%s" % (remote, branch)
    rc, err = _fetch(tree, remote, branch, ref)
    if rc != 0:
        return Verdict(
            "note",
            note="NOTE: fetching %s/%s failed, so behind-base was not judged: %s"
            % (remote, branch, err[-200:] or "no stderr"),
        )
    rc, tip, _err = _git(tree, "rev-parse", "--verify", "--quiet", ref + "^{commit}")
    if rc != 0 or not tip:
        return Verdict("note", note="NOTE: %s does not resolve after the fetch" % ref)
    if _git(tree, "merge-base", "--is-ancestor", tip, head)[0] == 0:
        return Verdict("clean", tip=tip)
    rc, out, err = _git(tree, "cherry", head, tip)
    if rc != 0:
        return Verdict(
            "note", tip=tip, note="NOTE: git cherry failed: %s" % (err[-160:] or "no stderr")
        )
    lines = out.splitlines()
    plus = sum(1 for line in lines if line.startswith("+"))
    minus = sum(1 for line in lines if line.startswith("-"))
    if plus == 0:
        return Verdict("absorbed", absorbed=minus, tip=tip)
    return Verdict("behind", behind=plus, absorbed=minus, tip=tip)


def lease_verdicts(
    world: dict, owner: str, branch: str, remote: str = REMOTE
) -> dict[str, dict[str, Verdict]]:
    """{lease id: {repo: Verdict}} for every lease in `world` (wl_worktrees.read_world) whose record names `owner` (a session prefix). Submodules are judged against the same branch name, the way their PR branches are named."""
    out: dict[str, dict[str, Verdict]] = {}
    for lease_id, repos in sorted(world.get("leases", {}).items()):
        record = world.get("records", {}).get(lease_id) or {}
        if not str(record.get("owner") or "").startswith(owner):
            continue
        cut = record.get("base") or {}
        for repo, tree in sorted(repos.items()):
            cut_at = cut.get(repo, "")
            if not cut_at or not tree.get("head"):
                continue
            out.setdefault(lease_id, {})[repo] = behind_base(
                tree["path"], tree["head"], cut_at, branch, remote
            )
    return out


def _subjects(repo, rng: str) -> list[tuple[str, str]]:
    rc, out, _err = _git(repo, "log", "--reverse", "--format=%H%x09%s", rng)
    if rc != 0:
        return []
    rows: list[tuple[str, str]] = []
    for line in out.splitlines():
        sha, sep, subject = line.partition("\t")
        if sep:
            rows.append((sha, subject))
    return rows


def rebase_proof(repo, base: str, old_tip: str, new_tip: str, uncovered: set[str]) -> dict | None:
    """What a rebase of base..old_tip into new_tip did, and what it left owed (PLAN-two-track-merge-dev RB4).

    carried / absorbed / missing come from `git cherry` exactly as wl_git.equivalent reads them. A missing commit whose subject matches a new commit that has no patch-equivalent of its own is CHANGED: the rebase resolved a conflict in it, so its patch-id moved and the successor map cannot carry its review record or its investigation rows. UNREVIEWED names every commit of base..new_tip in `uncovered` (wl_review.uncovered), the commits with no review record after the rebase. None when git cannot answer.
    """

    def marks(upstream, head):
        rc, out, _err = _git(repo, "cherry", upstream, head)
        if rc != 0:
            return None
        return {p[1]: p[0] for p in (ln.split() for ln in out.splitlines()) if len(p) == 2}

    accounted = marks(new_tip, old_tip)
    split = marks(base, old_tip)
    new_side = marks(old_tip, new_tip)
    if accounted is None or split is None or new_side is None:
        return None
    old = _subjects(repo, "%s..%s" % (base, old_tip))
    new = _subjects(repo, "%s..%s" % (base, new_tip))
    # `git cherry <new_tip> <old_tip>` lists only old commits NOT reachable from the new tip; one it does not list (an unchanged sha) is accounted, exactly as wl_git.equivalent reads it. Only `+` is lost.
    lost = [(s, subj) for s, subj in old if accounted.get(s) == "+" and split.get(s) == "+"]
    lost_shas = {s for s, _ in lost}
    carried = [s for s, _ in old if split.get(s) == "+" and s not in lost_shas]
    absorbed = [s for s, _ in old if split.get(s) == "-"]
    fresh = {subj: s for s, subj in new if new_side.get(s) == "+"}
    changed = [(s, fresh[subj], subj) for s, subj in lost if subj in fresh]
    missing = [s for s, subj in lost if subj not in fresh]
    unreviewed = [s for s, _ in new if s in uncovered]
    return {
        "carried": carried,
        "absorbed": absorbed,
        "changed": changed,
        "missing": missing,
        "unreviewed": unreviewed,
    }
