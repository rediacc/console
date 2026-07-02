/**
 * StateProvider factory - returns the local provider backed by the config file.
 */

import { LocalStateProvider } from './local-state-provider.js';
import type { IStateProvider } from './types.js';

let provider: IStateProvider | undefined;

/**
 * Get the state provider. Async signature retained for call-site stability.
 */
export function getStateProvider(): Promise<IStateProvider> {
  provider ??= new LocalStateProvider();
  return Promise.resolve(provider);
}
