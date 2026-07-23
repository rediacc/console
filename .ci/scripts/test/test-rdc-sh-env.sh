#!/usr/bin/env bash
#
# Leak test for rdc.sh's dev path. Two layers:
#
#   Layer 1 (static): rdc.sh must never `source` (or `set -a` + source)
#     private/account/.env, and the only variables it exports must be the
#     allowlist {PATH, REDIACC_CONFIG, NODE_COMPILE_CACHE}. This is the
#     structural guarantee that the private ED25519/X25519/JWT/API secrets in
#     that env file cannot reach the CLI process.
#
#   Layer 2 (functional): run the real dev path against a fixture ROOT_DIR whose
#     private/account/.env carries the two public values PLUS sentinel secret
#     lines. node and curl are PATH-shimmed (node -e runs the real node for the
#     seeder; the cli-bundle invocation dumps its environment instead of
#     executing; curl's liveness probe always succeeds). We assert the dumped
#     CLI environment contains REDIACC_CONFIG=dev, contains none of the sentinel
#     secrets, and that the seeded dev.json got the right accountServer.
#
# Runs standalone: ./test-rdc-sh-env.sh

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../.." && pwd)"
RDC_SH="$REPO_ROOT/rdc.sh"

RED='\033[0;31m'
GREEN='\033[0;32m'
NC='\033[0m'

PASS=0
FAIL=0
fail() {
    FAIL=$((FAIL + 1))
    echo -e "  ${RED}✗${NC} $1" >&2
}
pass() {
    PASS=$((PASS + 1))
    echo -e "  ${GREEN}✓${NC} $1"
}

if [[ ! -f "$RDC_SH" ]]; then
    echo "FAIL: rdc.sh not found at $RDC_SH" >&2
    exit 1
fi

# ---------------------------------------------------------------------------
# Layer 1: static structural guarantees
# ---------------------------------------------------------------------------
echo "Layer 1 (static): rdc.sh export allowlist + no-source tombstone"

# 1a. No `set -a` command (comments referencing it in backticks don't count:
#     they never start a line after optional whitespace with `set -a`).
if grep -nE '^[[:space:]]*set[[:space:]]+-a([[:space:]]|$)' "$RDC_SH" >/dev/null; then
    fail "rdc.sh contains a 'set -a' statement (env-export leak vector)"
else
    pass "no 'set -a' statement"
fi

# 1b. No `source`/`.` of the account env file.
if grep -nE '(^[[:space:]]*(source|\.)[[:space:]]).*(account_env|private/account/\.env)' "$RDC_SH" >/dev/null; then
    fail "rdc.sh sources the account env file (secret leak vector)"
else
    pass "does not source private/account/.env"
fi

# 1c. Export allowlist: the set of exported variable names must equal
#     {PATH, REDIACC_CONFIG, NODE_COMPILE_CACHE}.
exported="$(grep -oE '^[[:space:]]*export[[:space:]]+[A-Za-z_][A-Za-z0-9_]*' "$RDC_SH" |
    awk '{print $2}' | sort -u | tr '\n' ' ' | sed 's/ $//')"
allowlist="NODE_COMPILE_CACHE PATH REDIACC_CONFIG"
if [[ "$exported" == "$allowlist" ]]; then
    pass "exports exactly the allowlist: $exported"
else
    fail "export set is [$exported]; expected [$allowlist]"
fi

# 1d. Positive/negative tombstones for the deleted leak surface.
grep -q 'export REDIACC_CONFIG=dev' "$RDC_SH" || fail "dev path must export REDIACC_CONFIG=dev"
for dead in REDIACC_SUBSCRIPTION_TOKEN_FILE REDIACC_ENVIRONMENT RDC_BENCH .rdc-dev .rdc-bench; do
    if grep -qF "$dead" "$RDC_SH"; then
        fail "rdc.sh still references removed token/mode surface: $dead"
    fi
done
pass "no removed token/mode surface (REDIACC_SUBSCRIPTION_TOKEN_FILE / REDIACC_ENVIRONMENT / RDC_BENCH / .rdc-{dev,bench})"

# ---------------------------------------------------------------------------
# Layer 2: functional — run the dev path in a fixture, capture the CLI env
# ---------------------------------------------------------------------------
echo "Layer 2 (functional): dev path seeds config, leaks no secrets"

REAL_NODE="$(command -v node)"
if [[ -z "$REAL_NODE" ]]; then
    echo "FAIL: node not found; cannot run functional layer" >&2
    exit 1
fi

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT

FIX_ROOT="$FIX/root"
FIX_HOME="$FIX/home"
SHIM="$FIX/shim"
DUMP="$FIX/cli-env.dump"
mkdir -p "$FIX_ROOT/.ci/config" "$FIX_ROOT/.ci/lib" \
    "$FIX_ROOT/private/account" "$FIX_ROOT/packages/cli/dist" \
    "$FIX_ROOT/.claude/skills/rdc" "$FIX_HOME" "$SHIM"

# Copy the REAL rdc.sh under test into the fixture (ROOT_DIR derives from its
# own location, so a copy exercises the same code against fixture siblings).
cp "$RDC_SH" "$FIX_ROOT/rdc.sh"

# Stub the sourced CI helpers so no real build machinery runs.
cat >"$FIX_ROOT/.ci/config/constants.sh" <<'EOF'
NODE_VERSION_MIN=18
EOF
cat >"$FIX_ROOT/.ci/lib/local-common.sh" <<'EOF'
log_info() { echo "INFO: $*" >&2; }
log_warn() { echo "WARN: $*" >&2; }
log_error() { echo "ERROR: $*" >&2; }
log_step() { echo "STEP: $*" >&2; }
check_node_version() { :; }
ensure_deps() { :; }
ensure_packages_built() { :; }
ensure_cli_built() { :; }
ensure_renet_built() { :; }
EOF

# Fixture env file: the two PUBLIC values the dev config needs, plus sentinel
# SECRET lines that must NEVER reach the CLI environment.
cat >"$FIX_ROOT/private/account/.env" <<'EOF'
REDIACC_ACCOUNT_SERVER=http://127.0.0.1:9
X25519_PUBLIC_KEY=stubpublickey
ED25519_PRIVATE_KEY=LEAKSENTINEL_ED25519
X25519_PRIVATE_KEY=LEAKSENTINEL_X25519
JWT_SECRET=LEAKSENTINEL_JWT
API_KEY=LEAKSENTINEL_API
EOF

# A stand-in for the compiled CLI bundle (node shim never actually runs it).
echo '// fixture bundle' >"$FIX_ROOT/packages/cli/dist/cli-bundle.cjs"
# Pre-seed the skill reference so rdc.sh's regen check is skipped (ref newer
# than the bundle -> no `npx tsx` invocation).
echo '# reference' >"$FIX_ROOT/.claude/skills/rdc/reference.md"
touch "$FIX_ROOT/.claude/skills/rdc/reference.md"

# node shim: `-e` (the seeder) runs the real node; anything else (the final
# `exec node cli-bundle.cjs`) dumps the environment and exits without running.
cat >"$SHIM/node" <<EOF
#!/usr/bin/env bash
if [[ "\${1:-}" == "-e" ]]; then
    exec "$REAL_NODE" "\$@"
fi
env >"$DUMP"
exit 0
EOF
chmod +x "$SHIM/node"

# curl shim: the dev liveness probe always succeeds (the fixture gateway is
# deliberately unreachable; we're testing the wrapper, not the network).
cat >"$SHIM/curl" <<'EOF'
#!/usr/bin/env bash
exit 0
EOF
chmod +x "$SHIM/curl"

# Run the dev path. Strip the sentinel/secret names from the harness env first,
# so any appearance of them in the dump can ONLY have come from a source leak.
env -i \
    PATH="$SHIM:/usr/bin:/bin" \
    HOME="$FIX_HOME" \
    bash "$FIX_ROOT/rdc.sh" --dev config current >"$FIX/run.out" 2>"$FIX/run.err" || {
    echo "dev path exited non-zero:" >&2
    cat "$FIX/run.err" >&2
    fail "rdc.sh --dev exited non-zero"
}

if [[ ! -f "$DUMP" ]]; then
    fail "CLI env dump not produced (dev path did not reach exec node)"
else
    grep -q '^REDIACC_CONFIG=dev$' "$DUMP" || fail "CLI env missing REDIACC_CONFIG=dev"
    if grep -q 'LEAKSENTINEL' "$DUMP"; then
        fail "SECRET LEAK: sentinel value reached the CLI environment: $(grep LEAKSENTINEL "$DUMP")"
    else
        pass "no sentinel secret value in CLI environment"
    fi
    for name in ED25519_PRIVATE_KEY X25519_PRIVATE_KEY JWT_SECRET API_KEY; do
        if grep -qE "^${name}=" "$DUMP"; then
            fail "SECRET LEAK: $name present in CLI environment"
        fi
    done
    grep -q '^REDIACC_CONFIG=dev$' "$DUMP" && pass "CLI environment carries REDIACC_CONFIG=dev only"
fi

# The seeder must have written the dev config with the fixture's server URL.
DEV_JSON="$FIX_HOME/.config/rediacc/dev.json"
if [[ ! -f "$DEV_JSON" ]]; then
    fail "seeder did not create $DEV_JSON"
else
    got_server="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['account']['accountServer'])" "$DEV_JSON" 2>/dev/null || echo PARSE_ERR)"
    got_key="$(python3 -c "import json,sys; print(json.load(open(sys.argv[1]))['account'].get('e2ePublicKey',''))" "$DEV_JSON" 2>/dev/null || echo PARSE_ERR)"
    [[ "$got_server" == "http://127.0.0.1:9" ]] || fail "dev.json accountServer=$got_server (expected http://127.0.0.1:9)"
    [[ "$got_key" == "stubpublickey" ]] || fail "dev.json e2ePublicKey=$got_key (expected stubpublickey)"
    [[ "$got_server" == "http://127.0.0.1:9" && "$got_key" == "stubpublickey" ]] &&
        pass "dev.json seeded with accountServer + e2ePublicKey from the env file"
fi

echo ""
echo "Passed: $PASS"
echo "Failed: $FAIL"
[[ "$FAIL" -gt 0 ]] && exit 1
exit 0
