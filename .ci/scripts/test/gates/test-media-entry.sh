#!/bin/bash
# ---- gate ----
# kind: battery
# step: Quality-gate unit tests
# needs: none
# lane: quality-security
# blocker: BLOCKER: rides the hand-written "Quality-gate unit tests" step, which all 148 gate-tests share and none owns, so no gate-bind region may emit it
# why: Tests for .ci/media/media-entry.sh -- the one entry point for the media pipeline
# ---- end gate ----

# Tests for .ci/media/media-entry.sh -- the one entry point for the media pipeline.
#
# THE ASSERTION THIS FILE EXISTS FOR IS THE DELEGATION.
#
# Before the cutover run.sh carried its own copy of the media surface, and this file
# compared the two dispatch trees as SETS, in both directions, because the deletion that
# was coming was only safe if they routed the same verbs to the same functions. That
# comparison is spent: phase 2 deleted run.sh's arms, so one of the two sets is now empty
# by construction and comparing them would agree with itself forever.
#
# What replaces it is the thing the mirror was a proxy for. run.sh routes the whole media
# surface by `exec`ing this file, so the question is whether a verb typed at run.sh still
# lands on the module function that used to be inside run.sh -- and that is DRIVEN, not
# inferred: a sandbox repo, a real ./run.sh invocation, a marker planted inside the module
# function's own body, once per routed verb. Two structural assertions bracket it: run.sh
# must route NO media function itself (it has no copies left to route to), and every verb
# this file routes must be owned by a .ci/media module.
#
# Everything runs with docker, node, npm, nvcc, aws and ssh absent -- the chain needs
# `uname` and `dirname` and nothing else. The dispatch case sources the entry point -- it
# is written to be sourceable for exactly this -- replaces each verb with a recorder, and
# drives the tree.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

ENTRY="$ROOT/.ci/media/media-entry.sh"

# dispatched_media_functions <text-file>
#
# The media functions a dispatch tree actually calls. Fed the DISPATCH REGION of a file,
# never the whole file: run.sh both defines and calls these, and a definition is not a
# route.
dispatched_media_functions() {
    grep -oE '(provision_(start|stop|status)|www_tutorials_[a-z_]+|www_all)' "$1" | sort -u
}

test_the_entry_point_and_its_modules_all_exist() {
    [ -x "$ENTRY" ] || log_fail "media-entry.sh is not executable: $ENTRY"
    local m sourced=0
    while IFS= read -r m; do
        [ -f "$ROOT/.ci/media/$m" ] || log_fail "media-entry.sh sources a module that does not exist: $m"
        sourced=$((sourced + 1))
    done < <(grep -oE 'source "\$MEDIA_DIR/[a-z0-9-]+\.sh"' "$ENTRY" | sed 's|.*/||; s|"$||')
    # Anti-vacuity: an extraction that stopped matching would report every module present.
    [ "$sourced" -ge 7 ] || log_fail "media-entry.sh sources only $sourced module(s); the extraction has collapsed or the split has"
    log_pass "media-entry.sh is executable and every one of its $sourced sourced modules exists"
}

test_the_whole_media_surface_is_delegated_and_this_file_owns_it() {
    local d="$1"
    # run.sh's dispatch region is main() to end of file; the entry point's is one function.
    sed -n '/^main() {/,$p' "$ROOT/run.sh" >"$d/run-dispatch"
    fidelity_extract "$ENTRY" media_entry_main >"$d/entry-dispatch" ||
        log_fail "media_entry_main() could not be extracted from $ENTRY"

    dispatched_media_functions "$d/entry-dispatch" >"$d/entry-set"

    # ANTI-VACUITY FIRST, because every claim below is about a SET BEING EMPTY, and an
    # extraction that matched nothing satisfies all of them at once. Pin the floor on the
    # side that must be full before asserting anything about the side that must be empty.
    local n
    n="$(wc -l <"$d/entry-set")"
    [ "$n" -ge 10 ] || log_fail "only $n media function(s) found in media_entry_main; the extraction is broken, so nothing below proves anything"

    # run.sh must route NONE of them. It has no definitions left to route to, so a call
    # left behind here would be a 127 waiting for whoever types the verb.
    # `|| true`: an EMPTY result is the passing case here, and grep exits 1 when it
    # matches nothing. Without the guard this file's own `set -e` ended the run silently
    # on the green path -- one PASS printed, exit 1, no message.
    local still_in_run
    still_in_run="$(dispatched_media_functions "$d/run-dispatch" || true)"
    assert_eq "$still_in_run" "" "run.sh's dispatch tree still calls these media functions, which it no longer defines"

    # And the arms that carried them must now exec this file. Both are checked by name: a
    # `www` arm that delegated while `provision` quietly kept a stale copy is exactly the
    # half-done cutover this catches.
    local arm
    for arm in provision www; do
        grep -qF "        $arm) exec \"\$ROOT_DIR/.ci/media/media-entry.sh\" \"\$@\" ;;" "$ROOT/run.sh" ||
            log_fail "run.sh's '$arm' arm does not exec .ci/media/media-entry.sh"
    done
    grep -qF 'exec "$ROOT/.ci/media/media-entry.sh" growth "$@"' "$ROOT/media.sh" ||
        log_fail "media.sh does not exec .ci/media/media-entry.sh's growth arm"

    # Every verb this file routes must be owned by one of the modules beside it.
    local fn owner found
    while IFS= read -r fn; do
        found=""
        for owner in "$ROOT"/.ci/media/*.sh; do
            [ "$owner" = "$ENTRY" ] && continue
            media_defines "$owner" "$fn" && found="$(basename "$owner")"
        done
        [ -n "$found" ] || log_fail "media_entry_main routes $fn(), which no module in .ci/media defines"
    done <"$d/entry-set"

    log_pass "media_entry_main routes $n media functions, each owned by a module beside it; run.sh routes none and execs here for both provision and www, and so does media.sh"
}

test_the_delegation_assertion_can_fail() {
    # CONTROL, on both halves. Put a media call back into a copy of run.sh's dispatch tree
    # and the "routes none" check must see it; take the exec out and the arm check must.
    local d="$1"
    sed 's|^        www) exec .*|        www) www_tutorials_extract "$@" ;;|' "$ROOT/run.sh" >"$d/mutant-run.sh"
    local leaked
    leaked="$(sed -n '/^main() {/,$p' "$d/mutant-run.sh" | dispatched_media_functions /dev/stdin || true)"
    assert_eq "$leaked" "www_tutorials_extract" "a media call put back into run.sh must show up in the routed set"
    grep -qF '        www) exec "$ROOT_DIR/.ci/media/media-entry.sh" "$@" ;;' "$d/mutant-run.sh" &&
        log_fail "the mutant still execs media-entry.sh from its www arm, so this control tested nothing"
    log_pass "the delegation assertion fires when a media call reappears in run.sh and when the exec is removed"
}

test_the_usage_line_lives_in_exactly_one_place() {
    # The guidance still names ./run.sh, because that is still how a person reaches this
    # surface -- the exec is an implementation detail and nobody types media-entry.sh.
    # What changed is that there is now ONE copy of the string: run.sh must not carry a
    # second one to drift from.
    local needle="Usage: ./run.sh www tutorials [record|extract|scaffold-locales|generate|media|watch|video|validate|all]"
    grep -qF "$needle" "$ENTRY" || log_fail "media-entry.sh no longer carries the tutorials usage line"
    media_assert_absent_from_origins -F "$needle" "$ROOT" \
        "an origin carries a second copy of the tutorials usage line, which will fork from the one that prints"
    log_pass "the tutorials usage line still names ./run.sh, and exists only in media-entry.sh"
}

# EVERY ROUTED VERB, DRIVEN FOR REAL. script | argv | module | function | expected "$*".
# This is the assertion that replaced the mirror: the mirror compared two lists of names,
# this runs the operator's actual command and requires it to arrive inside the module
# function's own body. Every verb media_entry_main routes appears here, and the count is
# floored below so a row silently disappearing is a finding.
ROUTES=(
    "run.sh|provision start --basic|bridge.sh|provision_start|--basic"
    "run.sh|provision stop|bridge.sh|provision_stop|"
    "run.sh|provision status|bridge.sh|provision_status|"
    "run.sh|www tutorials record --force installation|tutorials.sh|www_tutorials_record|--force installation"
    "run.sh|www tutorials extract|tutorials.sh|www_tutorials_extract|"
    "run.sh|www tutorials scaffold-locales|tutorials.sh|www_tutorials_scaffold_locales|"
    "run.sh|www tutorials generate --lang de|tutorials.sh|www_tutorials_generate|--lang de"
    "run.sh|www tutorials video --jobs 2|tutorials.sh|www_tutorials_video|--jobs 2"
    "run.sh|www tutorials media --langs en,de|tutorials.sh|www_tutorials_media|--langs en,de"
    "run.sh|www tutorials watch --once|tutorials.sh|www_tutorials_watch|--once"
    "run.sh|www tutorials validate|tutorials.sh|www_tutorials_validate|"
    "run.sh|www tutorials all installation|tutorials.sh|www_tutorials_all|installation"
    "run.sh|www all installation|tutorials.sh|www_all|installation"
    "media.sh|run video_pipeline|teaser.sh|growth_run|video_pipeline"
    "media.sh|teaser safe-os-testing ru|teaser.sh|growth_teaser|safe-os-testing ru"
    "media.sh|luma /tmp/nothing.mp4|teaser.sh|growth_luma|/tmp/nothing.mp4"
)

_case_one_route_reaches_its_module() {
    local repo="$1" script="$2" argv="$3" fn="$4" expected="$5"
    # UNQUOTED ON PURPOSE: the table stores one argv per row as a single string, and this
    # is where it becomes separate arguments.
    # shellcheck disable=SC2086
    media_chain_run "$repo" "$script" $argv ||
        log_fail "./$script $argv failed in the sandbox: $LAST_CHAIN"
    assert_eq "$LAST_CHAIN" "MEDIA_CHAIN_REACHED:$fn:$expected" \
        "./$script $argv must arrive inside $fn() with its arguments intact"
}

test_every_routed_verb_reaches_the_module_that_owns_it() {
    local d="$1" repo rec script argv module fn expected n=0
    repo="$(media_chain_sandbox "$d")"
    for rec in "${ROUTES[@]}"; do
        IFS='|' read -r script argv module fn expected <<<"$rec"
        media_chain_probe "$repo" "$module" "$fn" ||
            log_fail "could not plant a probe for $fn() in $module"
        with_fake_bin "+uname +dirname" _case_one_route_reaches_its_module "$repo" "$script" "$argv" "$fn" "$expected"
        n=$((n + 1))
    done
    # FLOOR, because a table that lost rows would still pass every row it kept.
    [ "$n" -ge 16 ] || log_fail "only $n route(s) were driven; the table has lost rows and its green covers less than it claims"
    log_pass "all $n routed verbs cross run.sh's (or media.sh's) exec and arrive inside the module function that owns them"
}

_case_the_chain_stops_when_the_exec_goes() {
    local repo="$1"
    local rc=0
    media_chain_run "$repo" run.sh www tutorials extract || rc=$?
    assert_exit_code 9 "$rc" "the mutated run.sh must reach its own replacement arm, not the module"
    assert_not_contains "$LAST_CHAIN" "MEDIA_CHAIN_REACHED" "with the exec gone, no marker may be reported"
}

test_the_chain_probe_can_fail() {
    # CONTROL FOR THE SIXTEEN ROWS ABOVE. Plant the marker exactly as they do, then take
    # run.sh's exec out. If the marker still appeared, every green above would be
    # measuring something other than the delegation.
    local d="$1" repo
    repo="$(media_chain_sandbox "$d")"
    media_chain_probe "$repo" tutorials.sh www_tutorials_extract
    media_chain_mutate "$repo" run.sh 's|^        www) exec .*|        www) exit 9 ;;|'
    with_fake_bin "+uname +dirname" _case_the_chain_stops_when_the_exec_goes "$repo"
    log_pass "the chain probe goes quiet the moment run.sh stops exec-ing media-entry.sh"
}

# STUBS replaces every verb the tree routes to. Sourcing the entry point defines them
# from the real modules first; these override them, so what is under test is the routing.
STUBS='
provision_start() { echo "provision_start: $*"; }
provision_stop() { echo "provision_stop"; }
provision_status() { echo "provision_status"; }
www_tutorials_record() { echo "record: $*"; }
www_tutorials_extract() { echo "extract"; }
www_tutorials_scaffold_locales() { echo "scaffold"; }
www_tutorials_generate() { echo "generate: $*"; }
www_tutorials_video() { echo "video: $*"; }
www_tutorials_media() { echo "media: $*"; }
www_tutorials_watch() { echo "watch: $*"; }
www_tutorials_validate() { echo "validate"; }
www_tutorials_all() { echo "all: $*"; }
www_all() { echo "www_all: $*"; }
growth_run() { echo "growth_run: $*"; }
growth_teaser() { echo "growth_teaser: $*"; }
growth_luma() { echo "growth_luma: $*"; }
'

LAST_ENTRY=""
drive_entry() {
    local rc=0
    LAST_ENTRY="$("$BASH" -c "
        source '$ENTRY'
        $STUBS
        media_entry_main $1" 2>&1)" || rc=$?
    return "$rc"
}

_case_every_verb_reaches_its_function() {
    drive_entry "provision start --basic" || log_fail "provision start failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "provision_start: --basic" "provision start forwards its arguments"

    drive_entry "www tutorials record --force installation" || log_fail "record failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "record: --force installation" "record forwards its arguments"

    drive_entry "www tutorials extract" || log_fail "extract failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "extract" "extract takes no arguments"

    drive_entry "www tutorials media --langs en,de" || log_fail "media failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "media: --langs en,de" "media forwards its arguments"

    drive_entry "www all installation" || log_fail "www all failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "www_all: installation" "www all forwards its arguments"

    drive_entry "growth teaser safe-os-testing ru" || log_fail "growth teaser failed: $LAST_ENTRY"
    assert_eq "$LAST_ENTRY" "growth_teaser: safe-os-testing ru" "the private/growth wrapper forwards its arguments"
}

_case_unknown_verbs_are_refused() {
    local rc=0
    drive_entry "nosuchsurface" || rc=$?
    assert_exit_code 1 "$rc" "an unknown top-level verb must exit 1"
    assert_contains "$LAST_ENTRY" "provision" "the usage names the surfaces it does route"

    rc=0
    drive_entry "www tutorials nosuchverb" || rc=$?
    assert_exit_code 1 "$rc" "an unknown tutorials verb must exit 1"
    assert_contains "$LAST_ENTRY" "Unknown tutorials command: nosuchverb" "names the verb it refused"

    rc=0
    drive_entry "growth nosuchverb" || rc=$?
    assert_exit_code 1 "$rc" "an unknown growth verb must exit 1"
    assert_contains "$LAST_ENTRY" "cwd = private/growth" "falls back to media.sh's own usage text"
}

test_the_tree_routes_and_refuses() {
    # No fixture root: the entry point resolves ROOT_DIR from its own location, which is
    # the real repo, and every verb it would reach is replaced above. Nothing runs.
    _case_every_verb_reaches_its_function
    _case_unknown_verbs_are_refused
    log_pass "every verb reaches its own function with its arguments intact, and unknown verbs are refused"
}

log_test "test-media-entry"
test_the_entry_point_and_its_modules_all_exist
with_temp_dir test_the_whole_media_surface_is_delegated_and_this_file_owns_it
with_temp_dir test_the_delegation_assertion_can_fail
test_the_usage_line_lives_in_exactly_one_place
with_temp_dir test_every_routed_verb_reaches_the_module_that_owns_it
with_temp_dir test_the_chain_probe_can_fail
test_the_tree_routes_and_refuses
echo ""
log_pass "all tests passed"
