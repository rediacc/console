#!/bin/bash
# ./run.sh -- the router. Three destinations, and no logic of its own.
#
# WHERE THE OTHER 1,300 LINES WENT. Everything this script used to do is in
# .ci/legacy/run-legacy.sh, moved there whole on 2026-09-06. That file's header
# lists the handful of lines the move changed; nothing else was rewritten,
# because this split is the largest revert boundary in the tooling
# transformation and a reviewer has to be able to see that at a glance.
#
# WHY A ROUTER AT ALL. The transformation moves this repository's CI programs out
# of bash and into the `rediacc_ci` Python package one workstream at a time. A
# verb cannot move without a seam that can send `./run.sh <verb>` to either
# implementation, and a seam buried inside a 1,300-line file means every port
# re-opens the hottest file in the tree -- run.sh has exactly ONE writer at a time
# across the whole program (docs/ci-overhaul/08-driver-contract.md section 3).
# Here, porting a verb is one line in PORTED_VERBS and nothing else moves.
#
# PORTED_VERBS NAMES WHAT HAS ACTUALLY MOVED, and nothing else: `setup` and `dev` are
# served by `python3 -m rediacc_ci`, every other verb but the two media ones still goes
# to the legacy file, and each name arrived here in the same change that deleted its
# bash body. Not taken on trust -- .ci/scripts/test/gates/test-run-sh.sh asserts that
# this file's arms and the legacy dispatcher PARTITION the verb set `show_help`
# documents, in both directions: a verb cannot be ported into a gap or served twice.
#
# NOT A PLACE FOR LOGIC. Anything that is not "which implementation runs this verb"
# belongs on one side or the other; a router that grows a special case has quietly
# become a third implementation, which is what the gate test's line ceiling is for.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LEGACY_RUNNER="$ROOT_DIR/.ci/legacy/run-legacy.sh"

# One entry per top-level verb served by `python3 -m rediacc_ci`. Add a verb here
# in the SAME change that deletes its arm from the legacy dispatcher: the gate
# test refuses an orphan and an overlap alike, so a half-done port is red rather
# than ambiguous.
PORTED_VERBS=(setup dev)

# `.ci` on PYTHONPATH, not an install: the package directory is `.ci/rediacc_ci`, so
# the importable name is `rediacc_ci` with `.ci` on the path, which is what pyproject
# .toml's `pythonpath` key tells pytest too. There is deliberately no `[project]` table
# and no `pip install -e .`, because pip is absent on the host these gates run on.
run_ported() { # run_ported <verb> [args...]
    # NAME THE MISSING INTERPRETER. Without this the failure is a bare exit 127
    # and the word `python3`, on a verb nobody has any reason to know is Python.
    if ! command -v python3 >/dev/null 2>&1; then
        echo "run.sh: '$1' is served by the Python CI package, and python3 is not on PATH." >&2
        echo "run.sh: install it, or run .ci/bootstrap.sh which provisions this toolchain." >&2
        exit 1
    fi
    PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci "$@"
}

main() {
    case "${1:-}" in
        # VM Provisioning. Part of the media pipeline, so it delegates like www below.
        # NOT shifted: media_entry_main matches on `provision` itself, so the verb has
        # to arrive with the rest of the argv.
        provision) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;

        # THE MEDIA PIPELINE LIVES IN .ci/media/ NOW.
        #
        # 35 functions and three constants -- about 1,250 lines of the run.sh that
        # stood here, then 2,647 lines long -- were the tutorial recorder, the render
        # pool, the generative venv, the CUDA probe, the bridge helpers and the R2
        # narration cache. They drive private/generative and private/growth, two
        # gitignored repositories rather than submodules, so they cannot be ported to
        # Python with the rest of the tooling and are deliberately staying bash.
        # Splitting them into seven sourced modules with a gate test each was the only
        # maintainability move left.
        #
        # media-entry.sh's dispatch tree is a verb-for-verb mirror of the arms that
        # stood here, so every spelling, message and exit code is unchanged; the
        # `Usage: ./run.sh www ...` lines it prints still name this script, because
        # that is still how a person reaches it.
        # .ci/rediacc_ci/tests/gates/test_gate_media_entry.py drives a real
        # run.sh -> media-entry.sh -> module call and fails if this delegation stops
        # landing on the function that used to be here. THESE TWO ARMS STAY IN THE
        # ROUTER for that reason and one other: the sandbox that test drives copies
        # run.sh and media.sh and symlinks the rest of .ci, so a media verb that
        # reached the legacy file would step outside the sandbox it is being tested in.
        #
        # exec, NOT a call: the pipeline's exit code is then its own rather than
        # something this script has to forward, and a multi-hour render is not holding
        # a parent shell open for nothing. "$@" keeps the leading `www` because
        # media_entry_main matches on it.
        www) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;

        *)
            # `${ARR[@]+"${ARR[@]}"}` and not `"${ARR[@]}"`: under `set -u` an empty array
            # expansion is an unbound-variable error on bash before 4.4 (the bash on
            # macOS), so the plain form would abort on the empty table this file ships with.
            local ported
            for ported in ${PORTED_VERBS[@]+"${PORTED_VERBS[@]}"}; do
                [[ "${1:-}" == "$ported" ]] && run_ported "$@"
            done

            # SAY WHICH FILE IS MISSING. Otherwise the failure is `./run.sh: line N:
            # ...: No such file or directory`, naming this file and not the absent one.
            if [[ ! -x "$LEGACY_RUNNER" ]]; then
                echo "run.sh: the legacy runner is missing or not executable: $LEGACY_RUNNER" >&2
                echo "run.sh: every verb this router does not serve itself lives there." >&2
                exit 1
            fi

            # exec, not source and not a subshell. One process, so the exit code, the
            # signals and the terminal belong to the legacy script -- `devbox shell`
            # and `account dev` both hand a terminal to a child and would notice.
            exec "$LEGACY_RUNNER" "$@"
            ;;
    esac
}

# An `if` block, not `[[ … ]] && main "$@"`. With the `&&` form the whole file's exit
# status is the FAILED test when the file is SOURCED, so `source ./run.sh` returned 1
# and killed any caller running under `set -e` -- silently, because nothing had failed.
# The legacy file carries the same guard; not a copy for symmetry, the same defect.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
