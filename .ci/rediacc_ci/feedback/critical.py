"""Stage 4 of feedback triage: the R8 critical triggers and their worklist deferrals (PLAN-rdc-feedback R8, D5).

A critical report goes to the operator as a worklist `[?]` with a DEFAULT and a 6 h window, after which the default executes. The window is a `NOT-BEFORE:` six hours past the filing instant: the Stop hook runs a DEFAULT only once the ordinary window has closed AND the hold has passed (wl_checks `defer-expired`), so the hold is what stretches the window to 6 h.

THE TRIGGERS, each computed from the export aggregates, the Stage 2 outcome and the reproduction result:

  (a) 5 or more distinct reporters, or 3 or more orgs, within 24 h. The account's export carries `distinctReporters24h` / `distinctOrgs24h` (the owners and orgs of member reports seen in the last 24 h; `rediacc_ci.feedback.client.export` refuses a half or non-integer pair), and those counts decide. An account deployed before them sends only totals, and then the window is a fingerprint whose first and last report both fall inside the last 24 h.
  (b) a core path broken (install, update, login, repo up/down, backup or restore) that the reproduction confirmed, with no workaround found.
  (c) the AI cannot decide: the Stage 2 classifier quarantined the report (it flagged it suspicious, or its reply broke the schema), or a clean reproduction disagrees with a high-count report. A Stage 1 deterministic quarantine is NOT a trigger by itself: those rules fire on any URL, `curl` or backtick span, so most of their hits are ordinary error text, and a widespread one still reaches the operator through (a).
  (d) unresolved past 14 days with occurrences still growing (a report in the last 24 h).
  (e) docs contradict code, AI-confirmed: a `docs` report the reproduction confirmed.

Not critical by itself (R8): a regression, a release spike, a contract change, an enterprise reporter. No rule here reads a version spread or an owner kind.

Nothing here puts a report field into the worklist: an item names the short fingerprint, the trigger, the counts and the category only.
"""

from __future__ import annotations

import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import TYPE_CHECKING, Any

from rediacc_ci import paths
from rediacc_ci.feedback.classify import CORE_CATEGORIES

if TYPE_CHECKING:
    from collections.abc import Callable, Mapping, Sequence
    from pathlib import Path

    from rediacc_ci.feedback.classify import Outcome

REPORTERS_24H = 5
ORGS_24H = 3
DAY = timedelta(hours=24)
STALE_AFTER = timedelta(days=14)
WINDOW = timedelta(hours=6)
# "high-count" for (c): a clean reproduction against this many reporters or occurrences disagrees with the field.
HIGH_REPORTERS = 3
HIGH_OCCURRENCES = 10
RESOLVED = frozenset(("fixed", "rejected"))
REPRO_RESULTS = ("reproduced", "clean", "inconclusive")
SHORT_FP = 12

DEFAULT_PLAN = "plan and fix now: write the PLAN-feedback plan, promote it and land the fix"
DEFAULT_KEEP = "keep quarantined: no reproduction, the report stays quarantined"
DEFAULT_RAISE = "raise the linked plan's priority to P1"
DEFAULTS = {
    "a": DEFAULT_PLAN,
    "b": DEFAULT_PLAN,
    "c": DEFAULT_KEEP,
    "d": DEFAULT_RAISE,
    "e": DEFAULT_PLAN,
}
TITLES = {
    "a": "many reporters within 24 h",
    "b": "core path broken, no workaround",
    "c": "the AI cannot decide",
    "d": "unresolved past 14 days and still growing",
    "e": "docs contradict code",
}

WORKLIST_REL = (".claude", "hooks", "stop", "worklist.py")
ADDED_ID = re.compile(r"^added #([0-9a-f]+):", re.MULTILINE)
STATE_PARTS = (".ci", "cache", "feedback", "critical.json")
STATE_VERSION = 1


@dataclass(frozen=True)
class Trigger:
    code: str
    fingerprint: str
    evidence: str

    @property
    def default(self) -> str:
        return DEFAULTS[self.code]

    @property
    def key(self) -> str:
        return "%s:%s" % (self.fingerprint, self.code)


def _instant(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _int(item: Mapping[str, Any], key: str) -> int:
    value = item.get(key)
    return value if isinstance(value, int) and not isinstance(value, bool) else 0


def window_counts(item: Mapping[str, Any], now: datetime) -> tuple[int, int]:
    """(distinct reporters, distinct orgs) inside the last 24 h, per the (a) reading in the module docstring."""
    if "distinctReporters24h" in item and "distinctOrgs24h" in item:
        return _int(item, "distinctReporters24h"), _int(item, "distinctOrgs24h")
    first, last = _instant(item.get("firstSeenAt")), _instant(item.get("lastSeenAt"))
    if first is None or last is None or first < now - DAY or last > now + DAY:
        return 0, 0
    return _int(item, "distinctReporters"), _int(item, "distinctOrgs")


def evaluate(
    item: Mapping[str, Any],
    now: datetime,
    outcome: Outcome | None = None,
    repro: str | None = None,
    workaround: bool = False,
    category: str | None = None,
) -> list[Trigger]:
    """Every R8 trigger the item meets, in (a)..(e) order. `category` is the classifier's (or the export's) category; `repro` one of REPRO_RESULTS or None when no reproduction ran."""
    if repro is not None and repro not in REPRO_RESULTS:
        msg = "repro %r is not one of %s" % (repro, ", ".join(REPRO_RESULTS))
        raise ValueError(msg)
    fp = item["fingerprint"]
    short = fp[:SHORT_FP]
    cls = outcome.classification if outcome is not None else None
    category = category or (cls.category if cls else None) or item.get("category") or "other"
    reporters = _int(item, "distinctReporters")
    occurrences = _int(item, "occurrenceCount")
    out: list[Trigger] = []

    r24, o24 = window_counts(item, now)
    if r24 >= REPORTERS_24H or o24 >= ORGS_24H:
        out.append(
            Trigger("a", fp, "%s: %d reporter(s) and %d org(s) within 24 h" % (short, r24, o24))
        )

    core = (cls.core if cls else False) or category in CORE_CATEGORIES
    if repro == "reproduced" and core and not workaround:
        out.append(Trigger("b", fp, "%s: %s reproduced, no workaround found" % (short, category)))

    if outcome is not None and outcome.quarantined:
        why = (
            "classifier flagged it suspicious"
            if outcome.suspicious
            else "classifier reply broke the schema"
        )
        out.append(Trigger("c", fp, "%s: %s" % (short, why)))
    elif repro == "clean" and (reporters >= HIGH_REPORTERS or occurrences >= HIGH_OCCURRENCES):
        out.append(
            Trigger(
                "c",
                fp,
                "%s: clean reproduction against %d reporter(s) and %d occurrence(s)"
                % (short, reporters, occurrences),
            )
        )

    first, last = _instant(item.get("firstSeenAt")), _instant(item.get("lastSeenAt"))
    if (
        item.get("status") not in RESOLVED
        and first is not None
        and last is not None
        and first <= now - STALE_AFTER
        and last >= now - DAY
    ):
        age = (now - first).days
        out.append(Trigger("d", fp, "%s: open %d day(s), last report within 24 h" % (short, age)))

    if repro == "reproduced" and (category == "docs" or item.get("kind") == "docs"):
        out.append(Trigger("e", fp, "%s: docs report confirmed against the code" % short))
    return out


# ---- the worklist deferral -----------------------------------------------------------------------


def stamp(when: datetime) -> str:
    return when.astimezone(UTC).strftime("%Y-%m-%dT%H:%MZ")


def item_text(trigger: Trigger, me: str) -> str:
    return "(%s) feedback critical R8 (%s) %s: %s" % (
        me,
        trigger.code,
        TITLES[trigger.code],
        trigger.evidence,
    )


def defer_text(trigger: Trigger, now: datetime) -> str:
    """The deferral: the question, WHY, HOW, the DEFAULT and a NOT-BEFORE six hours out."""
    return (
        "Feedback fingerprint %s met R8 trigger (%s), %s: act on the default? "
        "WHY: PLAN-rdc-feedback R8 routes a critical report to the operator with a 6 h window "
        "before the triage agent acts on it; evidence %s. "
        "HOW: an operator answer to this item, or the window closing at the NOT-BEFORE instant. "
        "DEFAULT: %s. NOT-BEFORE:%s"
        % (
            trigger.fingerprint[:SHORT_FP],
            trigger.code,
            TITLES[trigger.code],
            trigger.evidence,
            trigger.default,
            stamp(now + WINDOW),
        )
    )


def worklist_cmd() -> list[str]:
    return [sys.executable, str(paths.from_root(*WORKLIST_REL))]


def add_argv(trigger: Trigger, me: str) -> list[str]:
    return [*worklist_cmd(), "--add", me, item_text(trigger, me)]


def defer_argv(trigger: Trigger, me: str, item_id: str, now: datetime) -> list[str]:
    return [*worklist_cmd(), "--defer", me, item_id, defer_text(trigger, now)]


def _capture(argv: Sequence[str]) -> tuple[int, str]:
    done = subprocess.run(list(argv), capture_output=True, text=True, check=False)
    return done.returncode, done.stdout


@dataclass
class Filed:
    trigger: Trigger
    item_id: str | None
    ok: bool
    note: str


def file_triggers(
    triggers: Sequence[Trigger],
    me: str,
    now: datetime,
    capture: Callable[[Sequence[str]], tuple[int, str]] = _capture,
) -> list[Filed]:
    """Each trigger as a worklist item (`--add`) deferred with its DEFAULT and window (`--defer`). A refused step is reported, never retried: a Filed with an `item_id` names an item that exists, so the caller records it as filed even when its `--defer` was refused."""
    out: list[Filed] = []
    for trigger in triggers:
        rc, stdout = capture(add_argv(trigger, me))
        match = ADDED_ID.search(stdout or "")
        if rc != 0 or match is None:
            out.append(Filed(trigger, None, ok=False, note="worklist --add exited %d" % rc))
            continue
        item_id = match.group(1)
        rc, _ = capture(defer_argv(trigger, me, item_id, now))
        out.append(
            Filed(
                trigger,
                item_id,
                ok=rc == 0,
                note="deferred"
                if rc == 0
                else "worklist --defer exited %d; the item is open without its deferral" % rc,
            )
        )
    return out


# ---- the filed-trigger state ---------------------------------------------------------------------


def state_path() -> Path:
    return paths.from_root(*STATE_PARTS)


def read_state(path: Path) -> dict[str, str]:
    """{`<fingerprint>:<code>`: filed-at} for every trigger already filed; an absent or foreign file is empty (a re-file is a duplicate question, never a lost one)."""
    try:
        doc = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    filed = (
        doc.get("filed") if isinstance(doc, dict) and doc.get("version") == STATE_VERSION else None
    )
    return {str(k): str(v) for k, v in filed.items()} if isinstance(filed, dict) else {}


def write_state(path: Path, filed: Mapping[str, str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(
        json.dumps({"version": STATE_VERSION, "filed": dict(filed)}, indent=2, sort_keys=True)
        + "\n",
        encoding="utf-8",
    )
    tmp.replace(path)


def unfiled(triggers: Sequence[Trigger], state: Mapping[str, str]) -> list[Trigger]:
    return [t for t in triggers if t.key not in state]
