/**
 * Export utilities for CSV and JSON file generation
 */

import dayjs from 'dayjs';

/**
 * Escape a value for CSV format
 * @param value - The value to escape
 * @returns Escaped string suitable for CSV
 */
export function escapeCSVValue(value: unknown): string {
  if (value == null) return '';
  const str = String(value);
  // Escape double quotes and wrap in quotes if contains special chars
  if (str.includes(',') || str.includes('"') || str.includes('\n') || str.includes('\r')) {
    return `"${str.replace(/"/g, '""')}"`;
  }
  return `"${str}"`;
}

/**
 * Build CSV content from headers and rows
 * @param headers - Array of header strings
 * @param rows - Array of row arrays
 * @returns CSV formatted string
 */
export function buildCSVContent(headers: string[], rows: unknown[][]): string {
  const headerRow = headers.join(',');
  const dataRows = rows.map((row) => row.map(escapeCSVValue).join(','));
  return [headerRow, ...dataRows].join('\n');
}

/**
 * Download content as a file
 * @param content - The content to download
 * @param filename - The filename for the download
 * @param mimeType - The MIME type of the content
 */
function downloadFile(content: string | Blob, filename: string, mimeType: string): void {
  const blob = content instanceof Blob ? content : new Blob([content], { type: mimeType });
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.setAttribute('download', filename);
  document.body.appendChild(link);
  link.click();
  document.body.removeChild(link);
  URL.revokeObjectURL(url);
}

/**
 * Download data as a CSV file
 * @param content - CSV content string
 * @param filename - Filename (without extension)
 */
export function downloadCSV(content: string, filename: string): void {
  downloadFile(content, `${filename}.csv`, 'text/csv;charset=utf-8;');
}

/**
 * Download data as a JSON file
 * @param data - Data to export as JSON
 * @param filename - Filename (without extension)
 * @param pretty - Whether to pretty-print the JSON (default: true)
 */
export function downloadJSON(data: unknown, filename: string, pretty: boolean = true): void {
  const content = pretty ? JSON.stringify(data, null, 2) : JSON.stringify(data);
  downloadFile(content, `${filename}.json`, 'application/json');
}

/**
 * Generate a timestamped filename
 * @param prefix - Filename prefix
 * @param extension - File extension (without dot)
 * @returns Filename with timestamp
 */
export function generateTimestampedFilename(prefix: string, extension: string): string {
  const timestamp = dayjs().format('YYYY-MM-DD_HH-mm-ss');
  return `${prefix}_${timestamp}.${extension}`;
}
