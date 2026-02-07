/**
 * High-level wrappers for common E2E local operations.
 *
 * Combines runLocalFunction() + assertSuccess() for cleaner test code.
 */
import { type CliResult } from './CliTestRunner';
import { assertSuccess, runLocalFunction } from './local';

interface RunOptions {
  contextName?: string;
  params?: Record<string, string>;
  debug?: boolean;
  timeout?: number;
}

/**
 * Run a renet function and assert it succeeds (exit code 0).
 */
export async function runAndAssert(
  fn: string,
  machine: string,
  options?: RunOptions
): Promise<CliResult> {
  const result = await runLocalFunction(fn, machine, options);
  assertSuccess(result, `${fn} on ${machine} failed`);
  return result;
}

/**
 * Create a repository on a machine.
 */
export async function createRepo(
  machine: string,
  repoName: string,
  size: string,
  contextName?: string
): Promise<CliResult> {
  return runAndAssert('repository_create', machine, {
    contextName,
    params: { repository: repoName, size },
    timeout: 300_000,
  });
}

/**
 * Delete a repository on a machine. Does not throw on failure.
 */
export function deleteRepo(
  machine: string,
  repoName: string,
  contextName?: string
): Promise<CliResult> {
  return runLocalFunction('repository_delete', machine, {
    contextName,
    params: { repository: repoName },
    timeout: 300_000,
  });
}

/**
 * Safely clean up a repository — ignores errors (for afterAll blocks).
 */
export async function safeDeleteRepo(
  machine: string,
  repoName: string,
  contextName?: string
): Promise<void> {
  try {
    // Try to bring down the repo first (unmount + close LUKS)
    await runLocalFunction('repository_down', machine, {
      contextName,
      params: { repository: repoName },
      timeout: 120_000,
    });
  } catch {
    // ignore
  }
  try {
    await runLocalFunction('repository_delete', machine, {
      contextName,
      params: { repository: repoName },
      timeout: 120_000,
    });
  } catch {
    // ignore
  }
}
