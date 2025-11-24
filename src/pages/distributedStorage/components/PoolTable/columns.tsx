import type { ColumnsType } from 'antd/es/table'
import type { TFunction } from 'i18next'
import { Dropdown } from 'antd'
import {
  EditOutlined,
  FunctionOutlined,
  HistoryOutlined,
  DeleteOutlined,
} from '@/utils/optimizedIcons'
import type { DistributedStoragePool } from '@/api/queries/distributedStorage'
import { createSorter } from '@/core'
import { getPoolFunctionMenuItems } from './menus'
import {
  PoolNameCell,
  ExpandIcon,
  PoolIcon,
  PoolNameText,
  VersionTag,
  ActionButton,
  ActionsContainer,
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
  {
    title: t('common:table.actions'),
    key: 'actions',
    width: 320,
    render: (_: unknown, record: DistributedStoragePool) => (
      <ActionsContainer>
        <ActionButton
          type="primary"
          size="small"
          icon={<EditOutlined />}
          onClick={() => onEditPool(record)}
          data-testid={`ds-pool-edit-${record.poolName}`}
        >
          {t('common:actions.edit')}
        </ActionButton>
        <Dropdown
          menu={{
            items: getPoolFunctionMenuItems(t),
            onClick: ({ key }) => {
              if (key === 'advanced') {
                onRunFunction(record)
              } else {
                onRunFunction({
                  ...record,
                  preselectedFunction: key,
                })
              }
            },
          }}
          trigger={['click']}
        >
          <ActionButton
            type="primary"
            size="small"
            icon={<FunctionOutlined />}
            data-testid={`ds-pool-function-dropdown-${record.poolName}`}
          >
            {t('common:actions.remote')}
          </ActionButton>
        </Dropdown>
        <ActionButton
          type="default"
          size="small"
          icon={<HistoryOutlined />}
          onClick={() => onShowAuditTrace(record)}
          data-testid={`ds-pool-trace-${record.poolName}`}
        >
          {t('common:actions.trace')}
        </ActionButton>
        <ActionButton
          type="primary"
          danger
          size="small"
          icon={<DeleteOutlined />}
          onClick={() => onDeletePool(record)}
          data-testid={`ds-pool-delete-${record.poolName}`}
        >
          {t('common:actions.delete')}
        </ActionButton>
      </ActionsContainer>
    ),
  },
]
