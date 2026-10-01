#!/bin/bash
# ./run.sh -- the router. Two destinations, and no logic of its own.
#
# `provision` and `www` go to `.ci/media/media-entry.sh`, which stays bash by design (see below).
# Every other verb, and no verb at all, goes to `python3 -m rediacc_ci`, whose VERBS table in
# `.ci/rediacc_ci/__main__.py` is the one list of what exists. `.ci/legacy/run-legacy.sh`, the
# bash dispatcher that served service, account, rotation, worktree, devbox, drill, quality, fix,
# clean and help, was deleted once its verb table was empty; its verbs are the entry functions in
# `.ci/rediacc_ci/core/run_verbs.py`.
#
# NOT A PLACE FOR LOGIC. Anything that is not "which implementation runs this verb" belongs on
# one side or the other; a router that grows a special case has quietly become a third
# implementation, which is what the gate test's line ceiling is for.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

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
        # reached the Python package would step outside the sandbox it is being tested in.
        #
        # exec, NOT a call: the pipeline's exit code is then its own rather than
        # something this script has to forward, and a multi-hour render is not holding
        # a parent shell open for nothing. "$@" keeps the leading `www` because
        # media_entry_main matches on it.
        www) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;

        *) run_ported "$@" ;;
    esac
}

# An `if` block, not `[[ … ]] && main "$@"`. With the `&&` form the whole file's exit
# status is the FAILED test when the file is SOURCED, so `source ./run.sh` returned 1
# and killed any caller running under `set -e` -- silently, because nothing had failed.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    main "$@"
fi
