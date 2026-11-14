import raw from '../../../.ci/config/ops-health.json';

/**
 * The generic thresholds of .ci/config/ops-health.json, bundled at build time (D-config). The Python side reads the same file, so no threshold is written twice.
 */
export interface OpsHealthConfig {
  tls: { warn_days: number; red_days: number };
  transitions: { to_red: number; to_green: number; remail_hours: number };
  stale: { last_cron_minutes: number };
  ingest: { max_age_h: Record<string, number> };
  worker: {
    probe_timeout_ms: number;
    mail_log_size: number;
    ct_cache_hours: number;
    ct_max_pages: number;
    digest: { weekday_utc: number; hour_utc: number };
  };
}

export const CONFIG: OpsHealthConfig = raw;

/**
 * The `max_age_h` of one ingest source: an exact key first, then the longest `<prefix>*` key that matches, then `default`.
 */
export function ingestMaxAgeHours(source: string, config: OpsHealthConfig = CONFIG): number {
  const table = config.ingest.max_age_h;
  if (Object.hasOwn(table, source) && !source.endsWith('*')) return table[source];
  let best: { len: number; hours: number } | null = null;
  for (const [key, hours] of Object.entries(table)) {
    if (!key.endsWith('*')) continue;
    const prefix = key.slice(0, -1);
    if (source.startsWith(prefix) && (best === null || prefix.length > best.len)) {
      best = { len: prefix.length, hours };
    }
  }
  if (best) return best.hours;
  return table.default;
}
