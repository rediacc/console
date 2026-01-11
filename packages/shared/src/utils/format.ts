/**
 * Text formatting utilities
 */

/**
 * Unescape literal escape sequences in log output.
 * Go loggers often escape newlines/tabs in msg= fields.
 */
export function unescapeLogOutput(text: string): string {
  return text
    .replaceAll('\\r\\n', '\n')
    .replaceAll('\\n', '\n')
    .replaceAll('\\r', '\r')
    .replaceAll('\\t', '\t');
}
