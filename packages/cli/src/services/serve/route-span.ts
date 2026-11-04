/**
 * The command span of a job route (PLAN-detached-jobs Design 13).
 *
 * `/v1/command` gets its span from the CLI it runs; the poll and cancel routes run no CLI, so each opens its own
 * here. The span carries the caller like a dispatched command's does and `rediacc.proxy.route`
 * (`job-poll`, `job-cancel`), so the request-duration drop of polling shows per route in the existing traces.
 * With telemetry off every call below is a no-op.
 */

import {
  currentRequestTelemetry,
  runWithRequestTelemetry,
} from '../telemetry/request-telemetry.js';
import { telemetryService } from '../telemetry/telemetry.js';

export type JobRoute = 'job-poll' | 'job-cancel';

let spanSequence = 0;

interface RouteCaller {
  userId: string;
  orgId: string;
  userEmail: string;
}

/** End the route's span with the response's status, or with the error that escaped the handler. */
function endRouteSpan(
  route: JobRoute,
  spanKey: string,
  started: number,
  failure: string | undefined
): void {
  telemetryService.endCommand(
    route,
    {
      success: failure === undefined,
      exitCode: failure === undefined ? 0 : 1,
      ...(failure === undefined ? {} : { error: failure }),
      duration: Date.now() - started,
    },
    spanKey
  );
}

/** Run one route handler inside its own request scope and span; the span ends with the response's status. */
export function withRouteSpan(
  route: JobRoute,
  caller: RouteCaller,
  handler: () => Promise<Response>
): Promise<Response> {
  return runWithRequestTelemetry(
    caller,
    () => {
      const spanKey = `${route}#${++spanSequence}`;
      const started = Date.now();
      telemetryService.startCommand(route, { spanKey });
      const scope = currentRequestTelemetry();
      if (scope) scope.open = { commandName: route, spanKey };
      return handler().then(
        (response) => {
          const failed = response.status >= 400;
          endRouteSpan(route, spanKey, started, failed ? `HTTP ${response.status}` : undefined);
          return response;
        },
        (error: unknown) => {
          endRouteSpan(
            route,
            spanKey,
            started,
            error instanceof Error ? error.message : 'The route failed.'
          );
          throw error;
        }
      );
    },
    route
  );
}
