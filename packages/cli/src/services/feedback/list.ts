/**
 * `rdc feedback list` and `rdc feedback show`: read the caller's visible reports
 * from the account server. A token user reads `GET /feedback`; a FREE machine
 * reads `POST /feedback/query` with its licence blob and machine id.
 */
import {
  FEEDBACK_STATUSES,
  type FeedbackListItem,
  type FeedbackListResponse,
} from '@rediacc/shared';
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { accountServerFetch } from '../account/account-client.js';
import { FEEDBACK_PATH, type FeedbackAuth, type FetchFn } from './send.js';

const FEEDBACK_QUERY_PATH = `${FEEDBACK_PATH}/query`;

/** `--status new,planned` as a validated list; an unknown name is a validation error. */
export function parseStatusFilter(raw: string | undefined): string[] {
  const names = (raw ?? '')
    .split(',')
    .map((s) => s.trim())
    .filter(Boolean);
  const known: readonly string[] = FEEDBACK_STATUSES;
  const bad = names.find((n) => !known.includes(n));
  if (bad !== undefined) {
    throw new CliExitError(
      ERROR_CODES.VALIDATION_ERROR,
      t('feedback.badStatus', { status: bad, allowed: FEEDBACK_STATUSES.join(', ') })
    );
  }
  return names;
}

/** The fixed status reads `fixed-in-v<x>` from `fixedIn`; a `v` already on the value is not doubled. */
export function displayStatus(item: Pick<FeedbackListItem, 'status' | 'fixedIn'>): string {
  if (item.status !== 'fixed' || !item.fixedIn) return item.status;
  return `fixed-in-v${item.fixedIn.replace(/^v/, '')}`;
}

/** Token route: GET with the stored credential. FREE route: POST the blob and machine id, no stored credential. */
export async function fetchReports(
  auth: FeedbackAuth,
  statuses: string[],
  fetchFn: FetchFn = accountServerFetch as FetchFn
): Promise<FeedbackListItem[]> {
  const response =
    auth.kind === 'free'
      ? await fetchFn<FeedbackListResponse>(FEEDBACK_QUERY_PATH, {
          method: 'POST',
          body: { ...auth.credential, status: statuses },
          noAuth: true,
        })
      : await fetchFn<FeedbackListResponse>(
          statuses.length > 0
            ? `${FEEDBACK_PATH}?status=${encodeURIComponent(statuses.join(','))}`
            : FEEDBACK_PATH,
          { method: 'GET', body: undefined }
        );
  return response.reports;
}

/** One report by its id or by a prefix of it that no other report shares. */
export function findReport(reports: FeedbackListItem[], id: string): FeedbackListItem {
  const exact = reports.find((r) => r.id === id);
  if (exact) return exact;
  const matches = id.length > 0 ? reports.filter((r) => r.id.startsWith(id)) : [];
  if (matches.length === 1) return matches[0];
  throw new CliExitError(
    ERROR_CODES.NOT_FOUND,
    matches.length > 1 ? t('feedback.ambiguousId', { id }) : t('feedback.noSuchReport', { id })
  );
}

/** A report as the JSON output carries it: the wire item plus the rendered status. */
export function withDisplay(item: FeedbackListItem): FeedbackListItem & { statusText: string } {
  return { ...item, statusText: displayStatus(item) };
}

export function listLines(reports: FeedbackListItem[]): string {
  if (reports.length === 0) return t('feedback.noReports');
  return reports
    .map((r) =>
      [r.id, r.fingerprint, displayStatus(r), r.firstSeenAt, r.lastSeenAt, r.commandPath].join('  ')
    )
    .join('\n');
}

export function showLines(r: FeedbackListItem): string {
  return [
    `${t('feedback.fieldId')}: ${r.id}`,
    `${t('feedback.fieldFingerprint')}: ${r.fingerprint}`,
    `${t('feedback.fieldKind')}: ${r.kind}`,
    `${t('feedback.fieldStatus')}: ${displayStatus(r)}`,
    `${t('feedback.fieldCommand')}: ${r.commandPath}`,
    `${t('feedback.fieldOccurrences')}: ${r.occurrenceCount}`,
    `${t('feedback.fieldFirstSeen')}: ${r.firstSeenAt}`,
    `${t('feedback.fieldLastSeen')}: ${r.lastSeenAt}`,
  ].join('\n');
}
