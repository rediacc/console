import { Flex, Typography } from 'antd';
import type { CephPool } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn, createVersionColumn } from '@/components/common/columns';
import { createSorter } from '@/platform';
import {
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  RightOutlined,
  DatabaseOutlined,
} from '@/utils/optimizedIcons';
import { getPoolFunctionMenuItems } from './menus';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BuildPoolColumnsParams {
  t: TFunction<'ceph' | 'common'>;
  expandedRowKeys: string[];
  onEditPool: (pool: CephPool) => void;
  onDeletePool: (pool: CephPool) => void;
  onRunFunction: (pool: CephPool & { preselectedFunction?: string }) => void;
  onShowAuditTrace: (pool: CephPool) => void;
}

export const buildPoolColumns = ({
  t,
  expandedRowKeys,
  onEditPool,
  onDeletePool,
  onRunFunction,
  onShowAuditTrace,
}: BuildPoolColumnsParams): ColumnsType<CephPool> => [
  {
    title: t('pools.poolName'),
    dataIndex: 'poolName',
    key: 'poolName',
    ellipsis: true,
    sorter: createSorter<CephPool>('poolName'),
    render: (name: string, record: CephPool) => {
      const isExpanded = expandedRowKeys.includes(record.poolGuid || '');
      return (
        <Flex align="center" gap={8} style={{ display: 'inline-flex' }}>
          <RightOutlined
            style={{
              transform: isExpanded ? 'rotate(90deg)' : undefined,
              transition: 'transform 0.2s ease',
            }}
          />
          <DatabaseOutlined style={{ fontSize: 16, color: 'var(--ant-color-primary)' }} />
          <Typography.Text style={{ fontWeight: 400 }}>{name}</Typography.Text>
        </Flex>
      );
    },
  },
  createVersionColumn<CephPool>({
    title: t('common:general.vaultVersion'),
    dataIndex: 'vaultVersion',
    key: 'vaultVersion',
    width: 140,
    sorter: createSorter<CephPool>('vaultVersion'),
    formatVersion: (version: number) => t('common:general.versionFormat', { version }),
  }),
  createActionColumn<CephPool>({
    width: 320,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'edit',
            icon: <EditOutlined />,
            tooltip: 'common:actions.edit',
            label: 'common:actions.edit',
            onClick: () => onEditPool(record),
          },
          {
            type: 'function-dropdown',
            icon: <FunctionOutlined />,
            tooltip: 'common:actions.remote',
            label: 'common:actions.remote',
            dropdownItems: getPoolFunctionMenuItems(t),
            onDropdownClick: (key) => {
              if (key === 'advanced') {
                onRunFunction(record);
              } else {
                onRunFunction({ ...record, preselectedFunction: key });
              }
            },
          },
          {
            type: 'trace',
            icon: <HistoryOutlined />,
            tooltip: 'common:actions.trace',
            label: 'common:actions.trace',
            onClick: () => onShowAuditTrace(record),
            variant: 'default',
          },
          {
            type: 'delete',
            icon: <DeleteOutlined />,
            tooltip: 'common:actions.delete',
            label: 'common:actions.delete',
            onClick: () => onDeletePool(record),
            danger: true,
          },
        ]}
        record={record}
        idField="poolName"
        testIdPrefix="ds-pool"
        t={t}
      />
    ),
  }),
];
