import type { ExecResult } from '../types';
/**
 * Test helper utilities for BridgeTestRunner.
 * Contains output parsing, validation, and fixture operations.
 */
export declare class TestHelpers {
    /**
     * Get combined output (stdout + stderr) from result.
     * Useful for checking output that may be in either stream.
     */
    getCombinedOutput(result: ExecResult): string;
    /**
     * Check if result has no shell syntax errors.
     * @deprecated Use hasValidCommandSyntax() for syntax tests, isSuccess() for execution tests
     */
    hasNoSyntaxErrors(result: ExecResult): boolean;
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
    hasValidCommandSyntax(result: ExecResult): boolean;
    /**
     * Check if command executed successfully.
     * Checks: exit code 0, no "unknown function" error, no fatal errors.
     */
    isSuccess(result: ExecResult): boolean;
    /**
     * Check if function is not implemented (for documenting which functions need work).
     */
    isNotImplemented(result: ExecResult): boolean;
    /**
     * Get error message from result.
     */
    getErrorMessage(result: ExecResult): string;
    /**
     * Read a fixture file from e2e/fixtures directory.
     * Useful for loading Rediaccfile, docker-compose.yaml, etc.
     */
    readFixture(relativePath: string): string;
}
//# sourceMappingURL=TestHelpers.d.ts.map
