#!/bin/bash
# Both-ways test for the version component of the closure key in
# .ci/scripts/ci/generate-tag.sh.
#
# WHAT THE KEY IS FOR. `generate-tag.sh --closure web|rdc` mints the tag that
# names a Docker image. initialize.sh asks the registry whether that tag exists
# and skips the build if it does, so the key is a cache key: two builds that
# hash the same reuse the same image. Both images BAKE a version in, and the
# version comes from a git tag, which is not a path -- so it is folded into the
# hash explicitly.
#
# WHAT WAS BROKEN. When no tag was reachable the fallback was an EMPTY marker,
# and an empty marker COLLAPSES the key: every version on a tagless checkout
# hashes identically, so a cached image built at an older version can be reused
# and then promoted under a new one. That is the exact failure the version
# component was added to prevent. It also runs at initialize.sh Step 5, BEFORE
# that script fetches tags, so the tagless path is not hypothetical -- it is
# latent purely because ci.yml's checkout happens to pass fetch-tags: true.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

# Every path the rdc closure hashes. Listed here so a closure that grows without
# this fixture growing with it fails loudly in build_fixture rather than
# silently testing a different code path.
RDC_CLOSURE_PATHS=(
    packages/cli
    packages/shared
    packages/provisioning
    package.json
    package-lock.json
    tsconfig.json
    .ci/scripts/build/build-cli-musl.sh
    .ci/scripts/build/build-cli-executables.sh
    .ci/scripts/build/prepare-cli-assets.sh
    scripts/generate-third-party-licenses.ts
    .github/workflows/ci-build-cli.yml
    .github/workflows/ci-build-docker.yml
)

# build_fixture <name> -- a throwaway git repo carrying the real generate-tag.sh,
# its lib and its resolver, plus a stand-in for every hashed closure path.
build_fixture() {
    local root="$WORK/$1"
    mkdir -p "$root/.ci/scripts/ci" "$root/.ci/scripts/lib" "$root/.ci/scripts/version"
    cp "$REPO_ROOT/.ci/scripts/ci/generate-tag.sh" "$root/.ci/scripts/ci/"
    cp "$REPO_ROOT/.ci/scripts/lib/common.sh" "$root/.ci/scripts/lib/"
    cp "$REPO_ROOT/.ci/scripts/version/resolve-version.sh" "$root/.ci/scripts/version/"

    local p
    for p in "${RDC_CLOSURE_PATHS[@]}"; do
        mkdir -p "$root/$(dirname "$p")"
        echo "closure stand-in for $p" >"$root/$p"
    done
    echo "unhashed" >"$root/README.md"

    git -C "$root" init -q
    git -C "$root" add -A
    git -C "$root" -c user.email=t@t -c user.name=t commit -q -m first
    echo "$root"
}

# commit_unhashed_change <root> -- moves HEAD without touching any hashed path,
# so only the version component can distinguish the two keys.
commit_unhashed_change() {
    echo "changed $RANDOM" >>"$1/README.md"
    git -C "$1" add README.md
    git -C "$1" -c user.email=t@t -c user.name=t commit -q -m next
}

closure_tag() {
    (cd "$1" && ./.ci/scripts/ci/generate-tag.sh --closure rdc 2>"$WORK/tag.err")
}

test_closure_paths_all_exist_in_the_real_script() {
    log_test "the fixture's closure path list matches the script"
    local p
    for p in "${RDC_CLOSURE_PATHS[@]}"; do
        assert_contains "$(sed -n '/^        rdc)/,/^            )/p' "$REPO_ROOT/.ci/scripts/ci/generate-tag.sh")" \
            "$p" "rdc closure must still hash $p"
    done
    log_pass "all 12 rdc closure paths accounted for"
}

test_untagged_keys_are_distinguishing() {
    log_test "with no tag reachable, two commits get different keys"
    local root t1 t2
    root="$(build_fixture untagged)"
    t1="$(closure_tag "$root")"
    assert_contains "$(cat "$WORK/tag.err")" "No version tag reachable" "the fallback must announce itself"
    commit_unhashed_change "$root"
    t2="$(closure_tag "$root")"
    if [[ "$t1" == "$t2" ]]; then
        log_fail "untagged closure keys collapsed: both commits produced '$t1'"
    fi
    log_pass "untagged keys differ per commit ($t1 vs $t2)"
}

test_tagged_keys_still_reuse() {
    log_test "with a tag reachable, an unrelated commit reuses the key"
    local root t1 t2
    root="$(build_fixture tagged)"
    git -C "$root" tag v1.2.17
    t1="$(closure_tag "$root")"
    assert_not_contains "$(cat "$WORK/tag.err")" "No version tag reachable" "a tagged repo must not take the fallback"
    commit_unhashed_change "$root"
    t2="$(closure_tag "$root")"
    assert_eq "$t2" "$t1" "a commit touching no hashed path must reuse the image"
    log_pass "cache reuse is preserved when a version exists ($t1)"
}

test_new_tag_invalidates_the_key() {
    log_test "cutting a tag changes the key"
    local root t1 t2
    root="$(build_fixture retagged)"
    git -C "$root" tag v1.2.17
    t1="$(closure_tag "$root")"
    git -C "$root" tag v1.2.18
    t2="$(closure_tag "$root")"
    if [[ "$t1" == "$t2" ]]; then
        log_fail "a version bump did not move the closure key: both were '$t1'"
    fi
    log_pass "v1.2.17 and v1.2.18 produce different keys"
}

# THE CONTROL. Plant the pre-fix empty marker and watch the untagged keys
# collapse into one. Without this, test_untagged_keys_are_distinguishing could
# be passing for reasons unrelated to the version component.
test_planted_empty_marker_collapses_the_key() {
    log_test "control: the empty marker collapses two commits into one key"
    local root t1 t2
    root="$(build_fixture planted)"
    sed -i 's|^        CLOSURE_VERSION="untagged-.*|        CLOSURE_VERSION=""|' \
        "$root/.ci/scripts/ci/generate-tag.sh"
    assert_contains "$(cat "$root/.ci/scripts/ci/generate-tag.sh")" 'CLOSURE_VERSION=""' "the plant must have applied"

    t1="$(closure_tag "$root")"
    commit_unhashed_change "$root"
    t2="$(closure_tag "$root")"
    assert_eq "$t2" "$t1" "planted empty marker must collapse the key (else the control proves nothing)"
    log_pass "the key stays distinct only because the fallback is distinguishing"
}

test_closure_paths_all_exist_in_the_real_script
test_untagged_keys_are_distinguishing
test_tagged_keys_still_reuse
test_new_tag_invalidates_the_key
test_planted_empty_marker_collapses_the_key
