"""Port of `.ci/scripts/deploy/upload-media-to-r2.sh`.

THE TWIN IS A COMPATIBILITY FORWARDING SHIM, NOT A PROGRAM. Its own header
explains why it still exists: the real primitive moved to
`.ci/media/tools/upload-r2.sh`, and one of its two callers is
`private/growth/video_pipeline/publish.py`, a gitignored repository this
checkout cannot open or edit -- so the old path has to keep working forever.
`exec`, no argument handling of its own: argv, stdin, stdout, stderr, signals
and the exit status all belong to the target.

THIS PORT IS THE SAME SHAPE, `os.execv`, for the same reason the twin uses
`exec` rather than a subprocess call: a subprocess would be a second process
watching the first, which is itself a second implementation of a contract
that already has one (the target script), and would leave a stray parent
process around if the caller sends it a signal expecting the exec'd program
to receive it directly.

`ROOT` is `.ci/rediacc_ci/deploy/../../..`, exactly as the twin's
`SCRIPT_DIR/../../..` is `.ci/scripts/deploy/../../..` -- both three
directories deep under the repository root, so the arithmetic is identical
even though the two files do not share a parent directory.

DELETING THIS FILE IS A CROSS-REPO BREAKING CHANGE, same warning as the twin
carries, for the same reason: `private/growth/video_pipeline/publish.py`
cannot be updated from here to spell a different path.
"""

from __future__ import annotations

import os
import sys


def main(argv: list[str]) -> int:
    root = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "..", ".."))
    target = os.path.join(root, ".ci", "media", "tools", "upload-r2.sh")
    os.execv(target, [target, *argv])  # noqa: S606 -- forwarding exec, same shape as the twin's
    return 1  # unreachable: execv replaces this process on success


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
