/**
 * check:ci-worker-secret-names — every name a deploy script pushes to a Worker
 * must be a name the Worker's env schema actually reads.
 *
 * THE DEFECT CLASS. Five scripts build a `wrangler secret bulk` payload by hand:
 *
 *   .ci/scripts/deploy/set-account-worker-secrets.sh
 *   .ci/scripts/deploy/set-www-worker-secrets.sh
 *   .ci/scripts/deploy/set-preview-worker-secrets.sh
 *   scripts/dev/deploy-bench.sh
 *   run.sh                                (the local PR-preview builder)
 *
 * and one file says what the Worker will look at:
 *
 *   private/account/src/types/env.ts      (zod schema, 85 keys)
 *
 * Nothing compared the two. And the way they disagree is SILENT: zod v4's
 * `z.object()` STRIPS unknown keys — verified against the installed 4.5.4 — so
 * a pushed name the schema does not know is discarded with no diagnostic, and
 * the Worker reads the key as absent. Only 6 of the 85 keys throw on absence;
 * the other 79 degrade in silence. The worst case measured this session: rename
 * both `AWS_SES_*` keys on the push side and the Worker builds an EmailService
 * with a null transport — magic-link login stops, every request still returns
 * 200, and nothing anywhere reports an error.
 *
 * That is exactly the shape a rename produces, and this repo is about to rename
 * every one of these. This gate is the check that would have caught the whole
 * class, and it is being landed BEFORE the rename so the rename's mistakes are
 * loud.
 *
 * WHAT IS CHECKED. For each builder, every `KEY: $var` line inside its jq
 * payload must name a key declared in env.ts. Direction is one-way on purpose:
 * env.ts legitimately declares far more than any one builder pushes (the
 * preview builder pushes 15 of 85), so "schema key nobody pushes" is not a
 * finding.
 *
 * Run: npx tsx scripts/check-worker-secret-names.ts
 *
 * Control-first: both extractors are proven on synthetic input before any
 * verdict, each builder has a per-file floor so a broken regex cannot read as
 * "nothing to check", and the failure control plants a renamed key.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

const SCHEMA = 'private/account/src/types/env.ts';

/**
 * The five builders and the fewest keys each is known to push (measured
 * 2026-09-02: 29/24/15/29/15). A count below the floor means the extractor
 * lost the payload, not that the payload shrank — refuse rather than pass.
 */
const BUILDERS: { file: string; floor: number }[] = [
  { file: '.ci/scripts/deploy/set-account-worker-secrets.sh', floor: 20 },
  { file: '.ci/scripts/deploy/set-www-worker-secrets.sh', floor: 15 },
  { file: '.ci/scripts/deploy/set-preview-worker-secrets.sh', floor: 10 },
  { file: 'scripts/dev/deploy-bench.sh', floor: 20 },
  { file: 'run.sh', floor: 10 },
];

/** `        KEY: $var,` inside a `jq -n '{ ... }'` object — the payload shape. */
const PUSHED_KEY = /^\s+([A-Z][A-Z0-9_]*):\s*\$/gm;

/** `  KEY: z.` or `  KEY: boolFromEnv` — a declared schema key. */
// `z$` matters: prettier wraps a long chain, leaving `MIN_CLI_VERSION: z` with the
// `.string()` on the NEXT line. Requiring `z.` on one line silently dropped that key,
// so the gate extracted 84 of 85 and the `size < 40` floor is far too low to notice.
// A one-key loss here is a latent FALSE POSITIVE: the day a builder pushes that name,
// the gate calls a correct push line undeclared.
const EXPECTED_SCHEMA_KEYS = 85;

const SCHEMA_KEY = /^\s{2}([A-Z][A-Z0-9_]*):\s*(?:z\.|z$|boolFromEnv)/gm;

export function pushedKeys(text: string): string[] {
  return [...text.matchAll(PUSHED_KEY)].map((m) => m[1]);
}

export function schemaKeys(text: string): Set<string> {
  return new Set([...text.matchAll(SCHEMA_KEY)].map((m) => m[1]));
}

// ── Control: both extractors, before either is trusted ─────────────────────
{
  const jq = "jq -n \\\n  --arg a \"$A\" \\\n  '{\n        ED25519_PRIVATE_KEY: $a,\n        API_KEY: $b,\n        lower_case: $c,\n  }'";
  const got = pushedKeys(jq);
  if (got.join(',') !== 'ED25519_PRIVATE_KEY,API_KEY') {
    console.error(`✗ instrument control: pushed-key extractor read ${JSON.stringify(got)} from a fixture that pushes ED25519_PRIVATE_KEY and API_KEY (and a lowercase decoy). Every verdict below would be meaningless.`);
    process.exit(1);
  }
  const schema = "export const envSchema = z.object({\n  ED25519_PRIVATE_KEY: z.string().min(1),\n  CI_MODE: boolFromEnv.optional(),\n    NESTED_NOT_A_KEY: z.string(),\n  // API_KEY: z.string()  (a comment)\n});";
  const keys = schemaKeys(schema);
  if (!keys.has('ED25519_PRIVATE_KEY') || !keys.has('CI_MODE') || keys.has('NESTED_NOT_A_KEY') || keys.has('API_KEY')) {
    console.error(`✗ instrument control: schema-key extractor read ${JSON.stringify([...keys])}; expected exactly ED25519_PRIVATE_KEY and CI_MODE (not a 4-space nested line, not a commented one).`);
    process.exit(1);
  }
  // The failure direction: a pushed name the schema lacks MUST be reportable.
  if (pushedKeys('        RENAMED_KEY: $x,\n').length !== 1 || keys.has('RENAMED_KEY')) {
    console.error('✗ instrument control did not fire: a pushed key absent from the schema was not detectable.');
    process.exit(1);
  }
}

const schema = schemaKeys(readFileSync(join(ROOT, SCHEMA), 'utf8'));
// 80, not 40. The old floor was half the population, which is a guard against the
// extractor finding NOTHING and nothing else -- it sat happily at 84 of 85 while a
// prettier-wrapped chain silently dropped a key. Be honest about the limit: no floor
// catches a one-key loss without being exact, and exact breaks the day a key is added
// on purpose. What catches that class is the regex tolerating a wrapped value, above.
if (schema.size < 80) {
  console.error(`✗ ${SCHEMA} yielded only ${schema.size} keys (${EXPECTED_SCHEMA_KEYS} expected). The schema extractor lost the file; refusing a verdict.`);
  process.exit(1);
}
// AND THE EXACT COUNT, because the floor above provably cannot do this job. Measured:
// with the pre-2026-09-02 regex the extractor yielded 84 of 85 -- a prettier-wrapped
// `MIN_CLI_VERSION: z` -- and sailed past a floor of 80 reporting "84 schema keys" as
// though that were the answer. A floor guards against finding NOTHING; only an exact
// count guards against finding ALMOST everything, which is the shape that produces a
// false positive on the day a builder starts pushing the dropped key.
//
// This number is a RATCHET, not a constant: change env.ts's key set on purpose and
// update it in the same commit. That is the deliberate step the old prose "85 expected"
// only pretended to be.
if (schema.size !== EXPECTED_SCHEMA_KEYS) {
  console.error(
    `✗ ${SCHEMA} yielded ${schema.size} keys, expected exactly ${EXPECTED_SCHEMA_KEYS}.\n` +
      `  If you added or removed a schema key on purpose, update EXPECTED_SCHEMA_KEYS in\n` +
      `  ${'scripts/check-worker-secret-names.ts'} in the same change. If you did not, the\n` +
      `  extractor has silently lost a key -- check whether a long zod chain wrapped onto a\n` +
      `  second line, which is exactly how it lost MIN_CLI_VERSION.`
  );
  process.exit(1);
}

const problems: string[] = [];
let checked = 0;
for (const { file, floor } of BUILDERS) {
  let text: string;
  try {
    text = readFileSync(join(ROOT, file), 'utf8');
  } catch {
    problems.push(`    ${file}: MISSING — a builder this gate knows about is gone; update BUILDERS or restore it`);
    continue;
  }
  const keys = pushedKeys(text);
  if (keys.length < floor) {
    problems.push(`    ${file}: extracted only ${keys.length} pushed key(s), floor is ${floor} — the payload moved or the regex broke`);
    continue;
  }
  checked += keys.length;
  for (const k of keys) {
    if (!schema.has(k)) {
      const line = text.split('\n').findIndex((l) => new RegExp(`^\\s+${k}:\\s*\\$`).test(l)) + 1;
      problems.push(`    ${file}:${line}  pushes ${k}, which ${SCHEMA} does not declare — zod will STRIP it silently`);
    }
  }
}

if (problems.length > 0) {
  console.error(
    `✗ worker secret names disagree with the schema (${problems.length}):\n${problems.join('\n')}\n\n` +
      '  A name pushed to a Worker that its env schema does not read is not an error\n' +
      "  anywhere: zod v4 strips unknown keys, and 79 of the schema's 85 keys are\n" +
      '  optional, so the value is discarded and the feature quietly turns itself off.\n' +
      '  Fix the builder to push the declared name, or declare the key in env.ts.'
  );
  process.exit(1);
}

console.log(
  `✓ worker secret names: ${checked} pushed key(s) across ${BUILDERS.length} builder(s) are all\n` +
    `  declared in ${SCHEMA} (${schema.size} schema keys; extractor controls fired both ways).\n` +
    '  Blind spot: this proves the NAMES agree. It cannot see an empty VALUE, which zod\n' +
    "  normalises to undefined and validates — that is the deploy scripts' non-empty\n" +
    '  guards, not this gate.'
);
