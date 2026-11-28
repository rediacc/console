/**
 * The local session opt-in (D22, D23): REDIACC_ALLOW_GRAND_REPO and REDIACC_ALLOW_CLUSTER_OPS, read
 * into the overrides shape `decide` takes (packages/shared/src/policy/decide.ts).
 *
 * Each variable holds a comma-separated list of names (whitespace around entries trimmed, matched
 * case-sensitively), and any `*` entry makes it a wildcard. A variable counts only when the
 * ancestry walk proves a human set it before the agent started (`isOverrideLegitimate`): a value an
 * agent injected into its own environment, or one the platform cannot verify, grants nothing.
 */

import type { DecisionOverrides } from '@rediacc/shared/policy';
import {
  isOverrideLegitimate,
  OVERRIDE_VAR_CLUSTER,
  OVERRIDE_VAR_GRAND,
} from '../../utils/process-ancestry.js';

type OptIn = DecisionOverrides['grandRepos'];

/** Parse one opt-in value: unset or empty grants nothing, any `*` entry is a wildcard. */
export function parseOptIn(raw: string | undefined): OptIn {
  const entries = (raw ?? '')
    .split(',')
    .map((entry) => entry.trim())
    .filter(Boolean);
  if (entries.length === 0) return null;
  if (entries.includes('*')) return '*';
  return entries;
}

export interface EnvOverrideSources {
  env: NodeJS.ProcessEnv;
  /** Whether a human set `name` before the agent started. */
  isLegitimate: (name: string) => boolean;
}

const defaultSources = (): EnvOverrideSources => ({
  env: process.env,
  isLegitimate: isOverrideLegitimate,
});

function readOne(name: string, sources: EnvOverrideSources): OptIn {
  const parsed = parseOptIn(sources.env[name]);
  if (parsed === null) return null;
  return sources.isLegitimate(name) ? parsed : null;
}

/** The env opt-ins of this process, each one dropped unless its ancestry proves a human set it. */
export function readEnvOverrides(
  sources: EnvOverrideSources = defaultSources()
): DecisionOverrides {
  const grandRepos = readOne(OVERRIDE_VAR_GRAND, sources);
  const clusterOps = readOne(OVERRIDE_VAR_CLUSTER, sources);
  return {
    grandRepos,
    clusterOps,
    source: grandRepos === null && clusterOps === null ? 'none' : 'env',
  };
}
