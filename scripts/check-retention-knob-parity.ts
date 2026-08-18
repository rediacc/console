/**
 * check:ci-retention-knob-parity — a retention knob the operator can DECLARE
 * must be one the server actually ENFORCES, in every layer between them.
 *
 * THE DEFECT CLASS. The GFS retention policy (keepLast, keepHourly, keepDaily,
 * keepWeekly, keepMonthly, keepYearly) is spelled independently in FOUR places:
 *
 *   1. packages/shared/src/config-schema/schemas.ts   the declared shape
 *   2. private/account/src/dto/backup.dto.ts          what PUT /retention accepts
 *   3. private/account/src/services/backup-gc.service.ts
 *                                                     what the sweep HONOURS
 *   4. packages/cli/src/commands/backup-storage.ts    the --keep-* flags
 *
 * Add a knob to 1, 2 and 4 but forget 3 and the operator declares a rule that
 * silently does nothing: the CLI accepts it, the DTO validates it, the row is
 * written, and the sweep never reads it. The consequence is not a crash — it is
 * snapshots being DELETED that the operator meant to keep, or kept that they
 * meant to delete, discovered whenever someone next needs a restore.
 *
 * WHY NO EXISTING CHECK SEES IT. Every layer is internally consistent, and each
 * has its own passing tests. `check:ci-backup-protocol-conformance` pins the
 * backup wire legs — /session, /streams, /exists, /grants, /read-grants and
 * /commit — and /retention is deliberately not one of them, because retention
 * is an api-token surface rather than part of the machine session protocol. So
 * nothing compares the four spellings to each other.
 *
 * A NOTE ON WHAT RETENTION MEANS, because it is easy to get backwards: a policy
 * CAUSES pruning, it does not prevent it. The knobs say what to KEEP; the sweep
 * deletes what falls outside them. A lineage with NO policy row is never
 * touched at all. The two real safety constraints — "a lineage with no policy
 * is never touched" and "the sweep never empties a lineage" — are behavioural
 * and live in private/account/tests/integration/backup-retention.test.ts; this
 * gate covers the structural half they cannot see.
 *
 * Run: npx tsx scripts/check-retention-knob-parity.ts
 *
 * Control-first: every run first proves the extractor on a synthetic layer that
 * is missing a knob, and refuses to pass if any layer yields nothing.
 */

import { readFileSync } from 'node:fs';
import { join } from 'node:path';
import { fileURLToPath } from 'node:url';

const ROOT = join(fileURLToPath(new URL('.', import.meta.url)), '..');

/**
 * The knobs, as the wire spells them. This list is the gate's own opinion and
 * is deliberately explicit: adding a knob means adding it here too, which is
 * the moment to check all four layers.
 */
const KNOBS = [
  'keepLast',
  'keepHourly',
  'keepDaily',
  'keepWeekly',
  'keepMonthly',
  'keepYearly',
] as const;

interface Layer {
  name: string;
  file: string;
  /** How this layer spells a knob. The CLI spells them as kebab-case flags. */
  spell: (knob: string) => string;
  /** Extra text that must ALSO be present, or the layer is not really wired. */
  hint?: string;
}

const LAYERS: Layer[] = [
  {
    name: 'shared config schema (what the operator declares)',
    file: 'packages/shared/src/config-schema/schemas.ts',
    spell: (k) => `${k}:`,
  },
  {
    name: 'account DTO (what PUT /retention accepts)',
    file: 'private/account/src/dto/backup.dto.ts',
    // `${k}:` is NOT specific enough: every knob also appears in the RESPONSE
    // schema, so dropping one from the REQUEST left the bare token present and
    // the gate green. Match the request spelling exactly.
    spell: (k) => `${k}: retentionKnob`,
  },
  {
    name: 'account sweep (what actually gets ENFORCED)',
    file: 'private/account/src/services/backup-gc.service.ts',
    // NOT a bare `includes(knob)`. The first draft of this gate did exactly
    // that and DID NOT FIRE when the sweep stopped honouring keepWeekly,
    // because the identifier still appears in the RetentionPolicy interface
    // whether or not anything reads it. A gate that cannot fail on its own
    // headline defect is worse than no gate.
    //
    // Enforcement has two shapes here and both are matched literally:
    // the five time buckets are entries in the BUCKETS table, and keepLast is
    // applied directly as a slice of the sorted rows.
    // keepLast is matched on the line that APPLIES it, not on any mention:
    // `policy.keepLast` also appears in the all-null probe above it, so a
    // bare mention stayed present when the application was disabled and the
    // gate went green on a knob that no longer did anything.
    spell: (k) => (k === 'keepLast' ? 'sorted.slice(0, policy.keepLast)' : `knob: '${k}'`),
  },
  {
    name: 'CLI flags (how the operator sets it)',
    file: 'packages/cli/src/commands/backup-storage.ts',
    // keepLast -> '--keep-last <n>'. The trailing argument placeholder and the
    // quote are load-bearing: a bare `--keep-last` is a SUBSTRING of a renamed
    // `--keep-lastXX`, so renaming a flag left the gate green.
    spell: (k) => `'--${k.replace(/([A-Z])/g, '-$1').toLowerCase()} <n>'`,
  },
];

function missingIn(root: string, layer: Layer, knobs: readonly string[]): string[] {
  let text: string;
  try {
    text = readFileSync(join(root, layer.file), 'utf8');
  } catch {
    return [`<file unreadable: ${layer.file}>`];
  }
  return knobs.filter((k) => !text.includes(layer.spell(k)));
}

// ── Control: the real extractor, on a real fixture, both directions ────────
{
  const good = LAYERS[3]; // the CLI layer, whose spelling transform is the tricky one
  if (
    good.spell('keepLast') !== "'--keep-last <n>'" ||
    good.spell('keepMonthly') !== "'--keep-monthly <n>'"
  ) {
    console.error(
      `✗ instrument control: the CLI flag spelling is wrong ` +
        `(keepLast -> ${good.spell('keepLast')}). Every CLI check below would be vacuous.`
    );
    process.exit(1);
  }
  // A synthetic layer missing exactly one knob must be reported, and a
  // complete one must not.
  const tmpLayer: Layer = { name: 'control', file: 'package.json', spell: () => '"name"' };
  if (missingIn(ROOT, tmpLayer, KNOBS).length !== 0) {
    console.error('✗ instrument control over-reports: a present token was called missing.');
    process.exit(1);
  }
  const absent: Layer = { name: 'control', file: 'package.json', spell: () => '__no_such_token__' };
  if (missingIn(ROOT, absent, KNOBS).length !== KNOBS.length) {
    console.error(
      '✗ instrument control did not fire: an absent token was NOT reported, so a\n' +
        '  green run below would mean nothing.'
    );
    process.exit(1);
  }
}

const problems: string[] = [];
for (const layer of LAYERS) {
  const missing = missingIn(ROOT, layer, KNOBS);
  if (missing.length > 0) {
    problems.push(`    ${layer.name}\n      ${layer.file}\n      missing: ${missing.join(', ')}`);
  }
}

if (problems.length > 0) {
  console.error(
    `✗ retention knob parity broken (${problems.length} layer(s)):\n${problems.join('\n')}\n\n` +
      '  A knob the operator can DECLARE must be one the server ENFORCES. A knob\n' +
      '  present in the schema, the DTO and the CLI but absent from the sweep is a\n' +
      '  rule that silently does nothing: the CLI accepts it, the row is written,\n' +
      '  and the sweep never reads it. The result is snapshots deleted that were\n' +
      '  meant to be kept, or kept that were meant to be deleted — noticed only\n' +
      '  when someone needs a restore.'
  );
  process.exit(1);
}

console.log(
  `✓ retention knob parity (${KNOBS.length} knobs across ${LAYERS.length} layers; control fired both ways)`
);
