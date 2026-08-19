#!/usr/bin/env python3
"""PostToolUse: state the context budget once per band, per compaction epoch.

This replaces a 60-minute timer with the only signal that actually predicts
compaction. It reads the transcript tail, derives the auto-compact threshold
the way Claude Code derives it, and when usage crosses a band it has not yet
crossed in this epoch it returns `hookSpecificOutput.additionalContext`.

THREE THINGS THIS HOOK DELIBERATELY DOES NOT DO:

1. It does not instruct. The text is factual state -- numbers, paths, and
   times. Claude Code's own hook documentation warns that text framed as an
   out-of-band system command trips the model's prompt-injection defenses and
   gets surfaced to the user instead of acted on, and an instruction that gets
   surfaced instead of acted on is a trigger that does not fire.
2. It does not repeat. One statement per band per epoch. A reminder attached
   to every tool result would be noise inside a minute, and noise is how a
   real signal gets ignored.
3. It does not block. Every failure path exits 0 with empty stdout. The cost
   of that choice is that a broken hook is invisible, so every swallowed
   exception is written to state/errors.log.
"""

import json
import os
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx_budget as B


def emit(text):
    json.dump(
        {
            "hookSpecificOutput": {
                "hookEventName": "PostToolUse",
                "additionalContext": text,
            }
        },
        sys.stdout,
    )
    sys.stdout.write("\n")


def describe_state_md(path, st, usage, threshold):
    """A factual line about the recovery document, including how stale it is
    IN CONTEXT TERMS rather than in minutes.

    Minutes were the old trigger and they were the wrong unit: a session can
    burn 200K tokens in ten minutes or 5K in an hour. What matters is how much
    of the window has gone by since the document was last true.
    """
    if not path.is_file():
        return "No compact-recovery document exists for this session at %s." % path.as_posix()
    mtime = path.stat().st_mtime
    age_min = int((time.time() - mtime) / 60)
    written_at = st.get("state_written_usage")
    if written_at and threshold:
        moved = usage - written_at
        return (
            "The compact-recovery document is %s, last written %d minutes ago at "
            "%s tokens of context. %s tokens have entered the context since."
            % (path.as_posix(), age_min, B.fmt(written_at), B.fmt(moved))
        )
    return "The compact-recovery document is %s, last written %d minutes ago." % (
        path.as_posix(),
        age_min,
    )


def build_text(band_name, usage, res, st, state_md):
    threshold = res["threshold"]
    pct = 100.0 * usage / threshold
    headroom = threshold - usage
    # A NEGATIVE HEADROOM IS NEVER A FACT ABOUT THE SESSION, only ever a fact
    # about this hook's denominator: a session past its compaction threshold
    # has compacted, by definition. Printing "-226,179 tokens" once is enough
    # to make every later notice ignorable, so the number is not printed.
    if headroom >= 0:
        head = "Headroom before compaction: %s tokens." % B.fmt(headroom)
    else:
        head = (
            "This reading is ABOVE the derived threshold, which means the "
            "threshold is too low rather than that compaction is overdue; "
            "treat the percentage as unreliable."
        )
    lines = [
        "Context budget: %s tokens in use, %.1f%% of this session's auto-compact "
        "threshold of %s (window %s, source %s). %s"
        % (
            B.fmt(usage),
            pct,
            B.fmt(threshold),
            B.fmt(res["window"]),
            res["source"],
            head,
        ),
        (
            "At the threshold Claude Code replaces this transcript with a summary; "
            "files on disk are what survive it."
        ),
        describe_state_md(state_md, st, usage, threshold),
        (
            "Measured in this repo across 414 real `worklist.py --state` writes: a "
            "rewrite turn costs about 2,200 tokens at the median, 4,900 at the 99th "
            "percentile, and 17,800 in the worst case observed."
        ),
    ]
    if res.get("cap_disproven"):
        lines.append(
            "The transcript reports the model as %r, whose default window would "
            "put the threshold far below the context this session is already "
            "carrying. That cap is disproven, so the configured window is used "
            "instead and the threshold above is a floor, not a measurement." % (res["model"],)
        )
    elif not res["confident"]:
        lines.append(
            "The model id %r is not one this hook recognises, so the threshold "
            "above is derived from the configured window alone and may be wrong." % (res["model"],)
        )
    lines.append("(band: %s)" % band_name)
    return "\n".join(lines)


def main():
    event = B.read_event()

    # A live end-to-end delivery probe. The control suite and the operator use
    # this to answer "does additionalContext actually reach the model in THIS
    # install", which is a question the documentation cannot answer. One shot:
    # the marker is consumed so it can never become a permanent nag.
    try:
        force = B.state_dir() / "force-emit"
        if force.exists():
            force.unlink()
            emit(
                "Context-band delivery probe: this text was produced by "
                ".claude/hooks/context/band-notice.py on a PostToolUse event. "
                "Its presence in the transcript is the proof that "
                "hookSpecificOutput.additionalContext reaches the model in this "
                "install."
            )
            return
    except Exception as exc:  # noqa: BLE001
        B.log_error("band-notice/force", exc)

    try:
        if os.environ.get("CTX_BAND_DUMP") or (B.state_dir() / "dump-events").exists():
            with open(B.state_dir() / "events.jsonl", "a", encoding="utf-8") as fh:
                fh.write(json.dumps(event, sort_keys=True) + "\n")
    except Exception as exc:  # noqa: BLE001
        B.log_error("band-notice/dump", exc)

    try:
        # A subagent has its own context window and does not own STATE.md.
        # Telling it about the main session's budget is both wrong and useless.
        if event.get("agent_id"):
            return

        transcript = event.get("transcript_path")
        if not transcript:
            return
        got = B.last_usage(transcript)
        if not got:
            return
        usage, model = got

        project = B.project_dir(event)
        session_id = event.get("session_id") or ""
        st = B.load_state(session_id)
        state_md = B.state_md_path(project, session_id)

        # The model cap is an inference off a transcript field that has
        # already been observed to lie (see cap_is_disproven). Once this
        # session has proven its window is bigger, that verdict is STICKY:
        # after a compaction usage drops back under the fake hard limit, and
        # without the sticky flag the wrong cap would quietly re-arm.
        sticky = bool(st.get("cap_disproven")) and st.get("cap_disproven_model") == model
        floor = st.get("window_floor")
        res = B.resolve_threshold(
            model, project, observed_usage=usage, cap_disproven=sticky, window_floor=floor
        )
        if not res["threshold"] or res["threshold"] <= 0:
            return
        if res["cap_disproven"] and not sticky and not floor:
            st["cap_disproven"] = True
            st["cap_disproven_model"] = model
            # The band recorded under the wrong threshold is meaningless.
            st["band"] = -1

        # EVIDENCE BEATS CONFIGURATION. A session that has carried more tokens
        # than the derived threshold allows, without compacting, has proven the
        # threshold wrong. This is the generalisation of the model-cap
        # disproof, and it catches the case that has no other tell: a session
        # started BEFORE the window was pinned is running on the old window,
        # and reads the new one out of settings on every tool call.
        high = max(usage, int(st.get("high_water") or 0))
        st["high_water"] = high
        if high > res["threshold"]:
            ceiling = max(int(res.get("model_max") or 0), B.WINDOW_MAX)
            if ceiling > (res["window"] or 0):
                st["window_floor"] = ceiling
                res = B.resolve_threshold(
                    model,
                    project,
                    observed_usage=usage,
                    cap_disproven=sticky,
                    window_floor=ceiling,
                )
                # Re-seat the ladder under the corrected threshold rather than
                # clearing it. Clearing would replay every band the session has
                # already passed; leaving it would suppress the bands it has
                # not reached yet under the new, larger denominator.
                st["band"] = B.band_for(usage, res["threshold"])
                st["threshold_corrected"] = True

        # A compaction this hook did not see still has to reset the ladder.
        # PostCompact is the primary reset; this is the backstop for a
        # compaction that happened while the hook was unregistered or failing.
        prev_usage = st.get("usage") or 0
        if prev_usage and usage < prev_usage * 0.75:
            st = {
                "epoch": int(st.get("epoch", 0)) + 1,
                "band": -1,
                "reset_reason": "usage_drop",
                # Carried across the reset on purpose: the window did not
                # change because the conversation was summarised. high_water
                # deliberately does NOT survive -- it is a fact about the
                # epoch that just ended.
                "cap_disproven": st.get("cap_disproven"),
                "cap_disproven_model": st.get("cap_disproven_model"),
                "window_floor": st.get("window_floor"),
                "threshold_corrected": st.get("threshold_corrected"),
            }

        # Track when STATE.md was last written, in context terms. Cheap: one
        # stat per tool call, and it is what makes the notice say something
        # more useful than a wall-clock age.
        try:
            mtime = state_md.stat().st_mtime if state_md.is_file() else None
        except OSError:
            mtime = None
        if mtime is not None and mtime != st.get("state_mtime"):
            st["state_mtime"] = mtime
            st["state_written_usage"] = usage

        band = B.band_for(usage, res["threshold"])
        st["usage"] = usage
        st["threshold"] = res["threshold"]
        st["model"] = model

        if band > int(st.get("band", -1)):
            st["band"] = band
            st["band_name"] = B.BANDS[band][0]
            B.save_state(session_id, st)
            emit(build_text(B.BANDS[band][0], usage, res, st, state_md))
            return

        B.save_state(session_id, st)
    except Exception as exc:  # noqa: BLE001 -- a PostToolUse hook must never break a tool call
        B.log_error("band-notice", exc)


if __name__ == "__main__":
    main()
    sys.exit(0)
