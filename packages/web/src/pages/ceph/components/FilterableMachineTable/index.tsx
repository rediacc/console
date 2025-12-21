import React from 'react';
import { Table } from 'antd';
import { useTranslation } from 'react-i18next';
import { MachineRepositoryTable } from '@/components/resources/MachineRepositoryTable';
import type { Machine } from '@/types';
import { buildMachineTableColumns } from './columns';
import type { TableRowSelection } from 'antd/es/table/interface';

export interface FilterableMachineTableProps {
  machines: Machine[];
  loading?: boolean;
  selectedRowKeys?: string[];
  onSelectionChange?: (keys: string[]) => void;
  showSelection?: boolean;
  expandedRowKeys?: string[];
  onExpandedRowsChange?: (keys: string[]) => void;
  refreshKeys?: Record<string, number>;
}

export const FilterableMachineTable: React.FC<FilterableMachineTableProps> = ({
  machines,
  loading = false,
  selectedRowKeys = [],
  onSelectionChange,
  showSelection = false,
  expandedRowKeys = [],
  onExpandedRowsChange,
  refreshKeys = {},
}) => {
  const { t } = useTranslation(['machines', 'ceph']);

  const columns = React.useMemo(() => buildMachineTableColumns(t), [t]);

  const rowSelection = React.useMemo<TableRowSelection<Machine> | undefined>(() => {
    if (!showSelection) {
      return undefined;
    }

    return {
      selectedRowKeys,
      onChange: (keys) => {
        onSelectionChange?.(keys.map(String));
      },
    };
  }, [showSelection, selectedRowKeys, onSelectionChange]);

  const handleExpandedRowsChange = React.useCallback(
    (keys: readonly React.Key[]) => {
      onExpandedRowsChange?.(keys.map(String));
    },
    [onExpandedRowsChange]
  );

  const renderExpandedRow = React.useCallback(
    (machine: Machine) => (
      <div>
        <MachineRepositoryTable machine={machine} refreshKey={refreshKeys[machine.machineName]} />
      </div>
    ),
    [refreshKeys]
  );

  return (
    <div style={{ width: '100%', overflow: 'hidden' }}>
      <Table<Machine>
        columns={columns}
        dataSource={machines}
        rowKey="machineName"
        loading={loading}
        rowSelection={rowSelection}
        data-testid="ds-machines-table"
        expandable={{
          expandedRowKeys,
          onExpandedRowsChange: onExpandedRowsChange ? handleExpandedRowsChange : undefined,
          expandedRowRender: renderExpandedRow,
          rowExpandable: (machine) => (machine.queueCount ?? 0) > 0,
        }}
        scroll={{ x: 800 }}
        pagination={{
          showSizeChanger: true,
          showTotal: (total: number, range: [number, number]) =>
            t('machines:showingMachines', {
              start: range[0],
              end: range[1],
              total,
            }),
        }}
      />
    </div>
  );
};

export default FilterableMachineTable;
