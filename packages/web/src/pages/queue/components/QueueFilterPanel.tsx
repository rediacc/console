import React from 'react';
import { Space } from 'antd';
import { useTranslation } from 'react-i18next';
import { RediaccCheckbox } from '@/components/ui';
import { FilterInput, FilterRangePicker, FilterSelect } from '@/styles/primitives';
import { SearchOutlined } from '@/utils/optimizedIcons';
import type { Dayjs } from 'dayjs';

interface DropdownData {
  teams?: Array<{ label: string; value: string }>;
  machines?: string[];
  regions?: Array<{ label: string; value: string }>;
  bridges?: Array<{ label: string; value: string }>;
}

export interface QueueFilterValues {
  teamName: string;
  machineName: string;
  regionName: string;
  bridgeName: string;
  statusFilter: string[];
  dateRange: [Dayjs | null, Dayjs | null] | null;
  taskIdFilter: string;
  onlyStale: boolean;
  includeCompleted: boolean;
  includeCancelled: boolean;
}

interface QueueFilterPanelProps {
  filters: QueueFilterValues;
  dropdownData?: DropdownData;
  onFilterChange: <K extends keyof QueueFilterValues>(key: K, value: QueueFilterValues[K]) => void;
  onStatusFilterChange: (values: Array<string | number>, options: unknown) => void;
  onDateRangeChange: (
    dates: [Dayjs | null, Dayjs | null] | null,
    dateStrings?: [string, string]
  ) => void;
}

export const QueueFilterPanel: React.FC<QueueFilterPanelProps> = ({
  filters,
  dropdownData,
  onFilterChange,
  onStatusFilterChange,
  onDateRangeChange,
}) => {
  const { t } = useTranslation(['queue']);

  const dateRangeValue: [Dayjs | null, Dayjs | null] | undefined = filters.dateRange ?? undefined;

  return (
    <Space size={8} wrap>
      <FilterSelect
        $minWidth={150}
        placeholder={t('filters.teamPlaceholder')}
        value={filters.teamName || undefined}
        onChange={(value) => {
          const nextValue = typeof value === 'string' ? value : '';
          onFilterChange('teamName', nextValue);
          onFilterChange('machineName', '');
        }}
        allowClear
        options={dropdownData?.teams || []}
        data-testid="queue-filter-team"
      />
      <FilterSelect
        $minWidth={150}
        placeholder={t('filters.machinePlaceholder')}
        value={filters.machineName || undefined}
        onChange={(value) => onFilterChange('machineName', typeof value === 'string' ? value : '')}
        allowClear
        options={(dropdownData?.machines || []).map((machine) => ({
          label: machine,
          value: machine,
        }))}
        data-testid="queue-filter-machine"
      />
      <FilterSelect
        $minWidth={130}
        placeholder={t('filters.regionPlaceholder')}
        value={filters.regionName || undefined}
        onChange={(value) => onFilterChange('regionName', typeof value === 'string' ? value : '')}
        allowClear
        options={dropdownData?.regions || []}
        data-testid="queue-filter-region"
      />
      <FilterSelect
        $minWidth={130}
        placeholder={t('filters.bridgePlaceholder')}
        value={filters.bridgeName || undefined}
        onChange={(value) => onFilterChange('bridgeName', typeof value === 'string' ? value : '')}
        allowClear
        options={dropdownData?.bridges || []}
        data-testid="queue-filter-bridge"
      />
      <FilterRangePicker
        value={dateRangeValue}
        onChange={onDateRangeChange}
        allowClear
        placeholder={[t('queue:filters.dateFrom'), t('queue:filters.dateTo')]}
        data-testid="queue-filter-date"
      />
      <FilterSelect
        mode="multiple"
        $minWidth={160}
        placeholder={t('filters.statusPlaceholder')}
        value={filters.statusFilter}
        onChange={onStatusFilterChange}
        options={[
          { label: t('queue:statusPending'), value: 'PENDING' },
          { label: t('queue:statusActive'), value: 'ACTIVE' },
          { label: t('queue:statusStale'), value: 'STALE' },
          { label: t('queue:statusCompleted'), value: 'COMPLETED' },
          { label: t('queue:statusCancelled'), value: 'CANCELLED' },
          { label: t('queue:statusFailed'), value: 'FAILED' },
        ]}
        data-testid="queue-filter-status"
      />
      <FilterInput
        placeholder={t('filters.taskIdPlaceholder')}
        prefix={<SearchOutlined />}
        value={filters.taskIdFilter}
        onChange={(e) => onFilterChange('taskIdFilter', e.target.value)}
        allowClear
        data-testid="queue-filter-task"
      />
      <RediaccCheckbox
        checked={filters.onlyStale}
        onChange={(e) => onFilterChange('onlyStale', e.target.checked)}
        data-testid="queue-checkbox-only-stale"
      >
        {t('queue:filters.onlyStale')}
      </RediaccCheckbox>
    </Space>
  );
};
