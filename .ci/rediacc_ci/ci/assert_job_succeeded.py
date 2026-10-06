#!/usr/bin/env python3
"""The transitive-skip sentinel: assert an upstream job was not silently skipped by the GHA needs-chain skip propagation (finding J).

When a job in the needs chain skips, downstream jobs without `always()` quietly skip too; this catches that regression at runtime on push-to-main.

THE STATE TABLE (this module owns it since the bash original, `.ci/scripts/ci/assert-job-succeeded.sh`, was retired under PLAN-retire-bash-oracles B3; its answers are frozen in `.ci/rediacc_ci/tests/goldens/twins/ci.assert-job-succeeded.jsonl`, whose header names the blob):

    success              pass
    skipped              FAIL: the bug is back; fix the upstream `if:` -- unless the optional third argument, CI Complete's verdict, is present and not "success": then the job skipped by design (its `if:` requires ci-complete to succeed), so pass with a warning naming the verdict; CI Complete reports the root failure
    cancelled, failure   pass. cancelled is externally imposed (CI watchdog force-cancel, concurrent-push auto-cancel, manual cancel); failure is already surfaced by the upstream job itself. Neither is the class of bug this sentinel guards against.
    anything else        FAIL, see below

LIVE. `.github/workflows/ci.yml` runs `python3 -m rediacc_ci.ci.assert_job_succeeded <label> <result> <ci-complete-verdict>` for the finalize-release sentinel. With no verdict argument the table above applies unchanged.

Ledger: `.ci/shadow/w7p6-assert-job-succeeded.observations.jsonl` (`npx tsx scripts/lib/shadow-gate.ts --pair w7p6-assert-job-succeeded --assert --k 5`).

-----------------------------------------------------------------------------
THE UNKNOWN-RESULT ARM FAILS CLOSED, WHICH IS WHY THE PORT KEEPS IT VERBATIM
-----------------------------------------------------------------------------
Unlike its sibling `assert_channel_for_event`, whose `*)` arm warns and ACCEPTS, this script's `*)` arm ERRORS and exits 1 -- including for an EMPTY
result, which is what `${{ needs.<job>.result }}` yields when the job name is
misspelled in `needs:`. A renamed job therefore breaks loudly rather than passing, and that asymmetry between the two sentinels is deliberate.

`$0` in the usage line is the program's own name, so the frozen bash answer carries the `.sh` path and this prints the `.py` path; the differential normalises that one token and compares the rest byte-for-byte.
"""

from __future__ import annotations

import sys

from rediacc_ci import log

SKIPPED_ADVICE = (
    "  Some job in {label}'s needs chain skipped and GH Actions propagated",
    "  the skip through to {label}. Prefix the if: on the {label} job",
    "  with 'always() &&' so skips in its needs chain cannot silently disable it.",
    "  The static audit .ci/scripts/security/check_workflow_gates.py should also",
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
    verdict = argv[2] if len(argv) >= 3 else ""

    if not job_label:
        log.error("Usage: %s <job_label> <result>" % sys.argv[0])
        return 2

    log.info("%s result: %s" % (job_label, result))

    if result == "success":
        return 0

    if result == "skipped" and verdict not in ("", "success"):
        log.warn(
            "%s skipped because CI Complete was %s; the root failure is reported by CI Complete."
            % (job_label, verdict)
        )
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
    # Rule T (PLAN-retire-bash-oracles B3): the bash original named itself here; after its deletion that advice pointed at a file that no longer exists.
    log.error("  Update .ci/rediacc_ci/ci/assert_job_succeeded.py to handle this state explicitly.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
