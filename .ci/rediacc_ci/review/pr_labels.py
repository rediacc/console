"""PR labels from the per-commit review records (agent/plans/PLAN-per-commit-review.md section 8; operator ruling 2026-10-02).

WHY THIS MOVED. Labeling lived inside the PR-level Claude review job (`claude_review_gate.run_apply_labels`), and half its input was that job's model verdict. The operator retired the PR-level review on 2026-10-02 (the Claude GitHub app is uninstalled), so the verdict now comes from the per-commit reviewer: every review record under `agent/reviews/<branch>/` carries its labels (a `<sha40>.md` file's `Labels:` line, or the `labels` key of a line in `clean.jsonl`, the ledger a clean full-coverage verdict is written to; `clean_ledger` reads it, and for one sha the `.md` wins), and
this module aggregates them for the PR. It runs ONCE PER GREEN HEAD, from Console CI's `pr-labels` job, which needs `ci-complete` and runs only when CI Complete succeeded (operator ruling 2026-10-02: the bump is decided at the end of the PR, not on every push, so a red head never carries a release decision).

TWO INPUTS, IN THIS ORDER OF TRUST, the same as before:

  1. A MECHANICAL FLOOR from the PR's changed paths alone: all-docs earns `documentation`, all-CI earns `ci`. No model can talk it out of a fact about the file list.
  2. The per-commit verdicts. Bump is the highest verdict over the reviewed commits: `major` applies `bump-major`, `minor` applies `bump-minor`, `patch` applies no bump label (a patch is the release default), and `bump-none` only when EVERY reviewed commit said `none`, so a docs/CI/agent-only PR lands without a release (operator rulings 2026-10-02: `bump-major` and `bump-none` are both applied automatically; the old applier only ever recommended a major). Kind is the union.

RECONCILED AGAINST THE LEDGER, NEVER A BLIND SYNC. The ledger comment (`<!-- claude-labels: <sha> -->` / `applied: a,b`) records what this applier put on the PR last time; only those labels are ever removed, so a hand-applied label is never touched, and a tampered ledger line is re-filtered through the managed whitelist before it can delete anything. The prefix is the one the old applier wrote, so the first run after the move reconciles the old
applier's labels instead of stranding them.

ADVISORY END TO END. Every failure logs and returns 0: a label is never worth failing CI over, and a fork PR's read-only token must not red the job. The verdicts are complete at a green head: block_push_with_unrecorded_reviews refuses a push until every commit's review file is committed, and a review-only commit is not reviewed again. The release reads the labels on the main-branch CI run that the merge starts (dispatch_release.py in finalize-release-sentinel), which runs long after this job finishes, so an auto-merge landing the moment CI Complete turns green does not race it.

    PYTHONPATH=.ci python3 -m rediacc_ci.review.pr_labels      env: GH_TOKEN PR_NUMBER HEAD_REF HEAD_SHA GITHUB_REPOSITORY
    PYTHONPATH=.ci python3 -m rediacc_ci.review.pr_labels --verdicts-only --branch <b>   prints {labels, note, n} as JSON from the local tree, no gh
"""

from __future__ import annotations

import json
import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci import log, paths
from rediacc_ci.review import clean_ledger

LEDGER_PREFIX = "<!-- claude-labels:"
# THE HARD WHITELIST. Adding a label the repo does not carry CREATES it, so an unfiltered name would appear on the repo and fail check:ci-label-inventory.
MANAGED_LABELS = (
    "bug",
    "enhancement",
    "documentation",
    "ci",
    "bump-major",
    "bump-minor",
    "bump-none",
)
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
    """Every labelled verdict of the branch, in sha order: the `.md` records, and each `clean.jsonl` line whose sha has no `.md` (the stricter record wins). Sha order is the order the `.md` files alone sorted in, so moving a record into the ledger never reorders the kind labels."""
    d = pathlib.Path(root) / REVIEWS_REL / branch_slug(branch)
    keyed: list[tuple[str, dict]] = []
    md_shas = set()
    for path in sorted(d.glob("*.md")) if d.is_dir() else []:
        md_shas.add(path.stem)
        try:
            got = read_verdict(path.read_text(encoding="utf-8"))
        except OSError:
            continue
        if got is not None:
            keyed.append((path.stem, got))
    for doc in clean_ledger.read(d / clean_ledger.NAME):
        if doc["sha"] in md_shas:
            continue
        got = clean_ledger.verdict_of(doc)
        if got is not None:
            keyed.append((doc["sha"], got))
    return [v for _k, v in sorted(keyed, key=lambda kv: kv[0])]


def verdicts_only(root: pathlib.Path, branch: str) -> str:
    """`{labels, note, n}` as one JSON line: the labels the reviews alone earn (no changed-file floor), for an offline comparison of two trees."""
    found = verdicts(root, branch)
    labels, note = desired_labels([], found)
    return json.dumps({"labels": labels, "note": note, "n": len(found)}, sort_keys=True)


def mechanical(changed: list[str]) -> list[str]:
    """The all-files floor: a fact about the file list, not a model's opinion."""
    out = []
    if changed and all(DOCS_ONLY_RE.search(p) for p in changed):
        out.append("documentation")
    if changed and all(CI_ONLY_RE.search(p) for p in changed):
        out.append("ci")
    return out


BUMP_LABEL = {"none": "bump-none", "patch": "", "minor": "bump-minor", "major": "bump-major"}


def aggregate(found: list[dict]) -> tuple[list[str], str]:
    """(labels, note) from the per-commit verdicts. At most one bump label: the highest verdict wins. `note` names the commit that earned a major, because a major release is the one decision a reader should be able to trace to its reason."""
    labels: list[str] = []
    if not found:
        return labels, ""
    top = max((v["bump"] for v in found), key=BUMP_RANK.__getitem__)
    if BUMP_LABEL[top]:
        labels.append(BUMP_LABEL[top])
    note = ""
    if top == "major":
        why = next(v.get("why") for v in found if v["bump"] == "major")
        note = "bump-major applied: a per-commit review judged a major bump (%s)" % (
            why or "no reason given"
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


def _opt(argv: list[str], name: str) -> str:
    if name in argv:
        i = argv.index(name)
        if i + 1 < len(argv):
            return argv[i + 1]
    return ""


def main(argv: list[str] | None = None) -> int:
    argv = list(argv or [])
    if "--verdicts-only" in argv:
        branch = _opt(argv, "--branch")
        if not branch:
            sys.stderr.write("--verdicts-only needs --branch <branch>\n")
            return 2
        print(verdicts_only(paths.repo_root(), branch))
        return 0
    try:
        return apply(dict(os.environ), paths.repo_root())
    except Exception as exc:  # noqa: BLE001 -- advisory: a label never fails CI
        log.warn("pr_labels failed (%s: %s); nothing more applied" % (type(exc).__name__, exc))
        return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
