import * as path from 'node:path';
import { fileURLToPath } from 'node:url';
import { execa, type Options } from 'execa';
import { loadGlobalState } from '../base/globalState.js';
import {
  CLI_BUNDLE_PATH,
  DEFAULT_CLI_TIMEOUT,
  DEFAULT_OUTPUT_FORMAT,
  getApiUrl,
  getCliTimeout,
} from '../constants.js';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);

/**
 * Result of a CLI command execution
 */
export interface CliResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  json: unknown;
  success: boolean;
}

/**
 * Options for running CLI commands
 */
export interface RunOptions {
  /** Override the default JSON output format */
  outputFormat?: 'json' | 'table' | 'yaml' | 'csv';
  /** Timeout in milliseconds */
  timeout?: number;
  /** Skip JSON parsing (for commands that don't output JSON) */
  skipJsonParse?: boolean;
  /** Override context for this command */
  context?: string;
}

/**
 * Configuration for CliTestRunner
 */
export interface RunnerConfig {
  /** API endpoint URL */
  apiUrl: string;
  /** CLI context name */
  context?: string;
  /** Default timeout in ms */
  timeout?: number;
  /** Test credentials */
  credentials?: {
    email: string;
    password: string;
    /** Master password for vault encryption (separate from login password) */
    masterPassword?: string;
  };
}

/**
 * CLI test runner for executing rediacc CLI commands.
 *
 * Provides:
 * - CLI execution wrapper with output parsing
 * - Test context management
 * - Domain-specific helper methods
 * - Error assertion helpers
 *
 * Usage:
 * ```typescript
 * const runner = CliTestRunner.withContext("test-context");
 * const result = await runner.teamList();
 * expect(runner.isSuccess(result)).toBe(true);
 * ```
 */
export class CliTestRunner {
  public config: RunnerConfig;
  private readonly cliDir: string;

  constructor(config: Partial<RunnerConfig> = {}) {
    this.config = {
      apiUrl: config.apiUrl ?? getApiUrl(),
      context: config.context,
      timeout: config.timeout ?? getCliTimeout(),
      credentials: config.credentials,
    };
    // CLI package root (tests/src/utils -> tests/src -> tests -> cli)
    this.cliDir = path.resolve(__dirname, '../../..');
  }

  /**
   * Factory: Create runner with specified context
   */
  static withContext(contextName: string): CliTestRunner {
    return new CliTestRunner({ context: contextName });
  }

  /**
   * Factory: Create runner with credentials
   */
  static withCredentials(email: string, password: string): CliTestRunner {
    return new CliTestRunner({
      credentials: { email, password },
    });
  }

  /**
   * Factory: Create runner from global test state (set by global setup).
   * This is the recommended way to get a runner in tests.
   */
  static fromGlobalState(): CliTestRunner {
    const state = loadGlobalState();
    return new CliTestRunner({
      context: state.contextName,
      apiUrl: state.apiUrl,
      credentials: {
        email: state.email,
        password: state.password,
        masterPassword: state.masterPassword,
      },
    });
  }

  // ===========================================================================
  // Core CLI Execution
  // ===========================================================================

  /**
   * Execute a CLI command and return the result.
   * Logs command and output to console for Playwright to capture.
   */
  async run(args: string[], options: RunOptions = {}): Promise<CliResult> {
    const outputFormat = options.outputFormat ?? DEFAULT_OUTPUT_FORMAT;
    const timeout = options.timeout ?? this.config.timeout ?? DEFAULT_CLI_TIMEOUT;
    const context = options.context ?? this.config.context;

    // Build args: context flag (if available), output format, then user args
    const contextArgs = context ? ['--config', context] : [];
    const fullArgs = [CLI_BUNDLE_PATH, ...contextArgs, '--output', outputFormat, ...args];

    // Log command for Playwright capture
    console.warn(`\n[CLI] ${args.join(' ')}`);

    const execaOptions: Options = {
      cwd: this.cliDir,
      timeout,
      env: {
        ...process.env,
        REDIACC_API_URL: this.config.apiUrl,
        // Provide master password for vault operations (non-interactive mode)
        // Use separate masterPassword if available, fall back to login password for backward compatibility
        REDIACC_MASTER_PASSWORD:
          this.config.credentials?.masterPassword ??
          this.config.credentials?.password ??
          process.env.CLI_MASTER_PASSWORD ??
          '',
        // Enable experimental commands (cloud-only commands are experimental)
        REDIACC_EXPERIMENTAL: '1',
        // Force no color for easier parsing
        NO_COLOR: '1',
        FORCE_COLOR: '0',
      },
      reject: false, // Don't throw on non-zero exit codes
    };

    const result = await execa('node', fullArgs, execaOptions);

    const stdout = String(result.stdout ?? '');
    const stderr = String(result.stderr ?? '');
    const exitCode = result.exitCode ?? 0;

    // Log output for Playwright capture
    if (stdout.trim()) {
      console.warn(`[STDOUT]\n${stdout}`);
    }
    if (stderr.trim()) {
      console.warn(`[STDERR]\n${stderr}`);
    }
    console.warn(`[EXIT] ${exitCode}`);

    return {
      stdout,
      stderr,
      exitCode,
      json: options.skipJsonParse ? null : this.tryParseJson(stdout),
      success: exitCode === 0,
    };
  }

  // ===========================================================================
  // Auth Commands
  // ===========================================================================

  async login(email?: string, password?: string): Promise<CliResult> {
    const e = email ?? this.config.credentials?.email ?? '';
    const p = password ?? this.config.credentials?.password ?? '';
    return this.run(['auth', 'login', '--endpoint', this.config.apiUrl, '-e', e, '-p', p]);
  }

  async logout(): Promise<CliResult> {
    return this.run(['auth', 'logout']);
  }

  async register(org: string, email: string, password: string, plan?: string): Promise<CliResult> {
    const args = [
      'auth',
      'register',
      '--organization',
      org,
      '-e',
      email,
      '-p',
      password,
      '--endpoint',
      this.config.apiUrl,
    ];
    if (plan) {
      args.push('--plan', plan);
    }
    return this.run(args);
  }

  async activate(email: string, password: string, code = 'AAA111'): Promise<CliResult> {
    return this.run([
      'auth',
      'activate',
      '-e',
      email,
      '-p',
      password,
      '--code',
      code,
      '--endpoint',
      this.config.apiUrl,
    ]);
  }

  async authStatus(): Promise<CliResult> {
    return this.run(['auth', 'status'], { skipJsonParse: true });
  }

  // ===========================================================================
  // Config Commands
  // ===========================================================================

  async contextCreate(name: string): Promise<CliResult> {
    return this.run(['config', 'init', name, '--api-url', this.config.apiUrl]);
  }

  async contextDelete(name: string): Promise<CliResult> {
    return this.run(['config', 'delete', name]);
  }

  async contextList(): Promise<CliResult> {
    return this.run(['config', 'list']);
  }

  // ===========================================================================
  // Team Commands
  // ===========================================================================

  async teamList(): Promise<CliResult> {
    return this.run(['team', 'list']);
  }

  async teamCreate(name: string): Promise<CliResult> {
    return this.run(['team', 'create', name]);
  }

  async teamDelete(name: string): Promise<CliResult> {
    return this.run(['team', 'delete', name, '--force']);
  }

  async teamRename(oldName: string, newName: string): Promise<CliResult> {
    return this.run(['team', 'rename', oldName, newName]);
  }

  async teamMemberList(teamName: string): Promise<CliResult> {
    return this.run(['team', 'member', 'list', teamName]);
  }

  async teamMemberAdd(teamName: string, email: string): Promise<CliResult> {
    return this.run(['team', 'member', 'add', teamName, email]);
  }

  async teamMemberRemove(teamName: string, email: string): Promise<CliResult> {
    return this.run(['team', 'member', 'remove', teamName, email]);
  }

  // ===========================================================================
  // Machine Commands
  // ===========================================================================

  async machineList(teamName: string): Promise<CliResult> {
    return this.run(['machine', 'list', '--team', teamName]);
  }

  async machineCreate(name: string, teamName: string, bridgeName: string): Promise<CliResult> {
    return this.run(['machine', 'create', name, '--team', teamName, '--bridge', bridgeName]);
  }

  async machineDelete(name: string, teamName: string): Promise<CliResult> {
    return this.run(['machine', 'delete', name, '--team', teamName, '--force']);
  }

  async machineHealth(machineName: string, teamName: string): Promise<CliResult> {
    return this.run(['machine', 'health', machineName, '--team', teamName]);
  }

  // ===========================================================================
  // Region Commands
  // ===========================================================================

  async regionList(): Promise<CliResult> {
    return this.run(['region', 'list']);
  }

  async regionCreate(name: string): Promise<CliResult> {
    return this.run(['region', 'create', name]);
  }

  async regionDelete(name: string): Promise<CliResult> {
    return this.run(['region', 'delete', name, '--force']);
  }

  // ===========================================================================
  // Bridge Commands
  // ===========================================================================

  async bridgeList(regionName: string): Promise<CliResult> {
    return this.run(['bridge', 'list', '--region', regionName]);
  }

  async bridgeCreate(name: string, regionName: string): Promise<CliResult> {
    return this.run(['bridge', 'create', name, '--region', regionName]);
  }

  async bridgeDelete(name: string, regionName: string): Promise<CliResult> {
    return this.run(['bridge', 'delete', name, '--region', regionName, '--force']);
  }

  // ===========================================================================
  // Repository Commands
  // ===========================================================================

  async repositoryList(teamName: string): Promise<CliResult> {
    return this.run(['repository', 'list', '--team', teamName]);
  }

  async repositoryCreate(name: string, teamName: string, machineName: string): Promise<CliResult> {
    return this.run(['repository', 'create', name, '--team', teamName, '--machine', machineName]);
  }

  async repositoryDelete(name: string, teamName: string): Promise<CliResult> {
    return this.run(['repository', 'delete', name, '--team', teamName, '--force']);
  }

  // ===========================================================================
  // Storage Commands
  // ===========================================================================

  async storageList(): Promise<CliResult> {
    return this.run(['storage', 'list']);
  }

  async storageCreate(name: string): Promise<CliResult> {
    return this.run(['storage', 'create', name]);
  }

  async storageDelete(name: string): Promise<CliResult> {
    return this.run(['storage', 'delete', name, '--force']);
  }

  // ===========================================================================
  // Queue Commands
  // ===========================================================================

  async queueList(
    teamName: string,
    options?: { status?: string; limit?: number }
  ): Promise<CliResult> {
    const args = ['queue', 'list', '--team', teamName];
    if (options?.status) args.push('--status', options.status);
    if (options?.limit) args.push('--limit', String(options.limit));
    return this.run(args);
  }

  async queueTrace(taskId: string): Promise<CliResult> {
    return this.run(['queue', 'trace', taskId]);
  }

  async queueCancel(taskId: string): Promise<CliResult> {
    return this.run(['queue', 'cancel', taskId]);
  }

  async queueRetry(taskId: string): Promise<CliResult> {
    return this.run(['queue', 'retry', taskId]);
  }

  // ===========================================================================
  // User Commands
  // ===========================================================================

  async userList(): Promise<CliResult> {
    return this.run(['user', 'list']);
  }

  async userCreate(email: string, password: string): Promise<CliResult> {
    return this.run(['user', 'create', email, '-p', password]);
  }

  async userDeactivate(email: string): Promise<CliResult> {
    return this.run(['user', 'deactivate', email, '--force']);
  }

  // ===========================================================================
  // Organization Commands
  // ===========================================================================

  async organizationGet(): Promise<CliResult> {
    return this.run(['organization', 'info']);
  }

  async organizationRename(newName: string): Promise<CliResult> {
    return this.run(['organization', 'rename', newName]);
  }

  // ===========================================================================
  // Audit Commands
  // ===========================================================================

  async auditList(options?: { limit?: number }): Promise<CliResult> {
    const args = ['audit', 'list'];
    if (options?.limit) args.push('--limit', String(options.limit));
    return this.run(args);
  }

  // ===========================================================================
  // Permission Commands
  // ===========================================================================

  async permissionList(): Promise<CliResult> {
    return this.run(['permission', 'list']);
  }

  // ===========================================================================
  // VS Code Commands
  // ===========================================================================

  /**
   * Check VS Code installation status
   * @param insiders - Check for VS Code Insiders variant
   */
  async vscodeCheck(insiders?: boolean): Promise<CliResult> {
    const args = ['vscode', 'check'];
    if (insiders) args.push('--insiders');
    return this.run(args, { skipJsonParse: true });
  }

  /**
   * List VS Code SSH connections
   */
  async vscodeList(): Promise<CliResult> {
    return this.run(['vscode', 'list'], { skipJsonParse: true });
  }

  /**
   * Cleanup VS Code SSH configurations
   * @param all - Remove all connections
   * @param connection - Remove specific connection by name
   */
  async vscodeCleanup(all?: boolean, connection?: string): Promise<CliResult> {
    const args = ['vscode', 'cleanup'];
    if (all) args.push('--all');
    if (connection) args.push('-c', connection);
    return this.run(args, { skipJsonParse: true });
  }

  /**
   * Connect to a machine via VS Code Remote SSH
   * @param teamName - Team name
   * @param machineName - Machine name
   * @param options - Additional connection options
   */
  async vscodeConnect(
    teamName: string,
    machineName: string,
    options?: {
      repository?: string;
      folder?: string;
      urlOnly?: boolean;
      newWindow?: boolean;
      skipEnvSetup?: boolean;
      insiders?: boolean;
    }
  ): Promise<CliResult> {
    const args = ['vscode', 'connect', '--team', teamName, '--machine', machineName];
    if (options?.repository) args.push('-r', options.repository);
    if (options?.folder) args.push('-f', options.folder);
    if (options?.urlOnly) args.push('--url-only');
    if (options?.newWindow) args.push('-n');
    if (options?.skipEnvSetup) args.push('--skip-env-setup');
    if (options?.insiders) args.push('--insiders');
    return this.run(args, { skipJsonParse: true });
  }

  // ===========================================================================
  // Ceph Commands
  // ===========================================================================

  async cephClusterStatus(): Promise<CliResult> {
    return this.run(['ceph', 'cluster', 'status']);
  }

  async cephPoolList(): Promise<CliResult> {
    return this.run(['ceph', 'pool', 'list']);
  }

  async cephPoolCreate(name: string): Promise<CliResult> {
    return this.run(['ceph', 'pool', 'create', name]);
  }

  async cephImageList(poolName: string): Promise<CliResult> {
    return this.run(['ceph', 'image', 'list', '--pool', poolName]);
  }

  async cephSnapshotList(poolName: string, imageName: string): Promise<CliResult> {
    return this.run(['ceph', 'snapshot', 'list', '--pool', poolName, '--image', imageName]);
  }

  async cephCloneList(
    poolName: string,
    imageName: string,
    snapshotName: string
  ): Promise<CliResult> {
    return this.run([
      'ceph',
      'clone',
      'list',
      '--pool',
      poolName,
      '--image',
      imageName,
      '--snapshot',
      snapshotName,
    ]);
  }

  // ===========================================================================
  // Utility Methods
  // ===========================================================================

  /**
   * Get CLI version
   */
  async version(): Promise<CliResult> {
    return this.run(['--version'], { skipJsonParse: true });
  }

  // ===========================================================================
  // Assertion Helpers
  // ===========================================================================

  /**
   * Check if result indicates success (exit code 0)
   */
  isSuccess(result: CliResult): boolean {
    return result.success && result.exitCode === 0;
  }

  /**
   * Get combined output (stdout + stderr) for logging
   */
  getCombinedOutput(result: CliResult): string {
    return [result.stdout, result.stderr].filter(Boolean).join('\n');
  }

  /**
   * Type guard to check if JSON result is a valid error response object.
   */
  private isJsonErrorResponse(
    json: unknown
  ): json is { success: false; error: { code?: string; message?: string; details?: string[] } } {
    if (!json || typeof json !== 'object' || Array.isArray(json)) {
      return false;
    }
    const obj = json as { success?: boolean; error?: unknown };
    return obj.success === false && typeof obj.error === 'object' && obj.error !== null;
  }

  /**
   * Format error message from structured error object.
   */
  private formatJsonError(error: { code?: string; message?: string; details?: string[] }): string {
    const { code, message, details } = error;
    let errorMsg = message ?? 'Unknown error';
    if (code) {
      errorMsg = `[${code}] ${errorMsg}`;
    }
    if (details?.length) {
      errorMsg += ` - Details: ${details.join(', ')}`;
    }
    return errorMsg;
  }

  /**
   * Extract error message from CLI result.
   * Handles both JSON error format and plain text.
   */
  getErrorMessage(result: CliResult): string {
    if (this.isJsonErrorResponse(result.json)) {
      return this.formatJsonError(result.json.error);
    }

    return result.stderr || result.stdout || 'No error details available';
  }

  /**
   * Assert CLI command succeeded and returned a JSON array.
   * Throws descriptive error if command failed or returned non-array.
   */
  expectSuccessArray<T = unknown>(result: CliResult): T[] {
    if (!result.success) {
      throw new Error(
        `CLI command failed (exit ${result.exitCode}): ${this.getErrorMessage(result)}`
      );
    }
    if (!Array.isArray(result.json)) {
      const preview = JSON.stringify(result.json).slice(0, 200);
      throw new Error(
        `Expected JSON array but got ${typeof result.json}: ${preview}\n` +
          `stdout: ${result.stdout.slice(0, 500)}`
      );
    }
    return result.json as T[];
  }

  /**
   * Assert CLI command succeeded and returned a JSON object.
   * Throws descriptive error if command failed or returned non-object.
   */
  expectSuccessObject<T = Record<string, unknown>>(result: CliResult): T {
    if (!result.success) {
      throw new Error(
        `CLI command failed (exit ${result.exitCode}): ${this.getErrorMessage(result)}`
      );
    }
    if (result.json === null || typeof result.json !== 'object' || Array.isArray(result.json)) {
      const preview = JSON.stringify(result.json).slice(0, 200);
      throw new Error(
        `Expected JSON object but got ${typeof result.json}: ${preview}\n` +
          `stdout: ${result.stdout.slice(0, 500)}`
      );
    }
    return result.json as T;
  }

  /**
   * Assert CLI command succeeded (exit code 0).
   * Throws descriptive error if command failed.
   */
  expectSuccess(result: CliResult): void {
    if (!result.success) {
      throw new Error(
        `CLI command failed (exit ${result.exitCode}): ${this.getErrorMessage(result)}`
      );
    }
  }

  // ===========================================================================
  // Private Helpers
  // ===========================================================================

  /**
   * Try to parse JSON from CLI output.
   * Handles spinner output by finding JSON array or object.
   */
  private tryParseJson(str: string): unknown {
    if (!str.trim()) return null;

    // First try direct parse
    try {
      return JSON.parse(str);
    } catch {
      // Continue to regex extraction
    }

    // Try to extract JSON array or object from output
    try {
      const arrayMatch = /\[[\s\S]*\]/.exec(str);
      if (arrayMatch) {
        return JSON.parse(arrayMatch[0]);
      }

      const objectMatch = /\{[\s\S]*\}/.exec(str);
      if (objectMatch) {
        return JSON.parse(objectMatch[0]);
      }
    } catch {
      // JSON extraction failed
    }

    return null;
  }
}
