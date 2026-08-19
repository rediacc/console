#!/usr/bin/env python3
"""PostCompact: open a new band epoch.

Compaction is the event that makes every band the notice already announced
untrue: usage has dropped, the transcript is a summary, and the recovery
document matters more than it did a minute ago, not less. This hook bumps the
epoch and clears the band ladder so `band-notice.py` will speak again on the
way back up.

It also records what the compaction produced. `compact_summary` is the only
place a session can see what its own summary said, and its LENGTH is the
cheapest available answer to "did the summary keep anything".

PostCompact has no decision control, so there is nothing to return. Exit 0,
always.
"""

import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import ctx_budget as B  # noqa: E402


def main():
    event = B.read_event()
    try:
        session_id = event.get("session_id") or ""
        st = B.load_state(session_id)
        summary = event.get("compact_summary") or ""
        B.save_state(
            session_id,
            {
                "epoch": int(st.get("epoch", 0)) + 1,
                "band": -1,
                "reset_reason": "postcompact",
                "reset_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                "compact_trigger": event.get("trigger"),
                "compact_summary_chars": len(summary),
                # Survives the epoch: a disproven model cap is a fact about
                # the session's window, and compaction does not change it.
                "cap_disproven": st.get("cap_disproven"),
                "cap_disproven_model": st.get("cap_disproven_model"),
                "window_floor": st.get("window_floor"),
                "threshold_corrected": st.get("threshold_corrected"),
                # Deliberately NOT carried forward: usage, threshold, model.
                # Usage in particular must not survive, or the usage-drop
                # backstop in band-notice would fire on the next tool call and
                # bump a second epoch for the same compaction.
            },
        )
    except Exception as exc:  # noqa: BLE001
        B.log_error("epoch-reset", exc)


if __name__ == "__main__":
    main()
    sys.exit(0)
