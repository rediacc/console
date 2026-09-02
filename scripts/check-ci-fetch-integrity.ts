/**
 * check:ci-fetch-integrity — a remote artifact that CI EXECUTES or EXTRACTS must
 * not come from an unverified or moving source.
 *
 * THE GAP THIS CLOSES. `check:ci-unverified-downloads` gates exactly one surface:
 * Dockerfiles. That was the right scope for the defect it was written for, and it
 * says so. But the same class lives in workflow YAML and `.ci` shell, where nothing
 * looked at all — and on 2026-09-02 two live instances were found there BY HAND:
 *
 *   - `cd-stage.yml` piped an nfpm release tarball straight into `sudo tar`, while
 *     its sibling `ci.yml:810` already verified the very same pin.
 *   - `ci-build-renet.yml` fetched golangci-lint's installer from the `master`
 *     branch — a moving target piped into a shell.
 *
 * Both were fixed. Nothing stopped them being reintroduced, and nothing would have
 * caught them in the first place: every gate over these files checks syntax
 * (actionlint), shell style (shellcheck) or step shape (check-workflow-gates).
 * A workflow that fetches a substituted binary parses perfectly and passes all three.
 *
 * WHAT IS FLAGGED
 *   1. a fetch piped into a shell            curl ... | sh / bash
 *   2. a fetch piped into an extractor       curl ... | tar / unzip / zstd
 *   3. a fetch from a MOVING ref             .../master/..., .../main/...,
 *                                            releases/latest, /latest/
 *
 * Rule 3 is the one people argue with, so state its case: a pinned-but-unverified
 * fetch is a supply-chain risk you can at least reason about, while a fetch from
 * `master` is one you cannot — the bytes are allowed to change under you, and no
 * hash can be written down for them. That is why it is a separate rule from the
 * hash question rather than a softer version of it.
 *
 * DELIBERATELY NOT FLAGGED, so a green is not read as more than it is:
 *   - a plain `curl` that probes an endpoint or calls an API and does not feed its
 *     output to an interpreter or an archiver. Most curls in this tree are that,
 *     and flagging them would make this gate noise and then make it deleted.
 *   - the hash question itself inside Dockerfiles — that is
 *     `check:ci-unverified-downloads`, which owns that surface and is not widened
 *     here. Two focused gates beat one that half-covers both.
 *
 * Run: npx tsx scripts/check-ci-fetch-integrity.ts
 *
 * Control-first: the classifier is proven on synthetic input in both directions,
 * including the two REAL historical defects above, before any verdict is reported,
 * and the run refuses a verdict if the sweep finds fewer files than the floor.
 */

import { readFileSync } from 'node:fs';
import { execSync } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

const SCOPE = [/^\.github\/workflows\/.*\.ya?ml$/, /^\.ci\/scripts\/.*\.sh$/];

const PIPE_TO_SHELL = /(curl|wget)[^|\n]*\|\s*(sudo\s+)?(ba)?sh\b/;
const PIPE_TO_ARCHIVER = /(curl|wget)[^|\n]*\|\s*(sudo\s+)?(tar|unzip|zstd|gunzip)\b/;
const MOVING_REF = /(curl|wget)[^;|\n]*https?:\/\/[^\s"']*(\/(master|main)\/|releases\/latest|\/latest\/)/;

/** Verified in the same breath — a hash or signature check makes the fetch answerable. */
const VERIFIED = /(sha256sum|sha512sum|shasum)\s+(-c|--check)|gpg\s+--verify|cosign\s+verify/;

export interface Finding {
  line: number;
  rule: 'pipe-to-shell' | 'pipe-to-archiver' | 'moving-ref';
  text: string;
}

/**
 * Blank out comment lines and QUOTED SPANS before matching.
 *
 * Both false positives this gate produced on its first measurement were text
 * inside quotes, not invocations: `check-python-lint.sh` ECHOES
 * `curl ... | sh` as advice for a human to run, and
 * `test-unverified-downloads.sh` names `curl|bash` inside an assertion message.
 * Stripping quoted spans removes both while leaving a real invocation visible,
 * because in `curl -fsSL "$URL" | bash` the pipe sits OUTSIDE the quotes.
 */
export function executableText(raw: string): string[] {
  return raw.split('\n').map((l) => {
    const t = l.trimStart();
    if (t.startsWith('#')) return '';
    return l.replace(/'[^']*'/g, "''").replace(/"[^"]*"/g, '""');
  });
}

export function scan(raw: string): Finding[] {
  const lines = executableText(raw);
  const out: Finding[] = [];
  for (let i = 0; i < lines.length; i++) {
    const l = lines[i];
    if (!l) continue;
    // A verification in the same line answers for the fetch on it.
    if (VERIFIED.test(l)) continue;
    if (PIPE_TO_SHELL.test(l)) out.push({ line: i + 1, rule: 'pipe-to-shell', text: l.trim() });
    else if (PIPE_TO_ARCHIVER.test(l))
      out.push({ line: i + 1, rule: 'pipe-to-archiver', text: l.trim() });
    else if (MOVING_REF.test(l)) out.push({ line: i + 1, rule: 'moving-ref', text: l.trim() });
  }
  return out;
}

// ── Control: both directions, including the two REAL historical defects ────
{
  const cases: [string, string, number][] = [
    // The two defects that were found by hand on 2026-09-02. If this gate cannot
    // see these, it has no reason to exist.
    [
      'REAL cd-stage.yml nfpm',
      'curl -sSL https://github.com/goreleaser/nfpm/releases/download/v2.43.1/nfpm.tar.gz | sudo tar -xz -C /usr/local/bin nfpm',
      1,
    ],
    [
      'REAL ci-build-renet.yml golangci-lint from master',
      'curl -sSfL https://raw.githubusercontent.com/golangci/golangci-lint/master/install.sh | sh -s -- -b $(go env GOPATH)/bin',
      1,
    ],
    ['pipe to bash', 'curl -fsSL https://example.com/i.sh | bash', 1],
    ['pipe to unzip', 'wget -qO- https://example.com/x.zip | unzip -', 1],
    ['releases/latest', 'curl -L https://github.com/o/r/releases/latest/download/x -o /tmp/x', 1],
    // ALLOW: without these a gate that flags everything would still pass above.
    ['a plain API call', 'curl -sS -H "X-Auth: $T" https://api.example.com/v4/zones', 0],
    ['an endpoint probe', 'curl -fsS -o /dev/null -w "%{http_code}" "$URL"', 0],
    [
      'a verified fetch',
      'curl -L https://example.com/x.tgz -o x.tgz && echo "$SHA x.tgz" | sha256sum -c - | tar -xz',
      0,
    ],
    ['a comment', '# curl https://x/install.sh | bash is what we must never do', 0],
    // The two false positives measured on this gate's first run.
    ['echoed advice', 'echo "    curl -fsSL https://astral.sh/ruff/install.sh | sh" >&2', 0],
    ['an assertion message', 'assert_exit_code 1 "$rc" "the tree\'s curl|bash fetches"', 0],
  ];
  for (const [name, src, want] of cases) {
    const got = scan(src).length;
    if (got !== want) {
      console.error(
        `✗ instrument control "${name}": scan() found ${got}, expected ${want}, in:\n` +
          `      ${src}\n  Every verdict below would be meaningless.`
      );
      process.exit(1);
    }
  }
}

const files = execSync('git ls-files -z', { cwd: ROOT, encoding: 'utf8', maxBuffer: 64 * 1024 * 1024 })
  .split('\0')
  .filter((p) => p && SCOPE.some((re) => re.test(p)));

// Anti-vacuity floor. 100+ files are in scope today; a broken scope regex would
// silently scan nothing and report green.
const FLOOR = 40;
if (files.length < FLOOR) {
  console.error(
    `✗ scope matched only ${files.length} file(s), floor is ${FLOOR}. The scope regexes or\n` +
      '  the checkout changed. Refusing a verdict over a set this gate does not recognise.'
  );
  process.exit(1);
}

const problems: string[] = [];
for (const rel of files) {
  let raw: string;
  try {
    raw = readFileSync(join(ROOT, rel), 'utf8');
  } catch {
    continue;
  }
  for (const f of scan(raw)) {
    problems.push(`    ${rel}:${f.line}  [${f.rule}]  ${f.text.slice(0, 90)}`);
  }
}

if (problems.length > 0) {
  console.error(
    `✗ unverified CI fetch (${problems.length} site(s)):\n${problems.join('\n')}\n\n` +
      '  A fetch that CI pipes into a shell or an archiver runs bytes nobody checked,\n' +
      '  and a fetch from master/latest runs bytes that are ALLOWED to change. Both\n' +
      '  parse fine, pass actionlint and shellcheck, and build successfully while\n' +
      '  installing a substituted artifact — which is why no other gate sees them.\n\n' +
      '  Fix by pinning an exact version AND verifying it (sha256sum -c, gpg --verify,\n' +
      '  or cosign verify) in the same step, as ci.yml already does for nfpm.'
  );
  process.exit(1);
}

console.log(
  `✓ CI fetch integrity: ${files.length} workflow/script file(s), no fetch piped into a\n` +
    '  shell or archiver and none from a moving ref (11 classifier controls fired,\n' +
    '  including the two real defects fixed by hand on 2026-09-02).\n' +
    '  Blind spot: this does NOT check that a pinned fetch is hash-verified — that is\n' +
    "  check:ci-unverified-downloads' job, and it covers Dockerfiles only."
);
