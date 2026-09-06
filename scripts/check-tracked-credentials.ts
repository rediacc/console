#!/usr/bin/env tsx
/**
 * Gate: no credential material may sit in a TRACKED file.
 *
 * WHY THIS EXISTS. On 2026-09-05 the operator asked whether AWS access key IDs were
 * sitting in the clear in agent/PLAN-secret-namespace-migration.md. Four of them were,
 * plus a Cloudflare token id, committed 2026-09-03 into a PUBLIC repo. The secret halves
 * were never there and an access key id cannot authenticate alone -- but it names the
 * account, pairs with any leaked secret half, and is what GitHub's own scanning alerts
 * on. ses-eu and ses-us were rotated, because redacting a value whose history is already
 * on a public remote does not unpublish it.
 *
 * WHY NOTHING CAUGHT IT. Six secret-related gates existed. Exactly one knew the AKIA
 * shape -- scripts/check-env-credential-drift.ts -- and only as TEST FIXTURES; it
 * compares .env against the rotation manifest. Nothing scanned tracked TEXT at all. A
 * design document was never in any gate's scope.
 *
 * SCOPE: `git ls-files`, which is what a runner checks out and what a public remote
 * serves. Untracked working files are out of scope; they are not published. The scan
 * reads the WORKING TREE copy of each tracked path deliberately, so a leak is caught
 * before the commit that publishes it, not after.
 *
 * A PEM HEADER IS A SHAPE; THE BASE64 BODY IS THE SECRET. The first real run of this
 * gate flagged 41 files on `-----BEGIN ... PRIVATE KEY-----` alone. Every one was a
 * header with NO key material: `"-----BEGIN OPENSSH PRIVATE KEY-----\n...\n-----END..."`
 * in docs, in doc-comments, in config fixtures. Matching the header alone makes this
 * gate fire on every document that explains what a private key looks like, and a gate
 * that reds on documentation gets switched off. So a hit requires an actual base64 body
 * (see `hasPemBody`), which takes 41 findings to 2.
 *
 * ...AND THOSE 2 ARE WHY THERE IS A BASELINE. They are legitimate, permanent test
 * fixtures: `validateSSHPrivateKey` cannot be tested without a validly-shaped key. No
 * rule separates a well-made fixture from a real key BY SHAPE -- that is a property of
 * the problem, not a gap in the regex -- so the known ones are frozen by id and anything
 * NEW is an addition. Shrink-only, enforced on the WRITE path through
 * scripts/lib/shrink-only-baseline.ts, the shared guard the other frozen-backlog gates
 * use: a reseed that drains two findings and absorbs one satisfies "the total did not
 * grow" while violating "the set only loses members".
 *
 * The AWS half contributes ZERO baseline entries and is meant to stay that way. Its
 * honest bound really is none: the leak was redacted before this gate existed, and there
 * are no AWS-id fixtures here. Any AKIA/ASIA/AIDA/AROA id is therefore an addition and
 * reds on sight -- which is the class the operator actually asked about.
 *
 * TOKEN SHAPES ARE GATED TOO, and the reason they were nearly left out is worth keeping.
 * `ghp_` and `xox*` both matched on the first run and both hits were synthetic --
 * .claude/hooks/stop/worklist-cases/26-migrate.sh plants `ghp_` + the literal alphabet to
 * prove the worklist store redacts tokens. I first excluded them on the grounds that
 * telling a fixture from a leak would need a baseline; by the time the PEM half was
 * finished this gate HAD a baseline, so that reason had quietly stopped being true and
 * the only thing it still bought was a hole. Operator ruling 2026-09-05: close it. A
 * committed PAT or Slack token now reds on sight, and the one fixture is frozen by id.
 */
/*
 * THE BASELINE MUST STAY TRACKED. CI checks out only tracked files, so an untracked
 * .ci/config/tracked-credentials-baseline.json would leave this gate reading an EMPTY
 * frozen set in CI and reporting both known fixtures as brand-new findings -- red on
 * main, for nothing. It is not declared as a manifest `leaf`, because that field mirrors
 * what package.json resolves to and check:ci-parity enforces the mirror.
 */
import { execFileSync } from 'node:child_process';
import { existsSync, readFileSync, writeFileSync } from 'node:fs';
import { join } from 'node:path';
import {
  baselineAdditions,
  commitBaseline,
  sharedSelftestCases,
  writeBaselineVerdict,
} from './lib/shrink-only-baseline.js';

const ROOT = process.env.TRACKED_CRED_ROOT ?? process.cwd();
const BASELINE = join(ROOT, '.ci', 'config', 'tracked-credentials-baseline.json');
const KEY = 'credentialShapedFindings';

/**
 * AWS access key id: the leak class this gate was written for.
 *
 * THESE TWO MUST STAY VALID IN BOTH ENGINES. Their `.source` is handed to `git grep -E`
 * as the prefilter AND used as a JS RegExp for the precise pass, so one spelling serves
 * both and cannot drift. POSIX ERE has no `(?:` -- writing the alternation as a
 * non-capturing group made git grep exit 128, which the `candidates` guard reported as a
 * failed scan rather than a clean repo. A plain group is legal in both. The
 * `prefilter accepts the patterns` control below runs the real `git grep` so a future
 * PCRE-ism is caught by the selftest instead of on the first real run.
 */
const AWS_RE = /\b(AKIA|ASIA|AIDA|AROA)[0-9A-Z]{16}\b/;
const PEM_BEGIN = /-----BEGIN [A-Z ]*PRIVATE KEY-----/;
/** GitHub personal-access / app / OAuth tokens, and Slack's bot and user tokens. */
const TOKEN_RE = /\b(ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bxox[baprs]-[A-Za-z0-9-]{10,}/;
/** Key material: a base64 run long enough that no prose or elision reaches it. */
const B64_RUN = /^[A-Za-z0-9+/=]{40,}/;

/**
 * ANTI-VACUITY FLOOR. This gate scans a file list; a list that came back empty -- a bad
 * TRACKED_CRED_ROOT, a run outside a work tree, a `git` that failed -- would print the
 * same tick as a clean repo. 4,723 tracked paths exist today, so a floor far below that
 * catches a broken scan without firing on ordinary churn. A check that cannot tell
 * "clean" from "did not run" is not evidence.
 */
const MIN_FILES = 500;

/**
 * True when a PEM header is followed by ACTUAL key material, in either shape this repo
 * writes: a real block whose body is on the next line, or a JSON/TS string literal where
 * the body follows an escaped `\n` on the SAME line. Up to 3 lines of lookahead absorbs
 * the RFC1421 `Proc-Type:`/`DEK-Info:` headers an encrypted key carries.
 */
export function hasPemBody(text: string): boolean {
  const lines = text.split('\n');
  for (let i = 0; i < lines.length; i += 1) {
    const m = PEM_BEGIN.exec(lines[i]);
    if (!m) continue;
    const sameLine = lines[i]
      .slice(m.index + m[0].length)
      .replace(/\\+n/g, '')
      .replace(/^["'\s]+/, '');
    if (B64_RUN.test(sameLine)) return true;
    // The budget counts SKIPPED header lines, not lines looked at: decrementing on the
    // body line too made an encrypted key (Proc-Type, DEK-Info, blank, body) run out of
    // lookahead exactly one line before its own body.
    for (let j = i + 1, skips = 3; j < lines.length; j += 1) {
      const l = lines[j].replace(/^["'\s]+/, '');
      if (B64_RUN.test(l)) return true;
      if (!/^(?:Proc-Type|DEK-Info|\r?$)/.test(l)) break;
      if ((skips -= 1) < 0) break;
    }
  }
  return false;
}

function trackedFiles(root: string): string[] {
  try {
    const out = execFileSync('git', ['-C', root, 'ls-files', '-z'], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'ignore'],
    });
    return out.split('\0').filter(Boolean);
  } catch {
    return []; // the floor below turns this into a loud VACUOUS, never a quiet tick
  }
}

/**
 * `git grep` narrows 4,723 paths to a handful in ~0.15s; the precise check then reads
 * only those. Scanning every tracked file in-process would be correct too, and far
 * slower, for the same answer.
 */
function candidates(root: string): string[] {
  try {
    const out = execFileSync(
      'git',
      [
        '-C',
        root,
        'grep',
        '-lI',
        '-E',
        '-e',
        AWS_RE.source,
        '-e',
        PEM_BEGIN.source,
        '-e',
        TOKEN_RE.source,
      ],
      { encoding: 'utf8', stdio: ['ignore', 'pipe', 'pipe'] }
    );
    return out.split('\n').filter(Boolean);
  } catch (e) {
    // ONLY exit 1 means "no match". Anything else -- a bad pattern, a broken work tree,
    // git missing -- must not be laundered into an empty result set, because an empty
    // result set is indistinguishable from a clean repo and would print the tick.
    const status = (e as { status?: number }).status;
    if (status === 1) return [];
    throw new Error(`git grep failed (exit ${String(status)}); the scan did not run`);
  }
}

/** Ids are `<path>:<shape>`, the form the shared guard expects. */
export function scan(root: string): string[] {
  const ids = new Set<string>();
  for (const f of candidates(root)) {
    let text: string;
    try {
      text = readFileSync(join(root, f), 'utf8');
    } catch {
      continue;
    }
    if (AWS_RE.test(text)) ids.add(`${f}:AWS_KEY_ID`);
    if (hasPemBody(text)) ids.add(`${f}:PEM_BODY`);
    if (TOKEN_RE.test(text)) ids.add(`${f}:TOKEN`);
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

  for (const c of sharedSelftestCases()) check(`shared: ${c.name}`, c.ok, c.detail);

  // ASSEMBLED FROM PARTS, ON PURPOSE. A literal AKIA + 16 in this file makes the gate a
  // finding in its OWN scan the moment the file is tracked -- which is exactly what
  // happened on the first run after `git add`, and the baseline note forbids the easy
  // way out ("rotate it, do not baseline it") for a reason. It also states this gate's
  // honest limit out loud: it matches LITERALS, so a credential split across a
  // concatenation evades it here and anywhere else. Every scanner of this kind shares
  // that limit; the gate is a floor against carelessness, not against intent.
  const plantedAwsId = 'AKIA' + 'WXE5TUDQ4T2EY5KV';
  check('an AWS access key id is detected', AWS_RE.test(`key ${plantedAwsId} here`));
  // CONTROL: without this the gate would fire on every document discussing AWS, and the
  // next person to trip on it would delete the pattern rather than narrow it.
  check('CONTROL: prose naming AKIA does not match', !AWS_RE.test('we rotate the AKIA keys'));
  // The redacted spelling this repo now uses must stay clean, or the gate reds on its own fix.
  check('CONTROL: the redacted spelling is clean', !AWS_RE.test('ses-eu `AKIA...redacted`'));

  // Assembled from parts for the same reason as the AWS id above: a literal here
  // would make this gate a finding in its own scan.
  const ghp = 'ghp' + '_' + 'A1b2C3d4E5f6G7h8I9j0K1l2M3n4O5p6Q7r8';
  check('a GitHub token is detected', TOKEN_RE.test(`token ${ghp} here`));
  check('a Slack token is detected', TOKEN_RE.test('xox' + 'b-1234567890-abcdef'));
  // CONTROL: the prefix alone is a word people write in prose and in docs; only the
  // full shape is a credential.
  check('CONTROL: the bare prefix is not a finding', !TOKEN_RE.test('a ghp_ style token'));
  check('CONTROL: a short xox- string is not a finding', !TOKEN_RE.test('xox-abc'));

  const body = 'MIIEowIBAAKCAQEA7x9kQ2mNvBc3pLzR8dYfWqTgXhJsKmPbNvCxZaEiOuYtRwQl';
  check('a real PEM block is detected', hasPemBody(`-----BEGIN RSA PRIVATE KEY-----\n${body}\n`));
  check(
    'a JSON-escaped PEM string is detected',
    hasPemBody(`{"privateKey":"-----BEGIN OPENSSH PRIVATE KEY-----\\n${body}\\n"}`)
  );
  check(
    'an encrypted PEM is detected past its RFC1421 headers',
    hasPemBody(
      `-----BEGIN RSA PRIVATE KEY-----\nProc-Type: 4,ENCRYPTED\nDEK-Info: AES-128-CBC,A1\n\n${body}\n`
    )
  );
  // THE LOAD-BEARING CONTROL. This exact shape appears in 41 tracked files -- docs,
  // doc-comments, config fixtures. If it ever starts matching, this gate reds on
  // documentation and gets switched off within the day.
  check(
    'CONTROL: a PEM header with an ELISION is not a finding',
    !hasPemBody('"-----BEGIN OPENSSH PRIVATE KEY-----\\n...\\n-----END OPENSSH PRIVATE KEY-----"')
  );
  check(
    'CONTROL: "private key" in prose is not a finding',
    !hasPemBody('the private key is in Bitwarden')
  );

  const old = ['a.ts:PEM_BODY', 'b.ts:PEM_BODY'];
  check(
    'a NEW credential is an addition',
    baselineAdditions(old, [...old, 'c.md:AWS_KEY_ID']).join() === 'c.md:AWS_KEY_ID'
  );
  // CONTROL: or baselineAdditions could be reporting everything and still pass above.
  check('CONTROL: an unchanged set adds nothing', baselineAdditions(old, old).length === 0);
  check(
    'the write path REFUSES a growing set',
    writeBaselineVerdict({
      baselineExists: true,
      firstSeedFlag: false,
      additions: ['c.md:AWS_KEY_ID'],
    })?.kind === 'would-grow'
  );
  // CONTROL: draining must stay possible, or the backlog freezes instead of ratcheting.
  check(
    'CONTROL: the write path ALLOWS a shrinking set',
    writeBaselineVerdict({
      baselineExists: true,
      firstSeedFlag: false,
      additions: [],
    }) === null
  );
  // Proves the ERE half of the contract: git grep must ACCEPT both patterns. Without it
  // a PCRE-only construct passes every JS assertion above and dies on the first real run.
  let prefilterOk = true;
  try {
    candidates(ROOT);
  } catch (e) {
    prefilterOk = false;
    check('prefilter accepts the patterns', false, String(e));
  }
  if (prefilterOk) check('prefilter accepts the patterns (git grep -E)', true);
  // CONTROL: and it must actually FIND a planted id, not merely fail to crash -- a
  // prefilter that matches nothing would hide every finding from the precise pass.
  check('CONTROL: the prefilter finds the fixtures it must', candidates(ROOT).length > 0);
  // CONTROL: this gate's own source must never be a finding. Without it, the next
  // person to inline a literal test key here learns about it from a red main rather
  // than from the selftest they were already running.
  check(
    "CONTROL: this gate's own source is not a finding",
    !scan(ROOT).some((id) => id.startsWith('scripts/check-tracked-credentials.ts:'))
  );
  check('an empty corpus is under the floor', trackedFiles('/nonexistent').length < MIN_FILES);
  // CONTROL: the real corpus must clear it, or the floor reds every run and gets raised away.
  check('CONTROL: the real corpus clears the floor', trackedFiles(ROOT).length >= MIN_FILES);

  if (n < 21) {
    console.error(`FAIL  only ${n} control(s) ran; the battery is not being executed as written`);
    bad += 1;
  }
  console.log(bad ? `FAIL: ${bad} of ${n} control(s) failed` : `${n} control(s) passed`);
  return bad ? 1 : 0;
}

function main(): number {
  if (process.argv.includes('--selftest')) return selftest();

  const seen = trackedFiles(ROOT).length;
  if (seen < MIN_FILES) {
    console.error(
      [
        `✗ VACUOUS: git ls-files returned ${seen} path(s) in ${ROOT}, floor is ${MIN_FILES}.`,
        '  The scan did not run against the real tree, so its silence means nothing.',
      ].join('\n')
    );
    return 1;
  }

  const current = scan(ROOT);

  if (process.argv.includes('--write-baseline')) {
    return commitBaseline({
      path: BASELINE,
      label: '.ci/config/tracked-credentials-baseline.json',
      noun: 'credential-shaped finding in a tracked file',
      key: KEY,
      note:
        'SHRINK-ONLY. Credential SHAPES in tracked files. Entries here are legitimate, ' +
        'permanent test fixtures -- a validly-shaped key or token that a test cannot do ' +
        'without. Nothing separates a good fixture from a real credential by shape, so the ' +
        'known ones are frozen and anything new reds. AWS_KEY_ID entries are NOT expected ' +
        'here at all: there are no AWS-id fixtures in this repo, so one appearing means a ' +
        'real access key id was committed to a PUBLIC remote -- rotate it, do not baseline ' +
        'it. A TOKEN entry is only ever a fixture whose value is visibly synthetic (the one ' +
        'here is the literal alphabet); a real-looking token belongs in a revocation, not ' +
        'in this file.',
      current,
      firstSeed: process.argv.includes('--first-seed'),
      read: (p) => (existsSync(p) ? readFileSync(p, 'utf8') : null),
      write: (p, b) => writeFileSync(p, b),
    })
      ? 0
      : 1;
  }

  const previous = readBaseline();
  const added = baselineAdditions(previous, current);
  if (added.length > 0) {
    console.error('✗ NEW credential material in TRACKED file(s):');
    for (const a of added) console.error(`    ${a}`);
    console.error('  This repo is PUBLIC, and a tracked file is served to anyone who clones it.');
    console.error('  Redaction alone does not undo that -- the value stays in git history, so');
    console.error('  ROTATE what it names. Only baseline it if it is a synthetic test fixture.');
    return 1;
  }
  const drained = previous.filter((p) => !current.includes(p));
  if (drained.length > 0) {
    console.error(
      `✗ ${drained.length} finding(s) gone -- ratchet the baseline in the same commit:`
    );
    for (const d of drained) console.error(`    ${d}`);
    console.error('  Run: npx tsx scripts/check-tracked-credentials.ts --write-baseline');
    return 1;
  }
  console.log(
    `✓ tracked credentials: ${seen} tracked path(s) scanned, ${current.length} known fixture(s), none added`
  );
  return 0;
}

process.exit(main());
