import { EllipsisOutlined } from '@ant-design/icons';
import type { TypedTFunction } from '@rediacc/shared/i18n/types';
import type { GetCephRbdImages_ResultSet1 as CephImage } from '@rediacc/shared/types';
import type { MenuProps } from 'antd';
import { Space, Tag, Tooltip, Typography } from 'antd';
import type { ColumnsType } from 'antd/es/table';
import { ActionButtonGroup } from '@/components/common/ActionButtonGroup';
import { createTruncatedColumn, RESPONSIVE_HIDE_XS } from '@/components/common/columns';
import { createActionColumn } from '@/components/common/columns/factories/action';
import { createSorter } from '@/platform';
import {
  CloudServerOutlined,
  CloudUploadOutlined,
  FileImageOutlined,
} from '@/utils/optimizedIcons';

interface BuildRbdImageColumnsParams {
  t: TypedTFunction;
  handleRunFunction: (functionName: string, image?: CephImage) => void;
  getImageMenuItems: (image: CephImage) => MenuProps['items'];
}

export const buildRbdImageColumns = ({
  t,
  handleRunFunction,
  getImageMenuItems,
}: BuildRbdImageColumnsParams): ColumnsType<CephImage> => [
  {
    title: t('images.name'),
    dataIndex: 'imageName',
    key: 'imageName',
    sorter: createSorter<CephImage>('imageName'),
    render: (text: string, record: CephImage) => (
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
  {
    ...createTruncatedColumn<CephImage>({
      title: t('images.guid'),
      dataIndex: 'imageGuid',
      key: 'imageGuid',
      width: 300,
      maxLength: 8,
      sorter: createSorter<CephImage>('imageGuid'),
      renderText: (value) => value ?? '',
    }),
    responsive: RESPONSIVE_HIDE_XS,
  },
  {
    title: t('images.assignedMachine'),
    dataIndex: 'machineName',
    key: 'machineName',
    width: 200,
    responsive: RESPONSIVE_HIDE_XS,
    sorter: createSorter<CephImage>('machineName'),
    render: (machineName: string, record: CephImage) =>
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
  createActionColumn<CephImage>({
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
