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
const SCHEMA_KEY = /^\s{2}([A-Z][A-Z0-9_]*):\s*(?:z\.|z$|boolFromEnv)/gm;

/**
 * Every two-space UPPERCASE key in the schema file, whatever its value looks like.
 *
 * THE ORACLE FOR THE ONE ABOVE, and it exists because a hand-maintained count is a
 * count nobody maintains. This used to be `EXPECTED_SCHEMA_KEYS = 85`, a ratchet a
 * session was trusted to bump in the same commit -- so the gate's protection against
 * "the extractor silently lost a key" was itself editable by the session losing it.
 * Deriving the number from the file removes the trust: adding a key on purpose moves
 * BOTH counts and needs no edit, while a value shape the strict regex cannot read
 * moves only one and reds.
 *
 * `^ {2}(?! )` and not `^\s{2}`: the latter matches the first two spaces of a
 * FOUR-space nested line, which would inflate this side and make the comparison
 * report a loss that is not there. The strict regex above is anchored by `z.` /
 * `boolFromEnv` so it never had that problem; this one has no anchor and needs the
 * negative lookahead instead.
 */
const ANY_SCHEMA_LINE = /^ {2}(?! )([A-Z][A-Z0-9_]*):/gm;

export function schemaLineKeys(text: string): Set<string> {
  return new Set([...text.matchAll(ANY_SCHEMA_LINE)].map((m) => m[1]));
}

export function pushedKeys(text: string): string[] {
  return [...text.matchAll(PUSHED_KEY)].map((m) => m[1]);
}

export function schemaKeys(text: string): Set<string> {
  return new Set([...text.matchAll(SCHEMA_KEY)].map((m) => m[1]));
}

// ── Control: both extractors, before either is trusted ─────────────────────
{
  const jq =
    'jq -n \\\n  --arg a "$A" \\\n  \'{\n        ED25519_PRIVATE_KEY: $a,\n        API_KEY: $b,\n        lower_case: $c,\n  }\'';
  const got = pushedKeys(jq);
  if (got.join(',') !== 'ED25519_PRIVATE_KEY,API_KEY') {
    console.error(
      `✗ instrument control: pushed-key extractor read ${JSON.stringify(got)} from a fixture that pushes ED25519_PRIVATE_KEY and API_KEY (and a lowercase decoy). Every verdict below would be meaningless.`
    );
    process.exit(1);
  }
  const schema =
    'export const envSchema = z.object({\n  ED25519_PRIVATE_KEY: z.string().min(1),\n  CI_MODE: boolFromEnv.optional(),\n    NESTED_NOT_A_KEY: z.string(),\n  // API_KEY: z.string()  (a comment)\n});';
  const keys = schemaKeys(schema);
  if (
    !keys.has('ED25519_PRIVATE_KEY') ||
    !keys.has('CI_MODE') ||
    keys.has('NESTED_NOT_A_KEY') ||
    keys.has('API_KEY')
  ) {
    console.error(
      `✗ instrument control: schema-key extractor read ${JSON.stringify([...keys])}; expected exactly ED25519_PRIVATE_KEY and CI_MODE (not a 4-space nested line, not a commented one).`
    );
    process.exit(1);
  }
  // The failure direction: a pushed name the schema lacks MUST be reportable.
  if (pushedKeys('        RENAMED_KEY: $x,\n').length !== 1 || keys.has('RENAMED_KEY')) {
    console.error(
      '✗ instrument control did not fire: a pushed key absent from the schema was not detectable.'
    );
    process.exit(1);
  }
  // And the ORACLE, in both directions. It replaced a hand-maintained count, so it
  // has to be proven to (a) agree with the strict extractor on a well-formed schema
  // and (b) DISAGREE on the exact shape that defeated the old regex -- a zod chain
  // wrapped onto a second line. Without (b) the comparison could be trivially equal
  // for a reason unrelated to the defect it is here to catch.
  // NOTE ON THE FIXTURE: a chain wrapped as `KEY:\n    z.string()` is NOT the defect
  // shape -- SCHEMA_KEY's `\s*` crosses the newline, so it reads that fine, and the
  // historical `MIN_CLI_VERSION: z` case is covered by the `z$` alternative. The shape
  // that still defeats it is a value that is neither `z.` nor `boolFromEnv`: a new
  // helper added to env.ts. That is what this plants, because a control must plant the
  // defect the comparison can actually catch.
  const helper =
    'export const envSchema = z.object({\n  GOOD_KEY: z.string(),\n  HELPER_KEY: portFromEnv(8080),\n    NESTED_NOT_A_KEY: z.string(),\n});';
  const strict = schemaKeys(helper);
  const loose = schemaLineKeys(helper);
  if (loose.has('NESTED_NOT_A_KEY')) {
    console.error(
      `✗ instrument control: the schema-line oracle counted a FOUR-space nested line, so it would inflate every comparison. Read ${JSON.stringify([...loose])}.`
    );
    process.exit(1);
  }
  if (!loose.has('HELPER_KEY') || strict.has('HELPER_KEY')) {
    console.error(
      '✗ instrument control did not fire: a key declared with a helper the strict regex does not know must be seen by the oracle and MISSED by the extractor, or the comparison below proves nothing.'
    );
    process.exit(1);
  }
}

const schemaText = readFileSync(join(ROOT, SCHEMA), 'utf8');
const schema = schemaKeys(schemaText);
const schemaLines = schemaLineKeys(schemaText);
// 80, not 40. The old floor was half the population, which is a guard against the
// extractor finding NOTHING and nothing else -- it sat happily at 84 of 85 while a
// prettier-wrapped chain silently dropped a key. A floor guards against finding
// nothing; only the comparison below guards against finding ALMOST everything.
if (schema.size < 80) {
  console.error(
    `✗ ${SCHEMA} yielded only ${schema.size} keys. The schema extractor lost the file; refusing a verdict.`
  );
  process.exit(1);
}
// AND THE EXACT COUNT, DERIVED FROM THE FILE rather than typed into this one.
// Measured: with the pre-2026-09-02 regex the extractor yielded 84 of 85 -- a
// prettier-wrapped `MIN_CLI_VERSION: z` -- and sailed past a floor of 80 reporting
// "84 schema keys" as though that were the answer.
//
// This used to be `EXPECTED_SCHEMA_KEYS = 85`, a ratchet a session was trusted to bump
// in the same commit. That put the protection against "the extractor silently lost a
// key" inside the reach of the session losing it: editing the number is exactly as easy
// as editing the schema, and a red that says "expected 85, got 84" invites the wrong
// one. Comparing against a SECOND reading of the same file removes the trust. A key
// added on purpose moves both counts and needs no edit here; a value shape the strict
// regex cannot read moves only one, and that is the whole defect class.
const lost = [...schemaLines].filter((k) => !schema.has(k));
if (lost.length > 0) {
  console.error(
    `✗ ${SCHEMA} declares ${schemaLines.size} key(s) but the extractor read only ${schema.size}.\n` +
      `  Missed: ${lost.join(', ')}\n` +
      `  The extractor has silently lost a key, which is a latent FALSE POSITIVE: the day\n` +
      `  a builder pushes one of these names, this gate calls a correct push line\n` +
      `  undeclared. Check whether a long zod chain wrapped onto a second line, which is\n` +
      `  exactly how it lost MIN_CLI_VERSION -- SCHEMA_KEY must tolerate the new shape.`
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
    problems.push(
      `    ${file}: MISSING — a builder this gate knows about is gone; update BUILDERS or restore it`
    );
    continue;
  }
  const keys = pushedKeys(text);
  if (keys.length < floor) {
    problems.push(
      `    ${file}: extracted only ${keys.length} pushed key(s), floor is ${floor} — the payload moved or the regex broke`
    );
    continue;
  }
  checked += keys.length;
  for (const k of keys) {
    if (!schema.has(k)) {
      const line = text.split('\n').findIndex((l) => new RegExp(`^\\s+${k}:\\s*\\$`).test(l)) + 1;
      problems.push(
        `    ${file}:${line}  pushes ${k}, which ${SCHEMA} does not declare — zod will STRIP it silently`
      );
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
