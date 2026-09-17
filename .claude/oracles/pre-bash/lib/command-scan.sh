#!/usr/bin/env bash
# FORWARDER, not a copy. Twenty-eight oracles beside this file open with
#
#     source "$(dirname "${BASH_SOURCE[0]}")/lib/command-scan.sh"
#
# and they were moved here, unchanged, by the W5 P7 cutover. The library itself
# did NOT move: block-pathspecless-git-commit.sh is still a live pre-bash guard
# and still sources it from .claude/hooks/pre-bash/lib/, and
# test_shellscan_differential.py compares shellscan.py against that same path.
# One copy, two readers.
#
# WHY FORWARD RATHER THAN REWRITE THE 28 SOURCE LINES. The differential's
# fairness rests on running the REAL file: "a differential against a
# transcription proves the transcription". Editing a line in each oracle would
# make every one of them a transcription, in the exact change that made them the
# only remaining record of what the ports were made from. Three lines here keep
# all 46 byte-identical to the guards they were at 1e97e183d.
#
# shellcheck source=/dev/null
source "$(dirname "${BASH_SOURCE[0]}")/../../../hooks/pre-bash/lib/command-scan.sh"
