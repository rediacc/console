"""The `feedback-triage-due` Stop advisory (agent/plans/PLAN-rdc-feedback.md D5 "When", box T4).

The triage run (`rediacc_ci.feedback.triage run`) is due on either of two facts, both read from local files so a stop spends no network:

  1. the newest ci:quick receipt (`.ci/cache/prepush-receipt.json`) is red and no triage run has happened since it finished;
  2. the newest run the cursor records (`.ci/cache/feedback/last-run.json`, the `ranAt` of every region row, written by `rediacc_ci.feedback.client.write_cursor`) is older than STALE_H hours.

An absent cursor is no run recorded, so only fact 1 can speak; a cursor the triage module would refuse is named as unreadable rather than read as fresh. A tree without the feedback package has no command to name and is silent.
"""

from __future__ import annotations

import datetime
import json
import pathlib

COMMAND = "PYTHONPATH=.ci python3 -m rediacc_ci.feedback.triage run"
STALE_H = 24
RECEIPT_REL = (".ci", "cache", "prepush-receipt.json")
CURSOR_REL = (".ci", "cache", "feedback", "last-run.json")
PACKAGE_REL = (".ci", "rediacc_ci", "feedback", "triage.py")
CURSOR_VERSION = 1


def _epoch(stamp):
    try:
        moment = datetime.datetime.fromisoformat(str(stamp))
    except ValueError:
        return None
    if moment.tzinfo is None:
        moment = moment.replace(tzinfo=datetime.UTC)
    return moment.timestamp()


def _read_json(path):
    """(document, present): an absent file is (None, False); an unreadable one (None, True)."""
    try:
        text = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None, False
    except OSError:
        return None, True
    try:
        return json.loads(text), True
    except ValueError:
        return None, True


def last_run(root):
    """(epoch of the newest `ranAt`, or None; True when the cursor exists but cannot be read as a version 1 cursor)."""
    doc, present = _read_json(pathlib.Path(root).joinpath(*CURSOR_REL))
    if not present:
        return None, False
    regions = doc.get("regions") if isinstance(doc, dict) else None
    if not isinstance(regions, dict) or doc.get("version") != CURSOR_VERSION:
        return None, True
    stamps = [_epoch(row.get("ranAt")) for row in regions.values() if isinstance(row, dict)]
    stamps = [s for s in stamps if s is not None]
    return (max(stamps) if stamps else None), False


def red_receipt(root):
    """(short head, finished epoch) when the newest ci:quick receipt is red, else None."""
    doc, _present = _read_json(pathlib.Path(root).joinpath(*RECEIPT_REL))
    if not isinstance(doc, dict) or doc.get("exitCode") in (0, None):
        return None
    finished = _epoch(doc.get("finishedAt"))
    if finished is None:
        return None
    return (str(doc.get("head") or "")[:8] or "?"), finished


def due(root, now=None):
    """The advisory text, or None."""
    root = pathlib.Path(root)
    if not root.joinpath(*PACKAGE_REL).is_file():
        return None
    now_epoch = (now or datetime.datetime.now(datetime.UTC)).timestamp()
    ran, unreadable = last_run(root)
    reasons = []
    red = red_receipt(root)
    if red is not None and (ran is None or ran < red[1]):
        reasons.append(
            "the newest ci:quick receipt (%s) is red and no triage run followed it" % red[0]
        )
    if unreadable:
        reasons.append("the cursor %s is unreadable" % "/".join(CURSOR_REL))
    elif ran is not None and now_epoch - ran > STALE_H * 3600:
        reasons.append(
            "the last triage run was %d h ago (over %d h)" % ((now_epoch - ran) // 3600, STALE_H)
        )
    if not reasons:
        return None
    return "FEEDBACK TRIAGE DUE: %s. Run `%s` (credentials through `bws_env exec`)." % (
        "; ".join(reasons),
        COMMAND,
    )
