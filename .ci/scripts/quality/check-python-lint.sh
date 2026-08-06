#!/usr/bin/env bash
# Lint every tracked Python file with ruff, under the repo's ruff.toml.
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
#
# The control plants F821 (undefined name) specifically, because that is the
# rule that caught the real bug. If a future config change disables it, this
# gate fails loudly rather than going quietly blind to the defect it was
# built for.
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
mapfile -t PY_FILES < <(git ls-files -- '*.py' ':!:private/**')
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
RUFF_VERSION="0.16.1"

# Resolution order: an explicitly provided binary, then one on PATH, then uvx,
# which fetches the pinned version. CI installs it as a real binary (see the
# "Install ruff" step) so the network is not on the critical path there.
resolve_ruff() {
    if [[ -n "${RUFF_BIN:-}" ]]; then
        printf '%s' "$RUFF_BIN"
        return 0
    fi
    if command -v ruff >/dev/null 2>&1; then
        printf 'ruff'
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
    echo "    pip install ruff==${RUFF_VERSION}" >&2
    echo "    uv tool install ruff@${RUFF_VERSION}" >&2
    echo "  or point RUFF_BIN at an existing binary." >&2
    echo "  NOT skipping: a linter that cannot run is a gate that cannot fail." >&2
    exit 1
fi

# ---- CONTROL: the linter must report a planted defect ------------------------
# Run from a scratch dir OUTSIDE the repo so ruff.toml is not discovered by
# ancestry, then point --config at it explicitly. That way this also proves the
# config path the real run uses actually resolves.
control_dir="$(mktemp -d)"
trap 'rm -rf "$control_dir"' EXIT
cat >"$control_dir/control.py" <<'PYEOF'
def planted():
    # F821: `undefined_on_purpose` is never bound anywhere.
    return undefined_on_purpose
PYEOF

control_out="$($RUFF check --config "$REPO_ROOT/ruff.toml" --no-cache \
    --output-format concise "$control_dir/control.py" 2>&1 || true)"
if ! grep -q 'F821' <<<"$control_out"; then
    echo "${RED}✗ CONTROL FAILED${NC}: ruff did not report F821 on a planted undefined name." >&2
    echo "  Either the linter is not running, the config did not resolve, or F821" >&2
    echo "  has been disabled. Any of those makes a clean result meaningless, so" >&2
    echo "  this gate refuses to judge the real files." >&2
    echo "  ruff said:" >&2
    sed 's/^/    /' <<<"$control_out" >&2
    exit 1
fi

echo "info: linting ${count} Python file(s) with ruff ${RUFF_VERSION}"

rc=0
$RUFF check --config "$REPO_ROOT/ruff.toml" --no-cache -- "${PY_FILES[@]}" || rc=$?
if ((rc != 0)); then
    echo "" >&2
    echo "${RED}✗${NC} ruff reported findings in tracked Python." >&2
    echo "  Fix them. Do NOT add a per-line noqa to get past this gate: if a rule" >&2
    echo "  is genuinely wrong for this repo it is disabled in ruff.toml with a" >&2
    echo "  stated reason, where it is reviewable." >&2
    exit 1
fi

$RUFF format --config "$REPO_ROOT/ruff.toml" --check --no-cache -- "${PY_FILES[@]}" || {
    echo "" >&2
    echo "${RED}✗${NC} Python formatting differs. Run: ruff format ${PY_FILES[*]}" >&2
    exit 1
}

echo "${GREEN}✓${NC} ${count} Python file(s) pass ruff lint and format"
