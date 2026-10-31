/** Node clamps a timer above 2^31-1 ms (about 24.8 days) to 1 ms, so a larger wait would fire at once. */
const MAX_TIMER_MS = 2 ** 31 - 1;
const MS_PER_SECOND = 1000;

/** Parse `--timeout`: "90", "90s", "5m", "2h". A bare number is seconds. Returns milliseconds, or undefined when malformed or beyond the timer limit. */
export function parseWaitTimeoutMs(raw: string): number | undefined {
  const match = /^(\d+)\s*([smh]?)$/.exec(raw.trim());
  if (!match) return undefined;
  const unit =
    { '': MS_PER_SECOND, s: MS_PER_SECOND, m: 60_000, h: 3_600_000 }[match[2]] ?? MS_PER_SECOND;
  const ms = Number.parseInt(match[1], 10) * unit;
  return ms > MAX_TIMER_MS ? undefined : ms;
}

/** "45s", "12m", "3h", "2d": the coarsest unit that is at least one. */
export function formatAge(fromIso: string | undefined, now: number = Date.now()): string {
  const from = fromIso ? Date.parse(fromIso) : Number.NaN;
  if (Number.isNaN(from)) return '-';
  const seconds = Math.max(0, Math.round((now - from) / 1000));
  if (seconds < 60) return `${seconds}s`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)}m`;
  if (seconds < 86_400) return `${Math.floor(seconds / 3600)}h`;
  return `${Math.floor(seconds / 86_400)}d`;
}
