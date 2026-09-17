"""FORWARDER, not a copy, and the same argument `oracles/pre-bash/lib/command-scan.sh` makes.

`oracles/pre-bash/block-adhoc-sanctioned.sh` resolves its library as

    LIB="$(cd "$(dirname "${BASH_SOURCE[0]}")/../lib" && pwd)"
    [ -f "$LIB/sanctioned.py" ] || exit 0

and then imports `sanctioned` with `$LIB` first on `sys.path`. It was moved here
unchanged by the W5 P7 cutover; the library itself did NOT move, because
`.claude/hooks/lib/sanctioned.py` is the live registry the port (`rediacc_hooks/guards/block_adhoc_sanctioned.py`) reads. One copy, two readers.

WHY `exec` AND NOT A STAR IMPORT. That was the first cut and it silently produced a module with no `match` and no `message`: with `$LIB` leading `sys.path`, an `import sanctioned` inside THIS file resolves to this file, which is already half-initialised in `sys.modules`, so the star import bound nothing. The guard's `except Exception: sys.exit(0)` then made it allow every command
in both directions -- a guard that cannot fail, arriving through a forwarder written to keep one honest. Measured, not imagined: the differential's block case came back
rc=0 from the oracle and rc=2 from the port. Executing the live source into this
namespace has no such loop and yields the identical module either way.
"""

import pathlib

_LIVE = pathlib.Path(__file__).resolve().parents[2] / "hooks" / "lib" / "sanctioned.py"
exec(compile(_LIVE.read_text(encoding="utf-8"), str(_LIVE), "exec"), globals())  # noqa: S102
