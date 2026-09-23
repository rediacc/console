#!/usr/bin/env python3
"""Controls for wl_deflect: the mechanical dismissed-finding check.

PLAN-deflected-finding-check.md's own boxes: phrase-family MUST_HIT/MUST_MISS pairs (verdict shape, finding-noun shape, harmless-noun exclusion, baseline exemption) using this session's own real quoted lines as fixtures, plus corroboration-window pairs using a synthetic transcript fixture, plus a documented false-negative control.

Run: python3 .claude/hooks/stop/test-deflect.py
"""

from __future__ import annotations

import json
import pathlib
import sys
import tempfile

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

import wl_deflect as D


class Tally:
    count = 0
    fails = 0


def ck(name, cond, detail=""):
    Tally.count += 1
    if cond:
        print("  PASS  %s" % name)
    else:
        Tally.fails += 1
        print("  FAIL  %s%s" % (name, ("  -- " + str(detail)) if detail else ""))


def _rec(rtype, text=None, tool_use=None, tool_result=False):
    content = []
    if text is not None:
        content.append({"type": "text", "text": text})
    if tool_use is not None:
        content.append({"type": "tool_use", "name": tool_use[0], "input": tool_use[1]})
    if tool_result:
        content.append({"type": "tool_result", "content": "ok"})
    return {"type": rtype, "message": {"content": content}}


def _write_transcript(path, records):
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")


print("== 1. PHRASE FAMILY: verdict shape ==")
# MUST HIT: the real quoted line from this session's own transcript.
REAL_LINE = (
    "Confirmed pre-existing and unrelated (untouched file, no uncommitted changes, "
    "environment-dependent identity-cache check)."
)
ck("MUST HIT: the real quoted dismissal fires", bool(D.deflected_findings(REAL_LINE)), REAL_LINE)
ck(
    "MUST HIT: 'this is ... not caused by' fires",
    bool(D.deflected_findings("this is not caused by anything I touched")),
)
ck(
    "MUST MISS: plain unrelated prose with no verdict shape",
    not D.deflected_findings("the weather is unrelated to this task"),
)

print("== 2. PHRASE FAMILY: finding-noun-adjacent shape ==")
ck(
    "MUST HIT: finding-noun before the attribution word",
    bool(D.deflected_findings("that regression is pre-existing, not something I broke")),
)
ck(
    "MUST HIT: attribution word before the finding-noun (either order)",
    bool(D.deflected_findings("this is unrelated to the bug we found")),
)
ck(
    "MUST MISS: finding-noun far outside the 60-char window",
    not D.deflected_findings(
        "there was a regression years ago in a totally different codebase, and separately, "
        "the CI vendor changed their pricing page, which is unrelated to any of that history"
    ),
)

print("== 3. HARMLESS-NOUN EXCLUSION (measured over-fire cases from this session) ==")
for text, label in (
    ("confirmed pre-existing docstrings need no fix", "docstrings"),
    ("this is unrelated content, nothing to see here", "content"),
    ("confirmed pre-existing, tests pass", "tests pass"),
    ("this is unrelated comments, ignore them", "comment"),
    ("confirmed pre-existing bump, nothing more", "bump"),
):
    ck("MUST MISS: harmless noun (%s)" % label, not D.deflected_findings(text), text)

print("== 4. BASELINE/RATCHET EXEMPTION ==")
for text, label in (
    ("this is pre-existing debt already in the baseline", "baseline"),
    ("confirmed pre-existing, already ratcheted", "ratcheted"),
    ("this is unrelated to the floor we set", "floor"),
    ("confirmed pre-existing, grandfathered in", "grandfathered"),
):
    ck("MUST MISS: baseline-exempt (%s)" % label, not D.deflected_findings(text), text)

print("== 5. CORROBORATION: commands and prose ==")
ck(
    "a worklist --add command corroborates",
    D.corroborated(["worklist.py --add d778be9d 'real work'"], REAL_LINE),
)
ck(
    "a worklist --defer command corroborates",
    D.corroborated(["worklist.py --defer d778be9d abc123 'q DEFAULT: x'"], REAL_LINE),
)
ck("a bare #id citation in prose corroborates", D.corroborated([], REAL_LINE + " see #a1b2c3d4"))
ck(
    "a door: token in prose corroborates",
    D.corroborated([], REAL_LINE + " door:operator-only"),
)
ck("no corroboration at all", not D.corroborated([], REAL_LINE))
ck(
    "an unrelated Bash command does not corroborate",
    not D.corroborated(["ls -la"], REAL_LINE),
)

print("== 6. THE DOCUMENTED FALSE-NEGATIVE CONTROL ==")
# An unrelated worklist --add present in the SAME turn cannot be told apart from real corroboration by a whole-turn window. Asserted as a KNOWN, ACCEPTED tradeoff, not a silent gap.
_unrelated_add = "worklist.py --add d778be9d 'totally unrelated other task'"
ck(
    "KNOWN GAP: an unrelated --add in the same turn is read as corroboration",
    D.corroborated([_unrelated_add], REAL_LINE),
    "documented tradeoff, not a bug: the whole-turn window cannot distinguish this from real corroboration",
)

print("== 7. END-TO-END check() over a synthetic transcript ==")
with tempfile.TemporaryDirectory() as tmp:
    root = pathlib.Path(tmp)
    worklist = root / "agent" / "worklist" / "test8be9d.jsonl"
    worklist.parent.mkdir(parents=True)
    session_id = "test8be9"

    # 7a. Dismissal with NO corroboration anywhere in the turn -> fires.
    t1 = root / "t1.jsonl"
    _write_transcript(
        t1,
        [
            _rec("user", text="do the thing", tool_result=False),
            _rec("assistant", text=REAL_LINE),
        ],
    )
    fired, matched = D.check(worklist, session_id, str(t1))
    ck("7a: fires with no corroboration", fired, matched)
    ck("7a: the matched text is returned", bool(matched))

    # 7b. Same claim set, SAME transcript file, run again -> settled, silent.
    fired2, _ = D.check(worklist, session_id, str(t1))
    ck("7b: settled on the second call for the identical turn", not fired2)

    # 7c. Dismissal WITH a worklist --add in the same turn -> silent (should-not-block).
    t2 = root / "t2.jsonl"
    _write_transcript(
        t2,
        [
            _rec("user", text="do another thing"),
            _rec("assistant", text=REAL_LINE + " Different wording so the signature differs."),
            _rec(
                "assistant",
                tool_use=("Bash", {"command": "worklist.py --add d778be9d 'tracked properly'"}),
            ),
        ],
    )
    fired3, _ = D.check(worklist, session_id, str(t2))
    ck("7c: should-not-block, corroborated by a later Bash call in the same turn", not fired3)

    # 7d. Turn-boundary reset: dismissal in one turn, a genuine operator message, new turn with unrelated text -- the dismissal must not leak forward and fire on the new turn.
    t3 = root / "t3.jsonl"
    _write_transcript(
        t3,
        [
            _rec("assistant", text=REAL_LINE + " Yet another distinct wording for this fixture."),
            _rec("user", text="thanks, next please"),  # genuine operator turn, no tool_result
            _rec("assistant", text="starting the next task now"),
        ],
    )
    fired4, matched4 = D.check(worklist, session_id, str(t3))
    ck(
        "7d: turn-boundary reset -- the dismissal does not leak into the new turn",
        not fired4,
        matched4,
    )

print()
if Tally.count < 25:
    print("VACUOUS: only %d checks ran; this suite has 25+" % Tally.count)
    Tally.fails += 1
print("%d checks, %d failures" % (Tally.count, Tally.fails))
sys.exit(1 if Tally.fails else 0)
