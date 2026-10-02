"""PR labels from the per-commit review records (agent/plans/PLAN-per-commit-review.md section 8; operator ruling 2026-10-02).

WHY THIS MOVED. Labeling lived inside the PR-level Claude review job (`claude_review_gate.run_apply_labels`), and half its input was that job's model verdict. The operator retired the PR-level review on 2026-10-02 (the Claude GitHub app is uninstalled), so the verdict now comes from the per-commit reviewer: every review file under `agent/reviews/<branch>/` carries one `Labels:` line, and this
module aggregates them for the PR. It runs from Console CI's `label-guide` job, on every PR push.

TWO INPUTS, IN THIS ORDER OF TRUST, the same as before:

  1. A MECHANICAL FLOOR from the PR's changed paths alone: all-docs earns `documentation`, all-CI earns `ci`. No model can talk it out of a fact about the file list.
  2. The per-commit verdicts. Bump is the highest of `patch` and `minor` over the reviewed commits; `bump-none` only when EVERY reviewed commit said `none`, which keeps its "removed on release-worthy pushes" meaning; `major` is logged as a recommendation and never applied (operator ruling: a wrong major is a statement to every consumer of the version stream). Kind is the union.

RECONCILED AGAINST THE LEDGER, NEVER A BLIND SYNC. The ledger comment (`<!-- claude-labels: <sha> -->` / `applied: a,b`) records what this applier put on the PR last time; only those labels are ever removed, so a hand-applied label is never touched, and a tampered ledger line is re-filtered through the managed whitelist before it can delete anything. The prefix is the one the old applier wrote, so the first run after the move reconciles the old
applier's labels instead of stranding them.

ADVISORY END TO END. Every failure logs and returns 0: a label is never worth failing CI over, and a fork PR's read-only token must not red the job. Labels trail the newest commit's review by one push, because a review file lands after its commit; the merge path requires reviews to be committed, so the last push before merge carries the final labels.

    PYTHONPATH=.ci python3 -m rediacc_ci.review.pr_labels      env: GH_TOKEN PR_NUMBER HEAD_REF HEAD_SHA GITHUB_REPOSITORY
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths

LEDGER_PREFIX = "<!-- claude-labels:"
# THE HARD WHITELIST. Adding a label the repo does not carry CREATES it, so an unfiltered name would appear on the repo and fail check:ci-label-inventory. `bump-major` is deliberately absent.
MANAGED_LABELS = ("bug", "enhancement", "documentation", "ci", "bump-minor", "bump-none")
# "<name>|<color>|<description>", created on demand immediately before first use; each row equals its `.github/labels.yml` declaration.
CREATE_ON_DEMAND_LABELS = (
    "ci|FEF2C0|Build system, CI workflows, or .ci tooling (applied by the automated review)",
    (
        "bump-none|C5DEF5|No user-facing change: merging skips the release "
        "(review-applied; removed on release-worthy pushes)"
    ),
)
APPLIED_RE = re.compile(r"^applied:[ \t\n\r\f\v]*")
DOCS_ONLY_RE = re.compile(
    r"(^docs/|^agent/|^packages/www/src/content/docs/|^CLAUDE\.md$|^LICENSE$|\.md$)"
)
CI_ONLY_RE = re.compile(r"(^\.github/|^\.ci/|^scripts/ci-runner/)")
KIND_LABEL = {"bug": "bug", "feature": "enhancement", "docs": "documentation", "ci": "ci"}
REVIEWS_REL = "agent/reviews"
BRANCH_SLUG = re.compile(r"[^A-Za-z0-9._-]+")
LABELS_LINE = re.compile(r"^Labels: bump=(none|patch|minor|major) kind=([a-z,]+) why=(.*)$")
VERDICT_LINE = re.compile(r"^Verdict: (.*)$")
BUMP_RANK = {"none": 0, "patch": 1, "minor": 2, "major": 3}


def branch_slug(branch: str) -> str:
    """The directory name the reviewer files a branch under (`wl_review.branch_slug`)."""
    return BRANCH_SLUG.sub("-", (branch or "").strip()).strip("-.")


def read_verdict(text: str) -> dict | None:
    """The `Labels:` verdict of one review file, or None for a skipped, failed or unlabelled review."""
    verdict = labels = None
    for line in text.split("\n")[:24]:
        m = VERDICT_LINE.match(line)
        if m:
            verdict = m.group(1)
        m = LABELS_LINE.match(line)
        if m:
            kinds = [] if m.group(2) == "none" else m.group(2).split(",")
            labels = {"bump": m.group(1), "kind": kinds, "why": m.group(3)}
    if verdict not in ("findings", "clean"):
        return None
    return labels


def verdicts(root: pathlib.Path, branch: str) -> list[dict]:
    d = pathlib.Path(root) / REVIEWS_REL / branch_slug(branch)
    out = []
    for path in sorted(d.glob("*.md")) if d.is_dir() else []:
        try:
            got = read_verdict(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if got is not None:
            out.append(got)
    return out


def mechanical(changed: list[str]) -> list[str]:
    """The all-files floor: a fact about the file list, not a model's opinion."""
    out = []
    if changed and all(DOCS_ONLY_RE.search(p) for p in changed):
        out.append("documentation")
    if changed and all(CI_ONLY_RE.search(p) for p in changed):
        out.append("ci")
    return out


def aggregate(found: list[dict]) -> tuple[list[str], str]:
    """(labels, major_note) from the per-commit verdicts. `major_note` is non-empty when a commit recommended a major bump, which is never applied."""
    labels: list[str] = []
    if not found:
        return labels, ""
    bumps = [v["bump"] for v in found]
    top = max(BUMP_RANK[b] for b in bumps)
    if all(b == "none" for b in bumps):
        labels.append("bump-none")
    elif top >= BUMP_RANK["minor"]:
        labels.append("bump-minor")
    note = ""
    majors = [v for v in found if v["bump"] == "major"]
    if majors:
        note = (
            "a per-commit review RECOMMENDS a major bump (%s); bump-major is never applied automatically, apply it by hand if you agree"
            % (majors[0].get("why") or "no reason given")
        )
    for v in found:
        for kind in v.get("kind") or []:
            label = KIND_LABEL.get(kind)
            if label and label not in labels:
                labels.append(label)
    return labels, note


def desired_labels(changed: list[str], found: list[dict]) -> tuple[list[str], str]:
    out: list[str] = []
    review_labels, note = aggregate(found)
    for label in mechanical(changed) + review_labels:
        if label in MANAGED_LABELS and label not in out:
            out.append(label)
    return out, note


def stale_labels(prev_applied: str, desired: list[str]) -> list[str]:
    """Labels this applier put on the PR last time and no longer wants; never one outside the whitelist."""
    out = []
    for chunk in prev_applied.replace(",", "\n").split("\n"):
        name = chunk.strip()
        if name and name not in desired and name in MANAGED_LABELS and name not in out:
            out.append(name)
    return out


def _gh(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(
            ["gh", *args],
            capture_output=True,
            text=True,
            stdin=subprocess.DEVNULL,
            check=False,
            timeout=60,
        )
    except (OSError, subprocess.SubprocessError):
        return 127, ""
    return proc.returncode, (proc.stdout or "").rstrip("\n")


def apply(env: dict[str, str], root: pathlib.Path, gh=_gh) -> int:
    """Compute and apply the labels. Always 0."""
    pr = env.get("PR_NUMBER", "")
    head_ref = env.get("HEAD_REF", "")
    head_sha = env.get("HEAD_SHA", "")
    repo = env.get("GITHUB_REPOSITORY", "")
    if not (pr and head_ref and repo):
        log.warn(
            "pr_labels: PR_NUMBER, HEAD_REF and GITHUB_REPOSITORY are required; nothing applied"
        )
        return 0
    rc, changed_text = gh(
        ["api", "repos/%s/pulls/%s/files" % (repo, pr), "--paginate", "--jq", ".[].filename"]
    )
    changed = [p for p in changed_text.split("\n") if p] if rc == 0 else []
    if not changed:
        log.warn(
            "could not read the changed-file list for PR %s; skipping the mechanical labels" % pr
        )
    found = verdicts(root, head_ref)
    log.info("per-commit review verdicts for %s: %d" % (head_ref, len(found)))
    desired, note = desired_labels(changed, found)
    if note:
        log.warn(note)
    rc, ledgers = gh(
        [
            "api",
            "repos/%s/issues/%s/comments" % (repo, pr),
            "--paginate",
            "--jq",
            '.[] | select(.body | startswith("%s")) | "\\(.id) \\(.body)"' % LEDGER_PREFIX,
        ]
    )
    prev, ledger_id = "", ""
    if rc == 0:
        for line in ledgers.split("\n"):
            if line.startswith(tuple("0123456789")):
                ledger_id = line.split(" ", 1)[0]
            if APPLIED_RE.match(line):
                prev = APPLIED_RE.sub("", line)
    for stale in stale_labels(prev, desired):
        if gh(["api", "-X", "DELETE", "repos/%s/issues/%s/labels/%s" % (repo, pr, stale)])[0] == 0:
            log.info("removed stale label '%s'" % stale)
        else:
            log.warn("could not remove the stale label '%s'" % stale)
    for label in desired:
        row = next((r for r in CREATE_ON_DEMAND_LABELS if r.split("|", 1)[0] == label), "")
        if row and gh(["api", "repos/%s/labels/%s" % (repo, label)])[0] != 0:
            _name, color, desc = row.split("|", 2)
            if (
                gh(
                    [
                        "api",
                        "-X",
                        "POST",
                        "repos/%s/labels" % repo,
                        "-f",
                        "name=%s" % label,
                        "-f",
                        "color=%s" % color,
                        "-f",
                        "description=%s" % desc,
                    ]
                )[0]
                != 0
            ):
                log.warn("could not create the '%s' label" % label)
        if (
            gh(
                [
                    "api",
                    "-X",
                    "POST",
                    "repos/%s/issues/%s/labels" % (repo, pr),
                    "-f",
                    "labels[]=%s" % label,
                ]
            )[0]
            != 0
        ):
            log.warn("could not apply the label '%s'" % label)
    applied = ",".join(desired)
    body = "%s %s -->\napplied: %s" % (LEDGER_PREFIX, head_sha, applied)
    if ledger_id:
        rc = gh(
            [
                "api",
                "-X",
                "PATCH",
                "repos/%s/issues/comments/%s" % (repo, ledger_id),
                "-f",
                "body=%s" % body,
            ]
        )[0]
    else:
        rc = gh(
            [
                "api",
                "-X",
                "POST",
                "repos/%s/issues/%s/comments" % (repo, pr),
                "-f",
                "body=%s" % body,
            ]
        )[0]
    if rc != 0:
        log.warn("could not write the label ledger comment")
    log.info("labels for %s: %s" % ((head_sha or "?")[:7], applied or "<none>"))
    return 0


def main(argv: list[str] | None = None) -> int:
    del argv
    try:
        return apply(dict(os.environ), paths.repo_root())
    except Exception as exc:  # noqa: BLE001 -- advisory: a label never fails CI
        log.warn("pr_labels failed (%s: %s); nothing more applied" % (type(exc).__name__, exc))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
