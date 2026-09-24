#!/bin/bash
# Standalone CLI runner for rdc (development mode)
# Auto-builds renet from Go source and makes it available to the CLI.
#
# The demo-prep cheat sheet that stood here (URL anatomy, the fork/connect/delete
# loop, the repos on `hostinger`, the agent-style prompts) moved to
# docs/agent-reference/local-env.md on 2026-09-09, beside the `--native` section that
# already documented half of it. 53 lines of demo runbook in the wrapper a developer
# types to run an ordinary CLI command is not where a runbook belongs.

set -euo pipefail

# Root directory (portable: works on Linux, macOS, and Windows/Git Bash)
ROOT_DIR="$(cd "$(dirname "$(readlink -f "${BASH_SOURCE[0]}")")" && pwd -P)"

# Source configuration and utilities
source "$ROOT_DIR/.ci/config/constants.sh"
source "$ROOT_DIR/.ci/lib/local-common.sh"

# --native: build the real single-executable binary (Node SEA) from local source and
# install it over the user's rdc, instead of running via the dev bundle. Use it to
# exercise SEA-only behaviours the bundle cannot reach (embedded-renet extraction,
# auto-update gating). docs/agent-reference/local-env.md carries the loop.
#
# THE BUILD ITSELF IS NOT HERE ANY MORE. It was 93 lines of this file, 60 of them code,
# including two `case "$(uname ...)"` blocks that were copies four and five of a mapping
# .ci/rediacc_ci/core/platform.py already owned and names by line. .ci/rediacc_ci/native.py
# holds it now, with `system` and `machine` as ARGUMENTS rather than uname calls, so
# check:ci-rdc-native drives the linux, mac and win arms from one Linux box -- in bash the
# mac and win arms were never once executed by anything in this repository.
#
# Do not re-inline it. check:ci-rdc-native holds this file to a line ceiling for the same
# reason .ci/scripts/test/gates/test-run-sh.sh holds run.sh to one.
if [[ "${1:-}" == "--native" ]]; then
    shift
    # NAME THE MISSING INTERPRETER, the way run.sh:44-50 does. Without this the
    # failure is a bare exit 127 and the word `python3`, on a flag nobody has any
    # reason to know is Python.
    if ! command -v python3 >/dev/null 2>&1; then
        log_error "--native is served by the Python CI package, and python3 is not on PATH."
        log_error "Install it, or run .ci/bootstrap.sh which provisions this toolchain."
        exit 1
    fi
    # exec, not a call: a multi-hour build's exit code and signals are its own.
    PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.native "$@"
fi

check_node_version "$NODE_VERSION_MIN"

if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" == "1" ]]; then
    # Self-register as 'rdc' in ~/.local/bin so it's accessible from any terminal,
    # but ONLY when nothing is already installed there. A real SEA binary (from
    # `./rdc.sh --native`) installs to ~/.local/share/rediacc/bin/rdc and
    # points this symlink at it; forcibly repointing it back to the wrapper would
    # silently undo that install. So we never overwrite an existing rdc on PATH —
    # we only bootstrap the link when it is entirely absent (no file, no symlink,
    # not even a dangling one).
    _local_bin="$HOME/.local/bin"
    mkdir -p "$_local_bin"
    if [[ ! -e "$_local_bin/rdc" && ! -L "$_local_bin/rdc" ]]; then
        ln -s "$ROOT_DIR/rdc.sh" "$_local_bin/rdc"
    fi
    unset _local_bin
else
    log_step "Preparing CLI development environment"
fi

# Ensure the toolchain is current. All build/progress output goes to STDERR:
# stdout belongs to the CLI command — a rebuild triggered by an edit must not
# corrupt an `rdc ... -o json` pipeline with npm build logs (observed live:
# the first post-edit invocation broke JSON.parse for the caller).
ensure_deps >&2
ensure_packages_built >&2
ensure_cli_built >&2
ensure_renet_built >&2

# Regenerate skill reference if CLI has changed
ref_file="$ROOT_DIR/.claude/skills/rdc/reference.md"
cli_dist="$ROOT_DIR/packages/cli/dist/cli-bundle.cjs"
if [[ ! -f "$ref_file" ]] || [[ "$cli_dist" -nt "$ref_file" ]]; then
    log_step "Regenerating skill reference"
    ref_tmp="$(mktemp)"
    if npx tsx "$ROOT_DIR/packages/cli/scripts/generate-skill-reference.ts" >"$ref_tmp" 2>/dev/null && grep -q "^#" "$ref_tmp"; then
        mv "$ref_tmp" "$ref_file"
    else
        rm -f "$ref_tmp"
        log_warn "Skill reference generation failed (keeping existing)"
    fi
fi

# Add renet binary directory to PATH so CLI can find it
renet_bin_dir="$ROOT_DIR/private/renet/bin"
export PATH="$renet_bin_dir:$PATH"

# WHICH UNIVERSE THIS RUNS AGAINST. Production is the default and `--dev` (or
# RDC_DEV=1) is the one opt-in on top; bench is not a flag, it is the named config
# `./rdc.sh --config bench <cmd>`. Every universe is a named CLI config carrying its
# own server, keys and token, so selecting one is the ONLY thing that changes here.
# The 27 lines of prose that stood here said what docs/agent-reference/local-env.md
# already says under 'The ./rdc.sh wrappers', including RDC_RENET_LICENSE=1, which is
# an independent renet build modifier this file does not read at all.
if [[ "${1:-}" == "--dev" ]]; then
    RDC_DEV=1
    shift
fi
if [[ "${RDC_DEV:-0}" == "1" ]]; then
    # Two PUBLIC values only, both from the RUNNING gateway: its port from this
    # worktree's .account-state and its X25519 key from /.well-known/server-info.
    # Nothing under private/account is read or sourced, so no secret reaches the CLI.
    dev_port=$(grep -E '^gateway_port=' "$ROOT_DIR/.account-state" 2>/dev/null | tail -1 | cut -d= -f2- || true)
    if [[ -z "$dev_port" ]]; then
        log_error "RDC_DEV=1 but no running dev gateway recorded in .account-state."
        log_error "Start it first: ./run.sh account dev"
        exit 1
    fi
    dev_server="http://localhost:$dev_port"
    if ! server_info=$(curl -fsS --max-time 2 "$dev_server/account/api/v1/.well-known/server-info" 2>/dev/null); then
        log_error "Dev gateway not responding at $dev_server"
        log_error "Start it first: ./run.sh account dev"
        exit 1
    fi
    # An empty key list yields "", and the seeder below then leaves e2ePublicKey alone.
    dev_e2e_key=$(node -e 'let k="";try{k=JSON.parse(process.argv[1])?.e2e?.keys?.[0]?.publicKeySpki??""}catch{}process.stdout.write(String(k))' "$server_info")

    # Seed/patch the "dev" named config. node is guaranteed present (we exec it
    # below); jq is not. The seeder writes a minimal v3 config when the file is
    # absent and merges only the account fields when it exists, leaving every
    # other key intact. `rdc config set` cannot reach account fields, so this
    # small node snippet is the mechanism.
    node -e '
      const fs = require("fs"), path = require("path"), p = process.argv[1];
      let c;
      try {
        c = JSON.parse(fs.readFileSync(p, "utf8"));
      } catch {
        c = { schemaVersion: 3, id: require("crypto").randomUUID(), version: 1, encryption: { mode: "plaintext" } };
      }
      c.account = {
        ...(c.account ?? {}),
        accountServer: process.argv[2],
        ...(process.argv[3] ? { e2ePublicKey: process.argv[3] } : {}),
      };
      fs.mkdirSync(path.dirname(p), { recursive: true, mode: 0o700 });
      fs.writeFileSync(p, JSON.stringify(c, null, 2) + "\n", { mode: 0o600 });
    ' "$HOME/.config/rediacc/dev.json" "$dev_server" "$dev_e2e_key"

    # The only export the dev path adds: select the "dev" config. Everything
    # else (server URL, E2E key) now lives inside that config file.
    export REDIACC_CONFIG=dev

    if [[ "${REDIACC_SKIP_MACHINE_ACTIVATION:-0}" != "1" ]]; then
        log_info "Renet available at: $renet_bin_dir/renet"
        log_step "Starting CLI (dev config — $dev_server)"
    fi
else
    log_info "Renet available at: $renet_bin_dir/renet"
    log_step "Starting CLI (production config)"
fi

# Run the compiled CLI bundle, passing through all arguments
# exec, not a child: signals sent to this wrapper must reach the CLI directly
# (a bash layer between kill and node defers SIGINT until the child exits,
# which hangs tutorial prewarm/interrupt patterns — see tutorial-helpers.sh).
#
# NODE_COMPILE_CACHE: V8 spends ~120ms compiling the 15MB bundle on EVERY
# invocation (measured, --cpu-prof); the on-disk compile cache cuts that to a
# few ms after the first run. Env-var form on purpose — it covers the entry
# file itself, which module.enableCompileCache() cannot. Invalidated
# automatically by node version + file content. (The SEA keeps
# useCodeCache:false — code cache is platform-bound and the SEAs are
# cross-compiled.)
export NODE_COMPILE_CACHE="${NODE_COMPILE_CACHE:-$ROOT_DIR/.ci/cache/v8-compile-cache}"
exec node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
