#!/usr/bin/env bash
# Start the LOCAL backup control plane for the chunk-store round-trip proof.
#
# Two processes, both local, neither touching anything remote:
#
#   1. RustFS (already running for `./run.sh account dev` config blobs) gains a
#      second bucket, `rediacc-backups-probe`. NEVER `rediacc-backups`: that is
#      the production name, and a local bucket wearing it is one env-var typo
#      away from a test writing where production backups live.
#   2. The account dev gateway on :4800, bound 0.0.0.0 so the worker VMs can
#      reach it, carrying ACCOUNT_BACKUP_S3_* so `createBackupPlane` selects the
#      S3 presign minter (the minter the operator chose for production).
#
# THE HOST HEADER IS LOAD-BEARING. `renewalUrlFor` (routes/license.ts:36)
# derives the licence's renewalUrl from `envConfig.baseUrl`, which is
# `env.PUBLIC_SITE_URL ?? \`${url.protocol}//${url.host}\`` (app.ts:534). renet
# derives the backup SESSION url from that renewalUrl by suffix swap
# (backup_snapshot.go:540). So a licence issued over http://localhost:4800
# stamps a renewalUrl no VM can reach, and the snapshot fails at session mint.
# Every account API call in this program therefore uses 192.168.111.254:4800.
#
# Same reasoning for ACCOUNT_BACKUP_S3_ENDPOINT: the presigned URLs the server signs are
# handed to renet ON THE VM, and SigV4 covers the Host header, so the endpoint
# must be spelled exactly as the VM will dial it.
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ACCOUNT_DIR="$ROOT_DIR/private/account"

BRIDGE_HOST="${BRIDGE_HOST:-192.168.111.254}"
GATEWAY_PORT="${GATEWAY_PORT:-4800}"
RUSTFS_PORT="${RUSTFS_PORT:-9100}"
RUSTFS_KEY="${RUSTFS_KEY:-configadmin}"
RUSTFS_SECRET="${RUSTFS_SECRET:-configadmin}"
PROBE_BUCKET="${PROBE_BUCKET:-rediacc-backups-probe}"
LOG_DIR="${LOG_DIR:-/tmp/backup-roundtrip}"

# Refuse the production bucket name outright. The drill carries the same guard
# for the same reason: a harness that CAN point at production eventually will.
if [[ "$PROBE_BUCKET" == "rediacc-backups" ]]; then
    echo "REFUSING bucket 'rediacc-backups': that is the production name." >&2
    exit 1
fi

mkdir -p "$LOG_DIR"

echo "==> RustFS bucket $PROBE_BUCKET on :$RUSTFS_PORT"
docker run --rm --network host \
    -e AWS_ACCESS_KEY_ID="$RUSTFS_KEY" \
    -e AWS_SECRET_ACCESS_KEY="$RUSTFS_SECRET" \
    -e AWS_DEFAULT_REGION=us-east-1 amazon/aws-cli \
    s3api create-bucket --bucket "$PROBE_BUCKET" \
    --endpoint-url "http://127.0.0.1:${RUSTFS_PORT}" >/dev/null 2>&1 || true

echo "==> account dev gateway on :$GATEWAY_PORT (ACCOUNT_BACKUP_S3_* -> $PROBE_BUCKET)"
cd "$ACCOUNT_DIR"
# `set -a` + source: the gateway needs the .env crypto keys. ACCOUNT_BACKUP_S3_* are
# absent from .env, so exporting them here reaches the process untouched --
# .env can only clobber keys it actually declares.
set -a
# shellcheck disable=SC1091
source "$ACCOUNT_DIR/.env"
set +a

export GATEWAY_PORT
export ACCOUNT_BACKUP_S3_ENDPOINT="http://${BRIDGE_HOST}:${RUSTFS_PORT}"
export ACCOUNT_BACKUP_S3_BUCKET="$PROBE_BUCKET"
export ACCOUNT_BACKUP_S3_ACCESS_KEY_ID="$RUSTFS_KEY"
export ACCOUNT_BACKUP_S3_SECRET_ACCESS_KEY="$RUSTFS_SECRET"
export CONFIG_R2_ENDPOINT="http://127.0.0.1:${RUSTFS_PORT}"
export CONFIG_R2_BUCKET="rediacc-configs"
export CONFIG_R2_ACCESS_KEY_ID="$RUSTFS_KEY"
export CONFIG_R2_SECRET_ACCESS_KEY="$RUSTFS_SECRET"
export TEST_MODE=true

exec npx tsx src/entry/dev-gateway.ts
