#!/bin/bash
# Local proxy for .ci/scripts/infra/docker-prepull.sh, the third of the three CI
# scripts this wave found with no test of any kind.
#
# WHAT IT DOES IN CI. Several docker build jobs call it to pull their public
# base images up front, because buildx occasionally fails to authenticate when
# it pulls a base itself. It parses "<ref>[=<platform>]" arguments, retries each
# pull three times, and exits non-zero if any image is still unpulled. The
# argument grammar is the interesting part: `image="${spec%%=*}"` has to survive
# a ref that itself contains ':' and '/', and nothing checked that.
#
# WHAT THE PROXY RUNS. The real script, against docker, on the smallest public
# image there is (hello-world, a few kilobytes), in both argument shapes. If the
# image was not already present it is removed afterwards, so the proxy leaves
# the daemon exactly as it found it.
#
# THE FAILURE PATH IS DELIBERATELY NOT DRIVEN, and this is the reason rather
# than an omission: an unpullable ref costs three attempts with 30 s and 60 s
# sleeps between them, so proving it would add 90 s to a pre-push gate. The
# no-arguments refusal below proves the script can fail and costs nothing.
#
# CANNOT-RUN, not a verdict: no docker binary, no reachable daemon, or no
# reachable registry all exit 77. A developer on a train must not see this red.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

SUBJECT="$ROOT_DIR/.ci/rediacc_ci/infra/docker_prepull.py"
# ABSOLUTE, and set for both proxies alike: the subject imports `rediacc_ci`.
export PYTHONPATH="$ROOT_DIR/.ci"
IMAGE="hello-world:latest"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

proxy_init docker-prepull ".ci/rediacc_ci/infra/docker_prepull.py"

proxy_need_exec "$SUBJECT" "the subject script is missing from this checkout"
proxy_need_docker_daemon
proxy_need_url "https://registry-1.docker.io/v2/" "the subject pulls public base images from docker hub"
proxy_preflight

# Leave the daemon as we found it: only remove what this run introduced.
PREEXISTING=0
docker image inspect "$IMAGE" >/dev/null 2>&1 && PREEXISTING=1
cleanup() {
    if [[ $PREEXISTING -eq 0 ]]; then
        docker image rm -f "$IMAGE" >/dev/null 2>&1 || true
    fi
}
trap cleanup EXIT

# A script that pulls nothing when asked for nothing must SAY so, not exit 0
# over an empty loop. This is the cheap proof that the subject really ran.
proxy_expect_exit 1 "no arguments is refused, not treated as an empty success" -- python3 "$SUBJECT"
proxy_expect_contains "$PROXY_LAST_STDERR$PROXY_LAST_STDOUT" "Usage:" "the refusal prints its usage"

# Bare ref.
proxy_expect_exit 0 "a bare ref pulls" -- python3 "$SUBJECT" "$IMAGE"
proxy_expect_contains "$PROXY_LAST_STDERR$PROXY_LAST_STDOUT" "Pre-pulled 1 base image" "the bare-ref run reported the count it pulled"

if docker image inspect "$IMAGE" >/dev/null 2>&1; then
    proxy_pass "$IMAGE is present in the local daemon after the pull"
else
    proxy_fail "$IMAGE is absent after a run that exited 0; the subject reported success without pulling anything"
fi

# "<ref>=<platform>". The ref contains a ':' of its own, which is what makes the
# %%= / #*= split worth exercising rather than assuming.
proxy_expect_exit 0 "the <ref>=<platform> form pulls" -- python3 "$SUBJECT" "${IMAGE}=linux/amd64"
proxy_expect_contains "$PROXY_LAST_STDERR$PROXY_LAST_STDOUT" "Pre-pulled 1 base image" "the ref=platform run reported the count it pulled"

# Two specs in one call: the count in the closing line is $#, so a loop that
# silently dropped one would still say what it was handed. Assert the count and
# the image both.
proxy_expect_exit 0 "two specs in one call" -- python3 "$SUBJECT" "$IMAGE" "${IMAGE}=linux/amd64"
proxy_expect_contains "$PROXY_LAST_STDERR$PROXY_LAST_STDOUT" "Pre-pulled 2 base image" "the two-spec run reported 2"

proxy_finish
