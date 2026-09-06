#!/bin/bash
# Tests for .ci/media/bridge.sh -- VM provisioning and the host->bridge SSH helpers.
#
# THE PART THAT CAN BE TESTED WITHOUT A CLUSTER is bigger than it looks. Four of these
# nine functions are pure address arithmetic over .provision-state and two shell
# variables, and they are exactly the ones that go wrong quietly: a worker index that is
# off by one, or a default that stops matching VM_NET_BASE, sends a recording at a
# machine that is not there and reports it as an SSH problem. Those are staged with
# fixture files and asserted here.
#
# The remaining five drive a real libvirt cluster or a real SSH endpoint. What is
# asserted about them is what a test legitimately can: the SHAPE of the command they
# build. `ssh` and `rsync` are fakes that record their argv, so the -F config path, the
# BatchMode and StrictHostKeyChecking settings and the rsync -e wrapper are all pinned
# without a VM existing.
#
# Nothing here reaches a network. ssh, rsync, rdc.sh, go and node are all absent or
# faked, and the machine mutex in docs/ci-overhaul/08-driver-contract.md §4 is untouched.

set -euo pipefail

# ONE LINE TO REACH THE PRELUDE, and the prelude does the rest: it assigns ROOT, sources
# test-helpers.sh, and carries the ownership assertions and the module sandbox. This block
# used to be five lines whose only job was to find that file, in seven files;
# check:ci-shape-duplication counted them and it was right to.
# shellcheck source=../../../media/verify.sh
# BLOCKER: the media gate-test prelude, the extraction's completeness proof and the module sandbox
source "$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../media" && pwd)/verify.sh"

MODULE="$ROOT/.ci/media/bridge.sh"

MOVED=(
    provision_start
    provision_stop
    provision_status
    _bridge_ip
    _worker_ip
    _bridge_ssh
    _bridge_rsync
    _build_cli_sea_cached
    _ensure_bridge_recording_tooling
)

run_bridge() {
    media_run_module "$1" "bridge.sh" "$2"
}

test_every_moved_function_is_solely_owned_by_this_module() {
    # WHAT THIS REPLACED. Until the cutover run.sh carried its own copy of all nine, and
    # this asserted the bodies were byte-identical. run.sh has no copies now, so the
    # equivalent question is ownership: exactly one file defines each name, it is this
    # module, run.sh and media.sh define none of them, and media-entry.sh resolves every
    # name to this file's body rather than to some other copy.
    media_assert_module_owns bridge.sh "${MOVED[@]}"
}

test_the_ssh_config_constant_lives_here_and_only_here() {
    # _BRIDGE_SSH_CONFIG is not a function, so the ownership assertion cannot see it, and
    # it is the single value every other helper in this module depends on. Assert the
    # same three things by hand: this module defines it, run.sh no longer does, and the
    # value that ends up in scope after sourcing media-entry.sh is the one written here.
    local in_module in_scope expected
    in_module="$(grep '^_BRIDGE_SSH_CONFIG=' "$MODULE")"
    [ -n "$in_module" ] || log_fail "_BRIDGE_SSH_CONFIG is not defined in bridge.sh -- this assertion has nothing to check"
    media_assert_absent_from_origins '^_BRIDGE_SSH_CONFIG=' "$ROOT" \
        "an origin still assigns _BRIDGE_SSH_CONFIG -- the cutover left a second copy of the value"
    expected="$HOME/.renet/staging/.ssh/config"
    in_scope="$("$BASH" -c "source '$ROOT/.ci/media/media-entry.sh' >/dev/null 2>&1; printf '%s' \"\${_BRIDGE_SSH_CONFIG:-}\"")"
    assert_eq "$in_scope" "$expected" "media-entry.sh must put the module's _BRIDGE_SSH_CONFIG in scope"
    log_pass "_BRIDGE_SSH_CONFIG is defined only in bridge.sh and reaches the entry point with its value intact"
}

test_the_ownership_assertion_can_fail() {
    # A worker index off by one is the exact defect this module invites, but a mutated
    # BODY is no longer detectable by comparison -- there is nothing left to compare it
    # against. What is detectable, and what the cutover made an invariant, is a SECOND
    # definition, so _worker_ip is the name the shared control re-plants into each origin.
    media_assert_ownership_control "$1" bridge.sh _worker_ip
}

# The off-by-one the fidelity assertion used to guard is still guarded, by the fixture
# cases further down (_case_ips_from_provision_state pins worker 1 to the FIRST entry of
# worker_ips). This control proves those cases are reading this module: it rewrites the
# index in a copy and requires the addresses they assert to change.
_case_a_mutated_module_changes_what_the_behaviour_cases_see() {
    local d="$1"
    local MEDIA_MODULE_DIR="$d/mutant"
    run_bridge "$d/staged" "echo \"w1=\$(_worker_ip 1)\"" ||
        log_fail "the mutated copy did not run at all (output: $LAST_OUT)"
    media_assert_mutation_swapped "$LAST_OUT" "w1=10.9.8.21" "w1=10.9.8.22" "worker address"
}

test_a_planted_mutation_is_visible_to_the_behaviour_cases() {
    local d="$1"
    mkdir -p "$d/staged" "$d/mutant"
    printf 'bridge_ip=10.9.8.1\nworker_ips=10.9.8.21,10.9.8.22\n' >"$d/staged/.provision-state"
    # The off-by-one is planted in the STATE-FILE branch, which is the one the fixture
    # cases exercise. Planting it in the VM_WORKERS fallback instead would leave the
    # control green while proving nothing, because a staged .provision-state never
    # reaches that line -- a mistake made once while writing this file.
    sed 's/cut -d, -f"\$idx"/cut -d, -f"$((idx + 1))"/' "$MODULE" >"$d/mutant/bridge.sh"
    grep -q 'f"$((idx + 1))"' "$d/mutant/bridge.sh" || log_fail "the off-by-one did not apply, so this control would pass for the wrong reason"
    with_fake_bin "+grep +cut +uname" _case_a_mutated_module_changes_what_the_behaviour_cases_see "$d"
    log_pass "an off-by-one worker index in bridge.sh changes what the fixture cases observe"
}

# THE DELEGATION ITSELF. `provision start|stop|status` is the one media surface whose
# functions live in this module, and after the cutover the only thing standing between
# the operator's `./run.sh provision start` and provision_start() is run.sh's exec into
# media-entry.sh. This drives that whole path in a sandbox repo -- run.sh, the exec,
# media-entry.sh's case tree, bridge.sh -- with a marker planted inside the function
# body, so nothing about it is simulated and nothing downstream of the marker runs.
_case_the_chain_reaches_this_module() {
    local repo="$1"
    media_chain_run "$repo" run.sh provision start --basic ||
        log_fail "./run.sh provision start failed in the sandbox: $LAST_CHAIN"
    assert_eq "$LAST_CHAIN" "MEDIA_CHAIN_REACHED:provision_start:--basic" \
        "run.sh must reach bridge.sh's provision_start with its arguments intact"
}

_case_the_chain_control_breaks_it() {
    local repo="$1"
    local rc=0
    media_chain_run "$repo" run.sh provision start --basic || rc=$?
    [ "$rc" -eq 0 ] &&
        log_fail "the chain still succeeded after provision_start was renamed in bridge.sh, so the probe proves nothing"
    assert_not_contains "$LAST_CHAIN" "MEDIA_CHAIN_REACHED" "no marker may be reported once the module no longer defines the name"
    assert_contains "$LAST_CHAIN" "provision_start" "the failure names the function the delegation could not find"
}

test_run_sh_still_reaches_this_module() {
    local d="$1" repo
    repo="$(media_chain_sandbox "$d")"
    media_chain_probe "$repo" bridge.sh provision_start
    with_fake_bin "+uname +dirname" _case_the_chain_reaches_this_module "$repo"
    # CONTROL: rename the function the delegation is looking for. Nothing else changes.
    media_chain_mutate "$repo" .ci/media/bridge.sh 's/^provision_start() {/provision_start_RENAMED() {/'
    with_fake_bin "+uname +dirname" _case_the_chain_control_breaks_it "$repo"
    log_pass "./run.sh provision start reaches bridge.sh's provision_start, and stops reaching it when the module renames it"
}

_case_ips_from_provision_state() {
    local d="$1"
    run_bridge "$d/staged" "echo \"bridge=\$(_bridge_ip) w1=\$(_worker_ip 1) w2=\$(_worker_ip 2)\"" ||
        log_fail "IP resolution failed (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "bridge=10.9.8.1" "the bridge IP comes from .provision-state"
    assert_contains "$LAST_OUT" "w1=10.9.8.21" "worker 1 is the FIRST entry of worker_ips"
    assert_contains "$LAST_OUT" "w2=10.9.8.22" "worker 2 is the second, so the index is 1-based"
}

_case_ips_from_defaults() {
    local d="$1"
    run_bridge "$d/bare" "echo \"bridge=\$(_bridge_ip) w1=\$(_worker_ip 1) w2=\$(_worker_ip 2)\"" ||
        log_fail "IP resolution failed (output: $LAST_OUT)"
    assert_contains "$LAST_OUT" "bridge=192.168.111.1" "with no state file the documented default applies"
    assert_contains "$LAST_OUT" "w1=192.168.111.11" "the default worker list starts at .11"
    assert_contains "$LAST_OUT" "w2=192.168.111.12" "and its second entry is .12"
}

test_address_resolution_reads_state_then_falls_back() {
    local d="$1"
    mkdir -p "$d/staged" "$d/bare"
    printf 'bridge_ip=10.9.8.1\nworker_ips=10.9.8.21,10.9.8.22\n' >"$d/staged/.provision-state"
    with_fake_bin "+grep +cut +uname" _case_ips_from_provision_state "$d"
    with_fake_bin "+grep +cut +uname" _case_ips_from_defaults "$d"
    log_pass "_bridge_ip and _worker_ip read .provision-state and fall back to the documented defaults"
}

_case_ssh_command_shape() {
    local d="$1"
    run_bridge "$d/staged" "_bridge_ssh whoami" || log_fail "the ssh call failed (output: $LAST_OUT)"
    local call
    call="$(fake_bin_record ssh)"
    assert_contains "$call" "-F $HOME/.renet/staging/.ssh/config" "the generated ops SSH config is used, never a hardcoded user or key"
    assert_contains "$call" "-o BatchMode=yes" "BatchMode keeps a missing key from hanging on a prompt"
    assert_contains "$call" "-o StrictHostKeyChecking=no" "a freshly provisioned VM has no known_hosts entry yet"
    assert_contains "$call" "-o ConnectTimeout=15" "the connect timeout is pinned"
    assert_contains "$call" "10.9.8.1 whoami" "it targets the resolved bridge IP and forwards the command"
}

_case_rsync_command_shape() {
    local d="$1"
    run_bridge "$d/staged" "_bridge_rsync /src/ host:/dst/" || log_fail "the rsync call failed (output: $LAST_OUT)"
    local call
    call="$(fake_bin_record rsync)"
    assert_contains "$call" "-e ssh -F $HOME/.renet/staging/.ssh/config" "rsync tunnels over the SAME generated config"
    assert_contains "$call" "/src/ host:/dst/" "the paths are forwarded verbatim"
}

test_the_ssh_and_rsync_wrappers_build_the_right_command() {
    local d="$1"
    # Its own fixture: with_temp_dir hands each test a FRESH directory, so the state file
    # staged by the address-resolution test is not here. Assuming otherwise made this case
    # assert against the fallback IP while claiming to assert against the staged one.
    mkdir -p "$d/staged"
    printf 'bridge_ip=10.9.8.1\nworker_ips=10.9.8.21,10.9.8.22\n' >"$d/staged/.provision-state"
    with_fake_bin "ssh +grep +cut +uname" _case_ssh_command_shape "$d"
    with_fake_bin "rsync ssh +grep +cut +uname" _case_rsync_command_shape "$d"
    log_pass "_bridge_ssh and _bridge_rsync pin the config path and the four connection options"
}

_case_provision_delegates_to_rdc() {
    local d="$1"
    run_bridge "$d" "provision_start --basic" || log_fail "provision_start failed (output: $LAST_OUT)"
    run_bridge "$d" "provision_stop" || log_fail "provision_stop failed (output: $LAST_OUT)"
    run_bridge "$d" "provision_status" || log_fail "provision_status failed (output: $LAST_OUT)"
    local calls
    calls="$(<"$d/rdc-calls")"
    assert_contains "$calls" "ops up --basic" "start forwards its arguments to rdc ops up"
    assert_contains "$calls" "ops down" "stop is rdc ops down"
    assert_contains "$calls" "ops status" "status is rdc ops status"
}

test_provisioning_is_a_thin_wrapper_over_rdc_ops() {
    # These three had NO definition anywhere in the repo once, and every caller died with
    # "provision_start: command not found". A fake rdc.sh at the fixture root proves they
    # exist, that they delegate, and that start still forwards "$@" -- without libvirt.
    local d="$1"
    printf '#!/bin/bash\nprintf "%%s\\n" "$*" >>"%s/rdc-calls"\n' "$d" >"$d/rdc.sh"
    chmod +x "$d/rdc.sh"
    : >"$d/rdc-calls"
    with_fake_bin "+cat +uname" _case_provision_delegates_to_rdc "$d"
    log_pass "provision start/stop/status delegate to rdc ops, and start forwards its arguments"
}

log_test "test-media-bridge"
test_every_moved_function_is_solely_owned_by_this_module
test_the_ssh_config_constant_lives_here_and_only_here
with_temp_dir test_the_ownership_assertion_can_fail
with_temp_dir test_a_planted_mutation_is_visible_to_the_behaviour_cases
with_temp_dir test_run_sh_still_reaches_this_module
with_temp_dir test_address_resolution_reads_state_then_falls_back
with_temp_dir test_the_ssh_and_rsync_wrappers_build_the_right_command
with_temp_dir test_provisioning_is_a_thin_wrapper_over_rdc_ops
echo ""
log_pass "all tests passed"
