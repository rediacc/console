import React from 'react'
import { Dropdown, Space, Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { MenuProps } from 'antd'
import { EllipsisOutlined, CloudUploadOutlined } from '@ant-design/icons'
import { TFunction } from 'i18next'
import type { DistributedStorageRbdClone } from '@/api/queries/distributedStorage'
import { CloneIcon, CloneName, NameCell, VaultTag, RemoteButton, DropdownButton } from './styles'

interface ColumnBuilderParams {
  t: TFunction<'distributedStorage' | 'common'>
  renderMachineCount: (clone: DistributedStorageRbdClone) => React.ReactNode
  handleRunFunction: (functionName: string, clone?: DistributedStorageRbdClone) => void
  getCloneMenuItems: (clone: DistributedStorageRbdClone) => MenuProps['items']
}

export const buildCloneColumns = ({
  t,
  renderMachineCount,
  handleRunFunction,
  getCloneMenuItems,
}: ColumnBuilderParams): ColumnsType<DistributedStorageRbdClone> => [
  {
    title: t('clones.name'),
    dataIndex: 'cloneName',
    key: 'cloneName',
    render: (text: string, record: DistributedStorageRbdClone) => (
      <NameCell data-testid={`clone-list-item-${record.cloneName}`}>
        <CloneIcon />
        <CloneName>{text}</CloneName>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <VaultTag color="blue" data-testid={`clone-list-vault-tag-${record.cloneName}`}>
              {t('common.vault')}
            </VaultTag>
          </Tooltip>
        )}
      </NameCell>
    ),
  },
  {
    title: t('machines:machines'),
    key: 'machines',
    width: 100,
    align: 'center' as const,
    render: (_: unknown, record: DistributedStorageRbdClone) => renderMachineCount(record),
  },
  {
    title: t('common.actions'),
    key: 'actions',
    width: 180,
    render: (_: unknown, record: DistributedStorageRbdClone) => (
      <Space>
        <Tooltip title={t('common.remote')}>
          <RemoteButton
            size="small"
            icon={<CloudUploadOutlined />}
            onClick={() => handleRunFunction('distributed_storage_rbd_info', record)}
            data-testid={`clone-list-remote-${record.cloneName}`}
          >
            {t('common.remote')}
          </RemoteButton>
        </Tooltip>
        <Dropdown menu={{ items: getCloneMenuItems(record) }} trigger={['click']}>
          <DropdownButton
            size="small"
            icon={<EllipsisOutlined />}
            data-testid={`clone-list-actions-${record.cloneName}`}
          />
        </Dropdown>
      </Space>
    ),
  },
]
