"""Port of `.ci/scripts/test/proxies/proxy-rdc-update.sh`.

Local proxy for the CI job that drives `rdc update` end to end, wired as the registered gate `check:ci-proxy-rdc-update` (`package.json:386`). CI runs `.ci/scripts/test/test-rdc-update.sh all` in the update-flow job of
`.github/workflows/ct-update-flow.yml` against a REAL SEA binary; that workflow
is outside the parity surface, so nothing in `npm run ci` has ever touched the updater.

The SUBJECT stays bash and is run as bash. Only the proxy is ported.

THE EXEMPTION IS BY NAME AND PRINTED EVERY RUN, preserved exactly. `happy` and `rollback` need genuine SEA packaging (the CLI refuses a plain node bundle with "Cannot update: not running as a packaged binary"), so with `RDC_BINARY` unset the run is five scenarios and the two are NAMED in yellow on every single run rather than quietly dropped. Setting `RDC_BINARY` removes the
exemption by itself.

-----------------------------------------------------------------------------
TWO PLACES WHERE THE TWIN'S BYTES ARE NOT WHAT A READER EXPECTS
-----------------------------------------------------------------------------
1. `:85` builds the drift message with `$(echo "$DECLARED" | tr '\\n' ' ')`.
   `tr` turns the trailing newline `echo` added into a trailing SPACE, and
   `$( )` strips only trailing NEWLINES, so the space survives into the
   message: `... declares [a b c ] but this proxy partitions [d e ]`. Not a
   defect, but a port that used `" ".join(...)` would differ by two bytes on
   the one path nobody runs. Reproduced, and pinned by
   `test_proxies_rdc_update.py::test_scenario_drift_message_keeps_the_trailing_
   space`.

2. `:119` is `PASS_LINES=$(grep -c 'PASS:' "$OUT" || true)` -- the subject's
   STDOUT FILE ALONE, not the merged pair the linux-packages proxy uses. A
   subject that moved its `PASS:` lines to stderr would therefore report
   `0 PASS: line(s) for 5 scenario(s); at least one asserted nothing` while
   every scenario really passed. That is the RIGHT direction to fail (loud,
   red, and it names the shape), which is why it is reproduced as written
   rather than widened.

-----------------------------------------------------------------------------
`sort` VERSUS `sorted()`, AND WHY IT IS SAFE HERE
-----------------------------------------------------------------------------
`:73` and `:75` both end in `sort`, whose collation depends on the caller's locale, while `sorted()` is always byte order. The two agree for every name the subject declares today (`[a-z0-9-]+` only, and no pair differs only by a hyphen), and `parse_declared` is exported so the differential can drive the comparison instead of this comment being the argument. A name outside that
class cannot appear anyway: `:73`'s own grep would not match it, which is the
ZERO-scenarios refusal at `:76-81`.

K=5 LEDGER: `.ci/shadow/w7p6-proxy-rdc-update.observations.jsonl`.
"""

from __future__ import annotations

import os
import pathlib
import re
import subprocess
import sys

from rediacc_ci.core import proxyx

SUBJECT_REL = ".ci/scripts/test/test-rdc-update.sh"
FALLBACK_REL = "packages/cli/dist/cli-bundle.cjs"

# Scenarios that need no SEA packaging (:43). Kept as a list rather than a count so a name added to the subject and forgotten here is visible in the diff.
SEA_FREE = ["check-only", "sha256-mismatch", "rollback-empty", "channel-switch", "reinstall"]
# BLOCKER: these two invoke the SEA-only update and rollback paths, which a node bundle cannot reach at all. Exempt by name, reported every run, and skipped only while RDC_BINARY is unset. (:45-47)
SEA_ONLY = ["happy", "rollback"]

# `grep -oE '^ [a-z0-9-]+\) scenario_'` (:73). EXACTLY eight spaces: a re-indented dispatch matches nothing and takes the loud refusal below, which is the right direction.
DISPATCH_RE = re.compile(r"^        ([a-z0-9-]+)\) scenario_", re.MULTILINE)


def _proxy_root() -> pathlib.Path:
    """`ROOT_DIR="$PROXY_DIR/../../../.."` (:33-34)."""
    return pathlib.Path(__file__).resolve().parents[3]


def parse_declared(subject_text: str) -> list[str]:
    """`:73`, the whole pipeline: grep -oE | sed | sort.

    The `sed 's/) scenario_//; s/^ *//'` reduces each match to the bare name,
    which is exactly the capture group here.
    """
    return sorted(DISPATCH_RE.findall(subject_text))


def joined(names: list[str]) -> str:
    """`$(echo "$X" | tr '\\n' ' ')` (:85). Note the TRAILING SPACE, see docstring."""
    return "".join(f"{n} " for n in names)


def run() -> int:
    root = _proxy_root()
    subject = str(root / SUBJECT_REL)
    fallback = str(root / FALLBACK_REL)

    p = proxyx.Proxy("rdc-update", SUBJECT_REL)

    # :56-61. An RDC_BINARY set to the empty string counts as unset, because
    # `[[ -z "${RDC_BINARY:-}" ]]` tests emptiness, not presence.
    reduced = not os.environ.get("RDC_BINARY")
    if reduced:
        os.environ["RDC_BINARY"] = fallback
    rdc_binary = os.environ["RDC_BINARY"]

    p.need_exec(subject, "the subject script is missing from this checkout")
    p.need_exec(
        rdc_binary,
        "cd packages/cli && npm run build:cli, or export RDC_BINARY=/path/to/rdc",
    )
    p.need_cmd("python3", "sudo apt-get install -y python3 (the subject's update fixture server)")
    p.need_cmd("node", "./run.sh setup")
    p.need_file(
        str(root / "packages" / "www" / "public" / "install.sh"),
        "the installer the subject drives is missing from this checkout",
    )
    p.preflight()

    # :70-86. The subject's own scenario set, read from its dispatch rather than retyped.
    declared = parse_declared(pathlib.Path(subject).read_text(encoding="utf-8"))
    known = sorted(SEA_FREE + SEA_ONLY)
    if not declared:
        red, off = p._c(proxyx.RED), p._c(proxyx.OFF)
        print(
            f"{red}proxy rdc-update: read ZERO scenarios out of the subject's dispatch{off}",
            file=sys.stderr,
        )
        print(
            "  The partition below would then be vacuous. Check the grep in this file",
            file=sys.stderr,
        )
        print(f"  against the dispatch block at the end of {subject}.", file=sys.stderr)
        return 1
    if declared == known:
        p.ok(f"this proxy's partition covers all {len(declared)} scenarios the subject declares")
    else:
        p.bad(
            f"scenario drift: the subject declares [{joined(declared)}] but this proxy "
            f"partitions [{joined(known)}]"
        )

    if reduced:
        to_run = list(SEA_FREE)
        yel, off = p._c(proxyx.YEL), p._c(proxyx.OFF)
        print(f"{yel}proxy rdc-update: REDUCED RUN. RDC_BINARY is unset, so the fallback is{off}")
        print(f"{yel}  {fallback} (a node bundle, not a packaged SEA binary).{off}")
        print(f"{yel}  NOT EXERCISED HERE: {' '.join(SEA_ONLY)} -- both need SEA packaging.{off}")
        print(
            f"{yel}  CI runs all {len(declared)} against a real binary; "
            f"to do the same locally run{off}"
        )
        print(f"{yel}  'cd packages/cli && npm run build:cli' and re-run with RDC_BINARY set.{off}")
    else:
        to_run = SEA_FREE + SEA_ONLY
        print(
            f"proxy rdc-update: FULL RUN against RDC_BINARY={rdc_binary} ({len(to_run)} scenarios)"
        )

    # :104-115. Streams kept separate, and the whole of each is dumped on a failure (`cat`, not `tail -N`).
    sys.stdout.flush()
    sub = subprocess.run([subject, *to_run], capture_output=True, text=True, check=False)
    rc = sub.returncode

    if rc == 0:
        p.ok(f"{len(to_run)} scenario(s) passed: {' '.join(to_run)}")
    else:
        p.bad(f"the subject exited {rc} over {' '.join(to_run)}")
        print("  --- subject stdout ---", file=sys.stderr)
        sys.stderr.write(sub.stdout)
        print("  --- subject stderr ---", file=sys.stderr)
        sys.stderr.write(sub.stderr)

    # :117-124. STDOUT ALONE; see this module's docstring, point 2.
    pass_lines = sum(1 for line in sub.stdout.split("\n") if "PASS:" in line)
    if pass_lines == len(to_run):
        p.ok(f"the subject emitted one PASS: line per scenario ({pass_lines} of {len(to_run)})")
    else:
        p.bad(
            f"the subject emitted {pass_lines} PASS: line(s) for {len(to_run)} scenario(s); "
            "at least one asserted nothing"
        )

    return p.finish()


def main(argv: list[str]) -> int:
    if argv and argv[0] == "--selftest":
        return proxyx.run_selftest()
    return run()


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
