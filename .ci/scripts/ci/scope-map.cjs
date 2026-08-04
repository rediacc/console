// The path-to-module classification table for the CI scope engine, plus the
// pure classify() that applies it. PURE on purpose: no network, no git, no
// GitHub API, no fs. Everything context-dependent (the workflow closure) is
// computed by the caller and passed in, so this file is a lookup table that a
// unit test can exercise offline in milliseconds.
//
// THE ONE RULE THAT MATTERS: every ambiguous case resolves to FULL CI. A false
// full run costs 70 minutes; a false reduced run merges untested code. So the
// table only names paths whose job surface is actually known, and everything
// else falls through to `unclassified:<path>` = full. A new top-level tree, a
// new package, a new submodule: all full until someone classifies them here.
//
// Design source: docs/ci-overhaul/02-v1-economics.md B1/B2 and the Wave B
// edge-case matrix (cases 17-24 are implemented here; the case number is cited
// at each site). This chunk is deliberately consumer-free: nothing in CI reads
// these outputs yet, so landing it cannot change CI behaviour.

'use strict';

// ---------------------------------------------------------------------------
// Modules. A module is a subtree with a known job surface. Submodules are
// modules too: the gitlink path (`private/renet`) and any expanded content
// path under it (`private/renet/pkg/x.go`) classify identically, so the
// pointer bump and the later compare-API expansion land in the same bucket.
// ---------------------------------------------------------------------------
const KNOWN_MODULES = [
  'docs', // repo docs, .claude/.gemini/.idx/.vscode, root README-likes
  'www', // packages/www
  'cli', // packages/cli
  'shared', // packages/shared (consumed by cli, www, account)
  'provisioning', // packages/provisioning (VM boot for the E2E bridge)
  'e2e', // packages/e2e-tests
  'json', // packages/json (repo templates)
  'workers', // workers/ (Cloudflare workers: preview + smoke surface)
  'tutorials', // .ci/tutorials scripts + the www tutorial docs that order them
  'devcontainer', // .devcontainer (built by build-docker-fast, no test surface)
  'renet', // private/renet submodule
  'account', // private/account submodule
  'elite', // private/elite submodule
  'homebrew-tap', // private/homebrew-tap submodule
];

// Root files that shape every job's environment: the npm tree (lockfile is the
// setup-workspace cache key for EVERY job, VM/E2E legs included), the build
// configs, the gate allowlists, the submodule set itself. Any of these => full.
// Exact basenames, matched only at the repo root.
const ROOT_MANIFESTS = new Set([
  '.actions-upgrade-blocklist',
  '.audit-allowlist',
  '.audit-prod-allowlist',
  '.ci-parity-exempt',
  '.ci-trigger',
  '.cli-i18n-orphan-allowlist',
  '.dead-bash-allowlist',
  '.deps-upgrade-blocklist',
  '.dockerignore',
  '.e2e-coverage-allowlist',
  '.editorconfig',
  '.embed-assets-upgrade-blocklist',
  '.gitattributes',
  '.gitignore',
  '.gitmodules',
  '.go-deps-upgrade-blocklist',
  '.npmrc',
  '.syncpackrc-reasons.json',
  '.syncpackrc.json',
  'Dockerfile',
  'Rediaccfile',
  'biome.json',
  'css-custom-data.json',
  'docker-compose.yml',
  'eslint.config.js',
  'knip.jsonc',
  'package-lock.json',
  'package.json',
  'pyroscope.yaml',
  'pyroscope.yaml.template',
  'rdc.sh',
  'regions.json',
  'run.sh',
  'tsconfig.json',
]);

// Root files that are prose, not build inputs.
const ROOT_DOCS = new Set(['CLAUDE.md', 'LICENSE', 'README.md']);

// Submodule gitlink paths (from .gitmodules) -> module name.
const SUBMODULES = {
  'private/renet': 'renet',
  'private/account': 'account',
  'private/elite': 'elite',
  'private/homebrew-tap': 'homebrew-tap',
};

// ---------------------------------------------------------------------------
// The rule table. First match wins; a rule either names modules or forces
// full with a reason prefix. Order is load-bearing where prefixes nest
// (.ci/scripts/lib before .ci, tutorial docs before packages/www).
// ---------------------------------------------------------------------------

// matchPrefix('a/') matches 'a/x' but never 'ab/x'; matchExactOrPrefix('a')
// matches 'a' itself (a gitlink) and 'a/x' (expanded submodule content).
const matchPrefix = (prefix) => (p) => p.startsWith(prefix);
const matchExactOrPrefix = (base) => (p) => p === base || p.startsWith(`${base}/`);

// Tutorial docs order and populate the ops tutorial-sequence job
// (.ci/tutorials/run-sequence.sh derives its list from these files), so they
// carry the tutorials module ON TOP of being www content.
const TUTORIAL_DOC_RE = /^packages\/www\/src\/content\/docs\/[^/]+\/tutorial-/;

const RULES = [
  // Case 23: .ci/scripts/lib is sourced by ~150 scripts across every lane.
  // A change here invalidates everything; distinct reason so the test can pin
  // it apart from the generic harness bucket.
  { name: 'ci-lib', match: matchPrefix('.ci/scripts/lib/'), full: 'ci-lib' },

  // Tutorial runner scripts: consumed only by the ops tutorial-sequence job.
  { name: 'ci-tutorials', match: matchPrefix('.ci/tutorials/'), modules: ['tutorials'] },

  // The rest of .ci is harness: build/test/release scripts whose per-subtree
  // job surface is not yet mapped. Conservative full; refining this into a
  // per-subtree map (with a gate cross-checking workflow references) is a
  // later, separately-tested step.
  { name: 'ci-harness', match: matchPrefix('.ci/'), full: 'harness' },

  // Case 24: workflows. The closure is computed at RUNTIME by the caller
  // (scope-engine.cjs walks `uses: ./.github/workflows/` from ci.yml), never
  // by a name pattern: ci.yml calls cd-stage.yml, so a `cd-*` exclusion would
  // wrongly drop a workflow that IS inside the CI closure. Both branches are
  // full in v1; the distinct reasons keep the closure live and observable, and
  // are the hook for later precision on non-closure workflows.
  {
    name: 'workflows',
    match: matchPrefix('.github/workflows/'),
    full: (p, ctx) =>
      ctx.workflowClosure && ctx.workflowClosure.has(p) ? 'workflow-closure' : 'workflow-non-closure',
  },

  // Composite actions (setup-workspace, app-token) run in nearly every job.
  { name: 'gh-harness', match: matchPrefix('.github/'), full: 'harness' },

  { name: 'tutorial-docs', match: (p) => TUTORIAL_DOC_RE.test(p), modules: ['www', 'tutorials'] },
  { name: 'www', match: matchPrefix('packages/www/'), modules: ['www'] },
  { name: 'cli', match: matchPrefix('packages/cli/'), modules: ['cli'] },
  { name: 'shared', match: matchPrefix('packages/shared/'), modules: ['shared'] },
  { name: 'provisioning', match: matchPrefix('packages/provisioning/'), modules: ['provisioning'] },
  { name: 'e2e', match: matchPrefix('packages/e2e-tests/'), modules: ['e2e'] },
  { name: 'json', match: matchPrefix('packages/json/'), modules: ['json'] },
  // A NEW packages/* directory deliberately has no rule: it falls through to
  // unclassified = full until it is mapped here (case 18).

  { name: 'workers', match: matchPrefix('workers/'), modules: ['workers'] },

  ...Object.entries(SUBMODULES).map(([base, mod]) => ({
    name: `submodule-${mod}`,
    match: matchExactOrPrefix(base),
    modules: [mod],
  })),
  // private/<anything else> falls through to unclassified = full: an added or
  // removed submodule (case 14 at the pointer level) must never skip anything.

  { name: 'docs', match: matchPrefix('docs/'), modules: ['docs'] },
  // .claude/.gemini/.idx/.vscode cannot affect CI (the CI action restores
  // .claude from origin/main regardless); editor metadata likewise.
  { name: 'agent-docs', match: matchPrefix('.claude/'), modules: ['docs'] },
  { name: 'gemini-docs', match: matchPrefix('.gemini/'), modules: ['docs'] },
  { name: 'idx-docs', match: matchPrefix('.idx/'), modules: ['docs'] },
  { name: 'vscode-docs', match: matchPrefix('.vscode/'), modules: ['docs'] },

  { name: 'devcontainer', match: matchPrefix('.devcontainer/'), modules: ['devcontainer'] },

  // Quality-gate sources and lint machinery: quality lanes are never
  // path-filtered (registry gates must stay immune to scoping by
  // construction), but these also feed hooks and dev flows whose surface is
  // unmapped. Conservative full.
  { name: 'scripts-harness', match: matchPrefix('scripts/'), full: 'harness' },
  { name: 'eslint-harness', match: matchPrefix('eslint-rules/'), full: 'harness' },
  { name: 'compose-harness', match: matchPrefix('compose/'), full: 'harness' },

  { name: 'root-docs', match: (p) => ROOT_DOCS.has(p), modules: ['docs'] },
  { name: 'root-manifest', match: (p) => ROOT_MANIFESTS.has(p), full: 'root-manifest' },
];

// ---------------------------------------------------------------------------
// Job surfaces: which modules each scoped job consumes. The eventual consumer
// derives run_<job> from these; nothing reads them yet. Keys are the future
// run_* names.
//
// migration-test is DELIBERATELY absent: it stays unconditional (edge case 26,
// and the standing comment in ct-tests.yml explains why it must run on the
// exact path that deploys migrations).
//
// The 8 VM/E2E jobs check out with `submodules: true` and run setup-workspace,
// so their surface includes packages/shared, packages/provisioning and every
// submodule pointer (verified against ct-tests.yml). package-lock.json is in
// their surface too, via ROOT_MANIFESTS => full: a lockfile change runs
// everything, which is how that dependency is honoured.
// ---------------------------------------------------------------------------
const VM_E2E_SURFACE = [
  'cli',
  'shared',
  'provisioning',
  'e2e',
  'json',
  'renet',
  'account',
  'elite',
  'homebrew-tap',
];

const VM_E2E_JOB_KEYS = [
  'e2e_workers',
  'e2e_ceph',
  'e2e_ceph_workers',
  'e2e_k8s',
  'e2e_k8s_ceph',
  'e2e_k8s_multinode',
  'e2e_migrate',
  'fork_isolation',
];

const JOB_SURFACES = {
  unit: ['shared', 'cli', 'www', 'provisioning', 'e2e', 'json', 'workers'],
  ...Object.fromEntries(VM_E2E_JOB_KEYS.map((k) => [k, VM_E2E_SURFACE])),
  renet: ['renet'],
  // The licensing enforcement leg builds renet from source and drives cmd/renet,
  // so renet is its whole surface. Its own harness (.ci/scripts/private/
  // license-e2e.sh and license-mint/) lives under .ci/, which already forces
  // full CI, so it needs no separate module.
  license_enforcement: ['renet'],
  account_e2e: ['account', 'shared'],
  // The drills leg runs `./run.sh drill universe` + `drill transfer`: the CLI's
  // own config resolution (`packages/cli`), the shared package both it and the
  // account server build against, and a live `./run.sh account dev` gateway
  // (`private/account`) the assertions log in to.
  //
  // The drills' OWN source (scripts/drills/*.sh) is not a module: `scripts/`
  // hits the `scripts-harness` rule => full CI, so an edit to a drill always
  // runs this leg. Same shape as license_enforcement's harness under `.ci/`.
  //
  // `www` is DELIBERATELY ABSENT even though `account_dev` starts the Astro dev
  // server from packages/www and exits non-zero if it does not come up. A www
  // change cannot change what these drills ASSERT (config isolation, per-config
  // tokens, config-storage seed/offline/fail-closed): it can only break the
  // harness. Carrying www here would run a ~15-minute leg on every marketing or
  // i18n PR, which is the single most common change shape in this repo. The
  // accepted cost: a www change that breaks `astro dev` while still building
  // clean would surface as a red drills leg on the NEXT cli/account PR.
  drills: ['cli', 'shared', 'account'],
  ops: ['cli', 'shared', 'provisioning', 'json', 'renet', 'account', 'tutorials'],
  elite_run: ['elite', 'renet'],
  update_flow: ['cli', 'shared', 'json', 'renet'],
  package_tests: ['cli', 'shared', 'json', 'renet'],
  install_methods: ['cli', 'shared', 'json', 'renet', 'homebrew-tap'],
};

// A surface naming a module the table cannot produce is rot that silently
// never matches, i.e. a job that can never re-enter scope. Throw at load.
function validateJobSurfaces(surfaces, knownModules) {
  const known = new Set(knownModules);
  for (const [job, mods] of Object.entries(surfaces)) {
    for (const mod of mods) {
      if (!known.has(mod)) {
        throw new Error(`JOB_SURFACES.${job} names unknown module '${mod}'`);
      }
    }
  }
}
validateJobSurfaces(JOB_SURFACES, KNOWN_MODULES);

// ---------------------------------------------------------------------------
// classify(paths, ctx) -> { modules, reasons, mode, full_reasons }
//
// paths: array of repo-relative path strings (already unquoted/normalized by
//   the caller; both sides of a rename appear as separate entries, and a
//   deleted path is just a path: deletion is a change like any other, cases
//   19/20 live in the caller's parser).
// ctx.workflowClosure: Set of '.github/workflows/x.yml' paths reachable from
//   ci.yml. Optional; when absent every workflow classifies as non-closure,
//   which is still full (fail-closed, only the reason degrades).
// ---------------------------------------------------------------------------
function classify(paths, ctx = {}) {
  const modules = new Set();
  const reasons = [];
  const fullReasons = [];

  // Case 22: an empty delta means the computation upstream failed, never that
  // nothing changed. Full, not reduced.
  if (!paths || paths.length === 0) {
    return { modules, reasons, mode: 'full', full_reasons: ['empty-delta'] };
  }

  for (const path of paths) {
    const rule = RULES.find((r) => r.match(path, ctx));
    if (!rule) {
      // Case 17: fail CLOSED. The single most important behaviour in the file.
      fullReasons.push(`unclassified:${path}`);
      continue;
    }
    if (rule.full) {
      const prefix = typeof rule.full === 'function' ? rule.full(path, ctx) : rule.full;
      fullReasons.push(`${prefix}:${path}`);
      continue;
    }
    for (const mod of rule.modules) modules.add(mod);
    reasons.push(`${path} -> ${rule.modules.join(',')}`);
  }

  return {
    modules,
    reasons,
    mode: fullReasons.length > 0 ? 'full' : 'reduced',
    full_reasons: fullReasons,
  };
}

// buildPlan(classification) -> the JSON plan --classify prints. In full mode
// every job runs; in reduced mode a job runs iff its surface intersects the
// touched modules.
function buildPlan(classification) {
  const { modules, reasons, mode, full_reasons } = classification;
  const jobs = {};
  for (const [job, surface] of Object.entries(JOB_SURFACES)) {
    if (mode === 'full') {
      jobs[job] = { run: true, reason: 'full' };
      continue;
    }
    const hit = surface.filter((mod) => modules.has(mod));
    jobs[job] =
      hit.length > 0
        ? { run: true, reason: `modules:${hit.join(',')}` }
        : { run: false, reason: 'out-of-scope' };
  }
  return {
    engine: 'scope-engine/1',
    mode,
    modules: [...modules].sort(),
    reasons,
    full_reasons,
    jobs,
  };
}

module.exports = {
  KNOWN_MODULES,
  ROOT_MANIFESTS,
  ROOT_DOCS,
  SUBMODULES,
  RULES,
  JOB_SURFACES,
  VM_E2E_SURFACE,
  VM_E2E_JOB_KEYS,
  validateJobSurfaces,
  classify,
  buildPlan,
};
