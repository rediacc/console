#!/bin/bash
# Run E2E tests with Playwright
# Usage: run-e2e.sh [options]
#
# Options:
#   --workers       Number of parallel workers (default: 1 in CI, 4 local)
#   --config        Playwright config file (default: playwright.config.ts)
#   --filter        Test name filter pattern (passed to --grep)
#   --grep          Alias for --filter (passed to Playwright --grep)
#   --grep-invert   Exclude tests matching pattern (passed to Playwright --grep-invert)
#   --test          Test file filter(s) passed to Playwright
#   --headed        Run tests with visible browser
#   --debug         Open Playwright Inspector for debugging
#   --ui            Open Playwright UI mode (interactive)
#   --fail-on-skip  Fail (exit 1) if ANY test was skipped. Reads the
#                   TextFileReporter's E2E_SKIPPED sentinel; fails closed if
#                   the sentinel is absent. The zero-skip contract: a job must
#                   select only tests its topology can run, never skip.
#   --shard-manifest <path>  T2.12 (PLAN-ci-time-budget). Read this leg's spec
#                   files from a committed `.ci/config/shards/<lane>.json`
#                   (scripts/ci-runner/shard-manifest.ts's ShardManifestFile
#                   shape) instead of running the whole suite. Required together
#                   with --shard; an id of the form
#                   `e2e-workers:<file>#<bucket>` runs only the describe-group
#                   `<bucket>` names (E2E_SHARD_GREP_BUCKETS below), in its own
#                   Playwright invocation, so one leg's --grep never narrows a
#                   different file sharing the leg.
#   --shard         "<index>/<of>", 1-based, the leg to run from --shard-manifest.
#   --also          Comma-separated extra spec files to run alongside a shard
#                   (unconditional, no grep) -- used for the two FULL_INTEGRATION
#                   legs' composition suites, which stay off the sharded plan.
#
# Example:
#   .ci/scripts/test/run-e2e.sh
#   .ci/scripts/test/run-e2e.sh --workers 2
#   .ci/scripts/test/run-e2e.sh --config playwright.ceph.config.ts
#   .ci/scripts/test/run-e2e.sh --filter "system-checks"
#   .ci/scripts/test/run-e2e.sh --grep "@ceph"
#   .ci/scripts/test/run-e2e.sh --grep-invert "@ceph"
#   .ci/scripts/test/run-e2e.sh --test tests/01-system-checks.test.ts
#   .ci/scripts/test/run-e2e.sh --debug
#   .ci/scripts/test/run-e2e.sh --shard-manifest .ci/config/shards/test-e2e-workers.json --shard 1/8

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "$SCRIPT_DIR/../lib/common.sh"

# Parse arguments
WORKERS=""
CONFIG=""
FILTER=""
GREP_INVERT=""
TEST_FILES=()
HEADED=false
DEBUG=false
UI=false
FAIL_ON_SKIP=false
SHARD_MANIFEST=""
SHARD_SPEC=""
ALSO_FILES=""
CURRENT_ARG=""

for arg in "$@"; do
    case "$arg" in
        --workers)
            CURRENT_ARG="workers"
            ;;
        --config)
            CURRENT_ARG="config"
            ;;
        --filter | --grep)
            CURRENT_ARG="filter"
            ;;
        --grep-invert)
            CURRENT_ARG="grep-invert"
            ;;
        --test)
            CURRENT_ARG="test"
            ;;
        --headed)
            HEADED=true
            ;;
        --debug)
            DEBUG=true
            ;;
        --ui)
            UI=true
            ;;
        --fail-on-skip)
            FAIL_ON_SKIP=true
            ;;
        --shard-manifest)
            CURRENT_ARG="shard-manifest"
            ;;
        --shard)
            CURRENT_ARG="shard"
            ;;
        --also)
            CURRENT_ARG="also"
            ;;
        *)
            case "$CURRENT_ARG" in
                workers)
                    WORKERS="$arg"
                    CURRENT_ARG=""
                    ;;
                config)
                    CONFIG="$arg"
                    CURRENT_ARG=""
                    ;;
                filter)
                    FILTER="$arg"
                    CURRENT_ARG=""
                    ;;
                grep-invert)
                    GREP_INVERT="$arg"
                    CURRENT_ARG=""
                    ;;
                test)
                    TEST_FILES+=("$arg")
                    CURRENT_ARG=""
                    ;;
                shard-manifest)
                    SHARD_MANIFEST="$arg"
                    CURRENT_ARG=""
                    ;;
                shard)
                    SHARD_SPEC="$arg"
                    CURRENT_ARG=""
                    ;;
                also)
                    ALSO_FILES="$arg"
                    CURRENT_ARG=""
                    ;;
            esac
            ;;
    esac
done

if [[ (-n "$SHARD_MANIFEST" && -z "$SHARD_SPEC") || (-z "$SHARD_MANIFEST" && -n "$SHARD_SPEC") ]]; then
    echo "run-e2e.sh: --shard-manifest and --shard must both be given, or neither" >&2
    exit 1
fi

# Change to repo root
cd "$(get_repo_root)"

E2E_TESTS_DIR="packages/e2e-tests"

# Determine workers
if [[ -z "$WORKERS" ]]; then
    if is_ci; then
        WORKERS=1
    else
        WORKERS=4
    fi
fi

log_step "Running E2E tests (workers: $WORKERS)..."

# T2.12 (PLAN-ci-time-budget): describe-group buckets `13-postgres-fork-isolation`
# splits into, keyed exactly as the shard manifest's `#<bucket>` suffix. The three
# groups are the file's 6 top-level `test.describe` blocks, paired in source order
# and weighted by their measured share of the file's 8.1-minute total (line count as
# the duration proxy, pending real per-describe timing from a T1.6 unit-duration run).
declare -A E2E_SHARD_GREP_BUCKETS=(
    ["part1"]="PostgreSQL Data Persistence @bridge @integration|Repository Fork Data Inheritance @bridge @integration"
    ["part2"]="Multiple Fork Independence @bridge @integration|Fork Data Integrity @bridge @integration"
    ["part3"]="Large Data Volume Fork @bridge @integration|Service Restart Persistence @bridge @integration"
)

E2E_LOG="$(mktemp)"
RC=0

if [[ -n "$SHARD_MANIFEST" ]]; then
    # Resolve this leg's unit ids from the committed manifest (the same file a
    # local `npm run ci -- --lane test-e2e-workers --shard i/N` replay would read,
    # once run.ts grows a test-lane path -- see scripts/ci-runner/run.ts:1090).
    LEG_IDS_RAW="$(node -e '
        const fs = require("fs");
        const [manifestPath, spec] = process.argv.slice(1);
        const [wantIndex, wantOf] = spec.split("/").map(Number);
        const data = JSON.parse(fs.readFileSync(manifestPath, "utf8"));
        if (data.of !== wantOf) {
            console.error(`shard manifest ${manifestPath} has ${data.of} leg(s); asked for ${wantIndex}/${wantOf}`);
            process.exit(1);
        }
        const leg = data.legs.find((l) => l.index === wantIndex);
        if (!leg || leg.ids.length === 0) {
            console.error(`shard manifest ${manifestPath} has no non-empty leg ${wantIndex}`);
            process.exit(1);
        }
        for (const id of leg.ids) console.log(id);
    ' "$SHARD_MANIFEST" "$SHARD_SPEC")" || exit 1
    LEG_IDS=()
    while IFS= read -r id; do
        LEG_IDS+=("$id")
    done <<<"$LEG_IDS_RAW"

    PLAIN_FILES=()
    BUCKET_FILES=()
    BUCKET_GREPS=()
    for id in "${LEG_IDS[@]}"; do
        rest="${id#e2e-workers:}"
        if [[ "$rest" == "$id" ]]; then
            log_error "shard manifest id '$id' is not an e2e-workers unit"
            exit 1
        fi
        if [[ "$rest" == *"#"* ]]; then
            file="${rest%%#*}"
            bucket="${rest#*#}"
            grep_pattern="${E2E_SHARD_GREP_BUCKETS[$bucket]:-}"
            if [[ -z "$grep_pattern" ]]; then
                log_error "shard manifest bucket '$bucket' (file $file) has no entry in E2E_SHARD_GREP_BUCKETS"
                exit 1
            fi
            BUCKET_FILES+=("$file")
            BUCKET_GREPS+=("$grep_pattern")
        else
            PLAIN_FILES+=("$rest")
        fi
    done
    if [[ -n "$ALSO_FILES" ]]; then
        IFS=',' read -ra ALSO_ARR <<<"$ALSO_FILES"
        PLAIN_FILES+=("${ALSO_ARR[@]}")
    fi

    RUN_OPTS=("--workers=$WORKERS")
    is_ci && RUN_OPTS+=("--max-failures=3")

    # T2.12 follow-up (PLAN-ci-time-budget): a leg used to run one `npx
    # playwright test` invocation for PLAIN_FILES and one more PER bucket.
    # Every invocation loads playwright.config.ts fresh, and that config's
    # globalSetup does a full `ops up --force` VM reset -- so a leg with both
    # plain files and buckets paid that reset 2-4x over (500-578s each, per
    # E2E Workers oracle 1/8's 529s + 500s resets in one job). Collapsed into
    # ONE invocation: every file (plain + bucket, deduped) as positional args,
    # with a single --grep whose alternation either matches a whole plain
    # file (its own relative path, regex-escaped, is a PREFIX of every one of
    # its tests' grep title -- Playwright's grep matches the joined title
    # path, whose first element is the file's path relative to rootDir; see
    # `_grepTitleWithTags`/`_collectGrepTitlePath`/`loadTestFile` in
    # node_modules/playwright/lib/common/index.js) or scopes a bucket's
    # describe-name pattern to its OWN file the same way (escaped file path,
    # then `.*`, then the bucket's alternation in a non-capturing group) so a
    # bucket pattern can never accidentally select a same-named describe in a
    # different file. A file that somehow ends up both plain AND bucketed in
    # one leg still gets the union of both clauses, which is harmless: the
    # whole-file clause already covers the bucket subset.
    ALL_FILES=()
    declare -A _seen_file=()
    for f in "${PLAIN_FILES[@]}" "${BUCKET_FILES[@]}"; do
        if [[ -z "${_seen_file[$f]:-}" ]]; then
            _seen_file[$f]=1
            ALL_FILES+=("$f")
        fi
    done

    COMBINED_GREP="$(node -e '
        const escapeRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");
        const args = process.argv.slice(1);
        let idx = 0;
        const nPlain = parseInt(args[idx++], 10);
        const plain = args.slice(idx, idx + nPlain); idx += nPlain;
        const nBucket = parseInt(args[idx++], 10);
        const bucketFiles = args.slice(idx, idx + nBucket); idx += nBucket;
        const bucketGreps = args.slice(idx, idx + nBucket); idx += nBucket;
        const parts = [];
        for (const f of plain) parts.push(escapeRe(f));
        for (let i = 0; i < nBucket; i++) {
            parts.push(escapeRe(bucketFiles[i]) + ".*(?:" + bucketGreps[i] + ")");
        }
        if (parts.length === 0) {
            process.stderr.write("run-e2e.sh: no files resolved for this leg\n");
            process.exit(1);
        }
        console.log(parts.join("|"));
    ' "${#PLAIN_FILES[@]}" "${PLAIN_FILES[@]}" "${#BUCKET_FILES[@]}" "${BUCKET_FILES[@]}" "${BUCKET_GREPS[@]}")"

    set +e
    (cd "$E2E_TESTS_DIR" && npx playwright test "${RUN_OPTS[@]}" --grep "$COMBINED_GREP" "${ALL_FILES[@]}") 2>&1 | tee -a "$E2E_LOG"
    RC=${PIPESTATUS[0]}
    set -e
else
    # Build command
    CMD=(npx playwright test)
    CMD+=("--workers=$WORKERS")

    # Add config if provided
    [[ -n "$CONFIG" ]] && CMD+=("--config" "$CONFIG")

    # Add filter if provided
    [[ -n "$FILTER" ]] && CMD+=("--grep" "$FILTER")

    # Add grep-invert if provided
    [[ -n "$GREP_INVERT" ]] && CMD+=("--grep-invert" "$GREP_INVERT")

    # Add test files if provided
    if [[ ${#TEST_FILES[@]} -gt 0 ]]; then
        CMD+=("${TEST_FILES[@]}")
    fi

    # Fail fast: stop after 3 failures to avoid wasting 60+ minutes on cascading timeouts
    # (e.g., when repository_create fails on Fedora, all downstream tests would also timeout)
    if is_ci; then
        CMD+=("--max-failures=3")
    fi

    # Add optional flags
    if [[ "$HEADED" == "true" ]]; then
        CMD+=("--headed")
    fi
    if [[ "$DEBUG" == "true" ]]; then
        CMD+=("--debug")
    fi
    if [[ "$UI" == "true" ]]; then
        CMD+=("--ui")
    fi

    # Capture output (still streamed live via tee) so the zero-skip gate can
    # inspect the TextFileReporter's E2E_SKIPPED sentinel after the run.
    set +e
    (cd "$E2E_TESTS_DIR" && "${CMD[@]}") 2>&1 | tee "$E2E_LOG"
    RC=${PIPESTATUS[0]}
    set -e
fi

if [[ "$FAIL_ON_SKIP" == "true" ]]; then
    # Fail closed if the sentinel is absent: the reporter didn't run, so we
    # cannot prove zero skips and must not pass an uninspected run.
    if ! grep -q 'E2E_SKIPPED=' "$E2E_LOG"; then
        log_error "Zero-skip gate ON but no E2E_SKIPPED sentinel found (TextFileReporter missing?). Failing closed."
        rm -f "$E2E_LOG"
        exit 1
    fi
    SKIPPED=$(grep -oE 'E2E_SKIPPED=[0-9]+' "$E2E_LOG" | grep -oE '[0-9]+$' | awk '{s+=$1} END{print s+0}' || true)
    if [[ "${SKIPPED:-0}" -gt 0 ]]; then
        log_error "Zero-skip gate: ${SKIPPED} test(s) were SKIPPED (must be 0). A skipped test is invisible coverage loss."
        log_error "Each E2E job must SELECT only the tests its topology can run (config testMatch/testIgnore), not collect-then-skip."
        echo "----- skipped tests -----"
        grep -E '0\.0s, skipped\)|, skipped\)' "$E2E_LOG" | head -80 || true
        rm -f "$E2E_LOG"
        exit 1
    fi
    log_info "Zero-skip gate: 0 skipped tests"
fi
rm -f "$E2E_LOG"

if [[ $RC -eq 0 ]]; then
    log_info "E2E tests passed"
else
    log_error "E2E tests failed"
    exit 1
fi
