# shellcheck shell=sh
# Devbox login-shell hook: export BWS_ACCESS_TOKEN from a host file, read at shell start.
#
# Bind-mounted read-only to /etc/profile.d/zz-devbox-bws.sh by `.ci/lib/devbox.sh` (devbox_script_binds), so every login shell in the devbox (`bash -l`, `docker exec ... bash -lc`, the ttyd tmux session) exports the token. Nothing is baked: the value lives only in a host file bound into the container, so it is in no image layer, no `docker inspect` Config.Env, no label and no tracked file. A rotated token reaches the next login shell without recreating anything.
#
# One source: /home/vscode/.config/rediacc/bws-access-token (DEVBOX_BWS_TOKEN_FILE overrides the path), the token-only file (host ${XDG_CONFIG_HOME:-$HOME/.config}/rediacc/bws-access-token, the FILE bound read-only by devbox_home_binds over the read-write .config/rediacc bind). An absolute path, because `docker exec` runs as root with HOME=/root. The account env file it once fell back to is retired (agent/plans/PLAN-account-env-to-bws.md).
#
# POSIX sh, not bash: /etc/profile is read by dash as well (`sh -l`), and a bashism here would break every such login.
#
# xtrace is suspended around the read, so `bash -lx` traces no value. Nothing is ever printed: with the file unreadable the variable stays unset, and `bws` and `.ci/rediacc_ci/core/bws_env.py` then refuse with their own explicit message.
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
    _devbox_bws_file=${DEVBOX_BWS_TOKEN_FILE:-/home/vscode/.config/rediacc/bws-access-token}
    if [ -r "$_devbox_bws_file" ]; then
        read -r _devbox_bws_val <"$_devbox_bws_file" || :
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
    unset _devbox_bws_val _devbox_bws_file
    if [ -n "$_devbox_bws_x" ]; then
        unset _devbox_bws_x
        set -x
    fi
    unset _devbox_bws_x
fi
