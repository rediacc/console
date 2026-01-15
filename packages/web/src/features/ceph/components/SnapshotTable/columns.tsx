import { CameraOutlined, CloudUploadOutlined, EllipsisOutlined } from '@ant-design/icons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephRbdSnapshots_ResultSet1 as CephSnapshot } from '@rediacc/shared/types';
import type { MenuProps } from 'antd';
import { Flex, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createTruncatedColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { createSorter } from '@/platform';

interface ColumnBuilderParams {
  t: TypedTFunction;
  getSnapshotMenuItems: (snapshot: CephSnapshot) => MenuProps['items'];
  handleRunFunction: (functionName: string, snapshot: CephSnapshot) => void;
}

export const buildSnapshotColumns = ({
  t,
  getSnapshotMenuItems,
  handleRunFunction,
}: ColumnBuilderParams): ColumnsType<CephSnapshot> => {
  return [
    {
      title: t('snapshots.name'),
      dataIndex: 'snapshotName',
      key: 'snapshotName',
      sorter: createSorter<CephSnapshot>('snapshotName'),
      render: (text: string, record: CephSnapshot) => (
        <Flex
          align="center"
          className="inline-flex"
          data-testid={`snapshot-list-item-${record.snapshotName}`}
        >
          <CameraOutlined />
          <Typography.Text>{text}</Typography.Text>
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
        </Flex>
      ),
    },
    {
      ...createTruncatedColumn<CephSnapshot>({
        title: t('snapshots.guid'),
        dataIndex: 'snapshotGuid',
        key: 'snapshotGuid',
        width: 300,
        maxLength: 8,
        sorter: createSorter<CephSnapshot>('snapshotGuid'),
        renderText: (value) => value ?? '',
      }),
      responsive: RESPONSIVE_HIDE_XS,
    },
    createActionColumn<CephSnapshot>({
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
};
