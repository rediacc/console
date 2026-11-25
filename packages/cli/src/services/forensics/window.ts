/**
 * The `--since` and `--until` flags of the forensics reads: an ISO 8601 instant or a span back
 * from now (`90m`, `24h`, `7d`). The account read API covers at most 31 days per window.
 */
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';

const MINUTE_MS = 60_000;
const UNIT_MS = { m: MINUTE_MS, h: 60 * MINUTE_MS, d: 24 * 60 * MINUTE_MS } as const;
const SPAN = /^(\d+)([mhd])$/;
const DEFAULT_SINCE = '24h';
export const MAX_WINDOW_MS = 31 * UNIT_MS.d;

export interface ForensicsWindow {
  from: string;
  to: string;
}

function invalid(message: string): CliExitError {
  return new CliExitError(ERROR_CODES.VALIDATION_ERROR, message);
}

function parseInstant(flag: string, value: string, now: Date): string {
  const span = SPAN.exec(value);
  if (span) {
    const unit = span[2] as keyof typeof UNIT_MS;
    return new Date(now.getTime() - Number(span[1]) * UNIT_MS[unit]).toISOString();
  }
  const parsed = Date.parse(value);
  if (Number.isNaN(parsed)) throw invalid(t('forensics.badInstant', { flag, value }));
  return new Date(parsed).toISOString();
}

/** The window of a read; `--until` defaults to now and `--since` to the last 24 hours. */
export function parseWindow(
  options: { since?: string; until?: string },
  now: Date = new Date()
): ForensicsWindow {
  const to =
    options.until === undefined ? now.toISOString() : parseInstant('--until', options.until, now);
  const from = parseInstant('--since', options.since ?? DEFAULT_SINCE, now);
  const span = Date.parse(to) - Date.parse(from);
  if (span < 0) throw invalid(t('forensics.sinceAfterUntil'));
  if (span > MAX_WINDOW_MS) throw invalid(t('forensics.windowTooLong'));
  return { from, to };
}
