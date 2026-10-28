import { VaultBuilder } from '../vault/VaultBuilder';
import type { TestFunctionOptions } from './types';

/** The option keys a password-carrying call may use; the vault mirrors exactly these. */
const SUPPORTED_KEYS: ReadonlySet<string> = new Set([
  'function',
  'datastorePath',
  'repository',
  'networkId',
  'password',
  'size',
  'newSize',
  'timeout',
]);

/**
 * Build the vault a `renet functions once --vault-file` run reads in place of the flags
 * `--repository/--network-id/--size/--new-size/--password`, so the repository passphrase
 * travels in a file (uploaded over stdin) and never on a command line.
 * Throws for any option the vault does not carry, so a flag is never dropped silently.
 */
export function buildPasswordVault(opts: TestFunctionOptions, defaultNetworkId: string): string {
  const { password, repository } = opts;
  if (!password || !repository) {
    throw new Error('buildPasswordVault needs both password and repository');
  }
  const unsupported = Object.entries(opts)
    .filter(([key, value]) => value !== undefined && !SUPPORTED_KEYS.has(key))
    .map(([key]) => key);
  if (unsupported.length > 0) {
    throw new Error(`password vault cannot carry: ${unsupported.join(', ')}`);
  }
  const networkId = Number(opts.networkId ?? defaultNetworkId);
  const builder = new VaultBuilder()
    .withFunction(opts.function)
    .withTeam('test-team')
    .withRepository(repository, repository, networkId)
    .withRepositoryCredential(repository, password)
    .withMachine('127.0.0.1', 'test', opts.datastorePath)
    .withParams({ network_id: networkId });
  if (opts.datastorePath) builder.withDatastore(opts.datastorePath);
  if (opts.size) builder.withParams({ size: opts.size });
  if (opts.newSize) builder.withParams({ new_size: opts.newSize });
  return builder.toJSON();
}
