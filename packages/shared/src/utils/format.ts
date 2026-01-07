/**
 * Text formatting utilities
 */

/**
 * Unescape literal escape sequences in log output.
 * Go loggers often escape newlines/tabs in msg= fields.
 */
export function unescapeLogOutput(text: string): string {
  return text
    .replace(/\\r\\n/g, '\n')
    .replace(/\\n/g, '\n')
    .replace(/\\r/g, '\r')
    .replace(/\\t/g, '\t');
}
