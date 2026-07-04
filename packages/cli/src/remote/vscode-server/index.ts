import { codeServerProvider } from './code-server.js';
import { openvscodeProvider } from './openvscode.js';
import type { VSCodeServerProvider } from './types.js';

export * from './types.js';

const PROVIDERS = new Map<string, VSCodeServerProvider>([
  [openvscodeProvider.id, openvscodeProvider],
  [codeServerProvider.id, codeServerProvider],
]);

const DEFAULT_SERVER_PROVIDER = openvscodeProvider.id;

export function getServerProvider(id?: string): VSCodeServerProvider {
  const provider = PROVIDERS.get(id ?? DEFAULT_SERVER_PROVIDER);
  if (!provider) {
    throw new Error(
      `Unknown VS Code server provider "${id}". Available: ${[...PROVIDERS.keys()].join(', ')}`
    );
  }
  return provider;
}
