#!/usr/bin/env bash
# Control for the `stable` field: a tree that MOVES during the run must record
# stable:false and warn. Without this the field can only ever say true, which is
# the vacuity failure this repo gates against.
#
# The mutation is an untracked file at the repo root, because dirtyDigest()
# hashes `git status --porcelain`, which lists untracked paths. It is created
# AFTER the run starts and removed only after the run ends -- a persistent
# change, which is the case two samples can actually see.
set -uo pipefail
cd "$(git rev-parse --show-toplevel)" || exit 1

# NO .tmp SUFFIX. .gitignore:73 ignores *.tmp, so such a file never reaches
# `git status`, the digest never moves, and this control reports success while
# measuring nothing -- which it did, twice, before the name was changed.
PROBE="STABILITY-PROBE-$$"
OUT="$(mktemp)"

npm run ci:quick -- --only check:ci-docker-image-freshness >"$OUT" 2>&1 &
RUN=$!

sleep 4
: >"$PROBE" # the tree moves, mid-run
echo "planted $PROBE at $(date -u +%H:%M:%SZ)"
echo "--- is the plant VISIBLE to git status? (must be 1) ---"
git status --porcelain | grep -c "STABILITY-PROBE"

wait $RUN
rm -f "$PROBE"

echo "--- did the run actually SELECT a gate? (0 here means the control was vacuous) ---"
grep -c "1 gate" "$OUT" || true
echo "--- warning present in output? ---"
grep -c 'working tree CHANGED' "$OUT"
echo "--- receipt ---"
python3 -c "
import json
r = json.load(open('.ci/cache/prepush-receipt.json'))
print('stable :', r.get('stable', 'FIELD ABSENT'))
"
echo "--- tree restored? (expect 0) ---"
git status --porcelain | grep -c 'STABILITY-PROBE' || true
