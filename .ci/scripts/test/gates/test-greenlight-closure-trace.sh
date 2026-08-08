#!/bin/bash
# Completeness gate for the cross-PR greenlight closure table,
# .ci/scripts/ci/greenlight.cjs::CLOSURES.
#
# WHAT THIS GUARDS, and why it is a different question from test-greenlight.sh.
# That file proves the ENGINE obeys its rules and that every path the table
# declares still exists. Neither property notices the failure that actually
# ships: a workflow gains a step, the job starts consuming an input nobody
# added to the table, and the greenlight keeps firing on evidence that no
# longer covers what the job runs. Every declared path still exists, every rule
# still holds, and a PR editing that new input inherits a green it did not earn.
# That is a WRONG SKIP, the one failure class this design must not risk.
#
# THE PROPERTY. For each key, derive the set of repo paths its DEFINING
# workflow job block references, then assert the table COVERS every one of
# them, either as an exact entry or as an ancestor directory entry. The
# direction is one-way on purpose: derived must be a subset of declared.
# Declaring MORE than the derivation finds is always legal, because a wider
# closure only ever makes a greenlight rarer, and several keys deliberately
# carry inputs no workflow text can reveal (an artifact's producer recipe, an
# image's build context, a lockfile that keys a cache).
#
# WHAT IS DELIBERATELY NOT DERIVED. Which SUBMODULES a job reads. `submodules:
# true` checks out all four gitlinks whatever the job then touches, so the
# workflow text cannot distinguish "renet is an input" from "renet happens to
# be on disk", and asserting all four would force every key to refuse on every
# unrelated pointer bump. Conversely install_methods and update_flow pin
# pointers they never check out, because the artifact under test embeds them.
# The one derivable half IS asserted: a job that checks out submodules must
# pin at least one, so a key cannot run against submodule code while claiming
# no pointer matters.
#
# THE CONTROL IS BUILT IN. The checker is a standalone program driven from a
# table file, so the last case re-runs it against a MUTATED table with one
# required entry deleted and asserts it goes red. Without that, a checker whose
# derivation silently produced the empty set would pass this file forever while
# proving nothing.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../../../.." && pwd)"
# shellcheck source=../lib/test-helpers.sh
# BLOCKER: shared assertion helpers used by every .ci/scripts/test/gates/test-*.sh
source "$SCRIPT_DIR/../lib/test-helpers.sh"

ENGINE="$REPO_ROOT/.ci/scripts/ci/greenlight.cjs"

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

CHECKER="$WORK/trace.cjs"

# ---------------------------------------------------------------------------
# THE CHECKER. Written out rather than inlined at its call site so the control
# case can drive the identical program over a deliberately broken table.
#
#   node trace.cjs <repo-root> <table.json> [key ...]
#
# Prints one `UNCOVERED <key> <path> <why>` line per finding on stdout and
# exits 1 if there were any; prints a `DERIVED <key> <n>` line per key either
# way, so an empty derivation is visible rather than silent.
# ---------------------------------------------------------------------------
cat >"$CHECKER" <<'CHECKER_EOF'
'use strict';
const fs = require('fs');
const path = require('path');

const root = process.argv[2];
const table = JSON.parse(fs.readFileSync(process.argv[3], 'utf8'));
const only = process.argv.slice(4);

// Where each key is DEFINED. `jobs` empty means "every job in the file", which
// is the right reading for a workflow that exists to serve exactly one key.
const SITES = {
  e2e_workers: { wf: 'ct-tests.yml', jobs: ['test-e2e-workers'] },
  e2e_k8s_multinode: { wf: 'ct-tests.yml', jobs: ['test-e2e-k8s-multinode'] },
  e2e_ceph_workers: { wf: 'ct-tests.yml', jobs: ['test-e2e-ceph-workers'] },
  e2e_k8s_ceph: { wf: 'ct-tests.yml', jobs: ['test-e2e-k8s-ceph'] },
  e2e_k8s: { wf: 'ct-tests.yml', jobs: ['test-e2e-k8s'] },
  e2e_migrate: { wf: 'ct-tests.yml', jobs: ['test-e2e-migrate'] },
  e2e_ceph: { wf: 'ct-tests.yml', jobs: ['test-e2e-ceph'] },
  fork_isolation: { wf: 'ct-tests.yml', jobs: ['test-fork-isolation'] },
  renet: { wf: 'ct-tests.yml', jobs: ['test-renet'] },
  ops: { wf: 'ci-ops-test.yml', jobs: [] },
  install_methods: { wf: 'ct-install-methods.yml', jobs: [] },
  account_e2e: { wf: 'ct-tests.yml', jobs: ['test-account-e2e'] },
  drills: { wf: 'ct-tests.yml', jobs: ['test-drills'] },
  elite_run: { wf: 'ci.yml', jobs: ['elite-run-test'] },
  license_enforcement: { wf: 'ct-tests.yml', jobs: ['test-license-enforcement'] },
  update_flow: { wf: 'ct-update-flow.yml', jobs: [] },
  package_tests: { wf: 'ci.yml', jobs: ['package-tests'] },
  unit: { wf: 'ct-tests.yml', jobs: ['test-unit'] },
};

// Full-line comments are dropped before ANY scanning. Both the workflows and
// the scripts document themselves with usage examples that name real paths
// ("# .ci/scripts/test/run-e2e.sh --workers 2"), and reading those as inputs
// would manufacture requirements out of prose. An inline trailing `#` is left
// alone: stripping it would need to know whether the `#` is inside a quoted
// shell word, and guessing wrong deletes a real path.
// `sparse-checkout:` goes with them, and for the same reason: it names what
// the runner FETCHES, not what the job reads. ct-install-methods.yml:222
// sparse-checks-out `.ci/scripts` so its aggregator can reach one file in it,
// and reading that as an input would put the entire script tree in the widest
// closure in the table, refusing a greenlight on every harness edit. The file
// the aggregator actually runs is named in its `run:` step and derived there.
const stripComments = (text) =>
  text
    .split('\n')
    .filter((line) => !/^\s*#/.test(line) && !/^\s*sparse-checkout:/.test(line))
    .join('\n');

// A job block: from `^  <id>:` to the next line at the same indent. Line-based
// rather than YAML-parsed because there is no parser available here and the
// shape is fixed by actionlint on the way in.
const jobBlock = (text, id) => {
  const lines = text.split('\n');
  const start = lines.findIndex((l) => l === `  ${id}:`);
  if (start === -1) return null;
  let end = lines.length;
  for (let i = start + 1; i < lines.length; i++) {
    if (/^ {2}[A-Za-z0-9_-]+:/.test(lines[i])) {
      end = i;
      break;
    }
  }
  return lines.slice(start, end).join('\n');
};

const allJobIds = (text) => {
  const ids = [];
  const lines = text.split('\n');
  let inJobs = false;
  for (const line of lines) {
    if (/^jobs:/.test(line)) {
      inJobs = true;
      continue;
    }
    if (!inJobs) continue;
    if (/^\S/.test(line)) break;
    const m = /^ {2}([A-Za-z0-9_-]+):\s*$/.exec(line);
    if (m) ids.push(m[1]);
  }
  return ids;
};

// Trailing punctuation a path picks up from surrounding YAML or shell.
const cleanPath = (p) => p.replace(/["'`,;:)\]}\\]+$/, '').replace(/\/+$/, '');

const scanCiPaths = (text) => {
  const out = new Set();
  const re = /\.ci\/[A-Za-z0-9_.\/-]+/g;
  let m;
  while ((m = re.exec(text)) !== null) {
    const p = cleanPath(m[0]);
    if (p.length > 4) out.add(p);
  }
  return out;
};

const exists = (p) => fs.existsSync(path.join(root, p));

// One level into every script the workflow names directly, and ONLY along the
// two edges that make a file an input to that script: it is SOURCED, or it is
// INVOKED as a command. Both the `.ci/...` repo-relative form and the
// `"$SCRIPT_DIR/../lib/common.sh"` sibling form are resolved; the latter is
// what every script in this tree actually writes, and it is invisible to a
// plain `.ci/` grep.
//
// SCANNING EVERY `.ci/` LITERAL IN THE BODY IS WHAT THIS DELIBERATELY DOES
// NOT DO. .ci/config/constants.sh:32,39 define CI_DOCKER_DIR and
// SERVICE_DOCKER_DIR pointing into .ci/docker; a body-wide scan pulled both
// into package_tests, which sources constants.sh for two version pins and
// never goes near Docker. A dictionary of paths that OTHER scripts use is not
// a dependency of every script that sources it.
const sweepScript = (rel) => {
  const out = new Set();
  const abs = path.join(root, rel);
  if (!fs.existsSync(abs) || !rel.endsWith('.sh')) return out;
  const dir = path.posix.dirname(rel);

  const take = (raw) => {
    let p = cleanPath(String(raw).replace(/^["']/, ''));
    if (p.startsWith('$SCRIPT_DIR/')) {
      p = path.posix.normalize(path.posix.join(dir, p.slice('$SCRIPT_DIR/'.length)));
    }
    if (p.startsWith('.ci/') && exists(p)) out.add(p);
  };

  for (const line of stripComments(fs.readFileSync(abs, 'utf8')).split('\n')) {
    // Sourced: `source <path>` or `. <path>`.
    const src = /^\s*(?:source|\.)\s+(\S+)/.exec(line);
    if (src) take(src[1]);
    // Invoked at command position, optionally behind sudo/bash/exec.
    const inv = /^\s*(?:sudo\s+|bash\s+|exec\s+)*(["']?(?:\$SCRIPT_DIR|\.ci)\/[^"'\s]+)/.exec(line);
    if (inv) take(inv[1]);
  }
  return out;
};

const deriveFor = (key) => {
  const site = SITES[key];
  if (!site) throw new Error(`no defining site recorded for key ${key}`);
  const wfRel = `.github/workflows/${site.wf}`;
  const raw = fs.readFileSync(path.join(root, wfRel), 'utf8');
  const ids = site.jobs.length > 0 ? site.jobs : allJobIds(raw);

  const required = new Set();
  // The defining workflow file itself: its `if:` gate, its matrix, its env and
  // its step order are all inputs to what the job does.
  required.add(wfRel);

  let checksOutSubmodules = false;

  for (const id of ids) {
    const block = jobBlock(raw, id);
    if (block === null) throw new Error(`job block ${id} not found in ${wfRel}`);
    const body = stripComments(block);

    for (const p of scanCiPaths(body)) required.add(p);

    // Local composite actions.
    const usesRe = /uses:\s*\.\/(\.github\/actions\/[A-Za-z0-9_-]+)/g;
    let m;
    while ((m = usesRe.exec(body)) !== null) required.add(m[1]);

    if (/submodules:\s*(true|recursive)/.test(body)) checksOutSubmodules = true;

    // setup-workspace runs install-deps.sh on a cache miss (action.yml:77,81)
    // and build-packages.sh whenever its flag is set (action.yml:91-93).
    if (/uses:\s*\.\/\.github\/actions\/setup-workspace/.test(body)) {
      required.add('.ci/scripts/setup/install-deps.sh');
      if (/build-packages:\s*'true'/.test(body)) {
        required.add('.ci/scripts/setup/build-packages.sh');
      }
    }

    // Anything that resolves node_modules consumes the manifest and the
    // lockfile, whether it says `npm ci` itself or leaves it to the action.
    if (/\b(npm|npx)\s/.test(body) || /uses:\s*\.\/\.github\/actions\/setup-workspace/.test(body)) {
      required.add('package.json');
      required.add('package-lock.json');
    }
  }

  // One-level sweep of every script named so far.
  for (const p of [...required]) {
    for (const q of sweepScript(p)) required.add(q);
  }

  // A derived path that is not in the tree is a stale WORKFLOW reference, not
  // a table defect, and blaming the table for it would send the next session
  // to the wrong file. Dropped here; test-greenlight.sh owns "declared paths
  // must exist" from the other direction.
  return { required: [...required].filter(exists).sort(), checksOutSubmodules };
};

const covers = (declared, p) =>
  declared.some((entry) => entry === p || p.startsWith(`${entry}/`));

let findings = 0;
const keys = only.length > 0 ? only : Object.keys(table);
for (const key of keys) {
  const closure = table[key];
  if (!closure) {
    process.stdout.write(`UNCOVERED ${key} - key-absent-from-table\n`);
    findings++;
    continue;
  }
  const { required, checksOutSubmodules } = deriveFor(key);
  process.stdout.write(`DERIVED ${key} ${required.length}\n`);
  const declared = [...closure.paths, ...closure.submodules];
  for (const p of required) {
    if (!covers(declared, p)) {
      process.stdout.write(`UNCOVERED ${key} ${p} not-in-closure\n`);
      findings++;
    }
  }
  if (checksOutSubmodules && closure.submodules.length === 0) {
    process.stdout.write(`UNCOVERED ${key} - checks-out-submodules-but-pins-none\n`);
    findings++;
  }
}

process.exit(findings > 0 ? 1 : 0);
CHECKER_EOF

# table.json -- CLOSURES as data, which is what makes the mutation control
# possible without ever editing the engine.
node -e '
const { CLOSURES } = require(process.argv[1]);
process.stdout.write(JSON.stringify(CLOSURES, null, 2));
' "$ENGINE" >"$WORK/table.json"

# ---------------------------------------------------------------------------
# Case 1: the derivation is not vacuous. A checker that derives nothing passes
# every coverage assertion in this file, so the size of the derived set is
# asserted BEFORE the coverage itself.
# ---------------------------------------------------------------------------
test_derivation_is_not_vacuous() {
    local out
    out="$(node "$CHECKER" "$REPO_ROOT" "$WORK/table.json" 2>&1 || true)"

    local keys
    keys="$(grep -c '^DERIVED ' <<<"$out" || true)"
    assert_eq "$keys" "18" "every key in the table must have a defining site and be traced"

    # Every key must derive MORE than the defining workflow file it gets for
    # free, or the job block was not found and the scan ran over nothing. The
    # floor is 2 rather than something rounder because update_flow honestly
    # derives exactly 2: ct-update-flow.yml runs one script against a
    # downloaded artifact and references nothing else in the tree.
    local thin
    thin="$(awk '$1 == "DERIVED" && $3 < 2 { print $2, $3 }' <<<"$out")"
    assert_eq "$thin" "" "no key may derive nothing beyond its own workflow file"

    # And the fat keys must actually be fat: e2e_workers walks a dozen step
    # scripts plus their sourced libraries, so a derivation that collapsed to
    # the workflow-plus-a-couple shape would still clear the floor above.
    local workers
    workers="$(awk '$1 == "DERIVED" && $2 == "e2e_workers" { print $3 }' <<<"$out")"
    assert_eq "$((workers > 14 ? 1 : 0))" "1" "e2e_workers must trace its whole step chain ($workers paths)"

    local total
    total="$(awk '$1 == "DERIVED" { s += $3 } END { print s + 0 }' <<<"$out")"
    # 195 across the 18 keys as of 2026-08-08. The floor sits just under it so
    # that any ONE key ceasing to derive (a renamed job id, a job block the
    # extractor stops finding) drops the total through it, rather than being
    # absorbed by slack.
    assert_eq "$((total > 190 ? 1 : 0))" "1" "the whole trace must derive a substantial set ($total paths)"
    log_pass "the derivation produces a real requirement set for all 18 keys ($total paths)"
}

# ---------------------------------------------------------------------------
# Case 2: THE PROPERTY. Every derived path is covered by the declared closure.
# ---------------------------------------------------------------------------
test_every_derived_path_is_covered() {
    local rc=0 out
    out="$(node "$CHECKER" "$REPO_ROOT" "$WORK/table.json" 2>&1)" || rc=$?
    if [[ "$rc" != "0" ]]; then
        printf '%s\n' "$out" | grep '^UNCOVERED ' >&2 || true
    fi
    assert_eq "$rc" "0" "every path each job references must be covered by its closure"
    assert_not_contains "$out" "UNCOVERED" "and no key may report an uncovered input"
    log_pass "every closure covers every input its job references (case 2)"
}

# ---------------------------------------------------------------------------
# Case 3: THE CONTROL. Delete ONE required entry from a copy of the table and
# the identical checker must go red, naming that key and that path. Without
# this the two cases above prove only that the checker ran.
#
# Two mutations, because they fail through different limbs: a path deletion
# exercises the coverage walk, and an emptied submodule list exercises the
# checkout implication.
# ---------------------------------------------------------------------------
test_a_missing_entry_is_caught() {
    local rc out

    # Mutation 1: e2e_workers loses run-e2e.sh, the script its final step runs.
    node -e '
const fs = require("fs");
const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
t.e2e_workers.paths = t.e2e_workers.paths.filter((p) => p !== ".ci/scripts/test/run-e2e.sh");
fs.writeFileSync(process.argv[2], JSON.stringify(t));
' "$WORK/table.json" "$WORK/mutant-path.json"

    rc=0
    out="$(node "$CHECKER" "$REPO_ROOT" "$WORK/mutant-path.json" 2>&1)" || rc=$?
    assert_eq "$rc" "1" "a table missing one required path must FAIL the checker"
    assert_contains "$out" "UNCOVERED e2e_workers .ci/scripts/test/run-e2e.sh not-in-closure" \
        "naming the key and the exact path that went uncovered"

    # And ONLY that key: the finding must be attributed, not smeared across the
    # table by a checker that collapses on any error.
    local hits
    hits="$(grep -c '^UNCOVERED ' <<<"$out" || true)"
    assert_eq "$hits" "1" "exactly one finding, so the failure is attributed to one key"

    # Mutation 2: renet keeps every path but stops pinning any submodule, while
    # its job block still checks out with `submodules: true`.
    node -e '
const fs = require("fs");
const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
t.renet.submodules = [];
fs.writeFileSync(process.argv[2], JSON.stringify(t));
' "$WORK/table.json" "$WORK/mutant-pins.json"

    rc=0
    out="$(node "$CHECKER" "$REPO_ROOT" "$WORK/mutant-pins.json" 2>&1)" || rc=$?
    assert_eq "$rc" "1" "a key that checks out submodules and pins none must FAIL"
    assert_contains "$out" "UNCOVERED renet - checks-out-submodules-but-pins-none" \
        "named as the checkout implication, not as a missing path"

    # CONTROL FOR THE CONTROL: the unmutated table through the same invocation
    # exits 0, so the two reds above are the mutations and not a checker that
    # fails on everything.
    rc=0
    node "$CHECKER" "$REPO_ROOT" "$WORK/table.json" >/dev/null 2>&1 || rc=$?
    assert_eq "$rc" "0" "the unmutated table through the same checker still passes"
    log_pass "the checker provably fires: one deleted entry turns it red (case 3)"
}

# ---------------------------------------------------------------------------
# Case 4: coverage is by exact entry OR by ancestor directory, and by nothing
# looser. Several keys declare a whole tree (`.ci/scripts/build`, `.ci/lib`,
# `.ci/tutorials`) because a directory listing self-maintains as files come and
# go. A prefix match that ignored the separator would let `.ci/scripts/te`
# cover `.ci/scripts/test/run-e2e.sh`, which is the shape a careless
# `startsWith` takes.
# ---------------------------------------------------------------------------
test_ancestor_coverage_respects_the_separator() {
    local rc out

    # An ancestor entry DOES cover its descendant: swap the exact path for its
    # directory and the checker must still pass.
    node -e '
const fs = require("fs");
const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
t.e2e_workers.paths = t.e2e_workers.paths.map((p) =>
  p === ".ci/scripts/test/run-e2e.sh" ? ".ci/scripts/test" : p
);
fs.writeFileSync(process.argv[2], JSON.stringify(t));
' "$WORK/table.json" "$WORK/mutant-dir.json"

    rc=0
    node "$CHECKER" "$REPO_ROOT" "$WORK/mutant-dir.json" >/dev/null 2>&1 || rc=$?
    assert_eq "$rc" "0" "a directory entry covers the files beneath it"

    # A truncated string that is NOT a directory boundary does not.
    node -e '
const fs = require("fs");
const t = JSON.parse(fs.readFileSync(process.argv[1], "utf8"));
t.e2e_workers.paths = t.e2e_workers.paths.map((p) =>
  p === ".ci/scripts/test/run-e2e.sh" ? ".ci/scripts/te" : p
);
fs.writeFileSync(process.argv[2], JSON.stringify(t));
' "$WORK/table.json" "$WORK/mutant-prefix.json"

    rc=0
    out="$(node "$CHECKER" "$REPO_ROOT" "$WORK/mutant-prefix.json" 2>&1)" || rc=$?
    assert_eq "$rc" "1" "a bare string prefix must NOT be read as an ancestor"
    assert_contains "$out" "UNCOVERED e2e_workers .ci/scripts/test/run-e2e.sh" \
        "the path is still reported uncovered"
    log_pass "coverage follows directory boundaries, not string prefixes (case 4)"
}

log_test "test-greenlight-closure-trace"
test_derivation_is_not_vacuous
test_every_derived_path_is_covered
test_a_missing_entry_is_caught
test_ancestor_coverage_respects_the_separator
echo ""
echo "assertion call sites: $(grep -cE '^[[:space:]]*assert_' "${BASH_SOURCE[0]}")"
log_pass "all tests passed"
