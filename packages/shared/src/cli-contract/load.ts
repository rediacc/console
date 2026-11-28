/**
 * Lazy access to the bundled CLI contract.
 *
 * The contract literal is over half a megabyte of source, so a web bundle must
 * not import it statically: `loadCliContract()` reaches it through a dynamic
 * import, which a bundler splits into its own chunk fetched on first call. Pair
 * it with `indexContract` from `./core` for lookups. The module system caches
 * the import, so later calls resolve to the same object.
 */
import type { CliContract } from './types.js';

/** Load the bundled contract on demand. */
export async function loadCliContract(): Promise<CliContract> {
  const { CLI_CONTRACT } = await import('./data/contract.generated.js');
  return CLI_CONTRACT;
}
