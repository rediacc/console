/**
 * Finding keys: the unit a carried red is carried by (agent/plans/PLAN-carried-red-finding-keys.md).
 *
 * A gate that takes part prints one `::finding::<key>` line per finding, on either stream. The key is built from stable identity (a plan path and a box signature, a rule and a hash of its message with digits and shas masked), never from counts, line numbers or commit shas, so the same finding keeps the same key from run to run. The receipt records the keys per failed gate, and the push guard compares them with the ones `.ci/config/carried-reds.json` names, so a carried gate can no longer hide a NEW finding.
 *
 * WHY NOT THE `✗` LINE. Measured when this was designed: 108 of 130 `scripts/gates/*.ts` print `✗`, and in the sample the `✗` line is usually a summary header with a count in it (`✗ ${issues.length} issue(s)`) with the details indented under it. Hashing it gives one key for many findings, and a key that changes whenever the count does.
 *
 * SILENCE IS NOT ZERO. A gate that emits no valid line reports `null`, never `[]`: "reported nothing parsable" and "reported no findings" are different observations, and a guard that read the first as the second would carry every new finding of a gate that does not speak the protocol.
 *
 * `_` IS IN THE KEY ALPHABET, beyond the plan's `[A-Za-z0-9._:/@#-]`: a closed plan lives under `agent/plans/_done/`, and its P-A2 key names that path. `.ci/rediacc_ci/log.py` FINDING_KEY_RE holds the same alphabet, and the guard in `.claude/rediacc_hooks/guards/block_unverified_push.py` compares keys as opaque strings.
 */

/** One key: the alphabet and the length bound. Matched after ANSI is stripped, so a coloured line still parses. */
const KEY_RE = /^[A-Za-z0-9._:/@#-]{1,200}$/;
const PREFIX = '::finding::';
/** A whole `::finding::<key>` line; the key is judged against KEY_RE after. */
const FINDING_LINE_RE = /^::finding::(.*)$/;
/** Keys per gate. 512 x 200 characters is about 100 KB a gate; past it the value is `null` and the runner says so. */
const FINDINGS_CAP = 512;
/** The ESC byte built with fromCharCode, the idiom exec.ts PASS_LINE uses, so no control character sits in a regex literal. */
const ANSI_RE = new RegExp(`${String.fromCharCode(27)}\\[[0-9;?]*[A-Za-z]`, 'g');

const byCodeUnit = (a: string, b: string): number => (a < b ? -1 : a > b ? 1 : 0);

/** The line a gate prints for `key`. Throws on a key outside the alphabet: a malformed key is a defect in the gate, and a quietly dropped one would read as "no findings". */
function findingLine(key: string): string {
  if (!KEY_RE.test(key)) throw new Error(`finding key ${JSON.stringify(key)} is not ${KEY_RE}`);
  return `${PREFIX}${key}`;
}

/** Print one finding line. `write` defaults to stderr, where the house logger writes too; the runner reads both streams. */
export function emitFinding(
  key: string,
  write: (text: string) => void = (text) => {
    process.stderr.write(text);
  }
): void {
  write(`${findingLine(key)}\n`);
}

type ParsedFindings = { keys: string[] } | { keys: null; overCap: boolean };

/**
 * The keys in a gate's output, deduped and sorted by plain code-unit order (not `localeCompare`, whose order depends on the ICU build), or `null` when no valid line was found or there were more than FINDINGS_CAP.
 *
 * A line counts only when, after ANSI is stripped and surrounding blanks are trimmed, it starts with the prefix and the rest matches the key alphabet whole. A key with a space in it is not a key.
 */
function parseFindings(output: string): ParsedFindings {
  const keys = new Set<string>();
  for (const raw of output.replace(ANSI_RE, '').split(/\r?\n/)) {
    const line = raw.trim();
    const m = FINDING_LINE_RE.exec(line);
    if (m !== null && KEY_RE.test(m[1] as string)) keys.add(m[1] as string);
  }
  if (keys.size === 0) return { keys: null, overCap: false };
  if (keys.size > FINDINGS_CAP) return { keys: null, overCap: true };
  return { keys: [...keys].sort(byCodeUnit) };
}

/**
 * The receipt's `findings` block: one entry per FAILED gate, inserted in sorted gate-id order so `JSON.stringify` of it is byte-stable for identical gate output. `warn` hears about every gate that went over the cap.
 */
export function receiptFindings(
  results: ReadonlyArray<{ id: string; status: string; stdout: string; stderr: string }>,
  warn: (text: string) => void
): Record<string, string[] | null> {
  const out: Record<string, string[] | null> = {};
  const failed = results.filter((r) => r.status === 'fail');
  failed.sort((a, b) => byCodeUnit(a.id, b.id));
  for (const r of failed) {
    const parsed = parseFindings(`${r.stdout}\n${r.stderr}`);
    if (parsed.keys === null && parsed.overCap) {
      warn(
        `WARNING: ${r.id} emitted more than ${FINDINGS_CAP} finding keys, so the receipt records it as null\n` +
          '  (no parsable findings) and a keyed carry of it cannot be verified.\n'
      );
    }
    out[r.id] = parsed.keys;
  }
  return out;
}

/**
 * The controls for this module, driven by the runner's `--selftest`: each planted defect beside its clean control. Returns the failures and the number of assertions, so the selftest's count is derived rather than restated.
 */
export function findingsSelftest(): { failures: string[]; assertions: number } {
  const failures: string[] = [];
  let assertions = 0;
  const check = (cond: boolean, message: string): void => {
    assertions++;
    if (!cond) failures.push(`findings: ${message}`);
  };
  const same = (a: string[] | null, b: string[] | null): boolean =>
    JSON.stringify(a) === JSON.stringify(b);
  const esc = String.fromCharCode(27);

  // A summary header with a count and no protocol line is NOT a report of zero findings.
  check(
    parseFindings('✗ 3 issue(s)\n  a.ts:1 bad\n').keys === null,
    "a gate printing '✗ 3 issue(s)' with no ::finding:: line must give null, not []"
  );
  // CONTROL: two valid lines, written by the emitter itself, give exactly those keys.
  let captured = '';
  const capture = (text: string): void => {
    captured += text;
  };
  emitFinding('b', capture);
  emitFinding('a', capture);
  check(same(parseFindings(captured).keys, ['a', 'b']), 'CONTROL: two valid lines must give [a,b]');
  check(
    same(parseFindings('::finding::z\n::finding::a\n::finding::z\n').keys, ['a', 'z']),
    'duplicate and unsorted keys must come out deduped and sorted'
  );
  check(
    same(parseFindings('::finding::b\n::finding::B\n').keys, ['B', 'b']),
    'the sort is code-unit order (uppercase first), not localeCompare'
  );
  check(
    same(parseFindings(`${esc}[0;31m::finding::P-A2:no-row:a/_done/x.md#ab12${esc}[0m\n`).keys, [
      'P-A2:no-row:a/_done/x.md#ab12',
    ]),
    'an ANSI-wrapped key must parse'
  );
  check(
    parseFindings('::finding::two words\n').keys === null,
    'a key with a space must be rejected'
  );
  let threw = false;
  try {
    emitFinding('two words', () => {});
  } catch {
    threw = true;
  }
  check(threw, 'emitFinding must refuse a key outside the alphabet rather than print it');
  const lines = Array.from({ length: FINDINGS_CAP + 1 }, (_, i) => `::finding::k${i}`);
  const over = parseFindings(lines.join('\n'));
  check(
    over.keys === null && 'overCap' in over && over.overCap,
    `${FINDINGS_CAP + 1} keys must give null (over the cap)`
  );
  check(
    parseFindings(lines.slice(0, FINDINGS_CAP).join('\n')).keys?.length === FINDINGS_CAP,
    `CONTROL: exactly ${FINDINGS_CAP} keys must be kept`
  );

  // The receipt block: failed gates only, sorted by id, byte-stable.
  const warned: string[] = [];
  const block = receiptFindings(
    [
      { id: 'z:gate', status: 'fail', stdout: '::finding::k2\n', stderr: '::finding::k1\n' },
      { id: 'a:gate', status: 'fail', stdout: '✗ 3 issue(s)', stderr: '' },
      { id: 'm:gate', status: 'ok', stdout: '::finding::k9\n', stderr: '' },
      { id: 'b:gate', status: 'fail', stdout: lines.join('\n'), stderr: '' },
    ],
    (text) => warned.push(text)
  );
  check(
    JSON.stringify(block) === '{"a:gate":null,"b:gate":null,"z:gate":["k1","k2"]}',
    `the receipt block must hold failed gates only, in id order, got ${JSON.stringify(block)}`
  );
  check(
    warned.length === 1 && warned[0].includes('b:gate'),
    'a gate over the cap must be warned about, loudly and by name'
  );
  return { failures, assertions };
}
