/**
 * The unit parsers of `npm run settings` (agent/plans/PLAN-settings-set-verb.md Design 3).
 *
 * One parser per unit, and every one refuses rather than guesses: a value it cannot read
 * exactly, or one that does not land on a whole number where the unit counts things, is
 * refused before `set` plans a single write.
 *
 *   bytes  `5TB`, `500GB`, `5e12`, `5000000000000`, `5_000_000_000_000`: decimal SI
 *          (`KB` = 1000); binary only when spelled so (`KiB` = 1024, `GiB`, `TiB`, `PiB`).
 *   count  `20M`, `2.5M`, `1.5k`, `20000000`, `2e7`: `k`/`K` = 1e3, `M` = 1e6, `G` = 1e9.
 *   ms     a count of milliseconds, with an optional duration word: `60M`, `60000000`,
 *          `90s`, `5min`, `2h` (`ms` is the default and may be written).
 *   usd    `$350`, `350`, `350 USD`, `49.99`: at most two decimals.
 */

export const UNITS = ['bytes', 'count', 'ms', 'usd'] as const;
export type Unit = (typeof UNITS)[number];

/** A value the unit's parser refuses; `set` prints the message and writes nothing. */
export class UnitError extends Error {}

const NUMBER = String.raw`[0-9][0-9_]*(?:\.[0-9_]+)?(?:[eE][+-]?[0-9]+)?|\.[0-9]+(?:[eE][+-]?[0-9]+)?`;

/** The decimal number a literal spells, or null; underscores group digits (`20_000_000`) and never lead or trail one. */
function decimal(text: string): number | null {
  if (!new RegExp(`^(?:${NUMBER})$`).test(text) || /_(?:$|[._eE])|(?:^|[.eE])_/.test(text))
    return null;
  const n = Number(text.replace(/_/g, ''));
  return Number.isFinite(n) ? n : null;
}

const BYTE_FACTORS: Record<string, number> = {
  '': 1,
  b: 1,
  kb: 1e3,
  mb: 1e6,
  gb: 1e9,
  tb: 1e12,
  pb: 1e15,
  kib: 2 ** 10,
  mib: 2 ** 20,
  gib: 2 ** 30,
  tib: 2 ** 40,
  pib: 2 ** 50,
};
const COUNT_FACTORS: Record<string, number> = { '': 1, k: 1e3, K: 1e3, M: 1e6, G: 1e9 };
const MS_FACTORS: Record<string, number> = { '': 1, ms: 1, s: 1e3, min: 6e4, h: 36e5 };

/** Scale a decimal mantissa by a factor without the float drift `2.5 * 1e6` would risk, then insist on a safe whole number. */
function whole(raw: string, mantissa: string, factor: number): number {
  const n = decimal(mantissa);
  if (n === null) throw new UnitError(`${JSON.stringify(raw)} is not a number`);
  const exact = Number((n * factor).toPrecision(15));
  if (!Number.isSafeInteger(exact))
    throw new UnitError(
      `${JSON.stringify(raw)} is ${exact}, not a whole number this unit can hold exactly`
    );
  if (exact < 0) throw new UnitError(`${JSON.stringify(raw)} is negative`);
  return exact;
}

function split(raw: string): { mantissa: string; suffix: string } | null {
  const m = new RegExp(`^\\s*(${NUMBER})\\s*([A-Za-z]*)\\s*$`).exec(raw);
  return m ? { mantissa: m[1], suffix: m[2] } : null;
}

export function parseBytes(raw: string): number {
  const s = split(raw);
  const factor = s ? BYTE_FACTORS[s.suffix.toLowerCase()] : undefined;
  // `kib` lowercased is fine; a lowercase `b` alone would read as bits elsewhere, so only `B` names a byte.
  if (!s || factor === undefined || (s.suffix !== '' && !/[B]$/.test(s.suffix)))
    throw new UnitError(
      `${JSON.stringify(raw)} is not a byte size (write 5TB, 500GB, 4GiB, 5e12 or 5000000000000)`
    );
  return whole(raw, s.mantissa, factor);
}

export function parseCount(raw: string): number {
  const s = split(raw);
  const factor = s ? COUNT_FACTORS[s.suffix] : undefined;
  if (!s || factor === undefined)
    throw new UnitError(`${JSON.stringify(raw)} is not a count (write 20M, 1.5k, 2e7 or 20000000)`);
  return whole(raw, s.mantissa, factor);
}

export function parseMs(raw: string): number {
  const m = new RegExp(`^\\s*(${NUMBER})\\s*([kKMG]?)\\s*(ms|s|min|h)?\\s*$`).exec(raw);
  if (!m)
    throw new UnitError(
      `${JSON.stringify(raw)} is not a duration in ms (write 60M, 60000000, 90s, 5min or 2h)`
    );
  return whole(raw, m[1], (COUNT_FACTORS[m[2]] ?? 1) * (MS_FACTORS[m[3] ?? ''] ?? 1));
}

export function parseUsd(raw: string): number {
  const m = new RegExp(`^\\s*\\$?\\s*(${NUMBER})\\s*(?:USD)?\\s*$`, 'i').exec(raw);
  const n = m ? decimal(m[1]) : null;
  if (n === null || n < 0)
    throw new UnitError(`${JSON.stringify(raw)} is not a USD amount (write $350, 350 or 49.99)`);
  const cents = Number((n * 100).toPrecision(15));
  if (!Number.isSafeInteger(cents))
    throw new UnitError(`${JSON.stringify(raw)} has more than two decimals`);
  return cents / 100;
}

export function parseValue(unit: Unit, raw: string): number {
  switch (unit) {
    case 'bytes':
      return parseBytes(raw);
    case 'count':
      return parseCount(raw);
    case 'ms':
      return parseMs(raw);
    case 'usd':
      return parseUsd(raw);
  }
}

/** The largest suffix that divides the value exactly, so `5000000000000` reads `5 TB` and `4294967296` reads `4 GiB`; otherwise the plain number. */
export function formatValue(unit: Unit, n: number): string {
  if (unit === 'usd') return `$${n}`;
  const table: [string, number][] =
    unit === 'bytes'
      ? [
          ['PB', 1e15],
          ['PiB', 2 ** 50],
          ['TB', 1e12],
          ['TiB', 2 ** 40],
          ['GB', 1e9],
          ['GiB', 2 ** 30],
          ['MB', 1e6],
          ['KB', 1e3],
        ]
      : [
          ['G', 1e9],
          ['M', 1e6],
          ['k', 1e3],
        ];
  const tail = unit === 'ms' ? ' ms' : '';
  // The largest suffix that leaves at most three exact decimals: 2500000 reads 2.5M, not 2500k.
  for (const [name, f] of table) {
    const q = n / f;
    if (q >= 1 && Number.isInteger(Number((q * 1000).toPrecision(15))))
      return unit === 'bytes' ? `${q} ${name}` : `${q}${name}${tail}`;
  }
  return unit === 'bytes' ? `${n} B` : `${n}${tail}`;
}
