#!/usr/bin/env python3
"""The per-commit review history, folded by CLASS and by FILE, so the next writer on a file hears what reviews kept finding there (agent/plans/PLAN-experience-feedback.md P1, box A1).

WHY. About 6,500 per-commit review findings sit under `agent/reviews/`, and they recur by class: doc contradicts code, a missing control test, a swallowed error. None of that history reached the writer about to edit the same files, so the same finding came back on the same file. `index(root)` folds the record once per change of the store, and `brief_lines(index, owns)` turns the classes that recur on a brief's
`Owns:` paths into at most three lines the spawn guard (`warn_writer_brief`) hands the lead. B6 reads the same index for the reviewer's own "Prior on this file" line.

WHAT IS COUNTED. Only high and medium findings: a low finding is a style note, and a writer brief that repeats style notes is a brief nobody reads. A `fixed` finding is evidence that the class was real on that file; a `not-a-bug` one is counted SEPARATELY as `refuted` (P6 wants the refutation rate per file), and never as fixed. `open`, `waived` and the legacy `deferred` say nothing either way and are not counted.

THE CLASSIFIER is a keyword table shaped like the effort tuner's `JUDGE_SHAPES` (`wl_effort_tune.py`): one row per class, a regex over the Claim, first match wins, `other` when none does. A finding that carries its own class (the optional `Class:` record line B6 adds, read here as the attribute `CLASS_ATTR`) is believed over the table, as long as it names a class this table knows.

THE CACHE. `.ci/cache/review-classes/index.json`, keyed by the mtime and entry count of `agent/reviews/` and of each branch directory under it, plus the classifier's own signature. A new or rewritten record changes its directory's mtime (`wl_review.write_atomic` renames into place), so a key match means nothing under the store moved and the cached fold is returned WITHOUT parsing a single record. Any failure to read or write the cache falls back to a fresh fold; a cache is never a reason to answer wrong.

NO ENVIRONMENT READ, NO MODEL CALL, NO WRITE outside the cache directory.
"""

from __future__ import annotations

import collections
import contextlib
import hashlib
import json
import os
import pathlib
import re
import tempfile

REVIEWS_REL = "agent/reviews"
CACHE_REL = ".ci/cache/review-classes/index.json"
SCHEMA = 1

# The severities a finding must carry to count. Low findings are style notes (module docstring).
COUNTED_SEVERITIES = ("high", "medium")
# A class needs this many FIXED findings on the brief's Owns paths before it earns a line; two is a coincidence (A1 control).
MIN_FIXED = 3
# At most this many brief lines, strongest class first.
MAX_LINES = 3
# The Finding attribute B6's optional `Class:` record line will populate. Read with getattr, so records parsed before B6 lands still classify by the table.
CLASS_ATTR = "klass"
OTHER = "other"

# ONE ROW PER CLASS, first match wins, so the order is part of the table. Seam and swallowed-error come before the test class because a claim like "the monkeypatch is never restored, so no test ..." is about the seam, and "a failure is silently dropped and no test covers it" is about the swallow; doc-contradicts-code is last of the four because "the comment says" also
# appears inside the other three as a quotation.
CLASSES: tuple[dict[str, str], ...] = (
    {
        "class": "seam-not-restored",
        "what": "a patched seam, env var or global is not restored",
        "rx": r"(?i)(?:\b(?:is|are|was|were|never|not) (?:restored|unpatched|undone)\b|\bwithout restoring\b|\bleaks? (?:into|to|across) (?:the )?(?:next|later|other|subsequent|following)\b|\bmonkeypatch\w*|\bglobal state\b|\bpatch(?:ed|es)? (?:is|are) (?:never|not) (?:removed|reverted|restored))",
        "line": "restore every patched seam, env var and global in a fixture or a finally, so no case leaks into the next",
    },
    {
        "class": "swallowed-error",
        "what": "an error is swallowed or turned into a pass",
        "rx": r"(?i)\b(?:swallow\w*|silently|bare except|except Exception|catch(?:es)? (?:every|all|any)|is ignored|are ignored|ignores (?:the|its|a) (?:error|failure|exit|return)|fails? open|exits? 0|returns? (?:0|true|none|null|an empty)\b[^.]{0,40}\b(?:fail|error)|no error|without (?:an )?error|error is (?:lost|dropped|discarded))",
        "line": "make every failure path name its failure: no bare except, no silent fallback, no exit 0 or empty result on a failed read",
    },
    {
        "class": "missing-control-test",
        "what": "a change with no test, or a test that cannot fail",
        "rx": r"(?i)(?:\bno (?:test|selftest|control|case|assertion)s?\b|\bhas no test|\bnot tested\b|\buntested\b|\bno added test|\bno new test|\bwithout a test|\bwould (?:still )?pass\b|\bpasses (?:on|for|even|whether|with|regardless)\b|\bstill passes\b|\bonly asserts?\b|\bnever (?:exercised|asserted|checked)\b|\bnot (?:exercised|asserted|checked)\b|\bcannot fail\b|\bvacuous)",
        "line": "give every new branch a test that fails without it, plus a control that must stay silent, and watch the test go red once",
    },
    {
        "class": "doc-contradicts-code",
        "what": "a comment, docstring or message says something the code does not do",
        "rx": r"(?i)(?:\b(?:comment|docstring|doc comment|header comment|module header|help text|usage text|error message|readme|the (?:docs?|prose|commit message|commit body|commit subject|subject|commit))\b[^.;]{0,80}?\b(?:says?|said|claims?|states?|promises?|documents?)\b|\bcontradict\w*|\bno longer (?:true|accurate|matches)|\bstale (?:comment|doc|docstring|count|number)\b|\bdoes not match (?:the|what the) code)",
        "line": "reread every comment, docstring, message and doc line the change touches against the code it describes, and fix whichever is wrong",
    },
)
CLASS_NAMES = (*tuple(row["class"] for row in CLASSES), OTHER)
_COMPILED = tuple((row["class"], re.compile(row["rx"])) for row in CLASSES)
_BY_CLASS = {row["class"]: row for row in CLASSES}

# The table's own signature: editing a regex or adding a class invalidates every cached fold.
CLASSIFIER_SIG = hashlib.sha256(
    json.dumps([SCHEMA, COUNTED_SEVERITIES, CLASSES], sort_keys=True).encode("utf-8")
).hexdigest()[:16]


def classify(claim: str) -> str:
    """The class of one Claim text by the table, `other` when no row matches."""
    text = str(claim or "")
    for name, rx in _COMPILED:
        if rx.search(text):
            return name
    return OTHER


def finding_class(finding) -> str:
    """A finding's own `Class:` when it names a known class, else the table's answer on its Claim."""
    own = str(getattr(finding, CLASS_ATTR, "") or "").strip()
    if own in CLASS_NAMES:
        return own
    return classify(getattr(finding, "claim", ""))


def _review_module():
    """`wl_review`, imported lazily: a cache hit never needs it, and its import pulls in the store."""
    import wl_review

    return wl_review


def store_key(root) -> list | None:
    """[[rel, mtime_ns, entries], ...] for the reviews directory and each branch directory under it, sorted, or None when there is no store."""
    base = pathlib.Path(root) / REVIEWS_REL
    try:
        top = os.stat(base)
        subs = sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        return None
    key = [[REVIEWS_REL, top.st_mtime_ns, len(subs)]]
    for sub in subs:
        try:
            st = os.stat(sub)
            count = sum(1 for _ in os.scandir(sub))
        except OSError:
            continue
        key.append(["%s/%s" % (REVIEWS_REL, sub.name), st.st_mtime_ns, count])
    return key


def fold(root, parse=None) -> dict:
    """The index, built from every record: {"files": {path: {"fixed": {class: n}, "refuted": {class: n}}}, "records": n, "malformed": n, "counted": n}.

    `parse` is `wl_review.parse` unless a test hands another."""
    if parse is None:
        parse = _review_module().parse
    base = pathlib.Path(root) / REVIEWS_REL
    files: dict[str, dict[str, collections.Counter]] = {}
    records = malformed = counted = 0
    for path in sorted(base.glob("*/*.md")):
        try:
            review = parse(path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            malformed += 1
            continue
        records += 1
        for finding in getattr(review, "findings", ()) or ():
            if finding.severity not in COUNTED_SEVERITIES:
                continue
            kind = finding.resolution_kind()
            if kind == "fixed":
                bucket = "fixed"
            elif kind == "not-a-bug":
                bucket = "refuted"
            else:
                continue
            counted += 1
            per = files.setdefault(
                finding.file, {"fixed": collections.Counter(), "refuted": collections.Counter()}
            )
            per[bucket][finding_class(finding)] += 1
    return {
        "files": {
            f: {b: dict(sorted(c.items())) for b, c in per.items()}
            for f, per in sorted(files.items())
        },
        "records": records,
        "malformed": malformed,
        "counted": counted,
    }


def _write_cache(path: pathlib.Path, doc: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".index.", dir=str(path.parent))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            json.dump(doc, handle, sort_keys=True)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def index(root, parse=None, notes=None) -> dict:
    """The fold, from the cache when its key still matches the store, else rebuilt and cached.

    Returns the fold plus "cached": True|False. `notes`, when a list, collects one line per cache problem (unreadable, unwritable); the answer is still right without the cache. An absent store folds to zero files."""
    root = pathlib.Path(root)
    key = store_key(root)
    if key is None:
        return {"files": {}, "records": 0, "malformed": 0, "counted": 0, "cached": False}
    cache = root / CACHE_REL
    want = {"schema": SCHEMA, "classifier": CLASSIFIER_SIG, "key": key}
    try:
        doc = json.loads(cache.read_text(encoding="utf-8"))
        if isinstance(doc, dict) and all(doc.get(k) == v for k, v in want.items()):
            got = dict(doc["fold"])
            got["cached"] = True
            return got
    except FileNotFoundError:
        pass
    except (OSError, ValueError, KeyError, TypeError) as exc:
        if notes is not None:
            notes.append(
                "review-class cache unreadable (%s: %s), rebuilt" % (type(exc).__name__, exc)
            )
    built = fold(root, parse)
    try:
        _write_cache(cache, {**want, "fold": built})
    except OSError as exc:
        if notes is not None:
            notes.append("review-class cache not written (%s: %s)" % (type(exc).__name__, exc))
    return {**built, "cached": False}


def file_prior(idx: dict, path: str) -> dict:
    """{"fixed": n, "refuted": n, "top": class|""} for one file: B6's "Prior on this file" line."""
    per = (idx.get("files") or {}).get(path) or {}
    fixed = per.get("fixed") or {}
    refuted = per.get("refuted") or {}
    top = ""
    if fixed:
        top = min(fixed.items(), key=lambda kv: (-kv[1], kv[0]))[0]
    return {"fixed": sum(fixed.values()), "refuted": sum(refuted.values()), "top": top}


def class_counts(idx: dict, owns, match=None) -> tuple[dict[str, int], dict[str, set[str]]]:
    """({class: fixed count}, {class: {files}}) over the indexed files any Owns glob names. `match(globs, files)` is `wl_planconc.materialise` over the normalised globs unless a test hands another."""
    files = sorted((idx.get("files") or {}).keys())
    if match is None:
        import wl_planconc as X

        globs, _problems = X.normalize_owns(list(owns))
        hit = X.materialise(globs, files)
    else:
        hit = match(list(owns), files)
    counts: collections.Counter = collections.Counter()
    where: dict[str, set[str]] = {}
    for f in hit:
        for cls, n in ((idx["files"][f].get("fixed")) or {}).items():
            counts[cls] += n
            where.setdefault(cls, set()).add(f)
    return dict(counts), where


def brief_lines(idx: dict, owns, match=None, minimum=MIN_FIXED, limit=MAX_LINES) -> list[str]:
    """At most `limit` lines, one per class with at least `minimum` fixed findings on the Owns paths, strongest first; `other` never earns a line, since it says nothing a writer can act on."""
    counts, where = class_counts(idx, owns, match)
    ranked = sorted(
        # `_BY_CLASS` holds the table's rows only, so `other` (and any stale name) is left out here.
        ((cls, n) for cls, n in counts.items() if cls in _BY_CLASS and n >= minimum),
        key=lambda kv: (-kv[1], kv[0]),
    )
    out = []
    for cls, n in ranked[:limit]:
        row = _BY_CLASS[cls]
        files = sorted(where.get(cls) or ())
        shown = ", ".join(files[:2]) + (" and %d more" % (len(files) - 2) if len(files) > 2 else "")
        out.append(
            "Prior reviews fixed %d %r finding(s) (%s) on these files (%s): %s."
            % (n, cls, row["what"], shown, row["line"])
        )
    return out
