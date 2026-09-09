/**
 * policy-paths.ts -- the ONE place that knows where a suppression policy file lives.
 *
 * WHY THIS EXISTS
 * ---------------
 * Fifteen allow / block / exempt files sat at the repository root, and the code
 * that read them mostly hard-coded that root, some of it cwd-relative after a
 * `cd`. They moved to `.ci/policy/` in W4 P2 (see .ci/policy/README.md for the
 * predicate and the list). A move like that is only safe once there is a
 * single seam every reader goes through, because otherwise the move half-lands:
 * some readers follow, some do not, and the ones that do not read a file that is
 * no longer there -- which for every one of these mechanisms means "zero entries",
 * which reads exactly like "nothing is suppressed".
 *
 * THREE RULES, all of them deliberate refusals.
 *
 * 1. PURE JOIN, NO FILESYSTEM. policyPath() never calls stat, exists, or readdir.
 *    It answers the same string on a tree that has no `.ci` directory at all, so
 *    a caller's failure to find the file is the caller's own ENOENT, reported at
 *    the caller's own path, rather than this module quietly answering somewhere
 *    else. Proven by .ci/scripts/test/gates/test-policy-path.sh against a fixture
 *    root containing nothing.
 *
 * 2. NO REGISTRY FILE. The valid names are the frozen array below, in source. A
 *    registry read at runtime would need its own path, which is the problem this
 *    module solves, one level up.
 *
 * 3. NO TRANSITION FALLBACK. There is exactly ONE location at a time, held in
 *    POLICY_DIR. A helper that tried the new location and fell back to the old
 *    one is precisely how a move half-lands and nobody notices: every reader
 *    keeps working, the gate stays green, and the two locations drift until a
 *    file exists in both with different contents. An unknown name THROWS, loudly,
 *    naming the valid set, rather than returning a plausible path that resolves
 *    to nothing.
 *
 * THE MOVE LANDED in W4 P2 as one edit here: POLICY_DIR went from '' to
 * '.ci/policy'. Nothing else in this module changed, and no caller that already
 * went through policyPath() changed at all.
 */

import path from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = path.dirname(fileURLToPath(import.meta.url));

/** The repository root, derived from this module's own location (scripts/lib/). */
const REPO_ROOT = path.resolve(__dirname, '..', '..');

/**
 * The directory, relative to the repository root, that holds the policy files.
 *
 * '.ci/policy' since W4 P2, which is where all fifteen live. '' would mean the
 * repository root, where they lived until that move. It is a constant rather
 * than an environment variable on purpose: two locations that can both be live
 * at once is the failure mode rule 3 above exists to refuse.
 */
const POLICY_DIR = '.ci/policy';

/**
 * The names policyPath() will answer for: every suppression policy file that
 * moves into `.ci/policy/`.
 *
 * `.ci-trigger` is DELIBERATELY ABSENT and stays at the repository root. It is
 * not a policy file -- no entries, no BLOCKER lines, no parser anywhere in the
 * tree -- and its whole semantic is a root gesture a human performs by hand to
 * force a full CI round. .ci/policy/README.md records that decision and the
 * evidence for it.
 */
const POLICY_FILES = Object.freeze([
  '.actions-upgrade-blocklist',
  '.audit-allowlist',
  '.audit-prod-allowlist',
  '.ci-parity-exempt',
  '.cli-i18n-orphan-allowlist',
  '.dead-bash-allowlist',
  '.deps-upgrade-blocklist',
  '.devcontainer-upgrade-blocklist',
  '.e2e-coverage-allowlist',
  '.embed-assets-upgrade-blocklist',
  '.go-deps-upgrade-blocklist',
  // W4-D1, CLOSED 2026-09-08. This name landed in the directory on 2026-09-07 with
  // check:ci-language-policy and was NOT added here, so 16 dotfiles on disk faced 15
  // names for a day with nothing red: its gate reached it through a hardcoded literal
  // instead of policyPath(), and a reader that bypasses the seam does not need the list
  // to know the file exists, which is exactly why a stale list is invisible. Both halves
  // are fixed: the literal became policy_path() in W4 P4a, and check:ci-policy-inventory
  // now asserts three-way set equality between this list, the Python one and the
  // directory, so the same drift cannot recur silently.
  '.language-policy-allowlist',
  '.plan-housekeeping-allowlist',
  '.profiler-coverage-allowlist',
  '.runner-advice-allowlist',
  '.unverified-download-allowlist',
  // D0, 2026-09-09. THE ONLY NON-DOTFILE AND THE ONLY .json IN THIS SET, and both are
  // deliberate. It is a pinned MEASUREMENT of what the hook wiring costs, not a list of
  // exempted entries, so a name-per-line dotfile could not hold it; it is policy by the
  // README's four-part predicate all the same, because every number in it is a claim
  // about the world that a change to .claude/settings.json can stop being true.
  'hook-exec-baseline.json',
  // D2, 2026-09-09. The WORKLIST_* environment registry: 133 names across 60 files at
  // 183 read sites, with no registry and no schema before this. A typo'd name reads as
  // UNSET, which for a flag defaulting to `on` is the FAIL-OPEN direction.
  'worklist-env-registry.json',
] as const);

type PolicyFileName = (typeof POLICY_FILES)[number];

const VALID = new Set<string>(POLICY_FILES);

/** True when `name` is one of the policy files this module will resolve. */
export function isPolicyFileName(name: string): name is PolicyFileName {
  return VALID.has(name);
}

/**
 * Absolute path of one policy file.
 *
 * @param name one of POLICY_FILES. Anything else throws.
 * @param root repository root to resolve against. Defaults to the real one;
 *             tests pass a fixture root, and the join is pure so the fixture
 *             need not contain anything at all.
 * @throws on an unknown name, naming the valid set. Refusing loudly is the
 *         point: a typo that returned `<root>/.audit-allowlst` would be read as
 *         an empty allowlist by every consumer here, which is indistinguishable
 *         from "nothing is suppressed".
 */
export function policyPath(name: string, root: string = REPO_ROOT): string {
  if (!VALID.has(name)) {
    throw new Error(
      `policyPath: "${name}" is not a known policy file.\n` +
        `  Known names (${POLICY_FILES.length}):\n` +
        POLICY_FILES.map((n) => `    ${n}`).join('\n') +
        `\n  Add the name to POLICY_FILES in scripts/lib/policy-paths.ts, and to the` +
        ` move list in .ci/policy/README.md, in the same change.`
    );
  }
  // Unconditional join: path.join(root, '', name) is path.join(root, name), so a
  // POLICY_DIR of '' still resolves to the repository root without a branch that
  // the compiler can prove dead against the literal above.
  return path.join(root, POLICY_DIR, name);
}

/** Absolute paths of every policy file, in POLICY_FILES order. */
function allPolicyPaths(root: string = REPO_ROOT): string[] {
  return POLICY_FILES.map((n) => policyPath(n, root));
}

// ---------------------------------------------------------------------------
// CLI, for callers that are not TypeScript.
//
// `.ci/scripts/test/gates/test-policy-path.sh` drives this rather than
// generating an import snippet, and the phase-2 movers -- shell and Python gates
// that must not each re-derive where a policy file lives -- get the same answer
// here that the TS gates get from policyPath() above.
//
// It is also what keeps the module's EXPORT surface honest: only policyPath and
// isPolicyFileName are imported by other TypeScript, so only those two are
// exported. The name list, the directory and the all-paths helper are reachable
// through this CLI instead of being exports nothing imports, which is the shape
// `lint:unused` refuses and rightly.
//
//   --path <name> [--root <dir>]  -> one absolute path
//   --list                        -> every known name, one per line
//   --dir                         -> POLICY_DIR (an empty line means the root)
//   --is <name>                   -> "true" or "false"
//
// Guarded so importing the module never runs it.
// ---------------------------------------------------------------------------

function cliMain(argv: string[]): number {
  const mode = argv[0] ?? '';

  if (mode === '--list') {
    for (const n of POLICY_FILES) process.stdout.write(`${n}\n`);
    return 0;
  }
  if (mode === '--dir') {
    process.stdout.write(`${POLICY_DIR}\n`);
    return 0;
  }
  if (mode === '--is') {
    process.stdout.write(`${isPolicyFileName(argv[1] ?? '')}\n`);
    return 0;
  }
  if (mode === '--path') {
    const name = argv[1] ?? '';
    const rootIdx = argv.indexOf('--root');
    const root = rootIdx >= 0 ? (argv[rootIdx + 1] ?? '') : REPO_ROOT;
    if (root === '') throw new Error('policyPath: --root was given without a directory');
    process.stdout.write(`${policyPath(name, root)}\n`);
    return 0;
  }
  if (mode === '--all-paths') {
    const rootIdx = argv.indexOf('--root');
    const root = rootIdx >= 0 ? (argv[rootIdx + 1] ?? '') : REPO_ROOT;
    if (root === '') throw new Error('policyPath: --root was given without a directory');
    for (const p of allPolicyPaths(root)) process.stdout.write(`${p}\n`);
    return 0;
  }

  throw new Error(
    `policy-paths: unknown mode "${mode}". Expected --path, --all-paths, --list, --dir or --is.`
  );
}

// process.argv[1] is this file's path only when it was EXECUTED. An import
// leaves it pointing at the importer, so the comparison is false.
const invokedPath = process.argv[1] ? path.resolve(process.argv[1]) : '';
if (invokedPath === fileURLToPath(import.meta.url)) {
  try {
    process.exit(cliMain(process.argv.slice(2)));
  } catch (err) {
    process.stderr.write(`${err instanceof Error ? err.message : String(err)}\n`);
    process.exit(2);
  }
}
