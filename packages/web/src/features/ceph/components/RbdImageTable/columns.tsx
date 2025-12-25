import { EllipsisOutlined } from '@ant-design/icons';
import { Space, Tag, Tooltip, Typography } from 'antd';
import type { CephRbdImage } from '@/api/queries/ceph';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createActionColumn, createTruncatedColumn } from '@/components/common/columns';
import { createSorter } from '@/platform';
import {
  CloudUploadOutlined,
  CloudServerOutlined,
  FileImageOutlined,
} from '@/utils/optimizedIcons';
import type { MenuProps } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import type { TFunction } from 'i18next';

interface BuildRbdImageColumnsParams {
  t: TFunction<'ceph' | 'common'>;
  handleRunFunction: (functionName: string, image?: CephRbdImage) => void;
  getImageMenuItems: (image: CephRbdImage) => MenuProps['items'];
}

export const buildRbdImageColumns = ({
  t,
  handleRunFunction,
  getImageMenuItems,
}: BuildRbdImageColumnsParams): ColumnsType<CephRbdImage> => [
  {
    title: t('images.name'),
    dataIndex: 'imageName',
    key: 'imageName',
    sorter: createSorter<CephRbdImage>('imageName'),
    render: (text: string, record: CephRbdImage) => (
      <Space data-testid={`rbd-image-name-${record.imageName}`}>
        <FileImageOutlined />
        <Typography.Text>{text}</Typography.Text>
        {record.vaultContent && (
          <Tooltip title={t('common.hasVault')}>
            <Tag data-testid={`rbd-vault-tag-${record.imageName}`}>{t('common.vault')}</Tag>
          </Tooltip>
        )}
      </Space>
    ),
  },
  createTruncatedColumn<CephRbdImage>({
    title: t('images.guid'),
    dataIndex: 'imageGuid',
    key: 'imageGuid',
    width: 300,
    maxLength: 8,
    sorter: createSorter<CephRbdImage>('imageGuid'),
    renderText: (value) => value ?? '',
  }),
  {
    title: t('images.assignedMachine'),
    dataIndex: 'machineName',
    key: 'machineName',
    width: 200,
    sorter: createSorter<CephRbdImage>('machineName'),
    render: (machineName: string, record: CephRbdImage) =>
      machineName ? (
        <Tag
          icon={<CloudServerOutlined />}
          bordered={false}
          data-testid={`rbd-machine-tag-${record.imageName}`}
        >
          {machineName}
        </Tag>
      ) : (
        <Tag data-testid={`rbd-machine-none-${record.imageName}`} bordered={false}>
          {t('common.none')}
        </Tag>
      ),
  },
  createActionColumn<CephRbdImage>({
    width: 150,
    renderActions: (record) => (
      <ActionButtonGroup
        buttons={[
          {
            type: 'remote',
            icon: <CloudUploadOutlined />,
            tooltip: 'ceph:common.remote',
            onClick: () => handleRunFunction('ceph_rbd_info', record),
            testIdSuffix: 'remote-button',
          },
          {
            type: 'actions',
            icon: <EllipsisOutlined />,
            tooltip: 'ceph:common.moreActions',
            dropdownItems: getImageMenuItems(record),
            variant: 'default',
            testIdSuffix: 'actions-dropdown',
          },
        ]}
        record={record}
        idField="imageName"
        testIdPrefix="rbd"
        t={t}
      />
    ),
  }),
];
