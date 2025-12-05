import { Tooltip } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { MenuProps } from 'antd';
import { EllipsisOutlined, CloudUploadOutlined } from '@ant-design/icons';
import { TFunction } from 'i18next';
import { createSorter } from '@/core';
import type { DistributedStorageRbdSnapshot } from '@/api/queries/distributedStorage';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns';
import { NameCell, NameIcon, NameText, VaultTag } from './styles';

interface ColumnBuilderParams {
  t: TFunction<'distributedStorage'>;
  getSnapshotMenuItems: (snapshot: DistributedStorageRbdSnapshot) => MenuProps['items'];
  handleRunFunction: (functionName: string, snapshot: DistributedStorageRbdSnapshot) => void;
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
  createTruncatedColumn<DistributedStorageRbdSnapshot>({
    title: t('snapshots.guid'),
    dataIndex: 'snapshotGuid',
    key: 'snapshotGuid',
    width: 300,
    maxLength: 8,
    sorter: createSorter<DistributedStorageRbdSnapshot>('snapshotGuid'),
    renderText: (value) => value || '',
  }),
  createActionColumn<DistributedStorageRbdSnapshot>({
    width: 150,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'remote',
            icon: <CloudUploadOutlined />,
            tooltip: 'distributedStorage:common.remote',
            onClick: () => handleRunFunction('distributed_storage_rbd_snapshot_list', record),
            testIdSuffix: 'remote',
          },
          {
            type: 'menu',
            icon: <EllipsisOutlined />,
            tooltip: 'distributedStorage:common.moreActions',
            dropdownItems: getSnapshotMenuItems(record),
            variant: 'default',
            testIdSuffix: 'menu',
          },
        ]}
        record={record}
        idField="snapshotName"
        testIdPrefix="snapshot-list"
        t={t}
      />
    ),
  }),
];
