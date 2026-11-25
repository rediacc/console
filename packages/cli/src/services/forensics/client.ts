/**
 * The account read API behind the forensics verbs (PLAN-forensics-investigation D3, D7):
 * `/console/forensics` opens a 60 minute investigation (owner or admin of a paid org, after a
 * step-up) and every read carries its id; `/console/incidents` holds the incident records.
 * The calls ride the tunnel with the stored token, which carries `forensics:read` after an
 * elevated browser approval.
 */
import { t } from '../../i18n/index.js';
import { ERROR_CODES } from '../../types/errors.js';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { type AccountFetchError, accountServerFetch } from '../account/account-client.js';
import type { ForensicsWindow } from './window.js';

export type ForensicsFetch = <T>(
  path: string,
  options?: { method?: string; body?: unknown }
) => Promise<T>;

const BASE = '/account/api/v1/console';
const PAGE_LIMIT = 500;
/** A timeline that never ends is a server fault: stop after this many pages. */
const MAX_PAGES = 200;

export type ScopeKind = 'repo' | 'machine';

export interface Scope {
  kind: ScopeKind;
  ref: string;
}

export interface TimelineRow {
  id: string;
  ts: string;
  kind: string;
  source?: string;
  basis?: string;
  data?: Record<string, unknown>;
}

export interface IncidentStep {
  name: string;
  status: string;
  at: string;
  detail?: string;
}

export interface IncidentRecord {
  id: string;
  scopeKind: ScopeKind;
  scopeRef: string;
  windowFrom: string;
  windowTo: string;
  status: 'declared' | 'contained' | 'closed';
  declaredBy: string;
  declaredAt: string;
  awareAt: string;
  notifiedAt: string | null;
  containedAt: string | null;
  closedAt: string | null;
  closedBy: string | null;
  forkRef: string | null;
  steps: IncidentStep[];
  releaseAt: string | null;
}

export interface Aggregates {
  bytesOutPerMinute: { minute: string; bytesOut: number }[];
  topDestinations: Record<string, unknown>[];
}

export interface MachineKey {
  machineId: string;
  subscriptionId: string;
  /** The pinned Ed25519 spool key as 64 hex characters. */
  publicKey: string;
  pinnedAt?: string;
}

export interface RawManifest {
  files: {
    key: string;
    source: 'audit' | 'forensics';
    day: string;
    machineId?: string;
    bytes: number;
  }[];
  bytes: number;
  tooLarge: boolean;
  /** The spool keys the server pinned for the scope's machines. */
  machineKeys: MachineKey[];
}

export interface TimelineRead {
  rows: TimelineRow[];
  unreadable: number;
}

function windowQuery(window: ForensicsWindow): string {
  return `from=${encodeURIComponent(window.from)}&to=${encodeURIComponent(window.to)}`;
}

/** A refused step-up becomes the portal pointer; every other failure passes through. */
function explain(error: unknown): unknown {
  const failure = error as Partial<AccountFetchError> | null;
  if (failure?.status === 403 && failure.details?.reauthRequired === true) {
    return new CliExitError(ERROR_CODES.AUTH_REQUIRED, t('forensics.reauthRequired'));
  }
  if (failure?.status === 403 && failure.code === 'FORENSICS_NOT_ENTITLED') {
    return new CliExitError(ERROR_CODES.PERMISSION_DENIED, t('forensics.notEntitled'));
  }
  return error;
}

export class ForensicsClient {
  constructor(private readonly fetchFn: ForensicsFetch = accountServerFetch as ForensicsFetch) {}

  private async call<T>(path: string, options?: { method?: string; body?: unknown }): Promise<T> {
    try {
      return await this.fetchFn<T>(`${BASE}${path}`, options);
    } catch (error) {
      throw explain(error);
    }
  }

  listIncidents(): Promise<IncidentRecord[]> {
    return this.call<{ incidents: IncidentRecord[] }>('/incidents').then((r) => r.incidents);
  }

  /** One incident by its id or by a prefix of it that no other incident shares. */
  async findIncident(id: string): Promise<IncidentRecord> {
    const all = await this.listIncidents();
    const exact = all.find((i) => i.id === id);
    if (exact) return exact;
    const matches = id.length > 0 ? all.filter((i) => i.id.startsWith(id)) : [];
    if (matches.length === 1 && matches[0]) return matches[0];
    throw new CliExitError(
      matches.length > 1 ? ERROR_CODES.AMBIGUOUS : ERROR_CODES.NOT_FOUND,
      t(matches.length > 1 ? 'forensics.ambiguousIncident' : 'forensics.noSuchIncident', { id })
    );
  }

  async openInvestigation(scope: Scope): Promise<string> {
    const opened = await this.call<{ id: string }>('/forensics/investigations', {
      method: 'POST',
      body: { scopeKind: scope.kind, scopeRef: scope.ref },
    });
    return opened.id;
  }

  /** Every timeline row of the window, page after page, in the server's time order. */
  async timeline(investigationId: string, window: ForensicsWindow): Promise<TimelineRead> {
    const rows: TimelineRow[] = [];
    let unreadable = 0;
    let cursor: string | undefined;
    for (let page = 0; page < MAX_PAGES; page++) {
      const paging = cursor ? `&cursor=${encodeURIComponent(cursor)}` : '';
      const read = await this.call<{
        rows: TimelineRow[];
        nextCursor?: string;
        unreadable: number;
      }>(
        `/forensics/investigations/${encodeURIComponent(investigationId)}/timeline?${windowQuery(window)}&limit=${PAGE_LIMIT}${paging}`
      );
      rows.push(...read.rows);
      unreadable += read.unreadable;
      if (!read.nextCursor) return { rows, unreadable };
      cursor = read.nextCursor;
    }
    throw new CliExitError(ERROR_CODES.SERVER_ERROR, t('forensics.timelineNeverEnds'));
  }

  aggregates(investigationId: string, window: ForensicsWindow): Promise<Aggregates> {
    return this.call<Aggregates>(
      `/forensics/investigations/${encodeURIComponent(investigationId)}/aggregates?${windowQuery(window)}`
    );
  }

  rawManifest(investigationId: string, window: ForensicsWindow): Promise<RawManifest> {
    return this.call<RawManifest>(
      `/forensics/investigations/${encodeURIComponent(investigationId)}/raw?${windowQuery(window)}`
    );
  }

  /** The bytes of one manifest file; the route answers them base64 inside JSON. */
  async rawFile(investigationId: string, window: ForensicsWindow, key: string): Promise<Buffer> {
    const read = await this.call<{ key: string; bytes: number; data: string }>(
      `/forensics/investigations/${encodeURIComponent(investigationId)}/raw/file?${windowQuery(window)}&key=${encodeURIComponent(key)}`
    );
    const bytes = Buffer.from(read.data, 'base64');
    if (bytes.length !== read.bytes) {
      throw new CliExitError(ERROR_CODES.SERVER_ERROR, t('forensics.rawFileTruncated', { key }));
    }
    return bytes;
  }
}
