#!/usr/bin/env bash
# Controls for .ci/scripts/lib/toolchain.sh.
#
# The hazard this file exists for: every tool prints its version differently, so
# the normaliser is per-tool and fragile. A normaliser that silently returns ""
# makes toolchain_check compare "" against "" and PASS -- vacuity inside the
# check whose whole job is preventing it. So every probe assertion is paired
# with a garbage-output control, and every match assertion with a mismatch.
#
# Fake binaries are built by CONSTRUCTION in a temp PATH, never by mutating a
# real tool, so a reworded real --version cannot void these.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
# shellcheck source=/dev/null
. "$ROOT/.ci/scripts/lib/toolchain.sh"

fails=0
count=0
ok() {
    count=$((count + 1))
    echo "PASS: $1"
}
no() {
    count=$((count + 1))
    fails=$((fails + 1))
    echo "FAIL: $1" >&2
}
check() { # check <label> <actual> <want>
    if [[ "$2" == "$3" ]]; then
        ok "$1"
    else
        no "$1 (got '$2', want '$3')"
    fi
}

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
mkdir -p "$TMP/bin"

fake() { # fake <name> <stdout>
    printf '#!/usr/bin/env bash\ncat <<'\''OUT'\''\n%s\nOUT\n' "$2" >"$TMP/bin/$1"
    chmod +x "$TMP/bin/$1"
}

toolchain_load || {
    echo "cannot load pins" >&2
    exit 1
}

# --- 1. every real-world --version shape parses to a bare version -------------
fake shfmt 'v3.13.1'
check "shfmt: a leading v is stripped" "$(PATH="$TMP/bin:$PATH" toolchain_probe_version shfmt "$TMP/bin/shfmt")" "3.13.1"

fake shellcheck 'ShellCheck - shell script analysis tool
version: 0.10.0
license: GNU General Public License, version 3'
check "shellcheck: read from a multi-line banner" "$(toolchain_probe_version shellcheck "$TMP/bin/shellcheck")" "0.10.0"

fake ruff 'ruff 0.16.1'
check "ruff: second field" "$(toolchain_probe_version ruff "$TMP/bin/ruff")" "0.16.1"

fake actionlint '1.7.12'
check "actionlint: bare version" "$(toolchain_probe_version actionlint "$TMP/bin/actionlint")" "1.7.12"

fake go 'go version go1.26.4 linux/arm64'
check "go: 'go' prefix stripped, arch dropped" "$(toolchain_probe_version go "$TMP/bin/go")" "1.26.4"

fake node 'v22.23.2'
check "node: leading v stripped" "$(toolchain_probe_version node "$TMP/bin/node")" "22.23.2"

# --- 2. THE PAIRS. Garbage must FAIL, never yield "" --------------------------
fake shfmt 'command not found: shfmt'
if toolchain_probe_version shfmt "$TMP/bin/shfmt" >/dev/null 2>&1; then
    no "CONTROL: unparseable output must not yield a version"
else
    ok "CONTROL: unparseable output fails instead of returning empty"
fi

fake shfmt ''
if toolchain_probe_version shfmt "$TMP/bin/shfmt" >/dev/null 2>&1; then
    no "CONTROL: empty output must not yield a version"
else
    ok "CONTROL: empty output fails instead of returning empty"
fi

# --- 3. toolchain_check: match, mismatch, absent ------------------------------
fake shfmt "v${SHFMT_VERSION}"
if PATH="$TMP/bin:$PATH" toolchain_check shfmt >/dev/null 2>&1; then
    ok "a PATH binary AT the pin is accepted"
else
    no "a PATH binary at the pin was rejected"
fi

fake shfmt 'v0.0.1'
if PATH="$TMP/bin:$PATH" toolchain_check shfmt >/dev/null 2>&1; then
    no "CONTROL: a WRONG version on PATH was accepted -- the pin is decorative"
else
    ok "CONTROL: a wrong version on PATH is rejected"
fi

if PATH="$TMP/empty" toolchain_check shfmt >/dev/null 2>&1; then
    no "CONTROL: an absent tool was accepted"
else
    ok "CONTROL: an absent tool is rejected"
fi

# node compares MAJOR only; both directions.
fake node 'v22.99.0'
if PATH="$TMP/bin:$PATH" toolchain_check node >/dev/null 2>&1; then
    ok "node: a different patch inside the pinned major is accepted"
else
    no "node: same major was rejected"
fi
fake node 'v24.14.0'
if PATH="$TMP/bin:$PATH" toolchain_check node >/dev/null 2>&1; then
    no "CONTROL: a different node MAJOR was accepted"
else
    ok "CONTROL: a different node major is rejected"
fi

# --- 4. the pins file itself --------------------------------------------------
n="$(toolchain_keys | wc -l | tr -d ' ')"
if [[ "$n" -ge 7 ]]; then
    ok "pins file defines $n keys"
else
    no "pins file defines only $n keys -- a shrinking file must not read as clean"
fi
if toolchain_pairs | grep -qvE '^[A-Z][A-Z0-9_]*=[^ ]*$'; then
    no "CONTROL: --env emitted a line \$GITHUB_ENV would reject"
else
    ok "CONTROL: every --env line is KEY=value, safe for \$GITHUB_ENV"
fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "✓ toolchain: $count control(s) passed"
    exit 0
fi
echo "✗ toolchain: $fails of $count control(s) failed" >&2
exit 1
