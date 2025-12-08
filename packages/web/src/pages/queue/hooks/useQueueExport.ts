import dayjs from 'dayjs';
import { useExportData, type ExportColumn } from '@/hooks/useExportData';
import type { GetTeamQueueItems_ResultSet1 as QueueItem } from '@rediacc/shared/types';

/**
 * Queue-specific export hook that uses the shared useExportData hook
 *
 * @param items - Queue items to export
 * @returns handleExport function to export in CSV or JSON format
 */
export const useQueueExport = (items: QueueItem[]) => {
  // Define queue-specific columns for CSV export
  const columns: ExportColumn<QueueItem>[] = [
    { key: 'taskId', header: 'Task ID' },
    { key: 'healthStatus', header: 'Status' },
    { key: 'priorityLabel', header: 'Priority', format: (val) => String(val || '') },
    { key: 'ageInMinutes', header: 'Age (minutes)' },
    { key: 'teamName', header: 'Team' },
    { key: 'machineName', header: 'Machine' },
    { key: 'regionName', header: 'Region' },
    { key: 'bridgeName', header: 'Bridge' },
    { key: 'hasResponse', header: 'Has Response', format: (val) => (val ? 'Yes' : 'No') },
    { key: 'retryCount', header: 'Retry Count', format: (val) => String(val || 0) },
    { key: 'createdBy', header: 'Created By', format: (val) => String(val || '') },
    { key: 'createdTime', header: 'Created' },
  ];

  // Generate timestamped filename
  const timestamp = dayjs().format('YYYY-MM-DD_HH-mm-ss');
  const filename = `queue_export_${timestamp}`;

  // Use shared export hook
  const { exportToCSV, exportToJSON } = useExportData({
    data: items,
    filename,
    columns,
  });

  /**
   * Handle export in the requested format
   * @param format - Export format ('csv' or 'json')
   */
  const handleExport = (format: 'csv' | 'json') => {
    if (format === 'csv') {
      exportToCSV();
    } else {
      exportToJSON();
    }
  };

  return { handleExport };
};
