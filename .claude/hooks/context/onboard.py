#!/usr/bin/env python3
"""First touch of a context epoch: say what this session already owns.

WHY THIS EXISTS. The Stop hook already tells a session what to do -- but only once it tries to stop, which is after the work. A fresh session, and above all a POST-COMPACTION session, arrives with no memory of the store and learns the rules by hitting the wall: it finishes a job, writes a `## Remaining` section from memory, and the hook refuses it.
The operator's words were that these sessions "hit the wall and repeat the same mistakes like completing the job without updating the remainings by invoking stop hook's commands with specific arguments".

WHERE IT FIRES, and both alternatives were measured rather than argued (see agent/plans/PLAN-session-onboarding-marker.md section 4):

  * NOT SessionStart. Its output lands behind a large system prompt and two
    other blocks, and this repo has already concluded a wall of text there is
    skimmed.
  * NOT the first Edit. Session 74de73ca's first Edit was at +600 minutes and
    its first stop refusal at +17.8; its third tool call, at +1.1 minutes, was a
    Bash heredoc writing a repo file. An Edit matcher delivers ten hours late.
  * The first TOOL CALL of the epoch. Across four working sessions those landed
    at +0.3, +3.0, +0.1 and +0.3 minutes -- before every observed refusal.

THE ANTI-NAG RULE IS THE LOAD-BEARING PART. In the corpus 38 of 41 sessions never edited a file and used 6-39 tool calls each. An unconditional first-tool-call notice would have fired on all 38 with nothing to say, and a notice that is noise 38 times out of 41 is a notice nobody reads on the other three. So:

  arm (a)  the session OWNS open items -> speak at tool call #1.
  arm (b)  it owns nothing -> stay silent until it edits a file, then speak once.

Never both, at most one emission per epoch.

SAFETY. This is a PostToolUse hook, so it must never break a tool call: every path exits 0, every exception is swallowed and written to state/errors.log, and stdout stays empty unless there is genuinely something to say.
"""

import contextlib
import json
import os
import subprocess
import sys
import time
from datetime import UTC, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from typing import Any

import ctx_budget as B

# One compaction fires SessionStart AND PostCompact. Re-arming twice would reset the machine and emit twice, so an arm inside this window is a no-op.
ARM_DEBOUNCE_S = 120
EDIT_TOOLS = {"Edit", "Write", "NotebookEdit", "MultiEdit"}


def marker_file(session_id):
    """Its OWN file, deliberately not a key in the band state.

    band-notice.py load/saves that file on every tool call. Two hooks on one event may run in parallel, and a last-writer-wins clobber would silently lose either this marker or the band ladder -- a failure that looks like "the notice just didn't fire".
    """
    return B.state_dir() / ("%s-onboard.json" % B.session_slug(session_id))


def load_marker(session_id):
    try:
        return json.loads(marker_file(session_id).read_text(encoding="utf-8"))
    except Exception:  # noqa: BLE001 -- absent or corrupt both mean "not armed"
        return {}


def save_marker(session_id, data):
    f = marker_file(session_id)
    tmp = f.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, sort_keys=True), encoding="utf-8")
    os.replace(tmp, f)


def current_epoch(session_id):
    """Read-only peek at the band state's epoch counter.

    THE ASYMMETRY THIS EXISTS FOR: an in-place compaction can fire NEITHER SessionStart nor PostCompact. It still moves the epoch, through the usage-drop backstop in band-notice.py -- the only thing in the tree that sees that case.
    So a marker whose recorded epoch differs from the current one re-arms itself, and that mismatch is how this marker learns about a compaction no hook saw.
    """
    try:
        return int(B.load_state(session_id).get("epoch", 0))
    except Exception:  # noqa: BLE001
        return 0


def my_open_items(session_id):
    """(rows, count) for THIS session's open slice, or ([], None) if unknown.

    None is not zero. A worklist that cannot be run must not read as "owns nothing" -- that is arm (b)'s condition, and firing it on a broken store would deliver the wrong notice with confidence.
    """
    hook = Path(__file__).resolve().parents[1] / "stop" / "worklist.py"
    if not hook.is_file():
        return [], None
    try:
        r = subprocess.run(
            [sys.executable, str(hook), "--list", "--open", str(session_id)[:8]],
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
            # A non-zero exit is DATA here, not an error: --list --open exits 1 on an EMPTY slice, which is a real answer and not a failure.
            check=False,
        )
    except Exception:  # noqa: BLE001
        return [], None
    rows = [ln for ln in r.stdout.splitlines() if ln.strip().startswith("- [")]
    if rows:
        return rows, len(rows)
    # EXIT CODE ALONE CANNOT ANSWER THIS, and reading it as if it could was a real bug here: `--list --open <session-with-nothing>` exits 1, so a plain
    # `returncode != 0 -> unknown` collapsed "owns nothing" into "cannot say"
    # and arm (b) could never fire. The empty slice announces itself in words, so key on those; anything else genuinely is unknown.
    blob = (r.stdout or "") + (r.stderr or "")
    if "no actionable items" in blob or "nothing open" in blob:
        return [], 0
    return [], None


def text_owns(rows, me, store):
    verbs = (
        "  worklist.py --tick %s <id> '<evidence>'   close it; evidence is mandatory\n"
        "  worklist.py --update %s <id> <text>       progress; resets the liveness ladder\n"
        "  worklist.py --defer %s <id> <q... DEFAULT: <action>>\n" % (me, me, me)
    )
    return (
        "This session already owns %d open worklist item(s). They are in the store at\n"
        "%s, not in this context, and they survive a restart and a compaction.\n\n"
        "%s\n"
        "The Stop hook compares these rows against the last `## Remaining` section and\n"
        "refuses the turn while any remains open, so write that section FROM THIS LIST\n"
        "rather than from memory. The prefix below is already this session's own -- a\n"
        "wrong identity argument is the most common error and the identity check refuses it.\n\n"
        "%s" % (len(rows), store, "\n".join(rows[:12]), verbs)
    )


def text_fresh(me):
    return (
        "This session owns 0 worklist items, and a file has just been edited.\n"
        "Findings are part of the deliverable here: track one before fixing it, so it\n"
        "survives a compaction and so the Stop hook can hold the turn open for it.\n\n"
        "  worklist.py --add %s <text...>            prints its #id\n"
        "  worklist.py --tick %s <id> '<evidence>'   evidence is MANDATORY and is\n"
        "        checked: a sha, a run id, a file:line that resolves, an exit code or\n"
        "        a URL. A tick without one is refused.\n\n"
        "Measured on this repo: 38 of 41 sessions never edited a file, which is why\n"
        "this notice waited for that edit rather than firing on tool call #1." % (me, me)
    )


def emit(text):
    json.dump(
        {"hookSpecificOutput": {"hookEventName": "PostToolUse", "additionalContext": text}},
        sys.stdout,
    )
    sys.stdout.write("\n")


def arm(session_id):
    """SessionStart / PostCompact. epoch is written as null ON PURPOSE.

    At PostCompact the registered hooks may run in parallel, so this cannot know whether the epoch counter has been bumped yet, and reading it here would be a race. The next tool call adopts whatever epoch it sees, in a single-writer context.
    """
    m = load_marker(session_id)
    now = time.time()
    if (
        m.get("state") in ("armed", "await-edit")
        and now - float(m.get("armed_at", 0)) < ARM_DEBOUNCE_S
    ):
        return  # one compaction fires both hooks; this is the same arming
    save_marker(session_id, {"state": "armed", "epoch": None, "armed_at": now})


# ---- the audit (plan section 5). READ-ONLY, and never registered as a hook. ----
#
# WHAT IT IS FOR. The notice was added on the claim that sessions are refused at a stop before they have ever written to the store. That claim was MEASURED before the change (three of four sessions in the 2026-09-03 cohort, one of them editing files for 19h37m without recording a single item), and a claim measured once and never again is a claim that quietly stops being true.
# This recomputes it from artifacts nobody edits by hand.
#
# THE HEADLINE IS refusal-before-write. The SILENCE RATE beside it should be HIGH: 38 of 41 sessions in the corpus never edited a file, so a notice that speaks to most of the cohort is speaking to sessions with nothing to say, which is the failure arm (b) exists to prevent.

# The substring a delivered notice leaves in a transcript. The TRANSCRIPT is the only durable source: the marker under state/ is swept after 24 hours, so an audit that trusted the marker alone would report a silent cohort the day after every run.
#
# Both live wordings are covered by design. The notice was rewritten out of the second person on 2026-09-08, so a mark taken from the current text alone reads every earlier delivery as silence -- the same false improvement the compaction floor below exists to prevent.
# `notice_marks_hold()` is the control that keeps this honest: it greps the LIVE text and refuses to run the audit when neither arm carries a mark any more.
NOTICE_MARKS = ("open worklist item", "0 worklist items")

AUDIT_USAGE = "onboard.py --audit [--json] [--session <sid-or-prefix>]"


def notice_marks_hold():
    """Do the marks the audit greps for still appear in the text it greps for?

    A gate on the audit itself. Reword the notice without touching NOTICE_MARKS and every delivery becomes invisible, the silence rate goes to 100%, and the numbers look like a notice nobody needed. That failure is silent and green, so it is checked before a single transcript is opened.
    """
    live = (
        ("arm (a)", text_owns(["- [ ] #abcdef01 something"], "0badcafe", "/dev/null")),
        ("arm (b)", text_fresh("0badcafe")),
    )
    for arm_name, body in live:
        if not any(mark in body for mark in NOTICE_MARKS):
            sys.stderr.write(
                "onboard --audit: the %s notice carries none of NOTICE_MARKS (%s), so every "
                "delivery would be counted as SILENCE. Update NOTICE_MARKS beside the wording "
                "in %s.\n" % (arm_name, ", ".join(NOTICE_MARKS), __file__)
            )
            return False
    return True


def when(stamp):
    """An ISO-8601 stamp as a datetime, or None.

    Two spellings are in play and both arrive here: a transcript stamps milliseconds and a Z, the event log stamps whole seconds and a Z.
    """
    if not stamp:
        return None
    try:
        return datetime.fromisoformat(str(stamp))
    except (ValueError, TypeError):
        return None


def mins(a, b):
    """Minutes from `a` to `b`, or None when either end is missing."""
    lo, hi = when(a), when(b)
    if lo is None or hi is None:
        return None
    return (hi - lo).total_seconds() / 60.0


def median(values):
    vals = sorted(v for v in values if v is not None)
    if not vals:
        return None
    mid = len(vals) // 2
    return vals[mid] if len(vals) % 2 else (vals[mid - 1] + vals[mid]) / 2.0


def fmt_lag(value):
    return "-" if value is None else "%+.1fm" % value


def scan_transcript(path):
    """The four transcript facts, in one pass: session start, first tool call, first Edit, first delivered notice, and the stop refusals.

    THE CHEAP SUBSTRING GATE IS NOT AN OPTIMISATION DETAIL. This corpus is 1.5 GB across 175 files, and `json.loads` on every line spends minutes; the tests below are C-level scans over raw bytes and discard the great majority of records before any parsing happens. An audit nobody runs because it takes five minutes measures nothing.
    """
    got = {
        "sid": path.stem,
        "start": None,
        "first_tool": None,
        "first_tool_name": "",
        "first_edit": None,
        "notice": None,
        "deliveries": 0,
        "first_refusal": None,
        "refusals": 0,
        "tool_calls": 0,
        "edits": 0,
        "carryover": 0,
    }
    seen_deliveries = set()
    try:
        handle = path.open(encoding="utf-8", errors="replace")
    except OSError as exc:
        got["error"] = str(exc)
        return got
    with handle:
        for line in handle:
            if '"timestamp"' not in line:
                continue
            want = (
                '"tool_use"' in line
                or "hook_additional_context" in line
                or "Stop hook feedback" in line
            )
            if got["start"] is not None and not want:
                continue
            try:
                rec = json.loads(line)
            except ValueError:
                continue  # a torn tail is skipped by the same contract the store uses
            stamp = rec.get("timestamp")
            if not stamp:
                continue
            if got["start"] is None:
                got["start"] = stamp
            elif stamp < got["start"]:
                # CARRY-OVER FROM THE CONVERSATION BEING CONTINUED, and it is not this session's. A resumed session opens a NEW transcript whose head replays records from the old one, stamps and all: f4da5c2e begins at 12:05:08 and its fourth record is a `Stop hook feedback` stamped 12:03:10, which belongs to the context that was compacted away.
                # Attributed here it became a refusal at MINUS 2.0 minutes, which made the session look refused before it had started. Counted rather than dropped in silence, because a cohort where this is common is a cohort whose starts are not what they seem.
                got["carryover"] += 1
                continue
            # A SIDECHAIN IS A SUBAGENT, and the notice is silent to subagents by design. Counting a subagent's tool call as this session's first touch would measure a turn the hook deliberately never speaks on.
            if rec.get("isSidechain"):
                continue
            kind = rec.get("type")
            if kind == "assistant":
                for block in (rec.get("message") or {}).get("content") or []:
                    if not isinstance(block, dict) or block.get("type") != "tool_use":
                        continue
                    name = str(block.get("name") or "")
                    got["tool_calls"] += 1
                    if got["first_tool"] is None:
                        got["first_tool"], got["first_tool_name"] = stamp, name
                    if name in EDIT_TOOLS:
                        got["edits"] += 1
                        if got["first_edit"] is None:
                            got["first_edit"] = stamp
            elif kind == "attachment":
                att = rec.get("attachment") or {}
                body = att.get("content")
                if isinstance(body, list):
                    body = " ".join(str(part) for part in body)
                body = str(body or "") + str(att.get("stdout") or "")
                if not any(mark in body for mark in NOTICE_MARKS):
                    continue
                # ONE DELIVERY LANDS AS TWO RECORDS (a hook_success carrying the raw stdout and a hook_additional_context carrying the parsed text) with the SAME stamp, so deliveries are counted by stamp rather than by record or the rate doubles.
                if stamp not in seen_deliveries:
                    seen_deliveries.add(stamp)
                    got["deliveries"] += 1
                if got["notice"] is None:
                    got["notice"] = stamp
            elif kind == "user" and rec.get("isMeta"):
                body = (rec.get("message") or {}).get("content")
                if isinstance(body, str) and body.startswith("Stop hook feedback"):
                    got["refusals"] += 1
                    if got["first_refusal"] is None:
                        got["first_refusal"] = stamp
    return got


def stop_modules():
    """`wl_core` and `wl_store`, or a loud failure naming what is missing.

    The audit reads the store through the store's OWN code rather than re-deriving where the log lives. The log is in two places at once (the tracked per-writer files and the legacy TMPDIR log still folded in beside them), and an audit reading a different union than the hook would be an audit of nothing.
    """
    stop_dir = Path(__file__).resolve().parents[1] / "stop"
    if str(stop_dir) not in sys.path:
        sys.path.insert(0, str(stop_dir))
    try:
        import wl_core  # noqa: PLC0415 -- deferred; it must follow the sys.path hop above, and the PostToolUse path must never pay this import
        import wl_store  # noqa: PLC0415 -- see wl_core
    except ImportError as exc:
        sys.stderr.write(
            "onboard --audit: cannot import the worklist store from %s (%s). The audit reads "
            "the log through wl_store so it sees exactly what the hook sees; fix the import "
            "rather than re-deriving the paths here.\n" % (stop_dir, exc)
        )
        return None, None
    return wl_core, wl_store


def store_first_writes(core, store):
    """({sid8: first `at` that identity WROTE}, the log floor, the event count)."""
    root = core.project_root(core.project_start())
    events = store._read_events(core.worklist_for(core.project_start()), root)
    first: dict[Any, Any] = {}
    floor = ""
    for ev in events:
        at = str(ev.get("at") or "")
        if not at:
            continue
        if not floor or at < floor:
            floor = at
        # `by`, NEVER the owner. The metric is when a session first WROTE, and an event merely OWNED by it can have been written by --migrate, by --reassign or by a peer; crediting those would report a write the session never made.
        by = str(ev.get("by") or "")
        if by and (by not in first or at < first[by]):
            first[by] = at
    return first, floor, len(events)


def audit_rows(paths, first_writes, floor, marker_state):
    """One row per transcript, split into the cohort and the skips.

    THE FLOOR SKIP IS THE HONESTY RULE, and it is not conservatism for its own sake. `worklist.py --compact` rewrites the whole event log stamping `by: "compact"`, which erases the writer of every historical event while keeping its owner.
    A session that started before the surviving log begins therefore CANNOT be shown to have written, and folding it in as "never wrote" would count it as refused-before-write and report the headline as worse than it is, on evidence that no longer exists. An unmeasurable session is skipped and SAID OUT LOUD, never averaged in.
    """
    rows, skipped = [], []
    for path in sorted(paths):
        got = scan_transcript(path)
        sid8 = got["sid"][:8]
        if got.get("error"):
            skipped.append((sid8, "unreadable: %s" % got["error"]))
            continue
        if not got["start"]:
            skipped.append((sid8, "no timestamped record, so nothing can be placed in time"))
            continue
        if floor and got["start"] < floor:
            skipped.append((sid8, "started before the log floor; attribution was compacted away"))
            continue
        wrote = first_writes.get(sid8)
        refused_first = bool(got["first_refusal"]) and (not wrote or got["first_refusal"] < wrote)
        rows.append(
            {
                "sid": sid8,
                "start": got["start"],
                "tool_calls": got["tool_calls"],
                "edits": got["edits"],
                "carryover": got["carryover"],
                "first_tool_min": mins(got["start"], got["first_tool"]),
                "first_tool_name": got["first_tool_name"],
                "first_edit_min": mins(got["start"], got["first_edit"]),
                "notice_min": mins(got["start"], got["notice"]),
                "deliveries": got["deliveries"],
                "write_min": mins(got["start"], wrote),
                "ever_wrote": bool(wrote),
                "refusals": got["refusals"],
                "refusal_min": mins(got["start"], got["first_refusal"]),
                "refused_before_write": refused_first,
                # ONLY WHEN THE NOTICE CAME FIRST. This metric's whole claim is that the notice was ACTED ON, and a write that PRECEDES it cannot support that claim; folding one in as a negative number drags the median below zero and the line then reports the opposite of what it says.
                # Measured on the live cohort before this guard existed: a median of -0.1m, which reads as "acted on 6 seconds early".
                "delivery_to_write_min": mins(got["notice"], wrote)
                if got["notice"] and wrote and wrote > got["notice"]
                else None,
                "delivered_after_first_refusal": bool(got["notice"])
                and bool(got["first_refusal"])
                and got["notice"] > got["first_refusal"],
                "marker": marker_state.get(sid8, ""),
            }
        )
    return rows, skipped


def audit_summary(rows):
    n = len(rows)
    delivered = [r for r in rows if r["notice_min"] is not None]
    wrote = [r for r in rows if r["ever_wrote"]]
    refused_first = [r for r in rows if r["refused_before_write"]]
    late = [r for r in rows if r["delivered_after_first_refusal"]]
    # THE EDITOR SLICE, and it is reported beside the whole-cohort headline rather than instead of it, because the two answer different questions and the pair is what stops a cohort change from reading as an improvement.
    # Section 5's baseline was measured over FOUR working sessions and came out at three of four; this corpus is 115 sessions of which the great majority open a file, run a handful of tool calls and end, so the same rate computed over everything lands near two percent while nothing whatever has improved.
    # A session that edited no file is one the notice is deliberately near-silent on, so it belongs in the denominator of the silence rate and not in the denominator of the headline.
    editors = [r for r in rows if r["edits"] > 0]
    ed_refused = [r for r in editors if r["refused_before_write"]]
    return {
        "editors": len(editors),
        "editors_refused_before_write": len(ed_refused),
        "editors_refused_pct": 100.0 * len(ed_refused) / len(editors) if editors else None,
        "audited": n,
        "refused_before_write": len(refused_first),
        "refused_before_write_pct": 100.0 * len(refused_first) / n if n else None,
        "never_wrote": n - len(wrote),
        "median_start_to_write_min": median([r["write_min"] for r in wrote]),
        "delivered": len(delivered),
        "silent": n - len(delivered),
        "silence_pct": 100.0 * (n - len(delivered)) / n if n else None,
        "median_delivery_latency_min": median([r["notice_min"] for r in delivered]),
        "median_delivery_to_write_min": median([r["delivery_to_write_min"] for r in rows]),
        "acted_on": sum(1 for r in rows if r["delivery_to_write_min"] is not None),
        "delivered_after_first_refusal": len(late),
        # Section 7 states the trigger in advance and in numbers: delivery landing after the first refusal in more than a third of the audited cohort means arm (b) is too late and a Bash-write arm follows. Printed every run so the decision is read off the artifact rather than argued.
        "arm_b_too_late_trigger": bool(n) and len(late) > n / 3.0,
    }


def audit_report(rows, summary, shape):
    out = []
    out.append(
        "onboard --audit  transcripts %d scanned, %d audited, %d skipped  |  store %d event(s), "
        "floor %s"
        % (
            shape["scanned"],
            summary["audited"],
            shape["skipped"],
            shape["events"],
            shape["floor"] or "(none)",
        )
    )
    out.append("")
    head = "%-9s %-21s %9s %9s %8s %9s %10s  %s" % (
        "sid",
        "start",
        "1st tool",
        "1st edit",
        "notice",
        "1st write",
        "1st refusal",
        "refused-before-write",
    )
    out.append(head)
    out.append("-" * len(head))
    out.extend(
        "%-9s %-21s %9s %9s %8s %9s %10s  %s"
        % (
            r["sid"],
            r["start"][:19],
            fmt_lag(r["first_tool_min"]),
            fmt_lag(r["first_edit_min"]),
            fmt_lag(r["notice_min"]),
            fmt_lag(r["write_min"]) if r["ever_wrote"] else "never",
            fmt_lag(r["refusal_min"]),
            "YES" if r["refused_before_write"] else "no",
        )
        for r in sorted(rows, key=lambda row: row["start"])
    )
    out.append("")
    out.append(
        "HEADLINE  refused-before-write: %d of %d audited (%.1f%%), %d never wrote at all"
        % (
            summary["refused_before_write"],
            summary["audited"],
            summary["refused_before_write_pct"] or 0.0,
            summary["never_wrote"],
        )
    )
    out.append(
        "          among the %d that edited a file at all: %d refused before writing%s. "
        "Section 5's 3-of-4 baseline was measured over WORKING sessions, so this is the "
        "comparable number and the line above is not."
        % (
            summary["editors"],
            summary["editors_refused_before_write"],
            ""
            if summary["editors_refused_pct"] is None
            else " (%.1f%%)" % summary["editors_refused_pct"],
        )
    )
    out.append(
        "          start -> first store write: median %s (over the %d that ever wrote)"
        % (
            fmt_lag(summary["median_start_to_write_min"]),
            summary["audited"] - summary["never_wrote"],
        )
    )
    out.append(
        "          notice -> first store write: median %s over the %d session(s) that wrote AFTER "
        "one (the notice was ACTED ON rather than merely delivered)"
        % (fmt_lag(summary["median_delivery_to_write_min"]), summary["acted_on"])
    )
    out.append(
        "          start -> notice: median %s over %d delivery/deliveries"
        % (fmt_lag(summary["median_delivery_latency_min"]), summary["delivered"])
    )
    out.append(
        "          SILENCE RATE: %d of %d (%.1f%%). HIGH is correct here; a low one means the "
        "notice is firing on sessions with nothing to say."
        % (summary["silent"], summary["audited"], summary["silence_pct"] or 0.0)
    )
    out.append(
        "          section 7 trigger (delivery after the first refusal in more than a third of "
        "the cohort): %s (%d of %d)"
        % (
            "MET -- arm (b) is too late, a Bash-write arm follows"
            if summary["arm_b_too_late_trigger"]
            else "not met",
            summary["delivered_after_first_refusal"],
            summary["audited"],
        )
    )
    if shape["skips"]:
        out.append("")
        out.append("SKIPPED, and never averaged in (an unmeasurable session is not a clean one):")
        for sid8, why in shape["skips"][:12]:
            out.append("  %s  %s" % (sid8, why))
        if len(shape["skips"]) > 12:
            out.append("  ... and %d more" % (len(shape["skips"]) - 12))
    return "\n".join(out)


def marker_states():
    """{sid8: marker state} for every marker still on disk, for the third source.

    Weak on purpose and reported rather than relied on: the sweep deletes these after 24 hours, so an absent marker says nothing at all about whether a notice was delivered. The transcript answers that.
    """
    out = {}
    try:
        for path in B.state_dir().glob("*-onboard.json"):
            try:
                out[path.name[: -len("-onboard.json")]] = str(
                    json.loads(path.read_text(encoding="utf-8")).get("state") or ""
                )
            except (OSError, ValueError):
                continue
    except OSError:
        pass
    return out


def audit_main(argv):
    """`--audit`, the read-only measurement of whether the notice changed anything.

    EVERY WAY THIS CAN SEE NOTHING IS A NON-ZERO EXIT, because the shape of failure available to an audit is a clean-looking report over an empty cohort. No transcripts, no events, or a cohort emptied by the floor rule each return 1 saying so.
    """
    as_json = "--json" in argv
    only = ""
    if "--session" in argv:
        index = argv.index("--session")
        only = argv[index + 1][:8] if index + 1 < len(argv) else ""
        if not only or only.startswith("-"):
            sys.stderr.write("onboard --audit: --session needs an id. %s\n" % AUDIT_USAGE)
            return 2

    if not notice_marks_hold():
        return 1
    core, store = stop_modules()
    if core is None:
        return 1

    root = core.project_root(core.project_start())
    projects = core.projects_dir(root)
    if not projects:
        sys.stderr.write(
            "onboard --audit: no transcript directory for %s. The convention is "
            "~/.claude/projects/<abs-path-with-slashes-as-dashes>/; WORKLIST_PROJECTS_DIR "
            "overrides it.\n" % root
        )
        return 1
    paths = sorted(Path(projects).glob("*.jsonl"))
    if only:
        paths = [p for p in paths if p.stem.startswith(only)]
    if not paths:
        sys.stderr.write(
            "onboard --audit: ZERO transcripts matched in %s%s. The audit is not seeing the "
            "corpus, so any number it printed would mean nothing.\n"
            % (projects, " for session %s" % only if only else "")
        )
        return 1

    first_writes, floor, n_events = store_first_writes(core, store)
    if not n_events:
        sys.stderr.write(
            "onboard --audit: the event log at %s holds ZERO events, so first-write cannot be "
            "computed for any session and every row would read as 'never wrote'.\n"
            % store.store_dir(root)
        )
        return 1

    rows, skipped = audit_rows(paths, first_writes, floor, marker_states())
    shape = {
        "scanned": len(paths),
        "skipped": len(skipped),
        "skips": skipped,
        "events": n_events,
        "floor": floor,
        "projects": str(projects),
    }
    if not rows:
        sys.stderr.write(
            "onboard --audit: all %d transcript(s) were skipped, %d of them for starting before "
            "the log floor %s. A compaction has erased the attribution this measurement needs; "
            "there is nothing here to report.\n"
            % (
                len(paths),
                sum(1 for _s, why in skipped if "floor" in why),
                floor or "(none)",
            )
        )
        return 1

    summary = audit_summary(rows)
    if as_json:
        print(
            json.dumps(
                {
                    "generated_at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "root": str(root),
                    "shape": shape,
                    "summary": summary,
                    "sessions": sorted(rows, key=lambda row: row["start"]),
                },
                indent=2,
                sort_keys=True,
            )
        )
    else:
        print(audit_report(rows, summary, shape))
    return 0


def main():
    if os.environ.get("ONBOARD_NOTICE") == "off":
        sys.exit(0)
    # ANSWERED BEFORE ANYTHING THAT NEEDS AN EVENT, and the order is the point. The audit has no stdin, no session id and no marker of its own, and every rung of the hook ladder below exits 0 when one of those is missing. Behind that ladder a broken audit would be indistinguishable from a clean one, which is the single failure an audit cannot afford.
    if "--audit" in sys.argv:
        sys.exit(audit_main(sys.argv[1:]))
    ev = B.read_event()
    session_id = ev.get("session_id") or os.environ.get("CLAUDE_CODE_SESSION_ID") or ""
    if not session_id:
        sys.exit(0)

    if "--arm" in sys.argv:
        arm(session_id)
        sys.exit(0)

    # A subagent has its own id and its own short life; it is not the session that will face the Stop hook, so telling it about the store is pure noise.
    if ev.get("parent_tool_use_id") or os.environ.get("CLAUDE_AGENT_TYPE"):
        sys.exit(0)

    m = load_marker(session_id)
    if not m:
        sys.exit(0)  # never armed: nothing to say
    epoch = current_epoch(session_id)
    if m.get("state") == "delivered" and m.get("epoch") == epoch:
        sys.exit(0)
    if m.get("state") == "delivered":
        m = {"state": "armed", "epoch": None, "armed_at": time.time()}  # epoch moved: re-arm

    tool = ev.get("tool_name") or ""
    rows, n = my_open_items(session_id)
    if n is None:
        sys.exit(0)  # cannot say; silence beats the wrong notice

    me = str(session_id)[:8]
    if n > 0:
        store = (Path.cwd() / ".claude" / "hooks" / "stop" / "worklist.py").as_posix()
        emit(text_owns(rows, me, store))
    elif tool in EDIT_TOOLS:
        emit(text_fresh(me))
    else:
        # Arm (b): owns nothing and has not edited yet. Stay armed, say nothing.
        m["state"] = "await-edit"
        m["epoch"] = epoch
        save_marker(session_id, m)
        sys.exit(0)

    save_marker(
        session_id, {"state": "delivered", "epoch": epoch, "armed_at": m.get("armed_at", 0)}
    )
    sys.exit(0)


if __name__ == "__main__":
    if "--audit" in sys.argv:
        # THE SWALLOW BELOW DELIBERATELY DOES NOT COVER THIS PATH. The audit is never registered as a hook, so nothing it raises can break a tool call, and catching here would turn a crashed audit into exit 0 with an empty stdout -- a silent green over a cohort nobody measured, which is precisely what this tool exists to refuse.
        main()
    else:
        try:
            main()
        except Exception as exc:  # noqa: BLE001 -- a PostToolUse hook must never break a tool call
            with contextlib.suppress(Exception):
                B.log_error("onboard", exc)
            sys.exit(0)
