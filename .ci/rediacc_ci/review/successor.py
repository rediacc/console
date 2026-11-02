"""A sha a rebase rewrote, mapped to the commit that replaced it on this branch.

ONE COPY FOR EVERY LEDGER THAT RECORDS A HEAD. Every repository here merges by rebase, so a ledger row's recorded `head` stops resolving in CI's fresh clone once the branch is rebased or scrubbed. Two gates judge such rows: `check_plan_implementation` (investigation rows, P-A3/P-A4) and `check_plan_live_proof` (live receipts, LP5, through `proof.live_tier.validate_row`), plus `ops.live_proof verify`. They all map through these functions, lifted here from check_plan_implementation so no gate carries a second copy.
"""

from __future__ import annotations

import importlib
import os
import re

from rediacc_ci.review import clean_ledger

REVIEW_HEADERS = ("Commit", "Parent", "Patch-Id")


def review_records(root):
    """[{commit, parent, patch}] from the header block of every per-commit review record under agent/reviews/, every branch directory included: a record written on another branch name still maps its sha. Headers only, the same first-lines read `wl_review.review_index` makes, plus every line of each directory's `clean.jsonl` ledger (read through `clean_ledger`)."""
    out: list[dict[str, str]] = []
    top = os.path.join(root, "agent", "reviews")
    if not os.path.isdir(top):
        return out
    sha40 = re.compile(r"^[0-9a-f]{40}$")
    for branch in sorted(os.listdir(top)):
        d = os.path.join(top, branch)
        if not os.path.isdir(d):
            continue
        for name in sorted(os.listdir(d)):
            if not name.endswith(".md") or not sha40.match(name[:-3]):
                continue
            got = {}
            try:
                with open(os.path.join(d, name), encoding="utf-8") as fh:
                    for _ in range(12):
                        key, sep, val = fh.readline().partition(": ")
                        if sep and key in REVIEW_HEADERS:
                            got[key] = val.strip()
            except OSError:
                continue
            if sha40.match(got.get("Patch-Id", "")):
                out.append(
                    {
                        "commit": got.get("Commit") or name[:-3],
                        "parent": got.get("Parent", ""),
                        "patch": got["Patch-Id"],
                    }
                )
        # A clean full-coverage verdict is a line of the branch's ledger, not a file (agent/plans/PLAN-clean-review-ledger.md).
        out.extend(
            {
                "commit": doc["sha"],
                "parent": str(doc.get("parent") or ""),
                "patch": doc["patch_id"],
            }
            for doc in clean_ledger.read(os.path.join(d, clean_ledger.NAME))
            if sha40.match(str(doc.get("patch_id") or ""))
        )
    return out


def make_successor_of(records, branch_pids, reachable_fn, parent_fn):
    """successor_of(sha) for a branch that was REBASED after its rows were written.

    WHY. Every repository here merges by rebase, so the `head` an investigation row recorded and the `commit:<sha>` pointers it cites are rewritten the moment the branch is rebased onto a moved `main`: the old shas stay reachable from nothing on the branch locally and do not exist at all in CI's clone. The ledger is append-only, so the rows cannot be re-pointed. The per-commit
    review records (`agent/reviews/<branch>/<sha40>.md`, written by `wl_review.py` at commit time and committed on the branch) are the surviving map: each one names its `Commit:`, its `Parent:` and its `Patch-Id:`, and the rebased commit carrying the same `git patch-id --stable` in `<base>..HEAD` is its successor -- the match `wl_review.uncovered` already makes.

    `records` is [{commit, parent, patch}], `branch_pids` {patch_id: sha} over `<base>..HEAD`, `reachable_fn(sha)` answers the FULL sha when `merge-base --is-ancestor <sha> HEAD` holds and "" otherwise, and `parent_fn(sha)` the full sha of `<sha>^`. The answer is the sha's own full spelling when it was never rewritten (reachable from HEAD), its successor when a record maps it, and None when it was rewritten and nothing maps it. A
    recorded head that is itself a commit with no record (a `chore(reviews)` commit is never reviewed) is mapped through a CHILD's record: a record whose `Parent:` is that head, whose successor's parent is then the head's successor.
    """

    def by_prefix(field, sha):
        if len(sha) < 7:
            return None
        hits = [r for r in records if str(r.get(field) or "").startswith(sha)]
        return hits[0] if len({r.get(field) for r in hits}) == 1 else None

    def successor_of(sha):
        sha = str(sha or "").strip().lower()
        if not sha:
            return None
        here = reachable_fn(sha)
        if here:
            return here
        own = by_prefix("commit", sha)
        if own is not None and branch_pids.get(own.get("patch")):
            return branch_pids[own["patch"]]
        child = by_prefix("parent", sha)
        if child is not None and branch_pids.get(child.get("patch")):
            return parent_fn(branch_pids[child["patch"]]) or None
        return None

    return successor_of


def lazy_successor_of(root, base, planrec):
    """The real `successor_of` for tick_findings, built on first use: a run whose heads were never rewritten pays no `git patch-id` at all.

    THE PATCH-ID IS `wl_review.patch_ids` (the batched `wl_review.patch_id`), imported rather than restated, because the records' `Patch-Id:` lines were written by that function and a second spelling of the computation (a different diff command, a different flag) would map nothing and read as a rewritten head with no record.
    """
    built = {}

    def build():
        # A hook module (`.claude/hooks/stop`), imported on first use: the caller puts that directory on sys.path.
        wl_review = importlib.import_module("wl_review")

        pids: dict[str, str] = {}
        if base:
            # One batched pass (`wl_review.patch_ids`), newest first as rev-list orders it, so the first sha seen for a patch-id is kept exactly as the per-commit loop kept it.
            listing = planrec._git_out(root, "rev-list", "--no-merges", "%s..HEAD" % base)
            by_sha = wl_review.patch_ids(root, "%s..HEAD" % base)
            for sha in listing.split():
                # A failed batch (None) falls back to one call per commit, so a git error costs time, never the map.
                pid = by_sha.get(sha) if by_sha is not None else wl_review.patch_id(root, sha)
                if pid:
                    pids.setdefault(pid, sha)
        return make_successor_of(
            review_records(root),
            pids,
            lambda c: (
                planrec._git_out(root, "rev-parse", "--verify", "--quiet", c + "^{commit}")
                if planrec._git_ok(root, "merge-base", "--is-ancestor", c, "HEAD")
                else ""
            ),
            lambda c: planrec._git_out(root, "rev-parse", "--verify", "--quiet", c + "^"),
        )

    def successor_of(sha):
        if "fn" not in built:
            built["fn"] = build()
        return built["fn"](sha)

    return successor_of
