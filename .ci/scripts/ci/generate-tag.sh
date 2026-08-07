#!/bin/bash
# Generate CI tags for Docker images
#
# Modes:
#   1. Time-based (default): YYYYMMDD-HHMMSS (UTC)
#   2. Submodule commit hash: Short git commit hash of a submodule
#
# Usage:
#   generate-tag.sh                         # Time-based tag to stdout
#   generate-tag.sh --output file.txt       # Write to file
#   generate-tag.sh --github-output         # Write to GITHUB_OUTPUT
#   generate-tag.sh --submodule path/to/sub # Get submodule commit hash
#   generate-tag.sh --self                  # Get current repo commit hash

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

OUTPUT_FILE=""
GITHUB_OUTPUT_MODE=false
SUBMODULE_PATH=""
SELF_MODE=false
CLOSURE_NAME=""
EXTRA_KEY=""

# Parse arguments
while [[ $# -gt 0 ]]; do
    case "$1" in
        --output)
            OUTPUT_FILE="$2"
            shift 2
            ;;
        --github-output)
            GITHUB_OUTPUT_MODE=true
            shift
            ;;
        --submodule)
            SUBMODULE_PATH="$2"
            shift 2
            ;;
        --self)
            SELF_MODE=true
            shift
            ;;
        --closure)
            CLOSURE_NAME="$2"
            shift 2
            ;;
        --extra)
            EXTRA_KEY+="$2"
            shift 2
            ;;
        -h | --help)
            echo "Usage: $0 [OPTIONS]"
            echo ""
            echo "Modes:"
            echo "  (default)              Generate time-based tag (YYYYMMDD-HHMMSS)"
            echo "  --submodule PATH       Get commit hash of specified submodule"
            echo "  --self                 Get commit hash of current repository"
            echo ""
            echo "Options:"
            echo "  --output FILE          Write tag to specified file"
            echo "  --github-output        Write to GITHUB_OUTPUT for GitHub Actions"
            echo "  -h, --help             Show this help message"
            echo ""
            echo "Examples:"
            echo "  $0                                    # -> 20260120-104603"
            echo "  $0 --submodule private/renet          # -> fb33b0f"
            echo "  $0 --self                             # -> c909b05"
            exit 0
            ;;
        *)
            log_error "Unknown option: $1"
            exit 1
            ;;
    esac
done

# Determine tag based on mode
if [[ -n "$SUBMODULE_PATH" ]]; then
    # Submodule commit hash mode with build config hash
    # Includes both submodule code AND build configuration to trigger rebuilds
    # when Dockerfiles or CI workflows change
    if [[ ! -d "$SUBMODULE_PATH" ]]; then
        log_error "Submodule not found: $SUBMODULE_PATH"
        exit 1
    fi

    if [[ ! -d "$SUBMODULE_PATH/.git" ]] && [[ ! -f "$SUBMODULE_PATH/.git" ]]; then
        log_error "Not a git repository: $SUBMODULE_PATH"
        exit 1
    fi

    SUBMODULE_COMMIT=$(git -C "$SUBMODULE_PATH" rev-parse --short HEAD)

    # Include build config files in tag hash (Dockerfiles, CI build workflow)
    #
    # MEMBERSHIP RULE: a file belongs here when its content determines the
    # CONTENT OF THE PUBLISHED IMAGE this tag names. The tag is what
    # initialize.sh checks against GHCR to decide `renet_exists`, so an input
    # missing from this list means a changed build produces an existing tag and
    # a stale image is reused; an input that does NOT affect the image means a
    # harmless edit costs a 45-minute rebuild.
    #
    # NOT IN THE LIST, DELIBERATELY: .ci/scripts/infra/build-renet.sh. It looks
    # like it belongs (nine CI steps run it: eight in ct-tests.yml, one in
    # ci-ops-test.yml, against one step here for the build/ script). It does not.
    # It compiles a dev binary from source into private/renet/bin for those test
    # jobs, which never pull ghcr.io/rediacc/renet and are never handed this tag
    # -- no input of ct-tests.yml carries an image tag (it takes full_suite,
    # pointer_bump_only and the scope engine's run_* vector, none of which name
    # an image), and its own cache is keyed on
    # private/renet/embed-assets.lock.json. Its edits take effect immediately in
    # all nine, so there is nothing here to invalidate.
    #
    # The first three entries are already covered by SUBMODULE_COMMIT above
    # (they live inside the submodule). They are kept because they cost nothing
    # and make the intent readable.
    BUILD_CONFIG_HASH=""
    BUILD_CONFIG_FILES=(
        "$SUBMODULE_PATH/Dockerfile"
        "$SUBMODULE_PATH/Dockerfile.native"
        "$SUBMODULE_PATH/build.sh"
        ".github/workflows/ci-build-renet.yml"
        ".github/workflows/ci-build-docker.yml"
        ".ci/scripts/build/build-renet.sh"
    )
    # A missing entry used to be skipped in silence. That is the failure mode
    # this list is most exposed to: rename or move one of these files and the
    # hash quietly stops covering it, while STILL minting a brand-new tag (the
    # remaining digests concatenate differently), so the one visible symptom --
    # a cache miss -- looks like normal behaviour. Renames happen: there are two
    # build-renet.sh scripts in this repo, in .ci/scripts/build/ and
    # .ci/scripts/infra/. Fail loudly instead.
    for f in "${BUILD_CONFIG_FILES[@]}"; do
        if [[ ! -f "$f" ]]; then
            log_error "Build-config input not found: $f"
            log_error "This file is hashed into the renet image tag. A missing entry silently"
            log_error "narrows what the tag covers, so a changed build can reuse a stale image."
            log_error "Fix the path in BUILD_CONFIG_FILES, or delete the entry if the file is gone."
            exit 1
        fi
        BUILD_CONFIG_HASH+=$(sha256sum "$f" | cut -c1-8)
    done

    # Combine the submodule commit with a hash of the build config. Keep 12 hex
    # chars (48 bits): the old 3-char (12-bit, 4096-value) hash collided often
    # enough that a build-config change could map to an existing tag and silently
    # reuse a stale image built from a DIFFERENT Dockerfile/workflow. 12 chars
    # makes that collision negligible.
    if [[ -n "$BUILD_CONFIG_HASH" ]]; then
        CONFIG_SHORT=$(echo -n "$BUILD_CONFIG_HASH" | sha256sum | cut -c1-12)
        CI_TAG="${SUBMODULE_COMMIT}-${CONFIG_SHORT}"
    else
        CI_TAG="$SUBMODULE_COMMIT"
    fi
    # Log to stderr so it doesn't interfere with captured stdout
    log_info "Generated submodule tag ($SUBMODULE_PATH): $CI_TAG" >&2

elif [[ -n "$CLOSURE_NAME" ]]; then
    # PRODUCER-CLOSURE MODE. Hash the inputs that actually determine the bytes of
    # a published image, instead of the console commit.
    #
    # WHY THIS EXISTS. `--self` is the console commit, so ANY commit invalidates
    # BOTH the server and rdc images. Measured: commit 8b7840ed4 changed exactly
    # one file, .ci/scripts/deploy/wait-for-preview-worker.sh, which is
    # .dockerignore'd (.dockerignore:20) and which no image consumes -- and both
    # images rebuilt, while renet's content-hashed tag was correctly reused.
    #
    # WHY NOT HASH THE BUILD CONTEXT. It is both smaller AND larger than the
    # COPY list. Smaller: .ci/scripts is excluded. Larger: .ci/docker/web is NOT
    # excluded (.dockerignore:18-19 name only .ci/docker/ci and /service), so
    # nginx.conf and entrypoint.sh do enter it. And the biggest inputs are not in
    # the context at all -- www-assets, account-web-assets, cli-npm and the renet
    # binaries all arrive as DOWNLOADED ARTIFACTS. So the key must cover each
    # artifact PRODUCER, not the Dockerfile'"'"'s own COPY list.
    #
    # MEMBERSHIP RULE, same contract as BUILD_CONFIG_FILES above: a path belongs
    # when its content determines the content of the published image.
    #
    # Hashed as git object ids at HEAD rather than sha256sum of files, for three
    # reasons: an entry may be a directory (the tree oid covers every file under
    # it, including files added later), or a gitlink (private/account resolves to
    # its recorded commit); and HEAD-based hashing is immune to the in-job
    # version bump that dirties package.json after initialize.sh has run.
    #
    # THIS IS WIRED AND LIVE. `initialize.sh:159-160` calls both closures and
    # publishes them as `web_tag` / `rdc_tag`, and `cd-stage.yml:195-196` retags
    # them straight onto a release channel, so a wrong key here ships bytes.
    #
    # The comment that stood here said the opposite ("NOT WIRED INTO
    # initialize.sh YET, deliberately") and was left behind when the wiring
    # landed. Corrected 2026-07-30, because a reader who believes this mode is
    # inert will not think hard about a key that is release-affecting -- which
    # is roughly how the missing-version bug below survived.
    #
    # Of the two issues it said had to be settled first: the unbounded staleness
    # window IS handled, by the weekly bucket below. The second is NOT, and it
    # stands as a known limitation: "same tag implies same bytes" is still false
    # because private/account is installed with an unpinned `npm install`, the
    # base images float, and ACCOUNT_ED25519_PUBLIC_KEY arrives as a build arg.
    # The bucket bounds the blast radius; it does not make the claim true.
    case "$CLOSURE_NAME" in
        web)
            CLOSURE_PATHS=(
                Dockerfile
                .ci/docker/web
                package.json
                package-lock.json
                tsconfig.json
                packages/shared
                packages/www
                packages/json
                packages/cli
                packages/provisioning
                private/account
                .ci/scripts/build/build-www.sh
                .ci/scripts/build/build-cli.sh
                .ci/scripts/build/pack-cli-npm.sh
                .ci/scripts/build/buildx-push-web.sh
                .github/workflows/ci-build-docker.yml
                .github/actions/setup-workspace
            )
            ;;
        rdc)
            CLOSURE_PATHS=(
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
            ;;
        *)
            log_error "Unknown closure: $CLOSURE_NAME (expected: web, rdc)"
            exit 1
            ;;
    esac

    CLOSURE_HASH=""
    for closure_path in "${CLOSURE_PATHS[@]}"; do
        if ! path_oid=$(git rev-parse "HEAD:$closure_path" 2>/dev/null); then
            # Same fail-loud contract as BUILD_CONFIG_FILES: a silently skipped
            # entry still mints a PLAUSIBLE tag, so the only symptom would be an
            # uninvestigatable cache miss -- or a stale image reused.
            log_error "Closure input not found at HEAD: $closure_path"
            log_error "It is hashed into the $CLOSURE_NAME image tag. A missing entry"
            log_error "narrows what the tag covers, so a changed build can reuse a"
            log_error "stale image. Fix the path, or delete the entry if it is gone."
            exit 1
        fi
        CLOSURE_HASH+="$path_oid"
    done
    # --extra folds in an opaque upstream key. Used for RENET_TAG: renet binaries
    # reach BOTH images as artifacts, never as source, so no path can cover them.
    CLOSURE_HASH+="$EXTRA_KEY"

    # WEEKLY TIME BUCKET, and it is a safety bound rather than cache tuning.
    #
    # A commit-hash key is always correct and merely wasteful: it cannot outlive
    # the commit. A closure key can, and there are inputs it provably does not
    # cover: ACCOUNT_ED25519_PUBLIC_KEY is passed as a build arg, the base images
    # (node:22-alpine, alpine:3.20) float, and private/account is installed with
    # an UNPINNED `npm install` -- so "same tag implies same bytes" is not true
    # today in either direction.
    #
    # Without a bucket, a key survives until the closure changes, which could be
    # months, and cd-stage.yml retags these straight onto a release channel.
    # With it, any staleness is capped at one week. Cost: one rebuild per image
    # per week. That is the trade the design was explicitly unwilling to skip.
    #
    # %G%V, not %Y%W: ISO year-and-week, so the last days of December cannot
    # collide with the first days of January.
    CLOSURE_HASH+="week:$(date -u +%G%V)"

    # THE RELEASED VERSION, and leaving it out was a real, reproduced bug.
    #
    # Both images BAKE a version in (the rdc SEA reports it from `rdc --version`,
    # the www footer from APP_VERSION), and that version is derived from the
    # latest git tag -- which is NOT a path, so no CLOSURE_PATHS entry can ever
    # cover it. Worse, the OID-at-HEAD hashing above is documented as being
    # "immune to the in-job version bump that dirties package.json". That
    # immunity is correct for a dirty working file and exactly wrong here: the
    # key ended up insensitive to the one input the image is stamped with.
    #
    # MEASURED, twice, not theorised. Release v1.2.12 landed 2026-07-30T10:16:14Z
    # mid-PR. On runs 30534726467 and 30542942037 `Validate Install Methods /
    # Linux` failed with "Version mismatch: expected '1.2.13', got '1.2.12'":
    # `Build (Docker) / CLI Docker` was SKIPPED while its cached twin succeeded,
    # so the mutable `pr-546` tag kept serving an image built before the release
    # while every run computed the next version afresh. Nothing on the branch
    # could break the tie, because the closure does not move when a tag is cut.
    # It was deterministic and self-perpetuating, not a race.
    #
    # `--current` (the latest tag) rather than the computed next version,
    # because the next version depends on a bump type that initialize.sh does
    # not detect until AFTER it calls this script, and reordering that is
    # release-affecting. Cutting a tag moves `--current`, which invalidates both
    # images exactly when their baked version changes.
    #
    # RESIDUAL, stated rather than hidden: two runs on the SAME base tag that
    # resolve different bump types (patch vs minor) would bake different
    # versions behind one key. That cannot produce the failure above, which
    # needed the base tag to move, and the weekly bucket bounds it regardless.
    #
    # Failure to resolve is NOT fatal: this script also runs where no tag is
    # reachable (a shallow clone, a fresh fork), and it runs at initialize.sh
    # Step 5, BEFORE that script fetches tags at all.
    #
    # But the old fallback was an EMPTY marker, and an empty marker COLLAPSES
    # the key -- every version on a tagless checkout hashes to the same thing,
    # which is precisely the failure mode the version component was added to
    # fix. A cached image built at an older version would be reused and then
    # promoted under a new one. Latent only because ci.yml's initialize
    # checkout happens to pass fetch-tags: true + fetch-depth: 0; nothing in
    # this script could tell.
    #
    # So the unresolved case stays non-fatal but becomes DISTINGUISHING: the
    # commit sha is unique per build, so an unresolved version can never share
    # a key with a resolved one, or with a different commit. And it says so out
    # loud instead of degrading in silence.
    if ! CLOSURE_VERSION="$("$SCRIPT_DIR/../version/resolve-version.sh" --current 2>/dev/null)" ||
        [[ -z "$CLOSURE_VERSION" ]]; then
        CLOSURE_VERSION="untagged-$(git rev-parse HEAD 2>/dev/null || echo unknown)"
        log_warn "No version tag reachable; closure key falls back to '$CLOSURE_VERSION'. Image reuse is disabled for this build."
    fi
    CLOSURE_HASH+="version:${CLOSURE_VERSION}"
    CI_TAG="${CLOSURE_NAME}-$(printf '%s' "$CLOSURE_HASH" | sha256sum | cut -c1-12)"
    log_info "Generated closure tag ($CLOSURE_NAME): $CI_TAG" >&2

elif [[ "$SELF_MODE" == "true" ]]; then
    # Current repo commit hash mode
    CI_TAG=$(git rev-parse --short HEAD)
    log_info "Generated self tag: $CI_TAG" >&2

else
    # Time-based mode (default)
    CI_TAG=$(date -u +%Y%m%d-%H%M%S)
    log_info "Generated CI tag: $CI_TAG" >&2
fi

# Output to file if requested
if [[ -n "$OUTPUT_FILE" ]]; then
    echo "$CI_TAG" >"$OUTPUT_FILE"
    log_info "Wrote CI tag to: $OUTPUT_FILE" >&2
fi

# Output to GITHUB_OUTPUT if requested
if [[ "$GITHUB_OUTPUT_MODE" == "true" ]] && [[ -n "${GITHUB_OUTPUT:-}" ]]; then
    echo "ci_tag=$CI_TAG" >>"$GITHUB_OUTPUT"
    log_info "Set GITHUB_OUTPUT: ci_tag=$CI_TAG" >&2
fi

# Always output to stdout
echo "$CI_TAG"
