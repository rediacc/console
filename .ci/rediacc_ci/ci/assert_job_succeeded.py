#!/usr/bin/env python3
"""Port of `.ci/scripts/ci/assert-job-succeeded.sh` (61 lines).

The transitive-skip sentinel: assert an upstream job was not silently skipped
by the GHA needs-chain skip propagation (finding J). The twin's header owns the
state table and why only `skipped` fails; it is not restated here beyond what
the code needs.

LIVE CALLERS, not repointed: `.github/workflows/ci.yml:1937` and its siblings,
one per sentinel job (`run: .ci/scripts/ci/assert-job-succeeded.sh
<label> "${{ needs.<job>.result }}"`). The bash twin stays the registered gate;
this module is its verified-equivalent alternative and the cutover is a
separate, later, driver-only step.

Ledger: `.ci/shadow/w7p6-assert-job-succeeded.observations.jsonl`
(`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-job-succeeded --assert
--k 5`).

-----------------------------------------------------------------------------
THE UNKNOWN-RESULT ARM FAILS CLOSED, WHICH IS WHY THE PORT KEEPS IT VERBATIM
-----------------------------------------------------------------------------
Unlike its sibling `assert-channel-for-event.sh`, whose `*)` arm warns and
ACCEPTS, this script's `*)` arm ERRORS and exits 1 -- including for an EMPTY
result, which is what `${{ needs.<job>.result }}` yields when the job name is
misspelled in `needs:`. A renamed job therefore breaks loudly rather than
passing, and that asymmetry between the two sentinels is deliberate on the
twin's part.

`$0` in the usage line is the program's own name, so bash prints the `.sh` path
and this prints the `.py` path; the differential normalises that one token and
compares the rest byte-for-byte.
"""

from __future__ import annotations

import sys

from rediacc_ci import log

SKIPPED_ADVICE = (
    "  Some job in {label}'s needs chain skipped and GH Actions propagated",
    "  the skip through to {label}. Prefix the if: on the {label} job",
    "  with 'always() &&' so skips in its needs chain cannot silently disable it.",
    "  The static audit .ci/scripts/security/check-workflow-gates.sh should also",
    "  have caught this; investigate why it did not.",
)

EXTERNAL_ADVICE = (
    "  Sentinel only fails on 'skipped' (the transitive-skip propagation signature).",
    "  cancelled => CI watchdog, concurrent-push auto-cancel, or manual cancel.",
    "  failure   => {label} already reported its own failure; no need to pile on.",
)


def main(argv: list[str]) -> int:
    job_label = argv[0] if len(argv) >= 1 else ""
    result = argv[1] if len(argv) >= 2 else ""

    if not job_label:
        log.error("Usage: %s <job_label> <result>" % sys.argv[0])
        return 2

    log.info("%s result: %s" % (job_label, result))

    if result == "success":
        return 0

    if result == "skipped":
        log.error(
            "%s was skipped. This is the GHA transitive-skip propagation bug (finding J)."
            % job_label
        )
        for line in SKIPPED_ADVICE:
            log.error(line.format(label=job_label))
        return 1

    if result in ("cancelled", "failure"):
        log.warn(
            "%s result=%s; treating as externally-imposed or already-surfaced."
            % (job_label, result)
        )
        for line in EXTERNAL_ADVICE:
            log.warn(line.format(label=job_label))
        return 0

    log.error(
        "%s has unexpected result='%s' (not success/skipped/cancelled/failure)."
        % (job_label, result)
    )
    log.error("  Update assert-job-succeeded.sh to handle this state explicitly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
