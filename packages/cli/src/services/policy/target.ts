/**
 * The one repo resolver every enforcement path uses to build `decide`'s target
 * (packages/shared/src/policy/decide.ts).
 *
 * A repo ref resolves through `configService.getRepository` with the same `name[:tag]` key the
 * action bodies pass. A repo is a fork exactly when its config record has a `grandGuid` naming
 * another repository. A ref that does not parse, or that the config does not name, comes back as
 * `unresolved` rather than absent, and `decide` treats it as grand (fail closed).
 *
 * The ops-VM test is the placement's (`isOpsVmPlacement`) for a repo the config names, and the
 * machine's (`isOpsVmMachine`) otherwise: the ref's `@place`, else the machine the caller passes.
 *
 * The lookups read the active config; the executor runs this inside its request context so they
 * read the request's config instead.
 */

import type { DecisionTarget, RepoState } from '@rediacc/shared/policy';
import { CliExitError } from '../../utils/cli-exit-error.js';
import { isOpsVmMachine, isOpsVmPlacement } from '../../utils/ops-vm.js';
import { type ParsedRef, parseRef } from '../addressing/ref-parser.js';
import { configService } from '../config/config-resources.js';

export interface TargetRef {
  /** The repo ref as typed (`name`, `name:tag`, `name@machine`); absent when the command names none. */
  ref?: string;
  /** The machine the command targets, when it names one apart from the ref. */
  machine?: string;
  /** The cluster or datastore name a cluster opt-in must cover. */
  subject?: string;
}

/** Parse a ref, or null when it breaks the ref grammar (any other failure propagates). */
function tryParseRef(ref: string): ParsedRef | null {
  try {
    return parseRef(ref);
  } catch (error) {
    if (error instanceof CliExitError) return null;
    throw error;
  }
}

/** The config key of a parsed ref: its name and tag without the `@place`. */
const repoKey = (parsed: ParsedRef): string =>
  parsed.tag ? `${parsed.name}:${parsed.tag}` : parsed.name;

function repoState(repo: { grandGuid?: string; repositoryGuid: string }): RepoState {
  return repo.grandGuid && repo.grandGuid !== repo.repositoryGuid ? 'fork' : 'grand';
}

/** Resolve a typed target into the plain data `decide` reads. */
export async function resolveTarget(input: TargetRef): Promise<DecisionTarget> {
  const { ref } = input;
  const parsed = ref ? tryParseRef(ref) : null;
  const machine = parsed?.place ?? input.machine;
  const base = {
    ...(machine ? { machine } : {}),
    ...(input.subject ? { subject: input.subject } : {}),
  };
  if (!ref) return { ...base, isOpsVm: await isOpsVmMachine(machine) };

  // The policy's `repos` globs and the opt-in lists name a repo without its `@place`.
  const key = parsed ? repoKey(parsed) : ref;
  const repo = parsed ? await configService.getRepository(key) : undefined;
  if (!repo) {
    return {
      ...base,
      repo: { name: key, state: 'unresolved' },
      isOpsVm: await isOpsVmMachine(machine),
    };
  }
  return {
    ...base,
    repo: { name: key, state: repoState(repo) },
    isOpsVm: await isOpsVmPlacement(repo.placement),
  };
}
