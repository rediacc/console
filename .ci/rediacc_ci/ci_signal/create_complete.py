"""Port of `.ci/scripts/signal/create-complete.sh`.

Writes the completion-signal file a CI job coordinator waits on. Eight
`ct-tests.yml` jobs call it (`ct-tests.yml:419,569,735,889,1049,1266,1449,1628`)
as `--name "<suite>" --status ${{ job.status }}`, and the backend job blocks
until those files appear. It is a workflow `run:` target, NOT a registered
`check:ci-*` gate: `grep -n create-complete package.json` matches nothing, so
there is no gate id to cite here and no manifest entry to keep in step.

WHAT IT CLOSES. The twin is 44 lines of which 25 are `parse_args`, `CI_TEMP`
and two log helpers borrowed from `.ci/scripts/lib/common.sh`, i.e. the exact
surface `rediacc_ci.core.common` and `rediacc_ci.log` already own and already
prove. Porting it removes the last reason `signal/` had to source a 500-line
library to write two files, and it puts the flag contract under a differential
instead of under a usage comment.

THE FLAG CONTRACT, from the twin's own header:

  --name    REQUIRED. Signal name, e.g. `cli-Linux`, `e2e-chromium`.
  --output  Output directory. Default `$CI_TEMP`, which `common.sh:511` sets
            from `get_temp_dir()`: `$RUNNER_TEMP`, else `$TMPDIR`, else `/tmp`.
  --status  Job status. Default `success`.

It writes TWO files, not one: `complete-<name>.txt` and a generic
`complete.txt`, both holding `<status>`. The generic one is the "simple cases"
convenience the twin's last line calls it, and it means two jobs sharing an
output directory overwrite each other's `complete.txt`. That is the twin's
behaviour and it is reproduced rather than corrected -- every live caller
passes a distinct `--name` and reads `complete-<name>.txt`.

MESSAGE TEXT IS BYTE-IDENTICAL, INCLUDING THE `.sh` IN THE USAGE LINE. Both
strings a human ever reads here (`Usage: create-complete.sh ...` and `Created
completion signal: ...`) are explicit `log_error`/`log_info` arguments the twin
author chose, so the port reproduces them exactly, `.sh` and all: the name in
that line is the name of the step a workflow author greps for, and rewriting it
to `.py` would make the two implementations answer differently for no gain
while the bash twin is still the live call site.

TWO DIVERGENCES, BOTH NAMED RATHER THAN HIDDEN:

  1. COLOUR UNDER `CI=true`. `common.sh:18` gates colour on `[[ -t 2 ]] &&
     [[ -z "${NO_COLOR:-}" ]]`; `rediacc_ci.log.colour_allowed` additionally
     refuses when `CI=true`. On a GitHub runner stderr is not a tty, so both
     sides are colourless and the difference is unreachable there. It IS
     reachable for a developer running with `CI=true` on a terminal, and the
     differential pins the ordinary tty case (colour on both sides) so the
     shared branch stays proven.
  2. AN UNUSABLE `--output`. The twin's `mkdir -p` failure is caught by
     `set -e`: exit 1 with `mkdir`'s own message. This port exits 1 with
     Python's `OSError` text. Same exit code, same stream, different words --
     and the port's words are the more useful ones, because they name the path.
     Measured 2026-09-10 on this host, where `/usr/bin/mkdir` is uutils rather
     than GNU coreutils, the twin's entire message is `mkdir: Already exists`,
     naming nothing at all. The differential asserts the exit code on both
     sides and the path only on the port's.

K=5 LEDGER: `.ci/shadow/w7p6-create-complete.observations.jsonl`.
"""

from __future__ import annotations

import pathlib
import sys

from rediacc_ci import log
from rediacc_ci.core import common

USAGE = "Usage: create-complete.sh --name <signal_name> [--output <dir>] [--status <status>]"


def main(argv: list[str]) -> int:
    args = common.parse_args(argv)

    # `${ARG_NAME:-}` / `${ARG_OUTPUT:-$CI_TEMP}` / `${ARG_STATUS:-success}`.
    # The `:-` form treats an EMPTY value as absent, which `--name=` can
    # produce, so `or` is the right Python spelling rather than `.get(k, d)`.
    name = args.get("ARG_NAME", "")
    output_dir = args.get("ARG_OUTPUT", "") or common.get_temp_dir()
    status = args.get("ARG_STATUS", "") or "success"

    if not name:
        log.error(USAGE)
        return 1

    out = pathlib.Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)

    signal_file = out / ("complete-%s.txt" % name)
    signal_file.write_text(status + "\n", encoding="utf-8")

    log.info("Created completion signal: %s (status: %s)" % (signal_file, status))

    # The generic sibling, written AFTER the log line, exactly as the twin orders them: a reader tailing stderr sees the named file announced before the unnamed one lands.
    (out / "complete.txt").write_text(status + "\n", encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
