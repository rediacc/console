#!/bin/bash
# Tests for .ci/media/portable.sh -- the seams where this pipeline names a system tool
# that is spelled differently, or does not exist, off Linux.
#
# WHY A SEAM MODULE NEEDS A GATE MORE THAN MOST CODE DOES. Its whole value is in the
# branch that never runs here. `stat -c %Y` works on this host, so does `nproc`, so does
# `sha256sum`; a test that only calls the seams on this machine proves that the GNU
# spelling still works, which nobody doubted, and says nothing at all about the fallbacks
# that are the reason the file exists. So every seam is driven THREE ways: the platform
# spelling this host has, the fallback spelling with the first one hidden from PATH, and
# the case where nothing answers, which must produce a named refusal rather than an empty
# string. The third is the one that matters: the defect this module was written to close
# was `stat -c %Y` returning nothing into `$(( now -  ))`, and "nothing" is what a
# fallback chain produces when its last link also fails silently.
#
# THE FOURTH TEST IS THE ONE THAT KEEPS THE OTHERS TRUE. Seams do not decay by breaking,
# they decay by being bypassed: the next person writes `stat -c %Y` inline because it works
# on the machine in front of them, and portable.sh becomes a file that three call sites use
# and eleven do not. test_no_unseamed_platform_tool_remains scans the whole folder and
# refuses any un-seamed spelling, so the careless version is not available rather than
# merely discouraged.
#
# Nothing here needs docker, node, npm, nvcc, aws, ssh, a GPU or a network. The fallbacks
# are driven with scripted fakes on an emptied PATH, and the refusals with an emptied PATH
# and a meminfo path that points at nothing.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/portable.sh"

# The digest of the four bytes "abc\n", which is what every arm below hashes. Written out
# rather than computed, because computing the expected value with the tool under test is
# the classic way a hash assertion agrees with itself no matter what it is measuring.
ABC_SHA256="edeaaff3f1774ad2888673770c6d64097e391bc362d7d6fb34982ddf0efd18cb"

# probe_portable <code>
#
# Sources ONLY portable.sh in a fresh bash and runs <code>. Fresh, because MEDIA_SHA256 is
# resolved at SOURCE time by a command -v probe: a fallback test has to source the module
# again with the emptied PATH in effect, not reuse the array this file already holds.
# Output merged into LAST_PORTABLE; the return value is the code's.
#
# THE COVERAGE PRELUDE IS SPLICED IN, and leaving it out was a measurement defect rather
# than a style slip. This file does not go through media_run_module -- it needs a shell
# that sources ONLY portable.sh -- so it never inherited verify.sh's MEDIA_COVERAGE_FILE
# seam, and .ci/media/coverage.sh therefore reported portable.sh at 7 PERCENT while a
# 260-line gate test drove every seam in it three ways. That number was not a fact about
# the tests, it was a fact about the instrument, and it pointed a reader at the one module
# in this folder with the most thorough suite as the one most in need of tests. The prelude
# is empty when MEDIA_COVERAGE_FILE is unset, so a normal run is unchanged, and the trace
# goes to descriptor 9 rather than onto the streams captured below.
LAST_PORTABLE=""
probe_portable() {
    local rc=0
    LAST_PORTABLE="$("$BASH" -c "$(_media_coverage_prelude) source '$MODULE'; $1" 2>&1)" || rc=$?
    return "$rc"
}

# ---------------------------------------------------------------------------
# 1. The platform spelling this host has
# ---------------------------------------------------------------------------

test_every_seam_answers_on_this_host() {
    local d="$1"
    printf 'abc\n' >"$d/f"

    probe_portable "\"\${MEDIA_SHA256[@]}\" '$d/f' | cut -d' ' -f1" ||
        log_fail "the sha256 seam failed on a host that has one: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "$ABC_SHA256" "the sha256 seam must produce the real digest of the bytes it was given"

    probe_portable "media_file_size '$d/f'" || log_fail "media_file_size failed: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "4" "media_file_size must count bytes, and 'abc' plus a newline is four of them"

    probe_portable "media_mtime '$d/f'" || log_fail "media_mtime failed: $LAST_PORTABLE"
    [[ "$LAST_PORTABLE" =~ ^[0-9]+$ ]] || log_fail "media_mtime printed '$LAST_PORTABLE', which is not an epoch second"
    [ "$LAST_PORTABLE" -gt 1600000000 ] ||
        log_fail "media_mtime printed $LAST_PORTABLE, which is before 2020 -- a file created a moment ago cannot be that old, so the seam is reporting a failure as a number"

    probe_portable "media_cpu_count" || log_fail "media_cpu_count failed: $LAST_PORTABLE"
    [[ "$LAST_PORTABLE" =~ ^[0-9]+$ ]] && [ "$LAST_PORTABLE" -ge 1 ] ||
        log_fail "media_cpu_count printed '$LAST_PORTABLE', which is not a count of processors"

    probe_portable "media_avail_mem_gb" || log_fail "media_avail_mem_gb failed: $LAST_PORTABLE"
    [[ "$LAST_PORTABLE" =~ ^[0-9]+$ ]] ||
        log_fail "media_avail_mem_gb printed '$LAST_PORTABLE', which is not a whole number of gigabytes"
    log_pass "all five seams answer correctly using this host's own spellings"
}

# ---------------------------------------------------------------------------
# 2. The fallback spelling, with the first one hidden
# ---------------------------------------------------------------------------

# stage_bsd_host <dir>
#
# A PATH that looks like macOS: no nproc, no sha256sum, and a `stat` that REFUSES the GNU
# flags and answers the BSD ones. Faking the refusal rather than simply omitting stat is
# what makes this a fallback test -- GNU stat exits 1 on `-f`, BSD stat exits 1 on `-c`,
# and the seam has to try the second after the first fails rather than after it is absent.
stage_bsd_host() {
    local d="$1"
    cat >"$FAKE_BIN_DIR/stat" <<'BSD'
#!/bin/bash
case "${1:-}" in
    -c*) echo "stat: invalid option -- 'c'" >&2; exit 1 ;;
    -f)  fmt="$2"; shift 2 ;;
    -f*) fmt="${1#-f}"; shift ;;
    *)   exit 1 ;;
esac
case "$fmt" in
    %m) echo 1700000000 ;;
    %z) echo 4 ;;
    *)  exit 1 ;;
esac
BSD
    cat >"$FAKE_BIN_DIR/sysctl" <<'BSD'
#!/bin/bash
[ "${1:-}" = -n ] && [ "${2:-}" = hw.ncpu ] && { echo 11; exit 0; }
exit 1
BSD
    cat >"$FAKE_BIN_DIR/shasum" <<BSD
#!/bin/bash
# Only the -a 256 spelling, because that is the only one the seam is allowed to use.
[ "\${1:-}" = -a ] && [ "\${2:-}" = 256 ] || exit 1
shift 2
echo "$ABC_SHA256  \${1:-}"
BSD
    chmod +x "$FAKE_BIN_DIR/stat" "$FAKE_BIN_DIR/sysctl" "$FAKE_BIN_DIR/shasum"
    : "$d"
}

_case_bsd_fallbacks() {
    local d="$1"
    stage_bsd_host "$d"

    probe_portable "\"\${MEDIA_SHA256[@]}\" '$d/f' | cut -d' ' -f1" ||
        log_fail "the sha256 seam did not fall through to shasum: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "$ABC_SHA256" "the shasum fallback must produce the same digest as sha256sum"

    probe_portable "media_mtime '$d/f'" || log_fail "media_mtime did not fall through to stat -f %m: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "1700000000" "media_mtime must take the BSD stat's answer once the GNU form is refused"

    probe_portable "media_file_size '$d/f'" || log_fail "media_file_size did not fall through: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "4" "media_file_size must take the BSD stat's answer once the GNU form is refused"

    probe_portable "media_cpu_count" || log_fail "media_cpu_count did not fall through to sysctl: $LAST_PORTABLE"
    assert_eq "$LAST_PORTABLE" "11" "media_cpu_count must take sysctl's answer when nproc is absent"
}

test_the_bsd_fallbacks_are_reachable() {
    local d="$1"
    printf 'abc\n' >"$d/f"
    # cut and bash are real; everything the seams reach for is either the scripted fake or
    # deliberately absent. nproc, sha256sum and GNU stat are all gone from this PATH, which
    # is the whole arrangement.
    with_fake_bin "+bash +cut +cat +chmod" _case_bsd_fallbacks "$d"
    log_pass "every seam reaches its BSD spelling when the GNU one is absent or refuses"
}

# ---------------------------------------------------------------------------
# 3. Nothing answers: a named refusal, never an empty string
# ---------------------------------------------------------------------------

_case_bare_host_refuses() {
    local d="$1" rc

    rc=0
    probe_portable "\"\${MEDIA_SHA256[@]}\" '$d/f'" || rc=$?
    [ "$rc" -ne 0 ] || log_fail "the sha256 seam succeeded with no hashing tool at all; a caller would have taken an empty hash for a real one"
    assert_contains "$LAST_PORTABLE" "no SHA-256 tool found" "the refusal must name what it looked for"

    rc=0
    probe_portable "media_mtime '$d/f'" || rc=$?
    [ "$rc" -ne 0 ] || log_fail "media_mtime succeeded with no stat at all -- this is the exact defect the seam exists to close"
    assert_contains "$LAST_PORTABLE" "cannot read the modification time" "the refusal must say what it could not do"

    rc=0
    probe_portable "MEDIA_MEMINFO='$d/no-such-meminfo'; media_avail_mem_gb" || rc=$?
    [ "$rc" -ne 0 ] || log_fail "media_avail_mem_gb succeeded with no meminfo, so the render pool would schedule against a fabricated number"
    assert_contains "$LAST_PORTABLE" "no portable equivalent of MemAvailable" "the refusal must state the limitation rather than guess a number"

    # THE ONE SEAM THAT GUESSES, and it says so. One render at a time is a correct if slow
    # answer; the asymmetry with the four above is deliberate and is documented at the seam.
    probe_portable "media_cpu_count" || log_fail "media_cpu_count must not fail, it must fall back to 1"
    assert_contains "$LAST_PORTABLE" "1" "media_cpu_count falls back to one processor"
    assert_contains "$LAST_PORTABLE" "assuming 1" "and it says on stderr that it is guessing"
}

test_every_seam_refuses_out_loud_when_nothing_answers() {
    local d="$1"
    printf 'abc\n' >"$d/f"
    # NOTHING but bash. No stat, no sha256sum, no shasum, no nproc, no sysctl, no wc.
    with_fake_bin "+bash" _case_bare_host_refuses "$d"
    log_pass "every seam that cannot answer refuses by name, and the one that guesses says so"
}

# ---------------------------------------------------------------------------
# 4. The invariant: no un-seamed spelling anywhere in the folder
# ---------------------------------------------------------------------------

# unseamed_uses <dir>
#
# Every line under <dir> that names a platform tool directly instead of going through a
# seam, as `<file>:<line>: <text>`. Empty output is the invariant holding.
#
# WHAT IS DELIBERATELY NOT A FINDING, each for a stated reason:
#   - portable.sh itself, which is where the real spellings are supposed to be.
#   - comment lines, because the seams are explained by naming what they replace, and a
#     scan that counted prose would force the explanations out of the file.
#   - any line calling _bridge_ssh, whose argument is a command that runs ON THE BRIDGE VM.
#     That host is Linux by construction and seaming its `sha256sum` would be a category
#     error: the seam picks a spelling for THIS machine.
#
# THREE MORE SPELLINGS WERE ADDED 2026-09-06, and the reason they were missing is worth
# more than the patterns. The original set covers the tools portable.sh has a SEAM for, so
# it was derived from the seam module: every function in there earned a pattern. That is a
# scan that can only ever police what has already been fixed. `sed -i`, `readlink -f` and
# `date -d` have no seam because nothing in this folder uses them -- which is exactly why
# they are the ones that get written next by somebody on a Linux box, and none of the three
# does what it says on macOS: BSD sed's `-i` demands a backup suffix, BSD readlink has no
# `-f` at all, and BSD date reads `-d` as "daylight savings" rather than a date to parse.
# Measured against this folder the day they were added: zero findings, so they cost nothing
# today and refuse the careless version tomorrow.
unseamed_uses() {
    local dir="$1"
    grep -rnE '(\bnproc\b|\bsha256sum\b|\bshasum\b|stat -c|stat -f|grep -[a-zA-Z]*P|MemAvailable|\bsed\b([[:space:]]+-[A-Za-z.]+)*[[:space:]]+-i|\breadlink\b[[:space:]]+-[A-Za-z]*f|\bdate\b[[:space:]]+-[A-Za-z]*d)' \
        --include='*.sh' "$dir" 2>/dev/null |
        grep -v '/portable\.sh:' |
        grep -vE '^[^:]+:[0-9]+:\s*#' |
        grep -v '_bridge_ssh' || true
}

test_no_unseamed_platform_tool_remains_in_this_folder() {
    local found
    found="$(unseamed_uses "$ROOT/.ci/media")"
    [ -z "$found" ] || log_fail "un-seamed platform tools in .ci/media:
$found
Route each through .ci/media/portable.sh, or, if it genuinely runs on another machine, say so at the call site the way the bridge's remote hash does."
    log_pass "no file in .ci/media names nproc, sha256sum, shasum, stat -c, stat -f, grep -P, MemAvailable, sed -i, readlink -f or date -d outside the seam module"
}

test_the_unseamed_scan_can_fail() {
    # CONTROL, in both directions. A grep-based invariant is the shape that goes quiet
    # most easily: change a character class and it matches nothing while still reporting
    # success. Plant one of each spelling in a copy of the folder and require every one to
    # be found, then confirm the scan is silent on the copy once they are removed.
    local d="$1" i=0 spelling
    mkdir -p "$d/media"
    cp "$ROOT/.ci/media"/*.sh "$d/media/"

    # The clean copy must be silent first, or a finding below would prove nothing.
    [ -z "$(unseamed_uses "$d/media")" ] ||
        log_fail "the scan already reports a finding on an unmodified copy of the folder"

    for spelling in 'x="$(nproc)"' 'h="$(sha256sum f)"' 'h="$(shasum -a 256 f)"' \
        't="$(stat -c %Y f)"' 't="$(stat -f %m f)"' 'g="$(grep -oP "x" f)"' \
        'm="$(awk "/MemAvailable/" /proc/meminfo)"' \
        'sed -i "s/a/b/" f' 'sed -E -i "s/a/b/" f' 'p="$(readlink -f f)"' \
        'd="$(date -d @123 +%s)"'; do
        i=$((i + 1))
        printf '%s\n' "$spelling" >"$d/media/planted-$i.sh"
        [ -n "$(unseamed_uses "$d/media")" ] ||
            log_fail "the scan did not notice the planted spelling: $spelling"
        rm -f "$d/media/planted-$i.sh"
    done

    # A COMMENT MUST NOT BE A FINDING, or the seam module's own explanations become
    # unwritable and the next reader loses the reason each seam exists.
    printf '# this comment mentions nproc and sha256sum and stat -c %%Y\n' >"$d/media/commented.sh"
    [ -z "$(unseamed_uses "$d/media")" ] ||
        log_fail "the scan treated a comment as a finding, which would force the seams' own prose out of the folder"
    rm -f "$d/media/commented.sh"

    # THE OTHER DIRECTION, and the one an added pattern breaks. Every spelling below is
    # POSIX and works on both platforms, and three of them sit one character away from a
    # pattern above: `date -u` next to `date -d`, `sed -n` next to `sed -i`, `readlink`
    # bare next to `readlink -f`. A regex widened carelessly starts refusing these, the
    # folder goes red for code that is already correct, and the next person's fix is to
    # delete the scan. .ci/media/tutorials.sh really does call `date -u +%Y...` and
    # .ci/media/teaser.sh really does call `sed -n`, so this is not hypothetical.
    local near
    for near in 'stamp="$(date -u +%Y%m%dT%H%M%SZ)"' 'now="$(date +%s)"' \
        'y="$(sed -n "s/x//p" f)"' 'p="$(readlink f)"' 'n="$(grep -c x f)"'; do
        printf '%s\n' "$near" >"$d/media/portable-form.sh"
        [ -z "$(unseamed_uses "$d/media")" ] ||
            log_fail "the scan refused a spelling that is portable and in use: $near
$(unseamed_uses "$d/media")"
        rm -f "$d/media/portable-form.sh"
    done
    log_pass "the un-seamed scan finds all $i spellings when planted, ignores a comment that names them, and stays silent on the five portable forms this folder actually uses"
}

log_test "test-media-portable"
with_temp_dir test_every_seam_answers_on_this_host
with_temp_dir test_the_bsd_fallbacks_are_reachable
with_temp_dir test_every_seam_refuses_out_loud_when_nothing_answers
test_no_unseamed_platform_tool_remains_in_this_folder
with_temp_dir test_the_unseamed_scan_can_fail
echo ""
log_pass "all tests passed"
