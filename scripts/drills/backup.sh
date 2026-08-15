#!/bin/bash
# drill backup — the live chunk-store battery.
#
#   ./run.sh drill backup [--legs a,b,c,d,e,f,g,h,j,k] [--selftest] [--no-restart]
#                         [--keep-work] [--vm <ip>] [--ssh-user <u>] [--ssh-key <p>]
#
# WHAT THIS DRILL IS FOR. The backup-storage program replaces rclone-shaped
# whole-image pushes with a content-addressed chunk store: a fixed cell grid
# over the LUKS image, SHA-256 of the ciphertext cell as both the object key
# and the dedup key, a manifest per snapshot, and a control plane that mints
# sessions, answers "which of these hashes do you already hold", mints
# delete-free write grants under a byte quota, and commits manifests. Every
# piece of that has unit tests on both sides. Until this drill, NOTHING had
# ever driven the whole path with real bytes over a real wire.
#
# COST. This drill needs NO virtual machines for its default legs. It runs
# against `./run.sh account dev` (which it restarts itself) and the RustFS the
# dev script already starts on :9100, and it uploads a few hundred kilobytes.
# The one machine-dependent leg (i) is opt-in and refuses itself by name when
# no machine is there.
#
# WHAT IT PROVES, one leg per claim:
#
#   a  SESSION MINT FROM A LICENSE BLOB. A machine holds no API token by
#      design, so the signed blob IS the credential. Ships with a tampered-blob
#      CONTROL, because "the good blob was accepted" proves nothing on its own.
#   b  SEED UPLOAD. exists-batch on a virgin lineage, a grant, real PUTs of
#      real cells into the store, a manifest object, a commit, and a ledger
#      that moved by exactly the bytes that moved.
#   c  INCREMENTAL UPLOAD. One cell changes; exactly one cell transfers, the
#      rest are answered as already-present (and that answer writes the 24h pin
#      that keeps GC off them).
#   d  POINT-IN-TIME RESTORE, BYTE-IDENTICAL. Both snapshots are reassembled
#      from the store and compared by SHA-256 against the sources — the OLD one
#      after the NEW one landed, which is the property a delta chain gets wrong.
#      Uses the technique e2e suite 17 uses for repository images.
#   e  QUOTA REFUSED AT MINT TIME, LIVE. Refusal BEFORE any I/O is spent, with
#      the retry hint attached, plus the control that raising the quota lets the
#      same request through (so the refusal was the quota, not a bad request).
#   f  THE CLI READ SURFACES. `rdc backup usage` and `rdc backup manifests`
#      against the same live server, including stream placement (a human line
#      on stdout corrupts `-o json` consumers).
#   g  THE PRUNE JSON CONTRACT, DRIVEN. Wave 0 wired four new prune rows into
#      the CLI parser against the Go STRUCT TAGS; no test had ever run a real
#      `renet ... prune --output json` and parsed its real output. This leg
#      does exactly that, with an over-eager control (a live anchor must NOT be
#      reported).
#   h  MACHINE WIRE CONFORMANCE. The shapes renet's session client actually
#      sends (pkg/chunkstore/session.go), presented to the live server. This leg
#      is the integration nobody had exercised: both sides were tested against
#      their own fakes, and its first run found five divergences at once. It
#      ships with a planted control (the pre-fix grant body must still be
#      refused) so an acceptance cannot come from an endpoint that takes
#      anything.
#   i  OPT-IN, NEEDS A MACHINE: `rdc backup verify` on a real repo.
#
# WHAT THIS DRILL DOES NOT PROVE, said plainly rather than implied:
#
#   * This drill does not RUN the verb. `renet backup snapshot` now exists
#     (cmd/renet/backup_snapshot.go) and calls chunkstore.Upload, so the older
#     claim here that no verb drives the engine is retired. What is still true
#     is narrower and worth keeping: driving it end to end needs a machine with
#     a real btrfs/LUKS repo and a licence, which this host-only drill does not
#     have. So legs b-d exercise the STORE and the CONTROL PLANE with cells this
#     drill produces and hashes
#     this drill computes; the FIEMAP/reflink/anchor half is proven by renet's
#     btrfs tier (TestIntegration_PipelineIncrementalMatchesFullRehash), not
#     here. Leg h measures the gap between the two halves.
#     Restore no longer belongs on this list: leg d reads THROUGH A READ GRANT
#     (POST /backups/read-grants on a restore-intent session), the way a machine
#     does, and leg j is its control — a backup-intent session is refused a read
#     grant and a restore-intent session is refused a write one, by name. Leg k
#     exercises the 60-day retain-on-cancel promise end to end. What is still
#     unproven here is the same as above: no MACHINE runs the restore in this
#     host-only drill, so `renet backup restore` itself is covered by e2e suite
#     26's RESTORE tier, not by leg d.
#
# THE OFFLINE CONTROL. `private/account/tests/integration/backup-lifecycle.test.ts`
# is this drill's VM-less twin (the license.sh precedent): the same lifecycle
# against the in-memory store, seconds instead of minutes. If a leg fails here
# and its twin passes there, the difference is the environment, not the logic.
#
# SELFTEST. `--selftest` plants one assertion that cannot pass and stops before
# any server or store work, so proving the instrument is free.

set -euo pipefail

DRILL_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../../.ci/scripts/lib/common.sh
source "$DRILL_DIR/../../.ci/scripts/lib/common.sh"
# shellcheck source=lib.sh
source "$DRILL_DIR/lib.sh"

RESTART_GATEWAY=1
LEGS="a,b,c,d,e,f,g,h,j,k"
VM_NET_BASE="${VM_NET_BASE:-192.168.111}"
VM_IP="${VM_NET_BASE}.11"
SSH_USER="${SSH_USER:-$USER}"
SSH_KEY="${SSH_KEY:-${RENET_DATA_DIR:-$HOME/.renet}/staging/.ssh/id_rsa}"

DRILL_EMAIL="drill-backup-$(date +%s)@rediacc.io"
DRILL_PASSWORD="DrillBackup123!"
CONFIG_NAME="drill-backup"
RDC="$DRILL_ROOT_DIR/rdc.sh"
RENET_BIN="${DRILL_RENET_BIN:-$DRILL_ROOT_DIR/private/renet/bin/renet}"

# The chunk store: the SAME RustFS `./run.sh account dev` starts for config
# blobs, on its canonical port, with a second bucket. Credentials match
# .ci/lib/account.sh's defaults; the drill never invents its own instance.
RUSTFS_PORT="${RUSTFS_PORT:-9100}"
RUSTFS_KEY="${CONFIG_R2_ACCESS_KEY_ID:-configadmin}"
RUSTFS_SECRET="${CONFIG_R2_SECRET_ACCESS_KEY:-configadmin}"
BACKUP_BUCKET="${BACKUP_BUCKET_NAME:-rediacc-backups}"
S3_REGION="us-east-1"

# TIER-B OPT-IN: point the whole drill at a REAL S3/R2 bucket instead of the
# local RustFS. Set DRILL_STORE_ENDPOINT plus its key/secret/bucket and every
# leg — seed writes, grants, the read-grant restore, byte-identity — runs
# against real object-store semantics.
#
# Why it matters: the testing-surface audit ranked "no delete path has ever run
# against a real store" the highest-consequence gap in the program, and the
# first real-store probe immediately found a latent data-loss defect that no
# in-memory or local fake had ever surfaced. A drill that only ever sees RustFS
# is one S3-semantics difference away from the same blind spot.
#
# UNSET BY DEFAULT, deliberately: CI runs this drill on every push and must stay
# hermetic and free. The default path below is unchanged.
DRILL_STORE_ENDPOINT="${DRILL_STORE_ENDPOINT:-}"
DRILL_STORE_BUCKET="${DRILL_STORE_BUCKET:-}"
DRILL_STORE_KEY="${DRILL_STORE_KEY:-}"
DRILL_STORE_SECRET="${DRILL_STORE_SECRET:-}"
DRILL_STORE_REGION="${DRILL_STORE_REGION:-auto}"

# A real-store run DELETES objects under its own tenant prefix, so it refuses
# any bucket not marked disposable — the same guard the delete probe carries,
# and for the same reason: a drill that can point at production will, once.
using_real_store() { [[ -n "$DRILL_STORE_ENDPOINT" ]]; }
assert_disposable_store() {
    using_real_store || return 0
    if [[ "$DRILL_STORE_BUCKET" == "rediacc-backups" ]]; then
        log_error "refusing the bare production bucket name 'rediacc-backups': this drill writes and deletes."
        exit 1
    fi
    if [[ ! "$DRILL_STORE_BUCKET" =~ (probe|test|scratch|bench) ]]; then
        log_error "refusing bucket '$DRILL_STORE_BUCKET': the name does not mark it disposable."
        log_error "Use a bucket named *probe*/*test*/*scratch*/*bench*."
        exit 1
    fi
}

# The fixture image: 8 cells, two of them holes. Small enough to keep the drill
# fast, big enough that "only the changed cell moved" is a real measurement.
CELL_BYTES=65536
SNAP_SEED="snap-seed-$(date +%s)"
SNAP_INCR="snap-incr-$(date +%s)"

API_TOKEN=""
SUBSCRIPTION_ID=""
ADMIN_JAR=""
SESSION_TOKEN=""
SESSION_BASE_URL=""
SESSION_MINT_URL=""
STREAM_ID=""
LINEAGE=""
SEED_STORED_BYTES=0
QUOTA_LOWERED=0
# Declared HERE, beside QUOTA_LOWERED, and not next to the leg that sets it:
# drill_teardown_hook reads it, and under `set -u` an early failure would make
# the teardown itself die on an unbound variable while cleaning up.
LAPSED_SUBSCRIPTION=0
IMAGE_HELPER=""

drill_teardown_hook() {
    # The quota edit outlives the work directory: a subscription left pinned at
    # a low quota would fail the NEXT run at leg b for a reason that has nothing
    # to do with what it tests. Everything else this drill created (a dev
    # subscription, objects under its own tenant prefix) is inert.
    if [[ -n "$ADMIN_JAR" && -n "$SUBSCRIPTION_ID" && "$QUOTA_LOWERED" == "1" ]]; then
        drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
            '{"storageQuotaBytes":null}' >/dev/null 2>&1 || true
    fi
    # Leg k suspends the subscription on purpose. Same reasoning as the quota:
    # left suspended, the NEXT run fails at leg a issuing a repo license, and
    # nothing in that failure points back here.
    if [[ -n "$ADMIN_JAR" && -n "$SUBSCRIPTION_ID" && "$LAPSED_SUBSCRIPTION" == "1" ]]; then
        drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
            '{"status":"active"}' >/dev/null 2>&1 || true
    fi
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
                echo "Usage: ./run.sh drill backup [--legs a,b,c,d,e,f,g,h,i,j,k] [--selftest]" \
                    "[--no-restart] [--keep-work] [--vm <ip>] [--ssh-user <u>] [--ssh-key <p>]" >&2
                exit 2
                ;;
        esac
        i=$((i + 1))
    done
}

leg_enabled() {
    [[ ",$LEGS," == *",$1,"* ]]
}

# KNOWN_LEGS is the whole registry, and validate_legs refuses anything outside
# it. Without this a typo is SILENT: `--legs a,b,c,d,e,f,g,h,jj` drops leg jj,
# runs everything else, and prints PASSED for a narrower battery than the
# operator asked for. The harness protects against the empty case (zero
# assertions reports SKIPPED, never PASSED — see check-drill-verdicts.sh), but
# nothing protected against a partially-mistyped list.
KNOWN_LEGS="a b c d e f g h i j k"
validate_legs() {
    local leg known ok
    for leg in ${LEGS//,/ }; do
        ok=0
        for known in $KNOWN_LEGS; do
            [[ "$leg" == "$known" ]] && ok=1 && break
        done
        if [[ $ok -eq 0 ]]; then
            log_error "Unknown leg '${leg}' in --legs ${LEGS}"
            log_error "Known legs: ${KNOWN_LEGS// /, }"
            exit 1
        fi
    done
    [[ -n "${LEGS//,/}" ]] || {
        log_error "--legs was given an empty list; nothing would run."
        exit 1
    }
}

# needs_plane — true when any selected leg talks to the control plane, which
# needs BOTH the dev gateway and a reachable chunk store. Legs g (a local
# binary and a fixture directory) and i (a machine) do not.
needs_plane() {
    # j and k belong here for the same reason a-f do: j mints a restore-intent
    # session and asks for both grant kinds, and k suspends the subscription
    # and restores through a read grant. Omitting them meant `--legs j,k` never
    # started the gateway or the store, and the legs then failed on a plane
    # that was never brought up — a self-inflicted red blaming the wrong thing.
    leg_enabled a || leg_enabled b || leg_enabled c || leg_enabled d ||
        leg_enabled e || leg_enabled f || leg_enabled h ||
        leg_enabled j || leg_enabled k
}

# needs_upload — the legs that move real bytes and therefore depend on every
# earlier leg's state. Selecting c without b is legitimate only if b ran in the
# same invocation; there is no state on disk to inherit.
needs_upload() {
    leg_enabled b || leg_enabled c || leg_enabled d || leg_enabled e || leg_enabled f
}

# -----------------------------------------------------------------------------
# Cost declaration and preflight
# -----------------------------------------------------------------------------

announce_cost() {
    cat <<EOF

  This drill runs against ./run.sh account dev and the RustFS it starts on
  :${RUSTFS_PORT}. It provisions NOTHING and needs NO virtual machines.

    legs a,b,c,d,e,f,h,j,k  the dev gateway (restarted by this drill) + Docker for
                        the RustFS chunk store. A few hundred KB uploaded into
                        bucket ${BACKUP_BUCKET}, under this run's own tenant prefix.
    leg  g              the LOCAL renet binary and a throwaway datastore
                        directory in the work dir. No server, no store.
    leg  i              OPT-IN, needs a machine with a repo (./rdc.sh ops up --basic
                        plus a licensed repo). Not selected by default.

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
    require_tool curl "curl" || ok=1
    require_tool node "Node.js — every wrapper in this repo needs it" || ok=1
    if needs_plane; then
        # The drill signs its own S3 requests for the parts of the store the
        # product has no grant for — the seed PUTs and the bucket create. Leg d
        # no longer needs this (it reads through presigned GET urls), but legs
        # a-c and e still sign their own writes.
        if ! curl --help all 2>/dev/null | grep -q -- '--aws-sigv4'; then
            log_error "This curl has no --aws-sigv4 (needs 7.75+); legs a-f cannot sign store requests."
            ok=1
        fi
        if ! docker info >/dev/null 2>&1; then
            log_error "Docker is not available, so ./run.sh account dev cannot start RustFS."
            log_error "Legs a,b,c,d,e,f,h,j,k all need the chunk store; only leg g can run here:"
            log_error "    ./run.sh drill backup --legs g"
            ok=1
        fi
    fi
    if leg_enabled g && [[ ! -x "$RENET_BIN" ]]; then
        log_error "Leg g needs the renet binary at $RENET_BIN, which is missing."
        log_error "Build it:  (cd private/renet && ./build.sh dev)   — or run any ./rdc.sh command."
        log_error "Or drop the leg:  ./run.sh drill backup --legs a,b,c,d,e,f,h,j,k"
        ok=1
    fi
    if leg_enabled i && [[ ! -f "$SSH_KEY" ]]; then
        log_error "Leg i (machine) needs an SSH key at $SSH_KEY (override with --ssh-key)."
        ok=1
    fi
    [[ $ok -eq 0 ]] || exit 1
    drill_note "curl $(curl --version | head -1 | cut -d' ' -f2), node $(node --version)"
}

# preflight_machines — leg i is the only machine-dependent leg, and it refuses
# itself BY NAME rather than failing nine assertions deep on an empty box.
preflight_machines() {
    leg_enabled i || return 0
    drill_step "Preflight: machine availability (leg i)"
    local status running
    if ! status=$("$RDC" ops status -o json 2>/dev/null); then
        log_error "Could not read ops status, and leg i needs a machine."
        log_error "Provision one:  ./rdc.sh ops up --basic     Or drop the leg."
        exit 1
    fi
    running=$(drill_json \
        '(((d.data && d.data.vms) || d.vms || []).filter(v => v.status === "running").map(v => v.ip).join(" "))' \
        <<<"$status") || running=""
    drill_note "running VMs: ${running:-<none>}"
    if [[ " $running " != *" $VM_IP "* ]]; then
        log_error "Leg i needs the worker VM $VM_IP, which is not running."
        log_error "Provision it:  ./rdc.sh ops up --basic"
        log_error "Or run the machine-less legs:  ./run.sh drill backup --legs a,b,c,d,e,f,g,h,j,k"
        exit 1
    fi
}

# announce_unrunnable — the legs this campaign WANTS and this build cannot
# host, named individually. A drill that silently omits them reads as coverage.
announce_unrunnable() {
    drill_step "Not covered by this run, and why (read this before trusting a green)"
    drill_note "renet-driven backup: the verb EXISTS (renet backup snapshot), but this"
    drill_note "  host-only drill does not run it: that needs a machine with a real"
    drill_note "  btrfs/LUKS repo and a licence. Legs b-d therefore produce their own cells;"
    drill_note "  the FIEMAP/anchor half is covered by renet's btrfs tier, not by this drill."
    drill_note "machine-side restore: legs d/j/k now read through a READ GRANT, as a machine"
    drill_note "  does, but no machine RUNS renet backup restore here; that is e2e suite 26."
    drill_note "cross-machine restore: byte-identity across two machines is suite 26's"
    drill_note "  RESTORE tier, which needs a two-worker fleet this host-only drill has not."
}

# -----------------------------------------------------------------------------
# Setup
# -----------------------------------------------------------------------------

setup_sandbox() {
    drill_step "Setup: isolated config directory"
    local config_home="$DRILL_WORK/xdg"
    mkdir -p "$config_home/rediacc"
    export XDG_CONFIG_HOME="$config_home"
    export REDIACC_CONFIG="$CONFIG_NAME"
    # See the universe drill: unpinned, a drill measures the json surface while
    # describing the human one, because its stdout is never a TTY.
    export REDIACC_DEFAULT_OUTPUT=table
}

# setup_store_env — point the dev gateway at a chunk store BEFORE it starts.
#
# `./run.sh account dev` exports CONFIG_R2_* for the config blob store and
# NOTHING for the backup plane, so a stock dev gateway has `createBackupPlane`
# return null and every backup route answers 503 BACKUP_NOT_CONFIGURED. That is
# a real gap (reported), and it is also why these exports must happen before
# drill_gateway_restart: the gateway inherits this environment, and tsx does not
# re-read it later.
#
# ONE host value for the whole run (the drill_bridge_host lesson): the account
# server presigns store URLs against BACKUP_S3_ENDPOINT and stamps its own
# addresses from the request Host header, and an API token binds to the first
# host it is used with. Mixing 127.0.0.1 and the bridge address inside one run
# is what produced "Token is bound to a different IP address" in the licensing
# drill.
setup_store_env() {
    needs_plane || return 0
    drill_step "Setup: chunk-store environment for the dev gateway"
    local host
    if host=$(drill_bridge_host "$VM_NET_BASE"); then
        DRILL_HOST="$host"
        drill_note "using the VM-network address $DRILL_HOST (reachable from machines too)"
    else
        drill_note "no ${VM_NET_BASE}.0/24 interface; using $DRILL_HOST for every URL in this run"
    fi
    if using_real_store; then
        BACKUP_BUCKET="$DRILL_STORE_BUCKET"
        export BACKUP_S3_ENDPOINT="${DRILL_STORE_ENDPOINT%/}"
        export BACKUP_S3_BUCKET="$DRILL_STORE_BUCKET"
        export BACKUP_S3_ACCESS_KEY_ID="$DRILL_STORE_KEY"
        export BACKUP_S3_SECRET_ACCESS_KEY="$DRILL_STORE_SECRET"
        drill_note "TIER-B: real object store, bucket $DRILL_STORE_BUCKET"
    else
        export BACKUP_S3_ENDPOINT="http://${DRILL_HOST}:${RUSTFS_PORT}"
        export BACKUP_S3_BUCKET="$BACKUP_BUCKET"
        export BACKUP_S3_ACCESS_KEY_ID="$RUSTFS_KEY"
        export BACKUP_S3_SECRET_ACCESS_KEY="$RUSTFS_SECRET"
    fi
    # The maintenance timer would run GC underneath the drill's own objects.
    export BACKUP_MAINTENANCE_INTERVAL_MS=0
    drill_note "chunk store: $BACKUP_S3_ENDPOINT/$BACKUP_S3_BUCKET"
}

setup_gateway() {
    needs_plane || return 0
    if [[ "$RESTART_GATEWAY" == "1" ]]; then
        drill_gateway_restart
    else
        drill_step "Reusing the running dev gateway (--no-restart)"
        if ! drill_gateway_alive; then
            log_error "No healthy dev gateway. Start one: ./run.sh account dev"
            exit 1
        fi
        drill_note "NOTE: a gateway this drill did not start may have no backup plane"
        drill_note "configured, in which case every backup route answers 503."
        DRILL_GATEWAY_PORT=$(drill_gateway_port)
    fi
    drill_note "account server: $(drill_server_url)"
}

s3_curl() {
    if using_real_store; then
        curl -sS --aws-sigv4 "aws:amz:${DRILL_STORE_REGION}:s3" \
            -u "${DRILL_STORE_KEY}:${DRILL_STORE_SECRET}" "$@"
        return
    fi
    curl -sS --aws-sigv4 "aws:amz:${S3_REGION}:s3" -u "${RUSTFS_KEY}:${RUSTFS_SECRET}" "$@"
}

store_url() {
    if using_real_store; then
        printf '%s' "${DRILL_STORE_ENDPOINT%/}"
        return
    fi
    printf 'http://%s:%s' "$DRILL_HOST" "$RUSTFS_PORT"
}

setup_store_bucket() {
    needs_plane || return 0
    drill_step "Setup: the chunk-store bucket"
    local waited=0
    while [[ $waited -lt 60 ]]; do
        # RustFS answers 403 to an unsigned root GET, which is a healthy store:
        # any answer at all proves the port is serving.
        if curl -sS -o /dev/null -m 2 "$(store_url)/" 2>/dev/null; then
            break
        fi
        sleep 2
        waited=$((waited + 2))
    done
    if ! curl -sS -o /dev/null -m 2 "$(store_url)/" 2>/dev/null; then
        log_error "No S3 store answering on $(store_url) after ${waited}s."
        log_error "./run.sh account dev starts RustFS there when Docker is available, and it"
        log_error "FAILS OPEN: the gateway comes up healthy with no config store and no backup"
        log_error "plane, so this check is the only thing that notices. Look in"
        log_error ".account-logs/rustfs.log first."
        log_error ""
        log_error "The failure seen on 2026-08-14 was the ghost-container state account.sh"
        log_error "documents: compose insists on recreating a container id the daemon does not"
        log_error "have (\"No such container: <id>\"), and account_docker_ghost_clean does not"
        log_error "clear it. The documented way out, which this drill then reuses:"
        log_error "    docker rm -f <the ghost container>"
        log_error "    docker run -d --name rediacc-config-rustfs-dev -p ${RUSTFS_PORT}:9000 \\"
        log_error "      -e RUSTFS_VOLUMES=/data -e RUSTFS_ADDRESS=0.0.0.0:9000 \\"
        log_error "      -e RUSTFS_ACCESS_KEY=${RUSTFS_KEY} -e RUSTFS_SECRET_KEY=${RUSTFS_SECRET} \\"
        log_error "      rustfs/rustfs:latest"
        exit 1
    fi
    # Create-bucket is idempotent here: this RustFS answers 200 to a re-create
    # rather than 409 (noted in the elite compose comments), so nothing keys on
    # the status.
    s3_curl -X PUT -o /dev/null "$(store_url)/${BACKUP_BUCKET}" || true
    drill_note "bucket ready: $(store_url)/${BACKUP_BUCKET}"
}

setup_account() {
    needs_plane || return 0
    drill_step "Setup: dev subscription and API token"
    drill_account_ensure_login "$DRILL_EMAIL" "$DRILL_PASSWORD"
    drill_account_ensure_subscription "$DRILL_EMAIL" PROFESSIONAL

    local jar="$DRILL_WORK/cookies.txt"
    drill_account_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$jar"
    SUBSCRIPTION_ID=$(drill_account_subscription_id "$jar")
    API_TOKEN=$(drill_account_mint_token "$jar" "$SUBSCRIPTION_ID" drill-backup \
        '["license:read","license:activate","subscription:read","backup:read"]')
    drill_note "subscription $SUBSCRIPTION_ID"

    # Leg e lowers the storage quota, which is an admin-route edit.
    ADMIN_JAR="$DRILL_WORK/admin-cookies.txt"
    drill_account_admin_session "$DRILL_EMAIL" "$DRILL_PASSWORD" "$ADMIN_JAR"
}

# The fixture generator and every assertion share ONE hasher and ONE grid, the
# mint-tool principle: a second hand-written implementation lets a battery agree
# with itself while disagreeing with the product.
setup_image_helper() {
    needs_upload || return 0
    IMAGE_HELPER="$DRILL_WORK/image.js"
    cat >"$IMAGE_HELPER" <<'IMAGE_JS'
// Fixture image + cell arithmetic for drill backup.
//   make <path> <version>     write an image (version 2 rewrites cell 3)
//   plan <path>               {cellBytes, imageBytes, cells:[hash|""], unique:[]}
//   slice <path> <index> <to> write one cell to its own file (the PUT body)
//   assemble <cells.json> <chunkdir> <to>   rebuild an image from cell hashes
//   sha <path>                sha256 of a file
const fs = require('fs');
const crypto = require('crypto');
const CELL = Number(process.env.DRILL_CELL_BYTES || 65536);
const CELLS = 8;
// Cell 2 and cell 6 are holes: all-zero, elided from the manifest as "" the
// way FIEMAP-driven ZERO detection elides an unwritten extent.
const HOLES = new Set([2, 6]);

const sha = (buf) => crypto.createHash('sha256').update(buf).digest('hex');

function make(path, version) {
  const image = Buffer.alloc(CELLS * CELL);
  for (let c = 0; c < CELLS; c++) {
    if (HOLES.has(c)) continue;
    const seed = c === 3 && version === '2' ? 99 : c + 1;
    for (let i = 0; i < CELL; i++) image[c * CELL + i] = (seed * 31 + i * 7) % 251;
  }
  fs.writeFileSync(path, image);
}

function cellsOf(path) {
  const image = fs.readFileSync(path);
  const cells = [];
  for (let c = 0; c < image.length / CELL; c++) {
    const slice = image.subarray(c * CELL, (c + 1) * CELL);
    cells.push(HOLES.has(c) ? '' : sha(slice));
  }
  return { image, cells };
}

const [cmd, ...args] = process.argv.slice(2);
if (cmd === 'make') {
  make(args[0], args[1]);
} else if (cmd === 'plan') {
  const { image, cells } = cellsOf(args[0]);
  const unique = [...new Set(cells.filter((c) => c !== ''))];
  process.stdout.write(
    JSON.stringify({ cellBytes: CELL, imageBytes: image.length, cells, unique })
  );
} else if (cmd === 'slice') {
  const image = fs.readFileSync(args[0]);
  const index = Number(args[1]);
  fs.writeFileSync(args[2], image.subarray(index * CELL, (index + 1) * CELL));
} else if (cmd === 'assemble') {
  // cells.json is the materialized inventory: one entry per cell, "" = hole.
  const cells = JSON.parse(fs.readFileSync(args[0], 'utf8'));
  const out = Buffer.alloc(cells.length * CELL);
  cells.forEach((hash, index) => {
    if (hash === '') return; // a hole stays a hole
    const chunk = fs.readFileSync(`${args[1]}/${hash}`);
    if (chunk.length !== CELL) throw new Error(`cell ${index}: ${chunk.length} bytes, want ${CELL}`);
    chunk.copy(out, index * CELL);
  });
  fs.writeFileSync(args[2], out);
} else if (cmd === 'sha') {
  process.stdout.write(sha(fs.readFileSync(args[0])));
} else {
  process.stderr.write(`unknown command: ${cmd}\n`);
  process.exit(2);
}
IMAGE_JS
    export DRILL_CELL_BYTES="$CELL_BYTES"
}

image_js() {
    node "$IMAGE_HELPER" "$@"
}

# run_tsx <script> [args...] — tsx resolved from the CLI package, which is
# where its devDependency and tsconfig live. A subshell cd, because the drill's
# own working directory must not move under the commands that follow.
run_tsx() {
    (cd "$DRILL_ROOT_DIR/packages/cli" && npx tsx "$@")
}

# -----------------------------------------------------------------------------
# HTTP helpers
# -----------------------------------------------------------------------------

# api <method> <url> <json-body-or-empty-string> [extra curl args...]
# Prints the response body and records the HTTP status where api_status can
# read it. A transport failure is a non-zero return, an HTTP error is not: the
# account server puts its reason in the body, and the assertions read it there.
# The body argument is mandatory (pass "" for none) so the shift below cannot
# eat a curl argument.
#
# THE STATUS GOES TO A FILE, not to a variable. Every caller runs this in a
# command substitution to capture the body, which is a SUBSHELL: a global
# assigned here would be discarded on return, and every status assertion would
# then compare against an empty string. That is exactly what the first live run
# did — six assertions failed while their JSON siblings passed, which is the
# signature of a harness bug rather than a product one.
api() {
    local method="$1" url="$2" body="$3"
    shift 3
    local out="$DRILL_WORK/api-body.json"
    local -a args=(-sS -o "$out" -w '%{http_code}' -X "$method" "$url")
    if [[ -n "$body" ]]; then
        args+=(-H 'Content-Type: application/json' -d "$body")
    fi
    curl "${args[@]}" "$@" >"$DRILL_WORK/api-status"
    cat "$out"
}

# api_status — the HTTP status of the last api call.
api_status() {
    cat "$DRILL_WORK/api-status" 2>/dev/null || printf 'none'
}

backup_api() {
    printf '%s/backups' "$(drill_api_base)"
}

# session_api <method> <path> [json-body] — a call carrying the storage session.
session_api() {
    local method="$1" path="$2" body="${3:-}"
    api "$method" "$(backup_api)$path" "$body" -H "X-Backup-Session: $SESSION_TOKEN"
}

# capture <description> <body> — stage a captured HTTP body as if drill_run had
# produced it, so the JSON assertions and the failure dump work unchanged.
capture() {
    DRILL_LAST_CMD="$1"
    printf '%s' "$2" >"$DRILL_STDOUT"
    : >"$DRILL_STDERR"
    DRILL_CODE=0
}

# -----------------------------------------------------------------------------
# Leg a — session mint from a license blob
# -----------------------------------------------------------------------------

leg_a_session_mint() {
    drill_step "Leg a: the license blob is the credential"

    local machine_id blob_response
    machine_id=$(node -e 'process.stdout.write(require("crypto").randomBytes(32).toString("hex"))')
    LINEAGE=$(uuidgen)
    blob_response=$(api POST "$(drill_api_base)/licenses/activate-repo" \
        "{\"machineId\":\"$machine_id\",\"clientMachineId\":\"$machine_id\",\"repositoryGuid\":\"$LINEAGE\",\"kind\":\"grand\",\"requestedSizeGb\":1}" \
        -H "Authorization: Bearer $API_TOKEN")
    capture "POST /licenses/activate-repo" "$blob_response"
    assert_equal 200 "$(api_status)" "a repo license is issued for a fresh machine"
    assert_stdout_json 'typeof d.license.payload' string "the blob carries a signed payload"

    local blob session
    blob=$(drill_json 'JSON.stringify(d.license)' <<<"$blob_response")
    # Retained for the restore-intent session legs d, j and k mint later: the
    # blob is both credential and address book, and re-issuing one per leg would
    # test a different machine than the one that wrote the chunks.
    DRILL_LICENSE_BLOB="$blob"
    DRILL_MACHINE_ID="$machine_id"
    SESSION_MINT_URL="$(backup_api)/session"
    session=$(api POST "$SESSION_MINT_URL" \
        "{\"license\":$blob,\"machineId\":\"$machine_id\"}")
    capture "POST /backups/session" "$session"
    assert_equal 200 "$(api_status)" "the blob alone mints a storage session (no API token presented)"
    assert_stdout_json 'd.token.startsWith("rbs_")' true "the session token carries its own prefix"
    assert_stdout_json 'd.subscriptionId' "$SUBSCRIPTION_ID" "and is scoped to this subscription"
    assert_stdout_json 'd.grantKind' presigned-s3 \
        "the server reports a configured data plane (presigned S3 over the local store)"
    # dataPlaneUrl is where CHUNK BYTES go and is NOT an API root; renet says so
    # at session.go:43-47 after mistaking it for one cost a 100% mint failure.
    assert_stdout_json 'd.dataPlaneUrl' "$(store_url)" \
        "dataPlaneUrl names the STORE (chunk bytes), not the control-plane root"
    SESSION_TOKEN=$(drill_json 'd.token' <<<"$session")
    # renet derives every later call from this value and nothing else
    # (session.go:35-36,178), so leg h needs it verbatim.
    SESSION_BASE_URL=$(drill_json 'd.dataPlaneUrl || ""' <<<"$session")

    # CONTROL. Without this, every assertion above could be passing on a server
    # that mints a session for anything at all.
    local forged forged_response
    forged=$(node -e '
      const d = JSON.parse(require("fs").readFileSync(0, "utf8"));
      const raw = JSON.parse(Buffer.from(d.license.payload, "base64").toString());
      raw.subscriptionId = require("crypto").randomUUID();
      d.license.payload = Buffer.from(JSON.stringify(raw)).toString("base64");
      process.stdout.write(JSON.stringify(d.license));
    ' <<<"$blob_response")
    forged_response=$(api POST "$(backup_api)/session" \
        "{\"license\":$forged,\"machineId\":\"$machine_id\"}")
    capture "POST /backups/session (tampered blob — planted control)" "$forged_response"
    assert_equal 403 "$(api_status)" \
        "planted control: a tampered blob is REFUSED, so the check above can fail"
    assert_stdout_json 'd.code' INVALID_LICENSE_SIGNATURE "and the refusal names the signature"
    assert_stdout_json 'typeof d.token' undefined "no session token leaks with the refusal"
}

# -----------------------------------------------------------------------------
# Leg b — the seed upload
# -----------------------------------------------------------------------------

# upload_cells <plan-json> <image> <missing-json-array>
# PUTs one object per MISSING hash through the grant's presigned URLs, and
# asserts each one. Content addressing means one PUT per unique hash, never one
# per cell.
GRANT_JSON=""
upload_cells() {
    local plan="$1" image="$2" missing="$3"
    local count hash index url status failures=0
    count=$(drill_json 'd.length' <<<"$missing")
    local i=0
    while [[ $i -lt $count ]]; do
        hash=$(drill_json "d[$i]" <<<"$missing")
        index=$(drill_json "d.cells.indexOf(\"$hash\")" <<<"$plan")
        image_js slice "$image" "$index" "$DRILL_WORK/cell.bin"
        # BARE HASH, not the object key: the DTO documents putUrls as
        # "hash -> presigned PUT URL" and renet indexes it that way
        # (pkg/chunkstore/grants.go:181). The server keyed it by full object
        # key once; every lookup missed on a grant that was otherwise perfectly
        # well formed, and the upload path failed silently and completely.
        url=$(drill_json "(d.grant.putUrls || {})[\"$hash\"] || \"\"" <<<"$GRANT_JSON")
        if [[ -z "$url" ]]; then
            failures=$((failures + 1))
            i=$((i + 1))
            continue
        fi
        # If-None-Match is MANDATORY, not decorative. The account presigns
        # these URLs with IfNoneMatch (backup-chunk-store.ts), SigV4 signs the
        # headers a request carries, and `if-none-match` therefore appears in
        # X-Amz-SignedHeaders. Drop it here and the store answers 403
        # SignatureDoesNotMatch — this drill IS the machine's stand-in, so it
        # sends exactly what pkg/chunkstore/grants.go sends.
        status=$(curl -sS -o /dev/null -w '%{http_code}' -X PUT \
            -H 'If-None-Match: *' --data-binary "@$DRILL_WORK/cell.bin" "$url")
        [[ "$status" == "200" ]] || failures=$((failures + 1))
        i=$((i + 1))
    done
    printf '%s' "$failures"
}

# put_manifest <snapshot-id> <manifest-json>
# The manifest object, written THE WAY A MACHINE WRITES IT: through the
# manifestPutUrl the grant carries, since a machine holds no store credentials.
# The drill-signed fallback below exists only for the case where a backend mints
# no manifest URL; it is announced when it fires, because a fallback that
# happens silently would hide the very gap assertion 20 measures.
put_manifest() {
    local snapshot="$1" body="$2" url
    printf '%s' "$body" >"$DRILL_WORK/manifest.json"
    url=$(drill_json 'd.grant.manifestPutUrl || ""' <<<"$GRANT_JSON")
    if [[ -n "$url" ]]; then
        # Create-only, same signed-header reason as the cell PUTs above. The
        # manifest key is unique per (lineage, snapshot) and this drill mints a
        # fresh lineage uuid per run, so the condition never collides here; when
        # it DOES collide, renet fails the run rather than swallowing it, because
        # a manifest key is a snapshot id and not a content hash.
        curl -sS -o /dev/null -w '%{http_code}' -X PUT -H 'If-None-Match: *' \
            --data-binary "@$DRILL_WORK/manifest.json" "$url"
        return 0
    fi
    drill_note "no manifestPutUrl in the grant: signing the manifest write with the"
    drill_note "store's own credentials, which a machine cannot do (see assertion 20)"
    s3_curl -o /dev/null -w '%{http_code}' -X PUT --data-binary "@$DRILL_WORK/manifest.json" \
        "$(store_url)/${BACKUP_BUCKET}/t/${SUBSCRIPTION_ID}/l/${LINEAGE}/m/${snapshot}"
}

# manifest_body <snapshot> <plan> [parent] — the shapes renet actually writes
# (pkg/chunkstore/manifest.go): a full manifest carries `cells` with "" for a
# hole; a delta carries `parent` + `changedCells`.
manifest_body() {
    local snapshot="$1" plan="$2" parent="${3:-}" parent_plan="${4:-}"
    node -e '
      const [snapshot, planRaw, parent, parentRaw, lineage, cellBytes] = process.argv.slice(1);
      const plan = JSON.parse(planRaw);
      const base = {
        version: 1,
        snapshotId: snapshot,
        repositoryGuid: lineage,
        lineage,
        cellBytes: Number(cellBytes),
        imageBytes: plan.imageBytes,
        createdAt: new Date().toISOString(),
      };
      if (parent) {
        const parentPlan = JSON.parse(parentRaw);
        const changedCells = {};
        plan.cells.forEach((hash, index) => {
          if (parentPlan.cells[index] !== hash) changedCells[String(index)] = hash;
        });
        process.stdout.write(JSON.stringify({ ...base, parent, changedCells }));
      } else {
        process.stdout.write(JSON.stringify({ ...base, cells: plan.cells }));
      }
    ' "$snapshot" "$plan" "$parent" "$parent_plan" "$LINEAGE" "$CELL_BYTES"
}

SEED_PLAN=""
INCR_PLAN=""

leg_b_seed_upload() {
    drill_step "Leg b: the seed upload, with real bytes in the store"

    image_js make "$DRILL_WORK/image-v1.bin" 1
    SEED_PLAN=$(image_js plan "$DRILL_WORK/image-v1.bin")

    local stream
    stream=$(session_api POST /streams "{\"repositoryGuid\":\"$LINEAGE\",\"lineageGuid\":\"$LINEAGE\"}")
    capture "POST /backups/streams" "$stream"
    assert_equal 200 "$(api_status)" "the server mints a stream id for this repo and machine"
    assert_stdout_json 'd.created' true "and reports it as newly created"
    STREAM_ID=$(drill_json 'd.streamId' <<<"$stream")

    local unique exists missing declared
    unique=$(drill_json 'JSON.stringify(d.unique)' <<<"$SEED_PLAN")
    exists=$(session_api POST /exists "{\"lineageGuid\":\"$LINEAGE\",\"hashes\":$unique}")
    capture "POST /backups/exists (virgin lineage)" "$exists"
    assert_equal 200 "$(api_status)" "exists-batch answers for a lineage the store has never seen"
    assert_stdout_json 'd.existing.length' 0 "and holds none of these hashes yet"
    assert_stdout_json 'd.pinExpiresAt' "" "so there is nothing to pin (null, not a stale promise)"

    missing="$unique"
    declared=$(drill_json "d.length * $CELL_BYTES" <<<"$missing")
    GRANT_JSON=$(session_api POST /grants \
        "{\"snapshotId\":\"$SNAP_SEED\",\"lineageGuid\":\"$LINEAGE\",\"declaredBytes\":$declared,\"hashes\":$missing}")
    capture "POST /backups/grants" "$GRANT_JSON"
    assert_equal 200 "$(api_status)" "a write grant is minted (the quota is checked here, before any I/O)"
    assert_stdout_json 'd.grant.kind' presigned-s3 "the grant is the presigned-S3 kind"
    assert_stdout_json 'Object.keys(d.grant.putUrls).length' \
        "$(drill_json 'd.length' <<<"$missing")" \
        "one PUT URL per missing hash — the wire contract renet treats a gap in as fatal"
    assert_stdout_json 'Object.values(d.grant.putUrls).every(u => u.includes("X-Amz-Signature=") && u.includes("/c/"))' \
        true "every URL is actually signed, and points into the lineage's chunk prefix"
    # The KEY shape, not just the value. renet indexes this map by bare hash
    # (pkg/chunkstore/grants.go:181) and the DTO documents it as
    # "hash -> presigned PUT URL". Keyed by full object key instead, every
    # lookup misses and the run uploads nothing while looking healthy — a
    # silent total failure of the upload path, which is why this is asserted
    # rather than discovered by a lookup that quietly returns undefined.
    assert_stdout_json 'Object.keys(d.grant.putUrls).every(k => /^[0-9a-f]{64}$/.test(k))' true \
        "putUrls is keyed by BARE HASH, the way the machine indexes it"
    # The manifest object must be in the bucket before commit will believe a
    # commit (the server HEADs it). On the presigned path the machine has no
    # credentials, so a grant without a manifest URL makes the documented flow
    # impossible; the DTO declares the field for exactly this reason.
    assert_stdout_json 'typeof d.grant.manifestPutUrl' string \
        "the grant carries a manifest PUT URL (commit HEADs that object; a machine has no other way to write it)"

    local failures
    failures=$(upload_cells "$SEED_PLAN" "$DRILL_WORK/image-v1.bin" "$missing")
    DRILL_LAST_CMD="PUT each missing cell through its presigned URL"
    assert_equal 0 "$failures" "every cell PUT into the store returns 200"

    local recheck
    recheck=$(session_api POST /exists "{\"lineageGuid\":\"$LINEAGE\",\"hashes\":$unique}")
    capture "POST /backups/exists (after the uploads)" "$recheck"
    assert_stdout_json 'd.existing.length' "$(drill_json 'd.length' <<<"$unique")" \
        "the server now HEADs every one of them in the store: the bytes really landed"

    local manifest status
    manifest=$(manifest_body "$SNAP_SEED" "$SEED_PLAN")
    status=$(put_manifest "$SNAP_SEED" "$manifest")
    DRILL_LAST_CMD="PUT the manifest object through the grant's manifestPutUrl"
    assert_equal 200 "$status" \
        "the manifest object reaches the bucket through the GRANT, as a machine would"

    SEED_STORED_BYTES=$declared
    local commit
    commit=$(session_api POST /commit \
        "{\"snapshotId\":\"$SNAP_SEED\",\"lineageGuid\":\"$LINEAGE\",\"streamId\":\"$STREAM_ID\",\"cellSizeBytes\":$CELL_BYTES,\"totalBytes\":$(drill_json 'd.imageBytes' <<<"$SEED_PLAN"),\"addedBytes\":$declared,\"addedChunkCount\":$(drill_json 'd.length' <<<"$missing")}")
    capture "POST /backups/commit (seed)" "$commit"
    assert_equal 200 "$(api_status)" "the snapshot commits"
    assert_stdout_json 'd.idempotent' false "as a first commit, not a replay"
    assert_stdout_json 'd.storedBytes' "$declared" "and the ledger moved by exactly the bytes uploaded"

    local replay
    replay=$(session_api POST /commit \
        "{\"snapshotId\":\"$SNAP_SEED\",\"lineageGuid\":\"$LINEAGE\",\"streamId\":\"$STREAM_ID\",\"cellSizeBytes\":$CELL_BYTES,\"totalBytes\":$(drill_json 'd.imageBytes' <<<"$SEED_PLAN"),\"addedBytes\":$declared,\"addedChunkCount\":$(drill_json 'd.length' <<<"$missing")}")
    capture "POST /backups/commit (replayed)" "$replay"
    assert_stdout_json 'd.idempotent' true "a replayed commit is idempotent"
    assert_stdout_json 'd.storedBytes' "$declared" "and bills nothing twice"
}

# -----------------------------------------------------------------------------
# Leg c — the incremental upload
# -----------------------------------------------------------------------------

leg_c_incremental_upload() {
    drill_step "Leg c: the second run moves only what changed"

    image_js make "$DRILL_WORK/image-v2.bin" 2
    INCR_PLAN=$(image_js plan "$DRILL_WORK/image-v2.bin")

    local unique exists missing declared
    unique=$(drill_json 'JSON.stringify(d.unique)' <<<"$INCR_PLAN")
    exists=$(session_api POST /exists "{\"lineageGuid\":\"$LINEAGE\",\"hashes\":$unique}")
    capture "POST /backups/exists (second run)" "$exists"
    assert_equal 200 "$(api_status)" "exists-batch answers for the changed image"
    assert_stdout_json 'd.existing.length' "$(drill_json 'd.unique.length - 1' <<<"$INCR_PLAN")" \
        "every unchanged cell is already held: exactly one hash is new"
    # An exists ANSWER is a promise ("you may skip these"), so it must pin them
    # for 24h; without the pin, GC can delete a skipped chunk between the answer
    # and the commit that references it.
    assert_stdout_json 'typeof d.pinExpiresAt' string "the skip promise is pinned"

    missing=$(node -e '
      const [uniqueRaw, existsRaw] = process.argv.slice(1);
      const unique = JSON.parse(uniqueRaw);
      const held = new Set(JSON.parse(existsRaw).existing);
      process.stdout.write(JSON.stringify(unique.filter((h) => !held.has(h))));
    ' "$unique" "$exists")
    DRILL_LAST_CMD="the missing set of the incremental run"
    assert_equal 1 "$(drill_json 'd.length' <<<"$missing")" \
        "one cell changed, so exactly one cell transfers"

    declared=$((CELL_BYTES))
    GRANT_JSON=$(session_api POST /grants \
        "{\"snapshotId\":\"$SNAP_INCR\",\"lineageGuid\":\"$LINEAGE\",\"declaredBytes\":$declared,\"hashes\":$missing}")
    capture "POST /backups/grants (incremental)" "$GRANT_JSON"
    assert_equal 200 "$(api_status)" "a grant is minted for the delta only"

    local failures
    failures=$(upload_cells "$INCR_PLAN" "$DRILL_WORK/image-v2.bin" "$missing")
    DRILL_LAST_CMD="PUT the single changed cell"
    assert_equal 0 "$failures" "the changed cell uploads"

    local manifest status commit total
    manifest=$(manifest_body "$SNAP_INCR" "$INCR_PLAN" "$SNAP_SEED" "$SEED_PLAN")
    status=$(put_manifest "$SNAP_INCR" "$manifest")
    DRILL_LAST_CMD="PUT the DELTA manifest object"
    assert_equal 200 "$status" "the delta manifest reaches the bucket"

    total=$(drill_json 'd.imageBytes' <<<"$INCR_PLAN")
    commit=$(session_api POST /commit \
        "{\"snapshotId\":\"$SNAP_INCR\",\"lineageGuid\":\"$LINEAGE\",\"streamId\":\"$STREAM_ID\",\"parentSnapshotId\":\"$SNAP_SEED\",\"cellSizeBytes\":$CELL_BYTES,\"totalBytes\":$total,\"addedBytes\":$declared,\"addedChunkCount\":1}")
    capture "POST /backups/commit (incremental)" "$commit"
    assert_equal 200 "$(api_status)" "the incremental snapshot commits"
    assert_stdout_json 'd.storedBytes' "$((SEED_STORED_BYTES + CELL_BYTES))" \
        "the ledger grew by ONE cell, not by another whole image"
}

# -----------------------------------------------------------------------------
# Leg d — point-in-time restore, byte-identical
# -----------------------------------------------------------------------------

# restore_session_token — mint a RESTORE-intent session for the drill's license.
# Separate from the backup-intent session leg a mints, because the two are
# deliberately not interchangeable: a restore session cannot write, and it is
# the only intent a lapsed-but-retained subscription can obtain.
RESTORE_SESSION_TOKEN=""
restore_session_token() {
    local response
    response=$(api POST "$SESSION_MINT_URL" \
        "{\"license\":$DRILL_LICENSE_BLOB,\"machineId\":\"$DRILL_MACHINE_ID\",\"intent\":\"restore\"}")
    RESTORE_SESSION_TOKEN=$(drill_json 'd.token || ""' <<<"$response")
    [[ -n "$RESTORE_SESSION_TOKEN" ]] || return 1
}

# read_grant <snapshot-id> [hash...] — POST /backups/read-grants on the restore
# session, echoing the response.
read_grant() {
    local snapshot="$1"
    shift
    local hashes
    hashes=$(node -e 'process.stdout.write(JSON.stringify(process.argv.slice(1)))' "$@")
    api POST "$(backup_api)/read-grants" \
        "{\"lineageGuid\":\"$LINEAGE\",\"snapshotId\":\"$snapshot\",\"hashes\":$hashes}" \
        -H "X-Backup-Session: $RESTORE_SESSION_TOKEN"
}

# restore_snapshot <snapshot-id> <out-image>
# Restore AS A MACHINE DOES IT: through a read grant, never with the store's own
# credentials. The drill used to sign these GETs itself because no read-side
# grant kind existed; it does now, so signing them here would prove the bytes
# are readable by SOMEBODY rather than that the grant is what authorized it.
#
# Two grants per restore, and that is the protocol, not a wasted round trip: the
# first is minted with NO hashes to learn `manifestChain` (which the machine
# cannot derive — it has no manifest index), and the second presigns the chunks
# once the composed inventory says which ones are wanted.
restore_snapshot() {
    local snapshot="$1" out="$2"
    local dir="$DRILL_WORK/restore-$snapshot"
    mkdir -p "$dir/chunks"

    local chain_grant chain
    chain_grant=$(read_grant "$snapshot") || return 1
    chain=$(drill_json '(d.manifestChain || []).join(" ")' <<<"$chain_grant")
    [[ -n "$chain" ]] || return 1

    # Fetch every manifest the server named, FULL ROOT FIRST, and compose the
    # chain one hop at a time. The chain is of unbounded depth: renet builds a
    # delta against the local anchor whenever it is trusted, so a full manifest
    # appears only at first backup, a geometry change, a corrupt journal, or
    # --reseed.
    local id url
    for id in $chain; do
        url=$(drill_json "(d.manifestGetUrls || {})[\"$id\"] || \"\"" <<<"$chain_grant")
        [[ -n "$url" ]] || return 1
        curl -fsS -o "$dir/m-$id.json" "$url" || return 1
    done
    local -a chain_files=()
    for id in $chain; do chain_files+=("$dir/m-$id.json"); done
    node -e '
      const fs = require("fs");
      const [out, ...files] = process.argv.slice(1);
      let cells = null;
      for (const f of files) {
        const m = JSON.parse(fs.readFileSync(f, "utf8"));
        if (cells === null) {
          if (m.parent) throw new Error(`chain root ${m.snapshotId} is a delta`);
          cells = [...m.cells];
        } else {
          for (const [i, h] of Object.entries(m.changedCells || {})) cells[Number(i)] = h;
        }
      }
      fs.writeFileSync(out, JSON.stringify(cells));
    ' "$dir/cells.json" "${chain_files[@]}" || return 1

    local wanted
    wanted=$(drill_json 'd.filter(h => h !== "").filter((h,i,a) => a.indexOf(h) === i).join(" ")' \
        <"$dir/cells.json")

    local chunk_grant hash
    # shellcheck disable=SC2086
    chunk_grant=$(read_grant "$snapshot" $wanted) || return 1
    for hash in $wanted; do
        url=$(drill_json "(d.getUrls || {})[\"$hash\"] || \"\"" <<<"$chunk_grant")
        # Keyed by BARE HASH, never by object key: the write path already paid
        # for the other choice and every lookup missed.
        [[ -n "$url" ]] || return 1
        curl -fsS -o "$dir/chunks/$hash" "$url" || return 1
    done
    image_js assemble "$dir/cells.json" "$dir/chunks" "$out"
}

leg_d_point_in_time_restore() {
    drill_step "Leg d: both snapshots restore byte-identically, THROUGH A READ GRANT"

    drill_run restore_session_token
    assert_exit 0 "a restore-intent session is minted from the same license blob"

    local seed_sha incr_sha restored_seed restored_incr
    seed_sha=$(image_js sha "$DRILL_WORK/image-v1.bin")
    incr_sha=$(image_js sha "$DRILL_WORK/image-v2.bin")
    DRILL_LAST_CMD="sha256 of the two source images"
    assert_not_equal "$seed_sha" "$incr_sha" \
        "control: the two source images really differ (a compare of identical inputs proves nothing)"

    drill_run restore_snapshot "$SNAP_SEED" "$DRILL_WORK/restored-v1.bin"
    assert_exit 0 "the seed snapshot is fetched and reassembled"
    restored_seed=$(image_js sha "$DRILL_WORK/restored-v1.bin")
    DRILL_LAST_CMD="sha256 of the restored seed image"
    assert_equal "$seed_sha" "$restored_seed" \
        "POINT IN TIME: the OLD snapshot still restores to the OLD bytes after the newer one landed"

    drill_run restore_snapshot "$SNAP_INCR" "$DRILL_WORK/restored-v2.bin"
    assert_exit 0 "the incremental snapshot is fetched and materialized over its parent"
    restored_incr=$(image_js sha "$DRILL_WORK/restored-v2.bin")
    DRILL_LAST_CMD="sha256 of the restored incremental image"
    assert_equal "$incr_sha" "$restored_incr" "and reassembles byte-identically too"
}

# -----------------------------------------------------------------------------
# Leg e — the quota refusal, observed live at mint time
# -----------------------------------------------------------------------------

leg_e_quota_refusal() {
    drill_step "Leg e: past the quota, the grant is refused before any I/O"

    local usage used
    usage=$(api GET "$(backup_api)/usage" "" -H "Authorization: Bearer $API_TOKEN")
    capture "GET /backups/usage" "$usage"
    assert_equal 200 "$(api_status)" "usage is readable with the backup:read scope"
    used=$(drill_json 'd.storedBytes' <<<"$usage")
    assert_equal "$((SEED_STORED_BYTES + CELL_BYTES))" "$used" \
        "and reports exactly the bytes this drill stored"

    # Pin the quota to what is already stored: the next byte cannot fit.
    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        "{\"storageQuotaBytes\":$used}" >/dev/null
    QUOTA_LOWERED=1
    drill_note "storage quota pinned to the stored bytes ($used)"

    local refused
    refused=$(session_api POST /grants \
        "{\"snapshotId\":\"snap-over-quota\",\"lineageGuid\":\"$LINEAGE\",\"declaredBytes\":1,\"hashes\":[]}")
    capture "POST /backups/grants (one byte over the quota)" "$refused"
    assert_equal 403 "$(api_status)" "one byte over the quota is refused"
    assert_stdout_json 'd.code' BACKUP_QUOTA_EXCEEDED "with the exact refusal code"
    assert_stdout_json 'd.retryAfter > 0' true "carrying a retry hint the client can back off on"
    assert_stdout_json 'd.quotaBytes' "$used" "and the quota it measured against"

    # CONTROL: the same request, one byte of headroom later, must succeed —
    # otherwise the refusal above could be any old rejection.
    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        "{\"storageQuotaBytes\":$((used + 1))}" >/dev/null
    local allowed
    allowed=$(session_api POST /grants \
        "{\"snapshotId\":\"snap-over-quota\",\"lineageGuid\":\"$LINEAGE\",\"declaredBytes\":1,\"hashes\":[]}")
    capture "POST /backups/grants (with one byte of headroom — planted control)" "$allowed"
    assert_equal 200 "$(api_status)" \
        "planted control: with one byte of room the SAME request is granted, so the refusal was the quota"

    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" \
        '{"storageQuotaBytes":null}' >/dev/null
    QUOTA_LOWERED=0
}

# -----------------------------------------------------------------------------
# Leg f — the CLI read surfaces
# -----------------------------------------------------------------------------

setup_cli_config() {
    drill_step "Setup: an rdc config pointed at this gateway"
    drill_setup_run "$RDC" config init "$CONFIG_NAME" --server "$(drill_server_url)"
    drill_setup_run "$RDC" config current -o json
    drill_setup_run "$RDC" subscription login --token "$API_TOKEN" --server "$(drill_server_url)"
}

leg_f_cli_reads() {
    drill_step "Leg f: rdc backup usage / manifests against the live server"
    setup_cli_config

    # The CLI wraps every -o json payload in its {success, data} envelope, so
    # the fields live one level down; asserting on the bare shape reads as a
    # missing field and blames the server for the client's envelope.
    drill_run "$RDC" backup usage -o json
    assert_exit 0 "rdc backup usage exits 0"
    assert_stdout_json 'd.data.storedBytes' "$((SEED_STORED_BYTES + CELL_BYTES))" \
        "and reports the same stored bytes the ledger holds"
    assert_stdout_json 'd.data.lineages.some(l => l.lineageGuid === "'"$LINEAGE"'")' true \
        "with this repo's lineage in the per-repo breakdown"

    drill_run "$RDC" backup manifests -o json
    assert_exit 0 "rdc backup manifests exits 0"
    assert_stdout_json 'd.data.manifests.some(m => m.snapshotId === "'"$SNAP_SEED"'")' true \
        "the seed snapshot is listed"
    assert_stdout_json 'd.data.manifests.some(m => m.snapshotId === "'"$SNAP_INCR"'" && m.parentSnapshotId === "'"$SNAP_SEED"'")' \
        true "and the incremental one, carrying its parent"

    # Stream placement: the human progress line must not land on stdout, or
    # every `-o json` consumer downstream parses garbage.
    drill_run "$RDC" backup usage -o json
    assert_stdout_not_contains "Fetching" "the progress line stays off stdout in json mode"
}

# -----------------------------------------------------------------------------
# Leg g — the prune JSON contract, driven end to end
# -----------------------------------------------------------------------------
# Wave 0 added four prune resource kinds to the CLI parser, pinned to renet's Go
# struct tags by a coverage test that READS the tags. Nothing had ever run the
# real binary and parsed its real output. This leg is that missing link, and it
# needs no machine: `renet repository prune --datastore <path>` scans a plain
# directory, so a throwaway fixture in the work dir is enough.

leg_g_prune_json_contract() {
    drill_step "Leg g: real renet prune JSON through the real CLI parser"

    local ds="$DRILL_WORK/ds"
    local dead_guid="11111111-2222-3333-4444-555555555555"
    local staging_guid="66666666-7777-8888-9999-aaaaaaaaaaaa"
    local live_guid="22222222-3333-4444-5555-666666666666"
    mkdir -p "$ds/repositories" "$ds/mounts" "$ds/.chunk-anchors"
    # An anchor whose repo image is gone: reclaimable.
    echo "anchor" >"$ds/.chunk-anchors/$dead_guid"
    # Staging left by a killed run, with no lock held: reclaimable.
    echo "staging" >"$ds/.chunk-anchors/$staging_guid.new"
    # An anchor whose repo image EXISTS: the over-eager control. Deleting it
    # would silently degrade the next backup to a full local rehash.
    echo "anchor" >"$ds/.chunk-anchors/$live_guid"
    echo "image" >"$ds/repositories/$live_guid"

    drill_run "$RENET_BIN" repository prune --datastore "$ds" --dry-run --output json
    assert_exit 0 "renet repository prune --output json exits 0 on a datastore directory"
    assert_stdout_json "d.stale_backup_anchors.includes(\"$dead_guid\")" true \
        "the anchor whose repo is gone is reported (stale_backup_anchors)"
    assert_stdout_json "d.stale_backup_anchors.includes(\"$staging_guid.new\")" true \
        "and so is the abandoned .new staging"
    assert_stdout_json "d.stale_backup_anchors.includes(\"$live_guid\")" false \
        "over-eager control: the anchor of a LIVE repo is NOT reported"
    assert_stdout_json '"stale_backup_journals" in d' true \
        "the journal key is present in the contract (empty here: the journal dir is machine-local)"
    assert_stdout_json '"stale_pull_staging" in d && "stale_churn_probe_bases" in d' true \
        "together with wave 0's two keys"

    # The other half of the contract: the CLI's parser turns THIS output into
    # preview rows. Reading the struct tags cannot catch a parser that never
    # sees real output.
    cp "$DRILL_STDOUT" "$DRILL_WORK/prune.json"
    cat >"$DRILL_WORK/parse-prune.ts" <<PARSE_TS
import { readFileSync } from 'node:fs';
import {
  buildPrunePreviewRows,
  parseDatastorePruneOutput,
  type DatastorePrunableResources,
} from '$DRILL_ROOT_DIR/packages/cli/src/commands/datastore-prune-parser.js';

const parsed = parseDatastorePruneOutput(
  readFileSync(process.argv[2], 'utf8')
) as DatastorePrunableResources;
process.stdout.write(JSON.stringify({ rows: buildPrunePreviewRows(parsed) }));
PARSE_TS
    drill_run run_tsx "$DRILL_WORK/parse-prune.ts" "$DRILL_WORK/prune.json"
    assert_exit 0 "the CLI parser consumes renet's real output"
    assert_stdout_json 'd.rows.filter(r => r.type === "backup-anchor").length' 2 \
        "and renders both reclaimable anchors as backup-anchor rows"
}

# -----------------------------------------------------------------------------
# Leg h — machine wire conformance
# -----------------------------------------------------------------------------
# renet's SessionControlPlane (pkg/chunkstore/session.go) is the ONLY client a
# machine will ever use, and it was tested exclusively against an httptest fake
# written from the same file. The account routes were tested against their own
# in-process app. Nothing ever put the two together. These assertions present
# the shapes renet actually sends to the server that actually answers.
#
# Each assertion states the CONFORMING outcome. A failure here is not a broken
# drill: it is the integration gap, and the message names both sides.

leg_h_machine_wire_conformance() {
    drill_step "Leg h: the shapes renet's session client sends, against the live server"

    # WHY THIS LEG EXISTS. renet's SessionControlPlane (pkg/chunkstore/session.go)
    # is the only client a machine will ever use, and it was tested exclusively
    # against an httptest fake written from the same file, while the account
    # routes were tested against their own in-process app. Nothing put the two
    # together. The first run of this leg found five divergences at once (wrong
    # base URL, /chunks/exists, bearer auth, a grant body missing the three
    # fields zod requires, and a manifest POST); the client was rewritten to
    # conform. These assertions are what keeps it conforming, so they present
    # the CURRENT client's shapes and are pinned to it by file:line.

    # 1. The API root. The client derives it as the mint URL minus its /session
    #    suffix (session.go:134) instead of trusting a baseUrl the server never
    #    sends, so the derivation must land on the group the routes live under.
    local derived
    derived="${SESSION_MINT_URL%/session}"
    DRILL_LAST_CMD="derive the API root the way session.go:134 does"
    assert_equal "$(backup_api)" "$derived" \
        "the mint URL minus /session IS the control-plane root (session.go:134)"

    # 2. exists: path, header and body, exactly as ExistsBatch sends them
    #    (session.go:256-261). The header is X-Backup-Session, never a bearer:
    #    the account reserves Authorization for api-token auth.
    local hash_a exists
    hash_a=$(printf 'a%.0s' {1..64})
    exists=$(api POST "$(backup_api)/exists" \
        "{\"lineageGuid\":\"$LINEAGE\",\"hashes\":[\"$hash_a\"]}" \
        -H "X-Backup-Session: $SESSION_TOKEN")
    capture "POST /exists as ExistsBatch sends it (session.go:256-261)" "$exists"
    assert_equal 200 "$(api_status)" "renet's exists call is accepted verbatim"
    # The client computes the MISSING set as the complement of `existing`
    # (session.go:266-289) because it once decoded a `missing` key the account
    # never sends: that decoded to nil, nil read as "nothing missing", and a run
    # would have uploaded ZERO chunks and still committed. So the field it
    # complements must actually be there.
    assert_stdout_json 'Array.isArray(d.existing)' true \
        "the answer carries an 'existing' array (a missing key = a silent zero-chunk backup)"

    # 3. grants: the body MintGrant sends (session.go:293-299), including the
    #    two fields the quota check needs before any mint happens.
    local grant
    grant=$(api POST "$(backup_api)/grants" \
        "{\"snapshotId\":\"wire-probe-$$\",\"lineageGuid\":\"$LINEAGE\",\"declaredBytes\":0,\"hashes\":[]}" \
        -H "X-Backup-Session: $SESSION_TOKEN")
    capture "POST /grants as MintGrant sends it (session.go:293-299)" "$grant"
    assert_equal 200 "$(api_status)" "renet's grant body satisfies the route's schema"
    # MintGrant decodes a FLAT union nested under `grant`, plus the lease it
    # stamps for GC's benefit (session.go:310-329).
    assert_stdout_json 'typeof d.grant.kind' string "the response nests the grant under 'grant', with a kind"
    assert_stdout_json 'typeof d.leaseId' string "and carries the leaseId the client stamps"

    # 4. commit: the FIELD SET CommitManifest sends (session.go:341-352), not
    #    the manifest document. The manifest object itself goes to the bucket.
    local commit
    commit=$(api POST "$(backup_api)/commit" \
        "{\"snapshotId\":\"$SNAP_INCR\",\"lineageGuid\":\"$LINEAGE\",\"streamId\":\"$STREAM_ID\",\"cellSizeBytes\":$CELL_BYTES,\"totalBytes\":0,\"addedBytes\":0,\"addedChunkCount\":0}" \
        -H "X-Backup-Session: $SESSION_TOKEN")
    capture "POST /commit as CommitManifest sends it (session.go:341-352)" "$commit"
    assert_equal 200 "$(api_status)" "renet's commit field set is accepted"
    assert_stdout_json 'd.idempotent' true \
        "and replaying leg c's snapshot is idempotent, so this probe bills nothing"

    # 5. streams: GetOrCreateStream's body (session.go:148-151).
    local stream
    stream=$(api POST "$(backup_api)/streams" \
        "{\"repositoryGuid\":\"$LINEAGE\",\"lineageGuid\":\"$LINEAGE\"}" \
        -H "X-Backup-Session: $SESSION_TOKEN")
    capture "POST /streams as GetOrCreateStream sends it (session.go:148-151)" "$stream"
    assert_equal 200 "$(api_status)" "renet's stream call is accepted"
    assert_stdout_json 'd.streamId' "$STREAM_ID" \
        "and resolves to the SAME stream leg b opened (identity is per repo and machine)"

    # 6. The control: a body the server must REFUSE. Without it, every
    #    acceptance above could be an endpoint that accepts anything.
    local refused
    refused=$(api POST "$(backup_api)/grants" \
        "{\"lineage\":\"$LINEAGE\",\"hashes\":[]}" \
        -H "X-Backup-Session: $SESSION_TOKEN")
    capture "POST /grants with the client's OLD body {lineage, hashes} — planted control" "$refused"
    assert_equal 400 "$(api_status)" \
        "planted control: the pre-fix body is still refused, so the acceptances above mean something"
}

# -----------------------------------------------------------------------------
# Leg i — opt-in, needs a machine
# -----------------------------------------------------------------------------

# lapse_subscription — move the drill subscription out of an entitled state.
# There is no /test route for this (lib.sh:792 says so), so it goes the same way
# the licensing drill reaches these states: the admin PUT, through the elevated
# root session setup_account already opened.
#
# LAPSED_SUBSCRIPTION (declared at the top, beside QUOTA_LOWERED) is the restore
# flag: leg e's quota edit taught this drill that an admin edit outlives the work
# directory, and a subscription left suspended would fail the NEXT run at leg a
# for a reason nothing explains. drill_teardown_hook puts it back.
lapse_subscription() {
    drill_account_patch_subscription "$ADMIN_JAR" "$SUBSCRIPTION_ID" '{"status":"suspended"}' >/dev/null
    LAPSED_SUBSCRIPTION=1
}

# -----------------------------------------------------------------------------
# Leg j — the planted control for leg d
# -----------------------------------------------------------------------------
# Leg d proves the bytes are readable THROUGH a read grant. On its own that does
# not prove the read grant is what authorized the read: the same bytes are
# readable by anyone holding the store's credentials, which is exactly how the
# drill used to do it. This leg closes that by asserting the negative — a
# session minted to WRITE must not be able to mint a read, and a read session
# must not be able to mint a write.
leg_j_write_grant_cannot_read() {
    drill_step "Leg j: a write session cannot read, and a read session cannot write"

    # The backup-intent session leg a minted is still in hand. It must be
    # refused at /read-grants.
    local refused
    refused=$(session_api POST /read-grants \
        "{\"lineageGuid\":\"$LINEAGE\",\"snapshotId\":\"$SNAP_SEED\"}")
    capture "POST /backups/read-grants on a BACKUP-intent session" "$refused"
    assert_not_equal 200 "$(api_status)" \
        "a backup-intent session is REFUSED a read grant (else leg d proves only that someone can read)"

    # And the mirror: the restore session must not be able to write. This is the
    # half that matters for blast radius — a read credential that can also write
    # is a ransomware path, not a restore path.
    drill_run restore_session_token
    assert_exit 0 "control: a restore-intent session still mints (the refusal above is about INTENT, not a dead token)"

    # declaredBytes, NOT totalBytes. The first version of this leg sent the
    # wrong field name, so the request died in schema validation with a 400 and
    # never reached the intent check it exists to exercise: the assertion failed
    # for a reason that had nothing to do with intent. The comment lives HERE
    # and not inside the call, because a comment between a backslash
    # continuation and its next argument breaks the continuation outright.
    local write_refused
    write_refused=$(api POST "$(backup_api)/grants" \
        "{\"hashes\":[],\"declaredBytes\":1,\"lineageGuid\":\"$LINEAGE\",\"snapshotId\":\"$SNAP_SEED\"}" \
        -H "X-Backup-Session: $RESTORE_SESSION_TOKEN")
    capture "POST /backups/grants on a RESTORE-intent session" "$write_refused"
    assert_equal 403 "$(api_status)" "a restore-intent session is REFUSED a write grant"
    # d.code, matching every other refusal assertion in this drill (:674, :1057).
    # The API's envelope names it `code`; `errorCode` read as empty, so this
    # assertion failed while the server was in fact refusing by name.
    assert_stdout_json 'd.code' BACKUP_SESSION_READ_ONLY \
        "and it is refused BY NAME, not as a generic 403 that could be anything"
}

# -----------------------------------------------------------------------------
# Leg k — the 60-day retention promise, exercised end to end
# -----------------------------------------------------------------------------
# The product keeps a cancelled customer's bytes for
# BACKUP_RETENTION_AFTER_CANCEL_DAYS. Until the restore-intent session existed it
# had no way to hand them back: mintSession refused a lapsed subscription before
# the request ever reached a grant. This is the only place that promise is
# exercised against a real server rather than asserted in a unit test.
leg_k_lapsed_restore() {
    drill_step "Leg k: a LAPSED subscription can still restore inside the retention window"

    # Control first, and it is the load-bearing one: a BACKUP intent against the
    # same lapsed subscription must be refused. Without it, a green restore
    # below could just mean the lapse never took effect.
    drill_run lapse_subscription
    assert_exit 0 "the drill subscription is moved to a lapsed state"

    local backup_refused
    backup_refused=$(api POST "$SESSION_MINT_URL" \
        "{\"license\":$DRILL_LICENSE_BLOB,\"machineId\":\"$DRILL_MACHINE_ID\"}")
    capture "POST /backups/session (backup intent, lapsed)" "$backup_refused"
    assert_not_equal 200 "$(api_status)" \
        "CONTROL: a backup-intent session is refused once the subscription lapses"

    local restore_ok
    restore_ok=$(api POST "$SESSION_MINT_URL" \
        "{\"license\":$DRILL_LICENSE_BLOB,\"machineId\":\"$DRILL_MACHINE_ID\",\"intent\":\"restore\"}")
    capture "POST /backups/session (restore intent, lapsed but retained)" "$restore_ok"
    assert_equal 200 "$(api_status)" \
        "but a RESTORE-intent session is granted: this is the 60-day promise"
    RESTORE_SESSION_TOKEN=$(drill_json 'd.token || ""' <<<"$restore_ok")

    drill_run restore_snapshot "$SNAP_SEED" "$DRILL_WORK/restored-lapsed.bin"
    assert_exit 0 "and the data actually comes back through it"
    local want got
    want=$(image_js sha "$DRILL_WORK/image-v1.bin")
    got=$(image_js sha "$DRILL_WORK/restored-lapsed.bin")
    DRILL_LAST_CMD="sha256 of the image restored on a lapsed subscription"
    assert_equal "$want" "$got" "byte-identically — retained data is USABLE data, not just stored data"
}

leg_i_machine_verify() {
    drill_step "Leg i: rdc backup verify on a real machine"
    drill_note "this leg needs a repo on $VM_IP that this drill did not create"

    drill_run "$RDC" backup verify "${DRILL_REPO_REF:-drill-repo}" -o json
    assert_exit 0 "rdc backup verify exits 0 on a repo with no backup yet (no-backup is not a failure)"
    assert_stdout_contains "no-backup" "and says so by name rather than inventing a verdict"
}

main() {
    drill_parse_args "$@"
    # Before ANYTHING else, including --selftest: a mistyped leg must be
    # refused whether or not the run would have reached a server.
    validate_legs
    assert_disposable_store
    drill_init backup
    announce_cost
    drill_selftest_probe
    if [[ "$DRILL_SELFTEST" == "1" ]]; then
        drill_note "selftest mode: stopping before any server or store work"
        drill_summary
        return
    fi

    preflight_tools
    preflight_machines
    announce_unrunnable

    setup_sandbox
    setup_store_env
    setup_gateway
    setup_store_bucket
    setup_account
    setup_image_helper

    # Legs b-f, j and k all operate on the session and lineage leg a opens. Selecting
    # them without leg a would produce a pile of 401s that read like defects.
    if needs_plane && ! leg_enabled a; then
        log_error "Legs b-f, h, j and k all run inside the session leg a mints, and there is no"
        log_error "session on disk to inherit. Include leg a:  --legs a,${LEGS}"
        exit 1
    fi

    leg_enabled a && leg_a_session_mint
    leg_enabled b && leg_b_seed_upload
    leg_enabled c && leg_c_incremental_upload
    leg_enabled d && leg_d_point_in_time_restore
    leg_enabled e && leg_e_quota_refusal
    leg_enabled f && leg_f_cli_reads
    leg_enabled g && leg_g_prune_json_contract
    leg_enabled h && leg_h_machine_wire_conformance
    leg_enabled i && leg_i_machine_verify
    leg_enabled j && leg_j_write_grant_cannot_read
    leg_enabled k && leg_k_lapsed_restore

    drill_summary
}

main "$@"
