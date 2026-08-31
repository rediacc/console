#!/usr/bin/env bash
# A script that INSTALLS a Go tool must be able to FIND it.
#
# WHY THIS EXISTS. `go install` writes to $(go env GOPATH)/bin, and nothing puts
# that directory on PATH. A script that installs a tool and then invokes it by
# bare name therefore reports a successful install and dies on the very next line
# with `command not found`, exit 127, taking its whole stage with it.
#
# Measured 2026-08-27 in private/renet: FOUR scripts did exactly this --
# quality/format.sh (goimports), quality/lint.sh (golangci-lint),
# quality/deadcode.sh (deadcode) and test/run-tests.sh (gotestsum). Patching the
# first only moved the failure to the second. `npm run check:ci-renet` exited 127
# about a second in, which also made its "fast" tier a measurement of crashing
# early rather than of running.
#
# AND IT IS INVISIBLE WHERE IT IS TESTED. CI never hits it, because
# actions/setup-go puts $(go env GOPATH)/bin on PATH itself. So the family is
# green in the one place nobody debugs and fatal in the one place people do,
# which is why it survived long enough to be four instances.
#
# THE SANCTIONED SHAPE, already used by this repo. .ci/scripts/lib/toolchain.sh
# installs with GOBIN pointed at a cache dir and then invokes the tool by
# ABSOLUTE path. That needs no PATH at all and is why check:ci-shell-format
# passes on a host with no shfmt anywhere on PATH. Any of these satisfy the gate:
#
#   GOBIN="$dir" go install ...   then run "$dir/tool"     (preferred)
#   PATH="$(go env GOPATH)/bin:$PATH"  before the invocation
#   invoke via an absolute or $-prefixed path rather than a bare name
#
# SCOPE. Tracked shell scripts under .ci/ and scripts/. The submodule has its own
# CI and its own copy of this problem, already fixed at its root in
# .ci/scripts/lib/common.sh; this gate keeps console from growing a fifth.
set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$ROOT" || exit 1

FAIL=0
pass() { printf 'ok   %s\n' "$1"; }
fail() {
    printf '\033[0;31m✗\033[0m   %s\n' "$1"
    FAIL=$((FAIL + 1))
}

# Tools commonly provisioned with `go install`. A bare invocation of one of these
# in a script that also installs it is the defect.
GO_TOOLS='goimports|golangci-lint|govulncheck|gotestsum|deadcode|staticcheck|shfmt|gopls|mockgen'

# --- the scan ----------------------------------------------------------------
#
# A file is a finding when it BOTH installs a go tool AND invokes one by bare
# name, with no PATH extension and no GOBIN indirection anywhere in the file.
# Deliberately per-FILE rather than per-line: the install and the invocation are
# usually several lines apart, and a PATH fix anywhere above the call site is
# what actually makes it work.
scan_file() {
    local f="$1" body
    body="$(cat "$f" 2>/dev/null)" || return 0

    # Does it provision a go tool at all?
    grep -qE '(^|[[:space:];&|])go[[:space:]]+install[[:space:]]' <<<"$body" || return 0

    # An explicit GOBIN, or a PATH that includes GOPATH/bin, is the fix. Either
    # anywhere in the file clears it -- see the per-FILE note above.
    if grep -qE 'GOBIN=|go env GOPATH.*bin|GOPATH_BIN|_go_bin' <<<"$body"; then
        return 0
    fi

    # Now: is any go tool invoked by BARE name? A path-qualified call ($x/tool,
    # ./tool, /usr/bin/tool, "$VAR") already resolves without PATH, and a mention
    # inside a string or comment is not an invocation.
    local hits
    hits="$(printf '%s' "$body" |
        grep -vE '^[[:space:]]*#' |
        grep -nE "(^|[[:space:];&|(]|\\\$\\()[[:space:]]*($GO_TOOLS)[[:space:]]" |
        grep -vE "[/\"'\$]($GO_TOOLS)" || true)"

    [ -z "$hits" ] && return 0
    fail "$f installs a go tool and then invokes one by bare name, with no GOBIN and no GOPATH/bin on PATH:"
    printf '%s\n' "$hits" | head -3 | sed 's/^/         /'
    printf '         FIX: GOBIN="$dir" go install ... then run "$dir/tool", the shape .ci/scripts/lib/toolchain.sh uses.\n'
}

FILES="$(git ls-files '.ci/**/*.sh' 'scripts/**/*.sh' 2>/dev/null)"
COUNT="$(printf '%s\n' "$FILES" | grep -c . || true)"

# ANTI-VACUITY FLOOR. A glob that silently matches nothing would make this gate
# green forever while checking not one line. Verified against the tracked list,
# not the filesystem, so a stray untracked file cannot prop the number up.
if [ "$COUNT" -lt 50 ]; then
    fail "only $COUNT shell file(s) in scope -- the scan is not reaching the tree, so a green here would mean nothing"
else
    pass "scope: $COUNT tracked shell file(s) under .ci/ and scripts/"
fi

while IFS= read -r f; do
    [ -n "$f" ] || continue
    scan_file "$f"
done <<<"$FILES"

# --- controls: the gate must be able to FIRE, and must not fire on the fix ----
#
# Run against fixtures in a scratch dir, because the live tree is expected to be
# clean and a gate proven only on a clean tree has proven nothing.
CTL="$(mktemp -d)"
trap 'rm -rf "$CTL"' EXIT

cat >"$CTL/bad.sh" <<'EOF'
#!/usr/bin/env bash
go install golang.org/x/tools/cmd/goimports@latest
unformatted=$(goimports -l .)
EOF

cat >"$CTL/good-gobin.sh" <<'EOF'
#!/usr/bin/env bash
GOBIN="$cache" go install golang.org/x/tools/cmd/goimports@latest
unformatted=$("$cache/goimports" -l .)
EOF

cat >"$CTL/good-path.sh" <<'EOF'
#!/usr/bin/env bash
PATH="$(go env GOPATH)/bin:$PATH"
go install golang.org/x/tools/cmd/goimports@latest
unformatted=$(goimports -l .)
EOF

cat >"$CTL/unrelated.sh" <<'EOF'
#!/usr/bin/env bash
echo "this script mentions goimports in prose and installs nothing"
EOF

ctl() {
    local file="$1" want="$2" label="$3" before="$FAIL"
    scan_file "$file" >/dev/null 2>&1
    local fired=$((FAIL - before))
    FAIL="$before" # a control must never colour the real verdict
    if [ "$want" = fire ] && [ "$fired" -eq 0 ]; then
        fail "CONTROL FAILED: $label -- the gate could not fire, so its green means nothing"
    elif [ "$want" = silent ] && [ "$fired" -ne 0 ]; then
        fail "CONTROL FAILED: $label -- the gate fires on the CORRECT shape"
    else
        pass "control: $label"
    fi
}

ctl "$CTL/bad.sh" fire "install-then-bare-invoke is detected"
ctl "$CTL/good-gobin.sh" silent "GOBIN plus an absolute path is not flagged"
ctl "$CTL/good-path.sh" silent "extending PATH with GOPATH/bin is not flagged"
ctl "$CTL/unrelated.sh" silent "a script that only MENTIONS a tool is not flagged"

if [ "$FAIL" -eq 0 ]; then
    printf '\033[0;32m✓\033[0m go tool PATH: every script that installs a go tool can find it.\n'
    exit 0
fi
printf '\033[0;31m✗\033[0m %d finding(s).\n' "$FAIL"
exit 1
