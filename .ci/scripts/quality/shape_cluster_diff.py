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

JSON FILES GET KEY PATHS, NOT SHAPES. A `.json` file's lines are nearly all `prose` to the shape table, so a dropped locale key reads as one prose line fewer, indistinguishable from a reformat. For each changed `.json` path the tool instead diffs the set of key paths (`a.b[0].c`) against `--rev`: added, removed, and value-type changed. A REMOVED key is the finding (exit 1); an added key or a type
change is reported for the reader. Chosen automatically by suffix, so one run over a mixed scope proves both kinds (agent/plans/PLAN-stop-hook-retro-20260925.md R20260925.4).

USE IT ON ANY MECHANICAL BULK CHANGE, before committing one. The exit code is the finding: 0 when no cluster shrank, 1 when one did. A shrinking cluster is not automatically wrong -- collapsing a hard-wrapped paragraph legitimately reduces `prose` -- so the tool reports and the reader rules. What it refuses to do is stay quiet.
"""

import argparse
import collections
import json
import pathlib
import re
import subprocess
import sys

# THE SHAPES, ordered because the FIRST match wins and the order encodes precedence. A fenced line is a fence before it is anything else; a table row is a row before it is prose. Each one is a structure a bulk transform can silently eat, and each was chosen from a real corruption rather than from a taxonomy: rule-line, table-row, html-comment and doc-header are the four REFLOW_STOP
# gaps this repository actually paid for, in the order they were found.
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


# TWO SHAPES ARE MARKDOWN-ONLY, and running them against source code was a real bug caught by dogfooding this tool against its own repository's first bulk `.py` reflow. `heading` (`^#{1,6}\s`) matches an ordinary single-`#` PYTHON COMMENT by coincidence, since one hash followed by a space satisfies `#{1,6}` at count 1. `indent-code` (`^ {4,}\S`) matches any ordinarily-indented
# Python statement, and just as often an ordinarily-indented COMMENT inside a function body. Both false-positived on a legitimate comment-paragraph join, reporting real reflow work as markdown-structure loss. `MARKDOWN_ONLY_SHAPES` names exactly the two, rather than a broader exclusion list, because every other shape (comment, list-item, table-row, allcaps, doctest) was measured to
# mean the same thing in a code comment that it means in markdown prose -- a banner or a numbered list inside a `#` block is exactly the structure this tool exists to protect there too.
MARKDOWN_ONLY_SHAPES = frozenset({"heading", "indent-code"})
MARKDOWN_SUFFIXES = frozenset({".md", ".mdx"})


def shape_of(line, markdown=True):
    """The first matching SHAPE name, or `prose`. First match wins; see the SHAPES note.

    `markdown=False` skips `MARKDOWN_ONLY_SHAPES`, so a `.py`/`.ts`/`.go` line falls through to `comment`/`list-item`/etc. instead of colliding with a pattern tuned for a different language.
    """
    for name, pattern in SHAPES:
        if not markdown and name in MARKDOWN_ONLY_SHAPES:
            continue
        if pattern.match(line):
            return name
    return PROSE


def cluster(text, markdown=True):
    """{shape: count} for one revision of one file."""
    counts = collections.Counter()
    for line in text.splitlines():
        counts[shape_of(line, markdown=markdown)] += 1
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


JSON_SUFFIXES = frozenset({".json"})


def _json_type(value):
    """The JSON type name of a parsed value: object, array, string, number, boolean or null."""
    if isinstance(value, dict):
        return "object"
    if isinstance(value, list):
        return "array"
    if isinstance(value, bool):
        return "boolean"
    if isinstance(value, (int, float)):
        return "number"
    if value is None:
        return "null"
    return "string"


def key_paths(value, prefix=""):
    """{key path: JSON type} for every node under `value`. An object member is `prefix.key`, an array element `prefix[i]`; the root itself is not a path."""
    out: dict[str, str] = {}
    if isinstance(value, dict):
        items = (("%s.%s" % (prefix, k) if prefix else str(k), v) for k, v in value.items())
    elif isinstance(value, list):
        items = (("%s[%d]" % (prefix, i), v) for i, v in enumerate(value))
    else:
        return out
    for path, child in items:
        out[path] = _json_type(child)
        out.update(key_paths(child, path))
    return out


def json_key_diff(before, after):
    """{added, removed, type_changed} between two JSON texts, or {error} when one side does not parse. `after=None` is a deleted file: every key is removed."""
    try:
        kb = key_paths(json.loads(before))
        ka = key_paths(json.loads(after)) if after is not None else {}
    except ValueError as exc:
        return {"error": str(exc)}
    return {
        "added": sorted(set(ka) - set(kb)),
        "removed": sorted(set(kb) - set(ka)),
        "type_changed": {k: (kb[k], ka[k]) for k in sorted(set(kb) & set(ka)) if kb[k] != ka[k]},
    }


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
    """(findings, summary): one entry per file whose shape multiset lost members, or, for a `.json` file, which lost a key path or no longer parses. `summary["json"]` carries every changed `.json` file's key diff."""
    findings = []
    totals_before = collections.Counter()
    totals_after = collections.Counter()
    json_files = []
    files = changed_paths(rev, paths)
    for rel in files:
        before = git_show(rev, rel)
        if before is None:
            continue
        if pathlib.Path(rel).suffix in JSON_SUFFIXES:
            try:
                after = pathlib.Path(rel).read_text(encoding="utf-8")
            except OSError:
                after = None
            keys = json_key_diff(before, after)
            if keys.get("error") or keys["added"] or keys["removed"] or keys["type_changed"]:
                json_files.append(dict(keys, path=rel))
            if keys.get("error") or keys["removed"]:
                findings.append({"path": rel, "lost": {}, "keys": keys})
            continue
        try:
            after = pathlib.Path(rel).read_text(encoding="utf-8", errors="surrogateescape")
        except OSError:
            continue
        markdown = pathlib.Path(rel).suffix in MARKDOWN_SUFFIXES
        cb, ca = cluster(before, markdown=markdown), cluster(after, markdown=markdown)
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
        "delta": {
            k: totals_after[k] - totals_before[k] for k in set(totals_before) | set(totals_after)
        },
        "json": json_files,
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
    check(
        "a legitimate rewrap loses no NON-prose shape",
        all(cluster(joined)[k] >= cluster(wrapped)[k] for k in cluster(wrapped) if k != PROSE),
    )

    indented = "- item\n  continuation line\n"
    flattened = "- item\ncontinuation line\n"
    check(
        "a flattened continuation is invisible to shapes",
        cluster(indented)["list-cont"] == cluster(flattened).get("list-cont", 0) + 1,
    )
    check("but visible to columns", columns(indented)[2] == 1 and columns(flattened).get(2, 0) == 0)

    check("a table row is a row before it is prose", shape_of("| a | b |") == "table-row")
    check("a fence is a fence first", shape_of("```python") == "fence")
    check("ordinary prose falls through", shape_of("an ordinary sentence here") == PROSE)

    # THE MARKDOWN-ONLY FIX, planted against the exact live case that found it: a bare single-`#` Python comment joining with its neighbour must not read as heading loss.
    py_comment = "# a first line of a comment paragraph here\n# a second line joining it\n"
    py_joined = "# a first line of a comment paragraph here a second line joining it\n"
    check(
        "a Python comment reads as 'comment', not 'heading', when markdown=False",
        cluster(py_comment, markdown=False)["heading"] == 0,
    )
    check(
        "joining it costs no heading count when markdown=False",
        cluster(py_joined, markdown=False)["heading"] == 0,
    )
    check(
        "the SAME line genuinely does read as a heading when markdown=True",
        cluster(py_comment, markdown=True)["heading"] == 2,
    )
    indented_comment = "def f():\n    # an indented comment line\n    x = 1\n"
    check(
        "an indented comment reads as 'comment', not 'indent-code', when markdown=False",
        cluster(indented_comment, markdown=False)["indent-code"] == 0,
    )

    # JSON KEY-PATH MODE (R20260925.4). Each fire has an inverse differing by one fact.
    locale = '{"a": {"b": "x", "c": "y"}, "n": 1}'
    check(
        "key paths name every nested member with its type",
        key_paths(json.loads(locale))
        == {"a": "object", "a.b": "string", "a.c": "string", "n": "number"},
    )
    dropped = json_key_diff(locale, '{"a": {"b": "x"}, "n": 1}')
    check("a dropped nested key is REMOVED", dropped["removed"] == ["a.c"])
    reordered = json_key_diff(locale, '{"n": 1, "a": {"c": "Y", "b": "X"}}')
    check(
        "but a reorder plus new values removes, adds and retypes nothing",
        reordered == {"added": [], "removed": [], "type_changed": {}},
    )
    grown = json_key_diff(locale, '{"a": {"b": "x", "c": "y", "d": "z"}, "n": 1}')
    check("an added key is ADDED, not removed", grown["added"] == ["a.d"] and not grown["removed"])
    retyped = json_key_diff(locale, '{"a": {"b": "x", "c": "y"}, "n": "1"}')
    check(
        "a value whose type changes is TYPE-CHANGED and nothing else",
        retyped["type_changed"] == {"n": ("number", "string")} and not retyped["removed"],
    )
    check("a deleted file removes every key", len(json_key_diff(locale, None)["removed"]) == 4)
    check("a file that no longer parses is an error", "error" in json_key_diff(locale, "{"))
    check(
        "an array element is an indexed path",
        key_paths([{"k": 1}]) == {"[0]": "object", "[0].k": "number"},
    )

    for label in failures:
        print("*** FAIL *** %s" % label, file=sys.stderr)
    print("%d control(s) passed, %d failed" % (ok, len(failures)))
    return 1 if failures else 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument(
        "--rev", default="HEAD", help="the revision to compare the working tree against"
    )
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
        print(
            "VACUOUS: no tracked file differs from %s; nothing was compared." % args.rev,
            file=sys.stderr,
        )
        return 2

    if args.as_json:
        print(json.dumps({"findings": findings, "summary": summary}, indent=2, sort_keys=True))
        return 1 if findings else 0

    print(
        "shape-cluster diff against %s: %d file(s) compared" % (args.rev, summary["files_compared"])
    )
    for shape in sorted(summary["delta"]):
        delta = summary["delta"][shape]
        if delta:
            print(
                "  %-14s %+d  (%d -> %d)"
                % (shape, delta, summary["before"].get(shape, 0), summary["after"].get(shape, 0))
            )
    for entry in summary["json"][:20]:
        if entry.get("error"):
            print("  json %-53s does not parse: %s" % (entry["path"][:53], entry["error"]))
            continue
        print(
            "  json %-53s +%d key(s) -%d key(s) ~%d type(s)"
            % (
                entry["path"][:53],
                len(entry["added"]),
                len(entry["removed"]),
                len(entry["type_changed"]),
            )
        )
        for label, keys in (("added", entry["added"]), ("removed", entry["removed"])):
            for key in keys[:10]:
                print("      %s %s" % (label, key))
        for key, (was, now) in list(entry["type_changed"].items())[:10]:
            print("      type %s %s->%s" % (key, was, now))
    if not findings:
        print("no file lost a shape or a key; nothing structural disappeared.")
        return 0
    print("\n%d file(s) LOST a structural shape or a JSON key:" % len(findings))
    for entry in findings[:20]:
        keys = entry.get("keys")
        if keys is not None:
            bits = keys.get("error") or "removed key(s): " + ", ".join(keys["removed"][:5])
            print("  %-58s %s" % (entry["path"][:58], bits))
            continue
        bits = ", ".join("%s %d->%d" % (k, v[0], v[1]) for k, v in sorted(entry["lost"].items()))
        cols = entry.get("columns_lost")
        if cols:
            bits += " | indents " + ", ".join(
                "%s:%d->%d" % (k, v[0], v[1]) for k, v in sorted(cols.items())
            )
        print("  %-58s %s" % (entry["path"][:58], bits))
    if len(findings) > 20:
        print("  ... and %d more file(s)" % (len(findings) - 20))
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
