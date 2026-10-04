#!/usr/bin/env python3
"""The Stop hook's view of the trapguard ledgers: rule errors (blocking) and retirement candidates (advisory).

    python3 .claude/hooks/stop/wl_trapfires.py --trap-confirm <rule>   record a confirmed true positive
    python3 .claude/hooks/stop/wl_trapfires.py --errors-seen           move a read error log aside

THE ERROR LOG BLOCKS (plan PLAN-trap-enforcement.md section 4.3.4). `.claude/hooks/trapguard/dispatch.py` fails open per rule, which is correct, and appends `{ts, rule, exc_type}` to `errors.jsonl` when a rule raises. Failing open is right; failing open QUIETLY is the trap the trapguard surface exists to close, so a non-empty log is an `always` violation (`trapguard-errors`) until it is read, the rule is fixed, and the log is moved aside with `--errors-seen`.

THE FIRE LOG ADVISES (section 5, defence 3: "a measured hit rate, or the rule is retired"). Every note the dispatcher shows appends `{rule, ts, session}` to `fires.jsonl`. A rule with more than RETIRE_FIRES fires and no row in `confirmed.jsonl` is a retirement candidate: it speaks often, and nobody has ever said it was right. The report names it; it never removes anything, because a rule that fires on real traps every time is also a rule with many fires.

THE MESSAGES LIVE HERE, not in worklist_messages.py, so the producer and its text change together.
"""

import datetime
import json
import os
import pathlib
import sys
from collections import Counter

# Section 5: "A rule that has fired more than RETIRE_FIRES = 40 times without the operator having confirmed a true positive is a candidate for retirement."
RETIRE_FIRES = 40

V_TRAPGUARD_ERRORS = """TRAPGUARD RULE ERRORS: %(n)d logged in %(path)s.

%(rows)s

A trapguard rule raised, so it was skipped and stayed silent on that call.
Failing open keeps the turn alive; this block keeps the failure visible.
  1. read the log and reproduce: the rule ids map to `rule_<id with _>` in
     .claude/hooks/trapguard/dispatch.py
  2. fix the rule and add a case to .claude/rediacc_hooks/tests/test_hooks_trapguard.py
  3. move the read log aside:
       python3 .claude/hooks/stop/wl_trapfires.py --errors-seen"""

N_TRAPFIRES_RETIRE = """trapguard retirement candidates (more than %(cap)d fires, no confirmed true positive):
%(rows)s
A rule that speaks this often unconfirmed may be teaching sessions to skim it.
Review its recent fires; if one was a real catch, record it:
    python3 .claude/hooks/stop/wl_trapfires.py --trap-confirm <rule>
otherwise narrow or retire the rule in .claude/hooks/trapguard/dispatch.py."""


def state_dir():
    """The same directory the dispatcher writes: `TRAPGUARD_DIR`, else `~/.claude/trapguard`."""
    return pathlib.Path(
        os.environ.get("TRAPGUARD_DIR") or (pathlib.Path.home() / ".claude" / "trapguard")
    )


def read_jsonl(path):
    """The rows of a JSON-lines ledger. A missing file is no rows; an unparseable line is kept as `{}` so it still counts."""
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    rows = []
    for line in text.splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except ValueError:
            row = {}
        rows.append(row if isinstance(row, dict) else {})
    return rows


def errors_violation(base=None):
    """The `trapguard-errors` violation text, or "" when the error log is empty or absent."""
    path = (base or state_dir()) / "errors.jsonl"
    rows = read_jsonl(path)
    if not rows:
        return ""
    counts = Counter((str(r.get("rule") or "?"), str(r.get("exc_type") or "?")) for r in rows)
    last = max((str(r.get("ts") or "") for r in rows), default="")
    lines = ["  %-32s %-20s x%d" % (rule, exc, n) for (rule, exc), n in counts.most_common(8)]
    if last:
        lines.append("  last at %s" % last)
    return V_TRAPGUARD_ERRORS % {"n": len(rows), "path": path, "rows": "\n".join(lines)}


def retire_candidates(base=None):
    """[(rule, fires)] for rules over RETIRE_FIRES with no confirmed true positive, most fires first."""
    base = base or state_dir()
    fires = Counter(str(r.get("rule") or "") for r in read_jsonl(base / "fires.jsonl"))
    fires.pop("", None)
    confirmed = {str(r.get("rule") or "") for r in read_jsonl(base / "confirmed.jsonl")}
    return [
        (rule, n) for rule, n in fires.most_common() if n > RETIRE_FIRES and rule not in confirmed
    ]


def retire_note(base=None):
    """The advisory text, or "" when no rule is a candidate."""
    cands = retire_candidates(base)
    if not cands:
        return ""
    rows = "\n".join("  %-32s %d fires" % (rule, n) for rule, n in cands)
    return N_TRAPFIRES_RETIRE % {"cap": RETIRE_FIRES, "rows": rows}


def _now():
    return datetime.datetime.now(datetime.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def confirm(rule, base=None):
    """Append one confirmed true positive for `rule` (append-only: a confirmation is a fact about the past)."""
    base = base or state_dir()
    base.mkdir(parents=True, exist_ok=True)
    with (base / "confirmed.jsonl").open("a", encoding="utf-8") as fh:
        fh.write(json.dumps({"rule": rule, "ts": _now()}, sort_keys=True) + "\n")
    return base / "confirmed.jsonl"


def errors_seen(base=None):
    """Move a read error log aside, keeping it. Returns the new path, or None when there was nothing to move."""
    base = base or state_dir()
    path = base / "errors.jsonl"
    if not path.exists():
        return None
    dest = base / ("errors-seen-%s.jsonl" % _now().replace(":", ""))
    path.rename(dest)
    return dest


def main(argv):
    if len(argv) == 2 and argv[0] == "--trap-confirm" and argv[1].strip():
        print("recorded: %s in %s" % (argv[1], confirm(argv[1].strip())))
        return 0
    if argv == ["--errors-seen"]:
        dest = errors_seen()
        print(
            "moved to %s" % dest if dest else "no error log at %s" % (state_dir() / "errors.jsonl")
        )
        return 0
    print(__doc__.split("\n\n", 1)[0], file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
