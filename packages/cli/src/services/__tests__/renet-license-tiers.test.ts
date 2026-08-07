import { LICENSE_TIERS } from '@rediacc/shared/renet-contract';

import {
  getRenetFunctionLicenseTier,
  isRepoProvisioningFunction,
  usesTagAsProvisioningTarget,
} from '../renet/renet-license-contract.js';

/**
 * The CLI has exactly ONE notion of which bridge functions are licence-relevant,
 * and it is the generated contract (emitted from renet's tier map). These tests
 * pin that seam so a Go-side tier flip forces a conscious acknowledgment here
 * rather than silently changing when the CLI mints a repo licence.
 *
 * The Wave-2 reconciliation landed: repository_commit and
 * repository_commit_meta are CREATE tier now, matching the cmd-layer check
 * that was always there. Both are pinned below.
 */
describe('renet licence tiers (generated contract)', () => {
  it('has a decided tier for every entry', () => {
    const pending = Object.entries(LICENSE_TIERS)
      .filter(([, entry]) => entry.pending)
      .map(([name]) => name);
    expect(pending).toEqual([]);
  });

  it.each([
    ['repository_create', 'create'],
    ['repository_commit', 'create'],
    ['repository_commit_meta', 'create'],
    ['repository_resize', 'full'],
    ['repository_up', 'operate'],
    ['repository_down', 'none'],
    ['backup_push', 'full'],
    ['backup_list', 'none'],
  ])('pins %s at tier %s', (functionName, tier) => {
    expect(getRenetFunctionLicenseTier(functionName)).toBe(tier);
  });

  it('returns undefined for a function renet does not know', () => {
    expect(getRenetFunctionLicenseTier('repository_teleport')).toBeUndefined();
    expect(getRenetFunctionLicenseTier('')).toBeUndefined();
  });

  describe('isRepoProvisioningFunction', () => {
    it('accepts the create-tier repository verbs that actually provision a repo', () => {
      const createTier = Object.entries(LICENSE_TIERS)
        .filter(([name, entry]) => name.startsWith('repository_') && entry.tier === 'create')
        .map(([name]) => name)
        .sort();
      // The class today, pinned literally so a wholesale regeneration that
      // widens or empties it fails here instead of silently changing issuance.
      //
      // ACKNOWLEDGMENT of the Wave-2 tier flip: the commit verbs joined this
      // list when renet reconciled repository_commit / repository_commit_meta
      // to CREATE. The CLI's answer is deliberately NOT the same for both.
      // `repository_commit` provisions: its new immutable commit is a repo
      // that does not exist yet, and renet's cmd layer validates a licence
      // against that commit's name before doing anything
      // (cmd/renet/repository_commit.go), so the CLI pre-issues for it.
      // `repository_commit_meta` provisions nothing: it rewrites an already
      // pushed commit's out-of-volume state mirror, its cmd layer runs no
      // licence check at all, and the only check it meets resolves the
      // EXISTING repo — so pre-issuance is subtracted for it.
      expect(createTier).toEqual([
        'repository_commit',
        'repository_commit_meta',
        'repository_create',
        'repository_fork',
      ]);
      const provisioning = createTier.filter(isRepoProvisioningFunction);
      expect(provisioning).toEqual(['repository_commit', 'repository_create', 'repository_fork']);
    });

    it('subtracts the metadata-only create-tier verb', () => {
      expect(getRenetFunctionLicenseTier('repository_commit_meta')).toBe('create');
      expect(isRepoProvisioningFunction('repository_commit_meta')).toBe(false);
    });

    it('names the provisioning verbs whose target rides params.tag', () => {
      // A param shape, not a tier: `repository_create` mints against
      // `params.repository`, the other two against `params.tag` (the source
      // repo is what `params.repository` names for them).
      const tagTargeted = Object.keys(LICENSE_TIERS).filter(usesTagAsProvisioningTarget).sort();
      expect(tagTargeted).toEqual(['repository_commit', 'repository_fork']);
      expect(usesTagAsProvisioningTarget('repository_create')).toBe(false);
      expect(usesTagAsProvisioningTarget('repository_commit_meta')).toBe(false);
    });

    it('rejects create-tier verbs outside the repository prefix', () => {
      // Licensed by renet, but there is no repo to mint a licence against, so
      // the CLI must not route them through pre-flight issuance.
      for (const name of ['datastore_create', 'datastore_fork', 'kube_install']) {
        expect(getRenetFunctionLicenseTier(name)).toBe('create');
        expect(isRepoProvisioningFunction(name)).toBe(false);
      }
    });

    it('rejects repository verbs of every other tier, and unknown names', () => {
      for (const name of ['repository_resize', 'repository_up', 'repository_down']) {
        expect(isRepoProvisioningFunction(name)).toBe(false);
      }
      expect(isRepoProvisioningFunction('repository_teleport')).toBe(false);
    });
  });
});
