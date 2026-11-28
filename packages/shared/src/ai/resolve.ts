/**
 * Which profile a chat uses (D3 of PLAN-console-ai-providers): the team config's
 * profile first, then the shared config's. Pure; the caller pulls both configs.
 *
 * With no name, the team config's `default` wins when it has one, else the
 * shared config's. With a name, a team profile of that name shadows a shared one.
 * A `default` that names a missing profile is an error rather than a reason to
 * fall through to the other config, and a profile that fails validation (shape or
 * the base URL guard) is never returned.
 *
 * `rediacc:standard` and `rediacc:premium` are built in (rediacc-tier.ts): they win over a config
 * profile of the same name, so a config can never shadow the metered path, and they skip the base URL
 * guard because their `ai.internal` host is the one that guard refuses for customer profiles.
 */
import { type AiConfig, type Profile, validateProfile } from './profile.js';
import { buildRediaccProfile, parseRediaccChoice } from './rediacc-tier.js';

export type ProfileSource = 'team' | 'shared' | 'rediacc';

export type ResolveFailure =
  | { ok: false; reason: 'none-configured'; message: string }
  | { ok: false; reason: 'unknown-profile'; source?: ProfileSource; message: string }
  | { ok: false; reason: 'invalid-profile'; source: ProfileSource; name: string; message: string };

export type ResolvedProfile =
  | { ok: true; name: string; source: ProfileSource; profile: Profile }
  | ResolveFailure;

export interface AiConfigs {
  team?: AiConfig | undefined;
  shared?: AiConfig | undefined;
}

function validated(name: string, source: ProfileSource, raw: unknown): ResolvedProfile {
  const checked = validateProfile(raw);
  if (checked.ok) return { ok: true, name, source, profile: checked.profile };
  return {
    ok: false,
    reason: 'invalid-profile',
    source,
    name,
    message: `profile "${name}" of the ${source} config is invalid: ${checked.issues
      .map((i) => `${i.path} ${i.message}`)
      .join('; ')}`,
  };
}

const SOURCES = ['team', 'shared'] as const;

function builtIn(name: string): ResolvedProfile | undefined {
  const tier = parseRediaccChoice(name);
  if (tier === undefined) return undefined;
  return { ok: true, name, source: 'rediacc', profile: buildRediaccProfile(tier) };
}

function resolveNamed(configs: AiConfigs, name: string): ResolvedProfile {
  const own = builtIn(name);
  if (own) return own;
  for (const source of SOURCES) {
    const config = configs[source];
    if (config && Object.hasOwn(config.providers, name)) {
      return validated(name, source, config.providers[name]);
    }
  }
  return {
    ok: false,
    reason: 'unknown-profile',
    message: `no AI profile named "${name}" in the team or shared config`,
  };
}

function resolveDefault(configs: AiConfigs): ResolvedProfile {
  for (const source of SOURCES) {
    const config = configs[source];
    const name = config?.default;
    if (config === undefined || name === undefined) continue;
    const own = builtIn(name);
    if (own) return own;
    if (!Object.hasOwn(config.providers, name)) {
      return {
        ok: false,
        reason: 'unknown-profile',
        source,
        message: `the ${source} config's default profile "${name}" does not exist`,
      };
    }
    return validated(name, source, config.providers[name]);
  }
  return {
    ok: false,
    reason: 'none-configured',
    message: 'no AI profile is configured: set a default profile in the team or shared config',
  };
}

/** Pick the profile for a chat. `requested` is a profile name the caller chose, if any. */
export function resolveProfile(configs: AiConfigs, requested?: string): ResolvedProfile {
  return requested === undefined ? resolveDefault(configs) : resolveNamed(configs, requested);
}
