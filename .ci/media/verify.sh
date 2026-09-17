#!/bin/bash
# Verification support for the media pipeline: the proof that a verb typed at run.sh or
# media.sh still lands on the .ci/media function that used to be inside them, and the
# sandbox the behaviour tests run those functions in. Sourced by
# .ci/scripts/test/gates/test-media-*.sh and by nothing else.
#
# WHAT THIS FILE USED TO PROVE, AND WHY THAT PROOF IS GONE.
#
# Phase 1 of the split copied 35 functions out of run.sh and three out of media.sh into
# seven modules WITHOUT deleting the originals, so for one phase both copies existed and
# the whole risk was silent drift between them. The proof that fitted that phase was
# byte-identity: fidelity_assert_same lifted each function's body out of BOTH files and
# compared the bytes, so a lost `local`, a changed default or a dropped `|| true` was red
# rather than merely different. fidelity_assert_equivalent did the same job for media.sh,
# whose three functions cannot be byte-identical to shfmt-formatted copies, by comparing
# what bash's own parser makes of each.
#
# Phase 2 deleted the originals. There is no second copy left to drift from, so BOTH of
# those helpers were removed rather than left pointing at an absent function: kept, they
# would either crash on every call or -- far worse -- be "fixed" by someone loosening the
# extraction until two empty strings compared equal, which is the exact vacuity the old
# header warned about. A comparison whose right-hand side no longer exists is not a
# weakened assertion, it is a decorative one.
#
# WHAT REPLACES IT. The question phase 1 asked was "did the copy drift". After the
# cutover the equivalent question is "does the delegation still reach the function that
# used to be here", and it is answered two ways:
#
#   media_assert_sole_owner  -- STRUCTURE. Exactly one file defines the function, it is
#                               the module under test, run.sh and media.sh no longer
#                               define it, and sourcing media-entry.sh resolves the name
#                               to that module's body and not to some other copy.
#   media_chain_probe/run    -- BEHAVIOUR. A real ./run.sh (or ./media.sh) invocation in
#                               a sandbox repo, driven all the way through the exec into
#                               media-entry.sh and into the module file, proved by a
#                               marker planted inside the function body itself. Delete
#                               the exec from run.sh, or rename the function in the
#                               module, and the marker does not appear.
#
# THE VACUITY TRAP IS THE SAME ONE, so it is guarded the same way. Extraction still fails
# loudly on a name it cannot find, every set comparison is preceded by a floor on its
# size, and each module's gate test plants a mutation and requires the assertion to fire,
# because a comparison that has never been seen to fail is a comparison nobody has
# checked.
#
# WHY IT LIVES HERE and not under .ci/scripts/test/lib/: it is the proof that this folder
# is what the operator's commands actually run, so it belongs beside the thing it is
# proving, and it has to stay correct as the modules change.

# fidelity_extract <file> <function-name>
#
# Prints the function's body: the `name() {` line through the closing `}` in column 0.
# Column 0 is what makes this unambiguous -- every nested block in these files closes
# indented, and shfmt (-i 4 -ci, enforced by check:ci-shell-format over .ci/**) is what
# keeps that true. Exits 1, with a reason on stderr, when the name is not found or its
# body never closes.
fidelity_extract() {
    local file="$1" name="$2"
    [ -f "$file" ] || {
        echo "fidelity_extract: no such file: $file" >&2
        return 1
    }
    awk -v NAME="$name" -v FILE="$file" '
        { lines[NR] = $0 }
        $0 == NAME "() {" && start == 0 { start = NR }
        END {
            if (start == 0) {
                print "fidelity_extract: " NAME "() not defined in " FILE > "/dev/stderr"
                exit 1
            }
            for (j = start + 1; j <= NR; j++) {
                if (lines[j] == "}") { close_at = j; break }
            }
            if (close_at == 0) {
                print "fidelity_extract: " NAME "() in " FILE " never closes at column 0" > "/dev/stderr"
                exit 1
            }
            for (k = start; k <= close_at; k++) print lines[k]
        }
    ' "$file"
}

# fidelity_extract_any <file> <function-name>
#
# fidelity_extract, widened to the ONE-LINE definition form `name() { ...; }`. media.sh
# wrote `die` that way before the cutover, and a block-only extractor reported it
# missing -- which under a naive comparison read as "both sides empty, therefore equal",
# the precise vacuity this file exists to refuse. media.sh no longer defines anything, so
# the form survives only in prose today; the widening stays because media_assert_sole_owner
# uses this to ASK WHETHER A FILE STILL DEFINES A NAME, and a definition written on one
# line would otherwise be invisible to exactly the check that must not miss it.
fidelity_extract_any() {
    local file="$1" name="$2"
    if grep -qE "^${name}\(\) \{.*\}\$" "$file"; then
        grep -E "^${name}\(\) \{.*\}\$" "$file"
        return 0
    fi
    fidelity_extract "$file" "$name"
}

# RESOLVED AT SOURCE TIME, NOT AT CALL TIME. Callers invoke this from inside
# with_fake_bin, where PATH holds only what the test named -- and `dirname` is not on
# anybody's list. Resolving here, while the caller's real PATH is still in effect, is the
# difference between a working sandbox and "dirname: command not found" reported as the
# module's exit code.
MEDIA_VERIFY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEDIA_VERIFY_ROOT="$(cd "$MEDIA_VERIFY_DIR/../.." && pwd)"

# env(1), resolved here for the same reason and used by exactly one caller. The chain probe
# has to launch ./run.sh with SHELLOPTS in its environment, which no assignment prefix can
# do -- bash refuses `SHELLOPTS=xtrace cmd` because SHELLOPTS is readonly -- so it needs the
# real program. Chain runs happen inside with_fake_bin, where PATH holds only what the test
# named, and `env` is on nobody's list; measured 2026-09-06, three gate tests failed under
# the coverage probe with "env: command not found" before this line existed. Empty when
# there is no env at all, in which case the probe silently skips tracing chain runs rather
# than breaking them.
MEDIA_ENV_BIN="$(command -v env || true)"

# THE MEDIA GATE TESTS' WHOLE PROLOGUE, AND WHY IT LIVES HERE.
#
# Every .ci/scripts/test/gates/test-media-*.sh opened with the same five lines: set the
# shell options, resolve SCRIPT_DIR, source test-helpers.sh, resolve ROOT four levels up,
# source this file. check:ci-shape-duplication reported that block at SEVEN copies, which
# is the correct reading of it: five identical lines whose only purpose is to find this
# file. A test now says `source .../verify.sh` and gets ROOT and the assertion helpers
# with it.
#
# ROOT IS ASSIGNED, NOT DEFAULTED FROM THE CALLER. A test that wanted a different root
# would be pointing the ownership assertions at a tree this file did not come from, which
# is not a configuration, it is a bug. The sandbox case is served by the ROOT-taking
# parameter on media_assert_sole_owner instead.
#
# test-helpers.sh guards against double-sourcing itself, so a test that still sources it
# directly (every non-media gate test does) is unaffected.
ROOT="$MEDIA_VERIFY_ROOT"
# shellcheck source=../scripts/test/lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$MEDIA_VERIFY_ROOT/.ci/scripts/test/lib/test-helpers.sh"

# media_origins <repo-root>
#
# Prints every file a moved media function or constant could be hiding in, one absolute
# path per line, and FAILS if any of them is missing.
#
# ONE LIST, BECAUSE FOUR HAND-MAINTAINED COPIES IS WHAT WENT WRONG. The 2026-09-06 router
# split moved every verb body out of run.sh into .ci/legacy/run-legacy.sh, which made that
# file a third origin overnight; four separate absence assertions had to be widened by
# hand to notice, and missing one of them would not have shown up as a failure. Adding a
# fourth origin is now one line here.
#
# IT REFUSES A MISSING ORIGIN RATHER THAN SKIPPING IT, and that is the point of the
# function. An absence assertion over a file that is not there passes for free in both
# spellings used here: media_defines returns 1 on a missing file, and `grep -q pat a b`
# with b absent exits 2 while writing to stderr. Both read as "the name is not there" when
# what happened is "nobody looked". Measured 2026-09-06 in a sandbox: deleting
# run-legacy.sh left media_assert_sole_owner green with its legacy arm doing nothing at
# all. Renaming that file is an ordinary thing for the bootstrap workstream to do, and
# quietly losing a third of this proof when it happens is not acceptable.
MEDIA_ORIGIN_RELPATHS=(run.sh media.sh .ci/legacy/run-legacy.sh)
media_origins() {
    local root="$1" rel missing=0
    for rel in "${MEDIA_ORIGIN_RELPATHS[@]}"; do
        if [ ! -f "$root/$rel" ]; then
            echo "media_origins: $root/$rel does not exist -- an absence assertion over a file nobody read is not absence, so this is a finding rather than a skip" >&2
            missing=1
            continue
        fi
        printf '%s\n' "$root/$rel"
    done
    [ "$missing" -eq 0 ]
}

# media_assert_absent_from_origins [-F] <grep-pattern> <repo-root> <message>
#
# The non-function half of the cutover invariant. TUTORIAL_COLS, _BRIDGE_SSH_CONFIG and
# the tutorials usage string are not functions, so media_assert_sole_owner cannot see
# them; this asserts the same thing for a pattern, over the same origin set, with the same
# refusal to treat a missing origin as a clean one.
#
# -F FORWARDS TO grep, and it is not decoration. The usage-line check hunts a fixed string
# containing `[record|extract|...]`, which as a basic regular expression is a bracket
# expression matching one character, so the un-flagged form would be looking for something
# else entirely and would answer "not present" whatever the file held.
media_assert_absent_from_origins() {
    local fixed=()
    if [ "${1:-}" = "-F" ]; then
        fixed=(-F)
        shift
    fi
    local pattern="$1" root="$2" msg="$3" list line
    list="$(media_origins "$root")" ||
        log_fail "$msg: the origin set is incomplete, so absence could not be established"
    local origins=()
    while IFS= read -r line; do origins+=("$line"); done <<<"$list"
    if grep -q ${fixed[0]+"${fixed[@]}"} -- "$pattern" "${origins[@]}"; then
        log_fail "$msg"
    fi
}

# media_run_module <root-dir> <modules> <code>
#
# Runs <code> against the named .ci/media modules in a FRESH bash, with ROOT_DIR set to
# <root-dir> and the real log_* helpers from .ci/scripts/lib/common.sh in scope. Output
# (stdout and stderr merged) lands in LAST_OUT; the return value is the code's.
#
# A FRESH SHELL RATHER THAN A SUBSHELL, for two reasons that both bit during writing:
# the functions under test call `exit`, which in a plain subshell ends the enclosing test
# rather than the code under test; and common.sh sets `set -euo pipefail`, which is what
# run.sh does too, so a fresh shell is also the honest environment rather than a
# convenient one.
#
# It inherits PATH, so a caller inside with_fake_bin gets the emptied PATH here too --
# which is the entire point. <modules> is a space-separated list of file names relative
# to .ci/media, sourced in the order given, so a test states its own dependency edges
# instead of pulling the whole folder in.
#
# THE MODULES COME FROM $MEDIA_MODULE_DIR, which defaults to this folder. That seam is
# how a test drives a MUTATED copy: it writes one altered module into a temp directory,
# points MEDIA_MODULE_DIR at it, re-runs the same probe, and requires the result to
# change. Without it a behaviour test could only ever run the module that is already
# green, and "this assertion would fail if the code were wrong" would be an assumption
# rather than something the test file has watched happen.
#
# ONE COMMAND IS ALWAYS REQUIRED: common.sh runs `CI_OS="$(detect_os)"` at source time
# (.ci/scripts/lib/common.sh:479), and detect_os shells out to `uname`. A caller inside
# with_fake_bin must therefore admit `+uname`, or every run carries a stray
# "uname: command not found" on stderr -- harmless to the code under test, and exactly
# the kind of noise that makes a real failure hard to read.
# THE COVERAGE SEAM. When MEDIA_COVERAGE_FILE names a file, the two functions below turn
# xtrace on INSIDE the shell that runs the module and send it to a descriptor opened onto
# that file. Off by default and invisible when off.
#
# WHY IT IS HERE AND NOT `SHELLOPTS=xtrace` AROUND THE WHOLE SUITE, which is what was tried
# first and measured on 2026-09-06: forcing xtrace into every child shell makes eight of the
# ten media gate tests FAIL. It is not a defect in them. media_run_module captures merged
# stdout and stderr into LAST_OUT and the behaviour cases assert on that text, so a probe
# that writes trace onto those streams is changing what the subject observes. Scoped here,
# the trace goes to its own descriptor and LAST_OUT is byte-identical with the probe on and
# off -- which .ci/scripts/test/gates/test-media-docs.sh asserts rather than assumes.
#
# THE PRELUDE IS TEXT, spliced into the code string, because the option has to be set INSIDE
# the fresh shell: SHELLOPTS is readonly in a running bash, so it can only be inherited from
# an environment, and inheriting it is precisely the thing that perturbs.
_media_coverage_prelude() {
    [ -n "${MEDIA_COVERAGE_FILE:-}" ] || return 0
    # ${BASH_SOURCE:-} AND NOT ${BASH_SOURCE}. common.sh sets `set -u`, and at the top level
    # of a `bash -c` string BASH_SOURCE is unset, so the bare form makes the FIRST traced
    # command die with "BASH_SOURCE: unbound variable" -- an empty trace file and a failed
    # run, which is exactly what it did on 2026-09-06 before this default was added.
    printf "exec 9>>'%s'; BASH_XTRACEFD=9; PS4='+|\${BASH_SOURCE:-}|\${LINENO}|'; set -x;" \
        "$MEDIA_COVERAGE_FILE"
}

LAST_OUT=""
media_run_module() {
    local root_dir="$1" modules="$2" code="$3"
    local media_dir="${MEDIA_MODULE_DIR:-$MEDIA_VERIFY_DIR}" repo_root="$MEDIA_VERIFY_ROOT" srcs="" m rc=0
    # portable.sh ALWAYS, and always from the REAL folder rather than $media_dir. It is
    # the seam layer, not a subject: every module is entitled to media_mtime and
    # ${MEDIA_SHA256[@]} being in scope exactly as media-entry.sh guarantees, and a test
    # that named its module without naming the seams would fail with "command not found"
    # for a reason that has nothing to do with what it is asserting. From the real folder
    # because MEDIA_MODULE_DIR points at a mutant directory holding one altered module and
    # nothing else.
    srcs="source '$MEDIA_VERIFY_DIR/portable.sh';"
    for m in $modules; do
        srcs="$srcs source '$media_dir/$m';"
    done
    # "$BASH" is the ABSOLUTE path of the running interpreter, and bare `bash` would not
    # do: callers run inside with_fake_bin, whose whole job is to leave PATH holding
    # nothing the test did not name.
    LAST_OUT="$("$BASH" -c "
        ROOT_DIR='$root_dir'
        source '$repo_root/.ci/scripts/lib/common.sh'
        $(_media_coverage_prelude)
        $srcs
        $code" 2>&1)" || rc=$?
    return "$rc"
}

# media_defines <file> <function-name>
#
# True when <file> carries a definition of <function-name> at column 0, in either the
# block form or the one-line form. Used to ask the two questions the cutover turned into
# invariants: "does exactly one module define this" and "has run.sh really stopped".
media_defines() {
    local file="$1" name="$2"
    [ -f "$file" ] || return 1
    fidelity_extract_any "$file" "$name" >/dev/null 2>&1
}

# media_assert_sole_owner <repo-root> <module-basename> <function-name>
#
# THE STRUCTURAL HALF OF THE POST-CUTOVER PROOF. Returns 0 when all four hold, and prints
# the one that did not on stderr otherwise:
#
#   1. <module> defines the function. Checked first and loudly, because every check below
#      is about UNIQUENESS, and "nobody defines it" satisfies uniqueness vacuously. This
#      is the same trap the old byte-identity helper was built around: two extractions
#      that both found nothing used to compare equal.
#   2. No OTHER file in .ci/media defines it. Two modules defining one name means the
#      winner is decided by media-entry.sh's source order, which is not a contract
#      anybody wrote down.
#   3. run.sh and media.sh do not define it. This is the cutover itself, stated as an
#      invariant rather than as a one-time event: re-add a copy to run.sh -- which is
#      exactly what a future session merging a conflict would do -- and this fires.
#   4. Sourcing media-entry.sh puts THIS module's body in scope under that name. Steps
#      1 to 3 are all about files; this one is about what the interpreter actually ends
#      up with, so a module that exists but is never sourced, or a name shadowed by a
#      later source, is caught. `declare -f` is bash's own canonical form, so the
#      comparison is indifferent to formatting and to nothing else.
#
# <repo-root> is a parameter rather than a constant so a control can point it at a
# sandbox where the invariant has been deliberately broken. That is the only way this
# assertion is ever watched failing.
media_assert_sole_owner() {
    local root="$1" module="$2" name="$3"
    local module_path="$root/.ci/media/$module"

    media_defines "$module_path" "$name" || {
        echo "media_assert_sole_owner: $name() is not defined in $module_path -- nothing here is uniquely owned, so uniqueness proves nothing" >&2
        return 1
    }

    local other
    for other in "$root"/.ci/media/*.sh; do
        [ "$other" = "$module_path" ] && continue
        if media_defines "$other" "$name"; then
            echo "media_assert_sole_owner: $name() is defined in BOTH $module and $(basename "$other") -- source order in media-entry.sh would silently pick the winner" >&2
            return 1
        fi
    done

    # THE ORIGINS, FROM THE ONE LIST. run.sh, media.sh and -- since the 2026-09-06 router
    # split moved every verb body there -- .ci/legacy/run-legacy.sh. A media function
    # re-planted in any of them means the cutover has been undone for that name.
    #
    # media_origins FAILS rather than skipping when one of those files is absent, and this
    # returns 1 with it. That is deliberate and it is the difference between an assertion
    # and a decoration: with a plain loop over paths, deleting or renaming an origin left
    # this green while it checked one file fewer.
    local origins origin
    origins="$(media_origins "$root")" || return 1
    while IFS= read -r origin; do
        if media_defines "$origin" "$name"; then
            echo "media_assert_sole_owner: $name() is defined again in $(basename "$origin") -- the cutover has been undone for this function" >&2
            return 1
        fi
    done <<<"$origins"

    local via_entry via_module
    via_entry="$("$BASH" -c "source '$root/.ci/media/media-entry.sh' >/dev/null 2>&1; declare -f '$name'" 2>/dev/null)" || via_entry=""
    via_module="$("$BASH" -c "ROOT_DIR='$root'; source '$module_path' >/dev/null 2>&1; declare -f '$name'" 2>/dev/null)" || via_module=""
    if [ -z "$via_entry" ] || [ -z "$via_module" ]; then
        echo "media_assert_sole_owner: $name() would not parse out of media-entry.sh or $module -- refusing to compare nothing" >&2
        return 1
    fi
    if [ "$via_entry" != "$via_module" ]; then
        echo "media_assert_sole_owner: media-entry.sh resolves $name() to something other than $module's definition" >&2
        diff <(printf '%s\n' "$via_module") <(printf '%s\n' "$via_entry") >&2 || true
        return 1
    fi
    return 0
}

# media_chain_sandbox <dir>
#
# Builds a REAL, RUNNABLE repo at <dir>/repo and prints its path.
#
# Everything at the repo root is a SYMLINK to the real checkout except run.sh, media.sh,
# .ci/media and .ci/legacy, which are copies -- those are the only paths a chain test or an
# ownership control needs to ALTER, and the last of them joined the list on 2026-09-06 when
# the router split made run-legacy.sh a third origin. .ci itself is rebuilt as a directory
# of symlinks for the same reason. Symlinks
# rather than copies because the whole tree is needed (run.sh sources .ci/config,
# .ci/scripts/lib, .ci/lib and reads .devcontainer/toolchain.env at startup) and copying
# it per test would be slow enough to matter.
#
# The point of building a whole repo rather than calling media_entry_main directly is
# that the DELEGATION is what is under test. A sandbox run starts at ./run.sh, goes
# through its `exec`, and ends inside a module file; nothing in that path is simulated.
media_chain_sandbox() {
    local dir="$1" repo="$1/repo" entry
    mkdir -p "$repo/.ci"
    for entry in "$MEDIA_VERIFY_ROOT"/* "$MEDIA_VERIFY_ROOT"/.[!.]*; do
        [ -e "$entry" ] || continue
        case "$(basename "$entry")" in
            # .ci, run.sh and media.sh are copied below because the chain tests edit
            # them. .git is skipped outright: nothing on the path to a marker runs git,
            # and a symlink into the real object store is not worth the one accident.
            .ci | run.sh | media.sh | .git) continue ;;
        esac
        ln -sfn "$entry" "$repo/$(basename "$entry")"
    done
    for entry in "$MEDIA_VERIFY_ROOT"/.ci/*; do
        case "$(basename "$entry")" in
            # .ci/media is copied below. .ci/legacy is REBUILT AS A REAL DIRECTORY OF
            # COPIES rather than symlinked, and that is a correctness requirement, not a
            # preference: the ownership control plants a duplicate function definition
            # into each origin, and since the router split one of those origins is
            # .ci/legacy/run-legacy.sh. Through a symlinked directory that append lands in
            # the REAL checkout, corrupting a 1,300-line file owned by another workstream
            # and leaving the sandbox proving nothing. Verified 2026-09-06: before this
            # change "$repo/.ci/legacy/run-legacy.sh" resolved to
            # /home/developer/console/.ci/legacy/run-legacy.sh.
            media) continue ;;
            legacy)
                mkdir -p "$repo/.ci/legacy"
                cp "$entry"/* "$repo/.ci/legacy/"
                continue
                ;;
        esac
        ln -sfn "$entry" "$repo/.ci/$(basename "$entry")"
    done
    mkdir -p "$repo/.ci/media"
    cp "$MEDIA_VERIFY_DIR"/*.sh "$repo/.ci/media/"
    cp "$MEDIA_VERIFY_ROOT/run.sh" "$MEDIA_VERIFY_ROOT/media.sh" "$repo/"
    chmod +x "$repo/run.sh" "$repo/media.sh" "$repo/.ci/media/media-entry.sh"
    printf '%s' "$repo"
}

# media_chain_probe <sandbox-repo> <module-basename> <function-name>
#
# Restores <module> from the real folder and then makes <function-name>'s FIRST act be to
# print `MEDIA_CHAIN_REACHED:<name>:<its arguments>` and return 0.
#
# Planting the marker INSIDE THE BODY is what makes the chain test mean something. A stub
# defined next to the call site would prove only that media-entry.sh's case tree routes,
# which the entry test already covers by other means; a marker in the module file proves
# the interpreter got as far as reading THAT FILE for THAT NAME. Nothing downstream of the
# marker runs, which is what keeps a probe of `www tutorials record` from wanting a VM.
#
# It restores the module first so probes can be planted one after another in one sandbox
# without stacking on each other.
media_chain_probe() {
    local repo="$1" module="$2" name="$3"
    cp "$MEDIA_VERIFY_DIR/$module" "$repo/.ci/media/$module"
    awk -v NAME="$name" '
        $0 == NAME "() {" && !done {
            print
            print "    echo \"MEDIA_CHAIN_REACHED:" NAME ":$*\"; return 0"
            done = 1
            next
        }
        { print }
        END { if (!done) { print "media_chain_probe: " NAME "() not found" > "/dev/stderr"; exit 1 } }
    ' "$MEDIA_VERIFY_DIR/$module" >"$repo/.ci/media/$module.probed" || return 1
    mv "$repo/.ci/media/$module.probed" "$repo/.ci/media/$module"
}

# media_chain_mutate <sandbox-repo> <file-relative-to-repo> <sed-expression>
#
# Applies one sed expression to a sandbox file. The controls use it to break the chain on
# purpose: drop run.sh's `exec`, or rename the function the module owns.
media_chain_mutate() {
    local repo="$1" rel="$2" expr="$3"
    sed "$expr" "$repo/$rel" >"$repo/$rel.mutated" || return 1
    mv "$repo/$rel.mutated" "$repo/$rel"
    chmod +x "$repo/$rel" 2>/dev/null || true
}

# media_chain_run <sandbox-repo> <script-basename> <args...>
#
# Runs the sandbox's own ./run.sh or ./media.sh with <args>. stdout and stderr merged
# into LAST_CHAIN; the return value is the script's.
#
# Called from inside with_fake_bin, so PATH holds only what the test admitted -- which for
# the whole chain is `uname` and `dirname` and nothing else. That is measured, not
# assumed: run.sh resolves ROOT_DIR with dirname on its first line, and
# .ci/scripts/lib/common.sh runs detect_os at source time. Everything else on the path to
# the marker is a bash builtin, which is why docker, node, npm, nvcc, aws and ssh being
# absent is not a special arrangement here but the ordinary case.
LAST_CHAIN=""
media_chain_run() {
    local repo="$1" script="$2"
    shift 2
    local rc=0
    if [ -n "${MEDIA_COVERAGE_FILE:-}" ] && [ -n "$MEDIA_ENV_BIN" ]; then
        # The chain starts at ./run.sh, so there is no code string to splice a prelude into
        # and the options have to arrive in the environment. BASH_XTRACEFD keeps the trace
        # off the captured streams, which is what makes this safe here and unsafe around the
        # whole suite. env, not an export, so nothing outside this call is affected.
        LAST_CHAIN="$(
            exec 9>>"$MEDIA_COVERAGE_FILE"
            "$MEDIA_ENV_BIN" BASH_XTRACEFD=9 PS4='+|${BASH_SOURCE:-}|${LINENO}|' SHELLOPTS=xtrace "$BASH" "$repo/$script" "$@" 2>&1
        )" || rc=$?
        return "$rc"
    fi
    LAST_CHAIN="$("$BASH" "$repo/$script" "$@" 2>&1)" || rc=$?
    return "$rc"
}

# media_assert_module_owns <module-basename> <function-name>...
#
# The ownership CASE that every module's gate test runs, extracted because it was the
# same nine lines in five files and check:ci-shape-duplication is right that five copies
# of a loop is one loop. Each name goes through media_assert_sole_owner against $ROOT,
# and the pass line names the module and the count.
#
# THE COUNT IS PRINTED, so a MOVED list that silently loses an entry reads differently
# even though it still passes. That is the only thing the old per-file copies said that a
# shared helper could have dropped, so it did not drop it.
media_assert_module_owns() {
    local module="$1"
    shift
    local fn
    for fn in "$@"; do
        media_assert_sole_owner "$ROOT" "$module" "$fn" ||
            log_fail "$fn() is not solely owned by $module, or media-entry.sh does not resolve to it"
    done
    if [ "$#" -eq 1 ]; then
        log_pass "$module holds the only definition of $1, and media-entry.sh resolves the name to it"
    else
        log_pass "$module holds the only definition of all $# moved functions, and media-entry.sh resolves each to it"
    fi
}

# media_assert_ownership_control <temp-dir> <module-basename> <function-name>
#
# THE CONTROL FOR THE CASE ABOVE, in the four ways that assertion could go quiet. An
# assertion nobody has watched fail is an assertion nobody has checked, and this one has
# a specific vacuity in its history: the byte-identity helper it replaced compared two
# extractions that had both found nothing and called them equal.
#
#   1. A second definition put back into EVERY origin, one at a time: run.sh,
#      .ci/legacy/run-legacy.sh (where the router split moved every verb body, so it is
#      where a re-planted media function would actually land today, and it was invisible
#      here until 2026-09-06) and media.sh.
#   2. In media.sh the plant uses the ONE-LINE `name() { ...; }` spelling, because that is
#      how media.sh actually wrote `die`, and a block-only search reports a one-line
#      re-plant as absent and passes. fidelity_extract_any exists for exactly that, and
#      this is the arm that proves it is wired in.
#   3. A name nothing defines anywhere. "Nobody defines it, so nobody else does either"
#      must NOT read as unique ownership. This is the vacuity the byte-identity helper
#      this replaced was built around.
#   4. AN ORIGIN FILE THAT IS NOT THERE. This is the arm that would otherwise be missing,
#      and it is the one that matters most for arms 1 and 2: an absence check over a
#      missing file passes for free, so renaming run-legacy.sh would silently retire a
#      third of this proof while every gate stayed green.
#
# Each arm restores the origin it damaged before the next one runs, so the arms are
# independent rather than cumulative and a failure names one cause.
media_assert_ownership_control() {
    local dir="$1" module="$2" name="$3" repo rel
    repo="$(media_chain_sandbox "$dir")"

    # REFUSE TO PROCEED THROUGH A SYMLINK. Every arm below WRITES to an origin inside the
    # sandbox, and if media_chain_sandbox ever goes back to symlinking .ci/legacy those
    # writes land in the real checkout. A guard rather than a comment, because the damage
    # is silent and lands in another workstream's 1,300-line file.
    [ -L "$repo/.ci/legacy" ] &&
        log_fail "the sandbox symlinked .ci/legacy -- planting an origin here would write into the real checkout"

    for rel in "${MEDIA_ORIGIN_RELPATHS[@]}"; do
        if [ "$rel" = media.sh ]; then
            printf '\n%s() { printf "%%s\\n" "$*" >&2; exit 1; }\n' "$name" >>"$repo/$rel"
        else
            printf '\n%s() {\n    :\n}\n' "$name" >>"$repo/$rel"
        fi
        if media_assert_sole_owner "$repo" "$module" "$name" 2>/dev/null; then
            log_fail "the ownership assertion passed with $rel defining $name() again, so it proves nothing"
        fi
        cp "$ROOT/$rel" "$repo/$rel"
    done

    if media_assert_sole_owner "$ROOT" "$module" zzz_no_such_function 2>/dev/null; then
        log_fail "the ownership assertion passed for a function nothing defines -- absence is not ownership"
    fi

    # PARKED AT THE SANDBOX ROOT, not beside the file it came from. A name under
    # .ci/legacy/ would read as a claim that such a path exists, and the folder's
    # documentation gate checks every .ci/ path a media file names.
    mv "$repo/.ci/legacy/run-legacy.sh" "$repo/absent-origin"
    if media_assert_sole_owner "$repo" "$module" "$name" 2>/dev/null; then
        log_fail "the ownership assertion passed with an origin file absent -- a file nobody read cannot testify that the name is not in it"
    fi
    mv "$repo/absent-origin" "$repo/.ci/legacy/run-legacy.sh"

    log_pass "the ownership assertion fires on $name() re-planted in each of the ${#MEDIA_ORIGIN_RELPATHS[@]} origins (one-line form in media.sh), on a name nothing defines, and on an origin that is missing"
}

# media_assert_mutation_swapped <observed> <original> <planted> <subject>
#
# The two-line pair that closes every "a planted mutation is visible to the behaviour
# cases" control: the original marker must be GONE and the planted one present. Both
# halves are load-bearing and the first is the one people forget -- asserting only that
# the planted text appears would still pass if the run were reading the unmutated module
# and the marker happened to be a substring of something else.
media_assert_mutation_swapped() {
    local observed="$1" original="$2" planted="$3" subject="$4"
    assert_not_contains "$observed" "$original" "the original $subject must be GONE, or the cases are not reading the module under test"
    assert_contains "$observed" "$planted" "the planted $subject is what the run reports"
}
