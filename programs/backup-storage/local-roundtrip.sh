#!/usr/bin/env bash
# Chunk-store backup/restore round trip, end to end, against a LOCAL S3.
#
# What this proves that nothing else did: a MACHINE uploaded a real repository
# image to a real S3 endpoint and a DIFFERENT repository was reconstructed from
# it byte for byte. Suite 26's RESTORE tier automates the same claim but drives
# `rdc`; the drill (`scripts/drills/backup.sh`) never creates a repo on a VM at
# all -- its leg `i` is not in the default LEGS list and needs a repo it did not
# make. So before this script the machine-level round trip had never run.
#
# It deliberately does NOT use `./rdc.sh`, because rdc rebuilds and redeploys
# renet to whatever machine it touches. Everything here is renet on the VM plus
# curl against the account API, so the binary under test is the one you chose.
#
# ## The three things that make it work, none of them obvious
#
# 1. THE HOST HEADER NAMES THE UNIVERSE. `renewalUrlFor`
#    (private/account/src/routes/license.ts:36) derives the licence's renewalUrl
#    from `envConfig.baseUrl`, which is `PUBLIC_SITE_URL ?? url.host`
#    (app.ts:534). renet then derives the backup SESSION url from that renewalUrl
#    by suffix swap (cmd/renet/backup_snapshot.go:540). Issue the licence over
#    localhost and the VM gets a session URL it cannot dial. Every call below
#    therefore goes to 192.168.111.254:4800, never localhost.
#
# 2. ONLY THE SERVER CAN MINT A USABLE LICENCE. `.ci/scripts/private/license-mint`
#    cannot stand in: it never sets `grandGuid` (its payload literal has no such
#    field), and `snapshotOneRepo` refuses a licence without one -- "repository
#    license carries no grandGuid, so the object-key lineage is unknown". The
#    lineage IS the object-key prefix, so there is nothing to upload under.
#
# 3. THE RESTORE TARGET NEEDS ITS OWN LICENCE. Without one,
#    `resolveRestoreLicense` (cmd/renet/backup_restore.go:360) falls back to the
#    FIRST installed licence carrying any renewalUrl, with no preference for one
#    covering the lineage being restored. On a machine holding licences from an
#    earlier session that is a DIFFERENT SUBSCRIPTION, and the restore dies on
#    `404 BACKUP_MANIFEST_MISSING` -- an error that names the manifest, not the
#    credential that was actually wrong. See docs/backup-storage/09-*.md.
#
# Prerequisites: worker VM at 192.168.111.11, docker on the host, a renet built
# from this tree already installed on the VM, and start-local-plane.sh running.
set -euo pipefail

VM="${VM:-192.168.111.11}"
BRIDGE_HOST="${BRIDGE_HOST:-192.168.111.254}"
GATEWAY_PORT="${GATEWAY_PORT:-4800}"
BASE="http://${BRIDGE_HOST}:${GATEWAY_PORT}/account/api/v1"
DATASTORE="${DATASTORE:-/mnt/rediacc}"
CELL_BYTES="${CELL_BYTES:-65536}"
WORK="${WORK:-/tmp/backup-roundtrip}"
SSH_OPTS=(-o BatchMode=yes -o StrictHostKeyChecking=no)

# Network ids are 2816 + n*64. 2816 belongs to whatever the fleet already had.
NET_SRC="${NET_SRC:-2880}"
NET_TGT="${NET_TGT:-2944}"

mkdir -p "$WORK"
FAILURES=0
step() { printf '\n=== %s ===\n' "$*"; }
check() {
    local label="$1" expected="$2" actual="$3"
    if [[ "$expected" == "$actual" ]]; then
        printf 'PASS  %s\n' "$label"
    else
        printf 'FAIL  %s\n        expected: %s\n        actual:   %s\n' "$label" "$expected" "$actual"
        FAILURES=$((FAILURES + 1))
    fi
}
vm() { timeout 900 ssh "${SSH_OPTS[@]}" "muhammed@${VM}" "$@"; }
jqp() { python3 -c "import sys,json;print(json.load(sys.stdin)$1)"; }

step "0. preflight"
curl -fsS -m 5 "http://${BRIDGE_HOST}:${GATEWAY_PORT}/health" >/dev/null ||
    {
        echo "no account gateway on ${BRIDGE_HOST}:${GATEWAY_PORT}; run start-local-plane.sh" >&2
        exit 1
    }
vm 'command -v renet >/dev/null' || {
    echo "renet missing on $VM" >&2
    exit 1
}

step "1. account, subscription, api token"
EMAIL="backup-roundtrip-$(date +%s)@rediacc.io"
PASS='RoundTrip123!'
JAR="$WORK/jar.txt"
curl -fsS -X POST "$BASE/test/ensure-login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" >/dev/null
SUB=$(curl -fsS -X POST "$BASE/test/ensure-subscription" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"planCode\":\"PROFESSIONAL\"}" | jqp "['subscriptionId']")
curl -fsS -c "$JAR" -X POST "$BASE/auth/login" -H 'Content-Type: application/json' \
    -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}" >/dev/null
TOKEN=$(curl -fsS -b "$JAR" -X POST "$BASE/api-tokens" -H 'Content-Type: application/json' \
    -d "{\"subscriptionId\":\"$SUB\",\"name\":\"roundtrip\",\"scopes\":[\"license:read\",\"license:activate\",\"subscription:read\",\"backup:read\",\"backup:manage\"]}" |
    jqp "['token']")
echo "subscription $SUB"

# issue_license <repo-guid> <grand-guid> <kind> -- mints server-side and installs
# the blob where renet reads it. The filename is the blob's own publicKeyId, so
# licences from different account universes coexist instead of clobbering.
issue_license() {
    local guid="$1" grand="$2" kind="$3"
    local machine_id client_id keyid
    machine_id=$(vm 'sudo -n renet machine-id' | tr -d '\r\n')
    client_id=$(cat /etc/machine-id)
    curl -fsS -X POST "$BASE/licenses/activate-repo" -H "Authorization: Bearer $TOKEN" \
        -H 'Content-Type: application/json' \
        -d "{\"machineId\":\"$machine_id\",\"clientMachineId\":\"$client_id\",\"repositoryGuid\":\"$guid\",\"grandGuid\":\"$grand\",\"kind\":\"$kind\",\"requestedSizeGb\":1}" |
        python3 -c "import sys,json;json.dump(json.load(sys.stdin)['license'],open('$WORK/lic.json','w'),indent=2)"
    keyid=$(jqp "['publicKeyId']" <"$WORK/lic.json")
    vm "cat > /tmp/rt-lic.json" <"$WORK/lic.json"
    vm "sudo -n mkdir -p /var/lib/rediacc/license/repos/$guid &&
        sudo -n cp /tmp/rt-lic.json /var/lib/rediacc/license/repos/$guid/$keyid.json &&
        sudo -n chmod 640 /var/lib/rediacc/license/repos/$guid/$keyid.json &&
        rm -f /tmp/rt-lic.json"
}

step "2. create a NEW repo and plant known content"
SRC=$(uuidgen)
openssl rand -base64 24 >"$WORK/luks.txt"
chmod 600 "$WORK/luks.txt"
vm "cat > /tmp/rt_pass.txt && chmod 600 /tmp/rt_pass.txt" <"$WORK/luks.txt"
vm "sudo -n sh -c 'cat /tmp/rt_pass.txt | renet repository create --name $SRC --network-id $NET_SRC --size 256M --password-stdin --output json'" >/dev/null
vm "sudo -n sh -c '
  echo \"marker: rediacc chunk-store round trip proof\" > $DATASTORE/mounts/$SRC/marker.txt
  head -c 8388608 /dev/urandom > $DATASTORE/mounts/$SRC/payload.bin
  mkdir -p $DATASTORE/mounts/$SRC/nested/dir
  printf \"nested content 1234567890\" > $DATASTORE/mounts/$SRC/nested/dir/deep.txt
  sync'"
issue_license "$SRC" "$SRC" grand
LIC_STATUS=$(vm "sudo -n renet repository license-status --output json" |
    python3 -c "import sys,json;print([r['status'] for r in json.load(sys.stdin) if r['repositoryGuid']=='$SRC'][0])")
check "source repo licence is valid" "valid" "$LIC_STATUS"

step "3. quiesce and record the source image digest"
vm "sudo -n renet repository down --name $SRC" >/dev/null 2>&1 || true
vm "sudo -n renet repository unmount --name $SRC" >/dev/null 2>&1
SRC_SHA=$(vm "sudo -n sh -c 'sync; sha256sum $DATASTORE/repositories/$SRC'" | awk '{print $1}')
echo "source image sha256: $SRC_SHA"

step "4. snapshot to the local S3"
vm "sudo -n renet backup snapshot --datastore $DATASTORE --repo $SRC --cell-bytes $CELL_BYTES" \
    >"$WORK/snap.out" 2>"$WORK/snap.err"
cat "$WORK/snap.out"
check "snapshot stored" "stored" "$(jqp "['status']" <"$WORK/snap.out")"
SNAP=$(jqp "['snapshotId']" <"$WORK/snap.out")
UPLOADED=$(jqp "['bytesUploaded']" <"$WORK/snap.out")

step "5. the manifest index lists it, and the quota ledger moved"
MANIFESTS=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/backups/manifests")
check "manifest index carries the snapshot" "$SNAP" \
    "$(echo "$MANIFESTS" | python3 -c "import sys,json;m=json.load(sys.stdin)['manifests'];print(m[0]['snapshotId'] if m else '')")"
USAGE=$(curl -fsS -H "Authorization: Bearer $TOKEN" "$BASE/backups/usage")
check "quota ledger equals bytes uploaded" "$UPLOADED" \
    "$(echo "$USAGE" | jqp "['storedBytes']")"

step "6. restore as a DIFFERENT repo"
TGT=$(uuidgen)
# The target's own licence. Skipping this is what makes resolveRestoreLicense
# reach for a stranger's; see the header.
issue_license "$TGT" "$SRC" fork
vm "sudo -n renet backup restore --datastore $DATASTORE --repo $TGT --lineage $SRC --at $SNAP" \
    >"$WORK/restore.out" 2>"$WORK/restore.err"
cat "$WORK/restore.out"
check "restore completed" "restored" "$(jqp "['status']" <"$WORK/restore.out")"

step "7. BYTE COMPARISON (the only step that proves anything)"
TGT_SHA=$(vm "sudo -n sh -c 'sha256sum $DATASTORE/repositories/$TGT'" | awk '{print $1}')
echo "source   $SRC_SHA"
echo "restored $TGT_SHA"
check "restored image is byte-identical to the source" "$SRC_SHA" "$TGT_SHA"
if vm "sudo -n cmp $DATASTORE/repositories/$SRC $DATASTORE/repositories/$TGT"; then
    echo "PASS  cmp reports the two images identical"
else
    echo "FAIL  cmp reports the two images differ"
    FAILURES=$((FAILURES + 1))
fi

# PROVE THE INSTRUMENT. A comparison that cannot fail is not evidence. Mutate one
# byte of the restored image and require the same cmp to notice.
step "8. control: the comparison can detect a difference"
vm "sudo -n sh -c 'printf \"\\x01\" | dd of=$DATASTORE/repositories/$TGT bs=1 seek=1048576 conv=notrunc status=none'"
if vm "sudo -n cmp -s $DATASTORE/repositories/$SRC $DATASTORE/repositories/$TGT"; then
    echo "FAIL  control did NOT fire: cmp still calls a mutated image identical"
    FAILURES=$((FAILURES + 1))
else
    echo "PASS  control fired: cmp detects the planted one-byte difference"
fi

step "9. teardown"
for g in "$SRC" "$TGT"; do
    vm "sudo -n renet repository unmount --name $g" >/dev/null 2>&1 || true
    vm "sudo -n renet repository delete --name $g --force" >/dev/null 2>&1 || true
    vm "sudo -n rm -rf /var/lib/rediacc/license/repos/$g" || true
done
vm "rm -f /tmp/rt_pass.txt" || true
echo "removed repos $SRC and $TGT and their licences"

printf '\n===== %s =====\n' "$([[ $FAILURES -eq 0 ]] && echo "ROUND TRIP PASSED" || echo "ROUND TRIP FAILED ($FAILURES)")"
exit "$FAILURES"
