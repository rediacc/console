/**
 * `subscription notices`: the account's notices store (licence expiry, backup health, renewals,
 * certificates, evaluations, Terms), read through the API-token route every CLI login can use.
 *
 * The server holds GUIDs and dates only. Names are joined here from the local config, and a GUID
 * the config does not know stays its 8-character form.
 */

import type { RepoNameEntry } from '@rediacc/shared/config-schema';
import { t } from '../i18n/index.js';
import { accountServerFetch } from '../services/account/account-client.js';
import { licenceDisplayName, readRepoNames } from '../services/account/license-retire.js';
import { getSubscriptionTokenState } from '../services/account/subscription-auth.js';
import { outputService } from '../services/core/output.js';
import { formatAge } from '../services/jobs/duration.js';
import { getOutputFormat, ValidationError } from '../utils/errors.js';
import {
  assertSubscriptionScopeMatchesConfig,
  unreadyTokenDiagnostic,
} from './subscription-actions.js';

const NOTICES_PATH = '/account/api/v1/notices';
const PAGE_LIMIT = 100;
/** How far back the default listing reaches, counted from each notice's last update. */
const RECENT_WINDOW_MS = 30 * 24 * 60 * 60 * 1000;
/** Names shown in the one-line summary of a licence notice. */
const SUMMARY_NAMES = 3;

export interface SubscriptionNoticesOptions {
  all?: boolean;
  unread?: boolean;
  markRead?: boolean;
}

/** One notice as the server sends it. */
export interface NoticeWire {
  id: string;
  kind: string;
  severity: string;
  createdAt: string;
  updatedAt: string;
  readAt: string | null;
  dismissedAt: string | null;
  orgId: string | null;
  teamId: string | null;
  subscriptionId: string | null;
  payload: Record<string, unknown>;
}

interface NoticePage {
  notices: NoticeWire[];
  nextCursor: string | null;
}

interface LicenceItem {
  guid: string;
  [key: string]: unknown;
}

/** One page of the listing: `--all` asks for dismissed notices too. */
function fetchNoticePage(all: boolean | undefined, cursor: string | null): Promise<NoticePage> {
  const query = new URLSearchParams({ limit: String(PAGE_LIMIT) });
  if (all) query.set('includeDismissed', '1');
  if (cursor) query.set('cursor', cursor);
  return accountServerFetch<NoticePage>(`${NOTICES_PATH}?${query}`);
}

/** Every page of the listing, newest update first. The default stops at the first notice older than the window. */
async function fetchNotices(
  options: SubscriptionNoticesOptions,
  now: number
): Promise<NoticeWire[]> {
  const cutoff = now - RECENT_WINDOW_MS;
  const collected: NoticeWire[] = [];
  let cursor: string | null = null;
  do {
    const page: NoticePage = await fetchNoticePage(options.all, cursor);
    const kept = options.all
      ? page.notices
      : page.notices.filter((n) => Date.parse(n.updatedAt) >= cutoff);
    collected.push(...kept);
    if (kept.length < page.notices.length) break;
    if (page.nextCursor !== null && page.nextCursor === cursor) {
      throw new Error(`The notices listing returned the cursor ${cursor} twice`);
    }
    cursor = page.nextCursor;
  } while (cursor);
  return collected;
}

function payloadItems(notice: NoticeWire): LicenceItem[] {
  const items = notice.payload.items;
  return Array.isArray(items) ? (items as LicenceItem[]) : [];
}

/** `-o json`: the server's payload, with the joined `name` and `machine` on every licence item. */
function withNames(notice: NoticeWire, names: Map<string, RepoNameEntry>): NoticeWire {
  if (notice.kind !== 'repo_licence') return notice;
  const items = payloadItems(notice).map((item) => {
    const entry = names.get(item.guid);
    return { ...item, name: entry?.ref ?? null, machine: entry?.machine ?? null };
  });
  return { ...notice, payload: { ...notice.payload, items } };
}

function text(value: unknown): string {
  return typeof value === 'string' ? value : '-';
}

function day(value: unknown): string {
  return typeof value === 'string' ? value.slice(0, 10) : '-';
}

function licenceSummary(notice: NoticeWire, names: Map<string, RepoNameEntry>): string {
  const counts = (notice.payload.counts ?? {}) as Record<string, unknown>;
  const items = payloadItems(notice);
  const shown = items.slice(0, SUMMARY_NAMES).map((item) => licenceDisplayName(item.guid, names));
  const hidden = items.length - shown.length;
  const list =
    hidden > 0 ? [...shown, t('commands.subscription.notices.more', { count: hidden })] : shown;
  return t('commands.subscription.notices.summary.repoLicence', {
    hardExpired: Number(counts.hardExpired ?? 0),
    refreshRecommended: Number(counts.refreshRecommended ?? 0),
    names: list.join(', '),
  });
}

/** The one line a table row carries for a notice. A kind this CLI does not know prints as its own name. */
function summarize(notice: NoticeWire, names: Map<string, RepoNameEntry>): string {
  const p = notice.payload;
  switch (notice.kind) {
    case 'repo_licence':
      return licenceSummary(notice, names);
    case 'backup_health':
      return t('commands.subscription.notices.summary.backupHealth', {
        count: payloadItems(notice).length,
      });
    case 'licence_renewal':
      return t('commands.subscription.notices.summary.licenceRenewal', {
        planCode: text(p.planCode),
        date: day(p.renewsAt),
      });
    case 'cert_expiry':
      return t('commands.subscription.notices.summary.certExpiry', {
        track: text(p.track),
        number: text(p.certificateNumber),
        date: day(p.expiresAt),
      });
    case 'eval_expiry':
      return t('commands.subscription.notices.summary.evalExpiry', {
        planCode: text(p.planCode),
        date: day(p.expiresAt),
      });
    case 'terms_notice':
      return t('commands.subscription.notices.summary.termsNotice', {
        version: text(p.version),
        date: day(p.effective),
      });
    default:
      return notice.kind;
  }
}

/** The ids that still need a read mark: a notice already read is not posted again. */
async function markNoticesRead(notices: NoticeWire[]): Promise<number> {
  const unread = notices.filter((n) => n.readAt === null);
  for (const notice of unread) {
    await accountServerFetch(`${NOTICES_PATH}/${encodeURIComponent(notice.id)}/read`, {
      method: 'POST',
    });
  }
  return unread.length;
}

export async function executeSubscriptionNotices(
  options: SubscriptionNoticesOptions = {}
): Promise<void> {
  const tokenState = getSubscriptionTokenState();
  if (tokenState.kind !== 'ready') {
    throw new ValidationError(unreadyTokenDiagnostic(tokenState));
  }
  await assertSubscriptionScopeMatchesConfig(tokenState.token);

  const now = Date.now();
  const all = await fetchNotices(options, now);
  const listed = options.unread ? all.filter((n) => n.readAt === null) : all;
  const names = await readRepoNames();
  const format = getOutputFormat();

  if (format !== 'table') {
    outputService.print(
      listed.map((n) => withNames(n, names)),
      format
    );
  } else if (listed.length === 0) {
    outputService.info(t('commands.subscription.notices.empty'));
  } else {
    outputService.print(
      listed.map((n) => ({
        age: formatAge(n.updatedAt, now),
        kind: n.kind,
        severity: n.severity,
        summary: summarize(n, names),
      })),
      format
    );
  }

  if (!options.markRead) return;
  const marked = await markNoticesRead(listed);
  if (format === 'table') {
    outputService.info(t('commands.subscription.notices.markedRead', { count: marked }));
  }
}
