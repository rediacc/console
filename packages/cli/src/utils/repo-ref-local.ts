/**
 * Config-local repo ref resolution, kept out of repo-target.ts on purpose: repo-target imports the
 * executor (job directives, the presence probe), so a config-only command that imported it would read
 * as machine-touching to check:ci-command-planes. This module reaches the config service and the
 * pure addressing rules only.
 */
import { parseRef } from '../services/addressing/ref-parser.js';
import {
  placementViewFromConfig,
  resolveRefLocal,
} from '../services/addressing/resolve-machine.js';
import { configService } from '../services/config/config-resources.js';
import { notFound } from './cli-exit-error.js';

/**
 * The config-local resolution of a positional repo `<ref>`: the family/tag and
 * the derived identifiers, WITHOUT resolving (or requiring) a placement machine.
 * For verbs whose whole effect lands in the local config and that never dispatch
 * to a machine (`repo secret get|list|set|unset`, `repo branch`), resolving a
 * machine there is both unnecessary and harmful, because it would refuse the verb
 * on a repo whose datastore is currently detached or whose placement has not been
 * reconciled yet.
 */
export interface ResolvedRepoRefLocal {
  /** The repo family name parsed from the ref (`shop` for `shop:test`). */
  name: string;
  /** The config/renet identifier: the ref minus any `@place` (`shop`, `shop:test`). */
  repoKey: string;
  /** The resolved stored tag key (the family's grand tag for a bare/base ref). */
  tag: string;
  /** The `@place` the ref carried (advisory for config-local verbs; not verified). */
  place?: string;
}

/**
 * Resolve a positional repo `<ref>` to its family/tag WITHOUT machine derivation
 * (spec/03 §2.3 tail). Throws a `CliExitError` (exit 2 grammar / exit 5 unknown
 * family or tag) but never exit 12 for a missing placement or detached datastore.
 */
export async function resolveRepoRefLocal(ref: string): Promise<ResolvedRepoRefLocal> {
  const parsed = parseRef(ref);
  const config = await configService.getCurrent();
  if (!config) {
    throw notFound(`repository "${parsed.name}" is not in this config.`);
  }
  const view = placementViewFromConfig(config);
  const { name, tag, place } = resolveRefLocal(ref, view);
  return {
    name,
    repoKey: parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name,
    tag,
    ...(place !== undefined && { place }),
  };
}
