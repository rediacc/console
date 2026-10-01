#!/bin/bash
# Load the well-known registry (.ci/config/well-known.env) into the shell.
#
# Usage:
#   source "$ROOT_DIR/scripts/lib/well-known.sh"
#   well_known_load
#
# The ONE place a bash script reads the WK_* facts (origins, registry, slugs,
# owned paths). It goes through env_file_load (scripts/lib/env-file.sh), the
# repo's sanctioned env-file loader, so the SHELL wins over the file exactly as
# for every other env file, and the file is parsed, never executed. An exported
# WK_* therefore beats the registry. Python reads the same file directly through
# rediacc_ci.well_known.
#
# Exempt by design: .ci/config/constants.sh sources the registry itself because
# it runs before python3 is guaranteed (the BLOCKER in check_env_file_adoption).
#
# A missing or empty registry is a failure, never a quiet no-op: env_file_load
# treats an absent file as normal, and a script that then reads an empty
# $WK_GH_ORIGIN would build a request against nothing.

if [[ -n "${WELL_KNOWN_SH_LOADED:-}" ]] && declare -F well_known_load >/dev/null 2>&1; then
    return 0
fi

_well_known_lib_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=env-file.sh
source "$_well_known_lib_dir/env-file.sh" || return 1
WELL_KNOWN_ENV_FILE="$_well_known_lib_dir/../../.ci/config/well-known.env"
unset _well_known_lib_dir
WELL_KNOWN_SH_LOADED=1

well_known_load() {
    if [[ ! -r "$WELL_KNOWN_ENV_FILE" ]]; then
        echo "well-known.sh: registry missing or unreadable: $WELL_KNOWN_ENV_FILE" >&2
        return 1
    fi
    env_file_load "$WELL_KNOWN_ENV_FILE" || return 1
    if [[ -z "${WK_GH_ORIGIN:-}" ]]; then
        echo "well-known.sh: loaded $WELL_KNOWN_ENV_FILE but WK_GH_ORIGIN is empty; the registry is not being read" >&2
        return 1
    fi
}
