import type { ColumnsType } from 'antd/es/table'
import type { TFunction } from 'i18next'
import { Dropdown, Tooltip } from 'antd'
import {
  EditOutlined,
  DeleteOutlined,
  FunctionOutlined,
  HistoryOutlined,
} from '@/utils/optimizedIcons'
import type { DistributedStorageCluster } from '@/api/queries/distributedStorage'
import { createSorter } from '@/core'
import { MachineCountBadge } from './components/MachineCountBadge'
import { getClusterFunctionMenuItems } from './menus'
import {
  ClusterNameCell,
  ExpandIcon,
  ClusterIcon,
  ClusterNameText,
  TeamTag,
  VersionTag,
  ActionButton,
  ManageMachinesButton,
  ActionsContainer,
  MachineManageCell,
} from './styles'

interface BuildClusterColumnsParams {
  t: TFunction<'distributedStorage' | 'common' | 'machines'>
  expandedRowKeys: string[]
  onManageMachines: (cluster: DistributedStorageCluster) => void
  onEditCluster: (cluster: DistributedStorageCluster) => void
  onDeleteCluster: (cluster: DistributedStorageCluster) => void
  onRunFunction: (
    cluster: DistributedStorageCluster & { preselectedFunction?: string },
  ) => void
  onShowAuditTrace: (cluster: DistributedStorageCluster) => void
}

export const buildClusterColumns = ({
  t,
  expandedRowKeys,
  onManageMachines,
  onEditCluster,
  onDeleteCluster,
  onRunFunction,
  onShowAuditTrace,
}: BuildClusterColumnsParams): ColumnsType<DistributedStorageCluster> => [
  {
    title: t('clusters.clusterName'),
    dataIndex: 'clusterName',
    key: 'clusterName',
    ellipsis: true,
    sorter: createSorter<DistributedStorageCluster>('clusterName'),
    render: (name: string, record: DistributedStorageCluster) => {
      const isExpanded = expandedRowKeys.includes(record.clusterName)
      return (
        <ClusterNameCell>
          <ExpandIcon $expanded={isExpanded} />
          <ClusterIcon />
          <ClusterNameText>{name}</ClusterNameText>
        </ClusterNameCell>
      )
    },
  },
  {
    title: t('common:general.team'),
    dataIndex: 'teamName',
    key: 'teamName',
    width: 150,
    ellipsis: true,
    sorter: createSorter<DistributedStorageCluster>('teamName'),
    render: (teamName: string) => <TeamTag>{teamName}</TeamTag>,
  },
  {
    title: t('machines:title'),
    key: 'machineCount',
    width: 160,
    align: 'center',
    render: (_: unknown, record: DistributedStorageCluster) => (
      <MachineManageCell>
        <MachineCountBadge cluster={record} />
        <ManageMachinesButton
          type="link"
          size="small"
          data-testid={`ds-cluster-manage-machines-${record.clusterName}`}
          onClick={(event) => {
            event.stopPropagation()
            onManageMachines(record)
          }}
        >
          {t('machines:manage')}
        </ManageMachinesButton>
      </MachineManageCell>
    ),
  },
  {
    title: t('common:general.vaultVersion'),
    dataIndex: 'vaultVersion',
    key: 'vaultVersion',
    width: 120,
    align: 'center',
    sorter: createSorter<DistributedStorageCluster>('vaultVersion'),
    render: (version: number) => (
      <VersionTag>{t('common:general.versionFormat', { version })}</VersionTag>
    ),
  },
  {
    title: t('common:table.actions'),
    key: 'actions',
    width: 260,
    render: (_: unknown, record: DistributedStorageCluster) => (
      <ActionsContainer>
        <Tooltip title={t('common:actions.edit')}>
          <ActionButton
            type="primary"
            size="small"
            icon={<EditOutlined />}
            data-testid={`ds-cluster-edit-${record.clusterName}`}
            onClick={() => onEditCluster(record)}
            aria-label={t('common:actions.edit')}
          />
        </Tooltip>
        <Dropdown
          menu={{
            items: getClusterFunctionMenuItems(t),
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
          <Tooltip title={t('common:actions.remote')}>
            <ActionButton
              type="primary"
              size="small"
              icon={<FunctionOutlined />}
              data-testid={`ds-cluster-function-dropdown-${record.clusterName}`}
              aria-label={t('common:actions.remote')}
            />
          </Tooltip>
        </Dropdown>
        <Tooltip title={t('common:actions.trace')}>
          <ActionButton
            type="default"
            size="small"
            icon={<HistoryOutlined />}
            data-testid={`ds-cluster-trace-${record.clusterName}`}
            onClick={() => onShowAuditTrace(record)}
            aria-label={t('common:actions.trace')}
          />
        </Tooltip>
        <Tooltip title={t('common:actions.delete')}>
          <ActionButton
            type="primary"
            danger
            size="small"
            icon={<DeleteOutlined />}
            data-testid={`ds-cluster-delete-${record.clusterName}`}
            onClick={() => onDeleteCluster(record)}
            aria-label={t('common:actions.delete')}
          />
        </Tooltip>
      </ActionsContainer>
    ),
  },
]
