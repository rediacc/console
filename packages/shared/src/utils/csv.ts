/**
 * CSV utilities for data export
 */

/**
 * Escape a value for CSV format
 * Handles null/undefined, double quotes, commas, and newlines
 *
 * @param value - The value to escape
 * @returns Escaped string suitable for CSV
 */
export function escapeCSVValue(value: unknown): string {
  if (value == null) return '';
  const str = String(value);
  // Escape double quotes and wrap in quotes if contains special chars
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replaceAll('"', '""')}"`;
  }
  return `"${str}"`;
}

/**
 * Build CSV content from headers and rows
 *
 * @param headers - Array of header strings
 * @param rows - Array of row arrays
 * @returns CSV formatted string
 */
export function buildCSVContent(headers: string[], rows: unknown[][]): string {
  const headerRow = headers.join(',');
  const dataRows = rows.map((row) => row.map(escapeCSVValue).join(','));
  return [headerRow, ...dataRows].join('\n');
}
