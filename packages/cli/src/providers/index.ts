/**
 * StateProvider factory - auto-detects adapter from config contents.
 * Uses lazy initialization and caching per config name.
 */

import { configService } from '../services/config-resources.js';
import { hasCloudCredentials } from '../types/index.js';
import type { IStateProvider } from './types.js';

const providerCache = new Map<string, IStateProvider>();

/**
 * Get the state provider for the current config.
 * Cached per config name — subsequent calls return the same instance.
 */
export async function getStateProvider(): Promise<IStateProvider> {
  const configName = configService.getCurrentName();
  const cached = providerCache.get(configName);
  if (cached) return cached;

  const config = await configService.getCurrent();

  let provider: IStateProvider;

  if (hasCloudCredentials(config)) {
    const { CloudStateProvider } = await import('./cloud-state-provider.js');
    provider = new CloudStateProvider();
  } else {
    const { LocalStateProvider } = await import('./local-state-provider.js');
    provider = new LocalStateProvider();
  }

  providerCache.set(configName, provider);
  return provider;
}
