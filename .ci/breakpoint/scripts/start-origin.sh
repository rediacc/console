#!/bin/bash
# Bring up the local origin the tunnel points at, and guarantee /health answers.
#
# WHY THIS EXISTS AT ALL: the deleted standalone-run.yml never started any
# services. `grep -n "docker compose\|ci-start" standalone-run.yml` on the
# recovered file finds only the desktop gateway overlay -- ci-start.sh is never
# invoked -- yet the hold loop curled http://localhost/health and the tunnel
# gated its own success on the same endpoint. So the tunnel step could not
# succeed even in principle: it burned three 60s attempts per matrix leg and
# `|| true` swallowed the failure. Three CI legs per PR, every PR, for months.
#
# The fix is not "call ci-start.sh somewhere". It is to make the origin an
# explicit, checked step that FAILS LOUDLY when the thing behind it is not
# serving, which is what this script is.
#
# ONE ORIGIN PORT, ALWAYS. Everything the tunnel fronts is reachable on
# --port (default 8080), so start-tunnel.sh's --origin is a constant and there
# is no branch anywhere on "which port is it this time".
#
# TWO KINDS OF ORIGIN
#
#   static  -- a python3 http.server over a directory containing a `health`
#              file. Zero install, present on every runner including
#              ubuntu-slim, no Docker. This is what the per-CI-round lifecycle
#              leg uses, and why that leg can run on slim at all.
#
#   gateway -- Caddy, path-multiplexing ONE hostname across the application
#              (:80), the noVNC desktop (:6080) and anything added later.
#              Needs Docker, which the session job has (ubuntu-latest) and the
#              slim CI leg does not need because it runs --desktop none.
#
# The kind is INFERRED, not asked for: a session with a desktop or services
# needs multiplexing, a bare tunnel does not. --kind overrides when you want to
# force one.
#
# WHY MULTIPLEXING IS REQUIRED AND NOT A NICETY: a quick tunnel gives you
# exactly ONE hostname. Without a gateway you must choose between tunnelling the
# app and tunnelling the desktop. The first cut of this script shipped only the
# static kind, which left the desktop reachable solely at localhost:6080 -- i.e.
# only from the runner itself, which is precisely the machine you cannot reach.
#
# Usage:
#   start-origin.sh [--port 8080] [--services none|core|full] [--desktop none|xfce]
#                   [--kind auto|static|gateway]
# Stdout: the origin URL (http://localhost:PORT). Nothing else.
# Exit:   0 ok, 1 origin never answered, 4 bad arguments.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=../lib/breakpoint-common.sh
source "$SCRIPT_DIR/../lib/breakpoint-common.sh"
# shellcheck source=../versions.sh
source "$(bp_root "$SCRIPT_DIR")/versions.sh"

parse_args "$@"

PORT="${ARG_PORT:-8080}"
SERVICES="${ARG_SERVICES:-none}"
DESKTOP="${ARG_DESKTOP:-none}"
KIND="${ARG_KIND:-auto}"

STATE_DIR="$(bp_state_dir)"
DOC_ROOT="$STATE_DIR/origin"
mkdir -p "$DOC_ROOT"

bp_state_set BP_SERVICES "$SERVICES"
bp_state_set BP_DESKTOP "$DESKTOP"

# -----------------------------------------------------------------------------
# Optional: bring up the repo's service stack.
# -----------------------------------------------------------------------------
# Called explicitly, unlike the old workflow. GITHUB_WORKSPACE is the repo root
# under Actions; pwd is the fallback so this works from a laptop.
REPO_ROOT="${GITHUB_WORKSPACE:-$(pwd)}"

if [[ "$SERVICES" != "none" ]]; then
    if [[ -x "$REPO_ROOT/.ci/scripts/infra/ci-start.sh" ]]; then
        log_step "starting services ($SERVICES) via ci-start.sh..."
        # `>&2` IS LOAD-BEARING, not tidiness. This script's stdout contract is
        # "exactly one line, the origin URL", and the caller does
        # `URL=$(start-origin.sh ...)`. ci-start.sh sources ci-env.sh, which
        # prints `::add-mask::<secret>` lines to STDOUT (ci-env.sh:94-100) to
        # register its generated ephemeral keys with the runner. Without this
        # redirect those lines were swallowed into $URL, producing a multi-line
        # value that killed the step with:
        #     Unable to process file command 'output' successfully.
        #     Invalid format 'MC4CAQAwBQYDK2VwBCIEID...'
        # -- and, worse, the mask directives never reached the runner at all,
        # so the very keys they were meant to hide got echoed into the log by
        # the error message. Anything this script calls must send its chatter to
        # stderr; only the URL may touch stdout.
        if ! "$REPO_ROOT/.ci/scripts/infra/ci-start.sh" >&2; then
            # FAIL. The operator asked for --services "$SERVICES"; delivering a
            # box whose app is silently absent is how you end up opening the
            # tunnel and getting "bad gateway" with nothing explaining why.
            # Pass hold-on-failure to keep the box alive for inspection.
            log_error "ci-start.sh FAILED -- --services $SERVICES cannot be delivered"
            log_error "refusing to hand over a session that is missing what was asked for"
            log_error "re-dispatch with services: none, or with hold-on-failure to debug this boot"
            exit 1
        fi
    else
        # Absent script = a repo that vendored breakpoint without console's
        # infra tree. Still a failure: --services was explicitly requested and
        # cannot be honoured here. The correct dispatch for such a repo is
        # services: none.
        log_error "--services $SERVICES requested but $REPO_ROOT/.ci/scripts/infra/ci-start.sh does not exist"
        log_error "this repo cannot start services; dispatch with services: none"
        exit 1
    fi
fi

if [[ "$DESKTOP" != "none" ]]; then
    log_step "starting desktop ($DESKTOP)..."
    # Same stdout discipline as ci-start.sh above: nothing but the URL may
    # reach this script's stdout.
    if ! "$SCRIPT_DIR/desktop-ctl.sh" start --resolution "${DESKTOP_RESOLUTION:-1600x900}" >&2; then
        log_error "desktop ($DESKTOP) FAILED to start -- refusing to hand over a session without it"
        exit 1
    fi
fi

# -----------------------------------------------------------------------------
# Choose the origin kind.
# -----------------------------------------------------------------------------
# Anything that needs path routing implies a gateway. A bare tunnel does not.
if [[ "$KIND" == "auto" ]]; then
    if [[ "$DESKTOP" != "none" ]] || [[ "$SERVICES" != "none" ]]; then
        KIND="gateway"
    else
        KIND="static"
    fi
    log_debug "origin kind inferred as '$KIND' (desktop=$DESKTOP services=$SERVICES)"
fi

if [[ "$KIND" == "gateway" ]] && ! command -v docker >/dev/null 2>&1; then
    # FAIL, do not degrade. A silent downgrade to the static origin produces a
    # session where /desktop 404s and the app is unreachable, and the operator
    # discovers it minutes later by opening the URL. Fallbacks hide; a dead
    # session that says why is worth more than a live one that lies.
    # `hold-on-failure: true` is the sanctioned way to keep a failed boot open
    # for inspection.
    log_error "--kind gateway needs docker, and docker is not available on this runner"
    log_error "without the gateway there is no path routing: /desktop and the app would both be unreachable"
    exit 1
fi

bp_state_set BP_ORIGIN_KIND "$KIND"

# -----------------------------------------------------------------------------
# GATEWAY: Caddy, path-multiplexing one hostname. See docker/Caddyfile.
# -----------------------------------------------------------------------------
start_gateway() {
    local caddyfile container
    caddyfile="$(bp_root "$SCRIPT_DIR")/docker/Caddyfile"
    container="breakpoint-gateway-${GITHUB_RUN_ID:-local}"

    require_file "$caddyfile"

    # Named per run, so two sessions on one machine cannot collide and teardown
    # never needs to guess which container is ours.
    bp_state_set BP_GATEWAY_CONTAINER "$container"

    # --network host is load-bearing: the desktop stack runs directly ON THE
    # RUNNER, not in a container, so localhost:6080 only resolves for a
    # container sharing the host network namespace.
    #
    # The image is pinned BY DIGEST (versions.sh), not by the `caddy:alpine`
    # tag the deleted overlay used, so the bytes are the ones that were reviewed.
    log_step "starting Caddy gateway on :${PORT} (image pinned by digest)..."
    if ! docker run -d --rm \
        --name "$container" \
        --network host \
        -v "${caddyfile}:/etc/caddy/Caddyfile:ro" \
        "$BREAKPOINT_CADDY_IMAGE" >"$STATE_DIR/gateway.cid" 2>"$STATE_DIR/gateway.log"; then
        log_error "failed to start the Caddy gateway"
        cat "$STATE_DIR/gateway.log" >&2 2>/dev/null || true
        return 1
    fi

    if ! bp_wait_for_port "$PORT" 30; then
        log_error "gateway never bound port $PORT"
        docker logs "$container" >&2 2>&1 || true
        return 1
    fi
    log_info "gateway listening on :${PORT} (container $container)"
}

# -----------------------------------------------------------------------------
# STATIC: python3 http.server. Zero install, no Docker, works on ubuntu-slim.
# -----------------------------------------------------------------------------
start_static() {
    printf 'breakpoint-origin-ok' >"$DOC_ROOT/health"
    cat >"$DOC_ROOT/index.html" <<'HTML'
<!doctype html>
<title>breakpoint</title>
<h1>breakpoint origin</h1>
<p>This runner is reachable.</p>
<ul>
  <li><a href="/health">/health</a> - liveness</li>
</ul>
<p>No gateway is running, so there is nothing else to route to. Start the
session with a desktop or services to get the Caddy gateway and its
<code>/desktop</code> route.</p>
HTML

    log_step "starting static origin on :${PORT}..."
    python3 -m http.server "$PORT" --directory "$DOC_ROOT" >"$STATE_DIR/origin.log" 2>&1 &
    local pid=$!
    bp_record_pid origin "$pid"
    bp_state_set BP_ORIGIN_PID "$pid"

    if ! bp_wait_for_port "$PORT" 20; then
        log_error "origin never bound port $PORT"
        cat "$STATE_DIR/origin.log" >&2 2>/dev/null || true
        return 1
    fi
}

case "$KIND" in
    gateway) start_gateway || exit 1 ;;
    static) start_static || exit 1 ;;
    *)
        log_error "unknown --kind '$KIND' (expected auto, static or gateway)"
        exit 4
        ;;
esac

# Assert the CONTENT, not just the port. A bound port with a broken doc root
# would still satisfy a port check and then fail confusingly through the tunnel.
BODY="$(curl -s --max-time 5 "http://localhost:${PORT}/health" || true)"
if [[ "$BODY" != "breakpoint-origin-ok" ]]; then
    log_error "origin bound :$PORT but /health returned '${BODY}' instead of 'breakpoint-origin-ok'"
    exit 1
fi

log_info "origin serving on :${PORT} (kind: ${KIND})"
if [[ "$KIND" == "gateway" ]]; then
    log_info "  /desktop -> noVNC on :6080, /* -> the app on :80"
fi
echo "http://localhost:${PORT}"
