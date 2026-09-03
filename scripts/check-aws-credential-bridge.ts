/**
 * check:ci-aws-credential-bridge — a script that invokes the `aws` CLI must
 * say where its credentials come from.
 *
 * THE DEFECT CLASS, and it cost seven consecutive red CI runs. R2 speaks the S3
 * API, so this repo drives it with the `aws` CLI. But the secrets are named
 * `CLOUDFLARE_R2_ACCESS_KEY_ID` / `CLOUDFLARE_R2_SECRET_ACCESS_KEY`, and the `aws` CLI only ever reads
 * `AWS_ACCESS_KEY_ID` / `AWS_SECRET_ACCESS_KEY`. Every script that talks to R2
 * therefore has to bridge the two names, and there are exactly two legitimate
 * shapes:
 *
 *   export AWS_ACCESS_KEY_ID="$CLOUDFLARE_R2_ACCESS_KEY_ID"   -- bridge it itself, or
 *   : "${AWS_ACCESS_KEY_ID:?...}"                  -- require it from the caller
 *
 * `.ci/scripts/release/assert-edge-tag-exists.sh` did NEITHER. It required
 * `CLOUDFLARE_R2_ENDPOINT`, never mentioned `AWS_` at all, and ran `aws s3api head-object`,
 * which died with `NoCredentials`. Because that script correctly treats "the
 * probe did not reach a verdict" as a failure, `promote-stable.yml` failed all
 * seven runs from 2026-08-27 onward and has never once been green since.
 *
 * WHY NO EXISTING CHECK SAW IT. check_secret_reachability.py proves a workflow's
 * `secrets.X` references are reachable from the repo, and all three of
 * promote-stable's R2 secrets are. The gap is one layer below the workflow,
 * inside the script body, where the name changes. This is the same class as the
 * runtime-constructed names in agent/PLAN-secret-namespace-migration.md Part 7:
 * a find-and-replace on `CLOUDFLARE_R2_ACCESS_KEY_ID` sees the consumer and never sees the
 * `AWS_*` name it turns into.
 *
 * Run: npx tsx scripts/check-aws-credential-bridge.ts
 *
 * Control-first: the classifier is proven on synthetic input in BOTH directions
 * before it is trusted, and the run refuses a verdict if the sweep finds fewer
 * callers than the floor below — a scan that matches nothing cannot fail.
 */

import { readFileSync } from 'node:fs';
import { execFileSync } from 'node:child_process';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/**
 * `aws` at a command position, followed by a service. Anchored to start-of-line
 * or a shell command separator so `# aws s3 ...` in prose and `$FAKEBIN/aws` do
 * not count, and restricted to the services actually used here rather than a
 * bare `aws\s` that matches any mention.
 *
 * A bare `(` and a backtick are deliberately NOT separators here. Both were in
 * the first draft and both produced false positives on the very first run — a
 * backtick matched `\`aws s3 ls\`` inside prose, and `(` matched this repo's own
 * linter data, `PIPE_HEADS_REGEX='(aws s3 ls|...)'`. Blind spot accepted in
 * exchange: a real `( aws s3 cp ... )` subshell would be missed. `$(` is kept
 * explicitly, which is the form the actual defect used.
 */
const INVOKES_AWS =
  /(^|[;&|!]|\$\(|\b(if|elif|while|until|then|do|else)\b|&&|\|\|)\s*aws\s+(s3|s3api|ses|iam|sts|configure)\b/m;

/** Bridges the R2 name onto the AWS one itself. */
const BRIDGES = /^\s*export\s+AWS_(ACCESS_KEY_ID|SECRET_ACCESS_KEY)=/m;

/** Demands it from the caller, in any of the shapes this repo uses. */
const REQUIRES = /(\$\{AWS_ACCESS_KEY_ID|"?\$AWS_ACCESS_KEY_ID|require_var\s+AWS_ACCESS_KEY_ID)/m;

/**
 * A test harness that puts its OWN `aws` earlier in PATH is not talking to R2
 * at all, so it needs no credentials. Detected by the stub it writes rather than
 * by its path — a path allowlist would also excuse a real script that happened
 * to live under a test directory.
 */
const STUBS_AWS = /(FAKEBIN|STUBDIR|BINDIR|fakebin)[^\n]*\/aws\b|cat\s*>\s*"?\$\w+\/aws"?/m;

export type Verdict = 'ok-bridges' | 'ok-requires' | 'ok-stubs' | 'MISSING' | 'not-a-caller';

/**
 * Drop lines that only MENTION the aws CLI. Two shapes, both of which produced
 * false positives on the first run of this gate and are pinned as controls
 * below: a comment (`# Rationale: \`aws s3 ls\` returns 1 when...`) and a
 * quoted fixture line inside a linter's own test data. Matching the mention
 * rather than the invocation is the classic way a scanner turns loud and then
 * gets deleted.
 */
function executableLines(text: string): string {
  return (
    text
      .split('\n')
      .filter((l) => !l.trimStart().startsWith('#'))
      // Blank out single-quoted spans. `aws` inside them is DATA, not a call --
      // this repo's own silent-failure linter holds
      // `PIPE_HEADS_REGEX='(aws s3 ls|...)'`, and a scanner that reads its
      // colleague's pattern table as an invocation is just noise. A real
      // `echo x | aws s3 cp -` (upload-to-r2.sh:213) sits OUTSIDE any quotes and
      // survives this, which is why the `|` separator can stay.
      .map((l) => l.replace(/'[^']*'/g, "''"))
      .join('\n')
  );
}

export function classify(raw: string): Verdict {
  const text = executableLines(raw);
  if (!INVOKES_AWS.test(text)) return 'not-a-caller';
  if (STUBS_AWS.test(raw)) return 'ok-stubs';
  if (BRIDGES.test(raw)) return 'ok-bridges';
  if (REQUIRES.test(raw)) return 'ok-requires';
  return 'MISSING';
}

// ── Control: the classifier, every arm, before it is trusted ───────────────
let CONTROL_ARMS = 0;
{
  const cases: [string, Verdict][] = [
    ['#!/bin/bash\naws s3 cp a b\n', 'MISSING'],
    [
      '#!/bin/bash\nexport AWS_ACCESS_KEY_ID="$CLOUDFLARE_R2_ACCESS_KEY_ID"\naws s3 cp a b\n',
      'ok-bridges',
    ],
    ['#!/bin/bash\n: "${AWS_ACCESS_KEY_ID:?must be set}"\naws s3 ls\n', 'ok-requires'],
    ['#!/bin/bash\ncat >"$FAKEBIN/aws" <<EOF\nEOF\naws s3 ls\n', 'ok-stubs'],
    ['#!/bin/bash\n# aws s3 cp is what the deploy does\necho hi\n', 'not-a-caller'],
    ['#!/bin/bash\nif aws s3api head-object; then :; fi\n', 'MISSING'],
    ['#!/bin/bash\nwhile aws s3 ls; do :; done\n', 'MISSING'],
    ['#!/bin/bash\nout="$(aws s3api head-object --bucket b)" || rc=$?\n', 'MISSING'],
    ['#!/bin/bash\nrun_it "$FAKEBIN/aws" s3 ls\n', 'not-a-caller'],
    // The two false positives this gate's own first run produced. Both are
    // MENTIONS, not invocations, and both must stay invisible to it.
    ['#!/bin/bash\n# Rationale: `aws s3 ls --recursive` returns exit code 1\n', 'not-a-caller'],
    [
      '#!/bin/bash\nassert_x \\\n    \'    count="$(aws s3api list-objects-v2)"\' \\\n',
      'not-a-caller',
    ],
    ["#!/bin/bash\nPIPE_HEADS_REGEX='(aws s3 ls|find [^|])'\n", 'not-a-caller'],
    // ...while a genuine pipe INTO aws, outside quotes, must still be seen.
    ['#!/bin/bash\necho "$c" | aws s3 cp - s3://b/k\n', 'MISSING'],
  ];
  CONTROL_ARMS = cases.length;
  for (const [text, want] of cases) {
    const got = classify(text);
    if (got !== want) {
      console.error(
        `✗ instrument control: classifier returned "${got}", expected "${want}", for:\n` +
          text.replace(/^/gm, '      ') +
          '  Every verdict below would be meaningless.'
      );
      process.exit(1);
    }
  }
}

const files = execFileSync('git', ['ls-files', '--recurse-submodules', '-z', '*.sh'], {
  cwd: ROOT,
  encoding: 'utf8',
  maxBuffer: 64 * 1024 * 1024,
})
  .split('\0')
  .filter(Boolean);

if (files.length === 0) {
  console.error('✗ git ls-files matched no shell scripts; refusing to pass vacuously.');
  process.exit(1);
}

const callers: string[] = [];
const problems: string[] = [];
for (const rel of files) {
  let text: string;
  try {
    text = readFileSync(join(ROOT, rel), 'utf8');
  } catch {
    continue; // a submodule that is not checked out
  }
  const verdict = classify(text);
  if (verdict === 'not-a-caller') continue;
  callers.push(rel);
  if (verdict === 'MISSING') {
    const line =
      text.split('\n').findIndex((l) => {
        const t = l.trimStart();
        if (t.startsWith('#')) return false;
        return INVOKES_AWS.test(l.replace(/'[^']*'/g, "''"));
      }) + 1;
    problems.push(`    ${rel}:${line} invokes the aws CLI with no AWS_ACCESS_KEY_ID in sight`);
  }
}

// Anti-vacuity floor. Chosen below the 25 callers present on 2026-09-02 so
// ordinary churn does not trip it, but high enough that a broken regex — which
// would silently classify everything as 'not-a-caller' — cannot read as green.
const FLOOR = 15;
if (callers.length < FLOOR) {
  console.error(
    `✗ found only ${callers.length} aws-CLI caller(s), floor is ${FLOOR}. Either the\n` +
      '  matcher broke or the scripts moved. A scan that matches nothing cannot fail,\n' +
      '  so this refuses a verdict rather than reporting a green it did not earn.'
  );
  process.exit(1);
}

if (problems.length > 0) {
  console.error(
    `✗ aws credential bridge missing (${problems.length} script(s)):\n${problems.join('\n')}\n\n` +
      '  R2 secrets are named CLOUDFLARE_R2_ACCESS_KEY_ID / CLOUDFLARE_R2_SECRET_ACCESS_KEY, but the aws CLI\n' +
      '  reads AWS_ACCESS_KEY_ID / AWS_SECRET_ACCESS_KEY. A script that bridges neither\n' +
      '  name nor demands one dies at runtime with "NoCredentials" — which reads as an\n' +
      '  outage or an expired key, not as a missing line. That is exactly how\n' +
      '  promote-stable.yml stayed red for seven runs.\n\n' +
      '  Fix with either:\n' +
      '    export AWS_ACCESS_KEY_ID="$CLOUDFLARE_R2_ACCESS_KEY_ID"      (bridge it here)\n' +
      '    : "${AWS_ACCESS_KEY_ID:?<script>: must be set}"   (demand it from the caller)'
  );
  process.exit(1);
}

console.log(
  `✓ aws credential bridge: ${callers.length} aws-CLI caller(s), each either bridging\n` +
    '  R2_* onto AWS_* or demanding AWS_ACCESS_KEY_ID from its caller (classifier\n' +
    `  control fired on all ${CONTROL_ARMS} arms).\n` +
    '  Blind spot: this proves the NAME is wired, not that the credential is valid,\n' +
    '  and it cannot see a bridge performed by the calling workflow rather than the\n' +
    '  script — those scripts pass here via the "demands it" arm.'
);
