/**
 * Durations of the backup surface: `15m`, `1h`, `1h30m`, `90s`, `2d`.
 *
 * One grammar for the declared protection target (`--rpo`), `indexEvery`, `hookTimeout` and the
 * keep-within window, so the config schema, the verbs and the unit generator never disagree on
 * what a string means. A bare number has no unit and is refused: `--rpo 15` could be minutes or
 * seconds, and a guess is a 60x error.
 */

const UNIT_SECONDS = { s: 1, m: 60, h: 3600, d: 86_400 } as const;
type Unit = keyof typeof UNIT_SECONDS;

/** The shortest declared target: the operator's gentleness order (decision O6). */
export const RPO_MIN_SECONDS = 300;
/** The longest declared target: a daily cadence is what a cron already expresses. */
export const RPO_MAX_SECONDS = 86_400;

/** Seconds for a duration string made of integer-unit parts, or undefined when it does not parse or is zero. */
export function parseDurationSeconds(raw: string): number | undefined {
  const text = raw.trim().toLowerCase();
  if (!/^(\d+[smhd])+$/.test(text)) return undefined;
  let total = 0;
  for (const part of text.matchAll(/(\d+)([smhd])/g)) {
    total += Number(part[1]) * UNIT_SECONDS[part[2] as Unit];
  }
  return Number.isSafeInteger(total) && total > 0 ? total : undefined;
}

/** The compact form Go's time.ParseDuration reads and a person recognises: 300 -> `5m`, 5400 -> `1h30m`, 45 -> `45s`. Days become hours, since Go has no `d`. */
export function formatDuration(seconds: number): string {
  const whole = Math.max(0, Math.round(seconds));
  if (whole === 0) return '0s';
  const h = Math.floor(whole / 3600);
  const m = Math.floor((whole % 3600) / 60);
  const s = whole % 60;
  return `${h > 0 ? `${h}h` : ''}${m > 0 ? `${m}m` : ''}${s > 0 ? `${s}s` : ''}`;
}

/**
 * Why a target length cannot be rendered as a timer, or undefined when it can.
 *
 * `OnCalendar` fires on clock boundaries, so only a length that divides its parent unit repeats evenly: under an hour a whole number of minutes that divides 60, from an hour a whole number of hours that divides 24. `7m` would fire at :00, :07 ... :56 and then again at :00, a 4-minute gap that the arithmetic of the target does not expect.
 */
export function rpoProblem(seconds: number): string | undefined {
  if (seconds < RPO_MIN_SECONDS) {
    return `a target below ${RPO_MIN_SECONDS / 60} minutes is refused`;
  }
  if (seconds > RPO_MAX_SECONDS) return 'a target above 24h is a cron schedule, use --cron';
  if (seconds < 3600) {
    return seconds % 60 === 0 && 60 % (seconds / 60) === 0
      ? undefined
      : 'under an hour the length must divide 60 minutes (5m, 6m, 10m, 12m, 15m, 20m, 30m)';
  }
  return seconds % 3600 === 0 && 24 % (seconds / 3600) === 0
    ? undefined
    : 'from an hour the length must be whole hours dividing 24 (1h, 2h, 3h, 4h, 6h, 8h, 12h, 24h)';
}

/** The 5-field cron whose firings are exactly a valid target's ticks, so cadence readers (coverage, expected interval) see the same schedule the timer runs. */
export function rpoCron(seconds: number): string {
  if (seconds < 3600) return `*/${seconds / 60} * * * *`;
  const hours = seconds / 3600;
  return hours === 24 ? '0 0 * * *' : `0 */${hours} * * *`;
}

const SIZE_UNITS: Record<string, number> = { k: 1024, m: 1024 ** 2, g: 1024 ** 3 };

/** Bytes for a cell size such as `1M` or `4M`, binary like renet's own size parser, or undefined when it does not read as one. */
export function parseCellSizeBytes(raw: string): number | undefined {
  const match = /^(\d+(?:\.\d+)?)([KMGkmg])$/.exec(raw.trim());
  if (!match) return undefined;
  const bytes = Math.round(Number(match[1]) * SIZE_UNITS[match[2].toLowerCase()]);
  return Number.isSafeInteger(bytes) && bytes > 0 ? bytes : undefined;
}
