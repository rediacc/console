import React, { type ReactNode } from 'react';
import { Card, Flex, Tag, Typography } from 'antd';
import type { CephPool } from '@/api/queries/ceph';
import ResourceListView from '@/components/common/ResourceListView';
import { CloudServerOutlined } from '@/utils/optimizedIcons';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface ClusterPoolsCardProps {
  clusterName: string;
  teamName?: string;
  pools: CephPool[];
  loading: boolean;
  columns: ColumnsType<CephPool>;
  expandedRowKeys: string[];
  onExpandedRowsChange: (clusterKeys: string[], keys: string[]) => void;
  expandedRowRender: (pool: CephPool) => React.ReactNode;
  onToggleRow: (poolGuid?: string) => void;
  mobileRender?: (record: CephPool) => ReactNode;
  t: TFunction<'ceph' | 'common'>;
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
  const clusterPoolKeys = pools.map((pool) => pool.poolGuid || '').filter(Boolean);
  const activeKeys = expandedRowKeys.filter((key) => clusterPoolKeys.includes(key));

  return (
    <Card
      key={clusterName}
      title={
        <Flex align="center" gap={8} wrap>
          <CloudServerOutlined />
          <Typography.Text>
            {t('pools.clusterPrefix')}: {clusterName}
          </Typography.Text>
          {teamName && <Tag bordered={false}>{teamName}</Tag>}
        </Flex>
      }
    >
      <Flex className="overflow-hidden">
        <ResourceListView<CephPool>
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
