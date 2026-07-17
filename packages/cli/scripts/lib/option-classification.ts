/**
 * Option classification tables for the CLI contract generator: which options
 * bind to resource kinds (console pickers), which carry secrets, which have a
 * rendering format hint, and how prominent each is in a rendered form.
 *
 * Two kinds of table. Name tables key on an option's LONG (without dashes) and
 * apply everywhere that long appears — safe only when the long means the same
 * thing on every command. Override tables key on `<pathKey> --<long>` and win
 * over the name tables, for the cases where the same long means different
 * things (or nothing) per command.
 *
 * Every override key is gated for staleness against the live tree
 * ({@link collectClassificationProblems}), copying the PROXY_EXCLUSIONS
 * pattern in generate-cli-contract.ts: a renamed command or flag must fail
 * generation loudly, because a stale key does not fail on its own — the lookup
 * simply misses and the classification silently stops applying.
 */
import type {
  ContractOption,
  FormatHint,
  OptionTier,
  ResourceKind,
} from '../../../shared/src/cli-contract/types.js';
import { RESOURCE_KINDS } from '../../../shared/src/cli-contract/discovery.js';

// ---------- Resource-kind binding (console pick-or-type combobox) ----------

/**
 * Longs that name a resource wherever they appear.
 *
 * GUARD: there is deliberately NO 'strategy' entry in this table. The option
 * long `--strategy` on `repo migrate|pull|push` is the block-delta transfer
 * enum (`.choices(['auto','physical','shared'])`) and must NEVER map to the
 * `strategy` RESOURCE kind (backup strategies, the config's backupStrategies
 * family). The strategy resource is bound by POSITIONALS — the `<strategy>`
 * arguments of `backup strategy *` — via POSITIONAL_KIND_BY_NAME in the
 * generator, never by an option long.
 */
export const OPTION_KINDS_BY_NAME: Readonly<Record<string, readonly ResourceKind[]>> = {
  machine: ['machine'],
  'to-machine': ['machine'],
  'from-machine': ['machine'],
  'control-node': ['machine'],
  container: ['container'],
  datastore: ['datastore'],
  storage: ['storage'],
  cluster: ['cluster'],
  repo: ['repo'],
  provider: ['provider'],
  template: ['template'],
};

/**
 * A per-command kinds decision: either the kinds the option binds, or an
 * explicit waiver saying why a resource-noun long does NOT bind a resource on
 * this command. A waiver reason must carry its own explanation (≥30 chars) —
 * the same bar as a BLOCKER comment.
 */
export type OptionKindOverride = readonly ResourceKind[] | { readonly waived: string };

export const OPTION_KIND_OVERRIDES: Readonly<Record<string, OptionKindOverride>> = {
  // ── Directional flags whose long says nothing about the noun ────────────
  'datastore attach --to': ['machine'],
  'datastore fork --attach-to': ['machine'],
  'repo push --to': ['machine', 'storage'],
  'repo pull --from': ['machine', 'storage'],
  'repo migrate --to': ['machine', 'cluster'],
  'cluster fork --to': ['cluster'],
  'cluster migrate --to': ['cluster'],
  'cluster rehearse --on': ['cluster'],
  'repo checkout --from': ['repo'],
  'repo merge --from': ['repo'],
  'repo diff --base': ['repo'],

  // ── Longs outside the noun set that still bind a resource ───────────────
  // `--provision <provider>` names a configured cloudProviders entry to
  // auto-provision the destination with.
  'repo push --provision': ['provider'],
  'repo migrate --provision': ['provider'],
  // `--grand <name>` names the parent credential repository to share secrets
  // with — a repo binding under a role name.
  'repo admin template apply --grand': ['repo'],

  // ── Waivers: the long is in the noun set, the option binds no resource ──
  'machine provider add --provider': {
    waived:
      'names the upstream registry source of a NEW provider being added (e.g. linode/linode), not a configured cloudProviders entry',
  },
  'cluster snapshot create --snapshot': {
    waived: 'labels the NEW snapshot being created; there is no existing snapshot to pick from',
  },
  'datastore snapshot create --snapshot': {
    waived: 'labels the NEW snapshot being created; there is no existing snapshot to pick from',
  },
  'backup strategy set --destination': {
    waived:
      'a destination is a named sub-entry INSIDE the strategy being edited, not one of the contract resource kinds',
  },
  'backup strategy remove --destination': {
    waived:
      'a destination is a named sub-entry INSIDE the strategy being edited, not one of the contract resource kinds',
  },
  'repo merge --base': {
    waived:
      'a common-ancestor commit GUID for the three-way merge, not a repository ref — FORMAT_OVERRIDES gives it format "guid" instead',
  },
};

/**
 * Longs that MUST resolve to a kinds decision: via {@link OPTION_KINDS_BY_NAME},
 * via {@link OPTION_KIND_OVERRIDES}, or via an explicit waiver. This is the
 * coverage gate's input — a new command reusing one of these resource-noun
 * longs cannot ship unclassified (a silent "no picker" degradation).
 */
export const RESOURCE_NOUN_GATE: ReadonlySet<string> = new Set([
  ...Object.keys(OPTION_KINDS_BY_NAME),
  'to',
  'from',
  'on',
  'base',
  'attach-to',
  'snapshot',
  'destination',
]);

// ---------- Sensitive values (console masks input, redacts run history) ----

/**
 * Longs whose value is a secret wherever they appear. Deliberately NOT here:
 * `--ssh-key` / `--key` (paths to key FILES, or public secret NAMES like
 * `repo secret --key` — the name is not the secret, the value is).
 */
export const SENSITIVE_BY_NAME: ReadonlySet<string> = new Set([
  'token',
  'master-password',
  'cf-dns-token',
  'current',
  'new',
  'current-secrets',
]);

export const SENSITIVE_OVERRIDES: Readonly<Record<string, boolean>> = {
  // The secret plaintext itself; `--key` beside it is just the secret's name.
  'repo secret set --value': true,
  // Rclone credentials as a JSON blob — a secret in run history even though
  // the long says nothing secret-sounding.
  'storage add --vault': true,
};

// ---------- Format hints (console picks a control, validates client-side) --

/** Longs whose value has the same shape on every command that declares them. */
export const FORMAT_BY_NAME: Readonly<Record<string, FormatHint>> = {
  // sizes ("100G")
  size: 'size',
  'cow-size': 'size',
  'control-ds-size': 'size',
  'max-quota': 'size',
  // schedules and rates
  cron: 'cron',
  bwlimit: 'bandwidth',
  refresh: 'duration',
  // identifiers and addresses
  'delta-base': 'guid',
  server: 'url',
  'api-url': 'url',
  'base-domain': 'domain',
  'network-cidr': 'cidr',
  'public-ipv4': 'ipv4',
  'public-ipv6': 'ipv6',
  port: 'port',
  // percentages
  weight: 'percent',
  'grow-threshold': 'percent',
  // bare numbers — verified against the live labels: `--older-than` is "in
  // hours", `--timeout` is milliseconds, `--health-*` are seconds,
  // `--trim-interval` is hours, so none of them parse a duration string.
  concurrency: 'integer',
  replicas: 'integer',
  count: 'integer',
  lines: 'integer',
  uid: 'integer',
  'since-line': 'integer',
  'max-bytes': 'integer',
  offset: 'integer',
  head: 'integer',
  tail: 'integer',
  'older-than': 'integer',
  timeout: 'integer',
  'health-window': 'integer',
  'health-timeout': 'integer',
  'trim-interval': 'integer',
  'grace-days': 'integer',
  'net-offset': 'integer',
  'control-id': 'integer',
  'vm-id': 'integer',
  // filesystem-ish paths
  path: 'path',
  remote: 'path',
  'remote-file': 'path',
  file: 'path',
  folder: 'path',
  'ssh-key': 'path',
  'renet-path': 'path',
  'datastore-path': 'path',
  apply: 'path',
  'server-archive': 'path',
};

/** Per-command exceptions; `null` suppresses a wrong name-table hint. */
export const FORMAT_OVERRIDES: Readonly<Record<string, FormatHint | null>> = {
  // Commit GUID (see the kinds waiver on the same key).
  'repo merge --base': 'guid',
  // `--key` is ambiguous by name (secret name vs key file); only this one is a path.
  'config ssh set --key': 'path',
  // `--local` is a directory on the sync commands but a PORT on the tunnels.
  'repo sync upload --local': 'path',
  'repo sync download --local': 'path',
  'repo sync status --local': 'path',
  'repo tunnel --local': 'port',
  'vscode connect --local': 'port',
  // A JSON Pointer glob (/credentials/*), not a filesystem path.
  'config audit log --path': null,
};

// ---------- Tier (progressive disclosure in rendered forms) ----------------

/**
 * Overrides promoting everyday options that the derivation (mandatory, kinds,
 * or choices ⇒ common) would otherwise fold behind the "advanced" disclosure.
 * Entries on already-mandatory options (`repo fork --tag`, …) are deliberate:
 * they pin the promotion even if the flag ever stops being requiredOption().
 *
 * An override can NEVER demote a mandatory option to 'advanced' — gated in
 * {@link collectClassificationProblems}.
 */
export const TIER_OVERRIDES: Readonly<Record<string, OptionTier>> = {
  'repo fork --tag': 'common',
  'repo checkout --tag': 'common',
  'datastore fork --tag': 'common',
  'cluster fork --tag': 'common',
  'cluster rehearse --tag': 'common',
  'datastore create --size': 'common',
  'repo create --size': 'common',
  'repo sync upload --local': 'common',
  'repo sync download --local': 'common',
  'repo logs --lines': 'common',
  'job logs --follow': 'common',
  'backup list --watch': 'common',
  'repo up --all': 'common',
  'repo down --all': 'common',
};

// ---------- Resolvers (what the generator applies per option) ---------------

function overrideKey(pathKey: string, long: string): string {
  return `${pathKey} --${long}`;
}

/** The kinds an option binds, or undefined (no binding, or waived). */
export function resolveOptionKinds(
  pathKey: string,
  long: string,
  valueTaking: boolean
): readonly ResourceKind[] | undefined {
  const override = OPTION_KIND_OVERRIDES[overrideKey(pathKey, long)];
  if (override !== undefined) {
    return 'waived' in override ? undefined : override;
  }
  if (!valueTaking) return undefined;
  return OPTION_KINDS_BY_NAME[long];
}

/** The rendering hint for an option's value, or undefined (plain text box). */
export function resolveOptionFormat(pathKey: string, long: string): FormatHint | undefined {
  const key = overrideKey(pathKey, long);
  if (key in FORMAT_OVERRIDES) return FORMAT_OVERRIDES[key] ?? undefined;
  return FORMAT_BY_NAME[long];
}

/** Whether an option's value is a secret. */
export function resolveOptionSensitive(pathKey: string, long: string): boolean {
  return SENSITIVE_OVERRIDES[overrideKey(pathKey, long)] ?? SENSITIVE_BY_NAME.has(long);
}

/**
 * How prominent an option is in a rendered form: mandatory, resource-bound and
 * enum options are common by derivation; everything else folds behind the
 * disclosure unless {@link TIER_OVERRIDES} promotes it.
 */
export function resolveOptionTier(
  pathKey: string,
  long: string,
  facts: { mandatory: boolean; hasKinds: boolean; hasChoices: boolean }
): OptionTier {
  const derived: OptionTier =
    facts.mandatory || facts.hasKinds || facts.hasChoices ? 'common' : 'advanced';
  return TIER_OVERRIDES[overrideKey(pathKey, long)] ?? derived;
}

// ---------- Gates -----------------------------------------------------------

type GateCommand = {
  readonly pathKey: string;
  readonly options: ReadonlyArray<Pick<ContractOption, 'long' | 'valueTaking' | 'mandatory'>>;
};

/**
 * Everything that must hold for the tables to be trustworthy, as a list of
 * human-readable problems (empty = clean). The generator prints these red and
 * exits 1: a wrong or stale entry must never survive a regen silently.
 *
 *   1. Staleness: every override key names a live command AND a flag that
 *      command declares (kinds/sensitive/format additionally require the flag
 *      to take a value — a boolean names no resource, carries no secret value,
 *      renders no value control).
 *   2. Waiver quality: a kinds waiver must explain itself in ≥30 characters.
 *   3. Kind hygiene: every kinds array is nonempty and every member is a real
 *      ResourceKind (guards a hand-edited table under tsx, which never
 *      typechecks).
 *   4. Coverage: every value-taking option whose long is in
 *      {@link RESOURCE_NOUN_GATE} resolves via name table, override, or waiver.
 *   5. Tier floor: an override can never demote a mandatory option to
 *      'advanced' — the CLI refuses to run without it, so a form can never be
 *      allowed to fold it out of sight.
 */
export function collectClassificationProblems(commands: readonly GateCommand[]): string[] {
  const problems: string[] = [];
  const byPath = new Map(commands.map((c) => [c.pathKey, c]));

  const checkOverrideKey = (
    key: string,
    table: string,
    opts?: { requireValueTaking?: boolean }
  ): GateCommand['options'][number] | undefined => {
    const idx = key.lastIndexOf(' --');
    if (idx === -1) {
      problems.push(`${table}["${key}"]: key must be "<pathKey> --<long>"`);
      return undefined;
    }
    const pathKey = key.slice(0, idx);
    const long = key.slice(idx + 3);
    const cmd = byPath.get(pathKey);
    if (!cmd) {
      problems.push(
        `${table}["${key}"]: no command "${pathKey}" — stale key, re-key it to the command's current name or delete it deliberately`
      );
      return undefined;
    }
    const opt = cmd.options.find((o) => o.long === long);
    if (!opt) {
      problems.push(
        `${table}["${key}"]: "${pathKey}" declares no --${long} — stale key, re-key it to the flag's current long or delete it deliberately`
      );
      return undefined;
    }
    if (opts?.requireValueTaking && !opt.valueTaking) {
      problems.push(`${table}["${key}"]: --${long} takes no value`);
    }
    return opt;
  };

  const validKinds = new Set<string>(RESOURCE_KINDS);
  const checkKindsArray = (owner: string, kinds: readonly ResourceKind[]): void => {
    if (kinds.length === 0) problems.push(`${owner}: kinds array is empty`);
    for (const kind of kinds) {
      if (!validKinds.has(kind)) problems.push(`${owner}: "${kind}" is not a ResourceKind`);
    }
  };

  for (const [name, kinds] of Object.entries(OPTION_KINDS_BY_NAME)) {
    checkKindsArray(`OPTION_KINDS_BY_NAME["${name}"]`, kinds);
  }
  for (const [key, entry] of Object.entries(OPTION_KIND_OVERRIDES)) {
    checkOverrideKey(key, 'OPTION_KIND_OVERRIDES', { requireValueTaking: true });
    if ('waived' in entry) {
      if (entry.waived.trim().length < 30) {
        problems.push(
          `OPTION_KIND_OVERRIDES["${key}"]: waiver reason must explain itself in ≥30 characters`
        );
      }
    } else {
      checkKindsArray(`OPTION_KIND_OVERRIDES["${key}"]`, entry);
    }
  }
  for (const key of Object.keys(SENSITIVE_OVERRIDES)) {
    checkOverrideKey(key, 'SENSITIVE_OVERRIDES', { requireValueTaking: true });
  }
  for (const key of Object.keys(FORMAT_OVERRIDES)) {
    checkOverrideKey(key, 'FORMAT_OVERRIDES', { requireValueTaking: true });
  }
  for (const [key, tier] of Object.entries(TIER_OVERRIDES)) {
    const opt = checkOverrideKey(key, 'TIER_OVERRIDES');
    if (opt && tier === 'advanced' && opt.mandatory) {
      problems.push(
        `TIER_OVERRIDES["${key}"]: may not demote a mandatory option to "advanced" — the CLI refuses to run without it, so it can never fold out of sight`
      );
    }
  }

  for (const cmd of commands) {
    for (const opt of cmd.options) {
      if (!opt.valueTaking) continue;
      if (!RESOURCE_NOUN_GATE.has(opt.long)) continue;
      const key = overrideKey(cmd.pathKey, opt.long);
      if (OPTION_KIND_OVERRIDES[key] !== undefined) continue;
      if (OPTION_KINDS_BY_NAME[opt.long] !== undefined) continue;
      problems.push(
        `${cmd.pathKey} --${opt.long}: resource-noun option is unclassified — add kinds via OPTION_KINDS_BY_NAME or OPTION_KIND_OVERRIDES, or waive it with { waived: '<why this long binds no resource here>' }`
      );
    }
  }

  return problems;
}
