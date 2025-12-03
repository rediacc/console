import type { ColumnsType } from 'antd/es/table'
import type { TFunction } from 'i18next'
import {
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  DeleteOutlined,
} from '@/utils/optimizedIcons'
import type { DistributedStoragePool } from '@/api/queries/distributedStorage'
import { createSorter } from '@/core'
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup'
import { VersionTag, createActionColumn } from '@/components/common/columns'
import { getPoolFunctionMenuItems } from './menus'
import {
  PoolNameCell,
  ExpandIcon,
  PoolIcon,
  PoolNameText,
} from './styles'

interface BuildPoolColumnsParams {
  t: TFunction<'distributedStorage' | 'common'>
  expandedRowKeys: string[]
  onEditPool: (pool: DistributedStoragePool) => void
  onDeletePool: (pool: DistributedStoragePool) => void
  onRunFunction: (
    pool: DistributedStoragePool & { preselectedFunction?: string },
  ) => void
  onShowAuditTrace: (pool: DistributedStoragePool) => void
}

export const buildPoolColumns = ({
  t,
  expandedRowKeys,
  onEditPool,
  onDeletePool,
  onRunFunction,
  onShowAuditTrace,
}: BuildPoolColumnsParams): ColumnsType<DistributedStoragePool> => [
  {
    title: t('pools.poolName'),
    dataIndex: 'poolName',
    key: 'poolName',
    ellipsis: true,
    sorter: createSorter<DistributedStoragePool>('poolName'),
    render: (name: string, record: DistributedStoragePool) => {
      const isExpanded = expandedRowKeys.includes(record.poolGuid || '')
      return (
        <PoolNameCell>
          <ExpandIcon $expanded={isExpanded} />
          <PoolIcon />
          <PoolNameText>{name}</PoolNameText>
        </PoolNameCell>
      )
    },
  },
  {
    title: t('common:general.vaultVersion'),
    dataIndex: 'vaultVersion',
    key: 'vaultVersion',
    width: 140,
    align: 'center',
    sorter: createSorter<DistributedStoragePool>('vaultVersion'),
    render: (version: number) => (
      <VersionTag>
        {t('common:general.versionFormat', { version })}
      </VersionTag>
    ),
  },
  createActionColumn<DistributedStoragePool>({
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
                onRunFunction(record)
              } else {
                onRunFunction({ ...record, preselectedFunction: key })
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
]
