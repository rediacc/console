/**
 * Console Color Utilities
 *
 * ANSI color codes for terminal output.
 * Colors are automatically disabled when stdout is not a TTY.
 */

const isTTY = process.stdout.isTTY;

export const RED = isTTY ? '\x1b[31m' : '';
export const GREEN = isTTY ? '\x1b[32m' : '';
export const YELLOW = isTTY ? '\x1b[33m' : '';
export const BLUE = isTTY ? '\x1b[34m' : '';
export const DIM = isTTY ? '\x1b[2m' : '';
export const NC = isTTY ? '\x1b[0m' : ''; // No Color (reset)
