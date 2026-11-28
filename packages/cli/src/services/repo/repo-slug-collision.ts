import { t } from '../../i18n/index.js';
import { ValidationError } from '../../utils/errors.js';
import { repoKeySlug } from '../cluster/repo-replicate.js';

const GRAND_TAG = 'latest';

/**
 * The ref a repo is known by: the bare name for a `latest` grand, `name:tag` for a fork.
 * Config keys are always `name:tag`, so `shop:latest` is shown as `shop`.
 */
export function repoDisplayKey(configKey: string): string {
  return configKey.endsWith(`:${GRAND_TAG}`)
    ? configKey.slice(0, -(GRAND_TAG.length + 1))
    : configKey;
}

/**
 * Refuse a new repo whose slug equals another repo's. `repoKeySlug` maps `shop:test` and a literal
 * `shop-test` to one stem, so both would derive the same replica set name and datastore fork tag.
 * Creation is the one place that can keep them apart; this is the guarantee `replicaSetNameFor`
 * and the canary name rely on. Keys are display keys (see `repoDisplayKey`); an identical key is
 * not a collision here, the duplicate-name checks own that.
 */
export function assertNoSlugCollision(newKey: string, existingKeys: Iterable<string>): void {
  const slug = repoKeySlug(newKey);
  for (const existing of existingKeys) {
    if (existing !== newKey && repoKeySlug(existing) === slug) {
      throw new ValidationError(t('errors.repo.slugCollision', { ref: newKey, existing, slug }));
    }
  }
}
