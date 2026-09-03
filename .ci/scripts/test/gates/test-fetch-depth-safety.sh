#!/bin/bash
# gate-test:fetch-depth-safety -- `git fetch --depth` may not truncate a full clone.
#
# WHAT THIS IS ABOUT, measured 2026-09-03 rather than reasoned about. `--depth` on
# a fetch is not a limit on what that fetch transfers; on a complete repository it
# WRITES A GRAFT and truncates the whole history. Against the real remote:
#
#     $ git rev-list --count refs/remotes/pull/585/merge   # 2467
#     $ git fetch --no-tags --depth=50 origin +refs/heads/main:refs/remotes/origin/main
#     $ git rev-list --count refs/remotes/pull/585/merge   # 114, .git/shallow: 1 graft
#
# The line that did it lived in packages/www/scripts/lib/translation-freshness-git.js
# and ran inside check:i18n. The job's actions/checkout had deliberately taken
# `fetch-depth: 0`. Four steps later check:ci-plan-housekeeping refused with
# "SHALLOW at a boundary that 58 plan(s) sit on", and the checkout -- which was
# innocent, and correct -- is what every reader went to look at.
#
# THE DAMAGE IS ALWAYS SOMEBODY ELSE'S, which is what makes this class worth a
# gate: the script that truncates history is not the script that fails.
#
# Exit 1 on any finding, 2 on a failed control.
set -uo pipefail
ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../../../.." && pwd)"
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT
FAIL=0
pass() { echo "  PASS  $1"; }
fail() {
    echo "  FAIL  $1"
    [[ -n "${2:-}" ]] && echo "        $2"
    FAIL=$((FAIL + 1))
}

# A fixture with MORE than 50 commits, or --depth=50 truncates nothing and every
# case below passes for the wrong reason.
make_fixture() {
    local dir="$1" origin="$1/origin" work="$1/work"
    mkdir -p "$origin"
    git init --quiet --bare "$origin"
    git init --quiet --initial-branch=main "$work"
    git -C "$work" config user.email t@example.com
    git -C "$work" config user.name t
    local i
    for i in $(seq 1 60); do
        echo "$i" >"$work/f.txt"
        git -C "$work" add f.txt
        git -C "$work" commit --quiet -m "c$i"
    done
    git -C "$work" remote add origin "$origin"
    git -C "$work" push --quiet origin main 2>/dev/null
    rm -rf "$dir/clone"
    git clone --quiet "$origin" "$dir/clone"
    git -C "$dir/clone" config user.email t@example.com
    git -C "$dir/clone" config user.name t
}

is_shallow() { [[ "$(git -C "$1" rev-parse --is-shallow-repository)" == "true" ]]; }

echo "fetch-depth safety: controls first, then the verdict"

# ---------------------------------------------------------------------------
# CONTROL: the fixture must be able to SHOW the defect. Without this every case
# below is a check that cannot fail.
# ---------------------------------------------------------------------------
make_fixture "$TMP/plant"
before="$(git -C "$TMP/plant/clone" rev-list --count HEAD)"
git -C "$TMP/plant/clone" fetch --no-tags --depth=50 origin \
    '+refs/heads/main:refs/remotes/origin/main' >/dev/null 2>&1
after="$(git -C "$TMP/plant/clone" rev-list --count HEAD)"
if is_shallow "$TMP/plant/clone" && ((after < before)); then
    pass "CONTROL: the pre-fix command truncates a full clone ($before -> $after commits)"
else
    fail "CONTROL: the pre-fix command did NOT truncate the fixture" \
        "shallow=$(git -C "$TMP/plant/clone" rev-parse --is-shallow-repository) $before -> $after"
fi

# ---------------------------------------------------------------------------
# THE REAL ENTRY POINT, driven against a real repository. detectChangedFiles is
# what validate:translation-freshness calls, and tryFetchBaseRef is private to
# the module -- so this drives the thing that actually runs in CI.
# ---------------------------------------------------------------------------
make_fixture "$TMP/real"
git -C "$TMP/real/clone" checkout --quiet -b feature
echo change >"$TMP/real/clone/g.txt"
git -C "$TMP/real/clone" add g.txt
git -C "$TMP/real/clone" commit --quiet -m "feature commit"
before="$(git -C "$TMP/real/clone" rev-list --count HEAD)"
MOD="$ROOT_DIR/packages/www/scripts/lib/translation-freshness-git.js"
if [[ ! -f "$MOD" ]]; then
    fail "the module under test is missing" "$MOD"
else
    env -u TRANSLATION_FRESHNESS_CHANGED_FILES node --input-type=module -e "
      import { detectChangedFiles } from '$MOD';
      detectChangedFiles('$TMP/real/clone', 'main');
    " >/dev/null 2>&1
    after="$(git -C "$TMP/real/clone" rev-list --count HEAD)"
    if is_shallow "$TMP/real/clone"; then
        fail "detectChangedFiles SHALLOWIFIED a full clone ($before -> $after commits)" \
            "the --depth must be conditional on the clone already being shallow"
    else
        pass "detectChangedFiles leaves a full clone full ($after commits, no graft)"
    fi
fi

# ---------------------------------------------------------------------------
# CONTROL ON THE FIX: an already-shallow clone must still work. The depth was an
# optimisation for exactly that case, and removing it everywhere would be the
# other kind of wrong.
# ---------------------------------------------------------------------------
make_fixture "$TMP/shallow"
rm -rf "$TMP/shallow/clone"
git clone --quiet --depth 5 "file://$TMP/shallow/origin" "$TMP/shallow/clone"
git -C "$TMP/shallow/clone" config user.email t@example.com
git -C "$TMP/shallow/clone" config user.name t
if ! is_shallow "$TMP/shallow/clone"; then
    fail "CONTROL: the shallow fixture is not shallow, so the case proves nothing"
else
    env -u TRANSLATION_FRESHNESS_CHANGED_FILES node --input-type=module -e "
      import { detectChangedFiles } from '$MOD';
      detectChangedFiles('$TMP/shallow/clone', 'main');
    " >/dev/null 2>&1
    rc=$?
    if ((rc == 0)); then
        pass "CONTROL: an already-shallow clone is still handled (exit 0)"
    else
        fail "an already-shallow clone now fails (exit $rc)"
    fi
fi

# ---------------------------------------------------------------------------
# THE CLASS, not the instance. Any script that hands `--depth` to `git fetch`
# must also be able to tell whether the repository is already shallow. That is a
# weak rule on purpose: it does not try to prove the guard is correctly placed,
# only that the author knew the question existed.
# ---------------------------------------------------------------------------
# COMMENTS ARE NOT CODE, and the first run of this sweep proved it: it named
# claude-review-reusable.yml, whose only match is PROSE describing what a
# third-party action does inside its own workspace. A gate whose first finding is
# a false positive teaches the reader to skim its output. Stated blind spot: a
# real command sitting inside a heredoc that opens with `#` is missed.
real_fetch_depth() {
    awk '
        { line = $0; sub(/^[ \t-]+/, "", line) }
        line ~ /^(#|\/\/|\*)/ { next }
        /git +fetch[^|&;]*--depth/ { found = 1 }
        END { exit found ? 0 : 1 }
    ' "$1"
}

offenders=""
while IFS= read -r f; do
    [[ -f "$ROOT_DIR/$f" ]] || continue
    real_fetch_depth "$ROOT_DIR/$f" || continue
    grep -qE 'is-shallow-repository|/shallow|isShallow' "$ROOT_DIR/$f" && continue
    offenders+="    $f"$'\n'
done < <(git -C "$ROOT_DIR" ls-files '*.sh' '*.js' '*.cjs' '*.mjs' '*.ts' '*.py' '*.yml' |
    grep -v '^.ci/scripts/test/gates/test-fetch-depth-safety.sh$')

if [[ -n "$offenders" ]]; then
    fail "these hand --depth to git fetch with no notion of shallowness:" $'\n'"$offenders"
else
    pass "every git-fetch --depth site can tell whether the repo is already shallow"
fi

# CONTROL ON THAT SWEEP: it must be looking at a real corpus, and it must be able
# to see a violation. A grep over an empty file list passes silently forever.
n_scanned="$(git -C "$ROOT_DIR" ls-files '*.sh' '*.js' '*.cjs' '*.mjs' '*.ts' '*.py' '*.yml' | wc -l)"
if ((n_scanned < 500)); then
    fail "CONTROL: the sweep enumerated only $n_scanned file(s); the corpus was lost"
else
    pass "CONTROL: the sweep enumerated $n_scanned tracked file(s)"
fi
printf 'git fetch --depth=1 origin main\n' >"$TMP/planted.sh"
if real_fetch_depth "$TMP/planted.sh" &&
    ! grep -qE 'is-shallow-repository|/shallow|isShallow' "$TMP/planted.sh"; then
    pass "CONTROL: a planted unguarded --depth is detected by the same expressions"
else
    fail "CONTROL: the sweep's own expressions do not flag a planted violation"
fi
# ... and the comment filter must not swallow real code: a commented mention is
# skipped, a command is not.
printf '# git fetch --depth=1 origin main -- prose about someone else\n' >"$TMP/prose.sh"
if real_fetch_depth "$TMP/prose.sh"; then
    fail "CONTROL: a commented mention is still counted as a command"
else
    pass "CONTROL: a commented mention is not counted as a command"
fi

echo
if ((FAIL > 0)); then
    echo "✗ fetch-depth safety: $FAIL failure(s)" >&2
    exit 1
fi
echo "✓ fetch-depth safety: no script can truncate a full clone by accident"
# Stated blind spot: the sweep enumerates THIS repository only. Checked by hand on
# 2026-09-03 -- account, renet, elite and homebrew-tap carry no `git fetch --depth`
# at all -- and a submodule script runs against the submodule's own git dir anyway,
# so it cannot truncate the superproject the way this gate's subject did.
echo "  Blind spot: submodules are not swept (checked by hand 2026-09-03: none carry one)"
