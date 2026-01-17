import { Flex, Typography } from 'antd';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createVersionColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { buildPoolMenuItems } from '@/features/ceph/utils/menuItems';
import { createSorter } from '@/platform';
import {
  DatabaseOutlined,
  DeleteOutlined,
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  RightOutlined,
} from '@/utils/optimizedIcons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephPools_ResultSet1 } from '@rediacc/shared/types';
import type { ColumnsType } from 'antd/es/table';

interface BuildPoolColumnsParams {
  t: TypedTFunction;
  expandedRowKeys: string[];
  onEditPool: (pool: GetCephPools_ResultSet1) => void;
  onDeletePool: (pool: GetCephPools_ResultSet1) => void;
  onRunFunction: (pool: GetCephPools_ResultSet1 & { preselectedFunction?: string }) => void;
  onShowAuditTrace: (pool: GetCephPools_ResultSet1) => void;
}

export const buildPoolColumns = ({
  t,
  expandedRowKeys,
  onEditPool,
  onDeletePool,
  onRunFunction,
  onShowAuditTrace,
}: BuildPoolColumnsParams): ColumnsType<GetCephPools_ResultSet1> => {
  return [
    {
      title: t('pools.poolName'),
      dataIndex: 'poolName',
      key: 'poolName',
      ellipsis: true,
      sorter: createSorter<GetCephPools_ResultSet1>('poolName'),
      render: (name: string, record: GetCephPools_ResultSet1) => {
        const isExpanded = expandedRowKeys.includes(record.poolGuid ?? '');
        return (
          <Flex align="center" className="inline-flex">
            <RightOutlined className={`expand-icon ${isExpanded ? 'expand-icon-rotated' : ''}`} />
            <DatabaseOutlined />
            <Typography.Text>{name}</Typography.Text>
          </Flex>
        );
      },
    },
    {
      ...createVersionColumn<GetCephPools_ResultSet1>({
        title: t('common:general.vaultVersion'),
        dataIndex: 'vaultVersion',
        key: 'vaultVersion',
        width: 140,
        sorter: createSorter<GetCephPools_ResultSet1>('vaultVersion'),
        formatVersion: (version: number) => t('common:general.versionFormat', { version }),
      }),
      responsive: RESPONSIVE_HIDE_XS,
    },
    createActionColumn<GetCephPools_ResultSet1>({
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
              dropdownItems: buildPoolMenuItems(t),
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
};
