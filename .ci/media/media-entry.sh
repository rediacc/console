#!/bin/bash
# The one entry point for the media pipeline. Every .sh file BESIDE it is a library that
# defines functions and nothing else, which is what makes each module testable by sourcing
# it with no daemon, no toolchain and no network present. The two standalone programs the
# folder also owns live under tools/ (run-in-tts.sh, upload-r2.sh) precisely so that
# "everything at this level is sourced, never executed" stays a true statement a reader can
# rely on rather than one they have to check.
#
# tools/ AND NOT bin/, WHICH IS NOT A STYLE CHOICE. .gitignore line 6 is a bare `bin/`, and
# git matches that against a directory of that name at ANY depth, so a `bin` directory beside this one was
# silently ignored: `git status` showed nothing, `git ls-files` showed nothing, and both
# relocated programs would have been absent from a fresh clone while every shim in the tree
# exec'd them. Caught on 2026-09-06 by `git check-ignore -v`, which is the only thing that
# says so out loud. Renaming the directory was the safe half of the fix; narrowing that
# pattern to `/bin/` is a repository-wide decision and belongs to whoever owns .gitignore.
#
# WHY THIS FOLDER EXISTS. run.sh was 2,647 lines and roughly 1,300 of them were this
# pipeline. Phase 2 moved them here, and the router split that followed on the same day
# moved everything else to .ci/legacy/run-legacy.sh, so run.sh itself is now a router of
# about 120 lines that execs one of three destinations. Do not read a line count for run.sh
# out of this paragraph; read the file. The pipeline drives private/generative and
# private/growth, which are separate gitignored repositories rather than submodules, so it
# cannot be ported to Python with the rest of the tooling and is deliberately staying bash.
# Moving it out of run.sh was therefore the only maintainability move available: one module
# per subject, and a gate test per module that can actually run in CI.
#
# THIS FILE CHANGED NO BEHAVIOUR. The functions it dispatches to were moved from run.sh
# byte for byte in phase 1, while run.sh kept its own copies; the dispatch tree below was
# written as a verb-for-verb MIRROR of run.sh's `provision` and `www` case arms precisely
# so that phase 2 would be a deletion rather than a translation, and it was.
#
# run.sh now `exec`s this file for both of those verbs and defines none of the functions.
# .ci/rediacc_ci/tests/gates/test_gate_media_entry.py no longer compares the two dispatch trees --
# one of them is empty -- and instead drives each routed verb from a real ./run.sh in a
# sandbox repo, requiring it to arrive inside the module function that owns it. Every
# `Usage: ./run.sh ...` string below still names run.sh, because that is still how a
# person reaches this surface; the exec is an implementation detail and nobody types
# media-entry.sh.
#
# The `growth` verb has no counterpart in run.sh: it is media.sh, whose three operations
# moved into .ci/media/teaser.sh for the same reason, and which is now itself three lines
# that exec into here.

set -euo pipefail

MEDIA_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$MEDIA_DIR/../.." && pwd)"

source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"

# portable.sh IS SOURCED FIRST and is not in the alphabetical list below, because it is
# not a subject module: it is the seam layer where this pipeline names a non-portable
# system tool, and every other module is entitled to have it in scope already. First
# rather than alphabetical so a reader does not have to check whether the order matters.
source "$MEDIA_DIR/portable.sh"

# ORDER MATTERS IN EXACTLY ONE PLACE: tutorials.sh calls into every other module, so
# it is sourced last. The rest are independent of each other with one edge --
# venv.sh's install_generative_python_deps calls cuda.sh's
# install_flash_attn_if_supported -- and because these are function DEFINITIONS, not
# calls, that edge is resolved at call time and does not constrain the order either.
# The list is alphabetical apart from tutorials.sh so a reader can see nothing is
# missing.
source "$MEDIA_DIR/bridge.sh"
source "$MEDIA_DIR/cuda.sh"
source "$MEDIA_DIR/pool.sh"
source "$MEDIA_DIR/r2.sh"
source "$MEDIA_DIR/teaser.sh"
source "$MEDIA_DIR/venv.sh"
source "$MEDIA_DIR/tutorials.sh"

media_entry_usage() {
    cat >&2 <<'USAGE'
Usage: .ci/media/media-entry.sh <command> ...

  provision [start|stop|status]
  www tutorials [record|extract|scaffold-locales|generate|video|media|watch|validate|all]
  www all
  growth [run|teaser|luma]
USAGE
}

media_entry_main() {
    case "${1:-}" in
        # VM Provisioning
        provision)
            shift
            case "${1:-}" in
                start)
                    shift
                    provision_start "$@"
                    ;;
                stop) provision_stop ;;
                status) provision_status ;;
                *)
                    log_error "Unknown provision command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh provision [start|stop|status]"
                    exit 1
                    ;;
            esac
            ;;

        www)
            shift
            case "${1:-}" in
                tutorials)
                    shift
                    case "${1:-}" in
                        record)
                            shift
                            www_tutorials_record "$@"
                            ;;
                        extract) www_tutorials_extract ;;
                        scaffold-locales) www_tutorials_scaffold_locales ;;
                        generate)
                            shift
                            www_tutorials_generate "$@"
                            ;;
                        video)
                            shift
                            www_tutorials_video "$@"
                            ;;
                        media)
                            shift
                            www_tutorials_media "$@"
                            ;;
                        watch)
                            shift
                            www_tutorials_watch "$@"
                            ;;
                        validate) www_tutorials_validate ;;
                        all)
                            shift
                            www_tutorials_all "$@"
                            ;;
                        *)
                            log_error "Unknown tutorials command: ${1:-}"
                            echo ""
                            echo "Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|media|watch|video|validate|all]"
                            exit 1
                            ;;
                    esac
                    ;;
                all)
                    shift
                    www_all "$@"
                    ;;
                *)
                    log_error "Unknown www command: ${1:-}"
                    echo ""
                    echo "Usage: ./run.sh www [all|tutorials] ..."
                    exit 1
                    ;;
            esac
            ;;

        # The private/growth wrapper that was media.sh.
        growth)
            shift
            case "${1:-}" in
                run)
                    shift
                    growth_run "$@"
                    ;;
                teaser)
                    shift
                    growth_teaser "$@"
                    ;;
                luma)
                    shift
                    growth_luma "$@"
                    ;;
                *)
                    growth_usage
                    exit 1
                    ;;
            esac
            ;;

        *)
            media_entry_usage
            exit 1
            ;;
    esac
}

# SOURCEABLE FOR TESTS, EXECUTABLE FOR PEOPLE. A gate test needs the dispatch tree in
# scope to interrogate it without running a pipeline, and `${BASH_SOURCE[0]}` differs
# from `$0` exactly when this file was sourced rather than run.
if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
    media_entry_main "$@"
fi
