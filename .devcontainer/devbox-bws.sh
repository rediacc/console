# shellcheck shell=sh
# Devbox login-shell hook: export BWS_ACCESS_TOKEN from a host file, read at shell start.
#
# Bind-mounted read-only to /etc/profile.d/zz-devbox-bws.sh by `.ci/lib/devbox.sh` (devbox_script_binds), so every login shell in the devbox (`bash -l`, `docker exec ... bash -lc`, the ttyd tmux session) exports the token. Nothing is baked: the value lives only in a host file bound into the container, so it is in no image layer, no `docker inspect` Config.Env, no label and no tracked file. A rotated token reaches the next login shell without recreating anything.
#
# Two sources, first hit wins:
#   1. /home/vscode/.config/rediacc-console/bws-access-token (DEVBOX_BWS_TOKEN_FILE overrides the path), the token-only file (host ${XDG_CONFIG_HOME:-$HOME/.config}/rediacc-console/, bound read-only by devbox_home_binds). An absolute path, because `docker exec` runs as root with HOME=/root.
#   2. The BWS_ACCESS_TOKEN line of $DEVBOX_WORKSPACE/private/account/.env, which the repo bind already carries in, until that .env is retired (agent/plans/PLAN-account-env-to-bws.md).
#
# POSIX sh, not bash: /etc/profile is read by dash as well (`sh -l`), and a bashism here would break every such login.
#
# Only the one line is parsed; the .env is never sourced. Sourcing it would export every other secret in it into every shell and execute whatever the file happens to contain.
#
# xtrace is suspended around the read, so `bash -lx` traces no value. Nothing is ever printed: with neither source readable the variable stays unset, and `bws` and `.ci/rediacc_ci/core/bws_env.py` then refuse with their own explicit message.
#
# An already-set BWS_ACCESS_TOKEN wins, so a caller can still point a single shell at another machine account.

if [ -z "${BWS_ACCESS_TOKEN:-}" ]; then
    case $- in
        *x*)
            _devbox_bws_x=1
            set +x
            ;;
        *) _devbox_bws_x= ;;
    esac
    _devbox_bws_val=
    _devbox_bws_file=${DEVBOX_BWS_TOKEN_FILE:-/home/vscode/.config/rediacc-console/bws-access-token}
    if [ -r "$_devbox_bws_file" ]; then
        read -r _devbox_bws_val <"$_devbox_bws_file" || :
    fi
    _devbox_bws_env="${DEVBOX_WORKSPACE:-}/private/account/.env"
    if [ -z "$_devbox_bws_val" ] && [ -n "${DEVBOX_WORKSPACE:-}" ] && [ -r "$_devbox_bws_env" ]; then
        while IFS= read -r _devbox_bws_line || [ -n "$_devbox_bws_line" ]; do
            _devbox_bws_line=${_devbox_bws_line#export }
            case $_devbox_bws_line in
                BWS_ACCESS_TOKEN=*) _devbox_bws_val=${_devbox_bws_line#BWS_ACCESS_TOKEN=} ;;
            esac
        done <"$_devbox_bws_env"
    fi
    _devbox_bws_val=${_devbox_bws_val%"$(printf '\r')"}
    case $_devbox_bws_val in
        \"*\")
            _devbox_bws_val=${_devbox_bws_val#\"}
            _devbox_bws_val=${_devbox_bws_val%\"}
            ;;
        \'*\')
            _devbox_bws_val=${_devbox_bws_val#\'}
            _devbox_bws_val=${_devbox_bws_val%\'}
            ;;
    esac
    if [ -n "$_devbox_bws_val" ]; then
        BWS_ACCESS_TOKEN=$_devbox_bws_val
        export BWS_ACCESS_TOKEN
    fi
    unset _devbox_bws_val _devbox_bws_line _devbox_bws_file _devbox_bws_env
    if [ -n "$_devbox_bws_x" ]; then
        unset _devbox_bws_x
        set -x
    fi
    unset _devbox_bws_x
fi
