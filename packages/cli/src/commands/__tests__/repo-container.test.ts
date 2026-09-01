/**
 * `repo exec` / `repo logs`: argument fidelity, output passthrough, exit codes.
 *
 * These verbs had NO tests, which is how three defects lived in ~40 lines of
 * code at once: output was discarded by the executor's default handler, argv was
 * flattened with `join(' ')` so the container's shell re-split it, and the
 * "verbatim exit code" contract in the file header was never true end to end.
 * The quoting case below is the regression test for the one that silently ran a
 * DIFFERENT command than the operator typed.
 */

import { Command } from 'commander';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import type { ExecuteOptions } from '../../services/executor/types.js';

const execute = vi.fn((_options: ExecuteOptions) =>
  Promise.resolve({ success: true, exitCode: 0, allSteps: [] })
);

vi.mock('../../services/executor/executor-factory.js', () => ({
  getExecutor: () => ({ execute }),
}));
vi.mock('../../utils/repo-target.js', () => ({
  resolveRepoRef: (ref: string) =>
    Promise.resolve({ repoKey: ref, machineName: 'm1', kubeCluster: undefined }),
}));
vi.mock('../../utils/command-policy.js', () => ({
  assertCommandPolicy: vi.fn(() => Promise.resolve()),
  CMD: { REPO_EXEC: 'repo exec' },
}));
vi.mock('../../services/core/output.js', () => ({
  outputService: { info: vi.fn(), success: vi.fn(), warn: vi.fn() },
}));

const handleError = vi.fn();
vi.mock('../../utils/errors.js', async (orig) => ({
  ...(await orig<Record<string, unknown>>()),
  handleError: (e: unknown) => handleError(e),
}));

import { registerRepoContainerCommands } from '../repo-container.js';

/** Drive the real Commander tree, so argv parsing is exercised, not simulated. */
async function run(argv: string[]): Promise<void> {
  const repo = new Command('repo');
  repo.exitOverride();
  registerRepoContainerCommands(repo);
  await repo.parseAsync(['node', 'repo', ...argv]);
}

function lastParams(): Record<string, unknown> {
  const call = execute.mock.calls.at(-1)?.[0] as unknown as { params: Record<string, unknown> };
  return call.params;
}

function lastOptions(): Record<string, unknown> {
  return execute.mock.calls.at(-1)?.[0] as unknown as Record<string, unknown>;
}

beforeEach(() => {
  execute.mockClear();
  handleError.mockClear();
  execute.mockResolvedValue({ success: true, exitCode: 0, allSteps: [] });
  process.exitCode = undefined;
});

describe('repo exec argument quoting', () => {
  it('quotes each argv element separately', async () => {
    await run(['exec', 'shop', '-c', 'web', '--', 'ls', '-la']);
    expect(lastParams().command).toBe("'ls' '-la'");
  });

  it('keeps a quoted argument as ONE word for the container shell', async () => {
    // The bug: `cmd.join(' ')` produced `sh -c echo A B`, so the inner shell read
    // `echo` as the script and `A`/`B` as $0/$1, printing an empty line.
    await run(['exec', 'shop', '-c', 'web', '--', 'sh', '-c', 'echo A B']);
    expect(lastParams().command).toBe("'sh' '-c' 'echo A B'");
  });

  it('escapes embedded single quotes', async () => {
    await run(['exec', 'shop', '-c', 'web', '--', 'echo', "it's"]);
    expect(lastParams().command).toBe("'echo' 'it'\\''s'");
  });

  it('neutralizes shell metacharacters in a single argument', async () => {
    await run(['exec', 'shop', '-c', 'web', '--', 'echo', '; rm -rf /']);
    expect(lastParams().command).toBe("'echo' '; rm -rf /'");
  });
});

describe('output passthrough', () => {
  it('is requested by repo exec', async () => {
    await run(['exec', 'shop', '-c', 'web', '--', 'whoami']);
    expect(lastOptions().passthroughOutput).toBe(true);
  });

  it('is requested by repo logs', async () => {
    await run(['logs', 'shop', '-c', 'web']);
    expect(lastOptions().passthroughOutput).toBe(true);
  });
});

describe('repo exec exit codes', () => {
  it('propagates a non-zero remote exit code verbatim', async () => {
    execute.mockResolvedValue({ success: false, exitCode: 7, allSteps: [] });
    await run(['exec', 'shop', '-c', 'web', '--', 'sh', '-c', 'exit 7']);
    expect(process.exitCode).toBe(7);
    expect(handleError).not.toHaveBeenCalled();
  });

  it('treats a dispatch failure (exitCode 0, success false) as an error', async () => {
    execute.mockResolvedValue({ success: false, exitCode: 0, allSteps: [] });
    await run(['exec', 'shop', '-c', 'web', '--', 'whoami']);
    expect(handleError).toHaveBeenCalled();
  });
});

describe('repo logs options', () => {
  it('passes follow and timestamps through', async () => {
    await run(['logs', 'shop', '-c', 'web', '--follow', '--timestamps']);
    expect(lastParams().follow).toBe(true);
    expect(lastParams().timestamps).toBe(true);
  });

  it('rejects a non-positive --lines without dispatching', async () => {
    await run(['logs', 'shop', '-c', 'web', '--lines', '0']);
    expect(execute).not.toHaveBeenCalled();
    expect(handleError).toHaveBeenCalled();
  });

  it('rejects a non-numeric --lines without dispatching', async () => {
    await run(['logs', 'shop', '-c', 'web', '--lines', 'abc']);
    expect(execute).not.toHaveBeenCalled();
    expect(handleError).toHaveBeenCalled();
  });
});
