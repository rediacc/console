/**
 * TOC public key install at schedule deploy (F6).
 *
 * The transport is a recording fake of the machine's renet: it answers `toc-key status` and `toc-key install` in the
 * JSON shape private/renet/cmd/renet/backup_toc_key.go emits (tocKeyRecord). Every command and every stdin byte that
 * leaves the CLI is recorded, so "only the public line leaves" is asserted over the whole conversation.
 */

import { deriveTocPublicKeyLine } from '@rediacc/shared/backup/toc-key';
import { WK_DATASTORE_PATH } from '@rediacc/shared/config/well-known.generated';
import { describe, expect, it } from 'vitest';
import { machineUnitSpecs, type ScheduledStrategy } from '../backup/backup-schedule-targets.js';
import {
  syncTocKeys,
  type TocKeyTarget,
  type TocKeyTransport,
  tocKeyTargetsFor,
} from '../backup/backup-schedule-toc-key.js';

const RENET = '/usr/lib/rediacc/renet';
const G = '10000000-0000-4000-8000-000000000001';
const GRAND = '10000000-0000-4000-8000-0000000000aa';
const SECRET = 'S3cretCredentialValue0123456789abcdef';

const target = (over: Partial<TocKeyTarget> = {}): TocKeyTarget => ({
  ref: 'mail:latest',
  guid: G,
  lineage: GRAND,
  credential: SECRET,
  datastore: WK_DATASTORE_PATH,
  ...over,
});

const publicLine = deriveTocPublicKeyLine(SECRET, GRAND);

interface Call {
  command: string;
  stdin?: string;
}

/** What renet's `toc-key install` answers for a key against what the machine holds. */
function installOutcome(current: string | null, line: string, replace: boolean): string {
  if (current === null) return 'installed';
  if (current.trim() === line.trim()) return 'unchanged';
  return replace ? 'replaced' : 'differs';
}

/** A machine holding `stored` (or nothing). Install answers like renet: unchanged, differs, installed, replaced. */
function fakeMachine(stored: string | null) {
  const calls: Call[] = [];
  let current = stored;
  const answer = (exitCode: number, record: object) => ({
    exitCode,
    stdout: `${JSON.stringify({ guid: G, ...record })}\n`,
  });
  const status = () =>
    answer(0, {
      action: 'status',
      outcome: current === null ? 'absent' : 'present',
      publicKey: current ?? undefined,
    });
  const install = (command: string) => {
    const line = /--public-key '([^']+)'/.exec(command)?.[1] ?? '';
    const outcome = installOutcome(current, line, command.includes('--replace'));
    if (outcome === 'installed' || outcome === 'replaced') current = line;
    return answer(outcome === 'differs' ? 1 : 0, { action: 'install', outcome });
  };
  const transport: TocKeyTransport = {
    run(command, stdin) {
      calls.push({ command, stdin });
      return Promise.resolve(command.includes('toc-key status') ? status() : install(command));
    },
  };
  return { transport, calls, stored: () => current };
}

describe('syncTocKeys', () => {
  it('installs the derived public half when the machine has no key', async () => {
    const m = fakeMachine(null);
    const [r] = await syncTocKeys(m.transport, RENET, [target()], {});
    expect(r.outcome).toBe('installed');
    expect(m.stored()?.trim()).toBe(publicLine.trim());
    const install = m.calls.find((c) => c.command.includes('toc-key install'));
    expect(install?.command).toContain(`--lineage '${GRAND}'`);
    expect(install?.command).toContain(`--repo '${G}'`);
  });

  it('is silent and makes no write when the stored key equals the derived one', async () => {
    const m = fakeMachine(publicLine);
    const [r] = await syncTocKeys(m.transport, RENET, [target()], {});
    expect(r.outcome).toBe('unchanged');
    expect(m.calls.some((c) => c.command.includes('toc-key install'))).toBe(false);
  });

  it('reports a different key and never overwrites it without --replace', async () => {
    const other = deriveTocPublicKeyLine('another credential value', GRAND);
    const m = fakeMachine(other);
    const [r] = await syncTocKeys(m.transport, RENET, [target()], {});
    expect(r.outcome).toBe('differs');
    expect(m.stored()).toBe(other);
    expect(m.calls.some((c) => c.command.includes('--replace'))).toBe(false);
  });

  it('warns about a repository with no credential and installs nothing', async () => {
    const m = fakeMachine(null);
    const [r] = await syncTocKeys(m.transport, RENET, [target({ credential: undefined })], {});
    expect(r.outcome).toBe('no-credential');
    expect(m.calls).toHaveLength(0);
  });

  it('a dry run touches nothing, not even a read', async () => {
    const m = fakeMachine(null);
    const results = await syncTocKeys(m.transport, RENET, [target()], { dryRun: true });
    expect(m.calls).toHaveLength(0);
    expect(results[0].outcome).toBe('dry-run');
  });

  it('flags a credential shorter than the generated shape, still installing the key', async () => {
    const m = fakeMachine(null);
    const [r] = await syncTocKeys(m.transport, RENET, [target({ credential: 'short' })], {});
    expect(r.outcome).toBe('installed');
    expect(r.weakCredential).toBe(true);
    const [ok] = await syncTocKeys(fakeMachine(null).transport, RENET, [target()], {});
    expect(ok.weakCredential).toBe(false);
  });

  it('sends nothing but the public line: the credential appears in no command and no stdin of the deploy path', async () => {
    for (const stored of [null, publicLine, deriveTocPublicKeyLine('x', GRAND)]) {
      const m = fakeMachine(stored);
      await syncTocKeys(m.transport, RENET, [target()], {});
      for (const c of m.calls) {
        expect(c.command).not.toContain(SECRET);
        expect(c.stdin ?? '').not.toContain(SECRET);
        expect(c.stdin).toBeUndefined();
      }
    }
  });

  it('--replace carries the credential on stdin only, and only into the install verb', async () => {
    const m = fakeMachine(deriveTocPublicKeyLine('old credential value', GRAND));
    const [r] = await syncTocKeys(m.transport, RENET, [target()], { replace: true });
    expect(r.outcome).toBe('replaced');
    const withStdin = m.calls.filter((c) => c.stdin !== undefined);
    expect(withStdin).toHaveLength(1);
    expect(withStdin[0].stdin).toBe(SECRET);
    expect(withStdin[0].command).toContain('toc-key install');
    expect(withStdin[0].command).toContain('--password-stdin');
    expect(withStdin[0].command).not.toContain(SECRET);
  });

  it('one repository failing does not stop the next', async () => {
    const m = fakeMachine(null);
    const flaky: TocKeyTransport = {
      run(command, stdin) {
        if (command.includes(`'${G}'`)) return Promise.reject(new Error('ssh dropped'));
        return m.transport.run(command, stdin);
      },
    };
    const results = await syncTocKeys(
      flaky,
      RENET,
      [target(), target({ guid: '10000000-0000-4000-8000-000000000002', ref: 'b:latest' })],
      {}
    );
    expect(results.map((r) => r.outcome)).toEqual(['unreadable', 'installed']);
  });
});

describe('tocKeyTargetsFor', () => {
  const FORK = '10000000-0000-4000-8000-000000000002';
  const config = {
    resources: {
      machines: { m1: { ip: '10.0.0.1', user: 'u', datastore: WK_DATASTORE_PATH } },
      repositories: {
        mail: {
          placement: { machine: 'm1' },
          grand: 'latest',
          tags: {
            latest: { repositoryGuid: G, credential: SECRET },
            trial: { repositoryGuid: FORK, credential: SECRET, grandGuid: G },
          },
        },
      },
    },
  } as unknown as Parameters<typeof machineUnitSpecs>[1];
  const strategy: ScheduledStrategy = {
    destinations: [{ name: 'c', kind: 'hosted-service' }],
    schedule: '0 2 * * *',
  };

  it('takes the lineage from grandGuid, else the repository GUID, for every repo in scope', () => {
    const specs = machineUnitSpecs([{ name: 's', config: strategy }], config, 'm1');
    const targets = tocKeyTargetsFor(config, 'm1', specs);
    expect(targets.map((t) => [t.ref, t.lineage, t.datastore])).toEqual([
      ['mail:latest', G, WK_DATASTORE_PATH],
      ['mail:trial', G, WK_DATASTORE_PATH],
    ]);
    expect(targets[0].credential).toBe(SECRET);
  });
});
