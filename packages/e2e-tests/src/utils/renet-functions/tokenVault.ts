import { VaultBuilder } from '../vault/VaultBuilder';
import type { TestFunctionOptions } from './types';

/**
 * Option key to the function parameter name the vault carries it under. These are exactly the
 * options the two token-bearing kube functions (kube_join, kube_identity_rewrite) read.
 */
const PARAM_NAMES: Readonly<Record<string, string>> = {
  token: 'token',
  mountPath: 'mount_path',
  role: 'role',
  endpoint: 'endpoint',
  bindIp: 'bind_ip',
  operation: 'operation',
  mode: 'mode',
  newNodeIp: 'new_node_ip',
  newNetworkId: 'new_network_id',
  writes: 'writes',
  server: 'server_endpoint',
};

/** Option keys that are not parameters (or are handled separately) and are fine to carry. */
const CONTROL_KEYS: ReadonlySet<string> = new Set([
  'function',
  'networkId',
  'keepThirdParty',
  'timeout',
]);

/**
 * Build the vault a `renet functions once --vault-file` run reads in place of the flags, so a
 * join token travels in a file (uploaded over stdin) and never on a logged command line.
 * Throws for any option the vault does not carry, so a flag is never dropped silently.
 */
export function buildTokenVault(opts: TestFunctionOptions, defaultNetworkId: string): string {
  if (!opts.token) {
    throw new Error('buildTokenVault needs a token');
  }
  const unsupported = Object.entries(opts)
    .filter(
      ([key, value]) => value !== undefined && !(key in PARAM_NAMES) && !CONTROL_KEYS.has(key)
    )
    .map(([key]) => key);
  if (unsupported.length > 0) {
    throw new Error(`token vault cannot carry: ${unsupported.join(', ')}`);
  }
  const record = opts as unknown as Record<string, unknown>;
  const params: Record<string, string | number | boolean> = {};
  for (const [key, name] of Object.entries(PARAM_NAMES)) {
    const value = record[key];
    if (typeof value === 'string' && value !== '') params[name] = value;
  }
  const networkId = Number(opts.networkId ?? defaultNetworkId);
  if (networkId) params.network_id = networkId;
  if (opts.keepThirdParty) params.keep_third_party_secrets = true;
  return new VaultBuilder()
    .withFunction(opts.function)
    .withTeam('test-team')
    .withMachine('127.0.0.1', 'test')
    .withParams(params)
    .toJSON();
}
