/**
 * The `REDIACC_DEBUG=proxy` trace of a proxied command request: which flags the
 * client sent and which the executor received, so a flag dropped between the two
 * shows up as two lines that disagree. Names only: option values and positional
 * values never appear, and no header or token is ever passed in.
 */

import type { CommandRequest } from '@rediacc/shared/cli-contract/wire';
import { debugEnabled } from '../../utils/debug.js';
import { writeStderr } from '../core/request-context.js';

export type ProxyTraceSide = 'sent' | 'received';

type TracedRequest = Pick<
  CommandRequest,
  'pathKey' | 'requestId' | 'background' | 'params' | 'positionals'
>;

/** The one-line form of a request's routing flags. */
export function proxyTraceLine(side: ProxyTraceSide, request: TracedRequest): string {
  const keys = (bag: Record<string, unknown> | undefined) =>
    Object.keys(bag ?? {}).sort((a, b) => a.localeCompare(b));
  return (
    `[proxy] ${side} path=${request.pathKey} background=${request.background === true}` +
    ` requestId=${request.requestId ?? '-'}` +
    ` params=[${keys(request.params).join(',')}] positionals=[${keys(request.positionals).join(',')}]`
  );
}

/** Print the trace line on stderr when `REDIACC_DEBUG` names the `proxy` scope (or is `1`/`*`). */
export function traceProxyRequest(side: ProxyTraceSide, request: TracedRequest): void {
  if (!debugEnabled('proxy')) return;
  writeStderr(`${proxyTraceLine(side, request)}\n`);
}
