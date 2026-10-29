/** Parse `--timeout`: "90", "90s", "5m", "2h". A bare number is seconds. Returns milliseconds. */
export function parseWaitTimeoutMs(raw: string): number | undefined {
  const match = /^(\d+)\s*([smh]?)$/.exec(raw.trim());
  if (!match) return undefined;
  const unit = { '': 1000, s: 1000, m: 60_000, h: 3_600_000 }[match[2]] ?? 1000;
  return Number.parseInt(match[1], 10) * unit;
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
