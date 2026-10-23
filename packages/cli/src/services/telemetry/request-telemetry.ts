/**
 * The telemetry identity of one executor request.
 *
 * The telemetry service is a process singleton, which is right for the SDK (one
 * exporter, one resource) and wrong for everything that belongs to a single
 * command: who asked, and which command span is open. Inside the container
 * executor many callers' commands run at once, so those two live here, in an
 * AsyncLocalStorage bound to the dispatch, and never on the singleton.
 */

import { AsyncLocalStorage } from 'node:async_hooks';

/** The caller as the account server introspected it, never as the client asserted it. */
export interface TelemetryCaller {
  userId: string;
  orgId: string;
  userEmail: string;
}

/** The command span currently open for this request. */
export interface OpenCommandSpan {
  commandName: string;
  spanKey: string;
}

export interface RequestTelemetryScope {
  caller?: TelemetryCaller;
  open?: OpenCommandSpan;
}

const storage = new AsyncLocalStorage<RequestTelemetryScope>();

export function currentRequestTelemetry(): RequestTelemetryScope | undefined {
  return storage.getStore();
}

export function runWithRequestTelemetry<T>(caller: TelemetryCaller | undefined, fn: () => T): T {
  return storage.run(caller ? { caller } : {}, fn);
}
