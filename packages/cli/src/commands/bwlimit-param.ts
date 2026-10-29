import { t } from '../i18n/index.js';
import { bandwidthToBytesPerSecond } from '../services/backup/backup-strategy-validate.js';
import { ValidationError } from '../utils/errors.js';

/**
 * A given `--bwlimit` must name a rate renet accepts (bytes/second, `12.5M`, `12Mi`, `100Mbps`); a blank or unparseable one is refused here, before any SSH, and the raw text goes to renet, which applies the same grammar. Mirrors `backup snapshot --bwlimit`.
 */
export function bwlimitParam(raw: string): string {
  const value = raw.trim();
  if (value === '' || bandwidthToBytesPerSecond(value) === undefined) {
    throw new ValidationError(t('commands.backup.snapshot.bwlimitInvalid', { value: raw }));
  }
  return value;
}

/** Refuses a bad `--bwlimit` up front; no value is fine. */
export function assertBwlimit(raw: string | undefined): void {
  if (raw !== undefined) bwlimitParam(raw);
}
