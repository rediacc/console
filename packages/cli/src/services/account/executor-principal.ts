/**
 * The principal a container-mode dispatch acts for, and the plain executor route a licence call takes there.
 *
 * Inside `rdc serve --mode container` the bearer is a placeholder the proxy egress swaps for the issued executor token, and the egress refuses the sealed tunnel (it cannot see the inner route). A licence call of a served command therefore goes plain to the executor routes under `/account/api/v1/proxy/licenses/`, naming the caller's own token id as `onBehalfOfTokenId`, which the account side checks (private/account/src/routes/proxy-licenses.ts). Outside a container dispatch every call is the tunnel, unchanged.
 */

import { AsyncLocalStorage } from 'node:async_hooks';
import { ValidationError } from '../../utils/errors.js';
import { accountServerFetch } from './account-client.js';
import { getSubscriptionTokenState } from './subscription-auth.js';

/** `tokenId` is absent when the introspected principal carried none. */
export interface ExecutorPrincipal {
  tokenId: string | undefined;
}

const storage = new AsyncLocalStorage<ExecutorPrincipal>();

/** Run `fn` as a container-mode dispatch acting for `principal`. */
export function withExecutorPrincipal<T>(principal: ExecutorPrincipal, fn: () => T): T {
  return storage.run(principal, fn);
}

/** True inside a container-mode dispatch. */
export function inContainerDispatch(): boolean {
  return storage.getStore() !== undefined;
}

interface PlainError extends Error {
  status: number;
  code?: string;
  details?: Record<string, unknown>;
}

function plainError(message: string, status: number, parsed: Record<string, unknown>): PlainError {
  const error = new Error(message) as PlainError;
  error.status = status;
  if (typeof parsed.code === 'string') error.code = parsed.code;
  error.details = parsed;
  return error;
}

/**
 * One licence call. Outside a container dispatch it is `accountServerFetch(tunnelPath)`. Inside one it is a plain POST of
 * `executorPath` with the placeholder bearer and `onBehalfOfTokenId` added to the body; a dispatch with no token id fails
 * by name rather than falling back to the tunnel the egress refuses.
 */
export async function licenceFetch<T>(
  tunnelPath: string,
  executorPath: string,
  body?: Record<string, unknown>
): Promise<T> {
  const principal = storage.getStore();
  if (!principal) {
    return accountServerFetch<T>(tunnelPath, {
      method: 'POST',
      ...(body === undefined ? {} : { body }),
    });
  }
  if (!principal.tokenId) {
    throw new ValidationError(
      'The caller of this command carries no token id, so the executor cannot act on its behalf for the licence call.'
    );
  }
  const state = getSubscriptionTokenState();
  if (state.kind !== 'ready') {
    throw new ValidationError('The executor holds no account token for the licence call.');
  }
  const resp = await fetch(`${state.serverUrl}${executorPath}`, {
    method: 'POST',
    headers: {
      Authorization: `Bearer ${state.token.token}`,
      'Content-Type': 'application/json',
    },
    body: JSON.stringify({ ...body, onBehalfOfTokenId: principal.tokenId }),
  });
  const parsed = (await resp.json().catch(() => ({}))) as Record<string, unknown>;
  if (!resp.ok) {
    const message = typeof parsed.error === 'string' ? parsed.error : `HTTP ${resp.status}`;
    throw plainError(message, resp.status, parsed);
  }
  return parsed as T;
}
