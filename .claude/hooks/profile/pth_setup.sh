# shellcheck shell=bash
# The user-site .pth loader for the resource recorder, sourced by bash_env.sh
# (agent/plans/PLAN-tooling-speed.md D6).
#
# WHY. bash_env.sh reaches python3 through PYTHONPATH, and `PYTHONPATH=.ci python3
# -m ...` replaces it. A .pth file in the user site directory is processed whatever
# PYTHONPATH says, so this writes one there, beside a copy of pth_loader.py, and
# appends this repo to ~/.claude/resprofile/pth-roots, the only roots the loader
# acts for (pth_loader.py says why it never walks up from the cwd instead).
#
# COST, because this is sourced by every non-interactive bash. The steady state is
# three `read`s and no fork: the user site path is cached in
# ~/.claude/resprofile/pth-site, and the loader is copied only when its version line
# differs. python3 runs once, to learn the user site path, and only while no cached
# path names an existing directory.
#
# CONTRACTS, bash_env.sh's: never prints, never changes a status the caller sees,
# off with WORKLIST_PROFILE=off (checked by the caller). Takes the repo root as $1.
__rp_repo=${1:-}
__rp_dir="$HOME/.claude/resprofile"
__rp_src="$__rp_repo/.claude/hooks/profile/pth_loader.py"
if [[ -n $__rp_repo && -r $__rp_src ]]; then
    __rp_have=0
    if [[ -r $__rp_dir/pth-roots ]]; then
        while IFS= read -r __rp_line; do
            [[ $__rp_line == "$__rp_repo" ]] && {
                __rp_have=1
                break
            }
        done <"$__rp_dir/pth-roots"
    fi
    if ((!__rp_have)); then
        mkdir -p "$__rp_dir" 2>/dev/null && printf '%s\n' "$__rp_repo" >>"$__rp_dir/pth-roots"
    fi
    __rp_site=''
    [[ -r $__rp_dir/pth-site ]] && IFS= read -r __rp_site <"$__rp_dir/pth-site"
    if [[ -z $__rp_site || ! -d $__rp_site ]]; then
        __rp_site=$(WORKLIST_PROFILE=off python3 -c 'import site; print(site.getusersitepackages() if site.ENABLE_USER_SITE else "")' 2>/dev/null)
        if [[ -n $__rp_site ]] && mkdir -p "$__rp_site" "$__rp_dir" 2>/dev/null; then
            printf '%s\n' "$__rp_site" >"$__rp_dir/pth-site"
        fi
    fi
    if [[ -n $__rp_site && -d $__rp_site ]]; then
        __rp_want='' __rp_got=''
        IFS= read -r __rp_want <"$__rp_src"
        [[ -r $__rp_site/rediacc_resprofile_loader.py ]] && IFS= read -r __rp_got <"$__rp_site/rediacc_resprofile_loader.py"
        if [[ $__rp_want != "$__rp_got" ]]; then
            cp -f "$__rp_src" "$__rp_site/rediacc_resprofile_loader.py.$$" 2>/dev/null &&
                mv -f "$__rp_site/rediacc_resprofile_loader.py.$$" "$__rp_site/rediacc_resprofile_loader.py" 2>/dev/null
        fi
        [[ -f $__rp_site/rediacc_resprofile.pth ]] ||
            printf 'import rediacc_resprofile_loader\n' >"$__rp_site/rediacc_resprofile.pth" 2>/dev/null
    fi
fi
unset __rp_repo __rp_dir __rp_src __rp_have __rp_line __rp_site __rp_want __rp_got
:
