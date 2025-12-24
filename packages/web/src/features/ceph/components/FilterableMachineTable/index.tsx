import React from 'react';
import { Badge, Checkbox, Flex, Space, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import { ExpandIcon } from '@/components/common/ExpandIcon';
import { MobileCard } from '@/components/common/MobileCard';
import ResourceListView from '@/components/common/ResourceListView';
import MachineAssignmentStatusCell from '@/components/resources/MachineAssignmentStatusCell';
import { MachineRepositoryTable } from '@/components/resources/MachineRepositoryTable';
import type { Machine } from '@/types';
import { DesktopOutlined } from '@/utils/optimizedIcons';
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
      <Flex>
        <MachineRepositoryTable machine={machine} refreshKey={refreshKeys[machine.machineName]} />
      </Flex>
    ),
    [refreshKeys]
  );

  const handleToggleRow = React.useCallback(
    (machineName: string) => {
      if (!onExpandedRowsChange) return;
      if (expandedRowKeys.includes(machineName)) {
        onExpandedRowsChange(expandedRowKeys.filter((key) => key !== machineName));
      } else {
        onExpandedRowsChange([...expandedRowKeys, machineName]);
      }
    },
    [expandedRowKeys, onExpandedRowsChange]
  );

  const mobileRender = React.useMemo(
    // eslint-disable-next-line react/display-name
    () => (record: Machine) => {
      const isExpanded = expandedRowKeys.includes(record.machineName);
      const isSelected = selectedRowKeys.includes(record.machineName);
      const hasQueueItems = (record.queueCount ?? 0) > 0;

      const handleCheckboxChange = (e: React.MouseEvent) => {
        e.stopPropagation();
        if (!onSelectionChange) return;

        if (isSelected) {
          onSelectionChange(selectedRowKeys.filter((key) => key !== record.machineName));
        } else {
          onSelectionChange([...selectedRowKeys, record.machineName]);
        }
      };

      const actions = (
        <Space direction="vertical" align="end">
          <Badge count={record.queueCount ?? 0} showZero title={t('machines:queueItems')} />
        </Space>
      );

      return (
        <MobileCard
          onClick={hasQueueItems ? () => handleToggleRow(record.machineName) : undefined}
          actions={actions}
        >
          <Space>
            {showSelection && (
              <Typography.Text onClick={handleCheckboxChange}>
                <Checkbox checked={isSelected} />
              </Typography.Text>
            )}
            {hasQueueItems && <ExpandIcon isExpanded={isExpanded} />}
            <DesktopOutlined />
            <Typography.Text strong className="truncate">
              {record.machineName}
            </Typography.Text>
          </Space>
          <Flex gap={8} wrap align="center">
            {record.teamName && <Tag bordered={false}>{record.teamName}</Tag>}
            {record.bridgeName && (
              <Tag bordered={false} color="blue">
                {record.bridgeName}
              </Tag>
            )}
          </Flex>
          <Flex align="center" gap={8}>
            <MachineAssignmentStatusCell machine={record} />
          </Flex>
        </MobileCard>
      );
    },
    [t, expandedRowKeys, selectedRowKeys, showSelection, onSelectionChange, handleToggleRow]
  );

  return (
    <Flex className="w-full overflow-hidden">
      <ResourceListView<Machine>
        columns={columns}
        data={machines}
        rowKey="machineName"
        loading={loading}
        rowSelection={rowSelection}
        data-testid="ds-machines-table"
        mobileRender={mobileRender}
        expandable={{
          expandedRowKeys,
          onExpandedRowsChange: onExpandedRowsChange ? handleExpandedRowsChange : undefined,
          expandedRowRender: renderExpandedRow,
          rowExpandable: (machine: Machine) => (machine.queueCount ?? 0) > 0,
        }}
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
    </Flex>
  );
};

export default FilterableMachineTable;
