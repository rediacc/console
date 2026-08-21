#!/bin/bash
# Both-ways test for the SERVER-SIDE copy in
# .ci/scripts/deploy/simulate-promotion.sh.
#
# WHAT BROKE. The promotion simulation synced the whole source channel DOWN to
# /tmp and then back UP to the promoted channel, so the job cost two full
# transfers of a channel that grows with every release. Measured on the `main`
# push runs: 21m57s (2026-07-27), 30m51s (2026-08-07, cancelled at the
# then-30-minute ceiling), 57m01s (2026-08-18, three minutes of headroom),
# 61m12s (2026-08-20, run 32423301927, blew the raised 60-minute ceiling). That
# cancellation failed CI Complete and Pipeline Sentinel, and the release
# sentinel never ran. The failing job's log holds ZERO retry warnings and died
# mid-transfer, so it was size and not flakiness.
#
# A PR CANNOT EXERCISE THE REAL PATH: PR runs promote a tiny per-PR channel in
# minutes, only `main` promotes the full `edge` channel. So this test does not
# try to prove the timing. It pins the SHAPE that caused the timing: the bytes
# must not travel through the runner. A regression to download-and-reupload is
# invisible to every other check in the repo and would simply be slow again.
#
# The transfers are driven through a STUB `aws` on PATH which records its argv,
# so the assertions read what the script actually invoked rather than what its
# source appears to say.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

FIXTURE="$(mktemp -d)"
trap 'rm -rf "$FIXTURE"' EXIT

# get_repo_root() resolves from the SCRIPT's own path (.ci/scripts/lib -> up 3),
# so the fixture mirrors the tree layout rather than just holding the script.
mkdir -p "$FIXTURE/repo/.ci/scripts/deploy" "$FIXTURE/repo/.ci/scripts/lib" "$FIXTURE/bin"
# PROMOTION_SCRIPT overrides the subject so the mutation proof can point this
# at the pre-fix script and watch these assertions FAIL. A test never seen
# failing is indistinguishable from `true`.
PROMOTION_SCRIPT="${PROMOTION_SCRIPT:-$REPO_ROOT/.ci/scripts/deploy/simulate-promotion.sh}"
cp "$PROMOTION_SCRIPT" "$FIXTURE/repo/.ci/scripts/deploy/simulate-promotion.sh"
cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$FIXTURE/repo/.ci/scripts/lib/"
TARGET="$FIXTURE/repo/.ci/scripts/deploy/simulate-promotion.sh"

# The purge step shells out to this; keep it inert but present.
# Records the URLs it is handed, so the purge assertions read what the script
# actually asked to be purged rather than a proxy for it.
cat >"$FIXTURE/repo/.ci/scripts/deploy/cf-purge-urls.sh" <<STUB
#!/bin/bash
cat >"$FIXTURE/purged.txt"
STUB
chmod +x "$FIXTURE/repo/.ci/scripts/deploy/cf-purge-urls.sh"

# write_fake_aws <version-string>: records every invocation to $FIXTURE/argv.log
# and answers `s3 ls --recursive` with a listing that includes a key containing
# a space, which is exactly what a naive field-split would corrupt.
# write_fake_aws <version-string> [rogue]
# `rogue` makes the listing return a key OUTSIDE the requested prefix, which is
# what the doubled-destination guard must catch.
write_fake_aws() {
    cat >"$FIXTURE/bin/aws" <<STUB
#!/bin/bash
printf '%s\n' "\$*" >>"$FIXTURE/argv.log"
case "\$1" in
    --version) echo "$1" ;;
    configure) exit 0 ;;
    s3)
        # Real \`aws s3 ls <prefix> --recursive\` prints FULL keys under the
        # prefix asked for. A stub that ignored the prefix would hide the
        # strip-and-rebuild logic entirely, so derive the keys from argv[3].
        if [[ "\$2" == "ls" ]]; then
            prefix="\${3#s3://rediacc-releases/}"
            [[ "${2:-}" == "rogue" ]] && prefix="somewhere-else/"
            echo "2026-08-20 12:00:01       1234 \${prefix}dists/Release"
            echo "2026-08-20 12:00:02         12 \${prefix}dists/with space/InRelease"
        fi
        # The sed-fix step downloads a config file and then edits it in place.
        # A stub that reports success without materialising the file would fail
        # the script for a reason that has nothing to do with what is tested.
        # A download takes the form: cp s3://SRC LOCALPATH --endpoint-url URL
        # so the destination is argv[4] and NOT the last argument, which is
        # the endpoint value. (No backticks in this heredoc: it is unquoted,
        # so a backtick pair would be command substitution at write time.) Materialise it, because the sed-fix step edits the
        # file in place and a stub that only reports success would fail the
        # script for a reason unrelated to what is under test.
        if [[ "\$2" == "cp" && "\$3" == s3://* && "\$4" != s3://* ]]; then
            printf 'baseurl=https://releases.rediacc.com/rpm/edge/\n' >"\$4"
        fi
        exit 0
        ;;
esac
exit 0
STUB
    chmod +x "$FIXTURE/bin/aws"
}

run_promotion() {
    : >"$FIXTURE/argv.log"
    rc=0
    PATH="$FIXTURE/bin:$PATH" \
        CHANNEL=edge AWS_ACCESS_KEY_ID=k AWS_SECRET_ACCESS_KEY=s \
        R2_ENDPOINT=https://example.invalid CLOUDFLARE_ZONE_ID=z \
        CLOUDFLARE_API_TOKEN=t \
        bash "$TARGET" >"$FIXTURE/out.txt" 2>&1 || rc=$?
    # Surface the script's own output instead of letting set -e kill the test
    # with an empty transcript, which hides the reason entirely.
    if [[ $rc -ne 0 ]]; then
        log_error "simulate-promotion.sh exited $rc under the stub:"
        cat "$FIXTURE/out.txt" >&2
        return 1
    fi
}
argv_log() { cat "$FIXTURE/argv.log"; }

test_the_copy_is_server_side() {
    # THE INVARIANT. Every recursive transfer must have an s3:// destination.
    # A sync whose target is a local path is the regression this exists for.
    write_fake_aws "aws-cli/2.31.0 Python/3.12"
    run_promotion
    assert_contains "$(argv_log)" "s3api copy-object --bucket rediacc-releases --key apt/edge-promoted/dists/Release --copy-source rediacc-releases/apt/edge/dists/Release" \
        "apt objects are copied bucket-to-bucket, and the destination key is rebuilt correctly"
    assert_not_contains "$(argv_log)" "/tmp/promote-" \
        "no transfer stages the channel through a local tmp directory"
    # THE R2 CONSTRAINT, pinned. `aws s3 sync`/`cp` reach for object tagging on
    # every s3-to-s3 path and R2 implements neither side of it: --copy-props
    # default needs GetObjectTagging, and any other value sends
    # x-amz-tagging-directive: REPLACE, which R2 answered with NotImplemented on
    # every object of run 32465461193. s3api sends only what is named here.
    assert_not_contains "$(argv_log)" "--copy-props" \
        "no --copy-props: it forces a tagging directive R2 does not implement"
    assert_not_contains "$(argv_log)" "--tagging-directive" \
        "no --tagging-directive: that is the exact header R2 rejected"
    log_pass "the channel is copied server-side via s3api, never through the runner and never touching tags"
}

test_all_four_formats_are_copied() {
    write_fake_aws "aws-cli/2.31.0 Python/3.12"
    run_promotion
    local fmt
    for fmt in apt rpm apk archlinux; do
        # s3api addresses objects by --bucket/--key, not an s3:// URL.
        assert_contains "$(argv_log)" "--key ${fmt}/edge-promoted/" \
            "${fmt} is promoted"
        assert_contains "$(argv_log)" "--copy-source rediacc-releases/${fmt}/edge/" \
            "${fmt} is sourced from the unpromoted channel"
    done
    log_pass "all four repo formats are promoted"
}

test_a_key_outside_the_prefix_is_REFUSED() {
    # A listing key that does not start with the source prefix would make the
    # strip a silent no-op and write to a DOUBLED destination such as
    # apk/edge-promoted/apt/edge/... The install tests that follow would then
    # read a channel nobody wrote, so this must fail loudly instead.
    write_fake_aws "aws-cli/2.31.0 Python/3.12" rogue
    local rc=0
    PATH="$FIXTURE/bin:$PATH" \
        CHANNEL=edge AWS_ACCESS_KEY_ID=k AWS_SECRET_ACCESS_KEY=s \
        R2_ENDPOINT=https://example.invalid CLOUDFLARE_ZONE_ID=z \
        CLOUDFLARE_API_TOKEN=t \
        bash "$TARGET" >"$FIXTURE/out.txt" 2>&1 || rc=$?
    [[ $rc -ne 0 ]] || {
        log_fail "a key outside the source prefix was accepted; the destination would be doubled"
        return 1
    }
    assert_contains "$(cat "$FIXTURE/out.txt")" "not under expected prefix" \
        "the guard names the reason"
    log_pass "a key outside the source prefix is refused rather than silently doubled"
}

test_cache_control_is_still_applied() {
    # Channel paths reuse filenames per release, so promoted bytes must never be
    # cacheable. Losing this in the rewrite would be silent until a stale POP
    # served an old Packages.gz to the install tests.
    write_fake_aws "aws-cli/2.31.0 Python/3.12"
    run_promotion
    assert_contains "$(argv_log)" "--cache-control no-cache" "promoted objects stay uncacheable"
    log_pass "cache-control no-cache survives the rewrite"
}

test_purge_urls_come_from_the_listing_and_survive_spaces() {
    # The old code walked the local tmp tree to build purge URLs. That tree is
    # gone, so the listing replaces it; a key containing a space must round-trip
    # intact rather than being split into two bogus URLs.
    write_fake_aws "aws-cli/2.31.0 Python/3.12"
    run_promotion
    # ONE listing of the SOURCE prefix now serves both the copy and the purge
    # list, rather than a second listing of the destination.
    assert_contains "$(argv_log)" "s3 ls s3://rediacc-releases/apt/edge/ --recursive" \
        "purge URLs are derived from a listing, not a transfer"
    assert_contains "$(cat "$FIXTURE/purged.txt")" "https://releases.rediacc.com/apt/edge-promoted/dists/Release" \
        "a promoted URL is queued for purge"
    assert_contains "$(cat "$FIXTURE/purged.txt")" "https://releases.rediacc.com/apt/edge-promoted/dists/with space/InRelease" \
        "a key containing a space survives into its purge URL intact"
    assert_contains "$(cat "$FIXTURE/out.txt")" "Promotion simulated" \
        "the script ran to completion under the stub"
    log_pass "purge URLs are enumerated by listing the promoted channel"
}

test_the_stub_is_actually_being_exercised() {
    # THE CONTROL. If the stub were never called, every assertion above would be
    # vacuous. An empty argv log must be impossible.
    write_fake_aws "aws-cli/2.31.0 Python/3.12"
    run_promotion
    local lines
    lines="$(wc -l <"$FIXTURE/argv.log")"
    [[ "$lines" -gt 4 ]] || {
        log_fail "the fake aws recorded only $lines invocations; the assertions above would be vacuous"
        return 1
    }
    log_pass "the stub recorded $lines invocations, so the assertions read real calls"
}

log_test "test-simulate-promotion-serverside"
test_the_copy_is_server_side
test_all_four_formats_are_copied
test_a_key_outside_the_prefix_is_REFUSED
test_cache_control_is_still_applied
test_purge_urls_come_from_the_listing_and_survive_spaces
test_the_stub_is_actually_being_exercised
echo ""
log_pass "all tests passed"
