/**
 * The option and target types of the `--proxy` client (split out of proxy-client.ts to keep it
 * within the file size budget).
 */

import type { TicketStore } from '../jobs/ticket-store.js';
import type { ProxySessionCache } from './proxy-session-cache.js';

export interface ProxyClientOptions {
  /** Base URL of the executor, e.g. https://proxy.rediacc.com or http://localhost:8080 */
  baseUrl: string;
  /** Resolves the bearer token presented to the executor. */
  getToken: () => Promise<string>;
  /** Contract version this client was built against. */
  contractVersion: string;
  /** Injectable for tests. */
  fetchImpl?: typeof fetch;
  /** Milliseconds the executor has to answer a request. Defaults to REDIACC_PROXY_TIMEOUT_MS, then 60s. */
  timeoutMs?: number;
  /**
   * Unwraps this device's config key (CEK). Called only when the executor is a
   * CONTAINER, which holds no key of its own and can open the config only with
   * one granted per session. A daemon derives its own and is never sent one.
   */
  getCek?: () => Promise<CryptoKey>;
  /** Test seams: the poll pacing and the ticket store (`null` writes no ticket). */
  sleep?: (ms: number) => Promise<void>;
  random?: () => number;
  /** How long consecutive failed polls are retried before the follow is given up with the ticket kept. */
  lostBudgetMs?: number;
  ticketStore?: TicketStore | null;
  /**
   * Where a granted session is kept for the next run. Absent keeps none beyond
   * this process; the `rdc --proxy` entry (proxy-command.ts) passes the file
   * cache beside the config tokens.
   */
  sessionCache?: ProxySessionCache;
}

/** Where to re-attach a dropped stream: the machine the command ran on. */
export interface ReattachTarget {
  machine: string;
}
