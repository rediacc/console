/**
 * TOC public key install at schedule deploy (F6).
 *
 * Browse listings are sealed to a public key stored beside each repository. The key is derived from the repository
 * credential in the CLI (shared/backup/toc-key.ts), so the machine never needs the secret to receive it: only the
 * public line travels. For each repository a deploy covers, the machine is asked what it holds (`renet backup toc-key
 * status`); a missing key is installed, an equal one is left alone, and a different one is reported and never
 * overwritten. Replacing a different key is the explicit `--replace` path, the only one that sends the credential
 * (stdin of `install --password-stdin`), because renet proves the passphrase before it swaps a key.
 */

import { deriveTocPublicKeyLine } from '@rediacc/shared/backup/toc-key';
import type { RdcConfig } from '@rediacc/shared/config-schema';
import { shellQuote } from '../../utils/shell-quote.js';
import { type ScheduleUnitSpec, specRepoGuids } from './backup-schedule-targets.js';

/** Runs one command on the machine. The command string never carries a secret; `stdin` does only for --replace. */
export interface TocKeyTransport {
  run(command: string, stdin?: string): Promise<{ exitCode: number; stdout: string }>;
}

export interface TocKeyTarget {
  /** `name:tag`, for messages. */
  ref: string;
  guid: string;
  /** grandGuid, else the repository GUID. */
  lineage: string;
  credential?: string;
  /** Datastore path renet is pointed at. */
  datastore: string;
}

export type TocKeyOutcome =
  | 'installed'
  | 'replaced'
  | 'unchanged'
  | 'differs'
  | 'refused'
  | 'no-credential'
  | 'unreadable'
  | 'dry-run';

export interface TocKeyResult {
  ref: string;
  guid: string;
  outcome: TocKeyOutcome;
  detail?: string;
  /** The credential is shorter than the 32 characters `repo create` generates (decision O7: HKDF stays, the operator is told). */
  weakCredential: boolean;
}

/** `repo create` generates 24 random bytes as base64, 32 characters. */
const GENERATED_CREDENTIAL_LENGTH = 32;

interface TocKeyAnswer {
  outcome?: string;
  publicKey?: string;
  reason?: string;
}

function parseAnswer(stdout: string): TocKeyAnswer {
  const lines = stdout.split('\n').filter((l) => l.trim().startsWith('{'));
  const last = lines.at(-1);
  if (!last) return {};
  try {
    return JSON.parse(last) as TocKeyAnswer;
  } catch {
    return {};
  }
}

function tocKeyCommand(
  renetPath: string,
  action: 'status' | 'install',
  target: TocKeyTarget,
  extra: string[] = []
): string {
  return [
    'sudo',
    shellQuote(renetPath),
    'backup toc-key',
    action,
    '--datastore',
    shellQuote(target.datastore),
    '--repo',
    shellQuote(target.guid),
    ...extra,
  ].join(' ');
}

interface RepoIdentity {
  ref: string;
  lineage: string;
  credential?: string;
}

/** Every configured repository by GUID: its `name:tag` ref, lineage (grandGuid, else its own GUID) and credential. */
function repoIdentities(config: RdcConfig): Map<string, RepoIdentity> {
  const byGuid = new Map<string, RepoIdentity>();
  for (const [name, family] of Object.entries(config.resources?.repositories ?? {})) {
    for (const [tag, record] of Object.entries(family.tags)) {
      byGuid.set(record.repositoryGuid, {
        ref: `${name}:${tag}`,
        lineage: record.grandGuid ?? record.repositoryGuid,
        credential: record.credential,
      });
    }
  }
  return byGuid;
}

/** The repositories every unit of a deploy covers, once each per datastore, with the lineage and credential from the config. */
export function tocKeyTargetsFor(
  config: RdcConfig,
  machineName: string,
  specs: ScheduleUnitSpec[]
): TocKeyTarget[] {
  const byGuid = repoIdentities(config);
  const seen = new Set<string>();
  const targets: TocKeyTarget[] = [];
  for (const spec of specs) {
    for (const guid of specRepoGuids(spec, config, machineName)) {
      const key = `${spec.datastore.path}\n${guid}`;
      const known = byGuid.get(guid);
      if (seen.has(key) || !known) continue;
      seen.add(key);
      targets.push({ guid, datastore: spec.datastore.path, ...known });
    }
  }
  return targets.sort((a, b) => a.ref.localeCompare(b.ref));
}

const INSTALL_ANSWERS = new Set(['installed', 'replaced', 'unchanged', 'differs']);

/** Install (or, with --replace, swap) the key on the machine and read renet's answer. */
async function installOne(
  transport: TocKeyTransport,
  renetPath: string,
  target: TocKeyTarget,
  credential: string,
  line: string,
  replacing: boolean
): Promise<TocKeyAnswer & { exitCode: number }> {
  const flags = ['--lineage', shellQuote(target.lineage), '--public-key', shellQuote(line)];
  if (replacing) flags.push('--replace', '--password-stdin');
  const answer = await transport.run(
    tocKeyCommand(renetPath, 'install', target, flags),
    replacing ? credential : undefined
  );
  return { ...parseAnswer(answer.stdout), exitCode: answer.exitCode };
}

async function syncOne(
  transport: TocKeyTransport,
  renetPath: string,
  target: TocKeyTarget,
  replace: boolean
): Promise<TocKeyResult> {
  const base = { ref: target.ref, guid: target.guid };
  const { credential } = target;
  if (!credential) {
    return {
      ...base,
      outcome: 'no-credential',
      detail:
        'the config holds no credential for this repository, so no listing key can be derived',
      weakCredential: false,
    };
  }
  const weakCredential = credential.length < GENERATED_CREDENTIAL_LENGTH;
  const line = deriveTocPublicKeyLine(credential, target.lineage).trimEnd();
  const status = parseAnswer(
    (await transport.run(tocKeyCommand(renetPath, 'status', target))).stdout
  );
  const present = status.outcome === 'present';
  if (present && status.publicKey?.trimEnd() === line) {
    return { ...base, outcome: 'unchanged', weakCredential };
  }
  if (present && !replace) {
    return {
      ...base,
      outcome: 'differs',
      detail: 'the machine holds a different key; it was not overwritten',
      weakCredential,
    };
  }
  const answer = await installOne(
    transport,
    renetPath,
    target,
    credential,
    line,
    replace && present
  );
  if (answer.outcome && INSTALL_ANSWERS.has(answer.outcome)) {
    return {
      ...base,
      outcome: answer.outcome as TocKeyOutcome,
      detail: answer.reason,
      weakCredential,
    };
  }
  return {
    ...base,
    outcome: 'refused',
    detail: answer.reason ?? `renet exited ${answer.exitCode}`,
    weakCredential,
  };
}

/**
 * Compare and install the TOC public key of each target. A failure on one repository is that repository's
 * result, never an exception, so the rest of the deploy and the rest of the repositories proceed.
 */
export async function syncTocKeys(
  transport: TocKeyTransport,
  renetPath: string,
  targets: TocKeyTarget[],
  options: { replace?: boolean; dryRun?: boolean }
): Promise<TocKeyResult[]> {
  const results: TocKeyResult[] = [];
  for (const target of targets) {
    if (options.dryRun) {
      results.push({
        ref: target.ref,
        guid: target.guid,
        outcome: 'dry-run',
        weakCredential: false,
      });
      continue;
    }
    try {
      results.push(await syncOne(transport, renetPath, target, options.replace === true));
    } catch (error) {
      results.push({
        ref: target.ref,
        guid: target.guid,
        outcome: 'unreadable',
        detail: error instanceof Error ? error.message : String(error),
        weakCredential: false,
      });
    }
  }
  return results;
}

/** The message for one result that needs attention, or undefined for the silent outcomes. */
function attentionLine(r: TocKeyResult): string | undefined {
  switch (r.outcome) {
    case 'differs':
      return `Repository ${r.ref} (${r.guid}): the machine holds a TOC key that differs from the one this credential derives. Browse listings sealed under the old key keep opening only with the old credential. Not overwritten; to replace it: rdc backup toc-key sync ${r.ref} --replace`;
    case 'no-credential':
      return `Repository ${r.ref} (${r.guid}): no credential in the config, so no browse-listing key was installed and its backups get no file listing.`;
    case 'refused':
    case 'unreadable':
      return `Repository ${r.ref} (${r.guid}): the TOC key was not installed (${r.detail ?? r.outcome}).`;
    default:
      return undefined;
  }
}

/** The operator-facing lines for results that need attention. Silent for `unchanged` and `installed`. */
export function tocKeyWarnings(results: TocKeyResult[]): string[] {
  const lines: string[] = [];
  for (const r of results) {
    const line = attentionLine(r);
    if (line) lines.push(line);
    if (r.weakCredential && (r.outcome === 'installed' || r.outcome === 'replaced')) {
      lines.push(
        `Repository ${r.ref}: its credential is shorter than the ${GENERATED_CREDENTIAL_LENGTH} characters repo create generates. The listing key is derived with a fast hash, so a short hand-picked credential can be guessed offline from the public key; prefer a generated one.`
      );
    }
  }
  return lines;
}
