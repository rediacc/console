import React from 'react';
import { Table } from 'antd';
import { useTranslation } from 'react-i18next';
import { MachineRepoTable } from '@/components/resources/MachineRepoTable';
import type { Machine } from '@/types';
import { buildMachineTableColumns } from './columns';
import { TableContainer, ExpandedRowContent } from './styles';
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
      <ExpandedRowContent>
        <MachineRepoTable machine={machine} refreshKey={refreshKeys[machine.machineName]} />
      </ExpandedRowContent>
    ),
    [refreshKeys]
  );

  return (
    <TableContainer>
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
          rowExpandable: (machine) => machine.queueCount > 0,
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
    </TableContainer>
  );
};

export default FilterableMachineTable;
