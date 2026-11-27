/**
 * The principal a container-mode dispatch acts for.
 *
 * Inside `rdc serve --mode container` the bearer is a placeholder the proxy egress swaps for the issued executor token, and the egress refuses the sealed tunnel (it cannot see the inner route). `accountServerFetch` reads this store: inside a dispatch it sends each call of the executor route table plain to `/account/api/v1/proxy/account/<inner>`, naming the caller's own token id in `X-Rediacc-On-Behalf-Of` (PLAN-executor-account-routes Design 7). Outside a container dispatch every call is the tunnel, unchanged. This module holds only the store, so account-client.ts can read it without an import cycle.
 */

import { AsyncLocalStorage } from 'node:async_hooks';

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

/** The principal of the current container-mode dispatch, or undefined outside one. */
export function currentExecutorPrincipal(): ExecutorPrincipal | undefined {
  return storage.getStore();
}
