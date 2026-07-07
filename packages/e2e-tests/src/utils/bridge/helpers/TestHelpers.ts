import * as fs from 'node:fs';
import * as path from 'node:path';
import type { ExecResult } from '../types';

/**
 * Test helper utilities for BridgeTestRunner.
 * Contains output parsing, validation, and fixture operations.
 */
export class TestHelpers {
  /**
   * Get combined output (stdout + stderr) from result.
   * Useful for checking output that may be in either stream.
   */
  getCombinedOutput(result: ExecResult): string {
    return (result.stdout + result.stderr).toLowerCase();
  }

  /**
   * Check if result has no shell syntax errors.
   * @deprecated Use hasValidCommandSyntax() for syntax tests, isSuccess() for execution tests
   */
  hasNoSyntaxErrors(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return (
      !output.includes('syntax error') &&
      !output.includes('unexpected token') &&
      !output.includes('bash:')
    );
  }

  /**
   * Check if command was built with valid syntax and flags.
   * Use this for "should not have shell syntax errors" tests.
   *
   * Checks for CLI/syntax errors:
   * - Shell syntax errors (bash parsing)
   * - Unknown CLI flags
   * - Missing required CLI flags
   *
   * Does NOT fail on runtime errors like:
   * - "repository not found" (requires actual data)
   * - "network ID not detected" (requires environment)
   */
  hasValidCommandSyntax(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return (
      !output.includes('syntax error') &&
      !output.includes('unexpected token') &&
      !output.includes('bash:') &&
      !output.includes('unknown flag') &&
      !output.includes('required flag') &&
      !output.includes('unknown function')
    );
  }

  /**
   * Check if command executed successfully.
   * Checks: exit code 0, no "unknown function" error, no fatal errors.
   */
  isSuccess(result: ExecResult): boolean {
    if (result.code !== 0) {
      return false;
    }
    const output = this.getCombinedOutput(result);
    // Match renet-specific error format (starts with time=), not third-party logs like Docker daemon
    const hasRenetError = /^time="[^"]*" level=(error|fatal)/m.test(output);
    return (
      !output.includes('unknown function') &&
      !hasRenetError &&
      !output.includes('syntax error') &&
      !output.includes('unexpected token') &&
      !output.includes('bash:')
    );
  }

  /**
   * Check if function is not implemented (for documenting which functions need work).
   */
  isNotImplemented(result: ExecResult): boolean {
    const output = this.getCombinedOutput(result);
    return output.includes('unknown function') || output.includes('not implemented');
  }

  /**
   * Get error message from result.
   */
  getErrorMessage(result: ExecResult): string {
    const output = result.stdout + result.stderr;
    const fatalRegex = /level=fatal msg="([^"]+)"/;
    const fatalMatch = fatalRegex.exec(output);
    if (fatalMatch) {
      return fatalMatch[1];
    }
    const errorRegex = /level=error msg="([^"]+)"/;
    const errorMatch = errorRegex.exec(output);
    if (errorMatch) {
      return errorMatch[1];
    }
    if (result.code !== 0) {
      return `Exit code: ${result.code}`;
    }
    return '';
  }

  /**
   * Read a fixture file from e2e/fixtures directory.
   * Useful for loading Rediaccfile, docker-compose.yaml, etc.
   */
  readFixture(relativePath: string): string {
    const fixturesPath = path.join(__dirname, '../../../..', 'fixtures');
    return fs.readFileSync(path.join(fixturesPath, relativePath), 'utf-8');
  }
}
