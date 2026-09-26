#!/usr/bin/env bash
# COMPATIBILITY ENTRY POINT. The wrapper itself is .ci/media/tools/run-in-tts.sh now, and
# the image context it builds is .ci/media/tts/; both moved there in W10 phase 3 because
# narration is media rather than generic docker plumbing.
#
# WHY THIS FILE STILL EXISTS, rather than the callers being updated. The two callers are
# step4000_voiceover.py in private/generative and tts_bridge.py in private/growth. Those
# are gitignored repositories, not submodules: this checkout cannot open them, cannot
# commit to them, and cannot even read the line that spells this path. A relocation that
# assumes it can update its callers is a relocation that breaks a pipeline nobody in this
# repository can see fail. So the old spelling stays live and forwards.
#
# NOT A WRAPPER WITH OPINIONS. exec, with no argument handling of its own, so argv, stdin,
# stdout, stderr, signals and the exit status all belong to the real wrapper. Anything
# added here becomes a second implementation of a contract that already has one, and the
# next reader would have to diff two files to answer "what does this do".
#
# HOW THE FORWARD IS PROVEN, given the callers cannot be inspected:
# .ci/rediacc_ci/tests/gates/test_gate_media_shims.py drives THIS path with docker absent and
# requires the invocation to arrive in .ci/media/tools/run-in-tts.sh with argv byte-identical,
# from an arbitrary cwd, with the exit status forwarded and stdin still connected. That is
# the whole of what a caller depends on, so proving it here is equivalent to proving it
# there, without needing there.
#
# DELETING THIS FILE IS A CROSS-REPO BREAKING CHANGE. It can go only in a change that also
# lands in private/generative and private/growth, which is a different session's job.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
exec "$ROOT/.ci/media/tools/run-in-tts.sh" "$@"
