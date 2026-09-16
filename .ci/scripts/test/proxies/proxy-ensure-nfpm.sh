#!/bin/bash
# Local proxy for .ci/scripts/build/ensure-nfpm.sh, the second of the three CI
# scripts this wave found with no test of any kind.
#
# WHAT IT GUARDS IN CI. Two workflows install nfpm through it (ci.yml's
# "Install packaging tools" step and cd-stage.yml), and it is the ONLY place the
# pinned version and its sha256 are enforced. Its own header records that the
# six lines it replaced had already drifted once, so the checksum was verified
# on one of two installs and not the other. That makes it exactly the kind of
# script whose silence is expensive: it can fetch the wrong version, or skip the
# verification, and every downstream package still builds.
#
# IT RUNS AGAINST A THROWAWAY REPO ROOT, NOT THIS ONE.
# The subject computes BIN_DIR from its own location as <root>/.ci/cache/bin, so
# running it in this checkout would hit the warm cache, take the early-exit
# branch, and never touch the download or the checksum at all -- a green that
# proves only that a file already existed. The proxy therefore builds a minimal
# fixture root holding the script, .ci/scripts/lib, .ci/config/constants.sh and
# .devcontainer/toolchain.env, and runs it there with a COLD cache. That is the
# only way the fetch-and-verify path is reachable without deleting a cache this
# proxy does not own.
#
# BOTH DIRECTIONS:
#   MUST SUCCEED  cold cache -> downloads, verifies the pinned sha256, prints a
#                 directory holding an nfpm whose --version equals NFPM_VERSION
#   MUST SUCCEED  a second call is idempotent and downloads nothing
#   MUST REFUSE   an architecture with no pinned checksum exits 1 and names
#                 .ci/config/constants.sh instead of downloading unverified bytes
#
# The refusal case is driven with a `uname` shim on PATH, which is a real
# execution of the branch rather than a claim about it.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT_REL=".ci/scripts/build/ensure-nfpm.sh"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init ensure-nfpm ".ci/scripts/build/ensure-nfpm.sh"

proxy_need_exec "$ROOT_DIR/$SUBJECT_REL" "the subject script is missing from this checkout"
proxy_need_file "$ROOT_DIR/.ci/config/constants.sh" "the pin site is missing from this checkout"
proxy_need_file "$ROOT_DIR/.devcontainer/toolchain.env" "constants.sh sources this; the checkout is incomplete"
proxy_need_cmd curl "sudo apt-get install -y curl"
proxy_need_cmd sha256sum "sudo apt-get install -y coreutils"
proxy_need_cmd tar "sudo apt-get install -y tar"
proxy_need_url "https://github.com" "the subject fetches the pinned tarball from github releases"
proxy_preflight

# The pin, read from the one place that holds it.
PINNED_VERSION="$(
    # shellcheck disable=SC1090
    source "$ROOT_DIR/.ci/config/constants.sh" >/dev/null 2>&1
    printf '%s' "${NFPM_VERSION:-}"
)"
if [[ -z "$PINNED_VERSION" ]]; then
    echo "${PROXY_RED}proxy ensure-nfpm: could not read NFPM_VERSION out of .ci/config/constants.sh${PROXY_OFF}" >&2
    echo "  Every comparison below would then be against an empty string, which matches" >&2
    echo "  nothing and would report a false failure, or worse a false pass." >&2
    exit 1
fi
proxy_pass "read the pin from .ci/config/constants.sh: NFPM_VERSION=$PINNED_VERSION"

FIX="$(mktemp -d)"
trap 'rm -rf "$FIX"' EXIT
mkdir -p "$FIX/.ci/scripts/build" "$FIX/.ci/config" "$FIX/.devcontainer"
cp "$ROOT_DIR/$SUBJECT_REL" "$FIX/$SUBJECT_REL"
cp -r "$ROOT_DIR/.ci/scripts/lib" "$FIX/.ci/scripts/lib"
cp "$ROOT_DIR/.ci/config/constants.sh" "$FIX/.ci/config/constants.sh"
cp "$ROOT_DIR/.devcontainer/toolchain.env" "$FIX/.devcontainer/toolchain.env"
chmod +x "$FIX/$SUBJECT_REL"

# A PATH with no nfpm on it, so the subject cannot take its `command -v nfpm`
# early exit and really has to fetch.
CLEAN_PATH="$PATH"
if command -v nfpm >/dev/null 2>&1; then
    NFPM_HOME="$(dirname "$(command -v nfpm)")"
    CLEAN_PATH="$(printf '%s' "$PATH" | tr ':' '\n' | grep -vxF "$NFPM_HOME" | paste -sd: -)"
fi

SO="$(mktemp)"
SE="$(mktemp)"

set +e
PRINTED_DIR="$(PATH="$CLEAN_PATH" "$FIX/$SUBJECT_REL" 2>"$SE")"
RC=$?
set -e

if [[ $RC -eq 0 ]]; then
    proxy_pass "cold-cache run exited 0"
else
    proxy_fail "cold-cache run exited $RC"
    echo "  --- stderr ---" >&2
    cat "$SE" >&2
fi

if [[ -n "$PRINTED_DIR" && -d "$PRINTED_DIR" ]]; then
    proxy_pass "it printed a directory that exists: ${PRINTED_DIR#"$FIX"/}"
else
    proxy_fail "it printed '$PRINTED_DIR', which is not a directory; every caller does PATH=\"\$(ensure-nfpm.sh):\$PATH\" and would silently get nothing"
fi

if [[ -x "$PRINTED_DIR/nfpm" ]]; then
    proxy_pass "the printed directory holds an executable nfpm"
    GOT_VERSION="$("$PRINTED_DIR/nfpm" --version 2>&1 | grep -oE '[0-9]+\.[0-9]+\.[0-9]+' | head -1)"
    if [[ "$GOT_VERSION" == "$PINNED_VERSION" ]]; then
        proxy_pass "the installed nfpm reports $GOT_VERSION, exactly the pin"
    else
        proxy_fail "the installed nfpm reports '$GOT_VERSION' but the pin is '$PINNED_VERSION'; the download and the pin site have drifted apart"
    fi
    # The fetch really went through `sha256sum -c`: on a mismatch the subject
    # aborts before extracting, so the presence of a working binary from a cold
    # cache is the checksum path having passed.
    if grep -q 'fetching nfpm' "$SE"; then
        proxy_pass "the cold-cache run really fetched and verified (its 'fetching nfpm' line is present), so the checksum branch was exercised, not skipped"
    else
        proxy_fail "the run produced a binary without printing its 'fetching nfpm' line; the fixture cache was not cold and the download plus checksum path went unexercised"
    fi
else
    proxy_fail "no executable nfpm at $PRINTED_DIR/nfpm"
fi

# IDEMPOTENCE. Every caller invokes this on every run; a second call that
# re-downloads would add a network round trip to every package build.
set +e
SECOND="$(PATH="$CLEAN_PATH" "$FIX/$SUBJECT_REL" 2>"$SO")"
RC2=$?
set -e
if [[ $RC2 -eq 0 && "$SECOND" == "$PRINTED_DIR" ]]; then
    if grep -q 'fetching nfpm' "$SO"; then
        proxy_fail "the second call downloaded again; the subject claims to be idempotent and is not"
    else
        proxy_pass "the second call is idempotent: same directory, no fetch"
    fi
else
    proxy_fail "the second call exited $RC2 and printed '$SECOND' (expected 0 and '$PRINTED_DIR')"
fi

# THE REFUSAL BRANCH, driven for real with a uname shim. An arch with no pinned
# checksum must abort rather than download bytes nothing verifies.
SHIM="$(mktemp -d)"
cat >"$SHIM/uname" <<'SHIMEOF'
#!/bin/bash
for a in "$@"; do [[ "$a" == "-m" ]] && { echo riscv64; exit 0; }; done
exec /usr/bin/uname "$@"
SHIMEOF
chmod +x "$SHIM/uname"
rm -rf "${FIX:?}/.ci/cache"
set +e
REFUSE_OUT="$(PATH="$SHIM:$CLEAN_PATH" "$FIX/$SUBJECT_REL" 2>&1)"
RC3=$?
set -e
rm -rf "$SHIM"
if [[ $RC3 -ne 0 ]]; then
    proxy_pass "an unpinned architecture is refused (exit $RC3), not downloaded unverified"
else
    proxy_fail "an unpinned architecture was NOT refused; the subject exited 0 and would install bytes no checksum covers"
fi
proxy_expect_contains "$REFUSE_OUT" "constants.sh" "the refusal names the pin site so the fix is in the message"

rm -f "$SO" "$SE"
proxy_finish
