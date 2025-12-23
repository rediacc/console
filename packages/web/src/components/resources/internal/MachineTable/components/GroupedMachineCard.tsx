import React, { type ReactNode } from 'react';
import { Card, Flex, Tag, Typography } from 'antd';
import { useTranslation } from 'react-i18next';
import ResourceListView from '@/components/common/ResourceListView';
import type { Machine } from '@/types';
import {
  BranchesOutlined,
  CloudServerOutlined,
  DashboardOutlined,
  GlobalOutlined,
  InboxOutlined,
  TeamOutlined,
} from '@/utils/optimizedIcons';
import type { ColumnsType, TableRowSelection } from 'antd/es/table/interface';

type GroupByMode = 'machine' | 'bridge' | 'team' | 'region' | 'repository' | 'status' | 'grand';

const iconMap: Record<GroupByMode, React.ReactNode> = {
  machine: null,
  bridge: <CloudServerOutlined />,
  team: <TeamOutlined />,
  region: <GlobalOutlined />,
  repository: <InboxOutlined />,
  status: <DashboardOutlined />,
  grand: <BranchesOutlined />,
};

interface GroupedMachineCardProps {
  groupKey: string;
  groupBy: GroupByMode;
  machines: Machine[];
  columns: ColumnsType<Machine>;
  mobileRender?: (record: Machine) => ReactNode;
  loading?: boolean;
  pageSize?: number;
  onRow?: (record: Machine) => React.HTMLAttributes<HTMLElement>;
  rowSelection?: TableRowSelection<Machine>;
}

export const GroupedMachineCard: React.FC<GroupedMachineCardProps> = ({
  groupKey,
  groupBy,
  machines,
  columns,
  mobileRender,
  loading = false,
  pageSize = 10,
  onRow,
  rowSelection,
}) => {
  const { t } = useTranslation(['machines', 'common']);

  return (
    <Card
      key={groupKey}
      title={
        <Flex align="center" gap={8} wrap>
          {iconMap[groupBy]}
          <Typography.Text strong>{groupKey}</Typography.Text>
          <Tag bordered={false}>
            {machines.length}{' '}
            {machines.length === 1 ? t('machines:machine') : t('machines:machines')}
          </Tag>
        </Flex>
      }
    >
      <Flex className="overflow-hidden">
        <ResourceListView<Machine>
          columns={columns}
          data={machines}
          rowKey="machineName"
          loading={loading}
          mobileRender={mobileRender}
          pagination={{
            pageSize,
            showSizeChanger: false,
            showTotal: (total, range) =>
              t('common:table.showingRecords', { start: range[0], end: range[1], total }),
          }}
          rowSelection={rowSelection}
          onRow={onRow}
          data-testid={`grouped-machine-table-${groupKey}`}
        />
      </Flex>
    </Card>
  );
};
