import { useCallback, useState } from 'react';
import { downloadCSV, downloadJSON, escapeCSVValue } from '@/platform/utils/export';
import { showMessage } from '@/utils/messages';

/**
 * Column definition for CSV export
 */
export interface ExportColumn<T> {
  /** Key or path to extract value from row data */
  key: string;
  /** Header label for the column */
  header: string;
  /** Optional formatter for the value */
  format?: (value: unknown, row: T) => string;
}

/**
 * Configuration options for useExportData hook
 */
export interface UseExportDataOptions<T> {
  /** Data to export */
  data: T[];
  /** Filename without extension */
  filename: string;
  /** Column definitions for CSV export */
  columns: ExportColumn<T>[];
  /** Callback after successful export */
  onSuccess?: (format: 'csv' | 'json') => void;
}

/**
 * Return value from useExportData hook
 */
export interface UseExportDataReturn {
  /** Export data as CSV file */
  exportToCSV: () => void;
  /** Export data as JSON file */
  exportToJSON: () => void;
  /** Whether an export is in progress */
  isExporting: boolean;
}

/**
 * Hook for exporting data to CSV or JSON formats
 *
 * Provides a reusable interface for exporting tabular data with proper
 * CSV escaping, custom formatters, and file download handling.
 *
 * @example
 * const { exportToCSV, exportToJSON, isExporting } = useExportData({
 *   data: queueItems,
 *   filename: `queue-export-${Date.now()}`,
 *   columns: [
 *     { key: 'taskId', header: 'Task ID' },
 *     { key: 'status', header: 'Status' },
 *     { key: 'createdAt', header: 'Created', format: (v) => formatDate(v) },
 *   ],
 *   onSuccess: (format) => console.log(`Exported as ${format}`),
 * });
 *
 * @template T - Type of data being exported
 * @param options - Configuration options
 * @returns Export functions and state
 */
export function useExportData<T extends object>(
  options: UseExportDataOptions<T>
): UseExportDataReturn {
  const { data, filename, columns, onSuccess } = options;
  const [isExporting, setIsExporting] = useState(false);

  /**
   * Extract value from row using column key
   * Supports nested keys with dot notation (e.g., 'user.name')
   */
  const extractValue = useCallback((row: T, key: string): unknown => {
    if (typeof key === 'string' && key.includes('.')) {
      // Handle nested keys
      const parts = key.split('.');
      let value: unknown = row;
      for (const part of parts) {
        value =
          value && typeof value === 'object' ? (value as Record<string, unknown>)[part] : undefined;
      }
      return value;
    }
    return row[key as keyof T];
  }, []);

  /**
   * Export data as CSV file
   */
  const exportToCSV = useCallback(() => {
    setIsExporting(true);
    try {
      // Build headers
      const headers = columns.map((col) => col.header);

      // Build rows with optional formatting
      const rows = data.map((row) =>
        columns.map((col) => {
          const value = extractValue(row, col.key);
          const formattedValue = col.format ? col.format(value, row) : value;
          return escapeCSVValue(formattedValue);
        })
      );

      // Join headers and rows
      const csvContent = [headers.join(','), ...rows.map((row) => row.join(','))].join('\n');

      // Download file
      downloadCSV(csvContent, filename);

      // Show success message
      showMessage('success', `Exported ${data.length} items to ${filename}.csv`);

      // Call success callback
      onSuccess?.('csv');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to export CSV';
      showMessage('error', `Export failed: ${errorMessage}`);
    } finally {
      setIsExporting(false);
    }
  }, [data, filename, columns, onSuccess, extractValue]);

  /**
   * Export data as JSON file
   */
  const exportToJSON = useCallback(() => {
    setIsExporting(true);
    try {
      // Download pretty-printed JSON
      downloadJSON(data, filename, true);

      // Show success message
      showMessage('success', `Exported ${data.length} items to ${filename}.json`);

      // Call success callback
      onSuccess?.('json');
    } catch (error) {
      const errorMessage = error instanceof Error ? error.message : 'Failed to export JSON';
      showMessage('error', `Export failed: ${errorMessage}`);
    } finally {
      setIsExporting(false);
    }
  }, [data, filename, onSuccess]);

  return {
    exportToCSV,
    exportToJSON,
    isExporting,
  };
}
