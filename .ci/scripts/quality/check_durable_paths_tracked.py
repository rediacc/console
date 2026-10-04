#!/usr/bin/env python3
"""check:ci-durable-paths-tracked -- no .gitignore rule may swallow a directory this repo keeps as durable record.

WHY THIS EXISTS, and it cost a commit on 2026-10-03. PLAN-program-state-in-repo moved program state into agent/programs/<slug>/state/, and the copy of clarity-round6's state committed its MANIFEST and screenshots but silently left out all 13 reports: `.gitignore` carries a bare `reports/` (aimed at test output), and git ignores a matching directory at any depth without a word. Nothing in the tree could see it -- `git status` simply never listed the files. The fix was a negation, `!agent/programs/*/state/reports/`, and this gate keeps that negation, and every other durable path, from being undone by the next broad ignore rule someone adds.

WHAT IT CHECKS. For each durable location below it asks git itself -- `git check-ignore --no-index`, the exact rule set `git add` uses, tracked or not -- whether a probe file there would be ignored, and fails naming the path and the rule that matched. `--no-index` matters: without it an already-tracked file reads as not ignored even under a matching rule, which is precisely how a new file in the same directory slips away while the old ones look fine.

CONTROL FIRST. Before reading the real tree it builds a scratch repository with a `.gitignore` of `reports/` and asserts the probe reports a planted path as IGNORED, then adds the negation and asserts it does NOT. If either control fails, the probe cannot see what it exists to see, and the gate exits 2 rather than reporting a pass.

Exit 1 on an ignored durable path, 2 on a failed control.

---- gate ----
kind: step
step: Durable paths are not gitignored
lane: quality-static
why: No .gitignore rule may swallow a directory this repo keeps as durable record.
---- end gate ----
"""

from __future__ import annotations

import os
import subprocess
import sys
import tempfile

REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))

# One probe file per durable location. A directory ignored at any depth by a bare pattern (the `reports/` case) is caught by a probe INSIDE it, so each entry names a file, not a directory.
DURABLE_PROBES = (
    ("agent/programs/<slug>/state/reports/", "agent/programs/zz-probe/state/reports/probe.md"),
    (
        "agent/programs/<slug>/state/checkpoints/",
        "agent/programs/zz-probe/state/checkpoints/probe.png",
    ),
    ("agent/programs/<slug>/state/MANIFEST.md", "agent/programs/zz-probe/state/MANIFEST.md"),
    (
        "agent/reviews/<branch>/",
        "agent/reviews/zz-probe/0000000000000000000000000000000000000000.md",
    ),
    ("agent/reviews/<branch>/clean.jsonl", "agent/reviews/zz-probe/clean.jsonl"),
    ("agent/worklist/", "agent/worklist/zz-probe.jsonl"),
    ("agent/plans/", "agent/plans/PLAN-zz-probe.md"),
    ("agent/ledgers/", "agent/ledgers/zz-probe.jsonl"),
    ("agent/pr/", "agent/pr/zz-probe.md"),
)


def ignored_by(root, rel):
    """The `.gitignore` rule that ignores `rel`, or "" when nothing does. Raises when git cannot answer."""
    r = subprocess.run(
        ["git", "-C", str(root), "check-ignore", "--no-index", "-v", "--", rel],
        capture_output=True,
        text=True,
        check=False,
    )
    if r.returncode == 0:
        return r.stdout.strip() or "(ignored)"
    if r.returncode == 1:
        return ""
    raise RuntimeError("git check-ignore exited %d: %s" % (r.returncode, r.stderr.strip()))


def controls():
    """[failed control names]. A scratch repository proves the probe sees a bare `reports/` rule and its negation."""
    failed = []
    with tempfile.TemporaryDirectory() as tmp:
        subprocess.run(["git", "init", "-q", tmp], check=True)
        probe = "agent/programs/x/state/reports/probe.md"
        with open(os.path.join(tmp, ".gitignore"), "w", encoding="utf-8") as handle:
            handle.write("reports/\n")
        if not ignored_by(tmp, probe):
            failed.append("CONTROL: a bare `reports/` rule must make the probe read as IGNORED")
        with open(os.path.join(tmp, ".gitignore"), "a", encoding="utf-8") as handle:
            handle.write("!agent/programs/*/state/reports/\n")
        if ignored_by(tmp, probe):
            failed.append("CONTROL: the negation must make the same probe read as tracked")
    return failed


def main():
    failed = controls()
    if failed:
        for name in failed:
            print("x %s" % name, file=sys.stderr)
        print(
            "x durable paths: the probe cannot see what it exists to see; refusing to report a pass",
            file=sys.stderr,
        )
        return 2
    print("durable paths: controls first, then the verdict")
    print("  2 controls fired (a bare reports/ rule is seen, its negation is honoured)")
    bad = []
    for label, rel in DURABLE_PROBES:
        rule = ignored_by(REPO_ROOT, rel)
        if rule:
            bad.append("%s is gitignored by %s" % (label, rule))
    if bad:
        print(
            "x %d durable location(s) would be silently left out of git:" % len(bad),
            file=sys.stderr,
        )
        for line in bad:
            print("    " + line, file=sys.stderr)
        print(
            "  Add a negation (`!<path>/`) after the rule that matched, the way .gitignore keeps agent/programs/*/state/reports/.",
            file=sys.stderr,
        )
        return 1
    print("v durable paths: %d location(s) checked, none gitignored" % len(DURABLE_PROBES))
    return 0


if __name__ == "__main__":
    sys.exit(main())
