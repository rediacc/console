/**
 * StateProvider factory - returns the appropriate provider based on context mode.
 * Uses lazy initialization and caching per context name.
 */

import { DEFAULTS } from "@rediacc/shared/config";
import { contextService } from "../services/context.js";
import type { IStateProvider } from "./types.js";

const providerCache = new Map<string, IStateProvider>();

/**
 * Get the state provider for the current context.
 * Cached per context name — subsequent calls return the same instance.
 */
export async function getStateProvider(): Promise<IStateProvider> {
  const contextName = contextService.getCurrentName();
  const cached = providerCache.get(contextName);
  if (cached) return cached;

  const context = await contextService.getCurrent();
  const mode = context?.mode ?? DEFAULTS.CONTEXT.MODE;

  let provider: IStateProvider;

  switch (mode) {
    case "s3":
    case "local": {
      const { LocalStateProvider } = await import("./local-state-provider.js");
      provider = new LocalStateProvider(mode);
      break;
    }
    case "cloud":
    default: {
      const { CloudStateProvider } = await import("./cloud-state-provider.js");
      provider = new CloudStateProvider();
      break;
    }
  }

  providerCache.set(contextName, provider);
  return provider;
}
