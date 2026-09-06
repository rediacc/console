#!/bin/bash
# Local proxy for a workspace unit-test suite that CI runs and the local gate
# set does not.
#
#   proxy-unit-tests.sh <workspace> <npm script key>
#
# WHAT IT CLOSES. .ci/scripts/test/run-unit.sh runs four suites: @rediacc/shared,
# @rediacc/cli (unit), @rediacc/provisioning and @rediacc/e2e-tests (unit). The
# manifest registers only cli, shared, www and workers, so provisioning's 11
# tests and e2e-tests' 63 unit tests have never been part of `npm run ci`. They
# are cheap (508 ms and 697 ms measured) and were missing for no reason beyond
# nobody adding the row.
#
# WHY A WRAPPER AND NOT A BARE `npm run test -w <ws>`, which is what the four
# existing check:test-* keys are. Three reasons, each a real failure shape:
#
#  1. THE 77 CONTRACT. A bare npm key cannot distinguish "the suite failed" from
#     "vitest is not installed on this host". Both exit 1. A proxy must say
#     cannot-run rather than let an unmeasured surface look like a verdict.
#  2. `npm run <name>` FOR A SCRIPT THAT DOES NOT EXIST EXITS 1 WITH ZERO BYTES
#     ON BOTH STREAMS under --silent. That is indistinguishable from a suite
#     failing for a real reason, and it is exactly what a workspace rename or a
#     dropped script key produces. So the key's existence is checked FIRST, and
#     its absence is a loud failure naming the workspace, never a 77.
#  3. ANTI-VACUITY. `vitest run` over a glob that matches no file exits 0. This
#     reads the "Tests N passed" summary back and REFUSES a run that executed
#     zero tests, which is the shape a broken include pattern produces.

set -uo pipefail

PROXY_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
ROOT_DIR="$(cd "$PROXY_DIR/../../../.." && pwd)"
# shellcheck source=./proxy-lib.sh
source "$PROXY_DIR/proxy-lib.sh"

if [[ "${1:-}" == "--selftest" ]]; then
    proxy_lib_selftest
    exit $?
fi

WORKSPACE="${1:-}"
SCRIPT_KEY="${2:-}"
if [[ -z "$WORKSPACE" || -z "$SCRIPT_KEY" ]]; then
    echo "usage: proxy-unit-tests.sh <workspace> <npm script key>" >&2
    exit 2
fi

proxy_init "unit-tests/${WORKSPACE}#${SCRIPT_KEY}" "npm run ${SCRIPT_KEY} -w ${WORKSPACE}"

cd "$ROOT_DIR" || exit 2

proxy_need_cmd node "./run.sh setup"
proxy_need_cmd npm "./run.sh setup"
proxy_need_file "$ROOT_DIR/node_modules" "npm install && npm run install:natives"
proxy_need_file "$ROOT_DIR/node_modules/.bin/vitest" "npm install && npm run install:natives"
proxy_preflight

# THE MISSING-KEY TRAP, closed before anything is run. Resolve the workspace
# directory from its name rather than assuming packages/<basename>, then read
# the key out of its package.json.
# Resolved from the root package.json `workspaces` globs, NOT with `npm query`:
# same answer, measured 31 ms against 1,056 ms, and it does not depend on npm
# query's output schema staying put. A name outside the workspace set does not
# resolve, which is the loud failure below rather than a silent skip.
WS_DIR="$(node -e '
      const fs=require("fs"),path=require("path");
      const ws=require("./package.json").workspaces||[];
      for(const g of ws){
        for(const d of fs.globSync(g)){
          const pj=path.join(d,"package.json");
          if(!fs.existsSync(pj))continue;
          if(JSON.parse(fs.readFileSync(pj,"utf8")).name===process.argv[1]){console.log(d);process.exit(0);}
        }
      }' "$WORKSPACE" 2>/dev/null || true)"

# THIS IS THE VACUITY REFUSAL for the workspace glob above, and it is worded to
# say so. The globSync enumerates every workspace directory; if that enumeration
# comes back empty, or resolves nothing matching this name, the proxy must refuse
# rather than carry on, because a proxy that skips its subject and exits 0 turns
# an unmeasured surface into a green one. check:ci-enumeration-vacuity could not
# SEE this guard until the word was here: its detector keys on VACUOUS, a MIN_
# name or the word floor, and a correct refusal in different words reads to it as
# no refusal at all.
if [[ -z "$WS_DIR" || ! -f "$WS_DIR/package.json" ]]; then
    proxy_fail "VACUOUS: workspace '$WORKSPACE' resolves to no package.json in any workspace glob; npm run would exit 1 with no output at all"
    proxy_finish
fi
proxy_pass "workspace $WORKSPACE resolves to ${WS_DIR#"$ROOT_DIR"/}"

# require() needs an absolute or ./-prefixed specifier; a bare "packages/x/
# package.json" is read as a MODULE name and throws MODULE_NOT_FOUND, which
# would make every workspace look like it was missing the key.
if node -e '
      const fs=require("fs"),path=require("path");
      const p=JSON.parse(fs.readFileSync(path.resolve(process.argv[1],"package.json"),"utf8"));
      process.exit(p.scripts && p.scripts[process.argv[2]] ? 0 : 1);
    ' "$WS_DIR" "$SCRIPT_KEY" 2>/dev/null; then
    proxy_pass "script key '$SCRIPT_KEY' exists in $WORKSPACE"
else
    proxy_fail "script key '$SCRIPT_KEY' is NOT in ${WS_DIR#"$ROOT_DIR"/}/package.json. 'npm run $SCRIPT_KEY' would exit 1 with zero bytes on both streams, which reads exactly like a failing suite. Fix the key, do not chase the empty failure."
    proxy_finish
fi

OUT="$(mktemp)"
ERR="$(mktemp)"
trap 'rm -f "$OUT" "$ERR"' EXIT

npm run "$SCRIPT_KEY" -w "$WORKSPACE" >"$OUT" 2>"$ERR"
RC=$?
BOTH="$(cat "$OUT" "$ERR")"

if [[ $RC -eq 0 ]]; then
    proxy_pass "npm run $SCRIPT_KEY -w $WORKSPACE exited 0"
else
    proxy_fail "npm run $SCRIPT_KEY -w $WORKSPACE exited $RC"
    echo "  --- stdout ---" >&2
    cat "$OUT" >&2
    echo "  --- stderr ---" >&2
    cat "$ERR" >&2
fi

# vitest prints "Tests  N passed (N)"; zero executed tests is a green that means
# nothing, so it is a failure here.
SUMMARY="$(printf '%s\n' "$BOTH" | grep -oE 'Tests +[0-9]+ (passed|failed)' | tail -1)"
COUNT="$(printf '%s' "$SUMMARY" | grep -oE '[0-9]+' | tail -1)"
FILES="$(printf '%s\n' "$BOTH" | grep -oE 'Test Files +[0-9]+ ' | grep -oE '[0-9]+' | tail -1)"
if [[ -z "$COUNT" ]]; then
    proxy_fail "no 'Tests N passed' summary in either stream; the runner produced no readable count, so this run proves nothing"
elif [[ "$COUNT" -eq 0 ]]; then
    proxy_fail "the runner executed 0 tests; an empty include pattern exits 0 and is the vacuity this check exists for"
else
    proxy_pass "$COUNT test(s) across ${FILES:-?} file(s) in $WORKSPACE"
fi

proxy_finish
