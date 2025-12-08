import { EllipsisOutlined, CloudUploadOutlined } from '@ant-design/icons';
import { Tooltip } from 'antd';
import { TFunction } from 'i18next';
import type { CephRbdSnapshot } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns';
import { RediaccTag } from '@/components/ui';
import { createSorter } from '@/platform';
import { NameCell, NameIcon, NameText } from './styles';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';

interface ColumnBuilderParams {
  t: TFunction<'ceph'>;
  getSnapshotMenuItems: (snapshot: CephRbdSnapshot) => MenuProps['items'];
  handleRunFunction: (functionName: string, snapshot: CephRbdSnapshot) => void;
}

export const buildSnapshotColumns = ({
  t,
  getSnapshotMenuItems,
  handleRunFunction,
}: ColumnBuilderParams): ColumnsType<CephRbdSnapshot> => [
  {
    title: t('snapshots.name'),
    dataIndex: 'snapshotName',
    key: 'snapshotName',
    sorter: createSorter<CephRbdSnapshot>('snapshotName'),
    render: (text: string, record: CephRbdSnapshot) => (
      <NameCell data-testid={`snapshot-list-item-${record.snapshotName}`}>
        <NameIcon />
        <NameText>{text}</NameText>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <RediaccTag
              variant="neutral"
              compact
              data-testid={`snapshot-list-vault-indicator-${record.snapshotName}`}
            >
              {t('common.vault')}
            </RediaccTag>
          </Tooltip>
        )}
      </NameCell>
    ),
  },
  createTruncatedColumn<CephRbdSnapshot>({
    title: t('snapshots.guid'),
    dataIndex: 'snapshotGuid',
    key: 'snapshotGuid',
    width: 300,
    maxLength: 8,
    sorter: createSorter<CephRbdSnapshot>('snapshotGuid'),
    renderText: (value) => value || '',
  }),
  createActionColumn<CephRbdSnapshot>({
    width: 150,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'remote',
            icon: <CloudUploadOutlined />,
            tooltip: 'ceph:common.remote',
            onClick: () => handleRunFunction('ceph_rbd_snapshot_list', record),
            testIdSuffix: 'remote',
          },
          {
            type: 'menu',
            icon: <EllipsisOutlined />,
            tooltip: 'ceph:common.moreActions',
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
