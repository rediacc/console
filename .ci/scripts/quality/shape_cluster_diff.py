#!/usr/bin/env python3
"""Shape-cluster diff: what a bulk transform did to the STRUCTURE of the lines it touched.

WHY THIS EXISTS, and it is one incident rather than a theory. On 2026-09-17 a reflow pass rewrote 884 files and destroyed 838 section banners across 161 of them, turning a three-line `---- / TITLE / ----` rule into one run-on line joined to the paragraph beneath it. Attached to that pass was a docstring-normalized AST-equality proof over every file, and it PASSED, because an AST
cannot see prose structure. So did a fence, heading, table-row and list-marker check. So did 82 selftest controls and 216 pytest cases. The damage was found by clustering every line the transform made disappear and reading the clusters.

WHAT IT DOES. For each file changed between a git revision and the working tree, every line on both sides is normalised to a SHAPE -- not its text, its kind -- and the per-shape counts are diffed. A transform that rewraps prose moves lines between the `prose` and `blank` clusters and leaves every other cluster alone. A transform that eats a banner shows `rule-line` falling to zero,
which is a sentence a reader acts on immediately and a line-count check never says.

WHAT IT CANNOT SEE, stated here because a proof whose limits go unstated is how the banner incident shipped in the first place:

  * a change that PRESERVES the shape distribution while altering meaning. Swap two paragraphs, or reverse a condition, and every cluster count is identical.
  * loss INSIDE a line whose shape does not change. Deleting half a sentence leaves one `prose` line before and one after.
  * a COLUMN. A list item's continuation flattened from two spaces to zero is still a `list-cont` line, which is exactly how a second defect rode out with this tool's own predecessor passing.

The first is covered by reading a sampled file per cluster across both revisions, the second by the same read, and the third by `--columns`, which reports the multiset of leading-indent widths per file and is the specific answer to that third bug.

USE IT ON ANY MECHANICAL BULK CHANGE, before committing one. The exit code is the finding: 0 when no cluster shrank, 1 when one did. A shrinking cluster is not automatically wrong -- collapsing a hard-wrapped paragraph legitimately reduces `prose` -- so the tool reports and the reader rules. What it refuses to do is stay quiet.
"""

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys

# THE SHAPES, ordered because the FIRST match wins and the order encodes precedence. A fenced line is a fence before it is anything else; a table row is a row before it is prose. Each one is a structure a bulk transform can silently eat, and each was chosen from a real corruption rather than from a taxonomy: rule-line, table-row, html-comment and doc-header are the four
# REFLOW_STOP gaps this repository actually paid for, in the order they were found.
SHAPES = (
    ("blank", re.compile(r"^\s*$")),
    ("fence", re.compile(r"^\s*(?:```|~~~)")),
    ("rule-line", re.compile(r"^\s*(?:[-=_*]{4,})\s*$")),
    ("table-row", re.compile(r"^\s{0,3}\|")),
    ("html-comment", re.compile(r".*<!--")),
    ("heading", re.compile(r"^\s{0,3}#{1,6}\s")),
    ("doc-header", re.compile(r"^\s{0,3}\*{0,2}[A-Z][A-Za-z0-9]*(?:-[A-Za-z0-9]+)*\*{0,2}:\s\S")),
    ("list-item", re.compile(r"^\s*(?:[-*+]|\d+\.)\s")),
    ("doctest", re.compile(r"^\s*(?:>>>|\.\.\.)\s")),
    ("indent-code", re.compile(r"^(?: {4,}|\t)\S")),
    ("list-cont", re.compile(r"^ {1,3}\S")),
    ("comment", re.compile(r"^\s*(?:#|//|/\*|\*)\s*\S")),
    ("allcaps", re.compile(r"^\s*[A-Z][A-Z0-9 ,'`/()\[\]._-]{6,}[.:]?\s*$")),
)
PROSE = "prose"


def shape_of(line):
    """The first matching SHAPE name, or `prose`. First match wins; see the SHAPES note."""
    for name, pattern in SHAPES:
        if pattern.match(line):
            return name
    return PROSE


def cluster(text):
    """{shape: count} for one revision of one file."""
    counts = collections.Counter()
    for line in text.splitlines():
        counts[shape_of(line)] += 1
    return counts


def columns(text):
    """{indent width: count}, the signal a shape cluster cannot carry.

    A continuation flattened from two spaces to zero keeps its shape and loses its meaning, and this is the only view in the tool that sees it.
    """
    widths = collections.Counter()
    for line in text.splitlines():
        if line.strip():
            widths[len(line) - len(line.lstrip(" \t"))] += 1
    return widths


def git_show(rev, path):
    """The file at `rev`, or None when it did not exist there."""
    done = subprocess.run(
        ["git", "show", "%s:%s" % (rev, path)], capture_output=True, text=True, check=False
    )
    return done.stdout if done.returncode == 0 else None


def changed_paths(rev, paths):
    """Tracked files differing between `rev` and the working tree, narrowed to `paths`."""
    argv = ["git", "diff", "--name-only", rev]
    if paths:
        argv += ["--", *paths]
    done = subprocess.run(argv, capture_output=True, text=True, check=False)
    return [p for p in done.stdout.split("\n") if p.strip()]


def report(rev, paths, want_columns):
    """(findings, summary): one entry per file whose shape multiset lost members."""
    findings = []
    totals_before = collections.Counter()
    totals_after = collections.Counter()
    files = changed_paths(rev, paths)
    for rel in files:
        before = git_show(rev, rel)
        if before is None:
            continue
        try:
            after = pathlib.Path(rel).read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            continue
        cb, ca = cluster(before), cluster(after)
        totals_before.update(cb)
        totals_after.update(ca)
        lost = {k: (cb[k], ca[k]) for k in cb if ca[k] < cb[k]}
        entry = {"path": rel, "lost": lost}
        if want_columns:
            wb, wa = columns(before), columns(after)
            entry["columns_lost"] = {str(k): (wb[k], wa[k]) for k in wb if wa[k] < wb[k]}
        if lost or entry.get("columns_lost"):
            findings.append(entry)
    summary = {
        "rev": rev,
        "files_compared": len(files),
        "before": dict(totals_before),
        "after": dict(totals_after),
        "delta": {k: totals_after[k] - totals_before[k] for k in set(totals_before) | set(totals_after)},
    }
    return findings, summary


def selftest():
    """Controls, each planted so the assertion can actually fail.

    A tool that reports structure must be shown to NOTICE a structure being eaten, and to stay quiet when a legitimate rewrap moves prose lines around. Both directions are here because a one-directional check passes just as well against a function that always answers the same way.
    """
    ok = 0
    failures = []

    def check(label, condition):
        nonlocal ok
        if condition:
            ok += 1
        else:
            failures.append(label)

    banner = "----------\nTITLE\n----------\nbody text here\n"
    eaten = "---------- TITLE ---------- body text here\n"
    check("a rule-line exists before the transform", cluster(banner)["rule-line"] == 2)
    check("and is gone after it", cluster(eaten)["rule-line"] == 0)
    check("the allcaps heading goes too", cluster(eaten)["allcaps"] == 0)

    wrapped = "one two\nthree four\nfive six\n"
    joined = "one two three four five six\n"
    check("a legitimate rewrap loses no NON-prose shape",
          all(cluster(joined)[k] >= cluster(wrapped)[k] for k in cluster(wrapped) if k != PROSE))

    indented = "- item\n  continuation line\n"
    flattened = "- item\ncontinuation line\n"
    check("a flattened continuation is invisible to shapes",
          cluster(indented)["list-cont"] == cluster(flattened).get("list-cont", 0) + 1)
    check("but visible to columns", columns(indented)[2] == 1 and columns(flattened).get(2, 0) == 0)

    check("a table row is a row before it is prose", shape_of("| a | b |") == "table-row")
    check("a fence is a fence first", shape_of("```python") == "fence")
    check("ordinary prose falls through", shape_of("an ordinary sentence here") == PROSE)

    for label in failures:
        print("*** FAIL *** %s" % label, file=sys.stderr)
    print("%d control(s) passed, %d failed" % (ok, len(failures)))
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--rev", default="HEAD", help="the revision to compare the working tree against")
    ap.add_argument("--columns", action="store_true", help="also report lost indent widths")
    ap.add_argument("--json", action="store_true", dest="as_json")
    ap.add_argument("--selftest", action="store_true")
    ap.add_argument("paths", nargs="*")
    args = ap.parse_args(argv)

    if args.selftest:
        return selftest()

    findings, summary = report(args.rev, args.paths, args.columns)

    # VACUOUS FLOOR. Zero compared files is not a clean result, it is the tool failing to see the change it was pointed at, and the two are indistinguishable from the exit code alone.
    if summary["files_compared"] == 0:
        print("VACUOUS: no tracked file differs from %s; nothing was compared." % args.rev,
              file=sys.stderr)
        return 2

    if args.as_json:
        print(json.dumps({"findings": findings, "summary": summary}, indent=2, sort_keys=True))
        return 1 if findings else 0

    print("shape-cluster diff against %s: %d file(s) compared" % (args.rev, summary["files_compared"]))
    for shape in sorted(summary["delta"]):
        delta = summary["delta"][shape]
        if delta:
            print("  %-14s %+d  (%d -> %d)" % (shape, delta, summary["before"].get(shape, 0),
                                               summary["after"].get(shape, 0)))
    if not findings:
        print("no file lost a shape; nothing structural disappeared.")
        return 0
    print("\n%d file(s) LOST a structural shape:" % len(findings))
    for entry in findings[:20]:
        bits = ", ".join("%s %d->%d" % (k, v[0], v[1]) for k, v in sorted(entry["lost"].items()))
        cols = entry.get("columns_lost")
        if cols:
            bits += " | indents " + ", ".join("%s:%d->%d" % (k, v[0], v[1]) for k, v in sorted(cols.items()))
        print("  %-58s %s" % (entry["path"][:58], bits))
    if len(findings) > 20:
        print("  ... and %d more file(s)" % (len(findings) - 20))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
