import { CameraOutlined, CloudUploadOutlined, EllipsisOutlined } from '@ant-design/icons';
import { Tag, Tooltip } from 'antd';
import { TFunction } from 'i18next';
import type { CephRbdSnapshot } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns';
import { createSorter } from '@/platform';
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
      <span
        style={{ display: 'inline-flex', alignItems: 'center', gap: 8 }}
        data-testid={`snapshot-list-item-${record.snapshotName}`}
      >
        <CameraOutlined style={{ fontSize: 16, color: 'var(--ant-color-primary)' }} />
        <span style={{ fontWeight: 400 }}>{text}</span>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <Tag
              data-testid={`snapshot-list-vault-indicator-${record.snapshotName}`}
              bordered={false}
            >
              {t('common.vault')}
            </Tag>
          </Tooltip>
        )}
      </span>
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
