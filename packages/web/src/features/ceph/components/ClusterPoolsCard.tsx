import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephPools_ResultSet1 } from '@rediacc/shared/types';
import { Card, Flex, Tag, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import React, { type ReactNode } from 'react';
import ResourceListView from '@/components/common/ResourceListView';
import { CloudServerOutlined } from '@/utils/optimizedIcons';

interface ClusterPoolsCardProps {
  clusterName: string;
  teamName?: string;
  pools: GetCephPools_ResultSet1[];
  loading: boolean;
  columns: ColumnsType<GetCephPools_ResultSet1>;
  expandedRowKeys: string[];
  onExpandedRowsChange: (clusterKeys: string[], keys: string[]) => void;
  expandedRowRender: (pool: GetCephPools_ResultSet1) => React.ReactNode;
  onToggleRow: (poolGuid?: string) => void;
  mobileRender?: (record: GetCephPools_ResultSet1) => ReactNode;
  t: TypedTFunction;
}

export const ClusterPoolsCard: React.FC<ClusterPoolsCardProps> = ({
  clusterName,
  teamName,
  pools,
  loading,
  columns,
  expandedRowKeys,
  onExpandedRowsChange,
  expandedRowRender,
  onToggleRow,
  mobileRender,
  t,
}) => {
  const clusterPoolKeys = pools.map((pool) => pool.poolGuid ?? '').filter(Boolean);
  const activeKeys = expandedRowKeys.filter((key) => clusterPoolKeys.includes(key));

  return (
    <Card
      key={clusterName}
      title={
        <Flex align="center" wrap>
          <CloudServerOutlined />
          <Typography.Text>
            {t('pools.clusterPrefix')}: {clusterName}
          </Typography.Text>
          {teamName && <Tag bordered={false}>{teamName}</Tag>}
        </Flex>
      }
    >
      <Flex className="overflow-hidden">
        <ResourceListView<GetCephPools_ResultSet1>
          columns={columns}
          data={pools}
          rowKey="poolGuid"
          loading={loading}
          pagination={false}
          data-testid={`ds-pool-table-${clusterName}`}
          mobileRender={mobileRender}
          expandable={{
            expandedRowRender,
            expandedRowKeys: activeKeys,
            onExpandedRowsChange: (keys: readonly React.Key[]) =>
              onExpandedRowsChange(clusterPoolKeys, keys as string[]),
            expandIcon: () => null,
            expandRowByClick: false,
          }}
          onRow={(record) => ({
            'data-testid': `ds-pool-row-${record.poolName}`,
            onClick: (event) => {
              const target = event.target as HTMLElement;
              if (target.closest('button') || target.closest('.ant-dropdown-trigger')) {
                return;
              }
              onToggleRow(record.poolGuid ?? undefined);
            },
          })}
        />
      </Flex>
    </Card>
  );
};
