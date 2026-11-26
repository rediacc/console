/**
 * The account read API behind the forensics verbs (PLAN-forensics-investigation D3, D7):
 * `/console/forensics` opens a 60 minute investigation (owner or admin of a paid org, after a
 * step-up) and every read carries its id; `/console/incidents` holds the incident records.
 * The calls ride the tunnel with the stored token, which carries `forensics:read` after an
 * elevated browser approval.
 *
 * On the executor (D8) the token carries no `forensics:read`: a served dispatch hands the reads
 * the single-use ticket the asking owner's open investigation minted. The first read redeems it
 * once for an agent read token, which every later read of the same dispatch reuses as its
 * investigation id. A served dispatch without a ticket refuses before any call.
 */
import { AsyncLocalStorage } from 'node:async_hooks';
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

type ScopeKind = 'repo' | 'machine';

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

interface IncidentStep {
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

/** POST /console/incidents: the scope, the window and an optional earlier awareness instant. */
export interface DeclareRequest {
  scopeKind: ScopeKind;
  scopeRef: string;
  windowFrom: string;
  windowTo: string;
  awareAt?: string;
}

/** The machine steps of D4, reported by the caller that ran them. */
export type MachineStepName = 'fork' | 'level';

/** POST /console/incidents/:id/steps: a machine step's outcome. */
export interface StepReport {
  name: MachineStepName;
  outcome: 'ok' | 'failed';
  detail?: string;
  /** The fork the step made, sent with a successful `fork` step. */
  forkRef?: string;
}

export interface Aggregates {
  bytesOutPerMinute: { minute: string; bytesOut: number }[];
  topDestinations: Record<string, unknown>[];
}

interface MachineKey {
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

/** The redeemed agent investigation: the signed read token and the scope and window it binds. */
interface AgentInvestigation {
  id: string;
  scopeKind: ScopeKind;
  scopeRef: string;
  from: string;
  to: string;
}

/**
 * One single-use read ticket, shared by every read a served request runs (an AI turn may call
 * several read tools): the first read redeems it, the rest reuse the answer.
 */
export class ForensicsTicket {
  private redeemed: Promise<AgentInvestigation> | undefined;

  constructor(readonly ticket: string) {}

  /** Redeem once; a refused redemption leaves the ticket for the next read to try. */
  redeem(redeemFn: () => Promise<AgentInvestigation>): Promise<AgentInvestigation> {
    this.redeemed ??= redeemFn().catch((error: unknown) => {
      this.redeemed = undefined;
      throw error;
    });
    return this.redeemed;
  }
}

/**
 * The ticket of the served dispatch in flight: undefined on a laptop, null for a served dispatch
 * that carries none.
 */
const ticketStore = new AsyncLocalStorage<ForensicsTicket | null>();

/** Run a served dispatch with its ticket, or with none (null), so a read without one refuses. */
export function withForensicsTicket<T>(ticket: ForensicsTicket | null, fn: () => T): T {
  return ticketStore.run(ticket, fn);
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
  if (failure?.status === 403 && failure.code === 'FORENSICS_TICKET_REFUSED') {
    return new CliExitError(
      ERROR_CODES.PERMISSION_DENIED,
      t('forensics.ticketRefused', { reason: (error as Error).message })
    );
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

  /**
   * The served dispatch's agent investigation, redeemed on first use; undefined on a laptop. A
   * served dispatch without a ticket, or a scope the ticket does not cover, refuses here.
   */
  private async agentInvestigation(scope?: Scope): Promise<AgentInvestigation | undefined> {
    const ticket = ticketStore.getStore();
    if (ticket === undefined) return undefined;
    if (ticket === null) {
      throw new CliExitError(ERROR_CODES.PERMISSION_DENIED, t('forensics.ticketRequired'));
    }
    const agent = await ticket.redeem(() =>
      this.call<AgentInvestigation>('/forensics/agent-investigations', {
        method: 'POST',
        body: {
          ticket: ticket.ticket,
          ...(scope ? { scopeKind: scope.kind, scopeRef: scope.ref } : {}),
        },
      })
    );
    if (scope && (agent.scopeKind !== scope.kind || agent.scopeRef !== scope.ref)) {
      throw new CliExitError(
        ERROR_CODES.PERMISSION_DENIED,
        t('forensics.ticketRefused', { reason: t('forensics.ticketOtherScope') })
      );
    }
    return agent;
  }

  async listIncidents(): Promise<IncidentRecord[]> {
    const agent = await this.agentInvestigation();
    const path = agent
      ? `/forensics/investigations/${encodeURIComponent(agent.id)}/incidents`
      : '/incidents';
    return this.call<{ incidents: IncidentRecord[] }>(path).then((r) => r.incidents);
  }

  /** One incident by its id or by a prefix of it that no other incident shares. */
  async findIncident(id: string): Promise<IncidentRecord> {
    const all = await this.listIncidents();
    const exact = all.find((i) => i.id === id);
    if (exact) return exact;
    const matches = id.length > 0 ? all.filter((i) => i.id.startsWith(id)) : [];
    if (matches.length === 1 && matches[0]) return matches[0];
    if (matches.length > 1) {
      throw new CliExitError(ERROR_CODES.AMBIGUOUS, t('forensics.ambiguousIncident', { id }));
    }
    throw new CliExitError(ERROR_CODES.NOT_FOUND, t('forensics.noSuchIncident', { id }));
  }

  /**
   * Declare an incident (`incident:manage`, after a step-up): the account record, its eviction
   * hold and lock rules, before any machine step runs.
   */
  declareIncident(input: DeclareRequest): Promise<IncidentRecord> {
    return this.call<IncidentRecord>('/incidents', { method: 'POST', body: input });
  }

  /** Report one machine step's outcome; the server marks the incident contained once both are ok. */
  recordStep(id: string, step: StepReport): Promise<IncidentRecord> {
    return this.call<IncidentRecord>(`/incidents/${encodeURIComponent(id)}/steps`, {
      method: 'POST',
      body: step,
    });
  }

  /** Close an incident (after a step-up); the hold and the lock rules end 30 days later. */
  closeIncident(id: string): Promise<IncidentRecord> {
    return this.call<IncidentRecord>(`/incidents/${encodeURIComponent(id)}/close`, {
      method: 'POST',
    });
  }

  async openInvestigation(scope: Scope): Promise<string> {
    const agent = await this.agentInvestigation(scope);
    if (agent) return agent.id;
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
