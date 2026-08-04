#!/bin/bash
# drill license — the live licensing battery, on real machines.
#
#   ./run.sh drill license [--legs a,b,c,d,e,f] [--selftest] [--no-restart]
#                          [--vm <ip>] [--vm2 <ip>] [--ssh-user <u>] [--ssh-key <p>]
#                          [--keep-work]
#
# THIS ONE COSTS REAL RESOURCES, so it says so before it does anything and
# refuses to start if the machines are not already there. It never provisions
# them itself: bringing up VMs is minutes of the operator's hardware, and a
# drill that silently decides to do that is a drill nobody runs twice.
#
# WHAT IT PROVES, one leg per licensing claim the campaign makes:
#
#   a  A DATASTORE FORK RE-METERS.  Forking a datastore re-mints its
#      datastoreId, so the repo inside the clone no longer has a licence under
#      the new scope: it reads `missing`, a reissue claims a fresh slot, and
#      the PARENT's licence is untouched. This is the hole the old per-repo
#      store had, where parent and fork shared one blob under the same GUID.
#   b  A PLAIN MIGRATION DOES NOT.  The descriptor travels inside the datastore,
#      so relocating the DATASTORE to another node (`datastore attach --to`)
#      carries its identity along and the repo is not re-metered on datastore
#      grounds. Not to be confused with `repo migrate`, which moves the repo OUT
#      of its datastore and legitimately re-meters; see the leg for why.
#   c  RENEWAL FROM A CREDENTIAL-LESS MACHINE.  `renet license renew` works with
#      no account token anywhere on the box: the installed blob carries its own
#      renewalUrl and its signature is the credential. This is what keeps
#      scheduled backups alive on fork-heavy machines.
#   d  RENEWAL REFUSAL ON A LAPSED SUBSCRIPTION, with the refusal code surfaced
#      rather than swallowed.
#   e  SOFT CLAIM OVER CAP.  Past maxActivations, renewal still SUCCEEDS and the
#      over-limit state becomes visible. Metering honestly beats breaking
#      backups; only new issuance blocks hard.
#   f  THE DTO BOUNDARY.  chainHash (and, on a delegated deployment,
#      delegationCert) survive the HTTP response. They used to be stripped by
#      the response airlock, and no test crossed the HTTP boundary to notice.
#      Ships with a planted-strip control, so a green here is not a green from
#      an assertion that cannot fail.
#
# COST. Legs b through f need the basic ops cluster (2 VMs). Leg a needs Ceph,
# which only exists in the FULL cluster (6 VMs). The preflight reports which
# legs the machines currently present can support and refuses the rest by name,
# rather than running them and blaming the failure on the code.
#
# REUSE. Where an assertion already exists offline it is named here rather than
# rewritten: .ci/scripts/private/license-e2e.sh scenarios S8a-S8e are the
# VM-less form of leg a (parent `valid`, fork `missing`, fork-issued `valid`,
# parent still `valid`, a copied blob `identity_mismatch`), and its
# assert_status helper is the shape drill_repo_status follows here. That script
# is the cheap control: if a leg fails here but its S8 twin passes there, the
# difference is the machine, not the licence logic.
#
# SELFTEST. `--selftest` plants one assertion that cannot pass and stops before
# any VM work, so proving the instrument costs nothing and needs no hardware.

set -euo pipefail

DRILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$DRILL_DIR/../../.ci/scripts/lib/common.sh"
# shellcheck source=lib.sh
source "$DRILL_DIR/lib.sh"

RESTART_GATEWAY=1
LEGS="a,b,c,d,e,f"
VM_NET_BASE="${VM_NET_BASE:-192.168.111}"
VM_IP="${VM_NET_BASE}.11"
VM2_IP="${VM_NET_BASE}.12"
SSH_USER="${SSH_USER:-$USER}"
# The ops VMs authorize the key `renet ops` itself provisions them with, which
# is id_rsa under the renet staging folder (opsconfig/config.go:292, rooted at
# RENET_DATA_DIR or ~/.renet). Do NOT default to ~/.ssh/id_ed25519: these VMs
# reject it, and the failure is invisible from a plain `ssh` because OpenSSH
# silently falls through to id_rsa as a default identity and connects anyway,
# while the CLI (ssh2, one explicit key, no fallback) fails with the unhelpful
# "All configured authentication methods failed".
SSH_KEY="${SSH_KEY:-${RENET_DATA_DIR:-$HOME/.renet}/staging/.ssh/id_rsa}"
# `renet (in PATH)` is the CLI's own default for a provisioned machine.
VM_RENET="${DRILL_RENET_PATH:-renet}"

DRILL_EMAIL="drill-license-$(date +%s)@rediacc.io"
DRILL_PASSWORD="DrillLicense123!"
# The activation cap this drill starts from, seeded explicitly rather than
# inherited from the dev server's default, so leg e asserts against a number
# this file owns and teardown restores that same number.
START_MAX_ACTIVATIONS=3
RDC="$DRILL_ROOT_DIR/rdc.sh"

CONFIG_NAME="drill-license"
CONFIG_HOME=""
SERVER_URL=""
API_TOKEN=""
SUBSCRIPTION_ID=""
ADMIN_JAR=""

MACHINE_NAME="drill-lic-1"
MACHINE2_NAME="drill-lic-2"
DATASTORE_NAME="drill-ds"
FORK_TAG="remeter"
REPO_NAME="drill-repo"

CEPH_AVAILABLE=0
SUBSCRIPTION_LAPSED=0
SUBSCRIPTION_CAP_LOWERED=0

drill_teardown_hook() {
    # Restore anything the drill changed on the SUBSCRIPTION, because those
    # edits outlive the work directory: a suspended subscription or a cap of 1
    # left behind would make the next run (or the next session) fail for a
    # reason that has nothing to do with what it is testing.
    if [[ -n "$ADMIN_JAR" && -n "$SUBSCRIPTION_ID" ]]; then
        if [[ "$SUBSCRIPTION_LAPSED" == "1" || "$SUBSCRIPTION_CAP_LOWERED" == "1" ]]; then
            drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
                "{\"status\":\"active\",\"maxActivations\":$START_MAX_ACTIVATIONS}" \
                >/dev/null 2>&1 || true
        fi
    fi
    # The VMs are deliberately NOT torn down: they are the operator's, they
    # take minutes to rebuild, and this drill did not create them.
    return 0
}

drill_parse_args() {
    drill_parse_common_args "$@"
    local -a rest=(${DRILL_ARGS_REST+"${DRILL_ARGS_REST[@]}"})
    local i=0
    while [[ $i -lt ${#rest[@]} ]]; do
        case "${rest[$i]}" in
            --no-restart) RESTART_GATEWAY=0 ;;
            --legs)
                i=$((i + 1))
                LEGS="${rest[$i]:-}"
                ;;
            --vm)
                i=$((i + 1))
                VM_IP="${rest[$i]:-}"
                ;;
            --vm2)
                i=$((i + 1))
                VM2_IP="${rest[$i]:-}"
                ;;
            --ssh-user)
                i=$((i + 1))
                SSH_USER="${rest[$i]:-}"
                ;;
            --ssh-key)
                i=$((i + 1))
                SSH_KEY="${rest[$i]:-}"
                ;;
            *)
                log_error "Unknown option: ${rest[$i]}"
                echo "Usage: ./run.sh drill license [--legs a,b,c,d,e,f] [--selftest]" \
                    "[--no-restart] [--vm <ip>] [--vm2 <ip>] [--ssh-user <u>] [--ssh-key <p>]" >&2
                exit 2
                ;;
        esac
        i=$((i + 1))
    done
}

leg_enabled() {
    [[ ",$LEGS," == *",$1,"* ]]
}

# needs_vm — true when any selected leg touches a machine. Leg f is the only
# one that does not, so `--legs f` must skip every VM-shaped precondition.
needs_vm() {
    leg_enabled a || leg_enabled b || leg_enabled c || leg_enabled d || leg_enabled e
}

# -----------------------------------------------------------------------------
# Cost declaration and preflight
# -----------------------------------------------------------------------------

announce_cost() {
    cat <<EOF

  This drill runs against the ops VM cluster. It does NOT provision anything.

    legs b,c,d,e   need the BASIC cluster   ./rdc.sh ops up --basic
                   2 VMs: ${VM_NET_BASE}.1 (bridge) + ${VM_NET_BASE}.11 (worker)
                   about 4 GB RAM and 16 GB disk each

    leg  a         needs the FULL cluster   ./rdc.sh ops up
                   6 VMs including the three Ceph nodes ${VM_NET_BASE}.21/.22/.23
                   about 24 GB RAM and ~190 GB disk in total
                   (a datastore fork is RBD-only; a local-backend fork is
                    refused outright, so leg a cannot run without Ceph)

    leg  f         needs no VM at all: it is an HTTP-boundary assertion

  VMs persist across sessions and are torn down only by ./rdc.sh ops down.
  Selected legs: ${LEGS}

EOF
}

require_tool() {
    local tool="$1" hint="$2"
    if ! command -v "$tool" >/dev/null 2>&1; then
        log_error "Missing required tool: $tool ($hint)"
        return 1
    fi
    return 0
}

preflight_tools() {
    drill_step "Preflight: tools"
    local ok=0
    require_tool ssh "openssh-client" || ok=1
    require_tool curl "curl" || ok=1
    require_tool node "Node.js — every wrapper in this repo needs it" || ok=1
    if needs_vm && [[ ! -f "$SSH_KEY" ]]; then
        log_error "SSH key not found at $SSH_KEY (override with --ssh-key)"
        ok=1
    fi
    [[ $ok -eq 0 ]] || exit 1
    drill_note "ssh user=$SSH_USER key=$SSH_KEY"
}

# preflight_ssh — prove THIS key authenticates to the machine, before any setup
# step depends on it. The CLI's failure mode here is a single unhelpful line
# ("All configured authentication methods failed") emitted from deep inside
# `machine setup`, so the key is checked where the error can still name the fix.
preflight_ssh() {
    # Leg f is an HTTP-boundary assertion and touches no machine, so `--legs f`
    # must not be gated on an SSH key or a running VM.
    needs_vm || return 0
    drill_step "Preflight: the SSH key actually authenticates"
    if _ssh "$VM_IP" true 2>/dev/null; then
        drill_note "authenticated to $VM_IP as $SSH_USER with $(basename "$SSH_KEY")"
        return 0
    fi
    log_error "Cannot authenticate to $VM_IP as $SSH_USER using $SSH_KEY."
    log_error "This is the key 'renet ops' provisions the VMs with; if you rebuilt them"
    log_error "with a different one, pass it:  ./run.sh drill license --ssh-key <path>"
    log_error "A plain 'ssh' may still succeed here while this fails — OpenSSH falls back"
    log_error "to your other default identities, and the CLI does not."
    exit 1
}

# preflight_agent_overrides — the drill's verbs provision and tear down real
# infrastructure, and two independent guards block them in agent mode:
#
#   REDIACC_ALLOW_CLUSTER_OPS  every mutating datastore verb (gate class D) —
#                              leg a's `datastore create` and `datastore fork`,
#                              leg b's `datastore attach`
#   REDIACC_ALLOW_GRAND_REPO   grand-repo verbs — leg a's `repo create` and
#                              leg b's `repo down`
#
# Both are ancestry-verified: the OPERATOR must export them before the agent
# session starts, and an override set from inside the session is rejected on
# purpose. Reporting BOTH missing vars at once matters — discovering them one
# failed run at a time is two wasted cluster runs.
preflight_agent_overrides() {
    drill_step "Preflight: agent-mode authorization"
    local agent=0
    [[ -n "${REDIACC_AGENT:-}${CLAUDECODE:-}${GEMINI_CLI:-}${COPILOT_CLI:-}${CURSOR_TRACE_ID:-}" ]] && agent=1
    if [[ $agent -eq 0 ]]; then
        drill_note "not an agent session: these guards do not apply"
        return 0
    fi

    local -a missing=()
    if { leg_enabled a || leg_enabled b; } && [[ -z "${REDIACC_ALLOW_CLUSTER_OPS:-}" ]]; then
        missing+=("REDIACC_ALLOW_CLUSTER_OPS=*  (leg a: datastore create/fork, leg b: datastore attach)")
    fi
    if { leg_enabled a || leg_enabled b; } && [[ -z "${REDIACC_ALLOW_GRAND_REPO:-}" ]]; then
        missing+=("REDIACC_ALLOW_GRAND_REPO=*   (leg a: repo create, leg b: repo down)")
    fi
    if [[ ${#missing[@]} -eq 0 ]]; then
        drill_note "required overrides are present (the CLI still verifies they predate this session)"
        return 0
    fi
    agent_override_blocked_message "${missing[@]}"
    exit 1
}

# The one place this precondition is worded, used by the preflight and by leg a
# when the CLI refuses an override this script could not evaluate from bash.
agent_override_blocked_message() {
    log_error "This drill's selected legs are blocked in agent mode. Missing override(s):"
    local m
    for m in "$@"; do
        log_error "    $m"
    done
    log_error ""
    log_error "These verbs provision and tear down real infrastructure, so an agent cannot"
    log_error "authorize them itself, and an override exported from inside the session is"
    log_error "rejected on purpose."
    log_error ""
    log_error "  To run them:  export the variable(s) in YOUR terminal BEFORE starting the"
    log_error "                agent session, or run this drill directly as the operator."
    log_error "  To skip them: ./run.sh drill license --legs c,d,e,f   (needs a licensed"
    log_error "                repo already on the machine), or --legs f (no VM at all)."
}

# ensure_repo_present — legs b through e all operate on the licensed repository
# that leg a creates. Selecting them without leg a is legitimate (the repo may
# survive from an earlier run), but it must be CHECKED: without this the legs
# would run against nothing and report a pile of assertion failures that look
# like licensing defects and are really an empty machine.
ensure_repo_present() {
    leg_enabled a && return 0
    local guid
    guid=$(drill_repo_status "$VM_IP" repositoryGuid)
    if [[ -n "$guid" ]]; then
        drill_note "reusing the licensed repo already on $VM_IP ($guid)"
        return 0
    fi
    log_error "Legs b-e operate on a licensed repository, and $VM_IP has none."
    log_error "Leg a is what creates it, so there is nothing here to migrate, renew or meter."
    log_error "Run leg a in the same invocation:  ./run.sh drill license --legs a,$LEGS"
    exit 1
}

# preflight_vms — which cluster is actually up, and therefore which legs can run.
# `ops status` lists every CONFIGURED VM including absent ones, so the gate is on
# each entry's status field, never on the length of the array.
preflight_vms() {
    drill_step "Preflight: ops VM availability"
    local status
    if ! status=$("$RDC" ops status -o json 2>/dev/null); then
        log_error "Could not read ops status. Is renet built and libvirt reachable?"
        exit 1
    fi
    # `rdc ops status -o json` wraps the renet payload in the CLI envelope, so
    # the array is at d.data.vms; accept the bare shape too in case the drill is
    # ever pointed at `renet ops status --json` directly.
    local running
    running=$(drill_json \
        '(((d.data && d.data.vms) || d.vms || []).filter(v => v.status === "running").map(v => v.ip).join(" "))' \
        <<<"$status") || running=""
    drill_note "running VMs: ${running:-<none>}"

    if needs_vm && [[ " $running " != *" $VM_IP "* ]]; then
        log_error "Worker VM $VM_IP is not running, and legs a-e need it."
        log_error "Provision it first:  ./rdc.sh ops up --basic"
        log_error "Or run only the VM-less leg:  ./run.sh drill license --legs f"
        exit 1
    fi

    if leg_enabled b && [[ " $running " != *" $VM2_IP "* ]]; then
        log_error "Leg b (migration) needs a SECOND machine at $VM2_IP, which is not running."
        log_error "Provision the full cluster:  ./rdc.sh ops up"
        exit 1
    fi

    CEPH_AVAILABLE=0
    if [[ " $running " == *" ${VM_NET_BASE}.21 "* ]]; then
        CEPH_AVAILABLE=1
    fi
    if leg_enabled a && [[ $CEPH_AVAILABLE -eq 0 ]]; then
        log_error "Leg a (datastore fork re-meters) needs Ceph, and ${VM_NET_BASE}.21 is not running."
        log_error "A local-backend datastore fork is refused by design, so this leg cannot be faked."
        log_error "Provision the full cluster:  ./rdc.sh ops up"
        log_error "Or drop the leg:            ./run.sh drill license --legs b,c,d,e,f"
        exit 1
    fi
    drill_note "ceph available: $([[ $CEPH_AVAILABLE -eq 1 ]] && echo yes || echo no)"
}

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

# _ssh <host> <cmd...>
#
# -F /dev/null, IdentitiesOnly and IdentityAgent=none are load-bearing, not
# hygiene. Without them OpenSSH quietly tries the agent, ~/.ssh/config and its
# default identities after the -i key is refused, so this helper can CONNECT
# WITH A DIFFERENT KEY than the one the drill handed the CLI. That divergence
# is what made the first live run so confusing: `ssh` worked by hand while
# `rdc machine setup` failed, because they were not using the same key. Forcing
# exactly one identity keeps the drill's own SSH honest about what the CLI will
# experience.
_ssh() {
    local host="$1"
    shift
    ssh -F /dev/null -i "$SSH_KEY" -o IdentitiesOnly=yes -o IdentityAgent=none \
        -o StrictHostKeyChecking=no -o UserKnownHostsFile=/dev/null \
        -o ConnectTimeout=10 -o LogLevel=ERROR "$SSH_USER@$host" "$@"
}

setup_sandbox() {
    drill_step "Setup: isolated config directory"
    CONFIG_HOME="$DRILL_WORK/xdg"
    mkdir -p "$CONFIG_HOME/rediacc"
    export XDG_CONFIG_HOME="$CONFIG_HOME"
    export REDIACC_CONFIG="$CONFIG_NAME"
    # This drill is ABOUT enforcement, so the renet it deploys must be the
    # license-enforcing flavor with the dev account key baked in. The default
    # dev build is nolicense (a permit-all stub that would make every leg
    # vacuous); RDC_RENET_LICENSE=1 flips build.sh dev to enforcing, and
    # ensure_renet_built picks up ED25519_PUBLIC_KEY from private/account/.env
    # on its own. The build stamp hashes the effective mode, so this forces a
    # rebuild here and the next plain ./rdc.sh rebuilds nolicense right back —
    # nothing sticky is left behind for other sessions.
    export RDC_RENET_LICENSE=1
    # See the universe drill: unpinned, a drill measures the json surface while
    # describing the human one, because its stdout is never a TTY.
    export REDIACC_DEFAULT_OUTPUT=table
}

# setup_gateway_address — advertise the gateway at an address the MACHINES can
# reach, not just this workstation.
#
# Leg c is the whole reason. A license blob's renewalUrl is stamped from the Host
# header of the request that issued it, so issuing over 127.0.0.1 hands every
# machine a URL pointing at ITSELF: `renet license renew` on the VM then fails
# with `dial tcp 127.0.0.1:4808: connect: connection refused`, which reads like a
# renewal defect and is really the drill handing out an unreachable address.
#
# The workstation's own address on the VM network (the renet<N> bridge, e.g.
# 192.168.111.254) is reachable from BOTH sides, so it is the one address that
# keeps the drill self-consistent: the same value goes into the config's
# accountServer, into every curl this script makes, and into the blobs. That last
# part matters beyond leg c — the API token binds to the first host it is used
# with, so a run that mixed 127.0.0.1 and the bridge address would fail legs e
# and f with "Token is bound to a different IP address".
#
# Leg f alone needs no VM, so it keeps the loopback default: there is nothing to
# be reachable FROM, and a workstation with no renet bridge would otherwise fail
# a leg that does not depend on one.
setup_gateway_address() {
    needs_vm || return 0
    local host
    if ! host=$(drill_bridge_host "$VM_NET_BASE"); then
        log_error "No interface on the ${VM_NET_BASE}.0/24 VM network, so no address the"
        log_error "machines could reach this gateway at. The ops bridge (renet<N>) is created"
        log_error "by ./rdc.sh ops up; without it leg c cannot be honest about renewal."
        exit 1
    fi
    DRILL_HOST="$host"
    drill_note "gateway advertised at $DRILL_HOST (reachable from the VMs and from here)"
}

setup_gateway() {
    if [[ "$RESTART_GATEWAY" == "1" ]]; then
        drill_gateway_restart
    else
        drill_step "Reusing the running dev gateway (--no-restart)"
        if ! drill_gateway_alive; then
            log_error "No healthy dev gateway. Start one: ./run.sh account dev"
            exit 1
        fi
        DRILL_GATEWAY_PORT=$(drill_gateway_port)
    fi
    SERVER_URL="$(drill_server_url)"
    drill_note "account server: $SERVER_URL"
}

setup_account() {
    drill_step "Setup: dev subscription and API token"
    drill_account_ensure_login "$DRILL_EMAIL" "$DRILL_PASSWORD"
    drill_account_ensure_subscription "$DRILL_EMAIL" PROFESSIONAL "$START_MAX_ACTIVATIONS"

    local jar="$DRILL_WORK/cookies.txt"
    drill_account_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$jar"
    SUBSCRIPTION_ID=$(drill_account_subscription_id "$jar")
    API_TOKEN=$(drill_account_mint_token "$jar" "$SUBSCRIPTION_ID" drill-license \
        '["license:read","license:activate","subscription:read"]')
    drill_note "subscription $SUBSCRIPTION_ID"

    # A separate root+elevated session for the admin edits legs d and e need.
    ADMIN_JAR="$DRILL_WORK/admin-cookies.txt"
    drill_account_admin_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$ADMIN_JAR"
}

# The stamp mechanism can be defeated by a foreign `go build -o bin/renet`
# (it fingerprints inputs, and until 2026-08-04 said nothing about the
# artifact), and a wrong-flavored renet fails every leg with an error that
# reads like a licensing bug: an enforcing keyless build refuses everything
# with "public key not configured", a nolicense build permits everything.
# Prove the flavor BEFORE deploying it: the buildinfo of an enforcing build
# carries no `-tags=nolicense` and DOES carry the baked dev key in ldflags.
verify_renet_flavor() {
    drill_step "Setup: the local renet build enforces licenses with the dev key"
    local bin="$DRILL_ROOT_DIR/private/renet/bin/renet" info
    info="$(go version -m "$bin" 2>/dev/null || true)"
    if [[ -z "$info" ]]; then
        log_error "Cannot read build info from $bin (missing or not a Go binary)."
        exit 1
    fi
    if grep -q 'tags=nolicense' <<<"$info"; then
        log_error "The renet at $bin is a NOLICENSE build: every licensing"
        log_error "assertion would be vacuous. RDC_RENET_LICENSE=1 should have"
        log_error "forced an enforcing rebuild; check the build stamp logic."
        exit 1
    fi
    if ! grep -q 'ProductionPublicKey=' <<<"$info"; then
        log_error "The renet at $bin has NO account public key baked in: every"
        log_error "validation fails as 'public key not configured'. This is the"
        log_error "signature of a foreign 'go build' overwriting bin/renet."
        log_error "Rebuild: RDC_RENET_LICENSE=1 (cd private/renet && ./build.sh dev)"
        exit 1
    fi
    drill_note "enforcing build with baked key confirmed"
}

setup_config() {
    drill_step "Setup: config, machines and subscription login"
    drill_setup_run "$RDC" config init "$CONFIG_NAME" --server "$SERVER_URL"
    # config init above was the first CLI invocation, so the renet (re)build
    # has happened by now; prove its flavor before machine setup deploys it.
    verify_renet_flavor
    # Sync the target server's E2E public key before anything tunnels; without
    # this the first tunnelled call dies as "Decryption failed" (reported).
    drill_setup_run "$RDC" config current -o json
    drill_setup_run "$RDC" config ssh set --key "$SSH_KEY"
    drill_setup_run "$RDC" subscription login --token "$API_TOKEN" --server "$SERVER_URL"

    # NOTE, not a silent side effect: `rdc machine add` also writes an SSH alias
    # into the user's real home (on WSL, into the WINDOWS home), which no
    # sandbox here can contain. Reported; unavoidable for a drill that must
    # drive a registered machine.
    drill_setup_run "$RDC" machine add "$MACHINE_NAME" --ip "$VM_IP" --user "$SSH_USER"
    if leg_enabled b; then
        drill_setup_run "$RDC" machine add "$MACHINE2_NAME" --ip "$VM2_IP" --user "$SSH_USER"
    fi

    # Setup steps, not assertions. As assertions they produced a cascade: the
    # provisioning failure was reported once, and then the renet-on-PATH check
    # failed too with empty streams, which reads like a second, independent
    # defect and is really just the first one still being true. drill_setup_run
    # aborts on the FIRST failure with both streams printed.
    drill_setup_run "$RDC" machine setup "$MACHINE_NAME"
    drill_setup_run _ssh "$VM_IP" "command -v $VM_RENET"
    drill_note "renet provisioned on $VM_IP"
}

# -----------------------------------------------------------------------------
# Shared probes
# -----------------------------------------------------------------------------

# drill_repo_status <vm-ip> <field> — one field of the repo's licence status,
# read the way license-e2e.sh's assert_status reads it: the JSON array from
# `repository license-status`, first matching entry, stdout only.
drill_repo_status() {
    local host="$1" field="$2"
    _ssh "$host" "sudo $VM_RENET repository license-status --all-datastores --output json" \
        2>/dev/null | drill_json "(d.find(e => e.repositoryGuid) || {}).$field"
}

# meter_snapshot — the subscription-side counters, as one line, so a leg can
# assert on the DELTA rather than on an absolute nobody can predict.
meter_snapshot() {
    local jar="$DRILL_WORK/cookies.txt"
    curl -sS -b "$jar" "$(drill_api_base)/portal/subscription" |
        drill_json 'd.repoLicenseIssuances.effectiveUsed + ":" + d.activations'
}

license_status_json() {
    curl -sS -H "Authorization: Bearer $API_TOKEN" "$(drill_api_base)/licenses/status"
}

# drill_machine_id — a fresh 32-byte machine identity, the shape the licensing
# routes expect from a machine that has never been seen before.
drill_machine_id() {
    node -e 'process.stdout.write(require("crypto").randomBytes(32).toString("hex"))'
}

# activate_repo_for <machine-id> — issue a repo licence for a machine over raw
# HTTP and print the whole response. Used where a leg needs a SECOND machine on
# the subscription and there is no second renet to install a blob on.
activate_repo_for() {
    curl -sS -X POST "$(drill_api_base)/licenses/activate-repo" \
        -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
        -d "{\"machineId\":\"$1\",\"clientMachineId\":\"$1\",\"repositoryGuid\":\"$(uuidgen)\",\"kind\":\"grand\",\"requestedSizeGb\":1}"
}

# renew_blob_for <machine-id> <activate-response> — present an installed blob
# back to /licenses/renew as that machine would, and print the response. This is
# the credential-less renewal path leg c drives through renet, reached here over
# HTTP because the machine in question is a synthetic one.
renew_blob_for() {
    local machine_id="$1" activated="$2" body
    body=$(node -e '
      const d = JSON.parse(require("fs").readFileSync(0, "utf8"));
      process.stdout.write(JSON.stringify({ license: d.license, machineId: process.argv[1] }));
    ' "$machine_id" <<<"$activated")
    curl -sS -X POST "$(drill_api_base)/licenses/renew" \
        -H 'Content-Type: application/json' -d "$body"
}

# -----------------------------------------------------------------------------
# Leg a — a datastore fork re-meters
# -----------------------------------------------------------------------------
# The VM-less twin of this leg is license-e2e.sh S8a-S8e; the assertions below
# are the same five facts against a real Ceph datastore instead of fixtures.
# Machine-side pre-clean for leg a: the config sandbox is fresh each run but
# the VM keeps its datastores, and a datastore with a MOUNTED repo inside
# refuses to detach ("holders still present ... target is busy"). As a silent
# one-liner this left stale state that failed the NEXT run's create with
# "already exists", nine assertions deep in cascade. So: unmount every repo
# inside each drill datastore first, then detach (fork with --discard, fork
# before parent), then delete. The per-repo network_id comes from the repo's
# own .rediacc.json under <mount>/mounts/<guid>/ because `repository list
# --json` does not expose it while `repository unmount` requires it (reported).
# Best-effort throughout: a fresh VM makes every line a no-op.
# Runs on BOTH machines: leg b relocates the drill datastore to the second one,
# and a run that dies between the relocation and the move back leaves it there.
# Precleaning only the first machine then failed the NEXT run's `datastore create`
# with "already exists" — the image is in the shared RBD pool, so it is visible
# from either node no matter which one's registry knows about it.
leg_a_preclean() {
    local host
    local -a hosts=("$VM_IP")
    # Only when leg b is in play: the preflight proves VM2 is running for that leg
    # and for no other, and an unreachable host here would abort the drill under
    # `set -e` for a step that is pure hygiene.
    leg_enabled b && hosts+=("$VM2_IP")
    for host in "${hosts[@]}"; do
        leg_a_preclean_on "$host" || true
    done
    return 0
}

leg_a_preclean_on() {
    _ssh "$1" "bash -s" <<EOF
# The installed licence store is machine-local and SURVIVES every datastore this
# drill deletes, so a machine that has run this drill before holds a pile of blobs
# for repos and datastores that no longer exist, issued by subscriptions the dev
# server has since replaced. That is not cosmetic: leg c asserts that EVERY
# installed licence renews, and \`renet license renew\` has no filter — on the run
# that first exercised leg c it reported ten results, eight of them corpses. Legs
# c-e are only deterministic on a machine whose licences all belong to THIS run,
# and leg a reissues everything it needs immediately after.
sudo rm -rf /var/lib/rediacc/license/repos \\
    /var/lib/rediacc/license/datastores \\
    /var/lib/rediacc/license/failed \\
    /var/lib/rediacc/license/renew-state.json \\
    /var/lib/rediacc/license/chain-state.json 2>/dev/null
for ds in ${DATASTORE_NAME}:${FORK_TAG} ${DATASTORE_NAME}; do
    mount=\$(sudo ${VM_RENET} datastore list --json 2>/dev/null |
        python3 -c "import json,sys; print(next((d.get('mountPath','') for d in json.load(sys.stdin) if d.get('name')=='\$ds'),''))" 2>/dev/null)
    if [ -n "\$mount" ]; then
        for guid in \$(sudo ${VM_RENET} repository list --datastore "\$mount" --json 2>/dev/null |
            python3 -c "import json,sys; [print(r['name']) for r in json.load(sys.stdin)]" 2>/dev/null); do
            nid=\$(sudo python3 -c "import json; print(json.load(open('\$mount/mounts/\$guid/.rediacc.json')).get('network_id',0))" 2>/dev/null || echo 0)
            sudo ${VM_RENET} repository unmount --name "\$guid" --network-id "\$nid" --datastore "\$mount" --stop-docker --force >/dev/null 2>&1
        done
    fi
    if [ "\$ds" != "\${ds%:*}" ]; then
        sudo ${VM_RENET} datastore detach --name "\$ds" --discard >/dev/null 2>&1
    else
        sudo ${VM_RENET} datastore detach --name "\$ds" >/dev/null 2>&1
    fi
    sudo ${VM_RENET} datastore delete --name "\$ds" >/dev/null 2>&1
done
true
EOF
}

leg_a_fork_remeters() {
    drill_step "Leg a: forking a datastore re-meters the repo inside it"

    leg_a_preclean

    # The ops provisioner creates pool rediacc_rbd_pool, not the rbd default.
    drill_run "$RDC" datastore create "$DATASTORE_NAME" -m "$MACHINE_NAME" \
        --size 10G --backend rbd --pool rediacc_rbd_pool
    # The preflight catches the common case from bash, but it cannot evaluate
    # the CLI's ancestry check on an override that IS set. If the CLI refuses
    # here, report the precondition rather than a bare assertion failure.
    if grep -q 'blocked in agent mode' "$DRILL_STDERR"; then
        agent_override_blocked_message \
            "REDIACC_ALLOW_CLUSTER_OPS=*  (rejected by the CLI's ancestry check)"
        exit 1
    fi
    assert_exit 0 "a Ceph-backed datastore is created"

    # A newly created datastore is DETACHED by design; attach before use.
    drill_run "$RDC" datastore attach "$DATASTORE_NAME" --to "$MACHINE_NAME"
    assert_exit 0 "the datastore is attached to the machine"

    # Exactly ONE placement flag: --machine (docker, default datastore) XOR
    # --datastore (named datastore). Passing both is rejected, and the named
    # datastore already implies its machine.
    drill_run "$RDC" repo create "$REPO_NAME" --datastore "$DATASTORE_NAME" --size 1G --debug
    assert_exit 0 "a repo is created inside it (issuance happens here)"

    local parent_status parent_ds before after
    parent_status=$(drill_repo_status "$VM_IP" status)
    parent_ds=$(drill_repo_status "$VM_IP" datastoreId)
    DRILL_LAST_CMD="renet repository license-status --all-datastores (parent)"
    assert_equal valid "$parent_status" "the parent repo's licence is valid"
    assert_not_equal "" "$parent_ds" "and it is scoped to a real datastoreId"

    before=$(meter_snapshot)

    drill_run "$RDC" datastore fork "$DATASTORE_NAME" --tag "$FORK_TAG" \
        --attach-to "$MACHINE_NAME" --writes local
    assert_exit 0 "the datastore is forked"

    local fork_ds fork_mount fork_status
    fork_ds=$(_ssh "$VM_IP" "sudo $VM_RENET datastore list --json" 2>/dev/null |
        drill_json "(d.find(e => e.name === '${DATASTORE_NAME}:${FORK_TAG}') || {}).datastoreId")
    DRILL_LAST_CMD="renet datastore list --json"
    assert_not_equal "$parent_ds" "$fork_ds" \
        "the clone carries a NEWLY minted datastoreId (fork time is the stamp point)"

    # The fork's mount is NOT /mnt/rediacc-ds/<name>:<tag> — renet mounts a
    # fork at <parent>-<tag> (hyphen). Read the real path from the registry
    # rather than deriving it; a wrong path makes license-status answer []
    # and every status read after it an empty string.
    fork_mount=$(_ssh "$VM_IP" "sudo $VM_RENET datastore list --json" 2>/dev/null |
        drill_json "(d.find(e => e.name === '${DATASTORE_NAME}:${FORK_TAG}') || {}).mountPath")

    fork_status=$(_ssh "$VM_IP" \
        "sudo $VM_RENET repository license-status --datastore $fork_mount --output json" \
        2>/dev/null | drill_json '(d[0] || {}).status')
    DRILL_LAST_CMD="renet repository license-status (fork)"
    assert_equal missing "$fork_status" \
        "the repo inside the clone reads 'missing' under the new scope (S8b)"

    drill_run "$RDC" subscription refresh -m "$MACHINE_NAME"
    assert_exit 0 "a refresh reissues for the new scope"

    fork_status=$(_ssh "$VM_IP" \
        "sudo $VM_RENET repository license-status --datastore $fork_mount --output json" \
        2>/dev/null | drill_json '(d[0] || {}).status')
    DRILL_LAST_CMD="renet repository license-status (fork, after reissue)"
    assert_equal valid "$fork_status" "the fork's own licence is now valid (S8c)"

    assert_equal valid "$(drill_repo_status "$VM_IP" status)" \
        "and the PARENT's licence is still valid (S8d — the fork did not steal it)"

    after=$(meter_snapshot)
    assert_not_equal "$before" "$after" \
        "the reissue claimed a slot: the subscription's meter moved ($before -> $after)"
}

# -----------------------------------------------------------------------------
# Leg b — a plain migration does not re-meter
# -----------------------------------------------------------------------------
# WHAT "MIGRATION" MEANS HERE, corrected 2026-08-04 after the first live run.
#
# This leg used to drive `rdc repo migrate <repo> --to <machine2>`, and its
# assertion (the datastoreId survives) could not be true of that verb. A repo-level
# migrate is a backup_push of the repo IMAGE: the licence blobs stay behind on the
# source machine, the peer vault gives the target its DEFAULT datastore, and the
# repo therefore lands in a different scope by construction. Re-metering there is
# correct behaviour, not a defect.
#
# The claim 02-licensing-design.md §2 actually makes is about DATASTORE migration
# — "same datastore, new node: identity travels with the datastore" — and the verb
# for that is `datastore attach --to <other machine>`, which relocates in one step
# (it detaches the current holder first). The datastore descriptor
# (<mount>/.rediacc/datastore.json) rides inside the image, so its identity arrives
# on the new node unchanged and NOTHING re-mints. That is what is asserted below.
#
# The licence blob itself does NOT travel: the store is machine-local
# (/var/lib/rediacc/license/datastores/<id>/repos/...), so on the new node the repo
# reads `missing` until something reissues it. That is a MACHINE-level reissue, the
# same one this leg's predecessor already called "the expected, documented
# recovery", and it is deliberately not asserted here: the narrow claim is that the
# DATASTORE did not re-meter, and the meter equality below is what proves it.
#
# WHY THE ASSERTION IS EQUALITY OF THE ID, not "the licence still validates".
# Identity survives a ceph relocation by two independent routes — the record adopt
# copies DatastoreID verbatim (adopt.go:55-58) and, failing that, attach reads the
# descriptor that travels inside the image and treats it as authoritative
# (attach.go:143-145). But there is a third arm: a PRE-IDENTITY datastore, one whose
# descriptor carries no id at all, gets a FRESH id minted on its first read-write
# plain attach (attach.go:146-153). Every repo inside it then re-scopes, reads
# `missing`, and re-issues — a silent re-meter. `still validates` would sail through
# that, because a re-mint followed by a successful reissue also validates. Equality
# of the id is what tells the two apart. Current renet always mints at create
# (create.go:140), so drill-ds cannot be pre-identity; the assertion is shaped for
# the case the drill cannot produce, which is the only kind worth guarding.
#
# The relocation is undone at the end, both because legs c-e read the machine this
# drill set up and because leg a's next run precleans on that machine only.
leg_b_migration_does_not_remeter() {
    drill_step "Leg b: relocating the datastore keeps its identity"

    local before_ds before_meter after_ds after_meter

    # A datastore with a mounted repo inside refuses to detach ("holders still
    # present ... target is busy"), and the relocation detaches implicitly, so the
    # repo comes down first. This is setup for the claim, not part of it.
    drill_setup_run "$RDC" repo down "$REPO_NAME" --unmount

    before_ds=$(drill_repo_status "$VM_IP" datastoreId)
    before_meter=$(meter_snapshot)
    DRILL_LAST_CMD="renet repository license-status --all-datastores on $VM_IP"
    assert_not_equal "" "$before_ds" "the datastore has an identity to travel with"

    drill_run "$RDC" datastore attach "$DATASTORE_NAME" --to "$MACHINE2_NAME"
    assert_exit 0 "the datastore relocates to the second machine"

    after_ds=$(_ssh "$VM2_IP" \
        "sudo $VM_RENET repository license-status --all-datastores --output json" \
        2>/dev/null | drill_json '(d.find(e => e.repositoryGuid) || {}).datastoreId')
    DRILL_LAST_CMD="renet repository license-status --all-datastores on $VM2_IP"
    assert_equal "$before_ds" "$after_ds" \
        "the datastoreId travelled with the descriptor: no datastore re-mint"

    after_meter=$(meter_snapshot)
    DRILL_LAST_CMD="GET /portal/subscription (meter after the relocation)"
    assert_equal "$before_meter" "$after_meter" \
        "and the subscription's meter did not move ($before_meter): no re-metering"

    # Put it back where legs c-e (and the next run's leg a preclean) expect it.
    drill_run "$RDC" datastore attach "$DATASTORE_NAME" --to "$MACHINE_NAME"
    assert_exit 0 "the datastore relocates back to the first machine"

    # The DETACHED relocation, which is a different code path and was broken for
    # longer: with nothing holding the datastore there is no current holder to
    # ferry its registry row from, so the CLI has to remember who held it last.
    # Both halves are exercised here because only the pair proves it — recording
    # the holder is useless if the ferry does not read it, and the ferry cannot be
    # tested without a detach that recorded one.
    drill_run "$RDC" datastore detach "$DATASTORE_NAME"
    assert_exit 0 "the datastore detaches, holding no machine at all"

    drill_run "$RDC" datastore attach "$DATASTORE_NAME" --to "$MACHINE2_NAME"
    assert_exit 0 "a DETACHED datastore still attaches elsewhere (ferried from its last holder)"

    after_ds=$(_ssh "$VM2_IP" \
        "sudo $VM_RENET repository license-status --all-datastores --output json" \
        2>/dev/null | drill_json '(d.find(e => e.repositoryGuid) || {}).datastoreId')
    DRILL_LAST_CMD="renet repository license-status --all-datastores on $VM2_IP (after the detached move)"
    assert_equal "$before_ds" "$after_ds" \
        "and it arrives with the same identity: a detached move re-meters nothing either"

    drill_run "$RDC" datastore attach "$DATASTORE_NAME" --to "$MACHINE_NAME"
    assert_exit 0 "the datastore comes home again"
}

# -----------------------------------------------------------------------------
# Leg c — renewal from a machine that holds no credentials
# -----------------------------------------------------------------------------
leg_c_credentialless_renewal() {
    drill_step "Leg c: renewal driven only by the installed blob"

    # The blob is the credential AND the address book. If it carries no
    # renewalUrl, or the machine cannot reach the one it carries, renewal
    # cannot work — and that is a finding about the deployment, so it is
    # asserted rather than worked around.
    local renewal_url
    renewal_url=$(_ssh "$VM_IP" \
        "sudo find /var/lib/rediacc/license -name '*.json' -path '*/repos/*' | head -1 | xargs -r sudo cat" \
        2>/dev/null | drill_json 'JSON.parse(Buffer.from(d.payload, "base64").toString()).renewalUrl')
    DRILL_LAST_CMD="read renewalUrl out of the installed blob on $VM_IP"
    assert_not_equal "" "$renewal_url" "the installed blob carries a renewalUrl"

    drill_run _ssh "$VM_IP" "curl -sf -m 5 -o /dev/null '${renewal_url%/licenses/renew}/health' || curl -sf -m 5 -o /dev/null '$renewal_url'"
    assert_exit 0 "the machine can reach that URL (a localhost baseUrl would fail here)"

    drill_run _ssh "$VM_IP" "test ! -e /root/.config/rediacc && test ! -e ~/.config/rediacc"
    assert_exit 0 "the machine holds no rdc config and no account token"

    drill_run _ssh "$VM_IP" "sudo $VM_RENET license renew --force --output json"
    assert_exit 0 "renet license renew exits 0"
    assert_stdout_json 'd.results.some(r => r.outcome === "renewed")' true \
        "at least one licence was renewed"
    assert_stdout_json 'd.results.every(r => r.outcome !== "error")' true \
        "and nothing errored"

    local seq
    seq=$(drill_json 'Math.max(...d.results.map(r => r.newSequence || 0))' <"$DRILL_STDOUT")
    assert_not_equal 0 "$seq" "the renewed blob carries a fresh sequence ($seq)"
}

# -----------------------------------------------------------------------------
# Leg d — renewal refuses on a lapsed subscription
# -----------------------------------------------------------------------------
leg_d_refusal_on_lapse() {
    drill_step "Leg d: renewal refuses, by name, once the subscription has lapsed"

    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        '{"status":"suspended"}' >/dev/null
    SUBSCRIPTION_LAPSED=1
    drill_note "subscription suspended"

    drill_run _ssh "$VM_IP" "sudo $VM_RENET license renew --force --output json"
    assert_exit 0 "renew still exits 0 — one dead repo must not stop every other backup"
    assert_stdout_json 'd.results.some(r => r.outcome === "refused")' true \
        "the refusal is reported per repository"
    assert_stdout_json 'd.results.some(r => r.code === "SUBSCRIPTION_LAPSED")' true \
        "and carries the exact refusal code, not a generic failure"

    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        '{"status":"active"}' >/dev/null
    SUBSCRIPTION_LAPSED=0
    drill_note "subscription restored to active"
}

# -----------------------------------------------------------------------------
# Leg e — soft claim over the activation cap
# -----------------------------------------------------------------------------
leg_e_soft_claim_over_cap() {
    drill_step "Leg e: past the cap, renewal still succeeds and the overage is visible"

    # Start from a known cap rather than a hoped-for one, so "the cap moved" is
    # an assertion instead of an assumption.
    local status_json
    status_json=$(license_status_json)
    DRILL_LAST_CMD="GET /licenses/status (before lowering the cap)"
    assert_equal "$START_MAX_ACTIVATIONS" \
        "$(drill_json 'd.maxMachines' <<<"$status_json")" \
        "the subscription starts at the cap this drill seeded ($START_MAX_ACTIVATIONS)"

    # WHICH MACHINE GOES OVER, and why this leg needs a second one at all.
    #
    # The cap is on MACHINES, and over-limit is positional: an activation row is
    # over the cap when its INDEX among the subscription's rows, ordered by id,
    # reaches maxActivations (subscription.service.ts, touchActivationSoftClaim).
    # So the first machine to claim is never over the cap, no matter how far the
    # cap is lowered — a cap of 1 with one machine is AT the cap, not past it,
    # and the first live run of this leg asserted an overage that could not
    # happen. This machine claimed in leg a, so it is row #1 forever.
    #
    # A second machine is therefore part of the SETUP. It is activated over raw
    # HTTP rather than provisioned: the claim under test is about the metering,
    # not about renet, and a synthetic machineId reaches the same rows. It is
    # activated BEFORE the cap drops, because new issuance past the cap blocks
    # hard by design — only renewal soft-claims, which is the whole point below.
    local second_machine activated renewed
    second_machine=$(drill_machine_id)
    activated=$(activate_repo_for "$second_machine")
    DRILL_LAST_CMD="POST /licenses/activate-repo (a second machine, still under the cap)"
    assert_equal string "$(drill_json 'typeof d.license.payload' <<<"$activated")" \
        "a second machine claims a slot while the subscription is still under its cap"

    # Lowering the cap on a LIVE subscription is the only way to reach an
    # overage, and it is also the realistic one (a downgrade). Seeding a low cap
    # at creation cannot produce it either: issuance past the cap blocks. So this
    # stays on the admin route even though /test/ensure-subscription can now seed
    # a cap, which would delete this subscription and orphan its licences.
    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        '{"maxActivations":1}' >/dev/null
    SUBSCRIPTION_CAP_LOWERED=1
    drill_note "maxActivations lowered to 1, below the two machines already claiming"

    # The first machine is still within the cap, so its own results are not
    # flagged; what it proves is that a subscription in overage does not break
    # the renewals of the machines that are still inside it.
    drill_run _ssh "$VM_IP" "sudo $VM_RENET license renew --force --output json"
    assert_exit 0 "renew exits 0 while the subscription is over its cap"
    assert_stdout_json 'd.results.some(r => r.outcome === "renewed")' true \
        "renewal SUCCEEDS over the cap (soft claim: meter honestly, never block)"

    renewed=$(renew_blob_for "$second_machine" "$activated")
    printf '%s' "$renewed" >"$DRILL_STDOUT"
    : >"$DRILL_STDERR"
    DRILL_CODE=0
    DRILL_LAST_CMD="POST /licenses/renew (the machine that is past the cap)"
    assert_stdout_json 'typeof d.license.payload' string \
        "the over-cap machine's renewal is honoured, not refused"
    assert_stdout_json 'd.overLimit' true \
        "and the renewed result is flagged overLimit"

    status_json=$(license_status_json)
    DRILL_LAST_CMD="GET /licenses/status (after the overage)"
    assert_not_equal 0 "$(drill_json 'd.overLimitCount || 0' <<<"$status_json")" \
        "/licenses/status reports the overage (overLimitCount > 0)"

    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        "{\"maxActivations\":$START_MAX_ACTIVATIONS}" >/dev/null
    SUBSCRIPTION_CAP_LOWERED=0
}

# -----------------------------------------------------------------------------
# Leg f — the DTO boundary (no VM)
# -----------------------------------------------------------------------------
# The response airlock used to strip chainHash and delegationCert from every
# licence response, and every existing assertion about those fields ran at the
# SERVICE layer, where the airlock does not exist. So this leg reads the raw
# HTTP body, and ships a planted-strip control so that a pass cannot come from
# a check that is incapable of failing.
leg_f_dto_boundary() {
    drill_step "Leg f: chainHash and delegationCert survive the HTTP boundary"

    local machine_id body
    machine_id=$(node -e 'process.stdout.write(require("crypto").randomBytes(32).toString("hex"))')
    body=$(curl -sS -X POST "$(drill_api_base)/licenses/activate-repo" \
        -H "Authorization: Bearer $API_TOKEN" -H 'Content-Type: application/json' \
        -d "{\"machineId\":\"$machine_id\",\"clientMachineId\":\"$machine_id\",\"repositoryGuid\":\"$(uuidgen)\",\"kind\":\"grand\",\"requestedSizeGb\":1}")
    printf '%s' "$body" >"$DRILL_STDOUT"
    : >"$DRILL_STDERR"
    DRILL_CODE=0
    DRILL_LAST_CMD="POST /licenses/activate-repo (raw HTTP)"

    # The signed blob is nested under `license` in the activate-repo response.
    assert_stdout_json 'typeof d.license.payload' string "the response carries a payload"
    assert_stdout_json 'typeof d.license.signature' string "and a signature"
    assert_stdout_json 'typeof d.license.chainHash' string \
        "and chainHash SURVIVES the response airlock (this is the field it used to strip)"

    # Planted-strip control: the same assertion against a body with the field
    # removed must report it missing. Without this, "chainHash is a string"
    # could be passing because the check never looks.
    printf '%s' "$body" | node -e '
      const d = JSON.parse(require("fs").readFileSync(0, "utf8"));
      delete d.license.chainHash;
      delete d.license.delegationCert;
      process.stdout.write(JSON.stringify(d));
    ' >"$DRILL_WORK/stripped.json"
    local stripped_type
    stripped_type=$(drill_json 'typeof d.license.chainHash' <"$DRILL_WORK/stripped.json")
    DRILL_LAST_CMD="planted-strip control"
    assert_equal undefined "$stripped_type" \
        "planted-strip control: with chainHash removed the same check sees it gone"

    local cert_type
    cert_type=$(drill_json 'typeof d.license.delegationCert' <"$DRILL_STDOUT")
    if [[ "$cert_type" == "undefined" ]]; then
        drill_note "this account server is not a delegated (on-premise) deployment, so it"
        drill_note "attaches no delegationCert. The chainHash half of the boundary is proven"
        drill_note "above; to prove the delegationCert half, point the drill at a server"
        drill_note "started from src/entry/on-premise.ts with DELEGATION_CERT_PATH set."
        DRILL_LAST_CMD="POST /licenses/activate-repo (non-delegated server)"
        assert_equal undefined "$cert_type" \
            "non-delegated server: no delegationCert to strip (delegated half NOT covered)"
    else
        DRILL_LAST_CMD="POST /licenses/activate-repo (delegated server)"
        assert_equal string "$cert_type" \
            "delegationCert SURVIVES the response airlock on a delegated deployment"
    fi
}

main() {
    drill_parse_args "$@"
    drill_init license
    announce_cost
    drill_selftest_probe
    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        setup_sandbox
        drill_note "selftest mode: stopping before any VM or server work"
        drill_summary
        return
    fi

    # Preflight BEFORE the sandbox exports: preflight_vms runs `rdc ops status`,
    # a full CLI invocation, and the CLI auto-creates the config named by
    # REDIACC_CONFIG on startup. With the export in place first, that
    # auto-creation races the later `config init` and it dies with
    # "already exists" (found live 2026-08-04; the auto-created config even got
    # the PRODUCTION server's key synced into it, since the bare config has no
    # accountServer and the default is eu.rediacc.com).
    preflight_tools
    preflight_vms
    preflight_ssh
    preflight_agent_overrides
    setup_sandbox
    setup_gateway_address
    setup_gateway
    setup_account

    if needs_vm; then
        setup_config
        ensure_repo_present
    fi

    leg_enabled a && leg_a_fork_remeters
    leg_enabled b && leg_b_migration_does_not_remeter
    leg_enabled c && leg_c_credentialless_renewal
    leg_enabled d && leg_d_refusal_on_lapse
    leg_enabled e && leg_e_soft_claim_over_cap
    leg_enabled f && leg_f_dto_boundary

    drill_summary
}

main "$@"
