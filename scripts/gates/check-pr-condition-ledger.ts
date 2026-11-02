#!/usr/bin/env tsx
/**
 * check-pr-condition-ledger.ts -- is .ci/config/merged-prs.json behind GitHub?
 *
 * A BLOCKER entry may wait on a PR with the one machine-read clause
 * `REVISIT WHEN PR #<N> MERGES` (or `owner/repo#N`). check:ci-suppression-liveness
 * judges those clauses OFFLINE, against the committed ledger .ci/config/merged-prs.json,
 * because a liveness verdict must move only when a commit moves it. That leaves one
 * question it cannot answer: has a clause-named PR merged on GitHub while the ledger
 * still does not say so? This gate asks exactly that, and nothing else.
 *
 * WHY IT EXISTS. `.ci/policy/.embed-assets-upgrade-blocklist` held k3s back with
 * "REVISIT WHEN PR #589 MERGES" from 2026-09-16; #589 merged 2026-09-22T08:22:16Z and
 * the hold stood for sixteen more days, because nothing read the clause at all.
 *
 * WHAT IT ASKS ABOUT. The PRs the clauses in BLOCKER_FILES name, plus every PR the
 * ledger already records. The second set is a consistency check (a recorded PR that
 * GitHub says is open, closed or absent means the ledger is wrong), and it is also
 * what keeps this gate from being a no-op on a tree with no live clause: the ledger
 * always holds at least one record, so a green run has made at least one real query.
 *
 * VERDICTS
 *   clause-named PR merged, not in the ledger      FAIL  run --refresh
 *   recorded PR merged at a different time         FAIL  the ledger is wrong
 *   recorded PR open / closed unmerged / absent    FAIL  the ledger is wrong
 *   clause-named PR closed without merging         FAIL  the hold waits on nothing
 *   clause-named PR not found                      FAIL  the clause names no PR
 *   clause-named PR still open                     ok    the hold is still waiting
 *   no token                                       local: loud SKIP, exit 0;  CI: FAIL
 *   401 / 403 / 429 (auth, rate limit)             local: UNCHECKED warning;  CI: FAIL
 *   network error, timeout, 5xx                    ::warning, UNCHECKED, exit 0
 *
 * The network row is the plan's ruling (PLAN-k3s-137-and-pr-conditions.md, B): the
 * offline probe is the enforcement, and this gate only reports that the ledger is
 * behind, so a GitHub outage must not redden every branch. Every unchecked PR is
 * still COUNTED and printed; it is never folded into "fine".
 *
 * --refresh writes the merged clause-named PRs into the ledger and stamps
 * refreshed_at. It refuses to write anything when any query went unanswered, so
 * a refreshed_at is only ever a claim it earned. /pr-merge runs it when it cuts the
 * next branch. A refresh that records a clause's PR turns check:ci-suppression-liveness
 * red on that clause, which is the point.
 *
 * Usage:
 *   npx tsx scripts/gates/check-pr-condition-ledger.ts [--refresh] [--selftest]
 *
 * Env:
 *   PR_CONDITION_LEDGER_ROOT  test seam: treat this directory as the repository root
 *   PR_STATE_FIXTURE          test seam: a JSON file answering for GitHub,
 *                             {"token": bool, "prs": {"owner/repo#N": {"state": ...}}}
 *                             where state is merged (with mergedAt), open, closed,
 *                             notfound, denied or network. A ref the fixture does not
 *                             answer is a loud error, never a guess.
 *
 * ---- gate ----
 * step: PR-condition ledger is current
 * needs: node
 * selftest: true
 * lane: quality-security
 * env-GITHUB_TOKEN: ${{ github.token }}
 * ---- end gate ----
 */

import fs from 'node:fs';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import { WK_GH_API_BASE } from '../../packages/shared/src/config/well-known.generated.js';
import { GREEN, NC, RED, YELLOW } from '../lib/console.js';
import { summarizeControls } from '../lib/controls.js';
import { githubToken } from '../lib/github-token.js';
import {
  BLOCKER_FILES,
  ledgerProblem,
  MERGED_PRS_REL,
  type MergedPrLedger,
  readMergedPrLedger,
  scanPrConditions,
} from '../lib/suppression-liveness.js';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.PR_CONDITION_LEDGER_ROOT || path.join(__dirname, '..', '..');

// --------------------------------------------------------------------------- Pure helpers (exported for the selftest) ---------------------------------------------------------------------------

export type PrState =
  | { kind: 'merged'; mergedAt: string }
  | { kind: 'open' }
  | { kind: 'closed' }
  | { kind: 'notfound' }
  | { kind: 'denied'; detail: string }
  | { kind: 'network'; detail: string };

/** One REST response from GET /repos/{owner}/{repo}/pulls/{n}, classified. */
export function classifyResponse(status: number, body: unknown): PrState {
  if (status === 404) return { kind: 'notfound' };
  if (status === 401 || status === 403 || status === 429) {
    return { kind: 'denied', detail: `HTTP ${status}` };
  }
  if (status >= 500) return { kind: 'network', detail: `HTTP ${status}` };
  if (status !== 200) return { kind: 'network', detail: `unexpected HTTP ${status}` };
  const b = (body ?? {}) as { merged_at?: unknown; state?: unknown };
  if (typeof b.merged_at === 'string' && b.merged_at) {
    return { kind: 'merged', mergedAt: b.merged_at };
  }
  if (b.state === 'open') return { kind: 'open' };
  if (b.state === 'closed') return { kind: 'closed' };
  return { kind: 'network', detail: `200 with no usable state (${JSON.stringify(b.state)})` };
}

export interface Verdict {
  ref: string;
  level: 'fail' | 'warn' | 'ok';
  /** True when the PR's state is unknown: counted and printed as UNCHECKED. */
  unchecked: boolean;
  message: string;
}

/**
 * One PR's verdict. `named` is true when some clause names it, `recorded` is its
 * ledger row if any, `ci` decides the denied row, `refresh` turns the one
 * "ledger is behind" failure into the record --refresh is about to write.
 */
export function judge(
  ref: string,
  state: PrState,
  recorded: { mergedAt: string } | undefined,
  opts: { named: boolean; ci: boolean; refresh: boolean }
): Verdict {
  const v = (level: Verdict['level'], message: string, unchecked = false): Verdict => ({
    ref,
    level,
    unchecked,
    message,
  });
  switch (state.kind) {
    case 'network':
      return v('warn', `UNCHECKED: GitHub could not be asked (${state.detail})`, true);
    case 'denied':
      return v(
        opts.ci ? 'fail' : 'warn',
        `UNCHECKED: GitHub refused the query (${state.detail}); auth or rate limit`,
        true
      );
    case 'notfound':
      return v(
        'fail',
        recorded
          ? `${MERGED_PRS_REL} records it, and GitHub has no such PR; delete the row`
          : 'a clause names it, and GitHub has no such PR; fix the clause'
      );
    case 'closed':
      return v(
        'fail',
        recorded
          ? `${MERGED_PRS_REL} records it as merged, and it was CLOSED without merging; delete the row`
          : 'closed without merging, so the hold that waits on it waits on nothing; rewrite the BLOCKER'
      );
    case 'open':
      return recorded
        ? v('fail', `${MERGED_PRS_REL} records it as merged, and it is still OPEN; delete the row`)
        : v('ok', 'still open; the hold is still waiting');
    case 'merged':
      if (!recorded) {
        if (opts.refresh) return v('ok', `merged at ${state.mergedAt}; recorded now`);
        return v(
          'fail',
          `merged at ${state.mergedAt} and ${MERGED_PRS_REL} does not record it; run: npx tsx scripts/gates/check-pr-condition-ledger.ts --refresh`
        );
      }
      if (recorded.mergedAt !== state.mergedAt) {
        return v(
          'fail',
          `${MERGED_PRS_REL} says merged at ${recorded.mergedAt}, GitHub says ${state.mergedAt}`
        );
      }
      return v('ok', `merged at ${state.mergedAt}, recorded`);
  }
}

/** `owner/repo#N` to its REST path. Throws on anything else: a guessed path would be a guessed answer. */
export function pullsPath(ref: string): string {
  const m = /^([\w.-]+)\/([\w.-]+)#(\d+)$/.exec(ref);
  if (!m) throw new Error(`not an owner/repo#N reference: ${JSON.stringify(ref)}`);
  return `/repos/${m[1]}/${m[2]}/pulls/${m[3]}`;
}

// --------------------------------------------------------------------------- GitHub, or the fixture standing in for it ---------------------------------------------------------------------------

interface Fixture {
  token: boolean;
  prs: Record<string, { state: string; mergedAt?: string }>;
}

function loadFixture(file: string): Fixture {
  const raw = JSON.parse(fs.readFileSync(file, 'utf-8')) as Partial<Fixture>;
  if (typeof raw.token !== 'boolean' || !raw.prs || typeof raw.prs !== 'object') {
    throw new Error(`PR_STATE_FIXTURE ${file}: needs {"token": bool, "prs": {...}}`);
  }
  return raw as Fixture;
}

function fixtureState(fx: Fixture, ref: string): PrState {
  const row = fx.prs[ref];
  if (!row)
    throw new Error(
      `PR_STATE_FIXTURE has no answer for ${ref}; a fixture must not be guessed past`
    );
  switch (row.state) {
    case 'merged':
      if (!row.mergedAt) throw new Error(`PR_STATE_FIXTURE: ${ref} is merged with no mergedAt`);
      return { kind: 'merged', mergedAt: row.mergedAt };
    case 'open':
    case 'closed':
    case 'notfound':
      return { kind: row.state };
    case 'denied':
    case 'network':
      return { kind: row.state, detail: 'fixture' };
    default:
      throw new Error(`PR_STATE_FIXTURE: ${ref} has unknown state ${JSON.stringify(row.state)}`);
  }
}

async function githubState(ref: string, token: string): Promise<PrState> {
  let res: Response;
  try {
    res = await fetch(`${WK_GH_API_BASE}${pullsPath(ref)}`, {
      headers: {
        Accept: 'application/vnd.github+json',
        Authorization: `Bearer ${token}`,
        'X-GitHub-Api-Version': '2022-11-28',
      },
      signal: AbortSignal.timeout(15_000),
    });
  } catch (err) {
    return { kind: 'network', detail: (err as Error).message };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    /* a non-JSON body is classified by its status alone */
  }
  return classifyResponse(res.status, body);
}

// --------------------------------------------------------------------------- Selftest ---------------------------------------------------------------------------

function selftest(): number {
  const cases: [string, boolean][] = [];
  const check = (name: string, ok: boolean): void => {
    cases.push([name, ok]);
  };
  const off = { named: true, ci: false, refresh: false };
  const at = '2026-09-22T08:22:16Z';

  check(
    '200 merged_at -> merged',
    classifyResponse(200, { merged_at: at, state: 'closed' }).kind === 'merged'
  );
  check(
    '200 open -> open',
    classifyResponse(200, { merged_at: null, state: 'open' }).kind === 'open'
  );
  check(
    '200 closed unmerged -> closed',
    classifyResponse(200, { merged_at: null, state: 'closed' }).kind === 'closed'
  );
  check('404 -> notfound', classifyResponse(404, {}).kind === 'notfound');
  check('403 -> denied', classifyResponse(403, {}).kind === 'denied');
  check('429 -> denied', classifyResponse(429, {}).kind === 'denied');
  check('502 -> network', classifyResponse(502, null).kind === 'network');
  check(
    '200 garbage -> network, never ok',
    classifyResponse(200, { state: 'weird' }).kind === 'network'
  );

  // Must fire.
  check(
    'merged + unrecorded -> fail',
    judge('o/r#1', { kind: 'merged', mergedAt: at }, undefined, off).level === 'fail'
  );
  check(
    'merged + wrong time -> fail',
    judge('o/r#1', { kind: 'merged', mergedAt: at }, { mergedAt: '2026-01-01T00:00:00Z' }, off)
      .level === 'fail'
  );
  check(
    'recorded + open -> fail',
    judge('o/r#1', { kind: 'open' }, { mergedAt: at }, off).level === 'fail'
  );
  check(
    'closed unmerged -> fail',
    judge('o/r#1', { kind: 'closed' }, undefined, off).level === 'fail'
  );
  check('notfound -> fail', judge('o/r#1', { kind: 'notfound' }, undefined, off).level === 'fail');
  check(
    'denied in CI -> fail',
    judge('o/r#1', { kind: 'denied', detail: 'x' }, undefined, { ...off, ci: true }).level ===
      'fail'
  );
  // Must NOT fire.
  check('open + unrecorded -> ok', judge('o/r#1', { kind: 'open' }, undefined, off).level === 'ok');
  check(
    'merged + recorded same time -> ok',
    judge('o/r#1', { kind: 'merged', mergedAt: at }, { mergedAt: at }, off).level === 'ok'
  );
  check(
    'merged + unrecorded under --refresh -> ok',
    judge('o/r#1', { kind: 'merged', mergedAt: at }, undefined, { ...off, refresh: true }).level ===
      'ok'
  );
  const net = judge('o/r#1', { kind: 'network', detail: 'x' }, undefined, { ...off, ci: true });
  check('network in CI -> warn, unchecked', net.level === 'warn' && net.unchecked);
  check(
    'denied locally -> warn, unchecked',
    judge('o/r#1', { kind: 'denied', detail: 'x' }, undefined, off).unchecked
  );

  check('pullsPath maps a ref', pullsPath('acme/widgets#589') === '/repos/acme/widgets/pulls/589');
  let threw = false;
  try {
    pullsPath('#589');
  } catch {
    threw = true;
  }
  check('pullsPath refuses a bare #N', threw);

  check(
    'ledger: valid',
    ledgerProblem({ format: 1, refreshed_at: at, prs: { 'o/r#1': { mergedAt: at } } }) === null
  );
  check(
    'ledger: unknown format refused',
    ledgerProblem({ format: 2, refreshed_at: at, prs: {} }) !== null
  );
  check(
    'ledger: bare key refused',
    ledgerProblem({ format: 1, refreshed_at: at, prs: { '#1': { mergedAt: at } } }) !== null
  );
  check(
    'ledger: missing mergedAt refused',
    ledgerProblem({ format: 1, refreshed_at: at, prs: { 'o/r#1': {} } }) !== null
  );

  return summarizeControls(cases.map(([name, ok]) => ({ name, ok })));
}

// --------------------------------------------------------------------------- Main ---------------------------------------------------------------------------

async function main(): Promise<number> {
  const args = process.argv.slice(2);
  if (args.includes('--selftest')) return selftest();
  const refresh = args.includes('--refresh');
  const ci = process.env.CI === 'true';
  const annotate = (kind: 'error' | 'warning', msg: string): void => {
    if (ci) console.log(`::${kind} file=${MERGED_PRS_REL}::${msg.replace(/\r?\n/g, ' ')}`);
  };

  const scan = scanPrConditions(ROOT);
  if (scan.filesRead === 0) {
    console.error(
      `${RED}✗${NC} none of the ${BLOCKER_FILES.length} BLOCKER files exists under ${ROOT}; the gate is not seeing the tree, so its green would mean nothing.`
    );
    return 1;
  }
  const ledgerRead = readMergedPrLedger(ROOT);
  if (ledgerRead.kind === 'invalid') {
    console.error(`${RED}✗${NC} ${MERGED_PRS_REL} is unreadable: ${ledgerRead.reason}`);
    return 1;
  }
  if (ledgerRead.kind === 'missing' && !refresh) {
    console.error(
      `${RED}✗${NC} ${MERGED_PRS_REL} is absent. Create it with: npx tsx scripts/gates/check-pr-condition-ledger.ts --refresh`
    );
    return 1;
  }
  const ledger: MergedPrLedger =
    ledgerRead.kind === 'ok'
      ? ledgerRead.ledger
      : { format: 1, refreshed_at: new Date().toISOString().replace(/\.\d+Z$/, 'Z'), prs: {} };

  const named = new Set(scan.conditions.map((c) => c.ref));
  const refs = [...new Set([...named, ...Object.keys(ledger.prs)])].sort(
    (a, b) => Number(a > b) - Number(a < b)
  );
  const shape = `${scan.filesRead}/${BLOCKER_FILES.length} BLOCKER file(s), ${scan.conditions.length} clause(s) naming ${named.size} PR(s), ${Object.keys(ledger.prs).length} recorded`;

  if (refs.length === 0) {
    console.log(`${GREEN}✓${NC} PR-condition ledger: nothing to ask GitHub (${shape}).`);
    return 0;
  }

  const fixtureFile = process.env.PR_STATE_FIXTURE;
  const fixture = fixtureFile ? loadFixture(fixtureFile) : null;
  const token = fixture ? (fixture.token ? 'fixture' : undefined) : githubToken();
  if (!token) {
    const msg = `no GitHub token (GITHUB_TOKEN, GH_TOKEN or \`gh auth login\`), so ${refs.length} PR(s) are UNCHECKED: ${refs.join(', ')}`;
    if (ci) {
      console.error(
        `${RED}✗${NC} ${msg}. In CI this is a failure: give the step GITHUB_TOKEN: \${{ github.token }}.`
      );
      annotate('error', msg);
      return 1;
    }
    console.log(
      `${YELLOW}SKIP${NC}  ${msg}. NOT proven current; run \`gh auth login\` and re-run.`
    );
    return refresh ? 1 : 0;
  }

  const verdicts: Verdict[] = [];
  const merged = new Map<string, string>();
  for (const ref of refs) {
    const state = fixture ? fixtureState(fixture, ref) : await githubState(ref, token);
    if (state.kind === 'merged') merged.set(ref, state.mergedAt);
    verdicts.push(judge(ref, state, ledger.prs[ref], { named: named.has(ref), ci, refresh }));
  }

  console.log(`PR-condition ledger: ${refs.length} PR(s) asked (${shape})`);
  for (const v of verdicts) {
    const label =
      v.level === 'fail'
        ? `${RED}FAIL${NC}`
        : v.level === 'warn'
          ? `${YELLOW}WARN${NC}`
          : `${GREEN}ok${NC}  `;
    console.log(`  ${label}  ${v.ref}  ${v.message}`);
    if (v.level !== 'ok')
      annotate(v.level === 'fail' ? 'error' : 'warning', `${v.ref}: ${v.message}`);
  }
  const fails = verdicts.filter((v) => v.level === 'fail').length;
  const unchecked = verdicts.filter((v) => v.unchecked).length;

  if (refresh) {
    if (fails > 0 || unchecked > 0) {
      console.error(
        `${RED}✗${NC} --refresh wrote nothing: ${fails} failing and ${unchecked} UNCHECKED PR(s). A refreshed_at is only stamped when every query was answered.`
      );
      return 1;
    }
    const added: string[] = [];
    for (const ref of named) {
      const at = merged.get(ref);
      if (at && !ledger.prs[ref]) {
        ledger.prs[ref] = { mergedAt: at };
        added.push(ref);
      }
    }
    const sorted: MergedPrLedger = {
      format: 1,
      refreshed_at: new Date().toISOString().replace(/\.\d+Z$/, 'Z'),
      prs: Object.fromEntries(
        Object.entries(ledger.prs).sort(([a], [b]) => (a < b ? -1 : a > b ? 1 : 0))
      ),
    };
    fs.mkdirSync(path.dirname(path.join(ROOT, MERGED_PRS_REL)), { recursive: true });
    fs.writeFileSync(path.join(ROOT, MERGED_PRS_REL), `${JSON.stringify(sorted, null, 2)}\n`);
    console.log(
      `${GREEN}✓${NC} wrote ${MERGED_PRS_REL}: ${added.length} PR(s) added${added.length ? ` (${added.join(', ')})` : ''}, ${Object.keys(sorted.prs).length} recorded.` +
        (added.length
          ? ' check:ci-suppression-liveness now fails on every clause naming them; lift those holds.'
          : '')
    );
    return 0;
  }

  if (fails > 0) {
    console.error(`${RED}✗${NC} ${fails} PR(s) disagree with ${MERGED_PRS_REL}.`);
    return 1;
  }
  if (unchecked > 0) {
    console.log(
      `${YELLOW}⚠${NC} ${unchecked} of ${refs.length} PR(s) UNCHECKED; the ledger is NOT proven current.`
    );
    return 0;
  }
  console.log(`${GREEN}✓${NC} ${MERGED_PRS_REL} agrees with GitHub on all ${refs.length} PR(s).`);
  return 0;
}

main().then(
  (rc) => process.exit(rc),
  (err: Error) => {
    console.error(`${RED}✗${NC} check-pr-condition-ledger: ${err.message}`);
    process.exit(1);
  }
);
