import { CliApiError } from '../services/api.js';
import { AuthError } from '../services/auth.js';
import { outputService } from '../services/output.js';
import { EXIT_CODES } from '../types/index.js';

export function handleError(error: unknown): never {
  let message: string;
  let exitCode: number = EXIT_CODES.GENERAL_ERROR;

  if (error instanceof CliApiError) {
    message = error.message;
    exitCode = error.exitCode;
  } else if (error instanceof AuthError) {
    message = error.message;
    exitCode = error.exitCode;
  } else if (error instanceof Error) {
    message = error.message;
  } else {
    message = String(error);
  }

  outputService.error(`Error: ${message}`);
  process.exit(exitCode);
}
