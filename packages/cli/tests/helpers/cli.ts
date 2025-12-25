import { execa, type Options } from 'execa';
import { getConfig } from './config.js';

export interface CliResult {
  stdout: string;
  stderr: string;
  exitCode: number;
  json: unknown | null;
  success: boolean;
}

export interface RunCliOptions {
  /** Override the default JSON output format */
  outputFormat?: 'json' | 'table' | 'yaml' | 'csv';
  /** Additional environment variables */
  env?: Record<string, string>;
  /** Timeout in milliseconds */
  timeout?: number;
  /** Skip JSON parsing */
  skipJsonParse?: boolean;
}

/**
 * Run a CLI command and return the result
 */
export async function runCli(args: string[], options: RunCliOptions = {}): Promise<CliResult> {
  const config = getConfig();

  // Build arguments with output format
  const outputFormat = options.outputFormat ?? 'json';
  const fullArgs = ['tsx', 'src/index.ts', '--output', outputFormat, ...args];

  const execaOptions: Options = {
    cwd: config.cliDir,
    timeout: options.timeout ?? config.timeout,
    env: {
      ...process.env,
      REDIACC_API_URL: config.apiUrl,
      // Provide master password for vault operations (non-interactive mode)
      REDIACC_MASTER_PASSWORD: config.password,
      // Force no color for easier parsing
      NO_COLOR: '1',
      FORCE_COLOR: '0',
      ...options.env,
    },
    reject: false, // Don't throw on non-zero exit codes
  };

  const result = await execa('npx', fullArgs, execaOptions);

  const stdout = result.stdout ?? '';
  const stderr = result.stderr ?? '';
  const exitCode = result.exitCode ?? 0;

  return {
    stdout,
    stderr,
    exitCode,
    json: options.skipJsonParse ? null : tryParseJson(stdout),
    success: exitCode === 0,
  };
}

/**
 * Run login command with test credentials
 */
export async function login(overrides?: {
  email?: string;
  password?: string;
  endpoint?: string;
}): Promise<CliResult> {
  const config = getConfig();

  return runCli([
    'login',
    '--endpoint',
    overrides?.endpoint ?? config.apiUrl,
    '-e',
    overrides?.email ?? config.email,
    '-p',
    overrides?.password ?? config.password,
  ]);
}

/**
 * Run logout command
 */
export async function logout(): Promise<CliResult> {
  return runCli(['logout']);
}

/**
 * Ensure the CLI is authenticated before running a test
 */
export async function ensureAuthenticated(): Promise<void> {
  const statusResult = await runCli(['auth', 'status'], { skipJsonParse: true });

  if (!statusResult.stdout.includes('Authenticated')) {
    const loginResult = await login();
    if (!loginResult.success) {
      throw new Error(`Failed to authenticate: ${getErrorMessage(loginResult)}`);
    }
  }
}

/**
 * Strip ANSI escape codes from string
 */
export function stripAnsi(str: string): string {
  // eslint-disable-next-line no-control-regex
  return str.replace(/\x1B\[[0-9;]*[a-zA-Z]/g, '');
}

/**
 * Try to parse JSON from CLI output
 * Handles spinner output by finding JSON array or object
 */
function tryParseJson(str: string): unknown | null {
  if (!str.trim()) return null;

  // First try direct parse
  try {
    return JSON.parse(str);
  } catch {
    // Continue to regex extraction
  }

  // Try to extract JSON array or object from output
  // This handles cases where spinner output is mixed with JSON
  try {
    // Look for array first (more common for list commands)
    const arrayMatch = str.match(/\[[\s\S]*\]/);
    if (arrayMatch) {
      return JSON.parse(arrayMatch[0]);
    }

    // Look for object
    const objectMatch = str.match(/\{[\s\S]*\}/);
    if (objectMatch) {
      return JSON.parse(objectMatch[0]);
    }
  } catch {
    // JSON extraction failed
  }

  return null;
}

/**
 * Assert that the result contains expected fields
 */
export function expectJsonArray(result: CliResult): unknown[] {
  if (!Array.isArray(result.json)) {
    throw new Error(`Expected JSON array, got: ${typeof result.json}`);
  }
  return result.json;
}

/**
 * Assert that the result is a JSON object
 */
export function expectJsonObject(result: CliResult): Record<string, unknown> {
  if (result.json === null || typeof result.json !== 'object' || Array.isArray(result.json)) {
    throw new Error(`Expected JSON object, got: ${typeof result.json}`);
  }
  return result.json as Record<string, unknown>;
}

/**
 * Extract error message from CLI result.
 * In JSON mode, errors are returned as structured JSON in stdout.
 * Returns a human-readable error string for logging.
 */
export function getErrorMessage(result: CliResult): string {
  // Check for JSON error response (new format)
  if (result.json && typeof result.json === 'object' && !Array.isArray(result.json)) {
    const jsonResult = result.json as {
      success?: boolean;
      error?: { code?: string; message?: string; details?: string[] };
    };
    if (jsonResult.success === false && jsonResult.error) {
      const { code, message, details } = jsonResult.error;
      let errorMsg = message ?? 'Unknown error';
      if (code) errorMsg = `[${code}] ${errorMsg}`;
      if (details?.length) errorMsg += ` - Details: ${details.join(', ')}`;
      return errorMsg;
    }
  }

  // Fallback to stderr/stdout
  return result.stderr || result.stdout || 'No error details available';
}
