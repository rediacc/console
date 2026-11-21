#!/usr/bin/env python3
"""The per-commit review's security checklist: rendered into wl_review.PROMPT, and learned from the review record over time (operator ruling 2026-11-19, worklist #bbd0f487).

WHY. The haiku reviewer saw "a security hole" as one word in its severity scale and nothing about this repository: renet runs shell as root, the CLI builds ssh commands, the account Worker queries D1, secrets come only through bws_env profiles. b940b84b3 fixed `rdc config field get` printing every secret below a parent pointer, a defect the per-commit review had passed. The checklist names those defects, and the finding class `security` makes every one of them block a push whatever its severity (wl_review.finding_blocks).

THE DATA. `.claude/config/review-security.json` holds the base items (id, area, text, examples, added_from) and the knobs. `agent/ledgers/review-security.jsonl` is the learned layer and its audit trail, append-only, one JSON row per event:

  {"v": 1, "kind": "proposal", "type": "fp-note" | "candidate", "key": ..., "ts": ..., <payload>}
  {"v": 1, "kind": "applied",  "type": ..., "key": ..., "ts": ..., "reason": ..., <payload>}
  {"v": 1, "kind": "retired",  "type": ..., "key": ..., "ts": ..., "reason": ...}

A key appears once as a proposal and never again as one, so the ledger grows by at most three rows per distinct lesson, and a retired lesson is not re-learned. The active set (applied minus retired) is capped per type (`learn.max_fp_notes`, `learn.max_learned_items`): past the cap the oldest applied rows are retired with the cap named as the reason.

WHAT IS LEARNED, deterministically and with no model call:
  fp-note    a `security` finding a person closed `not-a-bug` (the existence oracle's refutations are about names, not security, and are left out). Rendered as "refuted before, do not re-report" when a later commit touches the same file.
  candidate  a security fix found OUTSIDE the per-commit review: a commit whose subject is a `fix` naming a security keyword, whose `Plan-Box:` line says security, or which carries a `Security-Fix:` trailer, touching a non-test file whose previous commit has a model review (clean or findings) with no `security` finding on that file. Rendered as a learned checklist line when a later commit touches that file or its directory.

HOW IT RUNS WITHOUT A PERSON. The detached review child (`wl_review.py --run`) calls `maybe_learn` after each review; it learns at most once per `learn.every_h` hours (stamp under `.ci/cache/review-security/`, gitignored) and under a file lock, since two reviewers can finish at once. `--learn [--write]` runs it in the foreground. A failure is logged to the review log and never fails the review.

RENDERING is bounded by `render_cap_chars`: the base items always fit (a test pins that), the learned lines for the touched files follow until the cap.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import hashlib
import json
import pathlib
import posixpath
import re
import sys
import time

HERE = pathlib.Path(__file__).resolve().parent
CONSOLE_ROOT = HERE.parents[2]
CONFIG_REL = ".claude/config/review-security.json"
LEDGER_REL = "agent/ledgers/review-security.jsonl"
CACHE_REL = ".ci/cache/review-security"
REVIEWS_REL = "agent/reviews"
SECURITY = "security"
LEDGER_V = 1
TYPES = ("fp-note", "candidate")
KINDS = ("proposal", "applied", "retired")

LEARN_DEFAULTS = {
    "every_h": 6,
    "scan_commits": 300,
    "max_fp_notes": 24,
    "max_learned_items": 12,
    "render_fp_notes": 4,
    "render_learned": 3,
}

HEADER = (
    "SECURITY CHECKLIST. Class security is only for a concrete defect from this list that the diff shows; "
    "every security finding blocks the push whatever its severity, so never give the class to a guess:"
)

# A security fix found outside the review (module docstring, `candidate`).
SEC_TRAILER = re.compile(r"(?mi)^Security-Fix:[ \t]*\S")
PLANBOX_SEC = re.compile(r"(?mi)^Plan-Box:[^\n]*\bsecurity\b")
SUBJECT_FIX = re.compile(r"(?i)^(?:fix|security|sec)(?:\([^)]*\))?!?:")
SUBJECT_KW = re.compile(
    r"(?i)\b(?:secrets?|redact\w*|injection|inject(?:s|ed)?|path traversal|traversal|privilege\w*|pull_request_target|unauthori[sz]ed|auth bypass|cve-\d+)\b"
)
AREA_RULES = (
    (
        "secrets",
        re.compile(
            r"(?i)\b(?:secrets?|redact\w*|tokens?|credentials?|passwords?|private ?keys?|bws)\b"
        ),
    ),
    ("injection", re.compile(r"(?i)\b(?:inject\w*|quot\w*|travers\w*|escap\w*|sql|shell|argv)\b")),
    (
        "auth",
        re.compile(r"(?i)\b(?:auth\w*|tenant|role|permissions?|pull_request_target|workflow)\b"),
    ),
    ("guard", re.compile(r"(?i)\b(?:guard|gate|hook|bypass|fail[- ]open)\b")),
)
NOT_CODE = re.compile(r"(?:^agent/|^docs/|\.md$|\.jsonl$)")


class ChecklistError(ValueError):
    """The checklist file is missing or does not have the documented shape."""


# --------------------------------------------------------------------------- the checklist


def load_checklist(root=None) -> dict:
    """The checklist document, shape-checked. Raises ChecklistError naming what is wrong."""
    path = pathlib.Path(root or CONSOLE_ROOT) / CONFIG_REL
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as exc:
        raise ChecklistError(
            "%s unreadable: %s: %s" % (CONFIG_REL, type(exc).__name__, exc)
        ) from exc
    if not isinstance(doc, dict):
        raise ChecklistError("%s is not a JSON object" % CONFIG_REL)
    cap = doc.get("render_cap_chars")
    if not isinstance(cap, int) or isinstance(cap, bool) or cap < 200:
        raise ChecklistError(
            "%s render_cap_chars is %r; expected an integer >= 200" % (CONFIG_REL, cap)
        )
    items = doc.get("items")
    if not isinstance(items, list) or not items:
        raise ChecklistError("%s items is not a non-empty list" % CONFIG_REL)
    ids = set()
    for n, item in enumerate(items):
        if not isinstance(item, dict):
            raise ChecklistError("%s items[%d] is not an object" % (CONFIG_REL, n))
        for key in ("id", "area", "text", "added_from"):
            if not isinstance(item.get(key), str) or not item[key].strip():
                raise ChecklistError(
                    "%s items[%d].%s is not a non-empty string" % (CONFIG_REL, n, key)
                )
        if not isinstance(item.get("examples", []), list) or not all(
            isinstance(e, str) for e in item.get("examples", [])
        ):
            raise ChecklistError("%s items[%d].examples is not a list of strings" % (CONFIG_REL, n))
        if item["id"] in ids:
            raise ChecklistError("%s items[%d].id %r is a duplicate" % (CONFIG_REL, n, item["id"]))
        ids.add(item["id"])
    learn: dict[str, int | float] = dict(LEARN_DEFAULTS)
    raw = doc.get("learn", {})
    if not isinstance(raw, dict):
        raise ChecklistError("%s learn is not an object" % CONFIG_REL)
    for key, value in raw.items():
        if key in LEARN_DEFAULTS:
            if not isinstance(value, (int, float)) or isinstance(value, bool) or value < 0:
                raise ChecklistError(
                    "%s learn.%s is %r; expected a number >= 0" % (CONFIG_REL, key, value)
                )
            learn[key] = value
    doc["learn"] = learn
    return doc


def _item_line(item) -> str:
    examples = [e for e in item.get("examples") or [] if e.strip()]
    tail = " (e.g. %s)" % "; ".join(examples) if examples else ""
    return "- %s [%s] %s%s." % (item["id"], item["area"], item["text"].rstrip("."), tail)


def _learned_line(row) -> str:
    return (
        "- learned [%s] %s: %s fixed a security defect here after a clean review of %s (%s); check this change for the same defect."
        % (
            row.get("area", SECURITY),
            row.get("file", ""),
            str(row.get("fix", ""))[:8],
            str(row.get("missed", ""))[:8],
            str(row.get("fix_subject", ""))[:90],
        )
    )


def _fp_line(row) -> str:
    return "- %s: refuted before, do not re-report: %s" % (
        row.get("file", ""),
        str(row.get("claim", ""))[:120],
    )


def render(checklist: dict, active: list, paths) -> str:
    """The prompt block: the base items, then the learned lines about the touched files, newest first, until `render_cap_chars`. "" never: a valid checklist always renders its header and items."""
    cap = int(checklist["render_cap_chars"])
    learn = checklist["learn"]
    touched = set(paths or ())
    dirs = {posixpath.dirname(p) for p in touched}
    lines = [HEADER] + [_item_line(i) for i in checklist["items"]]
    newest = sorted(
        active, key=lambda r: (str(r.get("ts", "")), str(r.get("key", ""))), reverse=True
    )
    learned = [
        r
        for r in newest
        if r.get("type") == "candidate"
        and (r.get("file") in touched or posixpath.dirname(str(r.get("file", ""))) in dirs)
    ][: int(learn["render_learned"])]
    notes = [r for r in newest if r.get("type") == "fp-note" and r.get("file") in touched][
        : int(learn["render_fp_notes"])
    ]
    extra = []
    if learned:
        extra.append("Learned from security fixes the review missed on these files:")
        extra.extend(_learned_line(r) for r in learned)
    if notes:
        extra.append("Do not report (a person refuted these security claims on these files):")
        extra.extend(_fp_line(r) for r in notes)
    out: list[str] = []
    size = 1  # the block ends in two newlines and the join drops one separator, so the returned text is exactly `size` characters
    for line in lines + extra:
        if size + len(line) + 1 > cap:
            break
        out.append(line)
        size += len(line) + 1
    return "\n".join(out) + "\n\n"


def security_text(root, paths, log=print) -> str:
    """The rendered block for one review, or "" with a logged reason when the checklist cannot be read: a broken checklist is named in the review log, and the review still runs."""
    try:
        checklist = load_checklist(root)
    except ChecklistError as exc:
        log("security checklist unavailable: %s" % exc)
        return ""
    rows, problems = read_ledger(root)
    for p in problems[:3]:
        log("security ledger: %s" % p)
    return render(checklist, active_rows(rows), paths)


# --------------------------------------------------------------------------- the ledger


def ledger_path(root) -> pathlib.Path:
    return pathlib.Path(root) / LEDGER_REL


def read_ledger(root) -> tuple[list, list]:
    """(rows, problems): every well-formed row in file order, and one line per malformed one. A missing ledger is ([], [])."""
    path = ledger_path(root)
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return [], []
    except OSError as exc:
        return [], ["%s unreadable: %s" % (LEDGER_REL, exc)]
    rows, problems = [], []
    for n, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError as exc:
            problems.append("%s:%d is not JSON (%s)" % (LEDGER_REL, n, exc))
            continue
        if (
            not isinstance(row, dict)
            or row.get("kind") not in KINDS
            or row.get("type") not in TYPES
            or not isinstance(row.get("key"), str)
        ):
            problems.append("%s:%d lacks kind/type/key" % (LEDGER_REL, n))
            continue
        rows.append(row)
    return rows, problems


def active_rows(rows) -> list:
    """The applied rows not later retired, in the order they were applied."""
    active: dict[str, dict] = {}
    for row in rows:
        if row["kind"] == "applied":
            active[row["key"]] = row
        elif row["kind"] == "retired":
            active.pop(row["key"], None)
    return list(active.values())


def _append(root, rows) -> None:
    if not rows:
        return
    path = ledger_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(row, sort_keys=True) + "\n")


def _key(kind, *parts) -> str:
    return "%s:%s" % (kind, hashlib.sha256("\x1f".join(parts).encode("utf-8")).hexdigest()[:12])


def _norm(text) -> str:
    return " ".join(re.findall(r"[a-z0-9_]+", str(text or "").lower())[:16])


# --------------------------------------------------------------------------- learning


def _review_module():
    import wl_review

    return wl_review


def all_records(root) -> list:
    """[(dir name, review)] for every parsable record under agent/reviews/, and the malformed count is dropped here on purpose: branch_state and check:ci-review-resolutions name malformed records; the learner only reads what parses."""
    rv = _review_module()
    base = pathlib.Path(root) / REVIEWS_REL
    out: list = []
    try:
        dirs = sorted(p for p in base.iterdir() if p.is_dir())
    except OSError:
        return out
    for d in dirs:
        records, _bad = rv.dir_records(d)
        out.extend((d.name, review) for _path, review in records)
    return out


def fp_proposals(records, now_s) -> list:
    """One fp-note proposal per `security` finding a person closed not-a-bug."""
    rv = _review_module()
    rx = rv.RESOLUTION_BY_KIND["not-a-bug"]
    out = []
    for branch, review in records:
        for f in review.findings:
            if f.klass != SECURITY or f.resolution_kind() != "not-a-bug" or f.oracle_refuted():
                continue
            m = rx.match(f.resolution)
            out.append(
                {
                    "v": LEDGER_V,
                    "kind": "proposal",
                    "type": "fp-note",
                    "key": _key("fp", f.file, _norm(f.claim)),
                    "ts": now_s,
                    "file": f.file,
                    "finding": "%s/%s" % (branch, f.id),
                    "claim": f.claim[:200],
                    "evidence": (m.group(1) if m else "")[:160],
                }
            )
    return out


def is_security_fix(message) -> bool:
    text = str(message or "")
    subject = text.split("\n", 1)[0]
    return bool(
        SEC_TRAILER.search(text)
        or PLANBOX_SEC.search(text)
        or (SUBJECT_FIX.match(subject) and SUBJECT_KW.search(subject))
    )


def area_of(message) -> str:
    for area, rx in AREA_RULES:
        if rx.search(str(message or "")):
            return area
    return SECURITY


def candidate_proposals(root, records, now_s, scan, repo=None, skipped=None) -> list:
    """One candidate per (non-test code file, security-fix subject) whose previous commit a model review called clean of security findings on that file. A fix commit whose file list git cannot read is not learned from, and its short sha is appended to `skipped` when the caller passes a list."""
    rv = _review_module()
    repo = pathlib.Path(repo or root)
    by_sha: dict = {}
    by_patch: dict = {}
    for branch, review in records:
        by_sha.setdefault(review.sha, (branch, review))
        if rv.SHA40.match(review.patch_id or ""):
            by_patch.setdefault(review.patch_id, (branch, review))
    rc, out = rv.git(
        repo, "log", "--no-merges", "-n", str(int(scan)), "--format=%H%x1f%B%x1e", "HEAD"
    )
    if rc != 0:
        raise OSError("git log failed in %s (rc=%s)" % (repo, rc))
    found = []
    for chunk in out.split("\x1e"):
        if "\x1f" not in chunk:
            continue
        sha, message = chunk.strip("\n").split("\x1f", 1)
        sha = sha.strip()
        if not rv.SHA40.match(sha) or not is_security_fix(message):
            continue
        subject = message.strip().split("\n", 1)[0]
        rc, names = rv.git(repo, "show", "--name-only", "--format=", sha)
        if rc != 0:
            if skipped is not None:
                skipped.append(sha[:12])
            continue
        for path in sorted({n.strip() for n in names.splitlines() if n.strip()}):
            if NOT_CODE.search(path) or rv.is_test_path(path):
                continue
            prev = rv.git_out(repo, "log", "-1", "--format=%H", "%s^" % sha, "--", path)
            if not rv.SHA40.match(prev):
                continue
            hit = by_sha.get(prev)
            if hit is None:
                pid = rv.patch_id(repo, prev)
                hit = by_patch.get(pid) if pid else None
            if hit is None:
                continue
            branch, review = hit
            if review.verdict not in ("clean", "findings"):
                continue
            if any(f.klass == SECURITY and f.file == path for f in review.findings):
                continue
            found.append(
                {
                    "v": LEDGER_V,
                    "kind": "proposal",
                    "type": "candidate",
                    "key": _key("cand", path, _norm(subject)),
                    "ts": now_s,
                    "file": path,
                    "fix": sha,
                    "fix_subject": subject[:160],
                    "missed": prev,
                    "missed_review": "%s/%s" % (branch, review.sha8),
                    "area": area_of(message),
                }
            )
    return found


def _now_iso(now=None) -> str:
    t = time.time() if now is None else now
    return datetime.datetime.fromtimestamp(t, datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def plan(rows, proposals, checklist, now_s) -> list:
    """The rows one learning pass appends, in order: each NEW proposal (a key never seen in the ledger, first occurrence wins), its applied row, then a retired row for each oldest active row past its type's cap. Pure."""
    learn = checklist["learn"]
    caps = {"fp-note": int(learn["max_fp_notes"]), "candidate": int(learn["max_learned_items"])}
    known = {r["key"] for r in rows}
    out = []
    for p in proposals:
        if p["key"] in known:
            continue
        known.add(p["key"])
        out.append(p)
        applied = dict(p, kind="applied", ts=now_s)
        applied["reason"] = (
            "auto: a person refuted this security claim with cited evidence"
            if p["type"] == "fp-note"
            else "auto: a security fix touched code a model review called clean"
        )
        out.append(applied)
    active = active_rows(rows + out)
    for kind, cap in caps.items():
        mine = [r for r in active if r["type"] == kind]
        excess = len(mine) - cap
        if excess > 0:
            oldest = sorted(mine, key=lambda r: (str(r.get("ts", "")), r["key"]))[:excess]
            out.extend(
                {
                    "v": LEDGER_V,
                    "kind": "retired",
                    "type": kind,
                    "key": r["key"],
                    "ts": now_s,
                    "reason": "cap %d %s rows" % (cap, kind),
                }
                for r in oldest
            )
    return out


def learn(root, write=False, now=None, repo=None, log=print) -> dict:
    """One learning pass. Returns {"new": rows planned, "problems": [...], "written": bool}."""
    checklist = load_checklist(root)
    rows, problems = read_ledger(root)
    now_s = _now_iso(now)
    records = all_records(root)
    proposals = fp_proposals(records, now_s)
    skipped: list = []
    try:
        proposals += candidate_proposals(
            root, records, now_s, checklist["learn"]["scan_commits"], repo, skipped
        )
    except OSError as exc:
        problems.append("candidate scan skipped: %s" % exc)
    if skipped:
        problems.append(
            "candidate scan: git could not list the files of %d security fix(es), not learned from: %s"
            % (len(skipped), ", ".join(skipped[:5]))
        )
    new = plan(rows, proposals, checklist, now_s)
    if write:
        _append(root, new)
    for p in problems:
        log("security learner: %s" % p)
    return {"new": new, "problems": problems, "written": bool(write and new)}


@contextlib.contextmanager
def _lock(root):
    d = pathlib.Path(root) / CACHE_REL
    d.mkdir(parents=True, exist_ok=True)
    fh = (d / "lock").open("a+")
    try:
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except BlockingIOError:
            yield False
            return
        try:
            yield True
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)
    finally:
        fh.close()


def maybe_learn(root, now=None, log=print, repo=None):
    """The cadence the review child runs: one write-mode pass when `learn.every_h` hours passed since the last one and no other reviewer holds the lock. Returns the pass's summary, or None when not due or busy."""
    checklist = load_checklist(root)
    every_s = float(checklist["learn"]["every_h"]) * 3600
    t = time.time() if now is None else now
    stamp = pathlib.Path(root) / CACHE_REL / "stamp.json"
    with _lock(root) as held:
        if not held:
            log("security learner: another reviewer holds the lock")
            return None
        try:
            last = float(json.loads(stamp.read_text(encoding="utf-8")).get("last_s", 0))
        except FileNotFoundError:
            last = 0.0
        except (OSError, ValueError, AttributeError, TypeError) as exc:
            log("security learner: stamp unreadable (%s), learning now" % exc)
            last = 0.0
        if t - last < every_s:
            return None
        summary = learn(root, write=True, now=t, repo=repo, log=log)
        stamp.write_text(json.dumps({"last_s": t, "last": _now_iso(t)}), encoding="utf-8")
        log("security learner: %d row(s) appended to %s" % (len(summary["new"]), LEDGER_REL))
        return summary


USAGE = """usage:
  wl_reviewsec.py --render [<path>...]   print the checklist block a commit touching these paths gets
  wl_reviewsec.py --learn [--write]      one learning pass; without --write only print the rows it would append
  wl_reviewsec.py --status               the active learned rows and the ledger's problems
"""


def main(argv) -> int:
    root = CONSOLE_ROOT
    if not argv or argv[0] in ("-h", "--help"):
        sys.stdout.write(USAGE)
        return 0 if argv else 2
    try:
        if argv[0] == "--render":
            text = security_text(root, argv[1:], log=lambda m: print(m, file=sys.stderr))
            sys.stdout.write(text)
            print("(%d chars)" % len(text.rstrip("\n")), file=sys.stderr)
            return 0 if text else 1
        if argv[0] == "--learn":
            summary = learn(root, write="--write" in argv, log=lambda m: print(m, file=sys.stderr))
            for row in summary["new"]:
                print(json.dumps(row, sort_keys=True))
            print(
                "%d row(s) %s"
                % (len(summary["new"]), "appended" if summary["written"] else "planned"),
                file=sys.stderr,
            )
            return 0
        if argv[0] == "--status":
            rows, problems = read_ledger(root)
            active = active_rows(rows)
            print("%d ledger row(s), %d active learned row(s)" % (len(rows), len(active)))
            for row in active:
                print("  %s %s %s" % (row["type"], row["key"], row.get("file", "")))
            for p in problems:
                print("  PROBLEM %s" % p)
            return 1 if problems else 0
    except ChecklistError as exc:
        print("security checklist: %s" % exc, file=sys.stderr)
        return 2
    sys.stderr.write(USAGE)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
