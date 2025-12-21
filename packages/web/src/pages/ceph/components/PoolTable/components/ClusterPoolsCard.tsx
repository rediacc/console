import React from 'react';
import { Card, Flex, Table, Tag, Typography } from 'antd';
import type { CephPool } from '@/api/queries/ceph';
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
  t,
}) => {
  const clusterPoolKeys = pools.map((pool) => pool.poolGuid || '').filter(Boolean);
  const activeKeys = expandedRowKeys.filter((key) => clusterPoolKeys.includes(key));

  return (
    <Card
      key={clusterName}
      title={
        <Flex align="center" gap={8} wrap>
          <CloudServerOutlined style={{ fontSize: 16, color: 'var(--ant-color-primary)' }} />
          <Typography.Text style={{ fontWeight: 600 }}>
            {t('pools.clusterPrefix')}: {clusterName}
          </Typography.Text>
          {teamName && (
            <Tag bordered={false} color="processing">
              {teamName}
            </Tag>
          )}
        </Flex>
      }
    >
      <Flex style={{ overflow: 'hidden' }}>
        <Table<CephPool>
          columns={columns}
          dataSource={pools}
          rowKey="poolGuid"
          loading={loading}
          scroll={{ x: 'max-content' }}
          pagination={false}
          data-testid={`ds-pool-table-${clusterName}`}
          expandable={{
            expandedRowRender,
            expandedRowKeys: activeKeys,
            onExpandedRowsChange: (keys) => onExpandedRowsChange(clusterPoolKeys, keys as string[]),
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
          rowClassName={() => 'pool-row'}
        />
      </Flex>
    </Card>
  );
};
