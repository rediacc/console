#!/usr/bin/env bash
# HEADER REMOVED 2026-09-08 BY THE W7 P4 CUTOVER, and the FILE deliberately stays.
# check:ci-python-lint is now registered to the Python port's entry point,
# .ci/scripts/quality/check_python_lint.py, so a header here would declare a
# registration that has moved and gate-bind refuses that by name:
#   package.json runs ".ci/scripts/quality/check_python_lint.py" but its header derives ".ci/scripts/quality/check-python-lint.sh"
# This script is NOT dead: it is the differential twin the port is compared
# against, and invariant 5 forbids deleting a twin in the change that ports
# it. Deletion is W7 P5's job, in a later change.

# Lint every tracked Python file with ruff, under the repo's root pyproject.toml.
#
# WHY THIS EXISTS. This repo gated TypeScript, shell and Go and left Python
# entirely ungated, while 13 of its 15 tracked .py files are the Stop-hook
# program that gates every agent turn. The first run of this gate found a live
# NameError in wl_checks.guided_slice that both hook suites -- 584 and 118
# assertions -- passed straight over, because reaching that branch needs
# root=None and a plan-subagent triage at the same time. It then failed SOFT
# into a bare except that replaced the operator's whole worklist guide with an
# apology, so nothing ever surfaced it.
#
# TWO WAYS THIS GATE COULD BE GREEN WHILE PROVING NOTHING, and both are closed
# below before a single real file is judged:
#
#   1. AN EMPTY FILE LIST. `ruff check` with no paths exits 0. A gate whose
#      input silently became empty -- a moved directory, a bad glob, a
#      `git ls-files` run outside a repo -- would report success forever. So
#      the list is counted against a floor, and the floor is a real number
#      rather than 1: a glob that half-breaks is the interesting case.
#   2. A LINTER THAT ISN'T LINTING. A wrong config path, a version that dropped
#      a rule, a wrapper swallowing the exit code -- all look identical to a
#      clean tree. So a synthetic defect is planted and the linter must report
#      it. If the control cannot fire, this exits non-zero WITHOUT judging the
#      real files, because a verdict from an instrument that cannot fail is
#      worse than no verdict.
#   3. AN UNTRACKED FILE, silently omitted. Found live 2026-08-09: this gate
#      reported "27 files, All checks passed!" while wl_checklist.py, the
#      newest and second-largest module of the Stop-hook program, was untracked
#      and therefore never in the list. A format violation in it was caught
#      only by running ruff by hand. The omission is invisible by construction:
#      a shorter list still passes the floor, so nothing looks wrong. The list
#      now includes untracked-but-not-ignored Python, and control 3 below
#      plants an untracked file to prove the enumeration reaches it. Gitignored
#      files stay excluded, which is what keeps venvs and build output out.
#
# The control plants F821 (undefined name) specifically, because that is the
# rule that caught the real bug. If a future config change disables it, this
# gate fails loudly rather than going quietly blind to the defect it was
# built for.
#
# IT ALSO PLANTS ARG001 AND CHECKS THAT ANN001 IS ABSENT, and that pair is not
# belt-and-braces. The config moved from `ruff.toml` into the root
# pyproject.toml and the `--config` arguments came out, because both ruff and
# pytest DISCOVER a root pyproject.toml by walking up from the file they judge
# (docs/ci-overhaul/08-driver-contract.md section 2). Discovery is exactly the
# thing an explicit `--config` used to prove, so something else has to prove it
# now: F821 alone is reported under ruff's BUILT-IN defaults too, so a run with
# no configuration at all would satisfy the old control unchanged. ARG001 needs
# `select = ["ALL"]` and ANN001 is suppressed only by the `ignore` list, so
# requiring one present and the other absent pins that THIS repo's config is the
# one in force. See the control block itself for the measured three-way table.
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../.." && pwd)"
cd "$REPO_ROOT"

if [[ "${CI:-}" == "true" ]]; then
    RED="" GREEN="" NC=""
else
    RED=$'\033[0;31m' GREEN=$'\033[0;32m' NC=$'\033[0m'
fi

# ---- the real file list ------------------------------------------------------
# git ls-files, NOT a find: it excludes submodules and gitignored siblings under
# private/ by construction, which is what stops this gate reporting another
# repo's findings as ours.
if ! git rev-parse --is-inside-work-tree >/dev/null 2>&1; then
    echo "${RED}✗ VACUOUS INPUT${NC}: ${REPO_ROOT} is not a git work tree, so the" >&2
    echo "  file list cannot be enumerated at all. ruff exits 0 on an empty list," >&2
    echo "  which would read exactly like a clean tree. Refusing to report a pass." >&2
    exit 1
fi
# A read loop, NOT mapfile: check-commands.sh rejects mapfile as unavailable in
# the minimal CI shell, and it is right -- the gate failed on exactly that.
# ONE enumerator, used by the real list AND by control 3 below. It is a function
# specifically so the control cannot drift from the thing it guards: an earlier
# draft of control 3 ran its own copy of this query, which meant editing the real
# enumeration left the control green -- a check that cannot fail, introduced by
# the very commit that was fixing one.
enumerate_py() {
    git ls-files --cached --others --exclude-standard -- '*.py' ':!:private/**' |
        while IFS= read -r f; do [ -e "$f" ] && printf '%s\n' "$f"; done
    # `[ -e ]`: a tracked file deleted in the working tree (rm without git rm)
    # is still listed and would make ruff fail on a path that is not there.
}

# ---- CONTROL 3: the ENUMERATION must reach an UNTRACKED file -----------------
# Runs before the real list is built, because a list that omits files silently
# is not worth counting. Found live 2026-08-09: `git ls-files` alone reported
# "27 files, All checks passed!" while wl_checklist.py, the newest and second
# largest module of the Stop-hook program, was untracked and never in the list.
# The name is runtime-keyed so a crashed earlier run cannot make this pass by
# leaving its specimen behind.
enum_probe="enum_probe_$$_$(date +%s).py"
cleanup_probe() { rm -f "$REPO_ROOT/$enum_probe"; }
trap cleanup_probe EXIT
printf 'x = 1\n' >"$REPO_ROOT/$enum_probe"
if [ -z "$(enumerate_py | grep -x -- "$enum_probe")" ]; then
    echo "${RED}✗ CONTROL FAILED${NC}: the file enumeration did not return a planted" >&2
    echo "  UNTRACKED Python file (${enum_probe}), so this gate is blind to exactly" >&2
    echo "  the case that shipped on 2026-08-09. Refusing to judge the real files." >&2
    exit 1
fi
cleanup_probe

PY_FILES=()
while IFS= read -r _f; do
    [[ -n "$_f" ]] && PY_FILES+=("$_f")
done < <(enumerate_py)
count="${#PY_FILES[@]}"

# The floor is a real number, not 1. The interesting failure is a glob that
# half-breaks and still returns something. Raise it when the tree grows; a
# deliberate REMOVAL of Python from this repo should have to edit this line.
MIN_PY_FILES=10
if ((count < MIN_PY_FILES)); then
    echo "${RED}✗ VACUOUS INPUT${NC}: only ${count} Python file(s) found, expected at least ${MIN_PY_FILES}." >&2
    echo "  ruff exits 0 on an empty list, so a shrinking input reads exactly like" >&2
    echo "  a clean tree. Refusing to report a pass." >&2
    printf '    %s\n' "${PY_FILES[@]}" >&2
    exit 1
fi

# Pinned. An unpinned linter is a gate whose verdict changes without a commit,
# and this repo's .npmrc posture (minimum-release-age, no git deps) exists for
# the same reason. Bump deliberately, and re-run the whole suite when you do.
# The pin AND the resolver come from one place; see .devcontainer/toolchain.env.
# shellcheck source=/dev/null
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/scripts/lib/toolchain.sh"
toolchain_load || exit 1
RUFF_VERSION="0.16.1"

# Resolution order: an explicitly provided binary, then one on PATH, then uvx,
# which fetches the pinned version. CI installs it as a real binary (see the
# "Install ruff" step) so the network is not on the critical path there.
resolve_ruff() {
    if [[ -n "${RUFF_BIN:-}" ]]; then
        printf '%s' "$RUFF_BIN"
        return 0
    fi
    # AT THE PIN, not merely present. This branch used to accept whatever `ruff`
    # was on PATH, so a host carrying 0.5.0 linted with it while CI used the
    # pinned version and the two disagreed silently -- the same defect already
    # fixed for shfmt and shellcheck, left behind here because the class was
    # swept incompletely.
    if bin_at_pin="$(toolchain_check ruff 2>/dev/null)"; then
        printf '%s' "$bin_at_pin"
        return 0
    fi
    if command -v uvx >/dev/null 2>&1; then
        printf 'uvx ruff@%s' "$RUFF_VERSION"
        return 0
    fi
    return 1
}

if ! RUFF="$(resolve_ruff)"; then
    echo "${RED}error${NC}: ruff is not available and neither is uvx." >&2
    echo "  install one of:" >&2
    # THE STANDALONE INSTALLER IS FIRST BECAUSE IT IS THE ONE THAT WORKS HERE.
    # Measured 2026-08-27 in the devbox: `python3 -m pip` reports "No module
    # named pip" and neither uv nor uvx nor pipx is on PATH, so BOTH of the
    # options this message used to offer are dead ends on the machine most
    # likely to be reading it. A session that trusts the message concludes the
    # gate cannot be run locally and ships Python to CI unlinted -- which is
    # exactly what happened, at one ~10-minute CI round for a one-word finding.
    echo "    curl -fsSL https://astral.sh/ruff/${RUFF_VERSION}/install.sh | sh   # no pip needed" >&2
    echo "    pip install ruff==${RUFF_VERSION}" >&2
    echo "    uv tool install ruff@${RUFF_VERSION}" >&2
    echo "  or point RUFF_BIN at an existing binary:" >&2
    echo "    RUFF_BIN=/path/to/ruff npm run check:ci-python-lint" >&2
    echo "  NOT skipping: a linter that cannot run is a gate that cannot fail." >&2
    # EXIT 77 = "COULD NOT RUN", not "found something". The distinction is the
    # whole point: exit 1 said `ruff found a problem`, which is false and which
    # made a pre-push lane refuse every push on a machine that simply lacks the
    # tool. The ci-runner classifies 77 as BLOCKED -- counted, named with these
    # very lines, recorded in the push receipt and WARNED about -- but not a
    # verdict on the code.
    #
    # This is not a skip and it is not softer. Under CI the toolchain is
    # present, so 77 never fires there; if it ever did, the workflow sees a
    # plain non-zero and the lane is broken, which is correct. The sentence
    # above stays true: what changed is that "cannot run" is now SAYABLE.
    exit 77
fi

# ---- CONTROL: the linter must report a planted defect ------------------------
# THE CONTROL FILE IS NOW INSIDE THE REPO, and that is the whole change. It used
# to live in `mktemp -d` with `--config "$REPO_ROOT/ruff.toml"` pointed at it, so
# it proved "that path parses". The config moved into the root pyproject.toml
# (docs/ci-overhaul/08-driver-contract.md section 2), both tools DISCOVER that by
# walking up from the file they are judging, and the `--config` arguments came
# out -- which means a control run outside the tree would now be linted with
# ruff's DEFAULTS and would happily report F821 while proving nothing about this
# repo's configuration at all.
#
# `.ci/cache/` is the right place for it: it is inside the repo, so ancestry
# discovery reaches the same pyproject.toml the real run uses, and it is
# gitignored, so a crashed run cannot leave a stray .py that `enumerate_py`
# (which includes untracked files) would pick up on the next pass. Ruff lints an
# explicitly-named path even when it is gitignored, which is what makes the two
# properties compatible.
#
# THREE ASSERTIONS, NOT ONE, because "F821 was reported" is true under ruff's
# built-in defaults too and therefore cannot tell a resolved config from no
# config. Measured 2026-09-06 on this file:
#
#   ruff check --isolated            -> F821 only
#   ruff check --isolated --select ALL -> F821 + ARG001 + ANN001 + E501 + D + INP + CPY
#   ruff check (this repo's config)  -> F821 + ARG001
#
# so requiring F821 present, ARG001 present and ANN001 ABSENT pins all three
# facts at once: the linter runs, `select = ["ALL"]` is in force, and the `ignore`
# list is in force. Any one of them alone is satisfiable by the wrong config.
control_dir="$REPO_ROOT/.ci/cache/ruff-control-$$-$(date +%s)"
# Covers the probe too: bash EXIT traps REPLACE rather than stack, so this line
# silently disarms cleanup_probe above. The probe is already removed by here, but
# a future reordering would otherwise leak a stray .py into a SHARED worktree.
trap 'rm -rf "$control_dir"; cleanup_probe' EXIT
mkdir -p "$control_dir"
cat >"$control_dir/control.py" <<'PYEOF'
def planted(unused_arg):
    # ARG001 on `unused_arg`: only reachable via `select = ["ALL"]`.
    # ANN001 on `unused_arg` too, and it must NOT be reported: the ignore list
    # switches the whole ANN set off, so seeing it means the list did not load.
    # F821: `undefined_on_purpose` is never bound anywhere.
    return undefined_on_purpose
PYEOF

control_out="$($RUFF check --no-cache --output-format concise "$control_dir/control.py" 2>&1 || true)"
control_bad=""
grep -q 'F821' <<<"$control_out" || control_bad="F821 was not reported on a planted undefined name"
grep -q 'ARG001' <<<"$control_out" ||
    control_bad="${control_bad:+$control_bad; }ARG001 was not reported, so select = [\"ALL\"] did not reach ruff"
! grep -q 'ANN001' <<<"$control_out" ||
    control_bad="${control_bad:+$control_bad; }ANN001 WAS reported, so the ignore list did not reach ruff"
if [[ -n "$control_bad" ]]; then
    echo "${RED}✗ CONTROL FAILED${NC}: ${control_bad}." >&2
    echo "  Either the linter is not running, the root pyproject.toml did not" >&2
    echo "  resolve by ancestry, or a rule this control depends on has changed." >&2
    echo "  Any of those makes a clean result meaningless, so this gate refuses" >&2
    echo "  to judge the real files." >&2
    echo "  ruff said:" >&2
    sed 's/^/    /' <<<"$control_out" >&2
    exit 1
fi

echo "info: linting ${count} Python file(s) with ruff ${RUFF_VERSION}"

rc=0
$RUFF check --no-cache -- "${PY_FILES[@]}" || rc=$?
if ((rc != 0)); then
    echo "" >&2
    # NOT "tracked Python": the enumeration at :88 is `git ls-files --cached --others
    # --exclude-standard`, which deliberately INCLUDES untracked files, and a control
    # plants an untracked file to prove it. Saying "tracked" sent a reader hunting in
    # `git ls-files` output for a finding that was never going to be there. Found
    # 2026-09-07 by a port agent whose every finding was in an untracked file.
    echo "${RED}✗${NC} ruff reported findings in Python this gate scans (tracked and untracked)." >&2
    echo "  Fix them. Do NOT add a per-line noqa to get past this gate: if a rule" >&2
    echo "  is genuinely wrong for this repo it is disabled in pyproject.toml with a" >&2
    echo "  stated reason, where it is reviewable." >&2
    exit 1
fi

# Name the files that DIFFER, not the whole list. This used to print every
# tracked .py after "Run: ruff format", which read as "reformat the tree", and
# ruff 0.16 moved the path onto a `-->` line under "unformatted:", so the three
# real offenders were easy to miss among 80 names (2026-09-02).
format_out="$($RUFF format --check --no-cache -- "${PY_FILES[@]}" 2>&1)" || {
    echo "$format_out" >&2
    # STRIP ANSI FIRST. ruff colours its output even through a pipe, so the
    # `-->` lines arrive as `\e[1m\e[94m--> \e[0m<path>` and a plain anchored
    # sed matches nothing -- which silently fell back to naming all 80 files,
    # the very thing this block exists to stop. Same shape as the `bws` colour
    # defect found the same day: a tool that does not test for a tty.
    differing="$(printf '%s\n' "$format_out" | sed -e 's/\x1b\[[0-9;]*m//g' -e 's/^ *--> \([^:]*\):.*/\1/p' -n | sort -u | tr '\n' ' ')"
    echo "" >&2
    echo "${RED}✗${NC} Python formatting differs. Run: ruff format --no-cache -- ${differing:-${PY_FILES[*]}}" >&2
    exit 1
}
echo "$format_out"

# EXE001 IS INVISIBLE FROM HERE, so it is checked directly rather than trusted.
# Measured 2026-08-28: CI failed `Python lint + format (ruff)` with two EXE001
# findings ("Shebang is present but file is not executable"), while THIS gate --
# same ruff 0.16.1, same config, same 66 files -- reported "All checks
# passed". A fresh 644 file carrying a shebang, placed in the repo and linted
# with an explicit `--select EXE`, still produced no finding on this machine.
# So the divergence is environmental and NOT something this gate can fix by
# arguing with ruff; the answer is to check the property ourselves.
#
# THE PROPERTY IS THE GIT MODE, NOT THE DISK MODE, and that distinction is the
# whole point: CI lints a fresh checkout, so what it sees is whatever git
# recorded. A file chmod +x on disk AFTER `git add` is 755 locally and 644 in
# CI, which is exactly how two files passed here and failed there.
#
# Fix a violation with `git update-index --chmod=+x <file>` (or remove the
# shebang if the file is a library). Both directions are checked: an executable
# file with no shebang is EXE002 and is just as much a defect.
exe_bad=0
exe_seen=0
while IFS= read -r mode_path; do
    mode="${mode_path%% *}"
    file="${mode_path#* }"
    [ -f "$file" ] || continue
    exe_seen=$((exe_seen + 1))
    has_shebang=0
    [ "$(head -c2 "$file" 2>/dev/null)" = "#!" ] && has_shebang=1
    if [ "$has_shebang" = 1 ] && [ "$mode" = "100644" ]; then
        echo "${RED}✗${NC} $file has a shebang but git mode is 100644 (EXE001 in CI)" >&2
        echo "    fix: git update-index --chmod=+x $file" >&2
        exe_bad=$((exe_bad + 1))
    elif [ "$has_shebang" = 0 ] && [ "$mode" = "100755" ]; then
        echo "${RED}✗${NC} $file is git mode 100755 but has no shebang (EXE002 in CI)" >&2
        echo "    fix: git update-index --chmod=-x $file" >&2
        exe_bad=$((exe_bad + 1))
    fi
done < <(git -C "$REPO_ROOT" ls-files -s -- '*.py' ':!:private/**' | awk '{print $1, $4}')

# ANTI-VACUITY. An empty enumeration would make this silent forever, which is
# the failure the file-list section above already documents for ruff itself.
if [ "$exe_seen" -eq 0 ]; then
    echo "${RED}✗${NC} the shebang/mode scan enumerated ZERO tracked Python files." >&2
    echo "  A scan that sees nothing cannot fail, so its silence proves nothing." >&2
    exit 1
fi

if [ "$exe_bad" -gt 0 ]; then
    echo "" >&2
    echo "${RED}✗${NC} ${exe_bad} Python file(s) have a git mode CI will reject." >&2
    exit 1
fi

echo "${GREEN}✓${NC} ${count} Python file(s) pass ruff lint and format" \
    "(+ ${exe_seen} checked for shebang/mode agreement)"
