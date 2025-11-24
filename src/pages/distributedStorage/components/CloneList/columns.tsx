import React from 'react'
import { Tooltip } from 'antd'
import type { ColumnsType } from 'antd/es/table'
import type { MenuProps } from 'antd'
import { EllipsisOutlined, CloudUploadOutlined } from '@ant-design/icons'
import { TFunction } from 'i18next'
import type { DistributedStorageRbdClone } from '@/api/queries/distributedStorage'
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup'
import { CloneIcon, CloneName, NameCell, VaultTag } from './styles'

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
      <ActionButtonGroup
        buttons={[
          {
            type: 'remote',
            icon: <CloudUploadOutlined />,
            tooltip: 'distributedStorage:common.remote',
            label: 'distributedStorage:common.remote',
            onClick: () => handleRunFunction('distributed_storage_rbd_info', record),
            testIdSuffix: 'remote',
          },
          {
            type: 'actions',
            icon: <EllipsisOutlined />,
            tooltip: 'distributedStorage:common.moreActions',
            dropdownItems: getCloneMenuItems(record),
            variant: 'default',
            testIdSuffix: 'actions',
          },
        ]}
        record={record}
        idField="cloneName"
        testIdPrefix="clone-list"
        t={t}
      />
    ),
  },
]
