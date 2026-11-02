/**
 * check:ci-worker-secret-names — every name a deploy script pushes to a Worker
 * must be a name the Worker's env schema actually reads.
 *
 * THE DEFECT CLASS. Four builders hand-build a `wrangler secret bulk` payload:
 *
 *   .ci/rediacc_ci/deploy/set_account_worker_secrets.py   (module-level `KEYS` tuple)
 *   .ci/rediacc_ci/deploy/set_www_worker_secrets.py       (module-level `KEYS` tuple)
 *   .ci/rediacc_ci/deploy/set_preview_worker_secrets.py   (module-level `KEYS` tuple)
 *   .ci/rediacc_ci/ops/deploy_bench.py    (a Python dict, `secrets_payload()`)
 *
 * It was five until 2026-09-22; see the note on BUILDERS for where the fifth went.
 *
 * The three `set_*_worker_secrets.py` ports are what CI invokes
 * (`rediacc_ci.deploy.set_*_worker_secrets`); their bash twins are deleted. Each
 * port builds its jq payload from the `KEYS` tuple, so the tuple is the list of
 * names pushed, and this gate reads it.
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
 * WHAT IS CHECKED. For each builder, every row of its `KEYS` tuple (for
 * deploy_bench.py, every `"KEY":` entry of the dict `secrets_payload()` returns)
 * must name a key declared in env.ts. Direction is one-way on purpose:
 * env.ts legitimately declares far more than any one builder pushes (the
 * preview builder pushes 15 of 85), so "schema key nobody pushes" is not a
 * finding.
 *
 * LIVE EXTRAS (advisory). With CLOUDFLARE_API_TOKEN and CLOUDFLARE_ACCOUNT_ID in the
 * environment (`bws_env exec --profile deploy-workers`), the gate also asks
 * `rediacc_ci.ops.prune_worker_secrets --json` which secrets the live account Workers
 * hold that the push no longer carries, and prints them. A bulk push only adds, so a
 * renamed key lingers on the Worker; `prune_worker_secrets --delete` removes it. Without
 * a token the section is skipped and says so. It never changes the exit code: CI has no
 * token, and a live Worker is not part of the tree this gate judges.
 *
 * Run: npx tsx scripts/gates/check-worker-secret-names.ts
 *
 * Control-first: both extractors are proven on synthetic input before any
 * verdict, each builder has a per-file floor so a broken regex cannot read as
 * "nothing to check", and the failure control plants a renamed key.
 *
 * ---- gate ----
 * step: Worker secret names
 * needs: node, submodules
 * ---- end gate ----
 */

import { execFileSync } from 'node:child_process';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..', '..');

const SCHEMA = 'private/account/src/types/env.ts';

/**
 * The four builders and the fewest keys each is known to push (measured
 * 2026-09-02: 29/24/15/29, and unchanged by the move from the bash twins to the ports). A count below the floor means the extractor
 * lost the payload, not that the payload shrank — refuse rather than pass.
 *
 * THE FIFTH IS GONE ON PURPOSE. `run.sh`'s local PR-preview builder moved into
 * `.ci/legacy/run-legacy.sh` with the 2026-09-06 router split, and then commit
 * dd5dfba3c (2026-09-22) deleted the whole `pr` verb -- `pr_publish()`, its case
 * arm and its help text, 396 lines -- as one of four verbs with zero callers in
 * the tree. Its 15-key payload was byte-identical in NAMES to
 * set_preview_worker_secrets.py's, which is still checked below, so removing the
 * entry costs this gate no coverage of any name. Verified before removal: the
 * PUSHED_KEY regex reads 15 keys at dd5dfba3c^ and 0 at HEAD, so the floor caught
 * a deliberate deletion rather than a broken extractor.
 */
const BUILDERS: { file: string; floor: number }[] = [
  { file: '.ci/rediacc_ci/deploy/set_account_worker_secrets.py', floor: 20 },
  { file: '.ci/rediacc_ci/deploy/set_www_worker_secrets.py', floor: 15 },
  { file: '.ci/rediacc_ci/deploy/set_preview_worker_secrets.py', floor: 10 },
  { file: '.ci/rediacc_ci/ops/deploy_bench.py', floor: 20 },
];

/** `        KEY: $var,` inside a `jq -n '{ ... }'` object — the payload shape. */
const PUSHED_KEY = /^\s+([A-Z][A-Z0-9_]*):\s*\$/gm;

/** `        "KEY": value,` inside the dict deploy_bench.py's `secrets_payload()` returns. */
const PY_PUSHED_KEY = /^\s+"([A-Z][A-Z0-9_]*)":/gm;

/**
 * The keys of the dict `secrets_payload()` returns, and nothing else in the file.
 *
 * Sliced to that one `return {` ... `    }` block on purpose: the function first
 * builds a `signing` dict of the same six names, and the module carries other
 * quoted UPPERCASE strings, so a whole-file match would count keys twice or
 * read names that are never pushed. No `def secrets_payload` or no return dict
 * reads as zero keys, which the floor turns into a refusal.
 */
export function pythonPayloadKeys(text: string): string[] {
  const def = text.indexOf('\ndef secrets_payload(');
  if (def < 0) return [];
  const start = text.indexOf('\n    return {\n', def);
  if (start < 0) return [];
  const end = text.indexOf('\n    }\n', start);
  if (end < 0) return [];
  return [...text.slice(start, end).matchAll(PY_PUSHED_KEY)].map((m) => m[1]);
}

/** `    ("KEY", "var", ...),` row of a port's module-level `KEYS` tuple. */
const TUPLE_ROW = /^\s+\("([A-Z][A-Z0-9_]*)",/gm;

/**
 * The names in a port's module-level `KEYS = (...)` tuple, and nothing else in the file.
 *
 * Sliced from the `KEYS` assignment to the first column-0 `)` after it, because the
 * ports carry other tuples of quoted UPPERCASE names (`REQUIRED_NONEMPTY`, the
 * suffixed prefixes) that are guards, not pushed keys. No `KEYS` block reads as zero
 * keys, which the floor turns into a refusal.
 */
export function pythonTupleKeys(text: string): string[] {
  const start = text.search(/^KEYS\b[^\n]*=\s*\(\n/m);
  if (start < 0) return [];
  const end = text.indexOf('\n)\n', start);
  if (end < 0) return [];
  return [...text.slice(start, end).matchAll(TUPLE_ROW)].map((m) => m[1]);
}

function keysOf(file: string, text: string): string[] {
  if (!file.endsWith('.py')) return pushedKeys(text);
  return text.includes('\ndef secrets_payload(') ? pythonPayloadKeys(text) : pythonTupleKeys(text);
}

/** `  KEY: z.` or `  KEY: boolFromEnv` — a declared schema key. */
// `z$` matters: prettier wraps a long chain, leaving `MIN_CLI_VERSION: z` with the `.string()` on the NEXT line. Requiring `z.` on one line silently dropped that key, so the gate extracted 84 of 85 and the `size < 40` floor is far too low to notice. A one-key loss here is a latent FALSE POSITIVE: the day a builder pushes that name, the gate calls a correct push line undeclared.
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

/** A Python `wrangler secret bulk` argv: a literal `"wrangler"` head or the pinned `wrangler.ARGV` splat. */
const PY_BULK_ARGV = /(?:"wrangler"|\bwrangler\.ARGV),\s*"secret",\s*"bulk"/;

/**
 * Does this shell source build a `wrangler secret bulk` payload?
 *
 * BUILDERS above is hand-maintained, and the floor only catches the direction
 * where a LISTED file stops being a builder. Nothing caught the other direction:
 * a file that starts building a payload, or an existing builder that moves, is
 * simply never read and the gate still prints a confident green. That is the
 * vacuity this answers -- the list is re-derived from the tree every run and a
 * builder missing from it is a failure, not a silent gap.
 *
 * Both conditions matter. `wrangler secret bulk` alone matches docs and comments
 * that merely mention it; a `KEY: $var` line alone matches any jq object. A file
 * doing both is piping a hand-built payload at a Worker, which is the class.
 */
export function looksLikeBuilder(text: string, file = ''): boolean {
  if (file.endsWith('.py')) {
    // A Python builder spells the command as an argv list, and the file must also carry a payload the extractors can read: a test that only quotes the argv has none.
    // Two spellings of the head: the literal `"wrangler"` and the pinned `*wrangler.ARGV` from rediacc_ci.core.wrangler (`npx --no-install wrangler`), which every port moved to in a9603a30d. Recognising only the literal made the sweep find ZERO builders across the whole tree.
    return PY_BULK_ARGV.test(text) && keysOf(file, text).length > 0;
  }
  return text.includes('wrangler secret bulk') && pushedKeys(text).length > 0;
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
  // The Python extractor reads ONLY the returned dict: the `signing` dict before it and a module-level constant after it are decoys.
  const py =
    'HELP = {\n    "DECOY_TOP": 1,\n}\n\ndef secrets_payload() -> dict[str, str]:\n    signing = {\n        "SIGNING_DECOY": os.environ.get("X") or "",\n    }\n    return {\n        "API_KEY": signing["X"],\n        "ROOT_EMAIL": "",\n    }\n\nOTHER = {\n    "DECOY_AFTER": 2,\n}\n';
  const pyGot = pythonPayloadKeys(py);
  if (pyGot.join(',') !== 'API_KEY,ROOT_EMAIL') {
    console.error(
      `✗ instrument control: the Python payload extractor read ${JSON.stringify(pyGot)} from a fixture whose secrets_payload() returns API_KEY and ROOT_EMAIL (with a signing dict and two module dicts as decoys). Every verdict on deploy_bench.py would be meaningless.`
    );
    process.exit(1);
  }
  // The ports' tuple extractor reads ONLY the KEYS block: a guard tuple after it and a decoy before it are not pushed names.
  const port =
    'HELP = (\n    ("DECOY_TOP", "x"),\n)\n\nKEYS: tuple[tuple[str, str], ...] = (\n    ("API_KEY", "api"),\n    ("ROOT_EMAIL", "root"),\n)\n\nREQUIRED_NONEMPTY = (\n    ("DECOY_AFTER", "y"),\n)\n';
  const portGot = pythonTupleKeys(port);
  if (portGot.join(',') !== 'API_KEY,ROOT_EMAIL') {
    console.error(
      `✗ instrument control: the port tuple extractor read ${JSON.stringify(portGot)} from a fixture whose KEYS tuple holds API_KEY and ROOT_EMAIL (with a tuple before it and one after it as decoys). Every verdict on the set_*_worker_secrets ports would be meaningless.`
    );
    process.exit(1);
  }
  // And the ORACLE, in both directions. It replaced a hand-maintained count, so it has to be proven to (a) agree with the strict extractor on a well-formed schema and (b) DISAGREE on the exact shape that defeated the old regex -- a zod chain wrapped onto a second line. Without (b) the comparison could be trivially equal
  // for a reason unrelated to the defect it is here to catch.
  // NOTE ON THE FIXTURE: a chain wrapped as `KEY:\n z.string()` is NOT the defect shape -- SCHEMA_KEY's `\s*` crosses the newline, so it reads that fine, and the historical `MIN_CLI_VERSION: z` case is covered by the `z$` alternative. The shape that still defeats it is a value that is neither `z.` nor `boolFromEnv`: a new helper added to env.ts. That is what this plants, because a
  // control must plant the defect the comparison can actually catch.
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
  // The discovery predicate, in BOTH directions. A predicate that never says yes makes the sweep below unable to find an unlisted builder; one that never says no reports every doc that merely mentions wrangler as one.
  const builder = 'jq -n --arg a "$A" \'{\n  API_KEY: $a,\n}\' | npx wrangler secret bulk --name x';
  if (!looksLikeBuilder(builder)) {
    console.error(
      '✗ instrument control: the discovery predicate did not recognise a file that pipes a hand-built payload into `wrangler secret bulk`. The sweep below could not find an unlisted builder.'
    );
    process.exit(1);
  }
  const pyBuilder =
    'KEYS = (\n    ("API_KEY", "api"),\n)\n\ndef argv(n):\n    return ["npx", "wrangler", "secret", "bulk", "--name", n]\n';
  if (!looksLikeBuilder(pyBuilder, 'x.py')) {
    console.error(
      '✗ instrument control: the discovery predicate did not recognise a Python port that carries a KEYS tuple and a `wrangler secret bulk` argv. The sweep below could not find an unlisted Python builder.'
    );
    process.exit(1);
  }
  // The pinned head every port uses: `[*wrangler.ARGV, "secret", "bulk", ...]`.
  const pinnedBuilder =
    'KEYS = (\n    ("API_KEY", "api"),\n)\n\ndef argv(n):\n    return [*wrangler.ARGV, "secret", "bulk", "--name", n]\n';
  if (!looksLikeBuilder(pinnedBuilder, 'x.py')) {
    console.error(
      '✗ instrument control: the discovery predicate did not recognise a Python port whose argv starts with the pinned `*wrangler.ARGV`. Every real port spells it that way, so the sweep below would find none of them.'
    );
    process.exit(1);
  }
  if (
    looksLikeBuilder(
      'KEYS = (\n    ("API_KEY", "api"),\n)\n\nX = [*wrangler.ARGV, "secret", "put"]\n',
      'z.py'
    ) ||
    looksLikeBuilder('# see `npx wrangler secret bulk` for how deploys push secrets\n') ||
    looksLikeBuilder("jq -n '{\n  API_KEY: $a,\n}' > payload.json\n") ||
    looksLikeBuilder('assert argv("n") == ["npx", "wrangler", "secret", "bulk"]\n', 'test_x.py') ||
    looksLikeBuilder('KEYS = (\n    ("API_KEY", "api"),\n)\n', 'y.py')
  ) {
    console.error(
      '✗ instrument control: the discovery predicate said yes to a file that only MENTIONS wrangler, to a jq object that is not piped at a Worker, to a Python test that only quotes the argv, or to a Python file with a KEYS tuple and no `wrangler secret bulk` argv. It would report prose as an unlisted builder.'
    );
    process.exit(1);
  }
}

const schemaText = readFileSync(join(ROOT, SCHEMA), 'utf8');
const schema = schemaKeys(schemaText);
const schemaLines = schemaLineKeys(schemaText);
// 80, not 40. The old floor was half the population, which is a guard against the extractor finding NOTHING and nothing else -- it sat happily at 84 of 85 while a prettier-wrapped chain silently dropped a key. A floor guards against finding
// nothing; only the comparison below guards against finding ALMOST everything.
if (schema.size < 80) {
  console.error(
    `✗ ${SCHEMA} yielded only ${schema.size} keys. The schema extractor lost the file; refusing a verdict.`
  );
  process.exit(1);
}
// AND THE EXACT COUNT, DERIVED FROM THE FILE rather than typed into this one. Measured: with the pre-2026-09-02 regex the extractor yielded 84 of 85 -- a prettier-wrapped `MIN_CLI_VERSION: z` -- and sailed past a floor of 80 reporting "84 schema keys" as though that were the answer.
//
// This used to be `EXPECTED_SCHEMA_KEYS = 85`, a ratchet a session was trusted to bump
// in the same commit. That put the protection against "the extractor silently lost a key" inside the reach of the session losing it: editing the number is exactly as easy as editing the schema, and a red that says "expected 85, got 84" invites the wrong one. Comparing against a SECOND reading of the same file removes the trust. A key
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

// ── Discovery: BUILDERS, re-derived from the tree ──────────────────────────
// A hand-maintained list of files to read is a gate that checks whatever it was told about in 2026 and calls the rest green. The floor below catches a LISTED file that stops being a builder; this catches the opposite, which nothing did: a builder that is added, renamed or moved is read by nobody and the gate still prints its confident green. Every tracked shell and Python source is
// classified, and one that builds a payload without being listed is a failure.
let tracked: string[];
try {
  tracked = execFileSync('git', ['ls-files', '-z', '*.sh', '*.py'], {
    cwd: ROOT,
    encoding: 'utf8',
    maxBuffer: 64 * 1024 * 1024,
  })
    .split('\0')
    .filter(Boolean);
} catch (err) {
  console.error(
    `✗ could not list tracked shell and Python sources: \`git ls-files\` failed (${err instanceof Error ? err.message : String(err)}).\n` +
      '  The builder list cannot be re-derived from the tree, so this gate cannot tell a\n' +
      '  complete check from a partial one. Run it inside the repository with git on PATH.'
  );
  process.exit(1);
}
if (tracked.length === 0) {
  console.error(
    '✗ `git ls-files *.sh *.py` returned nothing. The gate is not seeing the tree, so its green would mean nothing.'
  );
  process.exit(1);
}
const listed = new Set(BUILDERS.map((b) => b.file));
const discovered = tracked.filter((f) => {
  try {
    return looksLikeBuilder(readFileSync(join(ROOT, f), 'utf8'), f);
  } catch {
    return false;
  }
});
if (discovered.length === 0) {
  console.error(
    `✗ swept ${tracked.length} tracked shell and Python source(s) and found ZERO that build a \`wrangler secret bulk\` payload.\n` +
      '  Four are known to exist, so the discovery predicate has stopped recognising the\n' +
      '  shape it is looking for. Refusing a verdict rather than reporting a clean sweep.'
  );
  process.exit(1);
}
const unlisted = discovered.filter((f) => !listed.has(f));
if (unlisted.length > 0) {
  console.error(
    `✗ ${unlisted.length} source file(s) build a \`wrangler secret bulk\` payload and are not in BUILDERS:\n` +
      unlisted.map((f) => `    ${f}`).join('\n') +
      '\n\n  Nothing checks their key names against the Worker schema, so a rename in one is\n' +
      '  silent exactly the way this gate exists to prevent. Add each to BUILDERS with a\n' +
      '  floor a little under its current key count. Do not narrow the sweep to get past this.'
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
  const keys = keysOf(file, text);
  if (keys.length < floor) {
    problems.push(
      `    ${file}: extracted only ${keys.length} pushed key(s), floor is ${floor} — the payload moved or the regex broke`
    );
    continue;
  }
  checked += keys.length;
  for (const k of keys) {
    if (!schema.has(k)) {
      const line =
        text
          .split('\n')
          .findIndex((l) => new RegExp(`^\\s+(?:${k}:\\s*\\$|"${k}":|\\("${k}",)`).test(l)) + 1;
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

/** One surveyed Worker as `prune_worker_secrets --json` prints it. */
interface LiveRow {
  region?: string;
  worker: string;
  extras: string[];
}

/**
 * The `worker: name name` lines for every Worker that holds a secret the push does not
 * carry, from the module's JSON. Unreadable input yields null so the caller can say so
 * instead of reading it as "no extras".
 */
export function liveExtraLines(json: string): string[] | null {
  try {
    const doc = JSON.parse(json) as { workers?: LiveRow[] };
    if (!Array.isArray(doc.workers) || doc.workers.length === 0) return null;
    return doc.workers
      .filter((w) => Array.isArray(w.extras) && w.extras.length > 0)
      .map((w) => `${w.worker}: ${w.extras.join(' ')}`);
  } catch {
    return null;
  }
}

// The one spelling of the removal command; `<region>` is filled per region with extras. The verb refuses --archive without an explicit --region (exit 2); `--archive` archives each value from bws, confirms it, then deletes the original, so it needs no `--delete`. The unit test `test_ops_prune_worker_secrets.py` reads this constant and runs it through the verb.
const PRUNE_HINT =
  'PYTHONPATH=.ci python3 -m rediacc_ci.ops.prune_worker_secrets --region <region> --archive';

/** The distinct regions of the Workers that hold extras, in listing order. */
export function liveExtraRegions(json: string): string[] {
  try {
    const doc = JSON.parse(json) as { workers?: LiveRow[] };
    const regions = (doc.workers ?? [])
      .filter((w) => Array.isArray(w.extras) && w.extras.length > 0 && w.region)
      .map((w) => w.region as string);
    return [...new Set(regions)];
  } catch {
    return [];
  }
}

/** The removal command lines: one per region with extras, or a refusal line when no row names a region. */
export function removeLines(json: string): string {
  const regions = liveExtraRegions(json);
  if (regions.length === 0) {
    return '    (no region in the listing: pass --region eu|us|asia to prune_worker_secrets by hand)';
  }
  return regions.map((r) => `    ${PRUNE_HINT.replace('<region>', r)}`).join('\n');
}

// Control: liveExtraRegions and removeLines must tell regions, none and several apart.
{
  const one =
    '{"workers":[{"region":"eu","worker":"a","extras":["X"]},{"region":"us","worker":"b","extras":[]}]}';
  const many =
    '{"workers":[{"region":"eu","worker":"a","extras":["X"]},{"region":"us","worker":"b","extras":["Y"]},{"region":"eu","worker":"c","extras":["Z"]}]}';
  const bare = '{"workers":[{"worker":"a","extras":["X"]}]}';
  if (
    liveExtraRegions(one).join() !== 'eu' ||
    liveExtraRegions(many).join() !== 'eu,us' ||
    liveExtraRegions(bare).length !== 0 ||
    liveExtraRegions('not json').length !== 0 ||
    removeLines(one).includes('<region>') ||
    removeLines(many).split('\n').length !== 2 ||
    !removeLines(many).includes('--region us --archive') ||
    removeLines(bare).includes('python3 -m') ||
    removeLines(bare).includes('<region>')
  ) {
    console.error('✗ instrument control: the region reader or the removal lines are wrong.');
    process.exit(1);
  }
}

// Control: both outcomes and the unreadable case must come out distinct.
{
  const withExtra = liveExtraLines(
    '{"workers":[{"worker":"w","extras":["OLD"]},{"worker":"v","extras":[]}]}'
  );
  const none = liveExtraLines('{"workers":[{"worker":"w","extras":[]}]}');
  if (
    withExtra?.join('|') !== 'w: OLD' ||
    none === null ||
    none.length !== 0 ||
    liveExtraLines('not json') !== null ||
    liveExtraLines('{"workers":[]}') !== null
  ) {
    console.error(
      '✗ instrument control: the live-extras reader does not tell extras, none and unreadable apart.'
    );
    process.exit(1);
  }
}

function reportLiveExtras(): void {
  if (!process.env.CLOUDFLARE_API_TOKEN || !process.env.CLOUDFLARE_ACCOUNT_ID) {
    console.log(
      '  Live extras: skipped (no CLOUDFLARE_API_TOKEN / CLOUDFLARE_ACCOUNT_ID; run under `bws_env exec --profile deploy-workers`).'
    );
    return;
  }
  let out = '';
  try {
    out = execFileSync('python3', ['-m', 'rediacc_ci.ops.prune_worker_secrets', '--json'], {
      cwd: ROOT,
      encoding: 'utf8',
      env: { ...process.env, PYTHONPATH: join(ROOT, '.ci') },
      stdio: ['ignore', 'pipe', 'pipe'],
    });
  } catch (err) {
    // Exit 1 means extras were found and the JSON is still on stdout; exit 2 has none.
    out = (err as { stdout?: string }).stdout ?? '';
  }
  const lines = liveExtraLines(out);
  if (lines === null) {
    console.log('  Live extras: no verdict (the listing failed or was unreadable).');
  } else if (lines.length === 0) {
    console.log('  Live extras: none on any account Worker.');
  } else {
    console.log(
      `  Live extras (advisory, ${lines.length} Worker(s)): secrets the push no longer carries:\n` +
        lines.map((l) => `    ${l}`).join('\n') +
        `\n  Remove with (--archive saves each value from bws as __ARCHIVE_<NAME>, then deletes it):\n${removeLines(out)}`
    );
  }
}

console.log(
  `✓ worker secret names: ${checked} pushed key(s) across ${BUILDERS.length} builder(s) are all\n` +
    `  declared in ${SCHEMA} (${schema.size} schema keys; extractor controls fired both ways).\n` +
    `  Swept ${tracked.length} tracked shell and Python source(s) for payload builders: found ${discovered.length}, all listed.\n` +
    '  Blind spot: this proves the NAMES agree. It cannot see an empty VALUE, which zod\n' +
    "  normalises to undefined and validates — that is the deploy scripts' non-empty\n" +
    '  guards, not this gate.'
);
reportLiveExtras();
