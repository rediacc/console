#!/usr/bin/env tsx
/**
 * Gate: a workflow may not read a secret that no longer exists.
 *
 * WHY THIS EXISTS. On 2026-09-05 the operator ruled "we should not have github
 * secrets at all" and all 45 rediacc ORG action secrets were deleted. Deleting
 * them does not delete the READS: every `${{ secrets.NAME }}` left in a workflow
 * now resolves to the EMPTY STRING. That is the worst shape of failure available
 * here, because an empty credential is not a loud 404 -- it is a
 * successful-looking call that authenticates as nobody, and the job then fails
 * somewhere that names the symptom rather than the cause.
 *
 * WHAT THIS GATE CANNOT DO, said plainly so its green is not read as more than it
 * is: it CANNOT verify the org secrets are actually gone. Reading
 * `orgs/<org>/actions/secrets` needs the `admin:org` scope, and CI's
 * `GITHUB_TOKEN` does not have it -- measured 2026-09-05, the call answers only
 * from an operator token carrying that scope. So the org side is checked by a
 * human or not at all. This checks the half that lives in the repo, which is also
 * the half that actually breaks jobs.
 *
 * SHRINK-ONLY, ENFORCED ON THE WRITE PATH. 54 names across 384 read sites existed
 * the moment the secrets were deleted, so demanding zero would just be red until a
 * migration nobody has run. The baseline freezes that SET, and the write path goes
 * through scripts/lib/shrink-only-baseline.ts -- the shared guard the seven other
 * frozen-backlog gates use. Enforcing on the read path alone was the defect
 * `gate-test:shrink-only-composition` exists to catch: a reseed that drains thirty
 * findings and absorbs one satisfies "the total did not grow" while violating "the
 * set only loses members", and prints a SMALLER number as it does it.
 *
 * ALLOWED, and why each survives:
 *   GITHUB_TOKEN            minted per-run by Actions; never an org secret
 *   BWS_ACCESS_TOKEN        THE BOOTSTRAP. Repo-scoped. It fetches every other
 *                           value from Bitwarden, so it cannot come from
 *                           Bitwarden itself. agent/PLAN-github-secrets-removal.md:17
 *                           names it the sole survivor.
 *   BREAKPOINT_TUNNEL_TOKEN NOT because it is repo-scoped -- that was the wrong
 *                           reason, corrected 2026-09-05. It is fully backed up
 *                           (Secrets Manager as CLOUDFLARE_BREAKPOINT_TUNNEL_TOKEN,
 *                           and the vault), so recovery is not the issue. Its main
 *                           consumer breakpoint.yml deliberately has NO Bitwarden
 *                           fetch: the bws-secrets action exports through
 *                           GITHUB_ENV, and that job's later steps include
 *                           `Start debug shell` -- a human on a shell in the runner
 *                           -- so fetching would promote credentials from step
 *                           scope to something that human can read. See
 *                           .github/workflows/breakpoint.yml:188-207, which says a
 *                           cutover "needs a DIFFERENT shape than the others".
 *                           Until that shape exists, these reads must stay.
 *   CLAUDE_CODE_OAUTH_TOKEN repo-scoped on renet/account/elite
 */
import { existsSync, readFileSync, readdirSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  baselineAdditions,
  commitBaseline,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const ROOT = process.env.SECRET_SCOPE_ROOT ?? process.cwd();
const WORKFLOWS = join(ROOT, '.github', 'workflows');
const BASELINE = join(ROOT, '.ci', 'config', 'secret-scope-baseline.json');
const KEY = 'orgScopedReads';

const ALLOWED = new Set([
  'GITHUB_TOKEN',
  'BWS_ACCESS_TOKEN',
  'BREAKPOINT_TUNNEL_TOKEN',
  'CLAUDE_CODE_OAUTH_TOKEN',
]);

const SECRET_RE = /secrets\.([A-Z0-9_]+)/g;

/**
 * ANTI-VACUITY FLOOR. This gate scans a directory; a glob that stops matching --
 * a renamed path, a moved workflows tree, a bad SECRET_SCOPE_ROOT -- would find
 * nothing and print the same tick as a fully migrated repo. 28 workflow files
 * exist today, so a floor well under that catches a broken scan without firing on
 * ordinary churn. A check that cannot tell "clean" from "did not run" is not
 * evidence.
 */
const MIN_WORKFLOWS = 20;

export function countWorkflows(dir: string): number {
  if (!existsSync(dir)) return 0;
  return readdirSync(dir).filter((n) => n.endsWith('.yml') || n.endsWith('.yaml')).length;
}

/** Ids are `<workflow>:<SECRET_NAME>`, the shape the shared guard expects. */
export function scan(dir: string): string[] {
  if (!existsSync(dir)) return [];
  const ids = new Set<string>();
  for (const f of readdirSync(dir).filter((n) => n.endsWith('.yml') || n.endsWith('.yaml'))) {
    for (const m of readFileSync(join(dir, f), 'utf8').matchAll(SECRET_RE)) {
      if (!ALLOWED.has(m[1])) ids.add(`${f}:${m[1]}`);
    }
  }
  return [...ids].sort();
}

function readBaseline(): string[] {
  if (!existsSync(BASELINE)) return [];
  return (JSON.parse(readFileSync(BASELINE, 'utf8'))[KEY] ?? []) as string[];
}

function selftest(): number {
  let n = 0;
  let bad = 0;
  const check = (label: string, ok: boolean, detail?: string) => {
    n += 1;
    if (ok) console.log(`  ok    ${label}`);
    else {
      bad += 1;
      console.error(`  FAIL  ${label}${detail ? `: ${detail}` : ''}`);
    }
  };

  // The shared cases assert the guard itself behaves; importing them is what
  // makes this gate part of the same contract rather than a lookalike.
  for (const c of sharedSelftestCases()) check(`shared: ${c.name}`, c.ok, c.detail);

  const old = ['a.yml:FOO', 'a.yml:BAR'];
  check(
    'a NEW org-scope read is an addition',
    baselineAdditions(old, [...old, 'b.yml:NEW']).join() === 'b.yml:NEW'
  );
  // CONTROL: the same call with nothing new must be empty, or the assertion above
  // would pass against a baselineAdditions that reports everything.
  check('CONTROL: an unchanged set adds nothing', baselineAdditions(old, old).length === 0);
  check(
    'the write path REFUSES a growing set',
    writeBaselineVerdict({
      baselineExists: true,
      firstSeedFlag: false,
      additions: ['b.yml:NEW'],
    })?.kind === 'would-grow'
  );
  // CONTROL: draining must be permitted, or the gate would freeze the backlog
  // forever instead of ratcheting it down.
  check(
    'CONTROL: the write path ALLOWS a shrinking set',
    writeBaselineVerdict({ baselineExists: true, firstSeedFlag: false, additions: [] }) === null
  );
  // The floor is the difference between "clean" and "did not run".
  check('an empty corpus is under the floor', countWorkflows('/nonexistent') < MIN_WORKFLOWS);
  // CONTROL: the REAL corpus must clear it, or the floor would red every run and
  // get raised away by the next person who trips on it.
  check('CONTROL: the real corpus clears the floor', countWorkflows(WORKFLOWS) >= MIN_WORKFLOWS);
  check('the allowlist exempts GITHUB_TOKEN', ALLOWED.has('GITHUB_TOKEN'));
  check('the allowlist exempts the bootstrap', ALLOWED.has('BWS_ACCESS_TOKEN'));

  if (n < 10) {
    console.error(`FAIL  only ${n} control(s) ran; the battery is not being executed as written`);
    bad += 1;
  }
  console.log(bad ? `FAIL: ${bad} of ${n} control(s) failed` : `${n} control(s) passed`);
  return bad ? 1 : 0;
}

function main(): number {
  if (process.argv.includes('--selftest')) return selftest();

  const seen = countWorkflows(WORKFLOWS);
  if (seen < MIN_WORKFLOWS) {
    console.error(
      [
        `✗ VACUOUS: scanned ${seen} workflow file(s) in ${WORKFLOWS}, floor is ${MIN_WORKFLOWS}.`,
        '  The scan did not run against the real corpus, so its silence means nothing.',
        '  Check the path before trusting any verdict from this gate.',
      ].join('\n')
    );
    return 1;
  }

  const current = scan(WORKFLOWS);

  if (process.argv.includes('--write-baseline')) {
    const ok = commitBaseline({
      path: BASELINE,
      label: '.ci/config/secret-scope-baseline.json',
      noun: 'org-scope secret read',
      key: KEY,
      note:
        'SHRINK-ONLY. Workflow reads of secrets that no longer exist: the rediacc org ' +
        'action secrets were all deleted 2026-09-05, so every id here resolves to the ' +
        'EMPTY STRING at run time. Fetch from Bitwarden instead; the name mapping is ' +
        '.ci/config/bws-secret-map.json and .ci/config/github-secret-preimage.json. ' +
        'The goal state is an empty list.',
      current,
      firstSeed: process.argv.includes('--first-seed'),
      read: (p) => (existsSync(p) ? readFileSync(p, 'utf8') : null),
      write: (p, body) => writeFileSync(p, body),
    });
    return ok ? 0 : 1;
  }

  const previous = readBaseline();
  const added = baselineAdditions(previous, current);
  if (added.length > 0) {
    console.error('✗ NEW org-scope secret read(s). These resolve to the EMPTY STRING:');
    for (const a of added) console.error(`    ${a}`);
    console.error('  The org secrets were deleted 2026-09-05. Fetch from Bitwarden instead;');
    console.error('  see .ci/config/bws-secret-map.json for the name mapping.');
    return 1;
  }
  const drained = previous.filter((p) => !current.includes(p));
  if (drained.length > 0) {
    console.error(
      `✗ ${drained.length} read(s) migrated -- ratchet the baseline in the same commit:`
    );
    for (const d of drained.slice(0, 10)) console.error(`    ${d}`);
    console.error('  Run: npx tsx scripts/check-secret-scope.ts --write-baseline');
    return 1;
  }
  console.log(`✓ secret scope: ${current.length} org-scope read(s) frozen, none added`);
  console.log('  Blind spot: cannot verify the org secrets are GONE -- that needs admin:org,');
  console.log("  which CI's GITHUB_TOKEN lacks. This checks the reads, which is what breaks jobs.");
  return 0;
}

process.exit(main());
