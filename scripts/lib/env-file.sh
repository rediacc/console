#!/bin/bash
# Load a KEY=value file into the shell WITHOUT executing it.
#
# Usage:
#   source "$ROOT_DIR/scripts/lib/env-file.sh"
#   env_file_load "$ACCOUNT_DIR/.env"              # every key the shell lacks
#   env_file_load "$ACCOUNT_DIR/.env" GATEWAY_PORT # only these
#
# THIS FILE IS A DELEGATING SHIM, the same shape as .ci/lib/find-port.sh and
# .ci/scripts/lib/age-check.sh. The implementation and all of its reasoning live
# in .ci/rediacc_ci/core/env.py: why parsing beats `source`, why the SHELL wins
# over the file, why an empty environment value counts as absent, and why a
# missing file is normal while an unreadable one is a defect. Read that module
# before changing anything here. There is deliberately no bash fallback: a
# fallback is a second implementation and a second implementation drifts, and
# what would drift here is which credential a process ends up holding.
#
# WHAT IT REPLACES, AND WHY THE REPLACEMENT IS NOT EQUIVALENT
#
#   set -a; source "$f"; set +a
#
# differs from this in two ways that are the entire point:
#
#   1. `source` EXECUTES the file. A `$(...)` in a value runs. .env files here
#      are written by .ci/lib/account.sh, but they are also hand-edited, and
#      rdc.sh:240-245 already refuses to source this exact file for this exact
#      reason.
#   2. `set -a; source` lets the FILE overwrite the SHELL. Every override this
#      repo ships arrives through the environment -- a workflow `env:` block, a
#      GITHUB_ENV append, a developer typing `PORT=4900 ./run.sh` -- and
#      file-wins discards all of them in favour of a value written to disk
#      months ago, silently. .ci/lib/account.sh:432-440 is the live case:
#      account_allocate_ports computes GATEWAY_PORT and four lines later the
#      file was free to overwrite it.
#
# So a call site that LAYERS two files has to load them in the reverse of the
# old order: whichever file should win goes FIRST, because once a key is in the
# environment the next file cannot take it back. scripts/ops/deploy-bench.sh is
# that case and says so at its call site.

# Prevent re-sourcing. Guard on the function, not on a flag alone, so a caller
# that sources this after `unset -f` gets the function back.
if [[ -n "${ENV_FILE_SH_LOADED:-}" ]] && declare -F env_file_load >/dev/null 2>&1; then
    return 0
fi

# REDIACC_CI_ROOT is the package's single environment override
# (.ci/rediacc_ci/paths.py). Honoured here for the same reason find-port.sh
# honours it: a planted-defect control can point the shim at a MUTATED COPY of
# the package and prove the delegation is real rather than reimplemented.
_env_file_root="${REDIACC_CI_ROOT:-$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)}"
if [[ ! -d "$_env_file_root/.ci/rediacc_ci/core" ]]; then
    echo "env-file.sh: cannot find rediacc_ci under '$_env_file_root/.ci' (set REDIACC_CI_ROOT)" >&2
    unset _env_file_root
    return 1
fi
if ! command -v python3 >/dev/null 2>&1; then
    echo "env-file.sh: python3 is required; the env-file logic lives in rediacc_ci.core.env" >&2
    unset _env_file_root
    return 1
fi
ENV_FILE_SH_LOADED=1
ENV_FILE_CI_DIR="$_env_file_root/.ci"
unset _env_file_root

# One place that builds the interpreter invocation, so PYTHONPATH is set
# identically for every verb. PYTHONPATH rather than `cd`: a caller may be
# running from anywhere, and changing directory would change what a relative
# path in its own arguments means.
_env_file_py() {
    PYTHONPATH="$ENV_FILE_CI_DIR${PYTHONPATH:+:$PYTHONPATH}" \
        python3 -m rediacc_ci.core.env "$@"
}

# env_file_load <path> [name...]
#
# Exports every key in <path> that the environment does not already carry, or
# only the named ones. Absent file: nothing happens, exit 0 (absence is a normal
# state meaning "not generated yet", .ci/lib/account.sh:311-313). Unreadable
# file, or a parse error: exit non-zero WITHOUT exporting anything.
#
# The output is captured and its status checked BEFORE the eval. Piping the
# generator straight into eval would evaluate an error message on failure and
# hide the exit code behind eval's own.
env_file_load() {
    if [[ $# -lt 1 ]]; then
        echo "env_file_load: usage: env_file_load <path> [name...]" >&2
        return 2
    fi
    local __env_file_out __env_file_rc=0
    __env_file_out="$(_env_file_py export "$@")" || __env_file_rc=$?
    if [[ $__env_file_rc -ne 0 ]]; then
        echo "env_file_load: refusing to continue; '$1' could not be read (rc=$__env_file_rc)" >&2
        return "$__env_file_rc"
    fi
    eval "$__env_file_out"
}

# env_file_get <path> <key>
#
# ONE value on stdout, nothing else. Exit 1 when the key is absent, so `set -e`
# and a bare `if !` both see it.
env_file_get() {
    _env_file_py get "$1" "$2"
}

# env_file_keys <path>
#
# The key NAMES, one per line, in file order. Never a value: this is what a call
# site prints when it wants a log line about the file it just loaded.
env_file_keys() {
    _env_file_py keys "$1"
}
