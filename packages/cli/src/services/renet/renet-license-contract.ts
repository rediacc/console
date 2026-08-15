import {
  LICENSE_TIERS,
  type LicenseTier,
  type LicenseTierEntry,
} from '@rediacc/shared/renet-contract';

export const RENET_LICENSE_REQUIRED_EXIT_CODE = 10;
export const RENET_LICENSE_REQUIRED_CODE = 'LICENSE_REQUIRED';

export interface RenetLicenseFailure {
  code: string;
  reason: string;
  message?: string;
}

function parseStructuredLine(line: string): RenetLicenseFailure | null {
  try {
    const parsed = JSON.parse(line) as Partial<RenetLicenseFailure>;
    if (
      typeof parsed.code === 'string' &&
      typeof parsed.reason === 'string' &&
      parsed.code === RENET_LICENSE_REQUIRED_CODE
    ) {
      return {
        code: parsed.code,
        reason: parsed.reason,
        message: typeof parsed.message === 'string' ? parsed.message : undefined,
      };
    }
  } catch {
    return null;
  }

  return null;
}

export function parseRenetLicenseFailure(
  stderr?: string,
  stdout?: string
): RenetLicenseFailure | null {
  for (const chunk of [stderr, stdout]) {
    if (!chunk) continue;
    const lines = chunk
      .split(/\r?\n/)
      .map((line) => line.trim())
      .filter(Boolean)
      .reverse();
    for (const line of lines) {
      const parsed = parseStructuredLine(line);
      if (parsed) return parsed;
    }
  }

  return null;
}

// A Map rather than a bare index access, so "not registered" is expressible.
// `Record<string, T>` types every index access as always-present, which makes
// the undefined case unwritable without lying to the type checker, and it is
// exactly the case callers must distinguish from tier 'none'.
const TIER_BY_FUNCTION: ReadonlyMap<string, LicenseTier> = new Map(
  Object.entries(LICENSE_TIERS).map(([name, entry]: [string, LicenseTierEntry]) => [
    name,
    entry.tier,
  ])
);

/**
 * The licence tier renet assigns to a bridge function, read from the generated
 * contract (`LICENSE_TIERS`), which is emitted from renet's tier map.
 *
 * `undefined` means renet has no entry for the name. That is not "free": every
 * registered function is required to carry a tier, and renet's completeness
 * gate fails the build when one does not. An unknown name here is either a typo
 * or a function this CLI build predates.
 */
export function getRenetFunctionLicenseTier(functionName: string): LicenseTier | undefined {
  return TIER_BY_FUNCTION.get(functionName);
}

/**
 * The prefix that scopes repo-licence issuance. Licences are minted per
 * repository, so only `repository_*` verbs have an issuance context to resolve
 * (a repo name, a GUID, a size). Create-tier verbs outside that prefix
 * (`datastore_create`, `kube_install`, `ceph_cluster_create`, ...) are licensed
 * by renet but have no repo to mint against.
 */
const REPO_LICENSE_FUNCTION_PREFIX = 'repository_';

/**
 * Create-tier repository verbs that provision NOTHING, and therefore need no
 * pre-issuance despite their tier.
 *
 * `repository_commit_meta` reconstructs an immutable commit's out-of-volume
 * state mirror on a machine the commit was just pushed to (repo-delta.ts
 * finalizePush). It makes no repository: renet's cmd layer runs no licence
 * check for it at all, and the only check it meets is the bridge dispatch's
 * create-tier one, which resolves `params.repository` — a repo that already
 * exists on that machine. So the licence it needs is the PUSHED repo's, which
 * the push path is responsible for, not a fresh one. Routing it through
 * pre-issuance would mint a second licence for an existing repo and burn an
 * issuance against the monthly quota for a metadata write.
 */
const METADATA_ONLY_CREATE_TIER_FUNCTIONS: ReadonlySet<string> = new Set([
  'repository_commit_meta',
]);

/**
 * Create-tier repository verbs whose NEW repo is named by `params.tag` rather
 * than by `params.repository`. `params.repository` on these names the SOURCE
 * (the parent repo, or the working fork being frozen), which is where the
 * lineage and the size estimate come from.
 *
 * This is a param shape, not a tier, which is why it is enumerated instead of
 * derived. Both entries are checked against renet at the seam: the bridge
 * builder for each declares a required `tag` param
 * (pkg/functions/commands/repository.go), and renet's cmd layer validates the
 * licence against that tag's name (cmd/renet/repository_commit.go's
 * ValidateInstalledRepoLicenseForCreate(scope, commitName)).
 */
const TAG_TARGETED_PROVISIONING_FUNCTIONS: ReadonlySet<string> = new Set([
  'repository_fork',
  'repository_commit',
]);

/**
 * True for the repository verbs that provision a NEW repo, and therefore need a
 * repo licence minted BEFORE renet runs, against a GUID that does not exist on
 * disk yet.
 *
 * The class is derived from renet's tier map rather than restated: `create` is
 * exactly the tier renet gives to verbs that bring a repository into existence.
 * Today that resolves to `repository_create`, `repository_fork` and
 * `repository_commit`; if renet adds another create-shaped repository verb,
 * this follows without an edit here.
 *
 * The one subtraction is the metadata-only set above: create-tier is renet's
 * answer to "what does the dispatch check look for", and for
 * `repository_commit_meta` that is an EXISTING repo. See its comment.
 */
export function isRepoProvisioningFunction(functionName: string): boolean {
  return (
    functionName.startsWith(REPO_LICENSE_FUNCTION_PREFIX) &&
    getRenetFunctionLicenseTier(functionName) === 'create' &&
    !METADATA_ONLY_CREATE_TIER_FUNCTIONS.has(functionName)
  );
}

/**
 * The disaster-recovery verb that needs a repo licence installed on the target
 * machine BEFORE it runs, without being a repo-provisioning verb.
 *
 * `renet backup restore` opens a chunk-store session, and the licence blob is
 * what it exchanges for one (cmd/renet/backup_restore.go's
 * `resolveRestoreLicense`): it is the bearer credential AND the address book,
 * since the session URL is derived from the blob's `RenewalURL`. On a fresh DR
 * machine there is no blob at all, so the restore refuses — which is exactly
 * the case the verb exists for.
 *
 * This is a SEPARATE classification from `isRepoProvisioningFunction`, and the
 * separation is deliberate rather than incidental:
 *
 * - It is not a repository_* verb, so it fails that predicate's prefix gate and
 *   `resolveRepoLicenseContext`'s (local-executor.ts, `if
 *   (!functionName.startsWith('repository_')) return null;`).
 * - It is TierNone in renet's map, and that is a load-bearing decision, not an
 *   oversight (pkg/license/tiermap.go: "a tier gate on the DISASTER RECOVERY
 *   verb would mean an expired licence can lock a customer out of their own
 *   backed-up data"). Promoting it to create-tier so it fell out of the tier
 *   map naturally would reintroduce the very lockout the pre-flight is here to
 *   remove.
 *
 * So the name is written out rather than derived. The requirement it encodes is
 * an IMPLEMENTATION one (a session needs a bearer blob), not a TIER one, and
 * the two must not be conflated — which is why this cannot be, and must not
 * become, a tier lookup.
 */
export function isRestoreLicenseFunction(functionName: string): boolean {
  return functionName === 'backup_restore';
}

/**
 * True when a provisioning verb's new repo is named by `params.tag`. Callers
 * resolving the issuance target must read `tag` for these and `repository` for
 * the rest.
 */
export function usesTagAsProvisioningTarget(functionName: string): boolean {
  return TAG_TARGETED_PROVISIONING_FUNCTIONS.has(functionName);
}

/*
 * `isLicensedRenetFunction` and its REPOSITORY_DENY_LIST used to live here.
 * Both are deleted, and the deletion is the point.
 *
 * They were a SECOND source of truth for which bridge functions need a licence,
 * maintained by hand alongside renet's tier map, and they had already drifted:
 * the prefix rule claimed every `backup_*` function was licensed, while renet
 * licenses none of them. Proven live, one enforcing binary, no licence
 * installed: `repository create` exits 10 LICENSE_REQUIRED, `backup list`
 * sails past licensing and fails on a missing flag.
 *
 * Nothing consumed it. The only production reference was the comment in
 * local-executor.ts explaining why recovery deliberately does NOT gate on it
 * (rediacc/console#482: skipping recovery for deny-listed functions is what
 * broke `repo push --up` to a fresh machine). Its only other callers were its
 * own tests. So it was dead code asserting something false, which is worse
 * than no code: the next person to need this answer would have found a
 * plausible helper and trusted it.
 *
 * You cannot drift from a duplicate that does not exist. The consumer that
 * genuinely needed this answer now exists directly above:
 * `getRenetFunctionLicenseTier` / `isRepoProvisioningFunction` read
 * `LICENSE_TIERS`, generated from renet's tier map (renet's pkg/license imports
 * neither pkg/functions nor pkg/functions/commands, so the generator reads the
 * map without an import cycle). local-executor.ts calls the second one wherever
 * it used to compare against the literals `repository_create` and
 * `repository_fork`. That is T3 of
 * docs/config-universe-follow-up/03-testing-pillar.md, and it is done.
 *
 * Literal function names survive only where the logic is genuinely per-function
 * rather than per-class, and they live HERE rather than in local-executor:
 * `repository_fork` and `repository_commit` take their target GUID from
 * `params.tag`, which is a param shape, not a tier.
 */
