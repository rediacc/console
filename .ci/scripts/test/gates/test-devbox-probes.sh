#!/usr/bin/env bash
# Controls for devbox_exec and the three usability probes.
#
# WHY THESE MATTER MORE THAN MOST. All three failure modes present IDENTICALLY:
# a gate that exits 0 having read nothing. An empty bind mount (macOS outside
# Docker Desktop's sharing list, WSL2 via Desktop integration) auto-creates the
# directory, so the path EXISTS and the tree is empty. A root exec makes git
# refuse the worktree, so `git ls-files` returns nothing. A read-only mount lets
# reads succeed and writes fail late. In each case the honest-looking answer is
# a green.
#
# So each probe is asserted in BOTH directions against fixtures built by
# CONSTRUCTION -- fake `docker` binaries on a temp PATH, never the real daemon --
# which also keeps this test hermetic and runnable where no devbox exists.

set -uo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"

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

TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

# A stand-in for the whole library surface the probes touch, so the fixtures
# decide what "the container" answers.
harness() { # harness <docker-behaviour-script>
    cat >"$TMP/lib.sh" <<'LIB'
log_error() { echo "error: $*" >&2; }
log_info()  { echo "info: $*"; }
devbox_docker() { printf '%s' "$FAKE_DOCKER"; }
devbox_container_id() { printf 'cid0'; }
devbox_container_running() { return 0; }
devbox_worktree() { printf '%s' "$WT"; }
devbox_mount_root() { printf '%s' "$WT"; }
LIB
    # shellcheck disable=SC1090
    . "$TMP/lib.sh"
    # the probe bodies, lifted from the real library so this cannot drift
    eval "$(sed -n '/^devbox_exec() {/,/^}/p;/^devbox_mount_ok() {/,/^}/p;/^devbox_identity_ok() {/,/^}/p;/^devbox_writable_ok() {/,/^}/p' "$ROOT/.ci/lib/devbox.sh")"
}

fake_docker() { # fake_docker <exit-code> <stdout>
    cat >"$TMP/docker" <<EOF
#!/usr/bin/env bash
printf '%s' "\$*" >> "$TMP/calls"
cat <<'OUT'
$2
OUT
exit $1
EOF
    chmod +x "$TMP/docker"
    FAKE_DOCKER="$TMP/docker"
}

WT="$TMP/wt"
mkdir -p "$WT/.ci/cache"
: >"$WT/run.sh"
export WT FAKE_DOCKER

# --- mount probe --------------------------------------------------------------
fake_docker 0 ".git"
harness
if devbox_mount_ok 2>/dev/null; then ok "mount: a container that finds the repo passes"; else no "mount: a healthy mount was rejected"; fi

fake_docker 1 ""
harness
if devbox_mount_ok 2>/dev/null; then no "CONTROL: an EMPTY mount passed -- the vacuous-green case is undetected"; else ok "CONTROL: an empty/absent mount is refused"; fi

# --- identity probe -----------------------------------------------------------
fake_docker 0 ""
harness
if devbox_identity_ok 2>/dev/null; then ok "identity: a clean git status passes"; else no "identity: a healthy identity was rejected"; fi

fake_docker 0 "fatal: detected dubious ownership in repository at '/x'"
harness
if devbox_identity_ok 2>/dev/null; then no "CONTROL: a root exec (dubious ownership) passed"; else ok "CONTROL: dubious ownership is refused"; fi

# --- writable probe -----------------------------------------------------------
fake_docker 0 ""
harness
if devbox_writable_ok 2>/dev/null; then ok "writable: a writable mount passes"; else no "writable: a writable mount was rejected"; fi

fake_docker 1 "touch: Read-only file system"
harness
if devbox_writable_ok 2>/dev/null; then no "CONTROL: a READ-ONLY mount passed"; else ok "CONTROL: a read-only mount is refused"; fi

# --- exec shape ---------------------------------------------------------------
# -u vscode BY NAME: a numeric id is only correct where the host's numbering is
# meaningful, which macOS breaks (501:20, gid 20 = dialout in the image).
if grep -q -- '-u vscode' "$ROOT/.ci/lib/devbox.sh"; then
    ok "exec: runs as 'vscode' by name, not a numeric uid"
else
    no "exec: does not pin the user by name"
fi
if grep -q 'bash -lc' "$ROOT/.ci/lib/devbox.sh"; then
    ok "exec: uses a LOGIN shell, so /etc/environment supplies go and node on PATH"
else
    no "exec: not a login shell; go/node would be missing from PATH"
fi

echo
if [[ "$fails" -eq 0 ]]; then
    echo "✓ devbox probes: $count control(s) passed"
    exit 0
fi
echo "✗ devbox probes: $fails of $count control(s) failed" >&2
exit 1
