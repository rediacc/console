import { Dropdown, Space, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { MenuProps } from 'antd'
import { EllipsisOutlined, CloudUploadOutlined } from '@ant-design/icons'
import { TFunction } from 'i18next'
import { createSorter } from '@/utils/tableSorters'
import type { DistributedStorageRbdSnapshot } from '@/api/queries/distributedStorage'
import {
  ActionButton,
  GuidText,
  NameCell,
  NameIcon,
  NameText,
  VaultTag,
} from './styles'

interface ColumnBuilderParams {
  t: TFunction<'distributedStorage'>
  getSnapshotMenuItems: (snapshot: DistributedStorageRbdSnapshot) => MenuProps['items']
  handleRunFunction: (functionName: string, snapshot: DistributedStorageRbdSnapshot) => void
}

export const buildSnapshotColumns = ({
  t,
  getSnapshotMenuItems,
  handleRunFunction,
}: ColumnBuilderParams): ColumnsType<DistributedStorageRbdSnapshot> => [
  {
    title: t('snapshots.name'),
    dataIndex: 'snapshotName',
    key: 'snapshotName',
    sorter: createSorter<DistributedStorageRbdSnapshot>('snapshotName'),
    render: (text: string, record: DistributedStorageRbdSnapshot) => (
      <NameCell data-testid={`snapshot-list-item-${record.snapshotName}`}>
        <NameIcon />
        <NameText>{text}</NameText>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <VaultTag
              color="blue"
              data-testid={`snapshot-list-vault-indicator-${record.snapshotName}`}
            >
              {t('common.vault')}
            </VaultTag>
          </Tooltip>
        )}
      </NameCell>
    ),
  },
  {
    title: t('snapshots.guid'),
    dataIndex: 'snapshotGuid',
    key: 'snapshotGuid',
    width: 300,
    sorter: createSorter<DistributedStorageRbdSnapshot>('snapshotGuid'),
    render: (text: string) => (
      <Tooltip title={text}>
        <GuidText>{text.substring(0, 8)}...</GuidText>
      </Tooltip>
    ),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 150,
    render: (_: unknown, record: DistributedStorageRbdSnapshot) => (
      <Space>
        <Tooltip title={t('common.remote')}>
          <ActionButton
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => handleRunFunction('distributed_storage_rbd_snapshot_list', record)}
            data-testid={`snapshot-list-remote-${record.snapshotName}`}
            aria-label={t('common.remote')}
          />
        </Tooltip>
        <Dropdown menu={{ items: getSnapshotMenuItems(record) }} trigger={['click']}>
          <ActionButton
            size="small"
            icon={<EllipsisOutlined />}
            data-testid={`snapshot-list-menu-${record.snapshotName}`}
          />
        </Dropdown>
      </Space>
    ),
  },
]
