#!/bin/bash
# Drives the REAL scan in .ci/scripts/quality/check_bws_map.py against fixture
# trees, which its internal selftest() cannot do.
#
# WHY BOTH EXIST. selftest() proves the pure logic -- the request parser and every
# way of writing a bad exemption -- and it runs before any verdict, so a broken
# instrument never judges anything. What it CANNOT reach is assertions 5-9, which
# are defined over the tree: the map, the allowlist, the reachability record, the
# workflows and the deploy scripts. Those had no fixture coverage at all, and
# they are about to be the sole guard on every credential once GitHub secrets go
# away (agent/PLAN-github-secrets-removal.md). A gate whose only controls are
# internal is thinner than this repo's standard for far less load-bearing checks.
#
# BWS_MAP_ROOT re-points every ROOT-derived path at a fixture. It is not an
# escape hatch: the anti-vacuity clauses fail on a tree that holds nothing, which
# the last case here proves.

set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test gate
source "$SCRIPT_DIR/../lib/test-helpers.sh"

GATE="$REPO_ROOT/.ci/scripts/quality/check_bws_map.py"

# A minimal tree the gate can judge: one mapped+requested name, one mapped name
# with no GitHub twin (so it needs an exemption), and the scaffolding every
# assertion reads.
fixture() {
    local d="$1"
    mkdir -p "$d/.ci/config" "$d/.ci/scripts/deploy" "$d/.github/workflows" \
        "$d/.github/actions" "$d/scripts/dev"
    (cd "$d" && git init -q .)
    cat >"$d/.ci/config/bws-secret-map.json" <<'MAP'
{ "refreshed_at": "2099-01-01T00:00:00Z", "project": "p",
  "secrets": { "ALPHA_TOKEN": { "id": "aaaaaaaa-0000-4000-8000-000000000001" },
               "ORPHAN_TOKEN": { "id": "aaaaaaaa-0000-4000-8000-000000000002" } } }
MAP
    cat >"$d/.ci/config/bws-unrequested.json" <<'EX'
{ "exemptions": { "ORPHAN_TOKEN": { "kind": "no-github-twin", "reason": "fixture" },
                  "PREFIX_EU": { "kind": "no-github-twin", "reason": "built by SUFFIX expansion, no twin" } } }
EX
    cat >"$d/.ci/config/secret-reachability.json" <<'RE'
{ "refreshed_at": "2099-01-01T00:00:00Z",
  "repos": { "console": { "ALPHA_TOKEN": { "reachable": true, "via": "org:all" } } } }
RE
    echo '{"regions":[{"secretSuffix":"EU"}]}' >"$d/regions.json"
    printf 'x_var="PREFIX_${SUFFIX}"\n' >"$d/.ci/scripts/deploy/build.sh"
    printf 'RENAMES: list[tuple[str, str]] = [\n    ("OLD_ALPHA", "ALPHA_TOKEN"),\n]\n' \
        >"$d/scripts/dev/secret-rename.py"
    cat >"$d/.github/workflows/w.yml" <<'WF'
jobs:
  j:
    steps:
      - uses: ./.github/actions/bws-secrets
        with:
          secrets: |
            ALPHA_TOKEN > BWS_ALPHA_TOKEN
      - env:
          GH_ALPHA_TOKEN: ${{ secrets.ALPHA_TOKEN }}
        run: echo hi
WF
    # PREFIX_EU must be mapped or exempt, and ALPHA_TOKEN/ORPHAN_TOKEN must be
    # spelled somewhere the corpus scan can see.
    python3 - "$d" <<'PY'
import json, pathlib, sys
d = pathlib.Path(sys.argv[1])
m = json.loads((d / ".ci/config/bws-secret-map.json").read_text())
m["secrets"]["PREFIX_EU"] = {"id": "aaaaaaaa-0000-4000-8000-000000000003"}
(d / ".ci/config/bws-secret-map.json").write_text(json.dumps(m))
(d / ".ci/scripts/deploy/build.sh").write_text(
    'x_var="PREFIX_${SUFFIX}"\n# ORPHAN_TOKEN PREFIX_EU are named here so the corpus scan sees them\n')
PY
    (cd "$d" && git add -A && git -c user.email=t@t -c user.name=t commit -qm x)
}

run_gate() {
    (
        set +e
        BWS_MAP_ROOT="$1" BWS_MIN_MAP_ENTRIES=1 BWS_MIN_CALLERS=1 \
            python3 "$GATE" 2>&1
        echo "rc=$?"
    )
}

test_clean_fixture_passes() {
    local d="$1"
    fixture "$d"
    local out
    out="$(run_gate "$d")"
    assert_contains "$out" "rc=0" "a coherent fixture tree must pass, or every case below proves nothing"
    log_pass "CONTROL: a coherent fixture tree passes"
}

test_unexempted_orphan_reds() {
    local d="$1"
    fixture "$d"
    echo '{ "exemptions": { "UNRELATED": { "kind": "no-github-twin", "reason": "x" } } }' \
        >"$d/.ci/config/bws-unrequested.json"
    local out
    out="$(run_gate "$d")"
    assert_contains "$out" "ORPHAN_TOKEN" "assertion 5 names the unexempted mapped name"
    assert_contains "$out" "rc=1" "and fails"
    log_pass "assertion 5: a mapped name nobody requests and nobody exempts fails"
}

test_twin_appearing_kills_the_exemption() {
    local d="$1"
    fixture "$d"
    python3 - "$d" <<'PY'
import json, pathlib, sys
p = pathlib.Path(sys.argv[1]) / ".ci/config/secret-reachability.json"
d = json.loads(p.read_text())
d["repos"]["console"]["ORPHAN_TOKEN"] = {"reachable": True, "via": "org:all"}
p.write_text(json.dumps(d))
PY
    local out
    out="$(run_gate "$d")"
    assert_contains "$out" "IS a console-reachable org secret" "the re-derivation notices the twin appeared"
    assert_contains "$out" "rc=1" "and fails"
    log_pass "no-github-twin is RE-DERIVED: creating the org secret ends the exemption"
}

test_empty_tree_is_not_a_pass() {
    local d="$1"
    mkdir -p "$d/empty"
    local out
    out="$(run_gate "$d/empty")"
    assert_contains "$out" "rc=1" "an empty tree must fail, or BWS_MAP_ROOT is an escape hatch"
    log_pass "the fixture override cannot be used to pass vacuously"
}

log_test "test-bws-map"
with_temp_dir test_clean_fixture_passes
with_temp_dir test_unexempted_orphan_reds
with_temp_dir test_twin_appearing_kills_the_exemption
with_temp_dir test_empty_tree_is_not_a_pass
echo ""
log_pass "all tests passed"
