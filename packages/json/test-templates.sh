#!/bin/bash

# Template Testing Script
# Tests all Rediaccfile templates by executing prep/up/down lifecycle
# Monitors health checks and cleans up resources for CI environments
#
# Usage: ./test-templates.sh [OPTIONS]
#
# Options:
#   --category <name>     Test only templates in specified category
#   --template <path>     Test only specific template (relative to templates/)
#   --skip <path>         Skip specific template (can be used multiple times)
#   --verbose             Show detailed output
#   --no-cleanup          Don't cleanup Docker images (for debugging)
#   --output <file>       Output file for JSON results (default: test-results.json)
#   --help                Show this help message

set -euo pipefail

# Configuration
TEST_TIMEOUT=${TEST_TIMEOUT:-240}  # 4 minutes max per function
HEALTH_CHECK_TIMEOUT=${HEALTH_CHECK_TIMEOUT:-360}  # 6 minutes for slow-starting services like GitLab
RESULTS_FILE=${RESULTS_FILE:-test-results.json}
VERBOSE=${VERBOSE:-0}
CLEANUP_IMAGES=${CLEANUP_IMAGES:-1}
CONTINUE_ON_ERROR=${CONTINUE_ON_ERROR:-1}

# Get script directory
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TEMPLATES_DIR="$SCRIPT_DIR/templates"
ARTIFACTS_DIR="${ARTIFACTS_DIR:-$SCRIPT_DIR/test-artifacts}"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
BLUE='\033[0;34m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

# Counters
TOTAL_TESTS=0
PASSED_TESTS=0
FAILED_TESTS=0
SKIPPED_TESTS=0

# Arrays for storing results
declare -a TEST_RESULTS=()
declare -a SKIP_TEMPLATES=()
declare -a FILTER_TEMPLATES=()

# Filter options
FILTER_CATEGORY=""

# Timestamps
START_TIME=$(date +%s)

#==============================================================================
# Helper Functions
#==============================================================================

print_color() {
    local color=$1
    shift
    echo -e "${color}$*${NC}" >&2
}

log_info() {
    print_color "$BLUE" "[INFO] $*"
}

log_success() {
    print_color "$GREEN" "[PASS] $*"
}

log_error() {
    print_color "$RED" "[FAIL] $*"
}

log_warn() {
    print_color "$YELLOW" "[WARN] $*"
}

log_verbose() {
    if [[ $VERBOSE -eq 1 ]]; then
        print_color "$CYAN" "[VERBOSE] $*"
    fi
}

show_help() {
    cat << 'EOF'
Template Testing Script

Tests all Rediaccfile templates by executing prep/up/down lifecycle

Usage: ./test-templates.sh [OPTIONS]

Options:
  --category <name>     Test only templates in specified category
  --template <path>     Test only specific template (relative to templates/)
  --skip <path>         Skip specific template (can be used multiple times)
  --verbose             Show detailed output
  --no-cleanup          Don't cleanup Docker images (for debugging)
  --output <file>       Output file for JSON results (default: test-results.json)
  --help                Show this help message

Environment Variables:
  TEST_TIMEOUT              Max time per function in seconds (default: 240)
  HEALTH_CHECK_TIMEOUT      Max wait for health checks in seconds (default: 360)
  RESULTS_FILE              Output file for JSON results
  VERBOSE                   Set to 1 for detailed output
  CLEANUP_IMAGES            Set to 0 to skip image cleanup

Examples:
  ./test-templates.sh                           # Test all templates
  ./test-templates.sh --category databases      # Test only database templates
  ./test-templates.sh --template databases/postgresql  # Test specific template
  ./test-templates.sh --skip databases/mssql --verbose # Skip MSSQL, verbose output
EOF
}

#==============================================================================
# Template Discovery Functions
#==============================================================================

discover_templates() {
    log_info "Discovering templates in $TEMPLATES_DIR"

    local templates=()
    local skip_count=0

    # Find all directories with Rediaccfile
    while IFS= read -r -d '' rediaccfile; do
        local template_dir=$(dirname "$rediaccfile")
        local relative_path=${template_dir#$TEMPLATES_DIR/}

        # Apply filters
        if [[ -n "$FILTER_CATEGORY" ]]; then
            local category=$(echo "$relative_path" | cut -d'/' -f1)
            if [[ "$category" != "$FILTER_CATEGORY" ]]; then
                continue
            fi
        fi

        if [[ ${#FILTER_TEMPLATES[@]} -gt 0 ]]; then
            local template_matches=0
            for filter_template in "${FILTER_TEMPLATES[@]}"; do
                if [[ "$relative_path" == "$filter_template" ]]; then
                    template_matches=1
                    break
                fi
            done
            if [[ $template_matches -eq 0 ]]; then
                continue
            fi
        fi

        # Check if template should be skipped
        local should_skip=0
        for skip in "${SKIP_TEMPLATES[@]}"; do
            if [[ "$relative_path" == "$skip" ]]; then
                should_skip=1
                break
            fi
        done

        if [[ $should_skip -eq 0 ]]; then
            templates+=("$relative_path")
        else
            log_verbose "Skipping template: $relative_path"
            ((skip_count++)) || true
        fi
    done < <(find "$TEMPLATES_DIR" -name "Rediaccfile" -type f -print0 2>/dev/null | sort -z)

    if [[ ${#templates[@]} -eq 0 ]]; then
        log_error "No templates found matching criteria"
        exit 1
    fi

    log_info "Found ${#templates[@]} templates to test"

    # Output skip count as first line, then templates
    echo "SKIP_COUNT:$skip_count"
    printf '%s\n' "${templates[@]}"
}

#==============================================================================
# Health Check Functions
#==============================================================================

validate_all_containers() {
    local template_dir=$1
    local check_healthchecks=${2:-0}
    local silent=${3:-0}  # When 1, suppress [FAIL] messages (used during polling)

    cd "$template_dir" || return 1

    # Get compose file
    local compose_file="$template_dir/docker-compose.yaml"
    if [[ ! -f "$compose_file" ]]; then
        compose_file="$template_dir/docker-compose.yml"
    fi

    if [[ ! -f "$compose_file" ]]; then
        [[ $silent -eq 0 ]] && log_error "No docker-compose file found"
        return 1
    fi

    # Get expected number of services from docker-compose.yaml
    local expected_count=$(docker compose config --services 2>/dev/null | wc -l)

    # Get actual container states
    local ps_output=$(docker compose ps --format json 2>/dev/null)

    if [[ -z "$ps_output" ]]; then
        [[ $silent -eq 0 ]] && log_error "No containers found (expected $expected_count)"
        return 1
    fi

    # Count containers and collect failures
    local container_count=0
    local running_count=0
    local healthy_count=0
    local unhealthy_containers=()

    while IFS= read -r container_json; do
        ((container_count++)) || true

        local name=$(echo "$container_json" | jq -r '.Name')
        local status=$(echo "$container_json" | jq -r '.Status')
        local state=$(echo "$container_json" | jq -r '.State')
        local health=$(echo "$container_json" | jq -r '.Health // empty')
        local exit_code=$(echo "$container_json" | jq -r '.ExitCode // 0')

        # Check if container is running
        if [[ "$status" =~ ^Up ]]; then
            ((running_count++)) || true

            # If healthchecks are being validated, check health status
            if [[ $check_healthchecks -eq 1 ]]; then
                if [[ -n "$health" ]] && [[ "$health" == "healthy" ]]; then
                    ((healthy_count++)) || true
                elif [[ -n "$health" ]]; then
                    unhealthy_containers+=("$name: health=$health")
                else
                    # Container is running but has no health status (might not have healthcheck defined)
                    ((healthy_count++)) || true
                fi
            fi
        else
            # Container is not running
            if [[ "$state" == "exited" ]]; then
                unhealthy_containers+=("$name: exited (code=$exit_code)")
            elif [[ "$state" == "restarting" ]]; then
                unhealthy_containers+=("$name: restarting")
            else
                unhealthy_containers+=("$name: $status")
            fi
        fi
    done < <(echo "$ps_output" | jq -c '.')

    # Validate container count
    if [[ $container_count -lt $expected_count ]]; then
        local missing=$((expected_count - container_count))
        [[ $silent -eq 0 ]] && log_error "Missing containers: found $container_count, expected $expected_count (missing $missing)"
        return 1
    fi

    # Report unhealthy containers
    if [[ ${#unhealthy_containers[@]} -gt 0 ]]; then
        if [[ $silent -eq 0 ]]; then
            log_error "Unhealthy containers detected:"
            for container_issue in "${unhealthy_containers[@]}"; do
                log_error "  - $container_issue"
            done
        fi
        return 1
    fi

    # Final validation
    if [[ $check_healthchecks -eq 1 ]]; then
        # When checking healthchecks, all containers should be healthy
        if [[ $healthy_count -eq $expected_count ]]; then
            [[ $silent -eq 0 ]] && log_verbose "All $healthy_count container(s) are healthy"
            return 0
        else
            [[ $silent -eq 0 ]] && log_error "Only $healthy_count/$expected_count container(s) are healthy"
            return 1
        fi
    else
        # When not checking healthchecks, all containers should be running
        if [[ $running_count -eq $expected_count ]]; then
            [[ $silent -eq 0 ]] && log_verbose "All $running_count container(s) are running"
            return 0
        else
            [[ $silent -eq 0 ]] && log_error "Only $running_count/$expected_count container(s) are running"
            return 1
        fi
    fi
}

check_health() {
    local template_dir=$1
    local timeout=$HEALTH_CHECK_TIMEOUT
    local interval=5
    local elapsed=0

    log_verbose "Checking container health in $template_dir"

    # Check if docker-compose.yaml has health checks defined
    local compose_file="$template_dir/docker-compose.yaml"
    if [[ ! -f "$compose_file" ]]; then
        compose_file="$template_dir/docker-compose.yml"
    fi

    local has_healthcheck=0
    if [[ -f "$compose_file" ]] && grep -q "healthcheck:" "$compose_file"; then
        has_healthcheck=1
        log_verbose "Health checks defined in compose file"
    fi

    cd "$template_dir" || return 1

    if [[ $has_healthcheck -eq 1 ]]; then
        # Wait for health checks to pass - poll with comprehensive validation
        log_verbose "Waiting for all containers to be healthy (timeout: ${timeout}s)"
        while [[ $elapsed -lt $timeout ]]; do
            # Use silent=1 during polling to suppress [FAIL] messages
            if validate_all_containers "$template_dir" 1 1; then
                log_verbose "All containers healthy after ${elapsed}s"
                return 0
            fi

            sleep $interval
            elapsed=$((elapsed + interval))
            # Only log progress every 30 seconds to reduce noise
            if [[ $((elapsed % 30)) -eq 0 ]]; then
                log_verbose "Waiting for health checks... ${elapsed}s/${timeout}s"
            fi
        done

        log_error "Health check timeout after ${timeout}s"
        # Run validation one more time with silent=0 to get detailed error output
        validate_all_containers "$template_dir" 1 0
        return 1
    else
        # No health checks defined, verify all containers are running
        log_verbose "No health checks defined, verifying all containers are running"
        sleep 10

        # Use silent=0 here since this is a one-time check, not polling
        if validate_all_containers "$template_dir" 0 0; then
            return 0
        else
            log_error "Container validation failed"
            return 1
        fi
    fi
}

#==============================================================================
# Cleanup Functions
#==============================================================================

cleanup_images() {
    local template_dir=$1

    if [[ $CLEANUP_IMAGES -eq 0 ]]; then
        log_verbose "Skipping image cleanup (--no-cleanup)"
        return 0
    fi

    log_verbose "Cleaning up Docker images for $template_dir"

    # Extract images from docker-compose.yaml
    local compose_file="$template_dir/docker-compose.yaml"
    if [[ ! -f "$compose_file" ]]; then
        compose_file="$template_dir/docker-compose.yml"
    fi

    if [[ ! -f "$compose_file" ]]; then
        log_verbose "No compose file found, skipping image cleanup"
        return 0
    fi

    local images=()
    while IFS= read -r image; do
        # Remove any variable substitution or quotes
        image=$(echo "$image" | sed 's/\${[^}]*}//g' | tr -d '"' | tr -d "'" | xargs)
        if [[ -n "$image" ]] && [[ "$image" != *"$"* ]]; then
            images+=("$image")
        fi
    done < <(grep -E "^\s*image:" "$compose_file" | awk '{print $2}')

    # Remove images
    for image in "${images[@]}"; do
        log_verbose "Removing image: $image"
        docker rmi -f "$image" >/dev/null 2>&1 || true
    done

    return 0
}

cleanup_directories() {
    local template_dir=$1

    log_verbose "Cleaning up directories in $template_dir"

    # Remove common data directories
    cd "$template_dir" || return 1

    rm -rf data >/dev/null 2>&1 || true
    rm -rf ./data >/dev/null 2>&1 || true

    # Remove any directories created during testing
    find . -maxdepth 1 -type d -name "data*" -exec rm -rf {} \; 2>/dev/null || true

    return 0
}

cleanup_volumes() {
    log_verbose "Pruning Docker volumes"
    docker volume prune -f >/dev/null 2>&1 || true
    return 0
}

#==============================================================================
# Diagnostic Collection Functions
#==============================================================================

initialize_artifacts() {
    if [[ -d "$ARTIFACTS_DIR" ]]; then
        rm -rf "$ARTIFACTS_DIR" >/dev/null 2>&1 || true
    fi

    mkdir -p "$ARTIFACTS_DIR" >/dev/null 2>&1 || true
    touch "$ARTIFACTS_DIR/.keep" >/dev/null 2>&1 || true
}

collect_template_artifacts() {
    local template_path=$1
    local template_dir=$2
    local stage=${3:-unknown}
    local sanitized_template="${template_path//\//__}"
    local template_artifact_dir="$ARTIFACTS_DIR/$sanitized_template"
    local timestamp stage_dir containers

    mkdir -p "$template_artifact_dir" >/dev/null 2>&1 || true

    timestamp=$(date -u +%Y%m%dT%H%M%SZ)
    stage_dir="$template_artifact_dir/${timestamp}_${stage}"
    mkdir -p "$stage_dir" >/dev/null 2>&1 || true

    log_warn "Collecting diagnostics for $template_path (stage: $stage) -> $stage_dir"

    {
        echo "template_path=$template_path"
        echo "stage=$stage"
        echo "captured_at=$(date -u +%Y-%m-%dT%H:%M:%SZ)"
    } > "$stage_dir/metadata.txt"

    cp -f "$template_dir/Rediaccfile" "$template_artifact_dir/Rediaccfile" >/dev/null 2>&1 || true
    cp -f "$template_dir/docker-compose.yaml" "$template_artifact_dir/docker-compose.yaml" >/dev/null 2>&1 || true
    cp -f "$template_dir/docker-compose.yml" "$template_artifact_dir/docker-compose.yml" >/dev/null 2>&1 || true

    (
        set +e
        cd "$template_dir" 2>/dev/null || exit 0

        docker compose config > "$stage_dir/docker-compose.config" 2>&1 || true
        docker compose ps > "$stage_dir/docker-compose.ps.txt" 2>&1 || true
        docker compose ps --format json > "$stage_dir/docker-compose.ps.json" 2>&1 || true
        docker compose logs --no-color > "$stage_dir/docker-compose.logs" 2>&1 || true

        containers=$(docker compose ps -q 2>/dev/null | tr '\n' ' ')
        containers=$(echo "$containers" | xargs)

        if [[ -n "$containers" ]]; then
            docker inspect $containers > "$stage_dir/docker-inspect.json" 2>&1 || true
            for container in $containers; do
                [[ -z "$container" ]] && continue
                docker logs "$container" > "$stage_dir/${container}.log" 2>&1 || true
            done
        fi
    )
}

#==============================================================================
# Test Execution Functions
#==============================================================================

test_template() {
    local template_path=$1
    local template_dir="$TEMPLATES_DIR/$template_path"

    log_info "Testing template: $template_path"

    # Initialize result structure
    local result='{"name":"'"$template_path"'","category":"'"$(dirname "$template_path")"'"'
    local test_start=$(date +%s)
    local overall_status="passed"
    local error_msg=""
    local first_failure_stage=""
    local original_network_mode="${NETWORK_MODE:-}"
    local auto_network=""
    local using_auto_network=0

    # Check if template directory exists
    if [[ ! -d "$template_dir" ]]; then
        log_error "Template directory not found: $template_dir"
        result+=',"prep":{"status":"failed","duration":"0s","error":"Directory not found"}'
        result+=',"overall":"failed","duration":"0s"}'
        TEST_RESULTS+=("$result")
        ((FAILED_TESTS++)) || true
        return 1
    fi

    # Check if Rediaccfile exists
    if [[ ! -f "$template_dir/Rediaccfile" ]]; then
        log_error "Rediaccfile not found in $template_dir"
        result+=',"prep":{"status":"failed","duration":"0s","error":"Rediaccfile not found"}'
        result+=',"overall":"failed","duration":"0s"}'
        TEST_RESULTS+=("$result")
        ((FAILED_TESTS++)) || true
        return 1
    fi

    cd "$template_dir" || {
        log_error "Failed to change directory to $template_dir"
        result+=',"prep":{"status":"failed","duration":"0s","error":"Cannot cd to directory"}'
        result+=',"overall":"failed","duration":"0s"}'
        TEST_RESULTS+=("$result")
        ((FAILED_TESTS++)) || true
        return 1
    }

    # Source Rediaccfile
    log_verbose "Sourcing Rediaccfile"
    # shellcheck source=/dev/null
    if ! source ./Rediaccfile; then
        log_error "Failed to source Rediaccfile"
        result+=',"prep":{"status":"failed","duration":"0s","error":"Failed to source Rediaccfile"}'
        result+=',"overall":"failed","duration":"0s"}'
        TEST_RESULTS+=("$result")
        ((FAILED_TESTS++)) || true
        return 1
    fi

    # Test prep function
    local prep_start=$(date +%s)
    log_verbose "Running prep()"
    if timeout "$TEST_TIMEOUT" bash -c 'source ./Rediaccfile && prep' >/dev/null 2>&1; then
        local prep_duration=$(($(date +%s) - prep_start))
        log_verbose "prep() passed (${prep_duration}s)"
        result+=',"prep":{"status":"passed","duration":"'"${prep_duration}s"'"}'
    else
        local prep_exit_code=$?
        local prep_duration=$(($(date +%s) - prep_start))
        local prep_error="prep function failed"
        if [[ $prep_exit_code -eq 124 ]]; then
            prep_error="prep function timed out after ${TEST_TIMEOUT}s"
            log_error "prep() timed out"
        else
            log_error "prep() failed with exit code $prep_exit_code"
        fi
        result+=',"prep":{"status":"failed","duration":"'"${prep_duration}s"'","error":"'"$prep_error"'"}'
        overall_status="failed"
        error_msg="prep() failed"
        if [[ -z "$first_failure_stage" ]]; then
            first_failure_stage="prep"
        fi
        collect_template_artifacts "$template_path" "$template_dir" "prep"
    fi

    # Test up function (only if prep passed or CONTINUE_ON_ERROR is set)
    if [[ "$overall_status" == "passed" ]] || [[ $CONTINUE_ON_ERROR -eq 1 ]]; then
        local up_start=$(date +%s)
        log_verbose "Running up()"

        if [[ $using_auto_network -eq 0 && -z "$original_network_mode" ]]; then
            auto_network=$(printf '%s' "$template_path" | tr '[:upper:]' '[:lower:]' | tr -c 'a-z0-9' '_')
            auto_network="rediacc_${auto_network}"
            log_verbose "Auto-configuring NETWORK_MODE=${auto_network}"
            if ! docker network inspect "$auto_network" >/dev/null 2>&1; then
                docker network create "$auto_network" >/dev/null 2>&1 || true
            fi
            export NETWORK_MODE="$auto_network"
            using_auto_network=1
        fi

        if timeout "$TEST_TIMEOUT" bash -c 'source ./Rediaccfile && up' >/dev/null 2>&1; then
            local up_duration=$(($(date +%s) - up_start))
            log_verbose "up() passed (${up_duration}s)"
            result+=',"up":{"status":"passed","duration":"'"${up_duration}s"'"}'
        else
            local up_exit_code=$?
            local up_duration=$(($(date +%s) - up_start))
            local up_error="up function failed"
            if [[ $up_exit_code -eq 124 ]]; then
                up_error="up function timed out after ${TEST_TIMEOUT}s"
                log_error "up() timed out"
            else
                log_error "up() failed with exit code $up_exit_code"
            fi
            result+=',"up":{"status":"failed","duration":"'"${up_duration}s"'","error":"'"$up_error"'"}'
            overall_status="failed"
            error_msg="up() failed"
            if [[ -z "$first_failure_stage" ]]; then
                first_failure_stage="up"
            fi
            collect_template_artifacts "$template_path" "$template_dir" "up"
        fi

        # Check health (only if up passed or CONTINUE_ON_ERROR is set)
        if [[ "$overall_status" == "passed" ]] || [[ $CONTINUE_ON_ERROR -eq 1 ]]; then
            local health_start=$(date +%s)
            log_verbose "Checking health"
            if check_health "$template_dir"; then
                local health_duration=$(($(date +%s) - health_start))
                log_verbose "Health check passed (${health_duration}s)"
                result+=',"health":{"status":"passed","duration":"'"${health_duration}s"'"}'
            else
                local health_duration=$(($(date +%s) - health_start))
                log_error "Health check failed"
                result+=',"health":{"status":"failed","duration":"'"${health_duration}s"'","error":"Health check timeout or containers not healthy"}'
                overall_status="failed"
                error_msg="Health check failed"
                if [[ -z "$first_failure_stage" ]]; then
                    first_failure_stage="health"
                fi
                collect_template_artifacts "$template_path" "$template_dir" "health"
            fi
        fi

        # Always try to run down() for cleanup
        local down_start=$(date +%s)
        log_verbose "Running down()"
        if timeout "$TEST_TIMEOUT" bash -c 'source ./Rediaccfile && down' >/dev/null 2>&1; then
            local down_duration=$(($(date +%s) - down_start))
            log_verbose "down() passed (${down_duration}s)"
            result+=',"down":{"status":"passed","duration":"'"${down_duration}s"'"}'
        else
            local down_exit_code=$?
            local down_duration=$(($(date +%s) - down_start))
            local down_error="down function failed"
            if [[ $down_exit_code -eq 124 ]]; then
                down_error="down function timed out after ${TEST_TIMEOUT}s"
                log_error "down() timed out"
            else
                log_error "down() failed with exit code $down_exit_code"
            fi
            result+=',"down":{"status":"failed","duration":"'"${down_duration}s"'","error":"'"$down_error"'"}'
            overall_status="failed"
            if [[ -z "$error_msg" ]]; then
                error_msg="down() failed"
            fi
            if [[ -z "$first_failure_stage" ]]; then
                first_failure_stage="down"
            fi
            collect_template_artifacts "$template_path" "$template_dir" "down"
        fi
    fi

    # Cleanup
    local cleanup_start=$(date +%s)
    log_verbose "Cleaning up"
    cleanup_images "$template_dir"
    cleanup_directories "$template_dir"
    cleanup_volumes

    if [[ $using_auto_network -eq 1 && -n "$auto_network" ]]; then
        log_verbose "Removing auto-configured network: $auto_network"
        docker network rm "$auto_network" >/dev/null 2>&1 || true
        unset NETWORK_MODE
    elif [[ -n "$original_network_mode" ]]; then
        export NETWORK_MODE="$original_network_mode"
    fi

    local cleanup_duration=$(($(date +%s) - cleanup_start))
    result+=',"cleanup":{"status":"passed","duration":"'"${cleanup_duration}s"'"}'

    # Calculate total duration
    local test_duration=$(($(date +%s) - test_start))

    if [[ "$overall_status" == "failed" && -z "$first_failure_stage" ]]; then
        collect_template_artifacts "$template_path" "$template_dir" "unknown"
    fi

    # Finalize result
    result+=',"overall":"'"$overall_status"'","duration":"'"${test_duration}s"'"'
    if [[ -n "$error_msg" ]]; then
        result+=',"error":"'"$error_msg"'"'
    else
        result+=',"error":null'
    fi
    result+='}'

    # Store result
    TEST_RESULTS+=("$result")

    # Update counters
    if [[ "$overall_status" == "passed" ]]; then
        ((PASSED_TESTS++)) || true
        log_success "Template passed: $template_path (${test_duration}s)"
    else
        ((FAILED_TESTS++)) || true
        log_error "Template failed: $template_path (${test_duration}s)"
    fi

    # Return to script directory
    cd "$SCRIPT_DIR" || true

    return 0
}

#==============================================================================
# Reporting Functions
#==============================================================================

generate_report() {
    local end_time=$(date +%s)
    local total_duration=$((end_time - START_TIME))
    local duration_formatted="${total_duration}s"

    # Calculate minutes if duration is significant
    if [[ $total_duration -ge 60 ]]; then
        local minutes=$((total_duration / 60))
        local seconds=$((total_duration % 60))
        duration_formatted="${minutes}m${seconds}s"
    fi

    log_info "Generating test report"

    # Create JSON report
    cat > "$RESULTS_FILE" << EOF
{
  "summary": {
    "total": $TOTAL_TESTS,
    "passed": $PASSED_TESTS,
    "failed": $FAILED_TESTS,
    "skipped": $SKIPPED_TESTS,
    "duration": "$duration_formatted",
    "timestamp": "$(date -u +%Y-%m-%dT%H:%M:%SZ)"
  },
  "results": [
EOF

    # Add results
    local first=1
    for result in "${TEST_RESULTS[@]}"; do
        if [[ $first -eq 1 ]]; then
            first=0
        else
            echo "," >> "$RESULTS_FILE"
        fi
        echo "    $result" >> "$RESULTS_FILE"
    done

    cat >> "$RESULTS_FILE" << EOF

  ]
}
EOF

    log_info "Test report saved to $RESULTS_FILE"
}

print_summary() {
    local end_time=$(date +%s)
    local total_duration=$((end_time - START_TIME))
    local duration_formatted="${total_duration}s"

    if [[ $total_duration -ge 60 ]]; then
        local minutes=$((total_duration / 60))
        local seconds=$((total_duration % 60))
        duration_formatted="${minutes}m${seconds}s"
    fi

    echo "" >&2
    echo "==========================================" >&2
    echo "          TEST SUMMARY" >&2
    echo "==========================================" >&2
    echo "Total tests:    $TOTAL_TESTS" >&2
    print_color "$GREEN" "Passed:         $PASSED_TESTS"
    print_color "$RED" "Failed:         $FAILED_TESTS"
    print_color "$YELLOW" "Skipped:        $SKIPPED_TESTS"
    echo "Duration:       $duration_formatted" >&2
    echo "==========================================" >&2
    echo "" >&2

    if [[ $FAILED_TESTS -gt 0 ]]; then
        print_color "$RED" "Some tests failed. Check $RESULTS_FILE for details."
        return 1
    else
        print_color "$GREEN" "All tests passed!"
        return 0
    fi
}

#==============================================================================
# Main Function
#==============================================================================

main() {
    # Parse arguments
    while [[ $# -gt 0 ]]; do
        case $1 in
            --category)
                FILTER_CATEGORY="$2"
                shift 2
                ;;
            --template)
                FILTER_TEMPLATES+=("$2")
                shift 2
                ;;
            --skip)
                SKIP_TEMPLATES+=("$2")
                shift 2
                ;;
            --verbose)
                VERBOSE=1
                shift
                ;;
            --no-cleanup)
                CLEANUP_IMAGES=0
                shift
                ;;
            --output)
                RESULTS_FILE="$2"
                shift 2
                ;;
            --help)
                show_help
                exit 0
                ;;
            *)
                log_error "Unknown option: $1"
                show_help
                exit 1
                ;;
        esac
    done

    log_info "Starting template tests"
    log_info "Templates directory: $TEMPLATES_DIR"
    log_info "Results file: $RESULTS_FILE"

    if [[ -n "$FILTER_CATEGORY" ]]; then
        log_info "Filter category: $FILTER_CATEGORY"
    fi

    if [[ ${#FILTER_TEMPLATES[@]} -gt 0 ]]; then
        log_info "Filter templates: ${FILTER_TEMPLATES[*]}"
    fi

    if [[ ${#SKIP_TEMPLATES[@]} -gt 0 ]]; then
        log_info "Skipping templates: ${SKIP_TEMPLATES[*]}"
    fi

    initialize_artifacts

    # Discover templates
    mapfile -t discovery_output < <(discover_templates)

    # Parse skip count from first line
    if [[ "${discovery_output[0]}" =~ ^SKIP_COUNT:([0-9]+)$ ]]; then
        SKIPPED_TESTS="${BASH_REMATCH[1]}"
        # Remove first line (skip count) to get template list
        templates=("${discovery_output[@]:1}")
    else
        # Fallback if format is unexpected
        templates=("${discovery_output[@]}")
    fi

    TOTAL_TESTS=${#templates[@]}

    # Test each template
    for template in "${templates[@]}"; do
        test_template "$template"
        echo "" >&2
    done

    # Generate report
    generate_report

    # Print summary
    print_summary

    local exit_code=$?
    exit $exit_code
}

# Run main function
main "$@"
