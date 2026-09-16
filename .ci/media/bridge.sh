#!/bin/bash
# The VM side of tutorial recording: provisioning the cluster, reaching the bridge
# over SSH, and putting a dev rdc SEA plus the tutorial scripts on it.
#
# This is the module with the machine mutex in it. Everything here talks to a real
# libvirt cluster or a real SSH endpoint, which is why it is separated from the
# pipeline logic that merely calls it: the pipeline can then be tested without a VM
# in sight, and this module's own test proves the pure parts (IP resolution from
# .provision-state, the ssh/rsync argument shapes) with ssh and rsync faked.
#
# Part of the media pipeline extraction (W10). Moved out of run.sh byte for byte in
# phase 1, comments included; phase 2 deleted run.sh's copies.
# .ci/scripts/test/gates/test-media-bridge.sh asserts that this module is the sole owner
# of all nine names, and drives `./run.sh provision start` end to end -- through run.sh's
# exec into media-entry.sh and into this file -- with no cluster anywhere near it.
#
# SOURCED, NEVER EXECUTED. Callers supply ROOT_DIR, the log_* helpers, and (for
# _build_cli_sea_cached only) ensure_deps/ensure_packages_built from
# .ci/lib/local-common.sh.

# --- VM provisioning ----------------------------------------------------------
# These wrap `rdc ops`, which owns local KVM/QEMU provisioning. They existed as
# call sites with no definitions anywhere in the repo: `./run.sh provision
# start|stop|status` and the tutorial recorder both died with
# "provision_start: command not found" (exit 127). The recorder is the only way
# to regenerate tutorial casts, so that surface was completely unreachable.
#
# `rdc ops up` also writes $_BRIDGE_SSH_CONFIG (see the note below), which is
# what the bridge helpers need, so there is nothing left for a separate
# post-setup step to do -- the recorder bootstraps the bridge itself right
# after provisioning.
provision_start() {
    "$ROOT_DIR/rdc.sh" ops up "$@"
}

provision_stop() {
    "$ROOT_DIR/rdc.sh" ops down
}

provision_status() {
    "$ROOT_DIR/rdc.sh" ops status
}

# --- Bridge recording helpers -------------------------------------------------
# Tutorials are recorded INSIDE the bridge VM so the local host's
# ~/.config/rediacc is never touched and the cast captures a pristine machine.
# Host->bridge SSH uses the config that `renet ops up` generates, which carries
# the correct VM user + key for THIS environment (vscode in CI, the host user
# locally), so we never hardcode either.
_BRIDGE_SSH_CONFIG="$HOME/.renet/staging/.ssh/config"

# Resolve the bridge IP from the provision state, with a sane default.
_bridge_ip() {
    local ip=""
    if [[ -f "$ROOT_DIR/.provision-state" ]]; then
        ip="$(grep '^bridge_ip=' "$ROOT_DIR/.provision-state" 2>/dev/null | cut -d= -f2)"
    fi
    echo "${ip:-${VM_NET_BASE:-${VM_NET_BASE_DEFAULT:-192.168.111}}.${VM_BRIDGE:-${VM_BRIDGE_DEFAULT:-1}}}"
}

# Resolve the Nth worker IP (1-based) from provision state (.11, .12, ...).
_worker_ip() {
    local idx="${1:-1}"
    local ips=""
    if [[ -f "$ROOT_DIR/.provision-state" ]]; then
        ips="$(grep '^worker_ips=' "$ROOT_DIR/.provision-state" 2>/dev/null | cut -d= -f2)"
    fi
    if [[ -n "$ips" ]]; then
        echo "$ips" | cut -d, -f"$idx"
    else
        local -a workers
        read -ra workers <<<"${VM_WORKERS:-11 12}"
        echo "${VM_NET_BASE:-${VM_NET_BASE_DEFAULT:-192.168.111}}.${workers[$((idx - 1))]:-11}"
    fi
}

_bridge_ssh() {
    ssh -F "$_BRIDGE_SSH_CONFIG" -o BatchMode=yes -o StrictHostKeyChecking=no \
        -o ConnectTimeout=15 "$(_bridge_ip)" "$@"
}

_bridge_rsync() {
    rsync -a -e "ssh -F $_BRIDGE_SSH_CONFIG -o BatchMode=yes -o StrictHostKeyChecking=no" "$@"
}

# Build the linux-x64 dev rdc SEA (for the bridge), cached by source hash so
# reruns skip the rebuild when packages/cli, packages/shared, or renet
# are unchanged. Output: dist/cli/rdc-linux-x64. Mirrors `rdc.sh --native`
# but installs nothing on the host.
_build_cli_sea_cached() {
    local out="$ROOT_DIR/dist/cli/rdc-linux-x64"
    local hash_file="$ROOT_DIR/dist/cli/.sea-source-hash"
    local cur
    cur="$(
        {
            find "$ROOT_DIR/packages/cli/src" "$ROOT_DIR/packages/shared/src" \
                -type f \
                \( -name '*.ts' -o -name '*.json' \) -exec "${MEDIA_SHA256[@]}" {} + 2>/dev/null | sort
            git -C "$ROOT_DIR/private/renet" rev-parse HEAD 2>/dev/null || true
        } | "${MEDIA_SHA256[@]}" | awk '{print $1}'
    )"
    if [[ -f "$out" && -f "$hash_file" && "$(cat "$hash_file" 2>/dev/null)" == "$cur" ]]; then
        log_info "Dev SEA up-to-date (source unchanged): $out"
        return 0
    fi

    log_step "Building dev rdc SEA (linux-x64) for the bridge..."
    ensure_deps
    ensure_packages_built
    local embed_renet="$ROOT_DIR/private/bin/renet-linux-amd64"
    mkdir -p "$ROOT_DIR/private/bin"
    # Full renet, all assets. The old `slim` tag existed only because the SEA blob
    # had to stay under postject 1.0.0-alpha.6's ~300 MB injection ceiling (its
    # Emscripten build aborts above that, which is what once made tutorial
    # recording impossible, #525). The streaming injector that replaced postject
    # has no such ceiling, so the bridge now carries the complete k8s stack and a
    # cluster tutorial can be recorded like any other. Per-arch embedding keeps the
    # binary to its own architecture's assets.
    (cd "$ROOT_DIR/private/renet" &&
        CGO_ENABLED=0 GOOS=linux GOARCH=amd64 go build \
            -tags "nolicense" -ldflags="-s -w -X main.Version=0.0.0-dev" \
            -o "$embed_renet" ./cmd/renet)
    bash "$ROOT_DIR/.ci/scripts/build/build-cli-executables.sh" --platform linux --arch x64
    [[ -f "$out" ]] || {
        log_error "SEA build did not produce $out"
        exit 1
    }
    echo "$cur" >"$hash_file"
}

# Ensure the bridge has node + asciinema + the dev rdc SEA + the tutorial scripts.
# Idempotent: safe to call before every recording batch (state is ephemeral —
# the bridge is torn down with provision_stop).
_ensure_bridge_recording_tooling() {
    local bridge
    bridge="$(_bridge_ip)"

    # Wait for the bridge to be reachable, then fail loudly if it never is.
    local who="" i
    for ((i = 1; i <= 15; i++)); do
        who="$(_bridge_ssh 'whoami' 2>/dev/null || true)"
        [[ -n "$who" ]] && break
        sleep 2
    done
    if [[ -z "$who" ]]; then
        log_error "Bridge VM ($bridge) is not reachable over SSH."
        log_error "Check 'rdc ops status' / './run.sh provision status' and $_BRIDGE_SSH_CONFIG."
        exit 1
    fi
    log_info "Bridge reachable as user: $who"

    # node + asciinema (bridge has internet + passwordless sudo).
    if ! _bridge_ssh 'command -v node >/dev/null && command -v asciinema >/dev/null'; then
        log_step "Installing node + asciinema on the bridge..."
        _bridge_ssh 'sudo DEBIAN_FRONTEND=noninteractive apt-get update -qq && \
            sudo DEBIAN_FRONTEND=noninteractive apt-get install -y -qq nodejs npm asciinema'
    fi

    # Dev rdc SEA — build (cached) and transfer only when the checksum differs.
    _build_cli_sea_cached
    local sea="$ROOT_DIR/dist/cli/rdc-linux-x64"
    local local_sum remote_sum
    local_sum="$("${MEDIA_SHA256[@]}" "$sea" | awk '{print $1}')"
    remote_sum="$(_bridge_ssh 'sha256sum /usr/local/bin/rdc 2>/dev/null | cut -d" " -f1' || true)"
    if [[ "$local_sum" != "$remote_sum" ]]; then
        log_step "Transferring dev rdc SEA to the bridge..."
        _bridge_rsync "$sea" "${bridge}:/tmp/rdc-dev"
        _bridge_ssh 'sudo install -m0755 /tmp/rdc-dev /usr/local/bin/rdc && rm -f /tmp/rdc-dev'
    else
        log_info "Bridge rdc up-to-date (checksum match)"
    fi
    log_info "Bridge rdc version: $(_bridge_ssh 'rdc --version 2>/dev/null | tail -1')"

    # Tutorial scripts + post-processors, preserving record.sh's ROOT_DIR=../..
    # layout so it resolves the .mjs post-processors under /tmp/rec/.ci.
    log_step "Syncing tutorial scripts to the bridge..."
    _bridge_ssh 'mkdir -p /tmp/rec/.ci/tutorials /tmp/rec/.ci/scripts/docs /tmp/rec/out'
    _bridge_rsync "$ROOT_DIR/.ci/tutorials/" "${bridge}:/tmp/rec/.ci/tutorials/"
    _bridge_rsync "$ROOT_DIR/.ci/scripts/docs/" "${bridge}:/tmp/rec/.ci/scripts/docs/"
}
