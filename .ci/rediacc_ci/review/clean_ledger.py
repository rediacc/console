"""The clean per-commit review ledger, read on the CI side (agent/plans/PLAN-clean-review-ledger.md D2, D4).

WHAT IT IS. `.claude/hooks/stop/wl_review.py` records a verdict that leaves nothing to do (clean or skipped, no finding, the whole diff seen, nothing dropped) as ONE JSON line of `agent/reviews/<branch-slug>/clean.jsonl`, and every other verdict as `<sha40>.md`. For any sha a `.md` beats a ledger line: it is the stricter record.

WHY A SECOND READER. Console CI's `pr-labels` job checks out `.ci/config/well-known.env`, `.ci/rediacc_ci`, `.github/actions` and `agent/reviews` only, so nothing on the CI side can import the writer. This module reads the same lines with the stdlib alone, as `review_table` mirrors the `.md` grammar for the same reason.

LENIENT WHERE THE WRITER IS STRICT. `wl_review.read_ledger` refuses an unknown key, and the push and merge guards refuse the branch on it. Here a garbled line is skipped with a warning, the way `review_table` still shows a garbled `.md` row: a label and a display are advisory, and never worth failing CI over. A sha seen twice keeps its first line (two checkouts on one branch can both append it).

The name avoids "ledger" for the constant because `pr_labels.LEDGER_PREFIX` already means the label-comment ledger on the PR.
"""

from __future__ import annotations

import json
import pathlib
import re

from rediacc_ci import log

NAME = "clean.jsonl"
VERDICTS = ("clean", "skipped (gitlink-only)", "skipped (no-review)")
SHA40 = re.compile(r"^[0-9a-f]{40}$")
BUMPS = ("none", "patch", "minor", "major")


def read(path: pathlib.Path | str) -> list[dict]:
    """Every readable line of one ledger as its JSON object plus `line` (1-based). [] when the file does not exist."""
    path = pathlib.Path(path)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return []
    except (OSError, UnicodeDecodeError) as exc:
        log.warn("clean_ledger: %s is unreadable (%s); its lines are skipped" % (path, exc))
        return []
    out: list[dict] = []
    seen: set[str] = set()
    for n, line in enumerate(text.split("\n"), start=1):
        if not line.strip():
            continue
        try:
            doc = json.loads(line)
        except ValueError:
            doc = None
        sha = doc.get("sha") if isinstance(doc, dict) else None
        if not (
            isinstance(doc, dict)
            and isinstance(sha, str)
            and SHA40.match(sha)
            and doc.get("verdict") in VERDICTS
        ):
            log.warn("clean_ledger: %s line %d is garbled; skipped" % (path, n))
            continue
        if sha in seen:
            continue
        seen.add(sha)
        out.append(dict(doc, line=n))
    return out


def verdict_of(doc: dict) -> dict | None:
    """The `{bump, kind, why}` vote of one line, as `pr_labels.read_verdict` reads a `.md`: only a `clean` verdict with labels votes, so a skipped line casts none."""
    labels = doc.get("labels")
    if doc.get("verdict") != "clean" or not isinstance(labels, dict):
        return None
    if labels.get("bump") not in BUMPS:
        return None
    kind = labels.get("kind")
    kinds = list(kind) if isinstance(kind, list) else []
    return {"bump": labels["bump"], "kind": kinds, "why": str(labels.get("why", ""))}


def labels_text(doc: dict) -> str:
    """The line's labels in the `.md` `Labels:` spelling (`bump=<b> kind=<k,...> why=<text>` or `(none)`), for a table cell."""
    labels = doc.get("labels")
    if not isinstance(labels, dict) or labels.get("bump") not in BUMPS:
        return "(none)"
    kinds = ",".join(labels.get("kind") or []) or "none"
    return "bump=%s kind=%s why=%s" % (labels["bump"], kinds, labels.get("why", ""))
