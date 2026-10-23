"""wl_ruling: the durable OPERATOR RULING record, and the one question a Stop check asks of it.

WHY (agent/plans/PLAN-stop-hook-rulings-campaign.md section 2, approved by the operator ruling on #373907ed). `agent/RULES.md` was read at exactly one place in the hook tree, where its text is pasted into a briefing, so no check consulted it before firing. A decision the operator gave about one subject (this submodule pointer, at this sha) lived only in a session's memory or
in prose a substring scan might or might not match, and the next session fired the same warning on its first stop.

THE LEDGER. `agent/rulings/<session8>.jsonl`, append-only, one file per WRITING session, for the reason wl_store's event log and wl_reggate's per-branch ledger already give: both sides of a merge append at EOF, so a single shared ledger conflicts on every concurrent append and per-writer files never do. One row per event:

    {ev, id, at, by, check, subject, sig, verdict, text[, until]}

`ev` is `rule` or `revoke`. A reversal is a second, `revoke` row naming the first row's id; THERE IS NO DELETE PATH, which is what makes a silent drop impossible. `sig` is `subject_sig(subject)`, the key a check computes from what it is about to say, so a ruling on one sha never mutes a different one.

THE RENDERED SECTION. `worklist.py --rule` appends the row AND rewrites the generated `## Rulings (machine-checked)` section of `agent/RULES.md` from the whole ledger; `check:ci-operator-rulings` holds the two byte-equal, the anti-lying-cache discipline wl_planindex states for the plan census. The render reads the LEDGER ONLY, never the clock: an expiry is printed as its instant, not as "expired", so the committed section cannot drift by the passage of time and the gate cannot flap at an `until`.

THE QUESTION. `settled(root, check_key, subject_sig)` globs EVERY session's ledger (a ruling binds the tree, not the session that recorded it) and returns the live ruling row or None. ANY error returns None, which restores exactly the behaviour a check had before rulings existed: this runs inside the Stop hook of every session in the worktree, and the safe direction is to warn
too often rather than too rarely.

Standard library only, so the CI gate can import it from a checkout with no hook dependencies installed.
"""

from __future__ import annotations

import contextlib
import datetime
import fcntl
import hashlib
import json
import os
import pathlib
import re
import tempfile

RULINGS_DIR_NAME = "rulings"
RULES_MD_NAME = "RULES.md"

#: The checks whose `vadd` passes a `subject=`, and so the only keys a ruling can mute. A ruling on any other key would be recorded and then consulted by nothing, which is a silent no-op dressed as a decision, so `--rule` refuses it and names this set.
RULABLE_CHECKS = frozenset({"submodule", "bigpieces"})

SECTION_HEADING = "## Rulings (machine-checked)"
BEGIN = (
    "<!-- rulings:begin -- generated from agent/rulings/*.jsonl by `worklist.py --rule`; "
    "check:ci-operator-rulings holds it byte-equal to the ledger. Never hand-edit. -->"
)
END = "<!-- rulings:end -->"
NONE_LINE = "(no ruling recorded)"

_ISO_RE = re.compile(r"^\d{4}-\d\d-\d\dT\d\d:\d\d(?::\d\d)?Z$")
_ID_RE = re.compile(r"^[0-9a-f]{8}$")


def rulings_dir(root=None):
    """`agent/rulings/`. HONOURS $WORKLIST_STORE_DIR the way wl_reggate.debt_dir does: a sibling of the store, so the one export that points a test fixture's store somewhere disposable redirects this ledger too and a suite run never appends to the operator's tree."""
    override = os.environ.get("WORKLIST_STORE_DIR")
    if override:
        return pathlib.Path(override).parent / RULINGS_DIR_NAME
    if root is None:
        root = os.environ.get("CLAUDE_PROJECT_DIR") or os.getcwd()
    return pathlib.Path(root) / "agent" / RULINGS_DIR_NAME


def rules_md_path(root=None):
    """The RULES.md the section lives in: the ledger directory's parent, so `agent/RULES.md` in the tree and a disposable copy beside a fixture's ledger."""
    return rulings_dir(root).parent / RULES_MD_NAME


def writer_slug(me):
    """The 8-character file name one writer owns, the slug wl_store.agent_session_slug mints."""
    return re.sub(r"[^A-Za-z0-9._-]", "_", str(me or "unknown"))[:8] or "unknown"


def subject_sig(subject):
    """The key a ruling and a check share: sha1 of the whitespace-collapsed subject, 16 hex characters."""
    norm = " ".join(str(subject or "").split())
    return hashlib.sha1(norm.encode("utf-8")).hexdigest()[:16]


def _now():
    return datetime.datetime.now(datetime.UTC)


def _stamp(when=None):
    return (when or _now()).strftime("%Y-%m-%dT%H:%M:%SZ")


def _parse(stamp):
    for fmt in ("%Y-%m-%dT%H:%M:%SZ", "%Y-%m-%dT%H:%MZ"):
        try:
            return datetime.datetime.strptime(str(stamp), fmt).replace(tzinfo=datetime.UTC)
        except (TypeError, ValueError):
            continue
    return None


def valid_until(stamp):
    """True for an ISO8601Z instant in the future, the only shape `--until` accepts."""
    when = _parse(stamp) if _ISO_RE.match(str(stamp or "")) else None
    return when is not None and when > _now()


def row_problem(row):
    """Why one parsed ledger row is malformed, or "" when it is well formed. The gate fails on any non-empty answer: a row nothing can read is a ruling that silently stopped binding."""
    if not isinstance(row, dict):
        return "not a JSON object"
    ev = row.get("ev")
    if ev not in ("rule", "revoke"):
        return "ev %r is neither rule nor revoke" % (ev,)
    if not _ID_RE.match(str(row.get("id") or "")):
        return "id %r is not 8 hex characters" % (row.get("id"),)
    if _parse(row.get("at")) is None:
        return "at %r is not an ISO8601Z instant" % (row.get("at"),)
    if not str(row.get("by") or "").strip():
        return "no by"
    if not str(row.get("text") or "").strip():
        return "no text"
    if ev == "rule":
        if row.get("check") not in RULABLE_CHECKS:
            return "check %r is not one of %s" % (row.get("check"), sorted(RULABLE_CHECKS))
        if not str(row.get("subject") or "").strip():
            return "no subject"
        if row.get("sig") != subject_sig(row.get("subject")):
            return "sig does not match the subject"
        if row.get("verdict") != "settled":
            return "verdict %r is not settled" % (row.get("verdict"),)
        if "until" in row and _parse(row.get("until")) is None:
            return "until %r is not an ISO8601Z instant" % (row.get("until"),)
    elif row.get("verdict") != "revoked":
        return "verdict %r is not revoked" % (row.get("verdict"),)
    return ""


def read_ledger(directory):
    """(rows, problems) over every `*.jsonl` in `directory`, sorted by (at, id) so the order is the same in every checkout. A missing directory is an empty ledger, not an error."""
    rows: list[dict] = []
    problems: list[str] = []
    directory = pathlib.Path(directory)
    if not directory.is_dir():
        return rows, problems
    for path in sorted(directory.glob("*.jsonl")):
        for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except ValueError:
                problems.append("%s:%d: not JSON" % (path.name, n))
                continue
            why = row_problem(row)
            if why:
                problems.append("%s:%d: %s" % (path.name, n, why))
                continue
            rows.append(row)
    rows.sort(key=lambda r: (str(r.get("at")), str(r.get("id"))))
    return rows, problems


def fold(rows):
    """{rule id: (rule row, revoke row or None)}, in ledger order. A revoke naming no known rule is ignored here; `read_ledger` already proved its shape."""
    out: dict[str, tuple[dict, dict | None]] = {}
    for row in rows:
        if row["ev"] == "rule":
            out.setdefault(row["id"], (row, None))
    for row in rows:
        if row["ev"] == "revoke":
            target = str(row.get("target") or "")
            if target in out and out[target][1] is None:
                out[target] = (out[target][0], row)
    return out


def live_rulings(rows, now=None):
    """The rule rows that bind right now: not revoked, and not past an `until`."""
    now = now or _now()
    live = []
    for rule, revoke in fold(rows).values():
        if revoke is not None:
            continue
        until = _parse(rule.get("until")) if rule.get("until") else None
        if until is not None and until <= now:
            continue
        live.append(rule)
    return live


def settled(root, check_key, sig):
    """The live ruling row for (check_key, sig), or None. ANY error is None: see the module docstring."""
    try:
        rows, _problems = read_ledger(rulings_dir(root))
        for rule in live_rulings(rows):
            if rule.get("check") == check_key and rule.get("sig") == sig:
                return rule
        return None
    except Exception:
        return None


def render_section(rows):
    """The generated block, markers included, from the ledger alone (never the clock)."""
    lines = [BEGIN]
    folded = fold(rows)
    if not folded:
        lines.append(NONE_LINE)
    for rule, revoke in folded.values():
        head = "- `%s` %s `%s`: %s (%s, %s%s)" % (
            rule["id"],
            rule["check"],
            " ".join(str(rule["subject"]).split()),
            " ".join(str(rule["text"]).split()),
            rule["by"],
            rule["at"],
            ", until %s" % rule["until"] if rule.get("until") else "",
        )
        if revoke is not None:
            head += " REVOKED `%s` (%s, %s): %s" % (
                revoke["id"],
                revoke["by"],
                revoke["at"],
                " ".join(str(revoke["text"]).split()),
            )
        lines.append(head)
    lines.append(END)
    return "\n".join(lines) + "\n"


def extract_section(text):
    """The generated block as it stands in RULES.md, markers included, or None when either marker is missing or they are out of order."""
    start = text.find(BEGIN)
    end = text.find(END, start + 1) if start >= 0 else -1
    if start < 0 or end < 0:
        return None
    end += len(END)
    if end < len(text) and text[end] == "\n":
        end += 1
    return text[start:end]


def splice(text, section):
    """RULES.md with the generated block replaced, or the heading and block appended when the markers are absent. Every byte outside the markers is copied through."""
    old = extract_section(text)
    if old is not None:
        return text.replace(old, section, 1)
    base = text.rstrip("\n")
    lead = "\n\n" if base else ""
    return base + lead + SECTION_HEADING + "\n\n" + section


def _atomic_write(path, text):
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=path.name, suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.replace(tmp, path)
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(tmp)
        raise


def _new_id(*parts):
    return hashlib.sha1("|".join(str(p) for p in parts).encode("utf-8")).hexdigest()[:8]


def record(root, me, row):
    """Append one row to this writer's ledger and re-render the RULES.md section, both under one flock on the ledger directory, the tempfile plus `os.replace` discipline `--state` uses. Returns the RULES.md path."""
    directory = rulings_dir(root)
    directory.mkdir(parents=True, exist_ok=True)
    target = rules_md_path(root)
    with open(directory / ".lock", "w", encoding="utf-8") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        with open(directory / ("%s.jsonl" % writer_slug(me)), "a", encoding="utf-8") as fh:
            fh.write(json.dumps(row, sort_keys=True) + "\n")
        rows, _problems = read_ledger(directory)
        current = target.read_text(encoding="utf-8") if target.is_file() else ""
        _atomic_write(target, splice(current, render_section(rows)))
    return target


def rule_row(me, check, subject, text, until=None):
    """A `rule` row, validated by `row_problem` before it is returned so a malformed one never reaches the ledger."""
    at = _stamp()
    row = {
        "ev": "rule",
        "id": _new_id(me, at, check, subject, text),
        "at": at,
        "by": writer_slug(me),
        "check": check,
        "subject": " ".join(str(subject).split()),
        "sig": subject_sig(subject),
        "verdict": "settled",
        "text": " ".join(str(text).split()),
    }
    if until:
        row["until"] = until
    return row


def revoke_row(me, target, text):
    at = _stamp()
    return {
        "ev": "revoke",
        "id": _new_id(me, at, "revoke", target, text),
        "at": at,
        "by": writer_slug(me),
        "target": target,
        "verdict": "revoked",
        "text": " ".join(str(text).split()),
    }
