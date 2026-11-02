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

# Logging, the same glyphs and the same stderr-only rule as .ci/scripts/lib/common.sh
# (colour only on a terminal, never under NO_COLOR). Stdout belongs to the CLI command.
if [[ -t 2 ]] && [[ -z "${NO_COLOR:-}" ]]; then
    _red='\033[0;31m' _green='\033[0;32m' _yellow='\033[1;33m' _blue='\033[0;34m' _nc='\033[0m'
else
    _red='' _green='' _yellow='' _blue='' _nc=''
fi
log_info() { echo -e "${_green}✓${_nc} $*" >&2; }
log_warn() { echo -e "${_yellow}⚠${_nc} $*" >&2; }
log_error() { echo -e "${_red}✗${_nc} $*" >&2; }
log_step() { echo -e "${_blue}→${_nc} $*" >&2; }

# NAME THE MISSING INTERPRETER, the way run.sh:44-50 does. The preparation below and
# --native are both served by the Python CI package; without this check the failure is
# a bare exit 127 and the word `python3`.
if ! command -v python3 >/dev/null 2>&1; then
    log_error "rdc.sh prepares the CLI through the Python CI package, and python3 is not on PATH."
    log_error "Install it, or run .ci/bootstrap.sh which provisions this toolchain."
    exit 1
fi

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
# reason .ci/rediacc_ci/tests/gates/test_gate_run_sh.py holds run.sh to one.
if [[ "${1:-}" == "--native" ]]; then
    shift
    # exec, not a call: a multi-hour build's exit code and signals are its own.
    PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" exec python3 -m rediacc_ci.native "$@"
fi

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
log_step "Preparing CLI development environment"

# Ensure the toolchain is current (node floor, deps, packages, CLI bundle, renet; the
# order is core/local_common.py prepare_cli). All build/progress output goes to STDERR:
# stdout belongs to the CLI command — a rebuild triggered by an edit must not
# corrupt an `rdc ... -o json` pipeline with npm build logs (observed live:
# the first post-edit invocation broke JSON.parse for the caller).
PYTHONPATH="$ROOT_DIR/.ci${PYTHONPATH:+:$PYTHONPATH}" python3 -m rediacc_ci.core.local_common prepare-cli >&2

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
export PATH="$ROOT_DIR/private/renet/bin:$PATH"

# WHICH UNIVERSE THIS RUNS AGAINST. Production is the default and `--dev` (or
# RDC_DEV=1) is the one opt-in on top; bench is not a flag, it is the named config
# `./rdc.sh --config bench <cmd>`. Every universe is a named CLI config carrying its
# own server, keys and token, so selecting one is the ONLY thing that changes here.
# The 27 lines of prose that stood here said what docs/agent-reference/local-env.md
# already says under 'The ./rdc.sh wrappers'.
if [[ "${1:-}" == "--dev" ]]; then
    RDC_DEV=1
    shift
fi
selected_config_name() { local p=""; for a in "$@"; do [[ "$p" == "--config" ]] && { printf '%s' "$a"; return; }; [[ "$a" == --config=* ]] && { printf '%s' "${a#--config=}"; return; }; p="$a"; done; printf '%s' "${REDIACC_CONFIG:-rediacc}"; } # the banner's config: --config <name>|=<name>, then REDIACC_CONFIG, then rediacc (production)
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

    # Seed/patch the "dev" config (`rdc config set` cannot reach account fields). It writes the CLI's file by the CLI's rules: the config dir of packages/shared/src/paths/dirs.ts, 'wx' creation, the CLI's proper-lockfile lock (the `<file>.lock` directory), temp+rename, no write when the fields already match, and a file it cannot parse is an error, never replaced. A key belongs to the server it came from: a moved gateway that advertised none keeps no key of the old one.
    node -e '
      const fs = require("fs"), path = require("path"), { randomUUID } = require("crypto"), env = process.env, home = require("os").homedir();
      const [server, key] = process.argv.slice(1), win = process.platform === "win32", mac = process.platform === "darwin";
      const dir = win ? path.join(env.APPDATA ?? path.join(home, "AppData", "Roaming"), "rediacc") : mac ? path.join(home, "Library", "Application Support", "rediacc") : path.join(env.XDG_CONFIG_HOME || path.join(home, ".config"), "rediacc");
      const p = path.join(dir, "dev.json"), seed = { schemaVersion: 3, id: randomUUID(), version: 1, encryption: { mode: "plaintext" } };
      fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
      try { fs.writeFileSync(p, JSON.stringify(seed, null, 2) + "\n", { mode: 0o600, flag: "wx" }); } catch (e) { if (e.code !== "EEXIST") throw e; }
      const lock = `${fs.realpathSync(p)}.lock`, deadline = Date.now() + 45000;
      for (;;) {
        try { fs.mkdirSync(lock); break; } catch (e) { if (e.code !== "EEXIST") throw e; }
        if (Date.now() - (fs.statSync(lock, { throwIfNoEntry: false })?.mtimeMs ?? Date.now()) > 45000) fs.rmSync(lock, { recursive: true, force: true });
        else if (Date.now() > deadline) throw new Error(`${lock} is still held after 45s`);
        else Atomics.wait(new Int32Array(new SharedArrayBuffer(4)), 0, 0, 50);
      }
      try {
        const c = JSON.parse(fs.readFileSync(p, "utf8"));
        const account = { ...(c.account ?? {}), accountServer: server, ...(key ? { e2ePublicKey: key } : {}) };
        const bare = (url) => String(url ?? "").replace(/\/+$/, "");
        if (!key && bare(c.account?.accountServer) !== bare(server)) delete account.e2ePublicKey;
        if (JSON.stringify(account) !== JSON.stringify(c.account ?? {})) {
          const tmp = `${p}.tmp.${process.pid}.${randomUUID()}`;
          fs.writeFileSync(tmp, JSON.stringify({ ...c, account }, null, 2) + "\n", { mode: 0o600 });
          fs.renameSync(tmp, p);
        }
      } finally {
        fs.rmdirSync(lock);
      }
    ' "$dev_server" "$dev_e2e_key"

    # The only export the dev path adds: select the "dev" config (server URL and E2E key live inside it).
    export REDIACC_CONFIG=dev

    log_info "Renet available at: $ROOT_DIR/private/renet/bin/renet"
    log_step "Starting CLI (dev config — $dev_server)"
else
    log_info "Renet available at: $ROOT_DIR/private/renet/bin/renet"
    log_step "Starting CLI (config $(selected_config_name "$@"))"
fi

# Run the compiled CLI bundle, passing through all arguments
# exec, not a child: signals sent to this wrapper must reach the CLI directly
# (a bash layer between kill and node defers SIGINT until the child exits,
# which hangs tutorial prewarm/interrupt patterns — see tutorial-helpers.sh).
# NODE_COMPILE_CACHE: V8 spends ~120ms compiling the 15MB bundle on EVERY
# invocation (measured, --cpu-prof); the on-disk compile cache cuts that to a
# few ms after the first run. Env-var form on purpose — it covers the entry
# file itself, which module.enableCompileCache() cannot. Invalidated
# automatically by node version + file content. (The SEA keeps
# useCodeCache:false — code cache is platform-bound and the SEAs are
# cross-compiled.)
export NODE_COMPILE_CACHE="${NODE_COMPILE_CACHE:-$ROOT_DIR/.ci/cache/v8-compile-cache}"
exec node "$ROOT_DIR/packages/cli/dist/cli-bundle.cjs" "$@"
